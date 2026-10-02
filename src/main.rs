//! Перебор TON-кошельков (WalletV4R2, workchain 0) до адреса с нужным окончанием.
//!
//! Адрес в user-friendly виде = base64url(flag | wc | hash(32) | crc16), ровно 48 символов,
//! поэтому последние k символов - это последние 6k бит (хвост хеша + CRC16).
//! Горячий цикл поэтому не строит строку, а сравнивает целое число.

use curve25519_dalek::{constants::ED25519_BASEPOINT_TABLE, scalar::Scalar};
use rand_chacha::{rand_core::{RngCore, SeedableRng}, ChaCha20Rng};
use sha2::{compress256, digest::generic_array::GenericArray, Digest, Sha256, Sha512};
use std::{
    fs::OpenOptions,
    io::Write,
    sync::{
        atomic::{AtomicBool, AtomicU64, Ordering::Relaxed},
        mpsc, Arc,
    },
    time::{Duration, Instant},
};

/// Версия кошелька. Хеши кода и глубины сверены с tonsdk (v4R2) и tonutils (v5R1).
#[derive(Clone, Copy, PartialEq, Eq)]
enum Wallet {
    V4R2,
    V5R1,
}

const V4R2_CODE_HASH: [u8; 32] = [
    0xfe, 0xb5, 0xff, 0x68, 0x20, 0xe2, 0xff, 0x0d, 0x94, 0x83, 0xe7, 0xe0, 0xd6, 0x2c, 0x81, 0x7d,
    0x84, 0x67, 0x89, 0xfb, 0x4a, 0xe5, 0x80, 0xc8, 0x78, 0x86, 0x6d, 0x95, 0x9d, 0xab, 0xd5, 0xc0,
];
const V5R1_CODE_HASH: [u8; 32] = [
    0x20, 0x83, 0x4b, 0x7b, 0x72, 0xb1, 0x12, 0x14, 0x7e, 0x1b, 0x2f, 0xb4, 0x57, 0xb8, 0x4e, 0x74,
    0xd1, 0xa3, 0x0f, 0x04, 0xf7, 0x37, 0xd4, 0xf6, 0x2a, 0x66, 0x8e, 0x95, 0x52, 0xd2, 0xb7, 0x2f,
];

impl Wallet {
    fn code_hash(self) -> &'static [u8; 32] {
        match self { Wallet::V4R2 => &V4R2_CODE_HASH, Wallet::V5R1 => &V5R1_CODE_HASH }
    }
    fn code_depth(self) -> u8 {
        match self { Wallet::V4R2 => 7, Wallet::V5R1 => 6 }
    }
    fn name(self) -> &'static str {
        match self { Wallet::V4R2 => "v4R2", Wallet::V5R1 => "v5R1" }
    }
    /// Стандартный wallet_id: v4R2 - 698983191; v5R1 (mainnet, workchain 0) - 2147483409.
    fn default_wallet_id(self) -> u32 {
        match self { Wallet::V4R2 => 698_983_191, Wallet::V5R1 => 0x7FFF_FF11 }
    }
    /// j-й субкошелёк: v4 - сложение, v5 - XOR в 15-битном поле номера субкошелька.
    fn wallet_id(self, j: u32) -> u32 {
        match self { Wallet::V4R2 => self.default_wallet_id().wrapping_add(j), Wallet::V5R1 => self.default_wallet_id() ^ (j & 0x7FFF) }
    }
    fn max_subwallets(self) -> u32 {
        match self { Wallet::V4R2 => u32::MAX, Wallet::V5R1 => 0x8000 }
    }
    fn parse(s: &str) -> Option<Wallet> {
        match s.to_ascii_lowercase().as_str() { "v4" | "v4r2" => Some(Wallet::V4R2), "v5" | "v5r1" => Some(Wallet::V5R1), _ => None }
    }
}
const FLAG_BOUNCEABLE: u8 = 0x11;
const FLAG_NON_BOUNCEABLE: u8 = 0x51;
const FLAGS: [u8; 2] = [FLAG_BOUNCEABLE, FLAG_NON_BOUNCEABLE];
const B64: &[u8; 64] = b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_";
const SHA256_IV: [u32; 8] = [
    0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a, 0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19,
];
const BATCH: u64 = 512; // ключей между обновлениями общего счётчика

// ---------- CRC16/XMODEM ----------

const fn make_crc_table() -> [u16; 256] {
    let mut t = [0u16; 256];
    let mut i = 0;
    while i < 256 {
        let mut c = (i as u16) << 8;
        let mut j = 0;
        while j < 8 {
            c = if c & 0x8000 != 0 { (c << 1) ^ 0x1021 } else { c << 1 };
            j += 1;
        }
        t[i] = c;
        i += 1;
    }
    t
}
static CRC_TABLE: [u16; 256] = make_crc_table();

#[inline(always)]
fn crc16(init: u16, data: &[u8]) -> u16 {
    let mut c = init;
    for &b in data {
        c = (c << 8) ^ CRC_TABLE[((c >> 8) as u8 ^ b) as usize];
    }
    c
}

/// CRC линеен: crc([flag,wc,hash]) = crc0(hash) ^ K[flag], где K = crc([flag,wc,0*32]).
/// Так CRC хеша считается один раз для обоих флагов.
fn crc_consts() -> [u16; 2] {
    let mut k = [0u16; 2];
    for (i, f) in FLAGS.iter().enumerate() {
        let mut m = [0u8; 34];
        m[0] = *f;
        k[i] = crc16(0, &m);
    }
    k
}

// ---------- адрес ----------

#[inline(always)]
fn compress(blocks: &[[u8; 64]], mut st: [u32; 8]) -> [u32; 8] {
    for b in blocks {
        compress256(&mut st, std::slice::from_ref(GenericArray::from_slice(b)));
    }
    st
}

/// Быстрый расчёт адресного хеша с готовыми шаблонами блоков SHA-256.
struct AddrHasher {
    wallet: Wallet,
    pk: [u8; 32],
    a: [u8; 64],  // ячейка data (43 байта + паддинг)
    b1: [u8; 64], // ячейка StateInit, блок 1
    b2: [u8; 64], // блок 2
}

impl AddrHasher {
    fn new(wallet: Wallet) -> Self {
        // d2 = floor(bits/8) + ceil(bits/8) = 81 и 41 байт данных (с завершающим тегом) у обоих кошельков:
        // v4R2 - 321 бит, v5R1 - 322 бита.
        let mut a = [0u8; 64];
        a[1] = 0x51;
        a[43] = 0x80;
        a[56..].copy_from_slice(&(43u64 * 8).to_be_bytes());
        let mut b1 = [0u8; 64];
        b1[..7].copy_from_slice(&[0x02, 0x01, 0x34, 0, wallet.code_depth(), 0, 0]);
        b1[7..39].copy_from_slice(wallet.code_hash());
        let mut b2 = [0u8; 64];
        b2[7] = 0x80;
        b2[56..].copy_from_slice(&(71u64 * 8).to_be_bytes());
        Self { wallet, pk: [0; 32], a, b1, b2 }
    }

    #[inline(always)]
    fn set_pubkey(&mut self, pk: &[u8; 32]) {
        self.pk = *pk;
        if self.wallet == Wallet::V4R2 {
            self.a[10..42].copy_from_slice(pk);
            self.a[42] = 0x40; // бит «плагины пусты» + тег
        }
    }

    #[inline(always)]
    fn address_hash(&mut self, wallet_id: u32) -> [u8; 32] {
        match self.wallet {
            Wallet::V4R2 => self.a[6..10].copy_from_slice(&wallet_id.to_be_bytes()),
            Wallet::V5R1 => {
                // биты: 1 (подпись разрешена) | seqno=0 (32) | wallet_id (32) | pubkey (256) | 0 (расширения) | тег 1
                let d = &mut self.a[2..43];
                d[0] = 0x80;
                d[1] = 0;
                d[2] = 0;
                d[3] = 0;
                d[4] = ((wallet_id >> 25) & 0x7f) as u8;
                d[5] = (wallet_id >> 17) as u8;
                d[6] = (wallet_id >> 9) as u8;
                d[7] = (wallet_id >> 1) as u8;
                d[8] = ((wallet_id & 1) << 7) as u8 | self.pk[0] >> 1;
                for i in 1..32 {
                    d[8 + i] = self.pk[i - 1] << 7 | self.pk[i] >> 1;
                }
                d[40] = (self.pk[31] & 1) << 7 | 0x20;
            }
        }
        let d = compress(&[self.a], SHA256_IV);
        let mut dh = [0u8; 32];
        for i in 0..8 {
            dh[i * 4..i * 4 + 4].copy_from_slice(&d[i].to_be_bytes());
        }
        self.b1[39..].copy_from_slice(&dh[..25]);
        self.b2[..7].copy_from_slice(&dh[25..]);
        let h = compress(&[self.b1, self.b2], SHA256_IV);
        let mut out = [0u8; 32];
        for i in 0..8 {
            out[i * 4..i * 4 + 4].copy_from_slice(&h[i].to_be_bytes());
        }
        out
    }
}

/// Медленный эталон через обычный Digest - для проверки найденного результата и тестов.
fn address_hash_slow(wallet: Wallet, pk: &[u8; 32], wallet_id: u32) -> [u8; 32] {
    // независимая от быстрого пути сборка data-ячейки через побитовый записыватель
    let mut bits: Vec<bool> = Vec::new();
    let mut put = |v: u64, n: u32| (0..n).rev().for_each(|i| bits.push(v >> i & 1 == 1));
    if wallet == Wallet::V5R1 {
        put(1, 1); // подпись разрешена
    }
    put(0, 32); // seqno
    put(wallet_id as u64, 32);
    pk.iter().for_each(|&b| put(b as u64, 8));
    put(0, 1); // v4: плагины, v5: расширения - пусто
    let nbits = bits.len();
    let (d2, mut data) = ((nbits / 8 + (nbits + 7) / 8) as u8, vec![0u8; (nbits + 7) / 8]);
    for (i, b) in bits.iter().enumerate() {
        if *b { data[i / 8] |= 0x80 >> (i % 8); }
    }
    if nbits % 8 != 0 {
        data[nbits / 8] |= 0x80 >> (nbits % 8); // завершающий тег внутри последнего байта
    }
    let mut cell = vec![0u8, d2];
    cell.extend_from_slice(&data);
    let dh = Sha256::digest(&cell);
    let mut st = vec![0x02u8, 0x01, 0x34, 0, wallet.code_depth(), 0, 0];
    st.extend_from_slice(wallet.code_hash());
    st.extend_from_slice(&dh);
    Sha256::digest(&st).into()
}

fn friendly(flag: u8, hash: &[u8; 32]) -> String {
    let mut p = [0u8; 36];
    p[0] = flag;
    p[2..34].copy_from_slice(hash);
    let c = crc16(0, &p[..34]);
    p[34..].copy_from_slice(&c.to_be_bytes());
    let mut s = String::with_capacity(48);
    for ch in p.chunks(3) {
        let n = (ch[0] as u32) << 16 | (ch[1] as u32) << 8 | ch[2] as u32;
        for sh in [18, 12, 6, 0] {
            s.push(B64[(n >> sh & 63) as usize] as char);
        }
    }
    s
}

// ---------- ключи ----------

#[inline(always)]
fn pubkey_from_seed(seed: &[u8; 32]) -> [u8; 32] {
    let h = Sha512::digest(seed);
    let mut k = [0u8; 32];
    k.copy_from_slice(&h[..32]);
    k[0] &= 248;
    k[31] &= 127;
    k[31] |= 64;
    (&Scalar::from_bytes_mod_order(k) * ED25519_BASEPOINT_TABLE)
        .compress()
        .to_bytes()
}

// ---------- поиск ----------

struct Cfg {
    suffix: String,
    targets: Vec<u64>, // отсортированы
    mask: u64,
    subwallets: u32,
    wallet: Wallet,
}

struct Hit {
    seed: [u8; 32],
    pubkey: [u8; 32],
    wallet_id: u32,
    hash: [u8; 32],
}

/// 13_630_000 -> "13.6M", 581_518 -> "582k"
fn human(x: f64) -> String {
    let (v, u) = match x {
        x if x >= 1e12 => (x / 1e12, "T"),
        x if x >= 1e9 => (x / 1e9, "B"),
        x if x >= 1e6 => (x / 1e6, "M"),
        x if x >= 1e3 => (x / 1e3, "k"),
        x => (x, ""),
    };
    if v >= 100.0 || u.is_empty() { format!("{v:.0}{u}") } else { format!("{v:.1}{u}") }
}

fn hex(b: &[u8]) -> String {
    b.iter().map(|x| format!("{x:02x}")).collect()
}

fn b64_val(c: u8) -> Option<u64> {
    B64.iter().position(|&x| x == c).map(|p| p as u64)
}

fn build_targets(suffix: &str, nocase: bool) -> Result<Vec<u64>, String> {
    if suffix.is_empty() || suffix.len() > 10 {
        return Err("суффикс должен быть длиной 1..10 символов".into());
    }
    let mut variants: Vec<Vec<u8>> = vec![vec![]];
    for c in suffix.bytes() {
        let opts: Vec<u8> = if nocase && c.is_ascii_alphabetic() {
            vec![c.to_ascii_lowercase(), c.to_ascii_uppercase()]
        } else {
            vec![c]
        };
        variants = variants
            .into_iter()
            .flat_map(|v| opts.iter().map(move |&o| { let mut n = v.clone(); n.push(o); n }))
            .collect();
    }
    let mut t = Vec::new();
    for v in variants {
        let mut acc = 0u64;
        for c in v {
            acc = acc << 6 | b64_val(c).ok_or_else(|| format!("символ '{}' недопустим в base64url (A-Z a-z 0-9 - _)", c as char))?;
        }
        t.push(acc);
    }
    t.sort_unstable();
    t.dedup();
    Ok(t)
}

fn worker(cfg: Arc<Cfg>, stop: Arc<AtomicBool>, total: Arc<AtomicU64>, tx: mpsc::Sender<Hit>) {
    let mut os = [0u8; 32];
    getrandom::getrandom(&mut os).expect("нет источника случайности ОС");
    let mut rng = ChaCha20Rng::from_seed(os);
    let k = crc_consts();
    let mut hasher = AddrHasher::new(cfg.wallet);
    let single = (cfg.targets.len() == 1).then(|| cfg.targets[0]);
    let mask = cfg.mask;
    let nsub = cfg.subwallets;
    let mut seed = [0u8; 32];

    while !stop.load(Relaxed) {
        for _ in 0..BATCH {
            rng.fill_bytes(&mut seed);
            let pk = pubkey_from_seed(&seed);
            hasher.set_pubkey(&pk);
            for j in 0..nsub {
                let wid = cfg.wallet.wallet_id(j);
                let h = hasher.address_hash(wid);
                let crc0 = crc16(0, &h);
                let tail = u64::from_be_bytes(h[24..32].try_into().unwrap()) << 16;
                for ki in k {
                    let v = (tail | (crc0 ^ ki) as u64) & mask;
                    let hit = match single {
                        Some(t) => v == t,
                        None => cfg.targets.binary_search(&v).is_ok(),
                    };
                    if hit {
                        let _ = tx.send(Hit { seed, pubkey: pk, wallet_id: wid, hash: h });
                        stop.store(true, Relaxed);
                        return;
                    }
                }
            }
        }
        total.fetch_add(BATCH * nsub as u64, Relaxed);
    }
}

fn usage() -> ! {
    eprintln!(
        "Использование: ton-vanity [--suffix pulse] [--nocase] [--threads N] [--wallet v5|v4] [--subwallets N] [--out found.txt]\n\
         \n       ton-vanity verify <seed_hex> [v5|v4] [wallet_id]\n\
         \n  --suffix S       нужное окончание адреса (по умолчанию pulse, регистр важен)\n\
         \n  --nocase         игнорировать регистр (гораздо быстрее)\n\
         \n  --threads N      число потоков (по умолчанию - все ядра)\n\
         \n  --subwallets N   на каждый ключ перебирать N subwallet_id (быстрее ~ в N раз, но wallet_id будет нестандартным!)\n\
         \n  --wallet W       версия кошелька: v5 (v5R1, по умолчанию) или v4 (v4R2)\n\
         \n  --out FILE       куда дописывать результат (по умолчанию found.txt)"
    );
    std::process::exit(2)
}

/// `ton-vanity verify <seed_hex> [v5|v4] [wallet_id]` - независимо пересчитать адрес по seed.
fn verify(args: &[String]) {
    let raw = args.get(0).map(|s| s.trim()).unwrap_or_else(|| usage());
    if raw.len() != 64 || !raw.is_ascii() {
        eprintln!("seed - это 64 hex-символа");
        std::process::exit(2);
    }
    let mut seed = [0u8; 32];
    for i in 0..32 {
        seed[i] = u8::from_str_radix(&raw[i * 2..i * 2 + 2], 16).unwrap_or_else(|_| usage());
    }
    let mut wallet = Wallet::V5R1;
    let mut wid = None;
    for a in &args[1..] {
        match Wallet::parse(a) {
            Some(w) => wallet = w,
            None => wid = Some(a.parse::<u32>().unwrap_or_else(|_| usage())),
        }
    }
    let wid = wid.unwrap_or(wallet.default_wallet_id());
    let pk = pubkey_from_seed(&seed);
    let h = address_hash_slow(wallet, &pk, wid);
    println!("wallet: {}, wallet_id {}", wallet.name(), wid);
    println!("bounceable    (EQ..): {}", friendly(FLAG_BOUNCEABLE, &h));
    println!("non-bounceable (UQ..): {}", friendly(FLAG_NON_BOUNCEABLE, &h));
    println!("public key: {}", hex(&pk));
}

fn main() {
    let argv: Vec<String> = std::env::args().skip(1).collect();
    if argv.first().map(|s| s.as_str()) == Some("verify") {
        return verify(&argv[1..]);
    }
    let mut suffix = "pulse".to_string();
    let mut nocase = false;
    let mut threads = std::thread::available_parallelism().map(|n| n.get()).unwrap_or(1);
    let mut subwallets = 1u32;
    let mut wallet = Wallet::V5R1;
    let mut out = "found.txt".to_string();
    let mut args = std::env::args().skip(1);
    while let Some(a) = args.next() {
        let mut val = || args.next().unwrap_or_else(|| usage());
        match a.as_str() {
            "--suffix" => suffix = val(),
            "--nocase" => nocase = true,
            "--threads" => threads = val().parse().unwrap_or_else(|_| usage()),
            "--subwallets" => subwallets = val().parse().unwrap_or_else(|_| usage()),
            "--wallet" => wallet = Wallet::parse(&val()).unwrap_or_else(|| usage()),
            "--out" => out = val(),
            _ => usage(),
        }
    }
    if threads == 0 || subwallets == 0 || subwallets > wallet.max_subwallets() {
        usage();
    }
    let targets = build_targets(&suffix, nocase).unwrap_or_else(|e| {
        eprintln!("Ошибка: {e}");
        std::process::exit(2)
    });
    let cfg = Arc::new(Cfg {
        mask: (1u64 << (6 * suffix.len())) - 1,
        targets,
        suffix: suffix.clone(),
        subwallets,
        wallet,
    });

    // вероятность успеха одной проверки: 2 флага * |targets| / 64^k
    let p = 2.0 * cfg.targets.len() as f64 / 64f64.powi(suffix.len() as i32);
    println!(
        "Кошелёк {}. Ищу адрес на \"{suffix}\"{}; потоков: {threads}; ожидаемо ~{} проверок (50% шанс за {})",
        wallet.name(),
        if nocase { " (без учёта регистра)" } else { "" },
        human(1.0 / p),
        human(std::f64::consts::LN_2 / p)
    );

    let stop = Arc::new(AtomicBool::new(false));
    let total = Arc::new(AtomicU64::new(0));
    let (tx, rx) = mpsc::channel();
    let handles: Vec<_> = (0..threads)
        .map(|_| {
            let (c, s, t, tx) = (cfg.clone(), stop.clone(), total.clone(), tx.clone());
            std::thread::spawn(move || worker(c, s, t, tx))
        })
        .collect();
    drop(tx);

    let start = Instant::now();
    let hit = loop {
        match rx.recv_timeout(Duration::from_secs(2)) {
            Ok(h) => break h,
            Err(mpsc::RecvTimeoutError::Timeout) => {
                let n = total.load(Relaxed);
                let secs = start.elapsed().as_secs_f64();
                eprint!(
                    "\r{} проверок, {}/с, вероятность найти к этому моменту {:.1}%   ",
                    human(n as f64),
                    human(n as f64 / secs),
                    (1.0 - (-p * n as f64).exp()) * 100.0
                );
            }
            Err(mpsc::RecvTimeoutError::Disconnected) => unreachable!(),
        }
    };
    for h in handles {
        let _ = h.join();
    }
    eprintln!();

    // независимая перепроверка медленным путём
    let slow = address_hash_slow(wallet, &hit.pubkey, hit.wallet_id);
    assert_eq!(slow, hit.hash, "внутренняя ошибка: быстрый и эталонный хеши расходятся");
    assert_eq!(pubkey_from_seed(&hit.seed), hit.pubkey);

    let matches = |s: &str| {
        if nocase { s.to_lowercase().ends_with(&cfg.suffix.to_lowercase()) } else { s.ends_with(&cfg.suffix) }
    };
    let mut report = String::new();
    for (name, flag) in [("bounceable    (EQ..)", FLAG_BOUNCEABLE), ("non-bounceable (UQ..)", FLAG_NON_BOUNCEABLE)] {
        let a = friendly(flag, &slow);
        report += &format!("{name}: {a}{}\n", if matches(&a) { "   <== нужное окончание" } else { "" });
    }
    report += &format!("raw:            0:{}\n", hex(&slow));
    report += &format!("wallet:         {}, workchain 0, wallet_id {}\n", wallet.name(), hit.wallet_id);
    report += &format!("public key:     {}\n", hex(&hit.pubkey));
    report += &format!("private seed:   {}\n", hex(&hit.seed));
    report += &format!("secret (seed||pub): {}{}\n", hex(&hit.seed), hex(&hit.pubkey));
    let secs = start.elapsed().as_secs_f64();
    report += &format!("найдено за {:.1} с, {} проверок\n", secs, human(total.load(Relaxed) as f64));
    print!("\n{report}");

    #[cfg(unix)]
    let file = {
        use std::os::unix::fs::OpenOptionsExt;
        OpenOptions::new().create(true).append(true).mode(0o600).open(&out)
    };
    #[cfg(not(unix))]
    let file = OpenOptions::new().create(true).append(true).open(&out);
    match file.and_then(|mut f| writeln!(f, "{report}")) {
        Ok(()) => eprintln!("Результат дописан в {out} (содержит приватный ключ - храните в секрете)"),
        Err(e) => eprintln!("Не удалось записать {out}: {e}"),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn pk0() -> [u8; 32] {
        std::array::from_fn(|i| i as u8)
    }

    #[test]
    fn matches_tonsdk_vector() {
        // v4R2: эталон tonsdk
        let mut h = AddrHasher::new(Wallet::V4R2);
        h.set_pubkey(&pk0());
        let wid = Wallet::V4R2.default_wallet_id();
        let fast = h.address_hash(wid);
        assert_eq!(hex(&fast), "7c380f242a59749f692f522934c3dd60ff1def38555349861702bb1ca9258623");
        assert_eq!(fast, address_hash_slow(Wallet::V4R2, &pk0(), wid));
        assert_eq!(friendly(FLAG_NON_BOUNCEABLE, &fast), "UQB8OA8kKll0n2kvUik0w91g_x3vOFVTSYYXArscqSWGI8My");
    }

    #[test]
    fn matches_tonutils_v5_vector() {
        // v5R1: эталон tonutils/ton_core; wallet_id mainnet = 2147483409, субкошелёк 5 -> XOR 5
        let mut h = AddrHasher::new(Wallet::V5R1);
        h.set_pubkey(&pk0());
        let wid = Wallet::V5R1.default_wallet_id();
        assert_eq!(wid, 2147483409);
        let fast = h.address_hash(wid);
        assert_eq!(hex(&fast), "6dfe165a8f27095f7206fea75bd22e890441dc486493987c2278ffd2c620818c");
        assert_eq!(fast, address_hash_slow(Wallet::V5R1, &pk0(), wid));
        assert_eq!(friendly(FLAG_NON_BOUNCEABLE, &fast), "UQBt_hZajycJX3IG_qdb0i6JBEHcSGSTmHwieP_SxiCBjJ_5");
        assert_eq!(friendly(FLAG_BOUNCEABLE, &fast), "EQBt_hZajycJX3IG_qdb0i6JBEHcSGSTmHwieP_SxiCBjMI8");
        let w5 = Wallet::V5R1.wallet_id(5);
        assert_eq!(w5, 2147483412);
        assert_eq!(hex(&h.address_hash(w5)), "135014d0995b60e4cfe1367554da7c70db2ac9530f1df95126da4f8371baf16b");
    }

    #[test]
    fn fast_equals_slow_random() {
        // быстрый путь (со сдвигами битов) против побитового эталона на разных ключах и wallet_id
        let mut x = 0x9E3779B97F4A7C15u64;
        let mut next = || { x ^= x << 13; x ^= x >> 7; x ^= x << 17; x };
        for w in [Wallet::V4R2, Wallet::V5R1] {
            let mut h = AddrHasher::new(w);
            for _ in 0..2000 {
                let mut pk = [0u8; 32];
                pk.chunks_mut(8).for_each(|c| c.copy_from_slice(&next().to_le_bytes()));
                h.set_pubkey(&pk);
                for wid in [next() as u32, w.default_wallet_id(), w.wallet_id(next() as u32 & 0x7fff)] {
                    assert_eq!(h.address_hash(wid), address_hash_slow(w, &pk, wid));
                }
            }
        }
    }

    #[test]
    fn crc_trick_equals_naive() {
        let k = crc_consts();
        let h: [u8; 32] = std::array::from_fn(|i| (i * 37 + 11) as u8);
        for (i, f) in FLAGS.iter().enumerate() {
            let mut m = vec![*f, 0];
            m.extend_from_slice(&h);
            assert_eq!(crc16(0, &m), crc16(0, &h) ^ k[i]);
        }
    }

    #[test]
    fn tail_compare_equals_string_suffix() {
        // 3-символьный суффикс: сравнение числа должно совпадать со сравнением строки
        let t = build_targets("aB_", false).unwrap()[0];
        let mask = (1u64 << 18) - 1;
        let k = crc_consts();
        let mut found = 0;
        for n in 0..200_000u32 {
            let h: [u8; 32] = Sha256::digest(n.to_be_bytes()).into();
            let crc0 = crc16(0, &h);
            let tail = u64::from_be_bytes(h[24..32].try_into().unwrap()) << 16;
            for (i, f) in FLAGS.iter().enumerate() {
                let fast = (tail | (crc0 ^ k[i]) as u64) & mask == t;
                assert_eq!(fast, friendly(*f, &h).ends_with("aB_"));
                found += fast as u32;
            }
        }
        assert!(found > 0);
    }

    #[test]
    fn seed_to_pubkey_rfc8032() {
        // RFC 8032, test 1
        let seed: [u8; 32] = hex_to_32("9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60");
        assert_eq!(hex(&pubkey_from_seed(&seed)), "d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a");
    }

    fn hex_to_32(s: &str) -> [u8; 32] {
        std::array::from_fn(|i| u8::from_str_radix(&s[i * 2..i * 2 + 2], 16).unwrap())
    }
}
