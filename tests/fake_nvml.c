/* A stand-in for libnvidia-ml.so.1 that returns fixed RTX 4070 values (tests only).
 * gcc -shared -fPIC -o fake_nvml.so fake_nvml.c */
#include <string.h>
typedef struct { unsigned long long total, free, used; } mem_t;
typedef struct { unsigned int gpu, memory; } util_t;
static int h = 1;
int nvmlInit_v2(void) { return 0; }
int nvmlDeviceGetHandleByPciBusId_v2(const char *id, void **out) {
    if (strcmp(id, "00000000:01:00.0") != 0) return 6;
    *out = &h; return 0;
}
int nvmlDeviceGetName(void *d, char *b, unsigned n) { strncpy(b, "NVIDIA GeForce RTX 4070", n); return 0; }
int nvmlDeviceGetVbiosVersion(void *d, char *b, unsigned n) { strncpy(b, "95.04.31.00.4A", n); return 0; }
int nvmlSystemGetDriverVersion(char *b, unsigned n) { strncpy(b, "560.35.03", n); return 0; }
int nvmlDeviceGetMemoryInfo(void *d, mem_t *m) { m->total = 12ULL << 30; m->used = 812ULL << 20; m->free = m->total - m->used; return 0; }
int nvmlDeviceGetMemoryBusWidth(void *d, unsigned *v) { *v = 192; return 0; }
int nvmlDeviceGetNumGpuCores(void *d, unsigned *v) { *v = 5888; return 0; }
int nvmlDeviceGetMaxClockInfo(void *d, int t, unsigned *v) { *v = t == 0 ? 3105 : 10501; return 0; }
int nvmlDeviceGetClockInfo(void *d, int t, unsigned *v) { *v = t == 0 ? 2475 : t == 2 ? 10501 : 1950; return 0; }
int nvmlDeviceGetEnforcedPowerLimit(void *d, unsigned *v) { *v = 200000; return 0; }
int nvmlDeviceGetMaxPcieLinkGeneration(void *d, unsigned *v) { *v = 4; return 0; }
int nvmlDeviceGetMaxPcieLinkWidth(void *d, unsigned *v) { *v = 16; return 0; }
int nvmlDeviceGetCurrPcieLinkGeneration(void *d, unsigned *v) { *v = 1; return 0; }
int nvmlDeviceGetCurrPcieLinkWidth(void *d, unsigned *v) { *v = 16; return 0; }
int nvmlDeviceGetTemperature(void *d, int s, unsigned *v) { *v = 47; return 0; }
int nvmlDeviceGetFanSpeed(void *d, unsigned *v) { *v = 30; return 0; }
int nvmlDeviceGetPowerUsage(void *d, unsigned *v) { *v = 23450; return 0; }
int nvmlDeviceGetUtilizationRates(void *d, util_t *u) { u->gpu = 4; u->memory = 2; return 0; }
int nvmlDeviceGetEncoderUtilization(void *d, unsigned *v, unsigned *p) { *v = 0; *p = 0; return 0; }
int nvmlDeviceGetDecoderUtilization(void *d, unsigned *v, unsigned *p) { *v = 11; *p = 0; return 0; }
int nvmlDeviceGetPerformanceState(void *d, int *v) { *v = 8; return 0; }
