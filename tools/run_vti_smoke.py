#!/usr/bin/env python3
"""Boot the synthetic DSI/VTI image and verify VTI video and keyboard I/O."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import stat
import subprocess
import sys
import time

SUCCESS_TEXT = "VTI KBD OK"
EXPECTED_SCREEN = bytes.fromhex("d6d4c9a0cb")  # "VTI K" with VTI character bit set


def wait_for_vti(screen: Path, keyboard: Path, proc: subprocess.Popen, timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            raise RuntimeError("targetsim exited before the VTI keyboard became ready")
        try:
            screen_ready = screen.stat().st_size == 1024
            keyboard_ready = stat.S_ISFIFO(keyboard.stat().st_mode)
        except OSError:
            screen_ready = keyboard_ready = False
        if screen_ready and keyboard_ready:
            return
        time.sleep(0.01)
    raise RuntimeError("timed out waiting for VTI screen file and keyboard FIFO")


def run(targetsim: Path, config: Path, disk: Path, screen: Path, keyboard: Path) -> str:
    screen.parent.mkdir(parents=True, exist_ok=True)
    keyboard.parent.mkdir(parents=True, exist_ok=True)
    screen.unlink(missing_ok=True)
    keyboard.unlink(missing_ok=True)

    env = os.environ.copy()
    env["TARGET_DSI0"] = str(disk.resolve())
    env["TARGET_DSI_TRACE"] = "0"
    env["TARGET_DSI_WRITE"] = "0"
    env["TARGET_DSI_BOOTSTRAP"] = "1"
    env["TARGET_VTI_ENABLE"] = "1"
    env["TARGET_VTI_SCREEN"] = str(screen.resolve())
    env["TARGET_VTI_KBD"] = str(keyboard.resolve())
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

        wait_for_vti(screen, keyboard, proc)
        fd = os.open(keyboard, os.O_WRONLY | os.O_NONBLOCK)
        try:
            os.write(fd, b"K")
        finally:
            os.close(fd)

        try:
            output, _ = proc.communicate(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            output, _ = proc.communicate()
            text = output.decode("utf-8", errors="replace")
            raise RuntimeError("VTI smoke test timed out\n" + text)
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
    parser.add_argument("--screen", required=True, type=Path)
    parser.add_argument("--keyboard", required=True, type=Path)
    args = parser.parse_args()

    try:
        output = run(args.targetsim, args.config, args.disk, args.screen, args.keyboard)
    except RuntimeError as exc:
        print(exc, file=sys.stderr)
        raise SystemExit(1)

    print(output, end="")
    if SUCCESS_TEXT not in output:
        print(f"VTI smoke test failed; missing console output {SUCCESS_TEXT!r}", file=sys.stderr)
        raise SystemExit(1)

    try:
        screen = args.screen.read_bytes()
    except OSError as exc:
        print(f"VTI smoke test failed; cannot read screen file: {exc}", file=sys.stderr)
        raise SystemExit(1)

    if len(screen) != 1024:
        print(f"VTI smoke test failed; screen file is {len(screen)} bytes, expected 1024", file=sys.stderr)
        raise SystemExit(1)
    if screen[: len(EXPECTED_SCREEN)] != EXPECTED_SCREEN:
        print(
            "VTI smoke test failed; first cells are "
            f"{screen[:len(EXPECTED_SCREEN)].hex()}, expected {EXPECTED_SCREEN.hex()}",
            file=sys.stderr,
        )
        raise SystemExit(1)

    print("VTI smoke test passed: video RAM mapping and keyboard ports are working")


if __name__ == "__main__":
    main()
