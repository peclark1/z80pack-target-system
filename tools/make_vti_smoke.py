#!/usr/bin/env python3
"""Create a DSI-bootable image that exercises the restored workstation VTI."""

from __future__ import annotations

import argparse
from pathlib import Path

TRACKS = 77
SECTORS_PER_TRACK = 26
SECTOR_SIZE = 128
IMAGE_SIZE = TRACKS * SECTORS_PER_TRACK * SECTOR_SIZE

# T0/S1 is loaded to 0000H by the DSI bootstrap overlay. Surviving VID.HEX from
# the restored IMSAI proves that this workstation mapped its Polymorphic VTI at
# F800H-FBFFH. The program writes "VTI " there in VTI character mode, prints a
# success line through normal Console I/O, then halts. The workstation's VTI is
# intentionally display-only; keyboard input remains on the normal console.
BOOTSTRAP = bytes.fromhex(
    "2100f8"            # LXI H,F800
    "36d623"            # MVI M,D6 ('V'|80H) / INX H
    "36d423"            # MVI M,D4 ('T'|80H) / INX H
    "36c923"            # MVI M,C9 ('I'|80H) / INX H
    "36a023"            # MVI M,A0 (space) / INX H
    "211e00"            # LXI H,message (001EH)
    "0610"              # MVI B,16
    "7ed3012305c21400"  # loop: MOV A,M / OUT 01 / INX H / DCR B / JNZ 0014H
    "f376"              # DI / HLT
    "56544920444953504c4159204f4b0d0a"  # "VTI DISPLAY OK\r\n"
)


def build(path: Path) -> None:
    if len(BOOTSTRAP) > SECTOR_SIZE:
        raise ValueError("VTI smoke bootstrap no longer fits in DSI T0/S1")
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
