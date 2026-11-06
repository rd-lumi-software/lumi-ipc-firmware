#!/usr/bin/env python3
"""Package our RV32 ELF and explicit relocations; never relocates vendor firmware."""
import argparse
import hashlib
import struct
from pathlib import Path

U32 = 0xffffffff
REGION = 0x100000
SHARED = 0xff000


def elf_image(path):
    b = Path(path).read_bytes()
    if b[:7] != b'\x7fELF\x01\x01\x01' or struct.unpack_from('<H', b, 18)[0] != 243:
        raise ValueError('requires ELF32 little-endian RISC-V')
    h = struct.unpack_from('<16sHHIIIIIHHHHHH', b)
    sh = [struct.unpack_from('<10I', b, h[6]+i*h[11]) for i in range(h[12])]
    sections = [s for s in sh if s[2] & 2 and s[1] != 8 and s[5]]
    base = min(s[3] for s in sections)
    end = max(s[3]+s[5] for s in sections)
    if end-base > SHARED or h[4] != base+0x80:
        raise ValueError('ELF layout')
    image = bytearray(end-base)
    for s in sections:
        image[s[3]-base:s[3]-base+s[5]] = b[s[4]:s[4]+s[5]]
    records = []
    for s in sh:
        if s[1] != 4 or not sh[s[7]][2] & 2:
            continue
        sy = sh[s[6]]
        for off in range(s[4], s[4]+s[5], 12):
            address, info, addend = struct.unpack_from('<IIi', b, off)
            kind = info & 255
            sym = struct.unpack_from('<IIIBBH', b, sy[4]+(info >> 8)*16)
            target = (sym[1]+addend) & U32
            internal = base <= target < base+REGION
            if kind in (1,26,27,28,35,39):
                if internal:
                    records.append((kind,address-base,target if kind not in (35,39) else 0))
            elif kind in (16,17,18,19,23,24,25,44,45):
                if not internal:
                    raise ValueError(f'external PC-relative relocation {kind} {address:x} {target:x}')
            elif kind not in (0,51):
                raise ValueError(f'unsupported relocation {kind}')
    return base, image, records


def relocate(image, records, delta):
    image = bytearray(image)
    for kind, off, value in records:
        if off < 0 or off+4 > len(image) or off % 2:
            raise ValueError('relocation offset')
        word = struct.unpack_from('<I', image, off)[0]
        target = (value+delta) & U32
        if kind == 1:
            word = target
        elif kind == 26:
            if word & 127 != 0x37: raise ValueError('HI20 opcode')
            word = (word & 0xfff) | (((target+0x800) >> 12) << 12 & U32)
        elif kind == 27:
            if word & 127 not in (0x13,0x03,0x67): raise ValueError('LO12_I opcode')
            word = (word & 0xfffff) | ((target & 0xfff) << 20)
        elif kind == 28:
            if word & 127 != 0x23: raise ValueError('LO12_S opcode')
            word = (word & ~0xfe000f80) | ((target & 0xfe0) << 20) | ((target & 31) << 7)
        elif kind == 35: word = (word+delta) & U32
        elif kind == 39: word = (word-delta) & U32
        else: raise ValueError('kind')
        struct.pack_into('<I',image,off,word)
    return image


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('elf',type=Path);p.add_argument('output',type=Path)
    p.add_argument('--compare',type=Path,action='append',default=[])
    a=p.parse_args()
    base,image,records=elf_image(a.elf)
    # Zero delta also verifies opcode assumptions against the actual linked image.
    if relocate(image,records,0) != image: raise ValueError('canonical relocation mismatch')
    for other in a.compare:
        newbase,newimage,_=elf_image(other)
        actual=relocate(image,records,newbase-base)
        if actual != newimage:
            mismatch=[hex(i) for i,(x,y) in enumerate(zip(actual,newimage)) if x!=y]
            raise ValueError(f'fresh link differs {other}: lengths {len(actual)}/{len(newimage)} first {mismatch[:12]}')
        print(f'fresh-link equality: base={newbase:#x}, {len(actual)} bytes')
    table=b''.join(struct.pack('<III',*r) for r in records)
    header=struct.pack('<8I',0x33565752,1,base,REGION,len(image),0x80,SHARED,len(records))
    a.output.write_bytes(header+hashlib.sha256(image).digest()+hashlib.sha256(table).digest()+image+table)
    print(f'{a.output}: image={len(image)} relocations={len(records)} sha256={hashlib.sha256(a.output.read_bytes()).hexdigest()}')


if __name__=='__main__': main()
