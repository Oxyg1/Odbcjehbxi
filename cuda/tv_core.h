// Ядро поиска TON-адресов (WalletV4R2). Один и тот же код компилируется
//   - nvcc-ом как __host__ __device__ (GPU-ядро и проверка на хосте),
//   - обычным g++/clang++ (тесты на CPU и эмуляция ядра без видеокарты).
#pragma once
#include <stdint.h>
#include <string.h>
#include "tv_consts.h"

#ifdef __CUDACC__
#define TV_HD __host__ __device__ __forceinline__
#define TV_ATOMIC_CAS(p, a, b) atomicCAS((p), (a), (b))
#else
#define TV_HD inline
static inline int tv_cas_host(int* p, int a, int b) { int o = *p; if (o == a) *p = b; return o; }
#define TV_ATOMIC_CAS(p, a, b) tv_cas_host((p), (a), (b))
#endif

// ---------- таблицы SHA (константная память на GPU, обычные массивы на CPU) ----------
#ifdef __CUDACC__
__constant__ uint64_t tv_k512_d[80] = { TV_K512_LIST };
__constant__ uint32_t tv_k256_d[64] = { TV_K256_LIST };
#endif
static const uint64_t tv_k512_h[80] = { TV_K512_LIST };
static const uint32_t tv_k256_h[64] = { TV_K256_LIST };
#ifdef __CUDA_ARCH__
#define TV_K512 tv_k512_d
#define TV_K256 tv_k256_d
#else
#define TV_K512 tv_k512_h
#define TV_K256 tv_k256_h
#endif

// ---------- параметры WalletV4R2 ----------
#define TV_CODE_HASH_LIST \
    0xfe, 0xb5, 0xff, 0x68, 0x20, 0xe2, 0xff, 0x0d, 0x94, 0x83, 0xe7, 0xe0, 0xd6, 0x2c, 0x81, 0x7d, \
    0x84, 0x67, 0x89, 0xfb, 0x4a, 0xe5, 0x80, 0xc8, 0x78, 0x86, 0x6d, 0x95, 0x9d, 0xab, 0xd5, 0xc0
#define TV_CODE_DEPTH 7
#define TV_DEFAULT_WALLET_ID 698983191u
#define TV_BATCH 8  // сколько ключей делят одну инверсию поля (метод Монтгомери)

// ---------- SHA-512 ----------
TV_HD uint64_t tv_rotr64(uint64_t x, int n) { return (x >> n) | (x << (64 - n)); }

TV_HD void tv_sha512_compress(uint64_t st[8], const uint64_t m[16]) {
    uint64_t w[16];
    for (int i = 0; i < 16; i++) w[i] = m[i];
    uint64_t a = st[0], b = st[1], c = st[2], d = st[3], e = st[4], f = st[5], g = st[6], h = st[7];
#pragma unroll
    for (int i = 0; i < 80; i++) {
        if (i >= 16) {
            uint64_t x = w[(i - 15) & 15], y = w[(i - 2) & 15];
            uint64_t s0 = tv_rotr64(x, 1) ^ tv_rotr64(x, 8) ^ (x >> 7);
            uint64_t s1 = tv_rotr64(y, 19) ^ tv_rotr64(y, 61) ^ (y >> 6);
            w[i & 15] = w[i & 15] + s0 + w[(i - 7) & 15] + s1;
        }
        uint64_t S1 = tv_rotr64(e, 14) ^ tv_rotr64(e, 18) ^ tv_rotr64(e, 41);
        uint64_t ch = (e & f) ^ (~e & g);
        uint64_t t1 = h + S1 + ch + TV_K512[i] + w[i & 15];
        uint64_t S0 = tv_rotr64(a, 28) ^ tv_rotr64(a, 34) ^ tv_rotr64(a, 39);
        uint64_t mj = (a & b) ^ (a & c) ^ (b & c);
        uint64_t t2 = S0 + mj;
        h = g; g = f; f = e; e = d + t1; d = c; c = b; b = a; a = t1 + t2;
    }
    st[0] += a; st[1] += b; st[2] += c; st[3] += d; st[4] += e; st[5] += f; st[6] += g; st[7] += h;
}

// SHA-512 сообщения до 111 байт (один блок).
TV_HD void tv_sha512_short(const uint8_t* msg, int len, uint8_t out[64]) {
    uint8_t blk[128];
    for (int i = 0; i < 128; i++) blk[i] = 0;
    for (int i = 0; i < len; i++) blk[i] = msg[i];
    blk[len] = 0x80;
    uint64_t bits = (uint64_t)len * 8;
    for (int i = 0; i < 8; i++) blk[127 - i] = (uint8_t)(bits >> (8 * i));
    uint64_t m[16], st[8];
    for (int i = 0; i < 16; i++) {
        uint64_t v = 0;
        for (int j = 0; j < 8; j++) v = (v << 8) | blk[i * 8 + j];
        m[i] = v;
    }
    {
        const uint64_t iv[8] = { TV_H512_LIST };
        for (int i = 0; i < 8; i++) st[i] = iv[i];
    }
    tv_sha512_compress(st, m);
    for (int i = 0; i < 8; i++)
        for (int j = 0; j < 8; j++) out[i * 8 + j] = (uint8_t)(st[i] >> (56 - 8 * j));
}

// ---------- SHA-256 ----------
TV_HD uint32_t tv_rotr32(uint32_t x, int n) { return (x >> n) | (x << (32 - n)); }

TV_HD void tv_sha256_compress(uint32_t st[8], const uint8_t blk[64]) {
    uint32_t w[16];
    for (int i = 0; i < 16; i++)
        w[i] = (uint32_t)blk[i * 4] << 24 | (uint32_t)blk[i * 4 + 1] << 16 | (uint32_t)blk[i * 4 + 2] << 8 | blk[i * 4 + 3];
    uint32_t a = st[0], b = st[1], c = st[2], d = st[3], e = st[4], f = st[5], g = st[6], h = st[7];
#pragma unroll
    for (int i = 0; i < 64; i++) {
        if (i >= 16) {
            uint32_t x = w[(i - 15) & 15], y = w[(i - 2) & 15];
            uint32_t s0 = tv_rotr32(x, 7) ^ tv_rotr32(x, 18) ^ (x >> 3);
            uint32_t s1 = tv_rotr32(y, 17) ^ tv_rotr32(y, 19) ^ (y >> 10);
            w[i & 15] = w[i & 15] + s0 + w[(i - 7) & 15] + s1;
        }
        uint32_t S1 = tv_rotr32(e, 6) ^ tv_rotr32(e, 11) ^ tv_rotr32(e, 25);
        uint32_t ch = (e & f) ^ (~e & g);
        uint32_t t1 = h + S1 + ch + TV_K256[i] + w[i & 15];
        uint32_t S0 = tv_rotr32(a, 2) ^ tv_rotr32(a, 13) ^ tv_rotr32(a, 22);
        uint32_t mj = (a & b) ^ (a & c) ^ (b & c);
        uint32_t t2 = S0 + mj;
        h = g; g = f; f = e; e = d + t1; d = c; c = b; b = a; a = t1 + t2;
    }
    st[0] += a; st[1] += b; st[2] += c; st[3] += d; st[4] += e; st[5] += f; st[6] += g; st[7] += h;
}

TV_HD void tv_sha256_out(const uint32_t st[8], uint8_t out[32]) {
    for (int i = 0; i < 8; i++)
        for (int j = 0; j < 4; j++) out[i * 4 + j] = (uint8_t)(st[i] >> (24 - 8 * j));
}

// ---------- CRC16/XMODEM ----------
TV_HD uint16_t tv_crc16(uint16_t c, const uint8_t* d, int n) {
    for (int i = 0; i < n; i++) {
        c ^= (uint16_t)((uint16_t)d[i] << 8);
        for (int k = 0; k < 8; k++) c = (c & 0x8000) ? (uint16_t)((c << 1) ^ 0x1021) : (uint16_t)(c << 1);
    }
    return c;
}

// ---------- хеш адреса v4R2 ----------
// data-ячейка: seqno(32)=0 | wallet_id(32) | pubkey(256) | 0 (плагины), далее StateInit(code,data).
TV_HD void tv_address_hash(const uint8_t pk[32], uint32_t wid, uint8_t out[32]) {
    uint8_t a[64];
    for (int i = 0; i < 64; i++) a[i] = 0;
    a[1] = 0x51;
    a[6] = (uint8_t)(wid >> 24); a[7] = (uint8_t)(wid >> 16); a[8] = (uint8_t)(wid >> 8); a[9] = (uint8_t)wid;
    for (int i = 0; i < 32; i++) a[10 + i] = pk[i];
    a[42] = 0x40;
    a[43] = 0x80;
    a[63] = 43 * 8 & 0xff; a[62] = (43 * 8) >> 8;
    const uint32_t iv[8] = { TV_H256_LIST };
    const uint8_t code_hash[32] = { TV_CODE_HASH_LIST };
    uint32_t st[8];
    for (int i = 0; i < 8; i++) st[i] = iv[i];
    tv_sha256_compress(st, a);
    uint8_t dh[32];
    tv_sha256_out(st, dh);

    uint8_t b1[64], b2[64];
    for (int i = 0; i < 64; i++) { b1[i] = 0; b2[i] = 0; }
    b1[0] = 0x02; b1[1] = 0x01; b1[2] = 0x34; b1[3] = 0; b1[4] = TV_CODE_DEPTH; b1[5] = 0; b1[6] = 0;
    for (int i = 0; i < 32; i++) b1[7 + i] = code_hash[i];
    for (int i = 0; i < 25; i++) b1[39 + i] = dh[i];
    for (int i = 0; i < 7; i++) b2[i] = dh[25 + i];
    b2[7] = 0x80;
    b2[63] = 71 * 8 & 0xff; b2[62] = (71 * 8) >> 8;
    for (int i = 0; i < 8; i++) st[i] = iv[i];
    tv_sha256_compress(st, b1);
    tv_sha256_compress(st, b2);
    tv_sha256_out(st, out);
}

// ---------- арифметика поля 2^255-19 (радикс 2^25.5, как в ref10) ----------
typedef int32_t fe[10];

TV_HD void fe_0(fe h) { for (int i = 0; i < 10; i++) h[i] = 0; }
TV_HD void fe_1(fe h) { fe_0(h); h[0] = 1; }
TV_HD void fe_copy(fe h, const fe f) { for (int i = 0; i < 10; i++) h[i] = f[i]; }
TV_HD void fe_add(fe h, const fe f, const fe g) { for (int i = 0; i < 10; i++) h[i] = f[i] + g[i]; }
TV_HD void fe_sub(fe h, const fe f, const fe g) { for (int i = 0; i < 10; i++) h[i] = f[i] - g[i]; }
TV_HD void fe_neg(fe h, const fe f) { for (int i = 0; i < 10; i++) h[i] = -f[i]; }

TV_HD void fe_carry(fe h, int64_t t[10]) {
    int64_t c;
    c = (t[0] + (1 << 25)) >> 26; t[1] += c; t[0] -= c << 26;
    c = (t[4] + (1 << 25)) >> 26; t[5] += c; t[4] -= c << 26;
    c = (t[1] + (1 << 24)) >> 25; t[2] += c; t[1] -= c << 25;
    c = (t[5] + (1 << 24)) >> 25; t[6] += c; t[5] -= c << 25;
    c = (t[2] + (1 << 25)) >> 26; t[3] += c; t[2] -= c << 26;
    c = (t[6] + (1 << 25)) >> 26; t[7] += c; t[6] -= c << 26;
    c = (t[3] + (1 << 24)) >> 25; t[4] += c; t[3] -= c << 25;
    c = (t[7] + (1 << 24)) >> 25; t[8] += c; t[7] -= c << 25;
    c = (t[4] + (1 << 25)) >> 26; t[5] += c; t[4] -= c << 26;
    c = (t[8] + (1 << 25)) >> 26; t[9] += c; t[8] -= c << 26;
    c = (t[9] + (1 << 24)) >> 25; t[0] += c * 19; t[9] -= c << 25;
    c = (t[0] + (1 << 25)) >> 26; t[1] += c; t[0] -= c << 26;
    for (int i = 0; i < 10; i++) h[i] = (int32_t)t[i];
}

TV_HD void fe_mul(fe h, const fe f, const fe g) {
    int64_t t[10];
    for (int i = 0; i < 10; i++) t[i] = 0;
#pragma unroll
    for (int i = 0; i < 10; i++) {
#pragma unroll
        for (int j = 0; j < 10; j++) {
            int64_t p = (int64_t)f[i] * g[j];
            if (i & j & 1) p *= 2;
            int k = i + j;
            if (k >= 10) { k -= 10; p *= 19; }
            t[k] += p;
        }
    }
    fe_carry(h, t);
}

// h = f^2 (dbl=0) или 2*f^2 (dbl=1)
TV_HD void fe_sq_(fe h, const fe f, int dbl) {
    int64_t t[10];
    for (int i = 0; i < 10; i++) t[i] = 0;
#pragma unroll
    for (int i = 0; i < 10; i++) {
#pragma unroll
        for (int j = i; j < 10; j++) {
            int64_t p = (int64_t)f[i] * f[j];
            if (j != i) p *= 2;
            if (i & j & 1) p *= 2;
            int k = i + j;
            if (k >= 10) { k -= 10; p *= 19; }
            t[k] += p;
        }
    }
    if (dbl) for (int i = 0; i < 10; i++) t[i] *= 2;
    fe_carry(h, t);
}
TV_HD void fe_sq(fe h, const fe f) { fe_sq_(h, f, 0); }
TV_HD void fe_sq2(fe h, const fe f) { fe_sq_(h, f, 1); }

#define TV_OFF(i) ((51 * (i) + 1) >> 1)  // 0,26,51,77,102,128,153,179,204,230
#define TV_LIMB_BITS(i) (((i) & 1) ? 25 : 26)

TV_HD void fe_frombytes(fe h, const uint8_t s[32]) {
    uint64_t w[5] = {0, 0, 0, 0, 0};
    for (int i = 0; i < 32; i++) w[i >> 3] |= (uint64_t)s[i] << (8 * (i & 7));
    for (int i = 0; i < 10; i++) {
        int off = TV_OFF(i), len = TV_LIMB_BITS(i), sh = off & 63;
        uint64_t v = w[off >> 6] >> sh;
        if (sh + len > 64) v |= w[(off >> 6) + 1] << (64 - sh);
        h[i] = (int32_t)(v & ((1ULL << len) - 1));
    }
}

TV_HD void fe_tobytes(uint8_t s[32], const fe f) {
    int32_t h[10];
    for (int i = 0; i < 10; i++) h[i] = f[i];
    int32_t q = (19 * h[9] + (1 << 24)) >> 25;
    q = (h[0] + q) >> 26; q = (h[1] + q) >> 25; q = (h[2] + q) >> 26; q = (h[3] + q) >> 25;
    q = (h[4] + q) >> 26; q = (h[5] + q) >> 25; q = (h[6] + q) >> 26; q = (h[7] + q) >> 25;
    q = (h[8] + q) >> 26; q = (h[9] + q) >> 25;
    h[0] += 19 * q;
    for (int i = 0; i < 9; i++) {
        int sh = (i & 1) ? 25 : 26;
        int32_t c = h[i] >> sh;
        h[i + 1] += c;
        h[i] -= c << sh;
    }
    int32_t c9 = h[9] >> 25;
    h[9] -= c9 << 25;
    uint64_t w[5] = {0, 0, 0, 0, 0};
    for (int i = 0; i < 10; i++) {
        int off = TV_OFF(i), len = TV_LIMB_BITS(i), sh = off & 63;
        uint64_t v = (uint64_t)(uint32_t)h[i];
        w[off >> 6] |= v << sh;
        if (sh + len > 64) w[(off >> 6) + 1] |= v >> (64 - sh);
    }
    for (int i = 0; i < 32; i++) s[i] = (uint8_t)(w[i >> 3] >> (8 * (i & 7)));
}

TV_HD void fe_norm(fe h) { uint8_t b[32]; fe_tobytes(b, h); fe_frombytes(h, b); }

TV_HD void fe_invert(fe out, const fe z) {
    fe t0, t1, t2, t3;
    fe_sq(t0, z);
    fe_sq(t1, t0); fe_sq(t1, t1);
    fe_mul(t1, z, t1);
    fe_mul(t0, t0, t1);
    fe_sq(t2, t0);
    fe_mul(t1, t1, t2);
    fe_sq(t2, t1); for (int i = 1; i < 5; i++) fe_sq(t2, t2);
    fe_mul(t1, t2, t1);
    fe_sq(t2, t1); for (int i = 1; i < 10; i++) fe_sq(t2, t2);
    fe_mul(t2, t2, t1);
    fe_sq(t3, t2); for (int i = 1; i < 20; i++) fe_sq(t3, t3);
    fe_mul(t2, t3, t2);
    fe_sq(t2, t2); for (int i = 1; i < 10; i++) fe_sq(t2, t2);
    fe_mul(t1, t2, t1);
    fe_sq(t2, t1); for (int i = 1; i < 50; i++) fe_sq(t2, t2);
    fe_mul(t2, t2, t1);
    fe_sq(t3, t2); for (int i = 1; i < 100; i++) fe_sq(t3, t3);
    fe_mul(t2, t3, t2);
    fe_sq(t2, t2); for (int i = 1; i < 50; i++) fe_sq(t2, t2);
    fe_mul(t1, t2, t1);
    fe_sq(t1, t1); for (int i = 1; i < 5; i++) fe_sq(t1, t1);
    fe_mul(out, t1, t0);
}

// ---------- точки Эдвардса ----------
typedef struct { fe X, Y, Z, T; } ge_p3;
typedef struct { fe X, Y, Z; } ge_p2;
typedef struct { fe X, Y, Z, T; } ge_p1p1;
typedef struct { fe YplusX, YminusX, Z, T2d; } ge_cached;
typedef struct { fe ypx, ymx, xy2d; } TvPre;  // аффинная точка (y+x, y-x, 2dxy)

TV_HD void ge_p3_0(ge_p3* h) { fe_0(h->X); fe_1(h->Y); fe_1(h->Z); fe_0(h->T); }
TV_HD void ge_p1p1_to_p2(ge_p2* r, const ge_p1p1* p) {
    fe_mul(r->X, p->X, p->T); fe_mul(r->Y, p->Y, p->Z); fe_mul(r->Z, p->Z, p->T);
}
TV_HD void ge_p1p1_to_p3(ge_p3* r, const ge_p1p1* p) {
    fe_mul(r->X, p->X, p->T); fe_mul(r->Y, p->Y, p->Z); fe_mul(r->Z, p->Z, p->T); fe_mul(r->T, p->X, p->Y);
}
TV_HD void ge_p3_to_p2(ge_p2* r, const ge_p3* p) { fe_copy(r->X, p->X); fe_copy(r->Y, p->Y); fe_copy(r->Z, p->Z); }
TV_HD void ge_p2_dbl(ge_p1p1* r, const ge_p2* p) {
    fe t0;
    fe_sq(r->X, p->X);
    fe_sq(r->Z, p->Y);
    fe_sq2(r->T, p->Z);
    fe_add(r->Y, p->X, p->Y);
    fe_sq(t0, r->Y);
    fe_add(r->Y, r->Z, r->X);
    fe_sub(r->Z, r->Z, r->X);
    fe_sub(r->X, t0, r->Y);
    fe_sub(r->T, r->T, r->Z);
}
TV_HD void ge_p3_dbl(ge_p1p1* r, const ge_p3* p) { ge_p2 q; ge_p3_to_p2(&q, p); ge_p2_dbl(r, &q); }

// r = p + q, q в аффинной предвычисленной форме
TV_HD void ge_madd(ge_p1p1* r, const ge_p3* p, const fe qypx, const fe qymx, const fe qxy2d) {
    fe t0;
    fe_add(r->X, p->Y, p->X);
    fe_sub(r->Y, p->Y, p->X);
    fe_mul(r->Z, r->X, qypx);
    fe_mul(r->Y, r->Y, qymx);
    fe_mul(r->T, qxy2d, p->T);
    fe_add(t0, p->Z, p->Z);
    fe_sub(r->X, r->Z, r->Y);
    fe_add(r->Y, r->Z, r->Y);
    fe_add(r->Z, t0, r->T);
    fe_sub(r->T, t0, r->T);
}

// Для построения таблицы (только хост, но код общий)
TV_HD void ge_p3_to_cached(ge_cached* r, const ge_p3* p, const fe d2) {
    fe_add(r->YplusX, p->Y, p->X); fe_sub(r->YminusX, p->Y, p->X);
    fe_copy(r->Z, p->Z); fe_mul(r->T2d, p->T, d2);
}
TV_HD void ge_add(ge_p1p1* r, const ge_p3* p, const ge_cached* q) {
    fe t0;
    fe_add(r->X, p->Y, p->X);
    fe_sub(r->Y, p->Y, p->X);
    fe_mul(r->Z, r->X, q->YplusX);
    fe_mul(r->Y, r->Y, q->YminusX);
    fe_mul(r->T, q->T2d, p->T);
    fe_mul(r->X, p->Z, q->Z);
    fe_add(t0, r->X, r->X);
    fe_sub(r->X, r->Z, r->Y);
    fe_add(r->Y, r->Z, r->Y);
    fe_add(r->Z, t0, r->T);
    fe_sub(r->T, t0, r->T);
}

// Таблица: tbl[j*9 + k] = k * 256^j * B (k = 0..8, k=0 - нейтральный элемент), j = 0..31.
#define TV_TBL_ENTRIES (32 * 9)

// Выбор знакового разряда b (-8..8) из блока таблицы без ветвлений по знаку.
TV_HD void tv_select(fe ypx, fe ymx, fe xy2d, const TvPre* row, int b) {
    int32_t neg = (b >> 31) & 1;       // 1, если b < 0
    int32_t babs = b - (((-neg) & b) << 1);
    const TvPre* e = &row[babs];
    int32_t m = -neg;                  // 0 или -1
    for (int i = 0; i < 10; i++) {
        int32_t a = e->ypx[i], c = e->ymx[i], x = e->xy2d[i];
        int32_t d = (a ^ c) & m;
        ypx[i] = a ^ d;
        ymx[i] = c ^ d;
        xy2d[i] = (x ^ m) - m;
    }
}

// h = k*B для уже «зажатого» 32-байтного скаляра k (little-endian)
TV_HD void ge_scalarmult_base(ge_p3* h, const TvPre* tbl, const uint8_t a[32]) {
    int8_t e[64];
    for (int i = 0; i < 32; i++) { e[2 * i] = a[i] & 15; e[2 * i + 1] = (a[i] >> 4) & 15; }
    int8_t carry = 0;
    for (int i = 0; i < 63; i++) {
        e[i] += carry;
        carry = (e[i] + 8) >> 4;
        e[i] -= carry << 4;
    }
    e[63] += carry;

    fe ypx, ymx, xy2d;
    ge_p1p1 r;
    ge_p2 s;
    ge_p3_0(h);
    for (int i = 1; i < 64; i += 2) {
        tv_select(ypx, ymx, xy2d, &tbl[(i >> 1) * 9], e[i]);
        ge_madd(&r, h, ypx, ymx, xy2d);
        ge_p1p1_to_p3(h, &r);
    }
    ge_p3_dbl(&r, h); ge_p1p1_to_p2(&s, &r);
    ge_p2_dbl(&r, &s); ge_p1p1_to_p2(&s, &r);
    ge_p2_dbl(&r, &s); ge_p1p1_to_p2(&s, &r);
    ge_p2_dbl(&r, &s); ge_p1p1_to_p3(h, &r);
    for (int i = 0; i < 64; i += 2) {
        tv_select(ypx, ymx, xy2d, &tbl[(i >> 1) * 9], e[i]);
        ge_madd(&r, h, ypx, ymx, xy2d);
        ge_p1p1_to_p3(h, &r);
    }
}

// ключ ed25519: seed -> клампнутый скаляр
TV_HD void tv_clamped_scalar(const uint8_t seed[32], uint8_t k[32]) {
    uint8_t h[64];
    tv_sha512_short(seed, 32, h);
    for (int i = 0; i < 32; i++) k[i] = h[i];
    k[0] &= 248; k[31] &= 127; k[31] |= 64;
}

// сжатие точки по известному 1/Z
TV_HD void tv_compress(uint8_t out[32], const fe X, const fe Y, const fe zinv) {
    fe x, y;
    fe_mul(x, X, zinv);
    fe_mul(y, Y, zinv);
    uint8_t xb[32];
    fe_tobytes(xb, x);
    fe_tobytes(out, y);
    out[31] ^= (uint8_t)((xb[0] & 1) << 7);
}

// эталонный путь: один ключ, своя инверсия (проверка найденного на хосте и тесты)
TV_HD void tv_pubkey_from_seed(const TvPre* tbl, const uint8_t seed[32], uint8_t pk[32]) {
    uint8_t k[32];
    ge_p3 p;
    fe zi;
    tv_clamped_scalar(seed, k);
    ge_scalarmult_base(&p, tbl, k);
    fe_invert(zi, p.Z);
    tv_compress(pk, p.X, p.Y, zi);
}

// ---------- поиск ----------
struct TvParams {
    uint8_t master[32];       // секретная случайная затравка запуска
    uint64_t base;            // номер первого ключа в этом запуске ядра
    uint32_t iters;           // ключей на поток (кратно TV_BATCH)
    uint32_t subwallets;      // сколько wallet_id пробовать на ключ
    uint64_t mask;            // маска нужных 6k бит
    uint32_t ntargets;
    uint64_t single;          // единственная цель (если ntargets == 1)
    const uint64_t* targets;  // отсортированные цели (для --nocase)
    uint16_t crcK[2];         // константы CRC для флагов 0x11 и 0x51
};

struct TvResult {
    int found;
    uint32_t wid;
    uint8_t seed[32];
};

// seed ключа с номером ctr: SHA-512(master || ctr)[0..32]. Master секретен, поэтому seed непредсказуем.
TV_HD void tv_seed_for(const TvParams& P, uint64_t ctr, uint8_t seed[32]) {
    uint8_t m[40], d[64];
    for (int i = 0; i < 32; i++) m[i] = P.master[i];
    for (int i = 0; i < 8; i++) m[32 + i] = (uint8_t)(ctr >> (8 * i));
    tv_sha512_short(m, 40, d);
    for (int i = 0; i < 32; i++) seed[i] = d[i];
}

TV_HD void tv_search_thread(const TvParams& P, const TvPre* tbl, uint64_t tid, TvResult* res) {
    const uint64_t ctr0 = P.base + tid * (uint64_t)P.iters;
    for (uint32_t it = 0; it < P.iters; it += TV_BATCH) {
        if (*(volatile int*)&res->found) return;

        uint8_t seeds[TV_BATCH][32];
        fe PX[TV_BATCH], PY[TV_BATCH], PZ[TV_BATCH];
        for (int n = 0; n < TV_BATCH; n++) {
            uint8_t k[32];
            ge_p3 p;
            tv_seed_for(P, ctr0 + it + n, seeds[n]);
            tv_clamped_scalar(seeds[n], k);
            ge_scalarmult_base(&p, tbl, k);
            fe_copy(PX[n], p.X); fe_copy(PY[n], p.Y); fe_copy(PZ[n], p.Z);
        }

        // одна инверсия на TV_BATCH ключей (трюк Монтгомери)
        fe pref[TV_BATCH], inv, zinv[TV_BATCH];
        fe_copy(pref[0], PZ[0]);
        for (int n = 1; n < TV_BATCH; n++) fe_mul(pref[n], pref[n - 1], PZ[n]);
        fe_invert(inv, pref[TV_BATCH - 1]);
        for (int n = TV_BATCH - 1; n > 0; n--) {
            fe_mul(zinv[n], inv, pref[n - 1]);
            fe_mul(inv, inv, PZ[n]);
        }
        fe_copy(zinv[0], inv);

        for (int n = 0; n < TV_BATCH; n++) {
            uint8_t pk[32];
            tv_compress(pk, PX[n], PY[n], zinv[n]);
            for (uint32_t j = 0; j < P.subwallets; j++) {
                const uint32_t wid = TV_DEFAULT_WALLET_ID + j;
                uint8_t h[32];
                tv_address_hash(pk, wid, h);
                const uint16_t crc0 = tv_crc16(0, h, 32);  // CRC линеен: флаги добавляются XOR-константой
                uint64_t tail = 0;
                for (int i = 24; i < 32; i++) tail = (tail << 8) | h[i];
                tail <<= 16;
                for (int f = 0; f < 2; f++) {
                    const uint64_t v = (tail | (uint16_t)(crc0 ^ P.crcK[f])) & P.mask;
                    bool hit;
                    if (P.ntargets == 1) {
                        hit = (v == P.single);
                    } else {
                        hit = false;
                        uint32_t lo = 0, hi = P.ntargets;
                        while (lo < hi) {
                            uint32_t mid = (lo + hi) >> 1;
                            uint64_t t = P.targets[mid];
                            if (t < v) lo = mid + 1; else hi = mid;
                        }
                        hit = (lo < P.ntargets && P.targets[lo] == v);
                    }
                    if (hit) {
                        if (TV_ATOMIC_CAS(&res->found, 0, 1) == 0) {
                            res->wid = wid;
                            for (int i = 0; i < 32; i++) res->seed[i] = seeds[n][i];
                        }
                        return;
                    }
                }
            }
        }
    }
}
