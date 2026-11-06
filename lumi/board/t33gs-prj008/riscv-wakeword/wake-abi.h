#ifndef LUMI_WAKE_ABI_H
#define LUMI_WAKE_ABI_H
#include <stdint.h>
#define WAKE_MAGIC UINT32_C(0x57414b45)
#define WAKE_VERSION 3
struct wake_shared {
 uint32_t magic, version, heartbeat, request, complete;
 uint32_t command; /* bit0: reset before processing; bit1: two steps (320 samples) */
 int32_t status;
 uint32_t raw_score, row_valid, ticks, arena_used, error;
 int8_t features[40];
 int16_t samples[160];
 uint32_t mstatus, mie, mip, mtvec;
 int16_t second_samples[160];
 int32_t second_status;
 uint32_t second_raw_score;
};
_Static_assert(sizeof(struct wake_shared) == 752, "wake wire ABI");
#endif
