MIPS_PREFIX ?= /home/hieunm/workspace/toolchain/ingenic/T33/mipsel-linux-muslsf-cross/bin/mipsel-linux-muslsf-
RISCV_PREFIX ?= /home/hieunm/workspace/poc/rockchip/rv1103b_sdk/sysdrv/source/mcu/prebuilts/gcc/linux-x86/riscv64/xpack-riscv-none-embed-gcc-10.2.0-1.2/bin/riscv-none-embed-
SDK_SOURCE ?= /home/hieunm/workspace/toolchain/riscv_project_t33_inspect/riscv_project_t33

.PHONY: all sdk
all: artifacts/t33-mcu-inspect artifacts/t33-mcu-trial artifacts/worker.bin

artifacts:
	mkdir -p $@

artifacts/t33-mcu-inspect: inspect.c | artifacts
	$(MIPS_PREFIX)gcc -Os -static -std=c11 -Wall -Wextra -Werror -Wformat=2 -o $@ $<

artifacts/t33-mcu-trial: trial.c worker-abi.h | artifacts
	$(MIPS_PREFIX)gcc -Os -static -std=c11 -Wall -Wextra -Werror -Wformat=2 -o $@ $<

artifacts/worker.elf: worker.S worker.c worker.ld worker-abi.h | artifacts
	$(RISCV_PREFIX)gcc -Os -march=rv32imc -mabi=ilp32 -msmall-data-limit=0 -mno-relax -ffreestanding -fno-builtin -fno-stack-protector -nostdlib -Wall -Wextra -Werror -T worker.ld -Wl,--no-relax,-Map,artifacts/worker.map worker.S worker.c -o $@

artifacts/worker.bin: artifacts/worker.elf
	$(RISCV_PREFIX)objcopy -O binary $< $@

# A fresh private copy keeps vendor inputs and all other worktrees untouched.
# Refuse reuse so sensor headers and old objects cannot contaminate this build.
sdk: | artifacts
	test ! -e artifacts/sdk-build
	cp -a "$(SDK_SOURCE)" artifacts/sdk-build
	$(MAKE) -C artifacts/sdk-build clean
	$(MAKE) -C artifacts/sdk-build -j4 SENSOR_NUM=1 SENSOR0=sc4336p PREFIX="$(RISCV_PREFIX)"
