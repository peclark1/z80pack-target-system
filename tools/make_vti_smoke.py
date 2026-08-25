#!/usr/bin/env python3
"""Create a DSI-bootable image that exercises Polymorphic VTI video/keyboard."""

from __future__ import annotations

import argparse
from pathlib import Path

TRACKS = 77
SECTORS_PER_TRACK = 26
SECTOR_SIZE = 128
IMAGE_SIZE = TRACKS * SECTORS_PER_TRACK * SECTOR_SIZE

# T0/S1 is loaded to 0000H by the DSI bootstrap overlay. The program writes
# "VTI " into VTI RAM at 8800H, polls the documented status port 89H until
# D0 becomes zero, reads the key from 88H, sets the VTI character-mode bit,
# stores it as the fifth display character, prints a success line through the
# normal Console I/O port, then halts.
BOOTSTRAP = bytes.fromhex(
    "210088"            # LXI H,8800
    "36d623"            # MVI M,D6 ('V'|80H) / INX H
    "36d423"            # MVI M,D4 ('T'|80H) / INX H
    "36c923"            # MVI M,C9 ('I'|80H) / INX H
    "36a023"            # MVI M,A0 (space) / INX H
    "db89e601c20f00"    # wait: IN 89 / ANI 01 / JNZ wait
    "db88f68077"        # IN 88 / ORI 80 / MOV M,A
    "212500"            # LXI H,message
    "060c"              # MVI B,12
    "7ed3012305c21e00"  # loop: MOV A,M / OUT 01 / INX H / DCR B / JNZ loop
    "f376"              # DI / HLT
    "565449204b4244204f4b0d0a"  # "VTI KBD OK\r\n"
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
