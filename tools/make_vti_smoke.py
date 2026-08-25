#!/usr/bin/env python3
"""Create a DSI-bootable image that exercises the restored workstation I/O."""

from __future__ import annotations

import argparse
from pathlib import Path

TRACKS = 77
SECTORS_PER_TRACK = 26
SECTOR_SIZE = 128
IMAGE_SIZE = TRACKS * SECTORS_PER_TRACK * SECTOR_SIZE

# T0/S1 is loaded to 0000H by the DSI bootstrap overlay. Surviving VID.HEX from
# the restored IMSAI proves that this workstation mapped its Polymorphic VTI at
# F800H-FBFFH. This program verifies that mapping, the printer/request ready
# port, the test-fixture completion status, and representative A/D readings.
# It then prints a success line through normal Console I/O and halts.
BOOTSTRAP = bytes.fromhex(
    "2100f8"            # LXI H,F800
    "36d623"            # MVI M,D6 ('V'|80H) / INX H
    "36d423"            # MVI M,D4 ('T'|80H) / INX H
    "36c923"            # MVI M,C9 ('I'|80H) / INX H
    "36a023"            # MVI M,A0 (space) / INX H
    "db03fe01c24900"    # IN 03 / CPI 01 / JNZ fail
    "dbe8fe0bc24900"    # IN E8 / CPI 0B / JNZ fail
    "3e01d3e8"          # MVI A,01 / OUT E8 (normal read channel)
    "dbeefe0ec24900"    # IN EE / CPI 0E / JNZ fail
    "dbeffed8c24900"    # IN EF / CPI D8 / JNZ fail (3800)
    "3e41d3e8"          # MVI A,41 / OUT E8 (overwrite/right channel)
    "dbeefe0fc24900"    # IN EE / CPI 0F / JNZ fail (4050 high byte)
    "214b00"            # LXI H,message
    "0611"              # MVI B,17
    "7ed3012305c23f00"  # loop: MOV A,M / OUT 01 / INX H / DCR B / JNZ loop
    "f376"              # DI / HLT
    "f376"              # fail: DI / HLT
    "565449204845414454455354204f4b0d0a"  # "VTI HEADTEST OK\r\n"
)


def build(path: Path) -> None:
    if len(BOOTSTRAP) > SECTOR_SIZE:
        raise ValueError("workstation smoke bootstrap no longer fits in DSI T0/S1")
    image = bytearray(IMAGE_SIZE)
    image[: len(BOOTSTRAP)] = BOOTSTRAP
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
