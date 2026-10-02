// Хост-утилиты: таблица базовой точки, цели поиска, случайность, форматирование адреса.
#pragma once
#ifdef _WIN32
#define _CRT_RAND_S
#endif
#include <ctype.h>
#include <stdlib.h>
#include <stdio.h>
#include <algorithm>
#include <string>
#include <vector>
#include "tv_core.h"

static const char* TV_B64 = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_";

inline std::string tv_hex(const uint8_t* b, size_t n) {
    std::string s;
    char t[3];
    for (size_t i = 0; i < n; i++) { snprintf(t, sizeof t, "%02x", b[i]); s += t; }
    return s;
}

inline void tv_os_random(uint8_t* buf, size_t n) {
#ifdef _WIN32
    for (size_t i = 0; i < n; i += 4) {
        unsigned int v;
        if (rand_s(&v) != 0) { fprintf(stderr, "rand_s failed\n"); exit(1); }
        for (size_t j = 0; j < 4 && i + j < n; j++) buf[i + j] = (uint8_t)(v >> (8 * j));
    }
#else
    FILE* f = fopen("/dev/urandom", "rb");
    if (!f || fread(buf, 1, n, f) != n) { fprintf(stderr, "нет /dev/urandom\n"); exit(1); }
    fclose(f);
#endif
}

inline void tv_crc_consts(uint16_t k[2]) {
    const uint8_t flags[2] = {0x11, 0x51};  // bounceable / non-bounceable
    for (int i = 0; i < 2; i++) {
        uint8_t m[34] = {0};
        m[0] = flags[i];
        k[i] = tv_crc16(0, m, 34);
    }
}

inline std::string tv_friendly(uint8_t flag, const uint8_t hash[32]) {
    uint8_t p[36] = {0};
    p[0] = flag;
    memcpy(p + 2, hash, 32);
    uint16_t c = tv_crc16(0, p, 34);
    p[34] = (uint8_t)(c >> 8);
    p[35] = (uint8_t)c;
    std::string s;
    for (int i = 0; i < 36; i += 3) {
        uint32_t n = (uint32_t)p[i] << 16 | (uint32_t)p[i + 1] << 8 | p[i + 2];
        for (int sh = 18; sh >= 0; sh -= 6) s += TV_B64[(n >> sh) & 63];
    }
    return s;
}

// отсортированные 6k-битные цели; err непустой при ошибке
inline std::vector<uint64_t> tv_build_targets(const std::string& suffix, bool nocase, std::string& err) {
    std::vector<uint64_t> out;
    if (suffix.empty() || suffix.size() > 10) { err = "суффикс должен быть длиной 1..10 символов"; return out; }
    std::vector<std::string> var = {""};
    for (char c : suffix) {
        std::string opts(1, c);
        if (nocase && isalpha((unsigned char)c)) opts = std::string(1, (char)tolower(c)) + (char)toupper(c);
        std::vector<std::string> nv;
        for (auto& v : var) for (char o : opts) nv.push_back(v + o);
        var.swap(nv);
    }
    for (auto& v : var) {
        uint64_t acc = 0;
        for (char c : v) {
            const char* p = strchr(TV_B64, c);
            if (!p || !c) { err = std::string("символ '") + c + "' недопустим в base64url (A-Z a-z 0-9 - _)"; return {}; }
            acc = acc << 6 | (uint64_t)(p - TV_B64);
        }
        out.push_back(acc);
    }
    std::sort(out.begin(), out.end());
    out.erase(std::unique(out.begin(), out.end()), out.end());
    return out;
}

// Таблица tbl[j*9+k] = k * 256^j * B
inline std::vector<TvPre> tv_build_table() {
    fe d, d2, t, c;
    uint8_t b[32] = {0};
    b[0] = 0x42; b[1] = 0xDB; b[2] = 0x01;  // 121666
    fe_frombytes(t, b);
    fe_invert(t, t);
    b[0] = 0x41;                            // 121665
    fe_frombytes(c, b);
    fe_mul(d, c, t);
    fe_neg(d, d);
    fe_norm(d);
    fe_add(d2, d, d);
    fe_norm(d2);

    static const char* bx = "216936d3cd6e53fec0a4e231fdd6dc5c692cc7609525a7b2c9562d608f25d51a";
    uint8_t xb[32], yb[32];
    for (int i = 0; i < 32; i++) {
        unsigned v;
        sscanf(bx + 2 * (31 - i), "%2x", &v);
        xb[i] = (uint8_t)v;
        yb[i] = 0x66;
    }
    yb[0] = 0x58;
    ge_p3 P;
    fe_frombytes(P.X, xb);
    fe_frombytes(P.Y, yb);
    fe_1(P.Z);
    fe_mul(P.T, P.X, P.Y);

    std::vector<TvPre> tbl(TV_TBL_ENTRIES);
    for (int j = 0; j < 32; j++) {
        TvPre& id = tbl[j * 9];
        fe_1(id.ypx); fe_1(id.ymx); fe_0(id.xy2d);
        ge_cached cp;
        ge_p3_to_cached(&cp, &P, d2);
        ge_p3 acc = P;
        for (int k = 1; k <= 8; k++) {
            fe zi, x, y, xy;
            fe_invert(zi, acc.Z);
            fe_mul(x, acc.X, zi);
            fe_mul(y, acc.Y, zi);
            TvPre& e = tbl[j * 9 + k];
            fe_add(e.ypx, y, x); fe_norm(e.ypx);
            fe_sub(e.ymx, y, x); fe_norm(e.ymx);
            fe_mul(xy, x, y);
            fe_mul(e.xy2d, xy, d2); fe_norm(e.xy2d);
            if (k < 8) { ge_p1p1 r; ge_add(&r, &acc, &cp); ge_p1p1_to_p3(&acc, &r); }
        }
        for (int i = 0; i < 8; i++) { ge_p1p1 r; ge_p3_dbl(&r, &P); ge_p1p1_to_p3(&P, &r); }
    }
    return tbl;
}
