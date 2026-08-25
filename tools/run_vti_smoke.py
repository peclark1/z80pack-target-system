#!/usr/bin/env python3
"""Boot the synthetic DSI workstation image and verify VTI/head-tester I/O."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import sys
import time

SUCCESS_TEXT = "VTI HEADTEST OK"
EXPECTED_SCREEN = bytes.fromhex("d6d4c9a0")  # "VTI " with VTI character bit set


def wait_for_vti(screen: Path, proc: subprocess.Popen, timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            # The screen file is persistent after a clean emulator exit, so
            # give it one final check below before treating this as failure.
            break
        try:
            if screen.stat().st_size == 1024:
                return
        except OSError:
            pass
        time.sleep(0.01)

    try:
        if screen.stat().st_size == 1024:
            return
    except OSError:
        pass
    raise RuntimeError("timed out waiting for the 1024-byte VTI screen file")


def run(targetsim: Path, config: Path, disk: Path, screen: Path) -> str:
    screen.parent.mkdir(parents=True, exist_ok=True)
    screen.unlink(missing_ok=True)

    env = os.environ.copy()
    env["TARGET_CONSOLE"] = "sio"
    env["TARGET_DSI0"] = str(disk.resolve())
    env["TARGET_DSI_TRACE"] = "0"
    env["TARGET_DSI_WRITE"] = "0"
    env["TARGET_DSI_BOOTSTRAP"] = "1"
    env["TARGET_VTI_ENABLE"] = "1"
    env["TARGET_HEADTEST_ENABLE"] = "1"
    env["TARGET_VTI_SCREEN"] = str(screen.resolve())
    env.pop("TARGET_VTI_KBD", None)
    env.pop("TARGET_DSI1", None)
    env.pop("TARGET_CF0", None)
    env.pop("TARGET_CF1", None)
    env.pop("TARGET_FDCPLUS0", None)
    env.pop("TARGET_FDCPLUS1", None)
    env.pop("TARGET_FDCPLUS2", None)
    env.pop("TARGET_FDCPLUS3", None)

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

        wait_for_vti(screen, proc)

        try:
            output, _ = proc.communicate(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            output, _ = proc.communicate()
            text = output.decode("utf-8", errors="replace")
            raise RuntimeError("workstation smoke test timed out\n" + text)
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
    # Retained as an ignored compatibility argument for the existing CI call.
    parser.add_argument("--keyboard", type=Path)
    args = parser.parse_args()

    try:
        output = run(args.targetsim, args.config, args.disk, args.screen)
    except RuntimeError as exc:
        print(exc, file=sys.stderr)
        raise SystemExit(1)

    print(output, end="")
    if SUCCESS_TEXT not in output:
        print(f"workstation smoke test failed; missing console output {SUCCESS_TEXT!r}", file=sys.stderr)
        raise SystemExit(1)

    try:
        screen = args.screen.read_bytes()
    except OSError as exc:
        print(f"workstation smoke test failed; cannot read screen file: {exc}", file=sys.stderr)
        raise SystemExit(1)

    if len(screen) != 1024:
        print(f"workstation smoke test failed; screen file is {len(screen)} bytes, expected 1024", file=sys.stderr)
        raise SystemExit(1)
    if screen[: len(EXPECTED_SCREEN)] != EXPECTED_SCREEN:
        print(
            "workstation smoke test failed; first VTI cells are "
            f"{screen[:len(EXPECTED_SCREEN)].hex()}, expected {EXPECTED_SCREEN.hex()}",
            file=sys.stderr,
        )
        raise SystemExit(1)

    print("workstation smoke test passed: native IMSAI SIO, VTI mapping, and head-tester I/O are working")


if __name__ == "__main__":
    main()
