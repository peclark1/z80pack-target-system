#!/usr/bin/env python3
"""Convert the logical 4K target ROM binary into Intel HEX at F000H."""

from __future__ import annotations

import argparse
from pathlib import Path

ROM_SIZE = 4096
ROM_ORIGIN = 0xF000
RECORD_SIZE = 16


def record(address: int, record_type: int, data: bytes) -> str:
    fields = [len(data), (address >> 8) & 0xFF, address & 0xFF, record_type]
    fields.extend(data)
    checksum = (-sum(fields)) & 0xFF
    return ":" + "".join(f"{value:02X}" for value in [*fields, checksum])


def convert(source: Path, destination: Path) -> None:
    image = source.read_bytes()
    if len(image) != ROM_SIZE:
        raise SystemExit(
            f"error: expected a {ROM_SIZE}-byte logical 4K ROM, got {len(image)} bytes"
        )

    lines = []
    for offset in range(0, ROM_SIZE, RECORD_SIZE):
        chunk = image[offset : offset + RECORD_SIZE]
        lines.append(record(ROM_ORIGIN + offset, 0x00, chunk))
    lines.append(record(0x0000, 0x01, b""))

    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text("\n".join(lines) + "\n", encoding="ascii")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convert IMSAI_TARGET_MONITOR_4K.bin to Intel HEX at F000H"
    )
    parser.add_argument("source", type=Path, help="4096-byte logical target ROM .bin")
    parser.add_argument("destination", type=Path, help="output Intel HEX file")
    args = parser.parse_args()
    convert(args.source, args.destination)


if __name__ == "__main__":
    main()
