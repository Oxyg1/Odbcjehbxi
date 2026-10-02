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

/// Хеш и глубина кода WalletV4R2 (проверено по tonsdk).
const CODE_HASH: [u8; 32] = [
    0xfe, 0xb5, 0xff, 0x68, 0x20, 0xe2, 0xff, 0x0d, 0x94, 0x83, 0xe7, 0xe0, 0xd6, 0x2c, 0x81, 0x7d,
    0x84, 0x67, 0x89, 0xfb, 0x4a, 0xe5, 0x80, 0xc8, 0x78, 0x86, 0x6d, 0x95, 0x9d, 0xab, 0xd5, 0xc0,
];
const CODE_DEPTH: u16 = 7;
const DEFAULT_WALLET_ID: u32 = 698_983_191;
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
    a: [u8; 64],  // ячейка data (43 байта + паддинг)
    b1: [u8; 64], // ячейка StateInit, блок 1
    b2: [u8; 64], // блок 2
}

impl AddrHasher {
    fn new() -> Self {
        let mut a = [0u8; 64];
        a[1] = 0x51; // d2 = ceil(321/8) + floor(321/8)
        a[42] = 0x40; // 1 бит (пустые плагины) + завершающий тег
        a[43] = 0x80;
        a[56..].copy_from_slice(&(43u64 * 8).to_be_bytes());
        let mut b1 = [0u8; 64];
        b1[..7].copy_from_slice(&[0x02, 0x01, 0x34, (CODE_DEPTH >> 8) as u8, CODE_DEPTH as u8, 0, 0]);
        b1[7..39].copy_from_slice(&CODE_HASH);
        let mut b2 = [0u8; 64];
        b2[7] = 0x80;
        b2[56..].copy_from_slice(&(71u64 * 8).to_be_bytes());
        Self { a, b1, b2 }
    }

    #[inline(always)]
    fn set_pubkey(&mut self, pk: &[u8; 32]) {
        self.a[10..42].copy_from_slice(pk);
    }

    #[inline(always)]
    fn address_hash(&mut self, wallet_id: u32) -> [u8; 32] {
        self.a[6..10].copy_from_slice(&wallet_id.to_be_bytes());
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
fn address_hash_slow(pk: &[u8; 32], wallet_id: u32) -> [u8; 32] {
    let mut data = vec![0u8, 0x51, 0, 0, 0, 0];
    data.extend_from_slice(&wallet_id.to_be_bytes());
    data.extend_from_slice(pk);
    data.push(0x40);
    let dh = Sha256::digest(&data);
    let mut st = vec![0x02u8, 0x01, 0x34, 0, CODE_DEPTH as u8, 0, 0];
    st.extend_from_slice(&CODE_HASH);
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
}

struct Hit {
    seed: [u8; 32],
    pubkey: [u8; 32],
    wallet_id: u32,
    hash: [u8; 32],
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
    let mut hasher = AddrHasher::new();
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
                let wid = DEFAULT_WALLET_ID.wrapping_add(j);
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
        "Использование: ton-vanity [--suffix pulse] [--nocase] [--threads N] [--subwallets N] [--out found.txt]\n\
         \n  --suffix S       нужное окончание адреса (по умолчанию pulse, регистр важен)\n\
         \n  --nocase         игнорировать регистр (гораздо быстрее)\n\
         \n  --threads N      число потоков (по умолчанию - все ядра)\n\
         \n  --subwallets N   на каждый ключ перебирать N subwallet_id (быстрее ~ в N раз, но wallet_id будет нестандартным!)\n\
         \n  --out FILE       куда дописывать результат (по умолчанию found.txt)"
    );
    std::process::exit(2)
}

fn main() {
    let mut suffix = "pulse".to_string();
    let mut nocase = false;
    let mut threads = std::thread::available_parallelism().map(|n| n.get()).unwrap_or(1);
    let mut subwallets = 1u32;
    let mut out = "found.txt".to_string();
    let mut args = std::env::args().skip(1);
    while let Some(a) = args.next() {
        let mut val = || args.next().unwrap_or_else(|| usage());
        match a.as_str() {
            "--suffix" => suffix = val(),
            "--nocase" => nocase = true,
            "--threads" => threads = val().parse().unwrap_or_else(|_| usage()),
            "--subwallets" => subwallets = val().parse().unwrap_or_else(|_| usage()),
            "--out" => out = val(),
            _ => usage(),
        }
    }
    if threads == 0 || subwallets == 0 {
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
    });

    // вероятность успеха одной проверки: 2 флага * |targets| / 64^k
    let p = 2.0 * cfg.targets.len() as f64 / 64f64.powi(suffix.len() as i32);
    println!(
        "Ищу адрес на \"{suffix}\"{}; потоков: {threads}; ожидаемо ~{:.2e} проверок (50% шанс за {:.2e})",
        if nocase { " (без учёта регистра)" } else { "" },
        1.0 / p,
        std::f64::consts::LN_2 / p
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
                    "\r{:.3e} проверок, {:.0}/с, вероятность найти к этому моменту {:.1}%   ",
                    n as f64,
                    n as f64 / secs,
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
    let slow = address_hash_slow(&hit.pubkey, hit.wallet_id);
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
    report += &format!("wallet:         v4R2, workchain 0, wallet_id {}\n", hit.wallet_id);
    report += &format!("public key:     {}\n", hex(&hit.pubkey));
    report += &format!("private seed:   {}\n", hex(&hit.seed));
    report += &format!("secret (seed||pub): {}{}\n", hex(&hit.seed), hex(&hit.pubkey));
    let secs = start.elapsed().as_secs_f64();
    report += &format!("найдено за {:.1} с, {:.3e} проверок\n", secs, total.load(Relaxed) as f64);
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
        let mut h = AddrHasher::new();
        h.set_pubkey(&pk0());
        let fast = h.address_hash(DEFAULT_WALLET_ID);
        assert_eq!(hex(&fast), "7c380f242a59749f692f522934c3dd60ff1def38555349861702bb1ca9258623");
        assert_eq!(fast, address_hash_slow(&pk0(), DEFAULT_WALLET_ID));
        assert_eq!(friendly(FLAG_NON_BOUNCEABLE, &fast), "UQB8OA8kKll0n2kvUik0w91g_x3vOFVTSYYXArscqSWGI8My");
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
