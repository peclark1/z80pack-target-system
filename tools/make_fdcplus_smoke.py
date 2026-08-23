#!/usr/bin/env python3
"""Create a deterministic FDC+ Type 8 IBM-3740 disk and test ROM."""

from __future__ import annotations

import argparse
from pathlib import Path

TRACKS = 77
SECTORS_PER_TRACK = 26
SECTOR_SIZE = 128
IMAGE_SIZE = TRACKS * SECTORS_PER_TRACK * SECTOR_SIZE
ROM_SIZE = 4096
MESSAGE = b"FDCPLUS8 OK\r\n"

# Z80/8080-compatible ROM code entered at F000H. It uses exactly the optimized
# FDC+3712 protocol documented by Mike Douglas' F400H PROM:
#   OUT 09H supplies data, OUT 08H supplies commands, IN 08H returns status or
#   FIFO data. It resets the controller, selects drive 0/sector 1, restores to
#   track zero, reads the sector, then clocks MESSAGE out of the read FIFO to
#   Console I/O port 01H. A read/status failure prints '!' instead.
ROM_CODE = bytes.fromhex(
    "3e81d308afd308"      # RESET, then status mode
    "afd3093e15d308afd308"  # config=0 / LOAD CONFIG / status mode
    "3e01d3093e21d308afd308"  # drive 0, sector 1 / DRIVE-SECTOR
    "3e0dd308afd308"      # RESTORE / status mode
    "3e03d308afd308"      # READ / status mode
    "db08e628c248f0"      # fail if NOT READY or CRC ERROR
    "060d"                # B = 13 bytes
    "3e40d308db08d301"    # READ BUFFER / IN 08 / Console OUT
    "3e41d308"            # SHIFT BUFFER
    "05c233f0"            # loop
    "afd308f376"          # leave status mode / DI / HLT
    "3e21d301f376"        # fail: print ! / DI / HLT
)


def build(disk_path: Path, rom_path: Path) -> None:
    image = bytearray(IMAGE_SIZE)
    image[: len(MESSAGE)] = MESSAGE
    disk_path.parent.mkdir(parents=True, exist_ok=True)
    disk_path.write_bytes(image)

    rom = bytearray([0xFF]) * ROM_SIZE
    rom[: len(ROM_CODE)] = ROM_CODE
    rom_path.parent.mkdir(parents=True, exist_ok=True)
    rom_path.write_bytes(rom)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--disk", required=True, type=Path)
    parser.add_argument("--rom", required=True, type=Path)
    args = parser.parse_args()

    build(args.disk, args.rom)
    print(f"wrote {args.disk} ({IMAGE_SIZE} bytes)")
    print(f"wrote {args.rom} ({ROM_SIZE} bytes)")


if __name__ == "__main__":
    main()
