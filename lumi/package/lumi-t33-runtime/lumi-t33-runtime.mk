# Dependencies remain built by their source-owned build recipes. Buildroot owns
# the package lifecycle and isolates all mutable source copies under BUILD_DIR.
LUMI_T33_RUNTIME_VERSION = compact
LUMI_T33_RUNTIME_SOURCE =
LUMI_T33_RUNTIME_DEPENDENCIES = lumi-t33-platform
LUMI_T33_RUNTIME_LICENSE = Proprietary

define LUMI_T33_RUNTIME_BUILD_CMDS
	$(HOST_MAKE_ENV) LUMI_RUNTIME_BUILD="$(@D)" LUMI_BUILD_VOICE="$(if $(filter y,$(BR2_PACKAGE_LUMI_T33_VOICE)),1,0)" \
		LUMI_BUILD_JOBS="$(PARALLEL_JOBS)" bash $(BR2_EXTERNAL_LUMI_PATH)/scripts/build-t33-runtime.sh
endef

define LUMI_T33_RUNTIME_INSTALL_TARGET_CMDS
	T33_RUNTIME_DIR="$(@D)/source/lumi-ipc-streamer/target/artifacts/t33gs-runtime" \
	 T33_RISCV_IMAGE="$(@D)/riscv-wakeword/wake.rvpack" \
	 T33_KERNEL_COPYING="$(LUMI_T33_PLATFORM_DIR)/sdk-build/sdk/kernel-4.4.94/COPYING" \
	 bash $(BR2_EXTERNAL_LUMI_PATH)/scripts/install-t33-runtime.sh $(TARGET_DIR)
endef

$(eval $(generic-package))
