RUNTIME_DIR := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))
FIRMWARE_ROOT := $(abspath $(RUNTIME_DIR)/../../../..)
STREAMER_SOURCE ?= $(abspath $(FIRMWARE_ROOT)/../lumi-ipc-streamer)
WAKE_ARCHIVE ?= $(STREAMER_SOURCE)/target/wakeword-riscv/liboklumi-riscv.a
RISCV_PREFIX ?= riscv-none-embed-
PYTHON ?= python3
BUILD_DIR ?= $(RUNTIME_DIR)/build
# Link addresses are verification fixtures. The Linux owner relocates the pack
# to its actual private allocation; none of these addresses is a deployment target.
LINK_BASES := 0x050d0000 0x04f00000 0x05100000
RV_FLAGS := -Os -march=rv32imc -mabi=ilp32 -msmall-data-limit=0 -mno-relax -ffunction-sections -fdata-sections
OBJECTS := $(BUILD_DIR)/start.o $(BUILD_DIR)/wake-worker.o $(BUILD_DIR)/newlib-heap.o
IMAGES := $(foreach base,$(LINK_BASES),$(BUILD_DIR)/wake-$(base).elf)

.PHONY: all clean
all: $(BUILD_DIR)/wake.rvpack

$(BUILD_DIR):
	mkdir -p "$@"

$(BUILD_DIR)/start.o: $(RUNTIME_DIR)/coexist.S $(RUNTIME_DIR)/Makefile | $(BUILD_DIR)
	$(RISCV_PREFIX)gcc $(RV_FLAGS) -c "$<" -o "$@"

$(BUILD_DIR)/wake-worker.o: $(RUNTIME_DIR)/wake-worker.c $(RUNTIME_DIR)/wake-abi.h $(STREAMER_SOURCE)/adapters/ipc-wakeword/riscv/oklumi_riscv.h $(RUNTIME_DIR)/Makefile | $(BUILD_DIR)
	$(RISCV_PREFIX)gcc $(RV_FLAGS) -Wall -Wextra -Werror -I"$(STREAMER_SOURCE)/adapters/ipc-wakeword/riscv" -c "$<" -o "$@"

$(BUILD_DIR)/newlib-heap.o: $(RUNTIME_DIR)/newlib-heap.c $(RUNTIME_DIR)/Makefile | $(BUILD_DIR)
	$(RISCV_PREFIX)gcc $(RV_FLAGS) -Wall -Wextra -Werror -c "$<" -o "$@"

define link_image
$(BUILD_DIR)/wake-$(1).elf: $(OBJECTS) $(WAKE_ARCHIVE) $(RUNTIME_DIR)/coexist.ld
	$(RISCV_PREFIX)g++ $(RV_FLAGS) -nostartfiles --specs=nosys.specs -Wl,--defsym,REGION_BASE=$(1),--no-relax,--emit-relocs,--gc-sections,-Map,$(BUILD_DIR)/wake-$(1).map -T "$(RUNTIME_DIR)/coexist.ld" $(OBJECTS) "$(WAKE_ARCHIVE)" -lm -o "$$@"
	$(RISCV_PREFIX)size "$$@"
endef
$(foreach base,$(LINK_BASES),$(eval $(call link_image,$(base))))

$(BUILD_DIR)/wake.rvpack: $(IMAGES) $(RUNTIME_DIR)/pack-wake.py
	$(PYTHON) "$(RUNTIME_DIR)/pack-wake.py" "$(word 1,$(IMAGES))" "$@" $(foreach image,$(wordlist 2,3,$(IMAGES)),--compare "$(image)")

# Restrict cleanup to products created by this Makefile, including custom output paths.
clean:
	rm -f $(OBJECTS) $(IMAGES) $(IMAGES:.elf=.map) "$(BUILD_DIR)/wake.rvpack"
