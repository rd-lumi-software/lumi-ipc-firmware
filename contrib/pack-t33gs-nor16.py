#!/usr/bin/env python3
"""Pack PRJ008N T33gs uImage and SquashFS into the 16 MiB SPI-NOR layout."""

import argparse
import hashlib
import json
from pathlib import Path
import struct
import zlib

DEFAULT_LAYOUT = Path(__file__).resolve().parents[1] / 'lumi/board/t33gs-prj008/layout.json'


def load_layout(path=DEFAULT_LAYOUT):
    layout = json.loads(Path(path).read_text())
    cursor = 0
    names = []
    for entry in layout['partitions']:
        if (entry['offset'] != cursor or entry['bytes'] <= 0
                or entry['bytes'] % layout['erase_bytes']):
            raise ValueError('Non-contiguous or unaligned flash partition: ' + entry['name'])
        cursor += entry['bytes']
        names.append(entry['name'])
    if names != ['boot', 'kernel', 'root', 'rootfs_data', 'env'] or cursor != layout['flash_bytes']:
        raise ValueError('Invalid NOR layout or flash capacity')
    memory = layout['memory']
    mib = 1024 * 1024
    if (any(type(v) is not int or v <= 0 or v % mib for v in memory.values())
            or memory['cma_bytes'] > memory['linux_bytes']):
        raise ValueError('Invalid RAM/CMA layout')
    if not 4 < layout['environment_data_bytes'] <= layout['partitions'][-1]['bytes']:
        raise ValueError('Environment does not fit its partition')
    return layout


def memory_args(layout):
    m = layout['memory']
    return (f"mem={m['linux_bytes'] // 1048576}M@0x0 "
            f"rmem={m['reserved_bytes'] // 1048576}M@{hex(m['linux_bytes'])} "
            f"cma={m['cma_bytes'] // 1048576}M")


def mtdparts(layout):
    return 'mtdparts=sfc0_nor:' + ','.join(
        f"{p['bytes'] // 1024}k({p['name']})" for p in layout['partitions'])


LAYOUT = load_layout()
FLASH_SIZE = LAYOUT['flash_bytes']
UBOOT, KERNEL, ROOTFS = [(p['offset'], p['bytes']) for p in LAYOUT['partitions'][:3]]
ENV_OFFSET = LAYOUT['partitions'][-1]['offset']
ENV_BLOCK_SIZE = LAYOUT['partitions'][-1]['bytes']
ENV_DATA_SIZE = LAYOUT['environment_data_bytes']


def check_uimage(data: bytes) -> None:
	if len(data) < 64:
		raise ValueError("truncated uImage")
	magic, hcrc, _, size, _, _, dcrc = struct.unpack_from(">7I", data)
	if magic != 0x27051956 or size != len(data) - 64:
		raise ValueError("invalid uImage magic or payload size")
	header = data[:4] + bytes(4) + data[8:64]
	if zlib.crc32(header) != hcrc or zlib.crc32(data[64:]) != dcrc:
		raise ValueError("uImage CRC mismatch")
	if data[28] != 5 or data[29:32] != bytes((5, 2, 3)):
		raise ValueError("expected a MIPS Linux kernel uImage with LZMA compression")


def make_environment(memory_args: str) -> bytes:
	variables = {
		"baudrate": "115200",
		"bootcmd": (f"sf0 probe;sf0 read {LAYOUT['kernel_load_address']} {hex(KERNEL[0])} "
                        f"{hex(KERNEL[1])};bootm {LAYOUT['kernel_load_address']}"),
		"bootdelay": "1",
		"bootargs": (
			f"console=ttyS1,115200n8 {memory_args} init=/init "
			"rootfstype=squashfs root=/dev/mtdblock2 rw "
			f"{mtdparts(LAYOUT)}"
		),
		"stdin": "serial",
		"stdout": "serial",
		"stderr": "serial",
		"wlandev": LAYOUT["wifi_device"],
	}
	data = b"\0".join(f"{key}={value}".encode() for key, value in variables.items()) + b"\0\0"
	payload = data.ljust(ENV_DATA_SIZE - 4, b"\0")
	return struct.pack("<I", zlib.crc32(payload) & 0xFFFFFFFF) + payload


def pack(uboot: bytes, kernel: bytes, rootfs: bytes, memory_args: str) -> bytes:
	for name, data, (_, capacity) in (
		("SPL+U-Boot", uboot, UBOOT),
		("kernel", kernel, KERNEL),
		("rootfs", rootfs, ROOTFS),
	):
		if not data or len(data) > capacity:
			raise ValueError(f"{name} is empty or exceeds its {capacity}-byte partition")
	check_uimage(kernel)
	if len(rootfs) < 96 or rootfs[:4] != b"hsqs":
		raise ValueError("rootfs is not little-endian SquashFS")
	used = struct.unpack_from("<Q", rootfs, 40)[0]
	if struct.unpack_from("<HH", rootfs, 28) != (4, 0) or not 96 <= used <= len(rootfs):
		raise ValueError("invalid SquashFS version or bytes_used")
	if len(make_environment(memory_args)) != ENV_DATA_SIZE:
		raise ValueError("invalid U-Boot environment size")

	image = bytearray(b"\xff" * FLASH_SIZE)
	image[UBOOT[0]:UBOOT[0] + len(uboot)] = uboot
	image[KERNEL[0]:KERNEL[0] + len(kernel)] = kernel
	image[ROOTFS[0]:ROOTFS[0] + len(rootfs)] = rootfs
	env = make_environment(memory_args)
	image[ENV_OFFSET:ENV_OFFSET + len(env)] = env
	return bytes(image)


def main() -> None:
	parser = argparse.ArgumentParser(description=__doc__)
	parser.add_argument("--uboot", type=Path, required=True)
	parser.add_argument("--kernel", type=Path, required=True)
	parser.add_argument("--rootfs", type=Path, required=True)
	parser.add_argument("--memory-args", default=memory_args(LAYOUT))
	parser.add_argument("--output", type=Path, required=True)
	args = parser.parse_args()
	try:
		image = pack(args.uboot.read_bytes(), args.kernel.read_bytes(), args.rootfs.read_bytes(), args.memory_args)
		# Exclusive creation protects previous builds and camera dumps.
		with args.output.open("xb") as output:
			output.write(image)
		if args.output.stat().st_size != FLASH_SIZE or args.output.read_bytes() != image:
			raise ValueError("output read-back differs")
	except (OSError, ValueError) as error:
		parser.exit(1, f"error: {error}\n")
	print(f"{hashlib.sha256(image).hexdigest()}  {args.output.name}")


if __name__ == "__main__":
	main()
