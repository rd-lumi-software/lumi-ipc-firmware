LUMI_T33_UBOOT_VERSION = prj008
LUMI_T33_UBOOT_SOURCE =
LUMI_T33_UBOOT_INSTALL_IMAGES = YES
LUMI_T33_UBOOT_LICENSE = GPL-2.0+

define LUMI_T33_UBOOT_BUILD_CMDS
	rsync -a --exclude=output --exclude=.git $(LUMI_WORKSPACE)/lumi-u-boot-t33/ $(@D)/source/
	$(HOST_MAKE_ENV) $(MAKE) -C $(@D)/source distclean
	$(HOST_MAKE_ENV) $(MAKE) -C $(@D)/source CROSS_COMPILE="$(T33_TOOLCHAIN_ROOT)/bin/mips-linux-uclibc-" PRJ008_n_sfcnor_config
	$(HOST_MAKE_ENV) $(MAKE) -C $(@D)/source -j$(PARALLEL_JOBS) CROSS_COMPILE="$(T33_TOOLCHAIN_ROOT)/bin/mips-linux-uclibc-" u-boot-with-spl.bin
	python3 $(BR2_EXTERNAL_LUMI_PATH)/../ci/t33gs/firmware.py check-board --uboot-header $(@D)/source/include/configs/PRJ.h --uboot-config $(@D)/source/include/autoconf.mk > $(@D)/layout.json
endef

define LUMI_T33_UBOOT_INSTALL_IMAGES_CMDS
	$(INSTALL) -m 644 $(@D)/source/u-boot-with-spl.bin $(BINARIES_DIR)/u-boot-with-spl.bin
endef

$(eval $(generic-package))
