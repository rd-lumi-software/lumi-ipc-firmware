#include "worker-abi.h"

static inline uint32_t cycle(void)
{
    /* Match vendor riscv_timer.c:get_mtime(). MCYCLE did not advance in trial 1. */
    return *(volatile uint32_t *)UINT32_C(0x12220010);
}

static inline void idle_poll(void)
{
    unsigned int n = 32768;
    /* Register-only RV32I loop bounds polling traffic; not a calibrated delay. */
    __asm__ volatile ("1: addi %0, %0, -1\n\tbnez %0, 1b" : "+r"(n));
}

static inline void publish(void)
{
    /* RISC-V FENCE orders memory IO; cacheability must be checked on board. */
    __asm__ volatile ("fence rw,rw" ::: "memory");
}

void worker_main(void)
{
    volatile struct worker_shared *s = (void *)WORKER_SHARED;
    uint32_t previous = cycle();
    s->version = 1;
    publish();
    s->magic = WORKER_MAGIC;
    for (;;) {
        idle_poll();
        uint32_t now = cycle();
        /* 10 ms at the observed 475 MHz; approximate heartbeat, not a clock API. */
        if ((uint32_t)(now - previous) >= 4750000) {
            s->heartbeat++;
            previous = now;
        }
        uint32_t request = s->request;
        if (request == s->complete)
            continue;
        publish();
        uint32_t start = cycle(), peak = 0, crossings = 0;
        uint64_t energy = 0;
        int32_t last = s->samples[0];
        for (unsigned int i = 0; i < FRAME_SAMPLES; i++) {
            int32_t x = s->samples[i];
            uint32_t magnitude = (uint32_t)(x < 0 ? -x : x);
            energy += (uint32_t)(x * x);
            if (magnitude > peak)
                peak = magnitude;
            if (i && ((x < 0) != (last < 0)))
                crossings++;
            last = x;
        }
        s->energy_lo = (uint32_t)energy;
        s->energy_hi = (uint32_t)(energy >> 32);
        s->peak = peak;
        s->crossings = crossings;
        s->cycles = cycle() - start;
        publish();
        s->complete = request;
    }
}
