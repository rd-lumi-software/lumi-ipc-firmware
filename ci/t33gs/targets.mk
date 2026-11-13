T33GS_LOCAL_ROOT := $(abspath $(dir $(lastword $(MAKEFILE_LIST)))/../..)
T33GS_LOCAL_CONFIG ?= $(T33GS_LOCAL_ROOT)/ci/t33gs/local.mk

# Local configuration must not alter the inherited default goal or BOARD flow.
ifneq ($(filter t33gs-plan t33gs-prepare t33gs-full t33gs-legacy-full,$(MAKECMDGOALS))$(if $(filter lumi_t33gs_prj008_sc4336,$(BOARD)),$(if $(filter 1,$(LUMI_T33_IN_CONTAINER)),,yes)),)
include $(T33GS_LOCAL_CONFIG)
endif

T33GS_BUILDER_IMAGE ?= lumi-t33gs-builder:local
T33GS_VOICE ?= 1
T33GS_JOBS ?= 4
# Explicit -jN wins; bare -j uses the configured limit across Docker.
T33GS_EFFECTIVE_JOBS = $(or $(patsubst -j%,%,$(lastword $(filter-out -j,$(filter -j%,$(MAKEFLAGS))))),$(T33GS_JOBS))
T33GS_WORKSPACE ?=
export T33GS_LOCAL_CONFIG T33GS_WORKSPACE T33GS_BUILDER_IMAGE T33GS_VOICE T33GS_JOBS
export T33GS_FIRMWARE_SRC T33GS_STREAMER_SRC T33GS_LINUX_SRC T33GS_UBOOT_SRC T33GS_RELAY_SRC
export T33GS_TFLM_SRC T33GS_OPUS_SRC T33GS_BUILDROOT_SRC T33GS_KERNEL_SRC T33GS_DRIVERS_SRC T33GS_AIC_SRC
export T33GS_UCLIBC_TOOLCHAIN T33GS_MUSL_TOOLCHAIN T33GS_IMP_HEADERS T33GS_VENDOR_LIBRARIES
export T33GS_SENSOR_TUNING T33GS_WIFI_FIRMWARE T33GS_RELAY_CERTIFICATE

.PHONY: t33gs-help t33gs-plan t33gs-prepare t33gs-full t33gs-test
t33gs-help:
	@printf '%s\n' \
	  'make t33gs-plan       Check local source and SDK paths' \
	  'make t33gs-prepare    Copy source to a fresh workspace' \
	  'make t33gs-full       Build all components, full NOR firmware and OTA' \
	  'make t33gs-test       Test source snapshots, SDK checks and image packaging' \
	  'T33GS_LOCAL_CONFIG=/absolute/path/local.mk (default: ci/t33gs/local.mk)' \
	  'T33GS_WORKSPACE=/absolute/path/new-directory (default: firmware/output/t33gs-local-XXXXXX)' \
	  'T33GS_VOICE=0|1 T33GS_JOBS=4'

t33gs-plan t33gs-prepare t33gs-full:
	@T33GS_JOBS="$(T33GS_EFFECTIVE_JOBS)" bash "$(T33GS_LOCAL_ROOT)/ci/t33gs/local.sh" "$@"

# These checks need no local SDK configuration, Docker or camera.
t33gs-test:
	@bash "$(T33GS_LOCAL_ROOT)/ci/t33gs/test-local.sh"
	@python3 "$(T33GS_LOCAL_ROOT)/ci/t33gs/test_pipeline.py"

.PHONY: lumi-board-full
# MAKEFLAGS carries an explicit -jN; forward N across the container boundary.
lumi-board-full:
	@T33GS_JOBS="$(T33GS_EFFECTIVE_JOBS)" LUMI_T33_BUILD_SCRIPT=build-board.sh bash "$(T33GS_LOCAL_ROOT)/ci/t33gs/local.sh" t33gs-full

.PHONY: t33gs-legacy-full
t33gs-legacy-full:
	@T33GS_JOBS="$(T33GS_EFFECTIVE_JOBS)" LUMI_T33_BUILD_SCRIPT=build.sh bash "$(T33GS_LOCAL_ROOT)/ci/t33gs/local.sh" t33gs-full
