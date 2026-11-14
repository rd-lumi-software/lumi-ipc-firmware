#!/usr/bin/env python3
"""Drop MIPS debugger-only procedure records, preserving all allocated sections."""
import argparse
from pathlib import Path
import struct
import subprocess


def sections(path):
    data = path.read_bytes()
    if data[:6] != b'\x7fELF\x01\x01':
        return {}
    offset = struct.unpack_from('<I', data, 32)[0]
    size, count, names_index = struct.unpack_from('<HHH', data, 46)
    table = [struct.unpack_from('<10I', data, offset + i * size) for i in range(count)]
    names = data[table[names_index][4]:table[names_index][4] + table[names_index][5]]
    return {names[row[0]:].split(b'\0')[0]:
            (row[1:4], row[5], data[row[4]:row[4] + row[5]] if row[1] != 8 else b'')
            for row in table}


def allocated(items):
    return {name: row for name, row in items.items() if row[0][1] & 2}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('lumi', type=Path)
    parser.add_argument('--objcopy', required=True)
    args = parser.parse_args()
    removed = 0
    for area in ('bin', 'lib', 'sbin', 'usr/bin', 'usr/lib', 'usr/sbin'):
        for path in (args.lumi / area).rglob('*'):
            if path.is_symlink() or not path.is_file():
                continue
            before = sections(path)
            if b'.pdr' not in before:
                continue
            if before[b'.pdr'][0][1] & 2:
                raise ValueError('Refusing to strip an allocated .pdr section')
            size = path.stat().st_size
            subprocess.run([args.objcopy, '--remove-section=.pdr', str(path)], check=True)
            if allocated(before) != allocated(sections(path)):
                raise ValueError('Allocated ELF section changed: ' + str(path))
            removed += size - path.stat().st_size
    print(f'PASS: removed {removed} debug bytes; allocated ELF sections unchanged')


if __name__ == '__main__':
    main()
