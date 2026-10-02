// ton_vanity.cu - перебор TON-кошельков (WalletV4R2, workchain 0) на видеокарте NVIDIA.
// Сборка:  nvcc -O3 -arch=native -o ton_vanity_cuda ton_vanity.cu
// Запуск:  ./ton_vanity_cuda --suffix pulse
#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <cmath>
#ifndef _WIN32
#include <sys/stat.h>
#endif
#include <string>
#include <vector>
#include <cuda_runtime.h>
#include "tv_host.h"

#define CK(x)                                                                              \
    do {                                                                                   \
        cudaError_t e_ = (x);                                                              \
        if (e_ != cudaSuccess) {                                                           \
            fprintf(stderr, "CUDA ошибка %s:%d: %s\n", __FILE__, __LINE__, cudaGetErrorString(e_)); \
            exit(1);                                                                       \
        }                                                                                  \
    } while (0)

#define TV_THREADS 128

__global__ void __launch_bounds__(TV_THREADS) tv_kernel(TvParams P, const TvPre* tbl, TvResult* res) {
    const uint64_t tid = (uint64_t)blockIdx.x * blockDim.x + threadIdx.x;
    tv_search_thread(P, tbl, tid, res);
}

static void usage() {
    fprintf(stderr,
            "Использование: ton_vanity_cuda [--suffix pulse] [--nocase] [--subwallets N] [--blocks N] [--out found.txt]\n"
            "  --suffix S       окончание адреса (по умолчанию pulse, регистр важен)\n"
            "  --nocase         игнорировать регистр\n"
            "  --subwallets N   на каждый ключ перебирать N wallet_id (698983191+j); быстрее, но wallet_id нестандартный\n"
            "  --blocks N       число блоков (по умолчанию 16 на мультипроцессор)\n"
            "  --out FILE       файл для результата (по умолчанию found.txt)\n");
    exit(2);
}

int main(int argc, char** argv) {
    std::string suffix = "pulse", out = "found.txt";
    bool nocase = false;
    uint32_t subwallets = 1;
    long blocks_arg = 0;
    for (int i = 1; i < argc; i++) {
        std::string a = argv[i];
        auto val = [&]() -> const char* { if (i + 1 >= argc) usage(); return argv[++i]; };
        if (a == "--suffix") suffix = val();
        else if (a == "--nocase") nocase = true;
        else if (a == "--subwallets") subwallets = (uint32_t)atol(val());
        else if (a == "--blocks") blocks_arg = atol(val());
        else if (a == "--out") out = val();
        else usage();
    }
    if (subwallets == 0) usage();

    std::string err;
    std::vector<uint64_t> targets = tv_build_targets(suffix, nocase, err);
    if (!err.empty()) { fprintf(stderr, "Ошибка: %s\n", err.c_str()); return 2; }

    int dev = 0;
    CK(cudaSetDevice(dev));
    cudaDeviceProp prop;
    CK(cudaGetDeviceProperties(&prop, dev));
    const int blocks = blocks_arg > 0 ? (int)blocks_arg : prop.multiProcessorCount * 16;
    const uint64_t nthreads = (uint64_t)blocks * TV_THREADS;
    printf("GPU: %s, SM: %d, блоков: %d x %d потоков\n", prop.name, prop.multiProcessorCount, blocks, TV_THREADS);

    // таблица базовой точки и цели - в память видеокарты
    std::vector<TvPre> htbl = tv_build_table();
    TvPre* dtbl = nullptr;
    CK(cudaMalloc(&dtbl, htbl.size() * sizeof(TvPre)));
    CK(cudaMemcpy(dtbl, htbl.data(), htbl.size() * sizeof(TvPre), cudaMemcpyHostToDevice));
    uint64_t* dtargets = nullptr;
    CK(cudaMalloc(&dtargets, targets.size() * sizeof(uint64_t)));
    CK(cudaMemcpy(dtargets, targets.data(), targets.size() * sizeof(uint64_t), cudaMemcpyHostToDevice));
    TvResult* dres = nullptr;
    CK(cudaMalloc(&dres, sizeof(TvResult)));
    CK(cudaMemset(dres, 0, sizeof(TvResult)));

    TvParams P;
    memset(&P, 0, sizeof P);
    tv_os_random(P.master, 32);
    P.subwallets = subwallets;
    P.mask = (1ULL << (6 * suffix.size())) - 1;
    P.ntargets = (uint32_t)targets.size();
    P.single = targets[0];
    P.targets = dtargets;
    tv_crc_consts(P.crcK);
    P.base = 0;
    P.iters = TV_BATCH;

    const double p1 = 2.0 * targets.size() / pow(64.0, (double)suffix.size());
    printf("Ищу адрес на \"%s\"%s; ожидаемо ~%.2e проверок (50%% шанс за %.2e)\n", suffix.c_str(),
           nocase ? " (без учёта регистра)" : "", 1.0 / p1, 0.6931471805599453 / p1);

    double checks = 0;
    auto t0 = std::chrono::steady_clock::now();
    auto tlast = t0;
    TvResult hres;
    memset(&hres, 0, sizeof hres);
    while (true) {
        auto ts = std::chrono::steady_clock::now();
        tv_kernel<<<blocks, TV_THREADS>>>(P, dtbl, dres);
        CK(cudaGetLastError());
        CK(cudaDeviceSynchronize());
        auto te = std::chrono::steady_clock::now();
        double dt = std::chrono::duration<double>(te - ts).count();

        CK(cudaMemcpy(&hres, dres, sizeof hres, cudaMemcpyDeviceToHost));
        if (hres.found) break;

        checks += (double)nthreads * P.iters * P.subwallets;
        P.base += nthreads * P.iters;
        // подгоняем длину запуска к ~0.25 с, чтобы отзывчиво реагировать и не упираться в watchdog Windows
        double scale = 0.25 / (dt > 1e-4 ? dt : 1e-4);
        if (scale > 2) scale = 2;
        if (scale < 0.5) scale = 0.5;
        uint32_t ni = (uint32_t)(P.iters * scale) / TV_BATCH * TV_BATCH;
        if (ni < TV_BATCH) ni = TV_BATCH;
        if (ni > (1u << 20)) ni = 1u << 20;
        P.iters = ni;

        double since = std::chrono::duration<double>(te - tlast).count();
        if (since >= 2.0) {
            double el = std::chrono::duration<double>(te - t0).count();
            fprintf(stderr, "\r%.3e проверок, %.3e/с, вероятность найти к этому моменту %.1f%%   ", checks, checks / el,
                    (1.0 - exp(-p1 * checks)) * 100.0);
            tlast = te;
        }
    }
    fprintf(stderr, "\n");
    double elapsed = std::chrono::duration<double>(std::chrono::steady_clock::now() - t0).count();

    // независимая перепроверка на хосте (отдельный путь: одиночная инверсия, SHA через общий код)
    uint8_t pk[32], h[32];
    tv_pubkey_from_seed(htbl.data(), hres.seed, pk);
    tv_address_hash(pk, hres.wid, h);
    std::string eq = tv_friendly(0x11, h), uq = tv_friendly(0x51, h);
    auto ends = [&](const std::string& s) {
        if (s.size() < suffix.size()) return false;
        std::string a = s.substr(s.size() - suffix.size()), b = suffix;
        if (nocase) { for (auto& c : a) c = (char)tolower(c); for (auto& c : b) c = (char)tolower(c); }
        return a == b;
    };
    if (!ends(eq) && !ends(uq)) {
        fprintf(stderr, "ВНУТРЕННЯЯ ОШИБКА: найденный на GPU ключ не проходит проверку на CPU. Результат отброшен.\n");
        return 1;
    }

    std::string report;
    report += "bounceable    (EQ..): " + eq + (ends(eq) ? "   <== нужное окончание" : "") + "\n";
    report += "non-bounceable (UQ..): " + uq + (ends(uq) ? "   <== нужное окончание" : "") + "\n";
    report += "raw:            0:" + tv_hex(h, 32) + "\n";
    report += "wallet:         v4R2, workchain 0, wallet_id " + std::to_string(hres.wid) + "\n";
    report += "public key:     " + tv_hex(pk, 32) + "\n";
    report += "private seed:   " + tv_hex(hres.seed, 32) + "\n";
    report += "secret (seed||pub): " + tv_hex(hres.seed, 32) + tv_hex(pk, 32) + "\n";
    char tail[128];
    snprintf(tail, sizeof tail, "найдено за %.1f с, %.3e проверок\n", elapsed, checks);
    report += tail;
    printf("\n%s", report.c_str());

    FILE* f = fopen(out.c_str(), "a");
    if (f) {
        fprintf(f, "%s\n", report.c_str());
        fclose(f);
#ifndef _WIN32
        chmod(out.c_str(), 0600);
#endif
        fprintf(stderr, "Результат дописан в %s (содержит приватный ключ - храните в секрете)\n", out.c_str());
    } else {
        fprintf(stderr, "Не удалось записать %s\n", out.c_str());
    }
    cudaFree(dtbl); cudaFree(dtargets); cudaFree(dres);
    return 0;
}
