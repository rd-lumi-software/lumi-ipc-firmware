/* Pinned resident-VIC interrupt ABI. Original code/data remain untouched. */
.section .text.start,"ax"
.option norvc
.org 0x80
.global _start
_start:
 fence.i
 fence rw,rw
 csrw mstatus, zero
 csrw mie, zero
 .option push
 .option norelax
 la gp, __global_pointer$
 .option pop
 la sp, __stack_top
 la t0, __bss_start
 la t1, __bss_end
1: bgeu t0, t1, 2f
 sw zero, 0(t0)
 addi t0, t0, 4
 j 1b
2:
 li t0, 0x07ffe000
 csrw mtvec, t0
 /* Existing timer/mailbox interrupt handlers save/restore all integer regs. */
 li t0, 0x07ffe65a
 jalr ra, t0, 0
 li t0, 0x10080
 csrw mie, t0
 csrsi mstatus, 8
 call worker_main
3: wfi
 j 3b

/* Resume resident main directly: reset startup would erase live VIC BSS. */
.global mcu_return_to_vic
mcu_return_to_vic:
 csrw mstatus, zero
 csrw mie, zero
 li sp, 0x07fff100
 li gp, 0
 li t0, 0x07ffe000
 csrw mtvec, t0
 fence rw,rw
 li t0, 0x07ffe7ba
 jr t0
