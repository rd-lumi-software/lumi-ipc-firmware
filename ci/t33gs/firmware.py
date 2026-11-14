#!/usr/bin/env python3
"""T33gs SDK validation, updater generation and full/OTA image packaging.

Make and shell own build orchestration. This tool handles firmware formats and
validation; the NOR layout implementation remains shared with post-image-t33.sh.
"""
import argparse
import gzip
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import re
import subprocess
import tarfile

HERE = Path(__file__).resolve().parent


def nor_packer():
    spec = importlib.util.spec_from_file_location(
        'nor', HERE.parents[1] / 'contrib/pack-t33gs-nor16.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as source:
        for block in iter(lambda: source.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def verify_inputs(root, expected):
    root = root.resolve(strict=True)
    manifest = root / 'SHA256SUMS'
    if not re.fullmatch('[0-9a-f]{64}', expected) or digest(manifest) != expected:
        raise ValueError('SDK SHA256SUMS differs from LUMI_T33GS_INPUTS_SHA256')
    listed = set()
    for line in manifest.read_text().splitlines():
        match = re.fullmatch(r'([0-9a-f]{64})  (.+)', line)
        if not match:
            raise ValueError('Invalid SHA256SUMS entry')
        checksum, name = match.groups()
        name = str(Path(name))
        path = root / name
        if Path(name).is_absolute() or '..' in Path(name).parts or name in listed:
            raise ValueError('Invalid or duplicate SDK path: ' + name)
        if not path.resolve(strict=True).is_relative_to(root):
            raise ValueError('SDK link escapes bundle: ' + name)
        if digest(path) != checksum:
            raise ValueError('SDK checksum mismatch: ' + name)
        listed.add(name)
    for path in root.rglob('*'):
        if path.is_symlink() and not path.resolve(strict=True).is_relative_to(root):
            raise ValueError('SDK link escapes bundle: ' + str(path))
        if path.is_file() and path != manifest and str(path.relative_to(root)) not in listed:
            raise ValueError('Unlisted SDK file: ' + str(path))
    for name in ('sdk', 'uclibc/bin/mips-linux-uclibc-gcc',
                 'musl/bin/mipsel-linux-muslsf-gcc', 'imp/include/imp/imp_isp.h',
                 'board/opt/ingenic-t33/lib/libimp.so',
                 'board/opt/ingenic-t33/lib/ld-uClibc-0.9.33.2.so',
                 'board/etc/sensor/sc4336-PRJ008-day.bin',
                 'board/etc/sensor/sc4336-PRJ008-night.bin',
                 'board/lib/firmware', 'tunnel.cert', 'PROVENANCE.md'):
        if not (root / name).exists():
            raise ValueError('Missing SDK input: ' + name)
    for archive in ('kernel-4.4.94.7z', 'drivers.7z'):
        source = root / 'sdk' / archive.removesuffix('.7z')
        if not source.is_dir() and len(list((root / 'sdk').rglob(archive))) != 1:
            raise ValueError('SDK must contain exactly one ' + archive)
    if not (root / 'aic8800.tar.gz').is_file() and not (root / 'aic8800/Makefile').is_file():
        raise ValueError('Missing AIC8800 source directory or archive')
    for compiler in ('uclibc/bin/mips-linux-uclibc-gcc', 'musl/bin/mipsel-linux-muslsf-gcc'):
        if not (root / compiler).stat().st_mode & 0o111:
            raise ValueError('Compiler is not executable: ' + compiler)
    if (root / 'riscv').exists():
        for compiler in ('riscv-none-embed-gcc', 'riscv-none-embed-g++'):
            path = root / 'riscv/bin' / compiler
            if not path.is_file() or not path.stat().st_mode & 0o111:
                raise ValueError('Missing RISC-V compiler: ' + compiler)
    # Board assets cannot inject services, executables or device identities.
    for path in (root / 'board').rglob('*'):
        if path.is_file():
            name = str(path.relative_to(root / 'board'))
            if not name.startswith(('opt/ingenic-t33/lib/', 'etc/sensor/', 'lib/firmware/')):
                raise ValueError('Unsupported board asset: ' + name)
    return {'sha256sums': expected, 'files': len(listed)}


def replace_once(text, old, new):
    if text.count(old) != 1:
        raise ValueError('Shared updater contract changed: ' + old)
    return text.replace(old, new, 1)


def adapt_updater(text):
    layout = nor_packer().LAYOUT
    expected_mtd = '\n'.join(f"{p['bytes']:08x} \"{p['name']}\"" for p in layout['partitions'])
    changes = (
        ('args="$@"', 'args="$@"\nskip_selfupdate=1'),
        ('vendor=$(ipcinfo -v)', 'vendor=ingenic'),
        ('flash_type=$(ipcinfo -F)', 'flash_type=nor'),
        ('get_device() {', 'get_device() {\n\t[ "$1" = rootfs ] && set -- root'),
        ('check_soc "$(head -1 $y/etc/hostname | cut -d- -f2)"',
         'check_soc "$(sed -n \'s/^BUILD_PLATFORM=//p\' "$y/etc/os-release" | cut -d_ -f1)"'),
        ('local ksoc=$(od -j 32 -N 32 -S 1 -A n "$x" | cut -d- -f3)',
         '''local ksoc=$(od -j 32 -N 32 -S 1 -A n "$x" | cut -d- -f3)
            # This source-built kernel uses its Linux release as the uImage
            # name. Accept only the exact PRJ008 release, never a generic alias.
            if [ "$(dd if="$x" bs=1 skip=32 count=32 2>/dev/null | tr -d '\\000')" = "Linux-4.4.94-lumi-t33gs" ]; then
                ksoc=t33
            fi'''),
        ('if [ "$vendor" != "ingenic" ] && [ "$vendor" != "rockchip" ]; then',
         'if [ "$vendor" != "rockchip" ]; then'),
        # Kernel timestamps are fixed for reproducibility; they cannot identify content.
        ('compare_versions "$kernel_version" "$(get_kernel_version "$x")" && return 0', ':'),
        ('compare_versions "$system_version" "$rootfs_version" && exit_update=1', ':'),
        ('free_resources() {', '''free_resources() {
    # This layout is also seeded by pack-t33gs-nor16.py. Reject migration here.
    layout=$(awk 'NR > 1 {print $2, $4}' /proc/mtd)
    expected='@EXPECTED_MTD@'
    [ "$layout" = "$expected" ] || die "Wrong T33gs NOR layout; full-image migration required"
    /etc/init.d/S61lumi-streamer-watch stop
    /etc/init.d/S60lumi-streamer stop
'''),
        ('\tramfs_discard\nfi\nflash_and_reboot',
         '\tramfs_discard\n\tdie "Cannot enter RAM; refusing live-rootfs flashing"\nfi\nflash_and_reboot'),
    )
    for old, new in changes:
        text = replace_once(text, old, new.replace('@EXPECTED_MTD@', expected_mtd))
    return text


def package(uboot, kernel, rootfs, sources, inputs_sha256, output):
    nor = nor_packer()
    if not re.fullmatch('[0-9a-f]{64}', inputs_sha256):
        raise ValueError('Input bundle SHA256 required')
    # Validate CRCs, ABI, filesystem metadata and capacities before publishing.
    image = nor.pack(uboot, kernel, rootfs, nor.memory_args(nor.LAYOUT))
    if kernel[32:64].rstrip(b'\0') != ('Linux-' + nor.LAYOUT['kernelrelease']).encode():
        raise ValueError('uImage name does not match the kernel release required by OTA')
    output.mkdir(parents=True, exist_ok=False)
    files = {'uImage.t33': kernel, 'rootfs.squashfs.t33': rootfs}
    for name, data in list(files.items()):
        files[name + '.md5sum'] = (hashlib.md5(data).hexdigest() + '  ' + name + '\n').encode()
    archive = io.BytesIO()
    with gzip.GzipFile(fileobj=archive, mode='wb', filename='', mtime=0) as zipped:
        with tarfile.open(fileobj=zipped, mode='w') as tar:
            for name, data in files.items():
                member = tarfile.TarInfo(name)
                member.size = len(data)
                member.mode = 0o644
                tar.addfile(member, io.BytesIO(data))
    files.update({'lumi-t33gs-full.bin': image,
                  'lumi-t33gs-ota.tgz': archive.getvalue()})
    metadata = {
        'board': 't33gs-prj008', 'soc': 't33', 'kernelrelease': '4.4.94-lumi-t33gs',
        'status': 'BUILD_VERIFIED_HARDWARE_QUALIFICATION_PENDING',
        'sources': sources, 'inputs_sha256sums': inputs_sha256,
        'layout': {'flash_bytes': nor.FLASH_SIZE, 'kernel': nor.KERNEL, 'rootfs': nor.ROOTFS,
                   'environment_offset': nor.ENV_OFFSET, 'board_config': nor.LAYOUT},
        'ota': {'updates': ['kernel', 'rootfs'], 'preserves': ['uboot', 'environment', 'rootfs_data'],
                'requires': 'Existing T33gs 256k/2560k/12288k/1248k/32k NOR layout'},
        'files': {name: {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
                  for name, data in files.items()},
    }
    files['build-manifest.json'] = (json.dumps(metadata, indent=2) + '\n').encode()
    for name, data in files.items():
        (output / name).write_bytes(data)
    (output / 'SHA256SUMS').write_text(''.join(
        hashlib.sha256(data).hexdigest() + '  ' + name + '\n' for name, data in sorted(files.items())))



def check_board(kernel_config=None, uboot_header=None, fw_env=None, uboot_config=None):
    nor = nor_packer()
    layout = nor.LAYOUT
    if kernel_config:
        lines = Path(kernel_config).read_text().splitlines()
        for expected in ('CONFIG_CMA=y',
                         f"CONFIG_CMA_SIZE_MBYTES={layout['memory']['cma_bytes'] // 1048576}"):
            if expected not in lines:
                raise ValueError('Kernel layout mismatch: ' + expected)
    if uboot_header:
        # Validate the PRJ008N branches rather than accepting a matching string
        # from a different board's fallback boot arguments.
        text = Path(uboot_header).read_text()
        ram = re.search(r'#if defined\(CONFIG_PRJ008N\)\s*\n#define BOOTARGS_COMMON "([^"]+)"', text)
        flash = re.search(r'#ifdef CONFIG_PRJ008N\s*\n#define LUMI_NOR_PARTITIONS "([^"]+)"', text)
        if not ram or ram[1] != 'console=ttyS1,115200n8 ' + nor.memory_args(layout):
            raise ValueError('U-Boot RAM layout mismatch')
        if not flash or flash[1] != nor.mtdparts(layout):
            raise ValueError('U-Boot flash layout mismatch')
    if uboot_config:
        values = dict(line.split('=', 1) for line in Path(uboot_config).read_text().splitlines()
                      if line.startswith('CONFIG_') and '=' in line)
        if values.get('CONFIG_PRJ008N') != 'y':
            raise ValueError('U-Boot was not configured for PRJ008N')
        def number(value):
            value = value.strip('"() ')
            terms = value.split('*')
            result = 1
            for term in terms:
                result *= int(term.strip(), 0)
            return result
        for key, expected in (('CONFIG_ENV_OFFSET', layout['partitions'][-1]['offset']),
                              ('CONFIG_ENV_SIZE', layout['environment_data_bytes']),
                              ('CONFIG_ENV_SECT_SIZE', layout['erase_bytes'])):
            if number(values.get(key, '-1')) != expected:
                raise ValueError('U-Boot environment layout mismatch: ' + key)
        kernel = layout['partitions'][1]
        address = layout['kernel_load_address']
        expected_boot = f"sf0 probe;sf0 read {address} {hex(kernel['offset'])} {hex(kernel['bytes'])};bootm {address}"
        if values.get('CONFIG_BOOTCOMMAND', '').strip('"') != expected_boot:
            raise ValueError('U-Boot kernel read offsets mismatch')
    if fw_env:
        entries = [l.split() for l in Path(fw_env).read_text().splitlines()
                   if l.strip() and not l.lstrip().startswith('#')]
        env = layout['partitions'][-1]
        expected = ['/dev/mtd4', 0, layout['environment_data_bytes'], env['bytes']]
        if (len(entries) != 1 or len(entries[0]) != 4 or entries[0][0] != expected[0]
                or [int(v, 0) for v in entries[0][1:]] != expected[1:]):
            raise ValueError('fw_env.config does not match board environment layout')
    return layout


def overlay_inventory(fw=None):
    fw = Path(fw) if fw else HERE.parents[1]
    layers = ['general/overlay', 'lumi/overlay', 'lumi/board/t33gs-prj008/overlay']
    allowed = json.loads((fw / 'lumi/board/t33gs-prj008/overlay-overrides.json').read_text())
    records = {}
    for layer in layers:
        for path in sorted((fw / layer).rglob('*')):
            if not (path.is_file() or path.is_symlink()):
                continue
            name = str(path.relative_to(fw / layer))
            prior = records.get(name)
            if prior and [prior['source'], layer] != allowed.get(name):
                raise ValueError('Unreviewed overlay override: ' + name)
            records[name] = {'source': layer, 'overrides': prior['source'] if prior else None}
    return records

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    check = commands.add_parser('check-inputs', help='Verify SDK contents and checksums')
    check.add_argument('root', type=Path)
    check.add_argument('--sha256', required=True)
    updater = commands.add_parser('install-updater', help='Generate the T33gs updater')
    updater.add_argument('source', type=Path)
    updater.add_argument('destination', type=Path)
    pack = commands.add_parser('package', help='Validate and emit full NOR and OTA images')
    for name in ('uboot', 'kernel', 'rootfs', 'sources', 'output'):
        pack.add_argument('--' + name, type=Path, required=True)
    pack.add_argument('--inputs-sha256', required=True)
    board = commands.add_parser('check-board', help='Check board RAM/flash consumers')
    board.add_argument('--kernel-config', type=Path)
    board.add_argument('--uboot-header', type=Path)
    board.add_argument('--fw-env', type=Path)
    board.add_argument('--uboot-config', type=Path)
    commands.add_parser('overlay-inventory', help='Validate overrides and list overlay sources')
    hardware = commands.add_parser('hardware-env', help='Generate hardware.env from board configuration')
    hardware.add_argument('destination', type=Path)
    args = parser.parse_args()
    if args.command == 'check-board':
        print(json.dumps(check_board(args.kernel_config, args.uboot_header, args.fw_env, args.uboot_config), indent=2))
    elif args.command == 'overlay-inventory':
        print(json.dumps(overlay_inventory(), indent=2))
    elif args.command == 'hardware-env':
        args.destination.write_text(''.join(f'{k}={v}\n' for k, v in nor_packer().LAYOUT['hardware'].items()))
    elif args.command == 'check-inputs':
        print(json.dumps(verify_inputs(args.root, args.sha256), indent=2))
    elif args.command == 'install-updater':
        args.destination.write_text(adapt_updater(args.source.read_text()))
        args.destination.chmod(0o755)
        subprocess.run(['/bin/sh', '-n', str(args.destination)], check=True)
    elif args.command == 'package':
        package(args.uboot.read_bytes(), args.kernel.read_bytes(), args.rootfs.read_bytes(),
                json.loads(args.sources.read_text()), args.inputs_sha256, args.output)


if __name__ == '__main__':
    main()
