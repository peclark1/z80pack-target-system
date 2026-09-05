#!/usr/bin/env python3
"""Exercise the real GTK4/VTE GUI under Xvfb for CI."""

from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "gui"))

import app as target_gui  # noqa: E402
from image_library_dialogs import MetadataDialog  # noqa: E402
from image_library_window import LibraryWindow  # noqa: E402
from rom_image import ROM_SIZE  # noqa: E402


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
    command = window.command.get_text()

    if "make -C" not in command or "CPU_MHZ=" not in command or "FP_PORT=" not in command:
        raise RuntimeError(f"unexpected GUI command preview: {command}")
    if "FP_FILE=" not in command:
        raise RuntimeError(f"GUI command does not enable live front-panel input: {command}")
    if "ROM_IMAGE=" not in command:
        raise RuntimeError(f"GUI command does not expose ROM selection: {command}")

    if window.terminal is None:
        raise RuntimeError("VTE terminal was not created")

    # The selector must not merely exist as a Python object: it must actually
    # be parented into the visible settings column. This catches GTK runtime
    # differences where a ScrolledWindow inserts an internal viewport layer.
    if window.rom_row.get_parent() is not window.settings_box:
        raise RuntimeError("4K ROM selector is not attached to the visible settings panel")
    if not window.rom_row.get_visible():
        raise RuntimeError("4K ROM selector is attached but hidden")

    # The graphical ROM row must accept a valid 4K binary, reflect it in the
    # Makefile command, and return cleanly to the current pinned ROM.
    with tempfile.TemporaryDirectory() as directory:
        rom = Path(directory) / "alternate.bin"
        rom.write_bytes(bytes([0xA5]) * ROM_SIZE)
        window.rom_row.set_path(str(rom))
        config = window._current_config()
        if config.rom_image != str(rom):
            raise RuntimeError("ROM selector did not update launch configuration")
        if f"ROM_IMAGE={rom}" not in window.command.get_text():
            raise RuntimeError("ROM selector did not update command preview")
        if "4K binary ROM @ F000H" not in window.rom_row.info.get_text():
            raise RuntimeError(f"ROM selector did not validate image: {window.rom_row.info.get_text()}")
        window.rom_row._use_current(None)
        if window._current_config().rom_image:
            raise RuntimeError("Use Current did not clear alternate ROM selection")

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

    # Construct the managed image-library UI using the real GTK runtime. This
    # verifies the wrapper installed ManagedImageRow for ordinary CF selectors,
    # and catches GTK property/API issues in the new browser and metadata dialog.
    if window.cf0.__class__.__name__ != "ManagedImageRow":
        raise RuntimeError(f"CF0 is not using ManagedImageRow: {type(window.cf0)!r}")
    library_window = LibraryWindow(window.cf0)
    if library_window.media_type != "cf":
        raise RuntimeError("CF image library opened with the wrong media type")
    if "read-only" not in (library_window.use_master.get_label() or ""):
        raise RuntimeError("image library does not identify masters as read-only")
    metadata = MetadataDialog(
        window,
        filename="smoke.img",
        media_type="cf",
        profile="target / IDE/CF",
        description="GUI smoke-test image",
    )
    if metadata.profile.get_text() != "target / IDE/CF":
        raise RuntimeError("image metadata dialog did not preserve the profile")
    metadata.destroy()
    library_window.destroy()

    # Exercise the exact Vte.Terminal.spawn_async() call used by Start/Build.
    window._spawn(
        ["/bin/sh", "-c", "printf 'VTE SPAWN OK\\n'"],
        "VTE spawn smoke test…",
        False,
    )
    drain_main_context_until(lambda: not window.running)
    if window.status.get_text() != "Build complete":
        raise RuntimeError(f"VTE child did not complete cleanly: {window.status.get_text()}")

    # Exercise the exact GUI Stop path too. Ubuntu 24.04's VTE binding expects
    # feed_child() data as bytes/list[int]; the application sends Ctrl-] as a
    # string and the compatibility shim must normalize it. The child puts its
    # PTY in raw mode and exits only after receiving exactly ASCII 1Dh.
    window._spawn(
        [
            sys.executable,
            "-c",
            "import os, tty; tty.setraw(0); b=os.read(0,1); raise SystemExit(0 if b == b'\\x1d' else 3)",
        ],
        "VTE stop smoke test…",
        True,
    )
    drain_main_context_until(lambda: window.status.get_text() == "Running")
    window._stop(None)
    drain_main_context_until(lambda: not window.running)
    if window.status.get_text() != "Stopped":
        raise RuntimeError(f"GUI Stop did not deliver Ctrl-] cleanly: {window.status.get_text()}")

    window.destroy()
    application.quit()
    print(
        "GTK GUI smoke test passed: ROM selector, switches, image library, "
        "FileDialog, VTE spawn, and Stop all work"
    )


if __name__ == "__main__":
    main()
