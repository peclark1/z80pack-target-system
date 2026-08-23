#!/usr/bin/env python3
"""Exercise the FDC+ Type 8 FD3712 command/FIFO protocol in targetsim."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import sys

SUCCESS_TEXT = "FDCPLUS8 OK"
READ_TRACE = "target-fdcplus8: drive=0 READ track=0 sector=1"


def run(targetsim: Path, config: Path, romdir: Path, disk: Path) -> str:
    env = os.environ.copy()
    env["TARGET_FDCPLUS0"] = str(disk.resolve())
    env["TARGET_FDCPLUS_TRACE"] = "1"
    env["TARGET_FDCPLUS_WRITE"] = "0"
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
    if SUCCESS_TEXT not in output:
        missing.append(f"console output {SUCCESS_TEXT!r}")

    if missing:
        print(
            "FDC+ Type 8 smoke test failed; missing " + ", ".join(missing),
            file=sys.stderr,
        )
        raise SystemExit(1)

    print("FDC+ Type 8 smoke test passed: FD3712 read/FIFO protocol completed")


if __name__ == "__main__":
    main()
