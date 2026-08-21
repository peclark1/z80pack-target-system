#!/usr/bin/env python3
"""Create a tiny CF image that proves the target monitor's IDE boot path."""

from __future__ import annotations

import argparse
from pathlib import Path

SECTOR_SIZE = 512
IMAGE_SECTORS = 64
LOADER_LBA = 1

# Loaded by the real monitor at 0100H.  It begins with LD SP,nn (31H), which
# is the monitor's CPMLDR signature check, then prints through the monitor's
# fixed CONOUT ABI entry at F006H and HALTs.
LOADER = bytes(
    [
        0x31,
        0xC0,
        0xEF,  # LD SP,EFC0H
        0x21,
        0x11,
        0x01,  # LD HL,0111H (message)
        0x7E,  # loop: LD A,(HL)
        0xB7,  # OR A
        0x28,
        0x06,  # JR Z,done
        0xCD,
        0x06,
        0xF0,  # CALL F006H (monitor CONOUT)
        0x23,  # INC HL
        0x18,
        0xF6,  # JR loop
        0x76,  # done: HALT
    ]
) + b"CPMLDR TEST OK\r\n\x00"


def build_image(destination: Path) -> None:
    image = bytearray(IMAGE_SECTORS * SECTOR_SIZE)
    offset = LOADER_LBA * SECTOR_SIZE
    image[offset : offset + len(LOADER)] = LOADER
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(image)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    build_image(args.destination)


if __name__ == "__main__":
    main()
