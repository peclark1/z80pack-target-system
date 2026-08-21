#!/usr/bin/env python3
"""Exercise the real GTK4/VTE GUI under Xvfb for CI."""

from __future__ import annotations

from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "gui"))

import app as target_gui  # noqa: E402


def drain_main_context_until(predicate, timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    context = target_gui.GLib.MainContext.default()
    while not predicate():
        while context.pending():
            context.iteration(False)
        if time.monotonic() >= deadline:
            raise RuntimeError("timed out waiting for GTK/VTE asynchronous operation")
        time.sleep(0.01)


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

    # Browse buttons use Gtk.FileDialog rather than the legacy
    # Gtk.FileChooserNative path that crashed on a real Ubuntu desktop.
    if not hasattr(target_gui.Gtk, "FileDialog"):
        raise RuntimeError("GTK runtime does not provide Gtk.FileDialog")
    dialog = target_gui.Gtk.FileDialog()
    dialog.set_title("Disk-image browse smoke test")
    if dialog.get_title() != "Disk-image browse smoke test":
        raise RuntimeError("Gtk.FileDialog could not be constructed/configured")

    # Exercise the exact Vte.Terminal.spawn_async() call used by Start/Build.
    # A previous smoke test only constructed the terminal, which allowed an
    # argument-order error in spawn_async() to reach a real desktop.
    window._spawn(
        ["/bin/sh", "-c", "printf 'VTE SPAWN OK\\n'"],
        "VTE spawn smoke test…",
        False,
    )
    drain_main_context_until(lambda: not window.running)
    if window.status.get_text() != "Build complete":
        raise RuntimeError(f"VTE child did not complete cleanly: {window.status.get_text()}")

    window.destroy()
    application.quit()
    print("GTK GUI smoke test passed: window, FileDialog, and VTE child spawn all work")


if __name__ == "__main__":
    main()
