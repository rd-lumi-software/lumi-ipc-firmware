/* Bounded, RAM-only MCU trial for the inspected T33gs resident VIC image.
 * Stop/start sequence: board ISP module tx_isp_riscv_run/stop disassembly.
 * A parent guardian retains the original RAM image and restores it even when
 * the trial child fails, times out or receives a signal. SIGKILL of the parent
 * or a kernel failure still requires the verified UART recovery path.
 */
#define _GNU_SOURCE
#include "worker-abi.h"
#include <errno.h>
#include <fcntl.h>
#include <inttypes.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>

#define REGION_SIZE 8192
#define STOP UINT32_C(0x80000000)
#define REG(p, off) ((p)[(off) / 4])
static volatile sig_atomic_t interrupted;

static void signal_stop(int sig) { (void)sig; interrupted = 1; }
static void barrier(void) { __sync_synchronize(); }
static uint64_t milliseconds(void)
{
    struct timespec t;
    if (clock_gettime(CLOCK_MONOTONIC, &t))
        _exit(90);
    return (uint64_t)t.tv_sec * 1000 + (unsigned long)t.tv_nsec / 1000000;
}

static int load_file(const char *path, void *buf, size_t limit, size_t *size)
{
    struct stat st;
    int fd = open(path, O_RDONLY);
    if (fd < 0 || fstat(fd, &st)) {
        perror(path);
        if (fd >= 0) close(fd);
        return -1;
    }
    if (st.st_size <= 0 || (uint64_t)st.st_size > limit) {
        fprintf(stderr, "Invalid file size: %s\n", path);
        close(fd);
        return -1;
    }
    *size = (size_t)st.st_size;
    size_t done = 0;
    while (done < *size) {
        ssize_t n = read(fd, (char *)buf + done, *size - done);
        if (n < 0 && errno == EINTR) continue;
        if (n <= 0) { close(fd); return -1; }
        done += (size_t)n;
    }
    return close(fd);
}

static int save_backup(const char *path, const void *buf)
{
    int fd = open(path, O_WRONLY | O_CREAT | O_EXCL, 0600);
    if (fd < 0) { perror(path); return -1; }
    size_t done = 0;
    while (done < REGION_SIZE) {
        ssize_t n = write(fd, (const char *)buf + done, REGION_SIZE - done);
        if (n < 0 && errno == EINTR) continue;
        if (n <= 0) { close(fd); return -1; }
        done += (size_t)n;
    }
    int rc = fsync(fd);
    if (close(fd)) rc = -1;
    return rc;
}

static int stop_mcu(volatile uint32_t *ccu)
{
    REG(ccu, 0xf0) |= STOP;
    barrier();
    /* Bounded settling allowance for this experiment, not a datasheet minimum. */
    usleep(1000);
    return (REG(ccu, 0xf0) & STOP) ? 0 : -1;
}

static void start_mcu(volatile uint32_t *ccu, uint32_t vector, uint32_t control)
{
    /* Match the vendor driver; interrupts/masks stay off in our worker. */
    REG(ccu, 0) = 0x23;
    REG(ccu, 4) = vector;
    REG(ccu, 0x20) = 0;
    REG(ccu, 0x24) = 0;
    barrier();
    REG(ccu, 0xf0) = control & ~STOP;
    barrier();
}

static int run_trial(volatile uint32_t *ccu, unsigned char *ram,
                     const unsigned char *image, size_t image_size)
{
    if (stop_mcu(ccu)) return 1;
    memset(ram, 0, REGION_SIZE);
    memcpy(ram, image, image_size);
    barrier();
    if (memcmp(ram, image, image_size)) return 1;
    start_mcu(ccu, WORKER_BASE + 0x80, 0);
    volatile struct worker_shared *s = (void *)(ram + WORKER_SHARED - WORKER_BASE);
    uint64_t deadline = milliseconds() + 500;
    while ((s->magic != WORKER_MAGIC || s->heartbeat < 2) && milliseconds() < deadline)
        usleep(1000);
    if (s->magic != WORKER_MAGIC || s->heartbeat < 2 || s->version != 1) {
        printf("BOOT_FAIL magic=%08" PRIx32 " heartbeat=%" PRIu32
               " trap=%08" PRIx32 " pc=%08" PRIx32 "\n",
               s->magic, s->heartbeat, s->trap_cause, s->trap_pc);
        return 1;
    }
    printf("MCU_HEARTBEAT magic=%08" PRIx32 " count=%" PRIu32 "\n",
           s->magic, s->heartbeat);
    uint32_t min_cycles = UINT32_MAX, max_cycles = 0;
    for (uint32_t request = 1; request <= 32; request++) {
        if (REG(ccu, 8) || REG(ccu, 12)) {
            puts("ISP mailbox activity: ending trial");
            return 1;
        }
        uint64_t energy = 0;
        uint32_t peak = 0, crossings = 0;
        int32_t last = 0;
        for (unsigned int i = 0; i < FRAME_SAMPLES; i++) {
            int32_t x;
            switch (request % 4) {
            case 0: x = 0; break;
            case 1: x = i & 1 ? 32767 : -32768; break;
            case 2: x = (int32_t)i * 311 - 24000; break;
            default: x = (int32_t)((i * 8191 + request * 131) & 65535) - 32768;
            }
            s->samples[i] = (int16_t)x;
            energy += (uint32_t)(x * x);
            uint32_t magnitude = (uint32_t)(x < 0 ? -x : x);
            if (magnitude > peak) peak = magnitude;
            if (i && ((x < 0) != (last < 0))) crossings++;
            last = x;
        }
        barrier();
        s->request = request;
        barrier();
        deadline = milliseconds() + 100;
        while (s->complete != request && milliseconds() < deadline)
            usleep(100);
        barrier();
        uint64_t actual = ((uint64_t)s->energy_hi << 32) | s->energy_lo;
        if (s->complete != request || actual != energy || s->peak != peak ||
            s->crossings != crossings || s->trap_cause) {
            printf("JOB_FAIL request=%" PRIu32 " complete=%" PRIu32
                   " energy=%" PRIu64 " expected=%" PRIu64 "\n",
                   request, s->complete, actual, energy);
            return 1;
        }
        if (s->cycles < min_cycles) min_cycles = s->cycles;
        if (s->cycles > max_cycles) max_cycles = s->cycles;
    }
    printf("MCU_JOBS_PASS frames=32 samples_per_frame=160 min_cycles=%" PRIu32
           " max_cycles=%" PRIu32 "\n", min_cycles, max_cycles);
    return 0;
}

int main(int argc, char **argv)
{
    unsigned char expected[REGION_SIZE], backup[REGION_SIZE], image[2048];
    size_t expected_size = 0, image_size = 0;
    if (argc != 4) {
        fprintf(stderr, "Usage: %s worker.bin expected-resident.bin new-backup.bin\n", argv[0]);
        return 2;
    }
    setvbuf(stdout, NULL, _IOLBF, 0);
    if (load_file(argv[1], image, sizeof(image), &image_size) ||
        load_file(argv[2], expected, sizeof(expected), &expected_size) ||
        expected_size != REGION_SIZE || image_size <= 0x80)
        return 2;
    int fd = open("/dev/mem", O_RDWR | O_SYNC);
    if (fd < 0) { perror("/dev/mem"); return 1; }
    volatile uint32_t *ccu = mmap(NULL, 4096, PROT_READ | PROT_WRITE, MAP_SHARED, fd, 0x12220000);
    unsigned char *ram = mmap(NULL, REGION_SIZE, PROT_READ | PROT_WRITE, MAP_SHARED, fd, WORKER_BASE);
    if (ccu == MAP_FAILED || ram == MAP_FAILED) {
        perror("mmap");
        return 1;
    }
    uint32_t control = REG(ccu, 0xf0), vector = REG(ccu, 4);
    if (control || vector != WORKER_BASE + 0x80 || REG(ccu, 0) != 0x3f ||
        REG(ccu, 8) || REG(ccu, 12) || REG(ccu, 0x20) || REG(ccu, 0x24) ||
        REG(ccu, 0x78) != 0x1f || REG(ccu, 0x7c) != 0x3f ||
        memcmp(expected, ram, REGION_SIZE)) {
        fputs("Preflight mismatch; no MCU writes performed\n", stderr);
        return 2;
    }
    /* The VIC BSS command state must be idle before temporarily borrowing MCU. */
    for (unsigned int i = 0x8d8; i < 0x8fc; i++)
        if (ram[i]) { fputs("VIC busy; trial refused\n", stderr); return 2; }
    memcpy(backup, ram, REGION_SIZE);
    if (save_backup(argv[3], backup)) return 1;
    uint32_t timer_lo = REG(ccu, 0x10), timer_hi = REG(ccu, 0x14);
    uint32_t cmp_lo = REG(ccu, 0x18), cmp_hi = REG(ccu, 0x1c);
    struct sigaction sa = {0};
    sa.sa_handler = signal_stop;
    sigemptyset(&sa.sa_mask);
    if (sigaction(SIGINT, &sa, NULL) || sigaction(SIGTERM, &sa, NULL) ||
        sigaction(SIGHUP, &sa, NULL)) return 1;
    pid_t child = fork();
    if (child < 0) { perror("fork"); return 1; }
    if (!child) {
        signal(SIGINT, SIG_DFL);
        signal(SIGTERM, SIG_DFL);
        signal(SIGHUP, SIG_DFL);
        _exit(run_trial(ccu, ram, image, image_size));
    }
    int status = 0, timed_out = 0;
    uint64_t end = milliseconds() + 3000;
    for (;;) {
        pid_t result = waitpid(child, &status, WNOHANG);
        if (result == child) break;
        if (result < 0 && errno != EINTR) { timed_out = 1; break; }
        if (interrupted || milliseconds() >= end) {
            timed_out = 1;
            kill(child, SIGKILL);
            while (waitpid(child, &status, 0) < 0 && errno == EINTR) { }
            break;
        }
        usleep(1000);
    }
    if (stop_mcu(ccu)) {
        fputs("CRITICAL: cannot stop trial MCU; use UART reboot\n", stderr);
        return 1;
    }
    memcpy(ram, backup, REGION_SIZE);
    barrier();
    if (memcmp(ram, backup, REGION_SIZE)) {
        fputs("CRITICAL: RAM restoration mismatch; MCU left stopped, use UART reboot\n", stderr);
        return 1;
    }
    REG(ccu, 0x10) = timer_lo;
    REG(ccu, 0x14) = timer_hi;
    REG(ccu, 0x18) = cmp_lo;
    REG(ccu, 0x1c) = cmp_hi;
    start_mcu(ccu, vector, control);
    usleep(20000);
    barrier();
    int restored = !memcmp(ram, backup, 0x8d8) && REG(ccu, 4) == vector &&
                   REG(ccu, 0xf0) == control && REG(ccu, 0) == 0x3f;
    printf("VIC_RESTORED=%d trial_timeout=%d child_status=%d\n", restored, timed_out, status);
    if (munmap(ram, REGION_SIZE) || munmap((void *)ccu, 4096) || close(fd)) return 1;
    return (!restored || timed_out || !WIFEXITED(status) || WEXITSTATUS(status)) ? 1 : 0;
}
