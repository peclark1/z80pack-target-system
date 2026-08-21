#!/usr/bin/env python3
"""Create a writable full-geometry work copy of a compact CP/M 3 CF image.

Archived/reference images may be truncated after their last meaningful sector to
save space.  The target BIOS, however, defines a 512-byte, 64-sector/track,
256-track IDE/CF disk.  Reads from a compact image are fine, but normal CP/M
file allocation can legitimately write beyond the compact file's EOF.

This tool preserves the source image and expands only the disposable copy to the
full logical capacity expected by the BIOS.
"""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import shutil

SECTOR_SIZE = 512
SECTORS_PER_TRACK = 64
TRACKS = 256
LOGICAL_SIZE = SECTOR_SIZE * SECTORS_PER_TRACK * TRACKS


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def make_workcopy(
    source: Path,
    destination: Path,
    *,
    sector_size: int = SECTOR_SIZE,
    logical_size: int = LOGICAL_SIZE,
) -> None:
    source = source.resolve()
    destination = destination.resolve()

    if source == destination:
        raise ValueError("source and destination must be different files")
    if not source.is_file():
        raise FileNotFoundError(source)

    size = source.stat().st_size
    if size % sector_size:
        raise ValueError(
            f"source size {size} is not a whole number of {sector_size}-byte sectors"
        )
    if size > logical_size:
        raise ValueError(
            f"source size {size} exceeds target logical capacity {logical_size}"
        )

    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)

    # Extending with truncate creates a sparse zero-filled tail on filesystems
    # that support sparse files.  CP/M considers those unallocated data sectors;
    # their pre-write contents are irrelevant.
    with destination.open("r+b") as f:
        f.truncate(logical_size)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()

    source_size = args.source.stat().st_size
    source_hash = sha256_file(args.source)
    make_workcopy(args.source, args.destination)

    print(f"source : {args.source} ({source_size} bytes)")
    print(f"         SHA256 {source_hash}")
    print(f"work   : {args.destination} ({args.destination.stat().st_size} bytes)")
    print(f"         SHA256 {sha256_file(args.destination)}")
    print(
        f"geometry: {SECTOR_SIZE}-byte sectors, {SECTORS_PER_TRACK} sectors/track, "
        f"{TRACKS} tracks ({LOGICAL_SIZE} bytes)"
    )


if __name__ == "__main__":
    main()
