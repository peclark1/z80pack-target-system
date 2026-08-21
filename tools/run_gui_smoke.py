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
    command = window.command.get_text()

    if "make -C" not in command or "CPU_MHZ=" not in command or "FP_PORT=" not in command:
        raise RuntimeError(f"unexpected GUI command preview: {command}")
    if "FP_FILE=" not in command:
        raise RuntimeError(f"GUI command does not enable live front-panel input: {command}")

    if window.terminal is None:
        raise RuntimeError("VTE terminal was not created")

    # The graphical IMSAI sense-switch bank must represent all eight FFH bits,
    # remain synchronized with the hexadecimal field, and update the live-value
    # file used by targetsim while a session is running.
    if set(window.fp_switch_buttons) != set(range(8)):
        raise RuntimeError("front-panel switch bank does not contain bits 7 through 0")
    window.fp_port.set_text("A5")
    if not window.fp_switch_buttons[7].get_active():
        raise RuntimeError("bit 7 did not follow FFH=A5")
    if not window.fp_switch_buttons[0].get_active():
        raise RuntimeError("bit 0 did not follow FFH=A5")
    window.fp_switch_buttons[0].set_active(False)
    if window.fp_port.get_text() != "A4":
        raise RuntimeError(f"switch toggle did not update FFH field: {window.fp_port.get_text()}")
    if window.fp_console_label.get_text() != "Console select: Console I/O":
        raise RuntimeError(f"unexpected console decode: {window.fp_console_label.get_text()}")
    if window.front_panel_state_path.read_text(encoding="ascii").strip() != "A4":
        raise RuntimeError("graphical switch change did not update live FFH state file")

    # Browse buttons use Gtk.FileDialog rather than the legacy
    # Gtk.FileChooserNative path that crashed on a real Ubuntu desktop.
    if not hasattr(target_gui.Gtk, "FileDialog"):
        raise RuntimeError("GTK runtime does not provide Gtk.FileDialog")
    dialog = target_gui.Gtk.FileDialog()
    dialog.set_title("Disk-image browse smoke test")
    if dialog.get_title() != "Disk-image browse smoke test":
        raise RuntimeError("Gtk.FileDialog could not be constructed/configured")

    # Exercise the exact Vte.Terminal.spawn_async() call used by Start/Build.
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
    print("GTK GUI smoke test passed: switches, FileDialog, and VTE child spawn all work")


if __name__ == "__main__":
    main()
