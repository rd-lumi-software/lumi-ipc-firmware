#!/usr/bin/env python3
"""Bind the qualified T33GS crypto profile to the exact installed gateway ELF."""
import argparse
import hashlib
import json
from pathlib import Path
import re

BACKEND = 't33gs-dma-aes-aes128-gcm-direct-mxu2-ghash'
FEATURES = {'t33gs-dma-aes', 't33gs-dma-gcm-batch', 't33gs-dma-gcm-mxu2'}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate(profile, binary):
    if profile.get('srtp_backend') != BACKEND or not FEATURES <= set(profile.get('features', [])):
        raise ValueError('T33GS requires DMA packet batching and direct MXU2 GHASH')
    if profile.get('sha256') != digest(binary):
        raise ValueError('gateway profile does not match installed ELF')


def create(runtime, destination):
    lines = (runtime / 'bin/ipc-stream-services.build-info').read_text().splitlines()
    def field(key):
        values = [line[len(key) + 1:] for line in lines if line.startswith(key + '=')]
        if len(values) != 1:
            raise ValueError('missing or duplicate gateway build field: ' + key)
        return values[0]
    hashes = []
    for line in lines:
        match = re.fullmatch(r'([0-9a-f]{64})  (.+)', line)
        if match and Path(match[2]).name == 'ipc-stream-services.t33gs':
            hashes.append(match[1])
    if len(hashes) != 1:
        raise ValueError('missing or duplicate gateway ELF digest in build receipt')
    crypto = field('webrtc_backend')
    if crypto != 'str0m; srtp=' + BACKEND:
        raise ValueError('T33GS requires DMA packet batching and direct MXU2 GHASH')
    profile = {'version': 1, 'srtp_backend': BACKEND,
               'features': field('features').split(','), 'sha256': hashes[0]}
    validate(profile, runtime / 'bin/ipc-stream-services')
    destination.write_text(json.dumps(profile, indent=2) + '\n')
    destination.chmod(0o644)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('create', 'verify'))
    parser.add_argument('root', type=Path)
    parser.add_argument('destination', type=Path, nargs='?')
    args = parser.parse_args()
    if args.action == 'create':
        if args.destination is None:
            parser.error('create requires destination')
        create(args.root, args.destination)
    else:
        validate(json.loads((args.root / 'gateway-profile.json').read_text()),
                 args.root / 'bin/ipc-stream-services')
    print('T33GS gateway profile verified: DMA batch + direct MXU2 GHASH')


if __name__ == '__main__':
    main()
