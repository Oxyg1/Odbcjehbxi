// Тесты ядра на CPU, включая эмуляцию GPU-ядра (tv_search_thread вызывается циклом по «потокам»).
// Сборка: g++ -O2 -o test_cpu test_cpu.cpp
#include <assert.h>
#include <iostream>
#include "tv_host.h"

static std::vector<uint8_t> unhex(const std::string& s) {
    std::vector<uint8_t> v;
    for (size_t i = 0; i < s.size(); i += 2) v.push_back((uint8_t)std::stoi(s.substr(i, 2), nullptr, 16));
    return v;
}

int main(int argc, char** argv) {
    auto tbl = tv_build_table();
    if (argc > 2 && std::string(argv[1]) == "stress") {  // test_cpu stress N: seed pk
        TvParams P{};
        tv_os_random(P.master, 32);
        for (int i = 0; i < atoi(argv[2]); i++) {
            uint8_t seed[32], pk[32];
            tv_seed_for(P, (uint64_t)i, seed);
            tv_pubkey_from_seed(tbl.data(), seed, pk);
            printf("%s %s\n", tv_hex(seed, 32).c_str(), tv_hex(pk, 32).c_str());
        }
        return 0;
    }
    // RFC 8032, test 1
    {
        auto seed = unhex("9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60");
        uint8_t pk[32];
        tv_pubkey_from_seed(tbl.data(), seed.data(), pk);
        assert(tv_hex(pk, 32) == "d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a");
        fprintf(stderr, "ok: RFC8032 pubkey\n");
    }
    // вектор tonsdk
    {
        uint8_t pk[32], h[32];
        for (int i = 0; i < 32; i++) pk[i] = (uint8_t)i;
        tv_address_hash(pk, TV_DEFAULT_WALLET_ID, h);
        assert(tv_hex(h, 32) == "7c380f242a59749f692f522934c3dd60ff1def38555349861702bb1ca9258623");
        assert(tv_friendly(0x51, h) == "UQB8OA8kKll0n2kvUik0w91g_x3vOFVTSYYXArscqSWGI8My");
        fprintf(stderr, "ok: address vs tonsdk\n");
    }
    // случайные seed -> pubkey, адрес (сверка снаружи питоном)
    {
        uint8_t master[32];
        tv_os_random(master, 32);
        TvParams P{};
        memcpy(P.master, master, 32);
        for (int i = 0; i < 400; i++) {
            uint8_t seed[32], pk[32], h[32];
            tv_seed_for(P, (uint64_t)i * 7919, seed);
            tv_pubkey_from_seed(tbl.data(), seed, pk);
            uint32_t wid = i % 3 ? TV_DEFAULT_WALLET_ID : 12345u + i;
            tv_address_hash(pk, wid, h);
            printf("VEC %s %s %u %s\n", tv_hex(seed, 32).c_str(), tv_hex(pk, 32).c_str(), wid, tv_friendly(0x51, h).c_str());
        }
    }
    // эмуляция ядра: ищем суффикс, потоки идут последовательно
    const char* suffixes[][3] = {{"Zz", "0", "1"}, {"zz", "1", "3"}, {"aB3", "0", "2"}};
    for (auto& cfg : suffixes) {
        std::string err;
        bool nocase = cfg[1][0] == '1';
        auto targets = tv_build_targets(cfg[0], nocase, err);
        assert(err.empty());
        TvParams P{};
        tv_os_random(P.master, 32);
        P.iters = 16 * TV_BATCH;
        P.subwallets = atoi(cfg[2]);
        P.mask = (1ULL << (6 * strlen(cfg[0]))) - 1;
        P.ntargets = (uint32_t)targets.size();
        P.single = targets[0];
        P.targets = targets.data();
        tv_crc_consts(P.crcK);
        TvResult res{};
        for (uint64_t launch = 0; !res.found; launch++) {
            P.base = launch * 64 * P.iters;
            for (uint64_t tid = 0; tid < 64 && !res.found; tid++) tv_search_thread(P, tbl.data(), tid, &res);
        }
        uint8_t pk[32], h[32];
        tv_pubkey_from_seed(tbl.data(), res.seed, pk);
        tv_address_hash(pk, res.wid, h);
        std::string e = tv_friendly(0x11, h), u = tv_friendly(0x51, h);
        auto ends = [&](const std::string& s) {
            std::string a = s.substr(s.size() - strlen(cfg[0])), b = cfg[0];
            if (nocase) { for (auto& c : a) c = tolower(c); for (auto& c : b) c = tolower(c); }
            return a == b;
        };
        assert(ends(e) || ends(u));
        printf("HIT %s %s %u %s %s\n", tv_hex(res.seed, 32).c_str(), tv_hex(pk, 32).c_str(), res.wid, e.c_str(), u.c_str());
        fprintf(stderr, "ok: emulated kernel suffix %s nocase=%d sub=%s\n", cfg[0], nocase, cfg[2]);
    }
    return 0;
}
