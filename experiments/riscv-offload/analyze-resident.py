#!/usr/bin/env python3
"""Check the exact resident VIC payload's startup relocations, without hardware IO."""
import argparse
import hashlib
import json
import struct
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("payload", type=Path)
    parser.add_argument("resident", type=Path)
    args = parser.parse_args()
    payload = args.payload.read_bytes()
    resident = args.resident.read_bytes()
    # This layout is specific to the inspected 2264-byte vendor VIC firmware.
    # Its reset code relocates words from the table at 0x890 to image end.
    if len(payload) != 0x8D8 or len(resident) != 8192:
        raise SystemExit("Unsupported payload/resident length")
    word = lambda b, off: struct.unpack_from("<I", b, off)[0]
    if word(payload, 0x80) != 0x0800006F:
        raise SystemExit("Unsupported reset-vector instruction")
    if word(payload, 0x8BC) != 0x890 or word(payload, 0x894) != len(payload):
        raise SystemExit("Unsupported relocation table")
    expected = bytearray(payload)
    base = 0x07FFE000
    for off in range(0x890, len(payload), 4):
        struct.pack_into("<I", expected, off, (word(payload, off) + base) & 0xFFFFFFFF)
    mismatches = [hex(i) for i, (a, b) in enumerate(zip(expected, resident)) if a != b]
    result = {
        "resident_bytes": len(resident),
        "payload_sha256": hashlib.sha256(payload).hexdigest(),
        "resident_sha256": hashlib.sha256(resident).hexdigest(),
        "matches_expected_relocated_payload": not mismatches,
        "mismatch_byte_offsets": mismatches,
        "relocated_word_count": (len(payload) - 0x890) // 4,
        "bss_words_0x8d8_to_0x8fc": {
            hex(i): hex(word(resident, i)) for i in range(0x8D8, 0x8FC, 4)
        },
        "limitation": "Memory contents are not an MCU-owned heartbeat or custom worker proof.",
    }
    print(json.dumps(result, indent=2))
    return int(bool(mismatches))


if __name__ == "__main__":
    raise SystemExit(main())
