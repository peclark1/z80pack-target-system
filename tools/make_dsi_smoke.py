#!/usr/bin/env python3
"""Create a minimal IBM-3740-size DSI FDC-1 regression disk."""

from __future__ import annotations

import argparse
from pathlib import Path

TRACKS = 77
SECTORS_PER_TRACK = 26
SECTOR_SIZE = 128
IMAGE_SIZE = TRACKS * SECTORS_PER_TRACK * SECTOR_SIZE

# 8080/Z80-compatible T0/S1 bootstrap. It selects drive 0, prepares a normal
# FDC-1 131-byte DMA request at 0100H for T0/S2, loads DMA high/low through
# 7EH/7DH, issues READ=40H at 7FH, waits for IO FINISH bit 3, then prints the
# 13-byte sector-2 payload through Console I/O data port 01H and halts.
BOOTSTRAP = bytes.fromhex(
    "3e08d37f"          # MVI A,08 / OUT 7F   select drive 0
    "210001"            # LXI H,0100
    "360023"            # MVI M,00 / INX H   track 0
    "360223"            # MVI M,02 / INX H   sector 2
    "36fb"              # MVI M,FB            SD data mark
    "3e01d37e"          # MVI A,01 / OUT 7E   DMA high
    "afd37d"            # XRA A / OUT 7D      DMA low
    "3e40d37f"          # MVI A,40 / OUT 7F   read
    "db7fe608ca1a00"    # wait: IN 7F / ANI 08 / JZ wait
    "210301"            # LXI H,0103          returned sector data
    "060d"              # MVI B,13
    "7ed3012305c22600"  # loop: MOV A,M / OUT 01 / INX H / DCR B / JNZ loop
    "f376"              # DI / HLT
)

MESSAGE = b"DSI FDC1 OK\r\n"


def build(path: Path) -> None:
    image = bytearray(IMAGE_SIZE)
    image[: len(BOOTSTRAP)] = BOOTSTRAP
    image[SECTOR_SIZE : SECTOR_SIZE + len(MESSAGE)] = MESSAGE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(image)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    build(args.output)
    print(f"wrote {args.output} ({IMAGE_SIZE} bytes)")


if __name__ == "__main__":
    main()
