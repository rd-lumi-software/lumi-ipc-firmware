/* Read-only inspection of the exact T33gs layout verified in the ISP driver.
 * MCU registers: vendor riscv_project_t33/include/riscv.h.
 * Resident allocation: tx_isp_riscv_probe reserves the last 8192 rmem bytes.
 * This program deliberately has no write/reset/run/mailbox command.
 */
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <sys/mman.h>
#include <unistd.h>

#define RESIDENT UINT32_C(0x07ffe000)
#define RESIDENT_SIZE 8192
#define REG(p, off) ((p)[(off) / sizeof(uint32_t)])

static void *map_ro(int fd, uint32_t address, size_t size)
{
    void *p = mmap(NULL, size, PROT_READ, MAP_SHARED, fd, address);
    if (p == MAP_FAILED)
        perror("mmap read-only");
    return p;
}

static int dump_resident(int fd)
{
    const unsigned char *p = map_ro(fd, RESIDENT, RESIDENT_SIZE);
    size_t done = 0;
    int rc = 0;
    if (p == MAP_FAILED)
        return 1;
    while (done < RESIDENT_SIZE) {
        ssize_t n = write(STDOUT_FILENO, p + done, RESIDENT_SIZE - done);
        if (n < 0 && errno == EINTR)
            continue;
        if (n <= 0) {
            perror("write stdout");
            rc = 1;
            break;
        }
        done += (size_t)n;
    }
    if (munmap((void *)p, RESIDENT_SIZE)) {
        perror("munmap resident");
        rc = 1;
    }
    return rc;
}

int main(int argc, char **argv)
{
    int rc = 1, dump = 0;
    volatile uint32_t *cpm, *ccu;
    if (argc == 2 && !strcmp(argv[1], "dump-resident"))
        dump = 1;
    else if (argc != 1 && !(argc == 2 && !strcmp(argv[1], "status"))) {
        fprintf(stderr, "Usage: %s [status|dump-resident]\n", argv[0]);
        return 2;
    }
    int fd = open("/dev/mem", O_RDONLY | O_SYNC);
    if (fd < 0) {
        perror("open /dev/mem read-only");
        return 1;
    }
    cpm = map_ro(fd, 0x10000000, 4096);
    if (cpm == MAP_FAILED)
        goto close_fd;
    if (REG(cpm, 0x20) & (UINT32_C(1) << 22)) {
        fprintf(stderr, "MCU clock gated; no controller access attempted\n");
        goto unmap_cpm;
    }
    ccu = map_ro(fd, 0x12220000, 4096);
    if (ccu == MAP_FAILED)
        goto unmap_cpm;
    if (dump) {
        if (REG(ccu, 4) != RESIDENT + 0x80) {
            fprintf(stderr, "Unexpected boot vector; resident read refused\n");
        } else {
            rc = dump_resident(fd);
        }
    } else {
        printf("CLKGR0=%08" PRIx32 " RISCV_CLK=%08" PRIx32 "\n",
               REG(cpm, 0x20), REG(cpm, 0x9c));
        printf("CONFIG=%08" PRIx32 " VECTOR=%08" PRIx32
               " CONTROL=%08" PRIx32 "\n",
               REG(ccu, 0), REG(ccu, 4), REG(ccu, 0xf0));
        printf("HOST_TO_MCU=%08" PRIx32 " MCU_TO_HOST=%08" PRIx32 "\n",
               REG(ccu, 8), REG(ccu, 12));
        for (unsigned int i = 0; i < 8; i++)
            printf("PMA%u ADDRESS=%08" PRIx32 " CONFIG=%08" PRIx32 "\n",
                   i, REG(ccu, 0x40 + i * 4), REG(ccu, 0x60 + i * 4));
        puts("Read-only snapshot; not instruction-execution proof.");
        rc = 0;
    }
    if (munmap((void *)ccu, 4096))
        rc = 1;
unmap_cpm:
    if (munmap((void *)cpm, 4096))
        rc = 1;
close_fd:
    if (close(fd))
        rc = 1;
    return rc;
}
