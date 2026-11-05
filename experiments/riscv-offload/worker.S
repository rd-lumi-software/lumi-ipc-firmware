/* RV32 privileged CSR setup follows vendor startup (crt0.boot.S).
 * Disable interrupts: the bounded worker does not own the ISP mailbox ABI.
 */
.section .vectors,"ax"
.option norvc
.org 0x80
.global _start
_start:
    csrw mstatus, zero
    csrw mie, zero
    la t0, trap
    csrw mtvec, t0
    li sp, 0x07fff000
    call worker_main
trap:
    li t0, 0x07fff800
    csrr t1, mcause
    sw t1, 40(t0)
    csrr t1, mepc
    sw t1, 44(t0)
1:  wfi
    j 1b
