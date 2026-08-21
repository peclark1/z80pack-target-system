#!/usr/bin/env python3
"""Instantiate the real GTK4/VTE GUI under Xvfb for CI."""

from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "gui"))

import app as target_gui  # noqa: E402


def main() -> None:
    application = target_gui.TargetSimApplication()
    if not application.register(None):
        raise RuntimeError("failed to register GTK application")

    window = target_gui.TargetSimWindow(application)
    config = window._current_config()
    command = config.shell_command(ROOT)

    if "make -C" not in command or "CPU_MHZ=" not in command or "FP_PORT=" not in command:
        raise RuntimeError(f"unexpected GUI command preview: {command}")

    if window.terminal is None:
        raise RuntimeError("VTE terminal was not created")

    window.destroy()
    application.quit()
    print("GTK GUI smoke test passed: GTK4/VTE window and controls constructed")


if __name__ == "__main__":
    main()
