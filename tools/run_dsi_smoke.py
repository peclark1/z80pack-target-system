#!/usr/bin/env python3
"""Boot the synthetic DSI disk and verify bootstrap plus one DMA sector read."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import sys

SUCCESS_TEXT = "DSI FDC1 OK"
BOOT_TRACE = "BOOTSTRAP T0/S1 -> 0000-007F"
READ_TRACE = "READ track=0 sector=2 dma=0100"


def run(targetsim: Path, config: Path, disk: Path) -> str:
    env = os.environ.copy()
    env["TARGET_DSI0"] = str(disk.resolve())
    env["TARGET_DSI_TRACE"] = "1"
    env["TARGET_DSI_WRITE"] = "0"
    env["TARGET_DSI_BOOTSTRAP"] = "1"
    env.pop("TARGET_DSI1", None)
    env.pop("TARGET_CF0", None)
    env.pop("TARGET_CF1", None)

    read_fd, write_fd = os.pipe()
    read_file = os.fdopen(read_fd, "rb", buffering=0)

    try:
        proc = subprocess.Popen(
            [
                str(targetsim.resolve()),
                "-z",
                "-c",
                str(config.resolve()),
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
            raise RuntimeError("DSI FDC-1 smoke test timed out\n" + text)
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
    parser.add_argument("--disk", required=True, type=Path)
    args = parser.parse_args()

    try:
        output = run(args.targetsim, args.config, args.disk)
    except RuntimeError as exc:
        print(exc, file=sys.stderr)
        raise SystemExit(1)

    print(output, end="")

    missing = []
    if BOOT_TRACE not in output:
        missing.append(f"bootstrap trace {BOOT_TRACE!r}")
    if READ_TRACE not in output:
        missing.append(f"read trace {READ_TRACE!r}")
    if SUCCESS_TEXT not in output:
        missing.append(f"console output {SUCCESS_TEXT!r}")

    if missing:
        print("DSI smoke test failed; missing " + ", ".join(missing), file=sys.stderr)
        raise SystemExit(1)

    print("DSI smoke test passed: FDC-1 bootstrap and DMA sector read completed")


if __name__ == "__main__":
    main()
