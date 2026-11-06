OUTPUT_ARCH(riscv)
ENTRY(_start)
/* Supplied with --defsym=REGION_BASE=... after an owned allocation. */
MEMORY { DDR (rwx) : ORIGIN = REGION_BASE, LENGTH = 0xff000 }
SECTIONS {
 .text : { KEEP(*(.text.start)) *(.text*) *(.rodata*) } > DDR
 .data : { *(.data*) *(.sdata*) } > DDR
 __global_pointer$ = . + 0x800;
 .bss (NOLOAD) : { . = ALIGN(16); __bss_start = .; *(.bss*) *(.sbss*) *(COMMON) . = ALIGN(16); __bss_end = .; } > DDR
 __heap_start = ALIGN(16);
 __heap_end = ORIGIN(DDR) + LENGTH(DDR) - 0x10000;
 __shared_base = ORIGIN(DDR) + LENGTH(DDR);
 __stack_top = ORIGIN(DDR) + LENGTH(DDR);
 ASSERT(__heap_start < __heap_end, "worker/arena leaves no bounded heap")
}
