OUTPUT_ARCH(riscv)
ENTRY(_start)
MEMORY { code (rwx) : ORIGIN = 0x07ffe000, LENGTH = 0x800 }
SECTIONS {
    .vectors : { KEEP(*(.vectors)) } > code
    .text : { *(.text*) *(.rodata*) } > code
    .data : { *(.data*) *(.sdata*) } > code
    .bss : { *(.bss*) *(.sbss*) *(COMMON) } > code
    ASSERT(SIZEOF(.data) == 0, "worker must not need data initialization")
    ASSERT(SIZEOF(.bss) == 0, "worker must not need BSS initialization")
}
