#ifndef LUMI_MCU_WORKER_ABI_H
#define LUMI_MCU_WORKER_ABI_H
#include <stdint.h>
#define WORKER_BASE UINT32_C(0x07ffe000)
#define WORKER_SHARED UINT32_C(0x07fff800)
#define WORKER_MAGIC UINT32_C(0x4c554d49)
#define FRAME_SAMPLES 160
struct worker_shared {
    uint32_t magic, version, heartbeat, request, complete;
    uint32_t energy_lo, energy_hi, peak, crossings, cycles;
    uint32_t trap_cause, trap_pc;
    int16_t samples[FRAME_SAMPLES];
};
_Static_assert(sizeof(struct worker_shared) == 368, "MCU wire ABI");
#endif
