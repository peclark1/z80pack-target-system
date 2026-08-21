#!/usr/bin/env python3
"""Validate a selected 4K ROM and stage it for a targetsim session."""

from __future__ import annotations

from pathlib import Path
import argparse
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "gui"))

from rom_image import inspect_rom, stage_rom  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Stage a 4K F000H target ROM (.bin or Intel HEX) for targetsim"
    )
    parser.add_argument("source", type=Path)
    parser.add_argument("destination_dir", type=Path)
    args = parser.parse_args()

    try:
        info = inspect_rom(args.source)
        destination = stage_rom(args.source, args.destination_dir)
    except (OSError, ValueError) as exc:
        raise SystemExit(f"error: invalid ROM image: {exc}") from exc

    print(f"ROM source : {args.source.expanduser().resolve()}")
    print(f"ROM format : {info.format}")
    print(f"ROM SHA256 : {info.sha256}")
    print(f"ROM staged : {destination}")


if __name__ == "__main__":
    main()
