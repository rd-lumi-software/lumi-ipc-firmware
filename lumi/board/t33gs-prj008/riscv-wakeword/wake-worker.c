#include "wake-abi.h"
#include "oklumi_riscv.h"
extern char __shared_base[] __attribute__((aligned(4)));
extern void mcu_return_to_vic(void) __attribute__((noreturn));
#define WORKER_SHARED __shared_base
static uint32_t timer(void) { return *(volatile uint32_t *)0x12220010; }
static void fence(void) { __asm__ volatile("fence rw,rw" ::: "memory"); }
void worker_main(void)
{
 volatile struct wake_shared *s = (void *)WORKER_SHARED;
 int rc = oklumi_rv_init();
 s->version = WAKE_VERSION;
 s->arena_used = oklumi_rv_arena_used();
 s->error = rc ? 1 : 0;
 s->status = rc;
 fence();
 s->magic = WAKE_MAGIC;
 uint32_t previous = timer();
 for (;;) {
  /* Timer IRQ wakes idle MCU; original VIC stays serviced. */
  __asm__ volatile("wfi");
  __asm__ volatile("csrr %0, mstatus" : "=r"(s->mstatus));
  __asm__ volatile("csrr %0, mie" : "=r"(s->mie));
  __asm__ volatile("csrr %0, mip" : "=r"(s->mip));
  __asm__ volatile("csrr %0, mtvec" : "=r"(s->mtvec));
  uint32_t now = timer();
  if ((uint32_t)(now - previous) >= 4750000) { s->heartbeat++; previous = now; }
  __asm__ volatile("fence.i" ::: "memory");
  fence();
  uint32_t request = s->request;
  if (request == s->complete) continue;
  if (s->command == 4) {
   __asm__ volatile("csrci mstatus, 8" ::: "memory");
   fence();
   s->complete = request;
   fence();
   mcu_return_to_vic();
  }
  if (s->error) continue;
  fence();
  uint32_t start = timer();
  int16_t pcm[160];
  int8_t features[40];
  for (unsigned i=0;i<160;i++) pcm[i] = s->samples[i];
  uint8_t score = 0;
  rc = s->command > 3 ? -1 : 0;
  if (!rc && (s->command & 1)) rc = oklumi_rv_reset();
  if (!rc) rc = oklumi_rv_process160(pcm, &score);
  s->row_valid = oklumi_rv_last_features(features) == 1;
  if (s->row_valid) for (unsigned i=0;i<40;i++) s->features[i] = features[i];
  s->raw_score = score;
  s->status = rc;
  s->second_status = 0;
  s->second_raw_score = 0;
  if (rc >= 0 && (s->command & 2)) {
   for (unsigned i=0;i<160;i++) pcm[i] = s->second_samples[i];
   score = 0;
   rc = oklumi_rv_process160(pcm, &score);
   s->second_status = rc;
   s->second_raw_score = score;
  }
  s->ticks = timer() - start;
  if (rc < 0) s->error = 2;
  fence();
  s->complete = request;
 }
}
