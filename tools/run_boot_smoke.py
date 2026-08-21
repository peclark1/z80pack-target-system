#!/usr/bin/env python3
"""Run targetsim non-interactively and verify real-ROM IDE boot reaches CPMLDR."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import sys

SUCCESS_TEXT = "CPMLDR TEST OK"
IDE_TRACE_TEXT = "command=20 lba=1 sectors=12"


def run(targetsim: Path, config: Path, romdir: Path, cf0: Path) -> str:
    env = os.environ.copy()
    env["TARGET_CF0"] = str(cf0.resolve())
    env.pop("TARGET_CF1", None)
    env["TARGET_IDE_TRACE"] = "1"

    # Keep an input pipe open without sending data.  This makes the monitor's
    # autoboot timeout deterministic: no keystroke cancels it, and stdin never
    # reaches EOF while the ROM polls Console I/O status.
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
            output, _ = proc.communicate(timeout=20)
        except subprocess.TimeoutExpired:
            proc.kill()
            output, _ = proc.communicate()
            text = output.decode("utf-8", errors="replace")
            raise RuntimeError("targetsim boot smoke test timed out\n" + text)
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
    parser.add_argument("--cf0", required=True, type=Path)
    args = parser.parse_args()

    try:
        output = run(args.targetsim, args.config, args.romdir, args.cf0)
    except RuntimeError as exc:
        print(exc, file=sys.stderr)
        raise SystemExit(1)

    print(output, end="")

    missing = []
    if IDE_TRACE_TEXT not in output:
        missing.append(f"IDE trace {IDE_TRACE_TEXT!r}")
    if SUCCESS_TEXT not in output:
        missing.append(f"loader output {SUCCESS_TEXT!r}")

    if missing:
        print("boot smoke test failed; missing " + ", ".join(missing), file=sys.stderr)
        raise SystemExit(1)

    print("boot smoke test passed: real monitor ROM read LBA 1..12 and ran CPMLDR")


if __name__ == "__main__":
    main()
