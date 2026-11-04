/* libhwz: the few things Linux HW-Z needs native code for.
 *
 *  - hwz_cpuid(): the CPUID instruction (user mode, no root needed)
 *  - hwz_bench_chunks(): the CPU benchmark / stress workload.  It is called
 *    from several Python threads at once; ctypes releases the GIL, so each
 *    call keeps one hardware thread fully busy.
 *
 * Build: gcc -O2 -march=x86-64-v2 -fPIC -shared -o libhwz.so libhwz.c
 */
#include <stdint.h>
#include <string.h>
#include <time.h>
#include <cpuid.h>

#define HWZ_API __attribute__((visibility("default")))

HWZ_API int hwz_version(void) { return 1; }

HWZ_API void hwz_cpuid(uint32_t leaf, uint32_t sub, uint32_t out[4]) {
    uint32_t a = 0, b = 0, c = 0, d = 0;
    __cpuid_count(leaf, sub, a, b, c, d);
    out[0] = a; out[1] = b; out[2] = c; out[3] = d;
}

HWZ_API uint64_t hwz_rdtsc(void) {
    uint32_t lo, hi;
    __asm__ __volatile__("rdtsc" : "=a"(lo), "=d"(hi));
    return ((uint64_t)hi << 32) | lo;
}

static double now_s(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return ts.tv_sec + ts.tv_nsec * 1e-9;
}

/* One "chunk" = a fixed amount of mixed integer + floating point work that
 * touches a 64 KiB working set (L1/L2 resident), roughly what a compression
 * or rendering inner loop does. */
#define BUF_WORDS (16384)

static uint64_t chunk(uint64_t seed, uint32_t *buf, double *facc) {
    uint64_t x = seed | 1;
    uint32_t h = 2166136261u;
    /* integer part: xorshift + hashed table updates + data-dependent branches */
    for (int i = 0; i < 4096; i++) {
        x ^= x << 13; x ^= x >> 7; x ^= x << 17;
        uint32_t idx = (uint32_t)(x >> 18) & (BUF_WORDS - 1);
        uint32_t v = buf[idx];
        h = (h ^ v) * 16777619u;
        if (h & 0x10) buf[idx] = v + (uint32_t)x;
        else buf[(idx + 7) & (BUF_WORDS - 1)] ^= h;
    }
    /* floating point part: a small Mandelbrot tile */
    double acc = 0.0;
    for (int py = 0; py < 8; py++) {
        for (int px = 0; px < 8; px++) {
            double cr = -2.0 + ((x >> (px + 3)) & 0xff) / 100.0 + px * 0.01;
            double ci = -1.2 + ((h >> (py + 2)) & 0xff) / 110.0 + py * 0.01;
            double zr = 0, zi = 0;
            int it = 0;
            for (; it < 48; it++) {
                double zr2 = zr * zr, zi2 = zi * zi;
                if (zr2 + zi2 > 4.0) break;
                zi = 2.0 * zr * zi + ci;
                zr = zr2 - zi2 + cr;
            }
            acc += it + zr * 1e-3;
        }
    }
    *facc += acc;
    return x ^ h;
}

/* Run chunks for `seconds` (or until *stop becomes non-zero).
 * Returns the number of chunks completed. */
HWZ_API uint64_t hwz_bench_chunks(double seconds, volatile int *stop, uint64_t seed) {
    static __thread uint32_t buf[BUF_WORDS];
    for (int i = 0; i < BUF_WORDS; i++) buf[i] = (uint32_t)(i * 2654435761u);
    double facc = 0.0;
    uint64_t n = 0, s = seed;
    double t0 = now_s(), deadline = t0 + seconds;
    for (;;) {
        for (int k = 0; k < 16; k++) { s = chunk(s, buf, &facc); n++; }
        if ((stop && *stop) || now_s() >= deadline) break;
    }
    /* keep the compiler from discarding the work */
    if (facc == 1.2345) n++;
    return n;
}
