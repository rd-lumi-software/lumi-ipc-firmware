# Use absolute paths. Copy this file to local.mk and adjust for your machine.
T33GS_FIRMWARE_SRC := /path/to/lumi-ipc-firmware
T33GS_STREAMER_SRC := /path/to/lumi-ipc-streamer
T33GS_LINUX_SRC := /path/to/lumi-ipc-linux
T33GS_UBOOT_SRC := /path/to/lumi-u-boot-t33
T33GS_RELAY_SRC := /path/to/iot-relay-cloud
T33GS_TFLM_SRC := /path/to/ingenic-tflite-micro
T33GS_OPUS_SRC := /path/to/opus
T33GS_BUILDROOT_SRC := /path/to/buildroot
T33GS_KERNEL_SRC := /path/to/kernel-4.4.94
T33GS_DRIVERS_SRC := /path/to/drivers
T33GS_AIC_SRC := /path/to/aic8800

T33GS_UCLIBC_TOOLCHAIN := /path/to/mips-gcc540-uclibc
T33GS_MUSL_TOOLCHAIN := /path/to/mipsel-linux-muslsf-cross
T33GS_RISCV_TOOLCHAIN := /path/to/xpack-riscv-none-embed-gcc-10.2.0-1.2
T33GS_IMP_HEADERS := /path/to/media/include
T33GS_VENDOR_LIBRARIES := /path/to/vendor-uclibc-libraries
T33GS_SENSOR_TUNING := /path/to/sc4336-prj008-tuning
T33GS_WIFI_FIRMWARE := /path/to/aic8800-firmware
T33GS_RELAY_CERTIFICATE := /path/to/tunnel.cert

T33GS_BUILDER_IMAGE := lumi-t33gs-builder:local
T33GS_VOICE := 1
T33GS_JOBS := 4
