#!/usr/bin/env python3
"""Exercise the FDC+ Type 8 FD3712 command/FIFO and format protocols."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import sys

SUCCESS_TEXT = "FDCPLUS8 OK"
READ_TRACE = "target-fdcplus8: drive=0 READ track=0 sector=1"
FORMAT_TRACE = "target-fdcplus8: drive=0 FORMAT track=2 sectors=1-26"
SECTORS_PER_TRACK = 26
SECTOR_SIZE = 128
FORMAT_TRACK = 2
FORMAT_FILL = 0xE5


def run(targetsim: Path, config: Path, romdir: Path, disk: Path) -> str:
    env = os.environ.copy()
    env["TARGET_FDCPLUS0"] = str(disk.resolve())
    env["TARGET_FDCPLUS_TRACE"] = "1"
    env["TARGET_FDCPLUS_WRITE"] = "1"
    for number in range(1, 4):
        env.pop(f"TARGET_FDCPLUS{number}", None)
    for name in (
        "TARGET_CF0",
        "TARGET_CF1",
        "TARGET_DSI0",
        "TARGET_DSI1",
        "TARGET_DSI2",
        "TARGET_DSI3",
    ):
        env.pop(name, None)

    read_fd, write_fd = os.pipe()
    read_file = os.fdopen(read_fd, "rb", buffering=0)

    try:
        proc = subprocess.Popen(
            [
                str(targetsim.resolve()),
                "-z",
                "-c",
                str(config.resolve()),
                "-r",
                str(romdir.resolve()),
            ],
            cwd=targetsim.resolve().parent,
            stdin=read_file,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            env=env,
        )
        read_file.close()
        try:
            output, _ = proc.communicate(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            output, _ = proc.communicate()
            text = output.decode("utf-8", errors="replace")
            raise RuntimeError("FDC+ Type 8 smoke test timed out\n" + text)
    finally:
        try:
            read_file.close()
        except OSError:
            pass
        os.close(write_fd)

    return output.decode("utf-8", errors="replace")


def verify_formatted_track(disk: Path) -> str | None:
    image = disk.read_bytes()
    track_size = SECTORS_PER_TRACK * SECTOR_SIZE
    start = FORMAT_TRACK * track_size
    end = start + track_size
    expected = bytes([FORMAT_FILL]) * track_size

    if image[start:end] != expected:
        return f"track {FORMAT_TRACK} was not fully filled with {FORMAT_FILL:02X}"

    # The format-mode WRITE must affect exactly the current track. The next
    # track began as zeroes in make_fdcplus_smoke.py and must remain untouched.
    next_start = end
    next_end = next_start + track_size
    if any(image[next_start:next_end]):
        return f"track {FORMAT_TRACK + 1} changed during track-format operation"

    return None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--targetsim", required=True, type=Path)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--romdir", required=True, type=Path)
    parser.add_argument("--disk", required=True, type=Path)
    args = parser.parse_args()

    try:
        output = run(args.targetsim, args.config, args.romdir, args.disk)
    except RuntimeError as exc:
        print(exc, file=sys.stderr)
        raise SystemExit(1)

    print(output, end="")

    missing = []
    if READ_TRACE not in output:
        missing.append(f"read trace {READ_TRACE!r}")
    if FORMAT_TRACE not in output:
        missing.append(f"format trace {FORMAT_TRACE!r}")
    if SUCCESS_TEXT not in output:
        missing.append(f"console output {SUCCESS_TEXT!r}")

    format_error = verify_formatted_track(args.disk)
    if format_error:
        missing.append(format_error)

    if missing:
        print(
            "FDC+ Type 8 smoke test failed; missing/invalid " + ", ".join(missing),
            file=sys.stderr,
        )
        raise SystemExit(1)

    print(
        "FDC+ Type 8 smoke test passed: FD3712 read/FIFO and FDC+3712 "
        "track-format protocols completed"
    )


if __name__ == "__main__":
    main()
