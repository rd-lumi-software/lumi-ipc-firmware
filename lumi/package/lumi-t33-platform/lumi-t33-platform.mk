# The SDK needs vendor source preparation and a compiler distinct from TARGET_CC.
# Keep its kernel/module ABI in one package; Buildroot owns ordering and stamps.
LUMI_T33_PLATFORM_VERSION = 4.4.94
LUMI_T33_PLATFORM_SOURCE =
LUMI_T33_PLATFORM_DEPENDENCIES = host-uboot-tools host-kmod
LUMI_T33_PLATFORM_INSTALL_IMAGES = YES
LUMI_T33_PLATFORM_LICENSE = GPL-2.0, Proprietary

LUMI_T33_PLATFORM_ENV = $(HOST_MAKE_ENV) \
	LUMI_LINUX_SOURCE="$(LUMI_WORKSPACE)/lumi-ipc-linux" \
	T33_HOST_TOOLS_DIR="$(HOST_DIR)" \
	T33_4494_OUTPUT_DIR="$(LUMI_T33_PLATFORM_DIR)/sdk-build" \
	T33_BUILD_JOBS="$(PARALLEL_JOBS)"

define LUMI_T33_PLATFORM_BUILD_CMDS
	# linux-patcher exports a name for the ordinary Buildroot Linux package.
	# The SDK kernel must use its own release, which the OTA updater verifies.
	$(LUMI_T33_PLATFORM_ENV) env -u UIMAGE_NAME -u GIT_DIR bash $(BR2_EXTERNAL_LUMI_PATH)/../contrib/build-t33gs-k4494.sh --all
endef

define LUMI_T33_PLATFORM_INSTALL_TARGET_CMDS
	mkdir -p $(TARGET_DIR)/lib/modules $(TARGET_DIR)/lumi/bin
	cp -a $(LUMI_T33_PLATFORM_DIR)/sdk-build/artifacts/modules-root/lib/modules/. $(TARGET_DIR)/lib/modules/
	cp -a $(LUMI_INPUTS)/board/. $(TARGET_DIR)/
	"$(T33_TOOLCHAIN_ROOT)/bin/mips-linux-uclibc-gcc" -Os -s -march=mips32r2 \
	 -I"$(LUMI_WORKSPACE)/lumi-ipc-linux/kernel/ingenic/t33gs-tnpu" \
	 -Wl,--dynamic-linker=/opt/ingenic-t33/lib/ld-uClibc-0.9.33.2.so -Wl,-rpath,/opt/ingenic-t33/lib \
	 "$(LUMI_WORKSPACE)/lumi-ipc-linux/kernel/ingenic/t33gs-tnpu/vendor-monitor/utilization.c" \
	 -o $(TARGET_DIR)/lumi/bin/utilization
endef

define LUMI_T33_PLATFORM_INSTALL_IMAGES_CMDS
	$(INSTALL) -m 644 $(@D)/sdk-build/artifacts/uImage $(BINARIES_DIR)/uImage
	$(INSTALL) -m 644 $(@D)/sdk-build/artifacts/kernel.config $(BINARIES_DIR)/kernel.config
	$(INSTALL) -m 644 $(@D)/sdk-build/artifacts/verification.json $(BINARIES_DIR)/kernel-verification.json
endef

$(eval $(generic-package))
