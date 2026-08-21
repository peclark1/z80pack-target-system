#!/usr/bin/env python3
"""State-preserving entry point for the GTK4/VTE target-system GUI."""

from __future__ import annotations

from pathlib import Path

import core_app as _core
from rom_image import inspect_rom
from window_state import WindowState, load_window_state, save_window_state

_BaseTargetSimWindow = _core.TargetSimWindow


def _find_main_paned(window):
    """Return the main left/right Gtk.Paned created by core_app, if present."""
    root = window.get_child()
    child = root.get_first_child() if root is not None else None
    return child if isinstance(child, _core.Gtk.Paned) else None


def _find_settings_box(window):
    paned = _find_main_paned(window)
    scroll = paned.get_start_child() if paned is not None else None
    return scroll.get_child() if isinstance(scroll, _core.Gtk.ScrolledWindow) else None


class RomRow(_core.Gtk.Frame):
    """Selectable 4K ROM row; empty selection means the current pinned ROM."""

    def __init__(self, on_change):
        super().__init__()
        self.set_label("4K ROM @ F000H")
        self.on_change = on_change
        self._file_dialog = None

        body = _core.Gtk.Box(orientation=_core.Gtk.Orientation.VERTICAL, spacing=6)
        body.set_margin_top(8)
        body.set_margin_bottom(8)
        body.set_margin_start(8)
        body.set_margin_end(8)
        self.set_child(body)

        line = _core.Gtk.Box(orientation=_core.Gtk.Orientation.HORIZONTAL, spacing=6)
        self.entry = _core.Gtk.Entry(hexpand=True)
        self.entry.set_placeholder_text("Current target ROM")
        self.entry.connect("changed", self._changed)
        line.append(self.entry)

        browse = _core.Gtk.Button(label="Browse…")
        browse.set_tooltip_text("Select a 4096-byte binary ROM or Intel HEX for F000H-FFFFH")
        browse.connect("clicked", self._browse)
        line.append(browse)

        current = _core.Gtk.Button(label="Use Current")
        current.set_tooltip_text("Return to the pinned/current build/target-monitor.hex")
        current.connect("clicked", self._use_current)
        line.append(current)
        body.append(line)

        self.info = _core.Gtk.Label(xalign=0)
        self.info.set_wrap(True)
        self.info.add_css_class("dim-label")
        body.append(self.info)
        self.refresh_info()

    def get_path(self) -> str:
        return self.entry.get_text().strip()

    def set_path(self, value: str) -> None:
        self.entry.set_text(value or "")

    def _changed(self, *_args) -> None:
        self.refresh_info()
        self.on_change()

    def refresh_info(self) -> None:
        value = self.get_path()
        if not value:
            self.info.set_text("Current pinned target ROM · build/target-monitor.hex")
            return
        try:
            self.info.set_text(inspect_rom(value).summary)
        except OSError:
            self.info.set_text("ROM image not found")
        except ValueError as exc:
            self.info.set_text(f"Invalid ROM: {exc}")

    def _browse(self, _button) -> None:
        dialog = _core.Gtk.FileDialog()
        dialog.set_title("Select 4K target ROM")

        current = self.get_path()
        if current:
            candidate = Path(current).expanduser()
            if candidate.is_file():
                dialog.set_initial_file(_core.Gio.File.new_for_path(str(candidate.resolve())))
            elif candidate.parent.is_dir():
                dialog.set_initial_folder(
                    _core.Gio.File.new_for_path(str(candidate.parent.resolve()))
                )

        self._file_dialog = dialog
        dialog.open(self.get_root(), None, self._browse_response)

    def _browse_response(self, dialog, result) -> None:
        try:
            selected = dialog.open_finish(result)
        except _core.GLib.Error:
            return
        finally:
            self._file_dialog = None

        path = selected.get_path() if selected else None
        if path:
            self.set_path(path)

    def _use_current(self, _button) -> None:
        self.set_path("")


class TargetSimWindow(_BaseTargetSimWindow):
    """Core GUI window with ROM selection and persistent window state."""

    def __init__(self, *args, **kwargs):
        state = load_window_state()
        super().__init__(*args, **kwargs)

        self.rom_row = RomRow(self._controls_changed)
        self.rom_row.set_path(self.config.rom_image)
        settings = _find_settings_box(self)
        if isinstance(settings, _core.Gtk.Box):
            previous = None
            child = settings.get_first_child()
            while child is not None:
                if isinstance(child, _core.Gtk.Separator):
                    break
                previous = child
                child = child.get_next_sibling()
            settings.insert_child_after(self.rom_row, previous)

        # GTK recommends get/set_default_size() for persistent window sizing;
        # it retains the normal (unmaximized) dimensions as the user resizes.
        self.set_default_size(state.width, state.height)
        self._state_paned = _find_main_paned(self)
        if self._state_paned is not None:
            self._state_paned.set_position(state.paned_position)
        if state.maximized:
            self.maximize()

        self._profile_changed()
        self._controls_changed()

    def _current_config(self):
        config = super()._current_config()
        if hasattr(self, "rom_row"):
            config.rom_image = self.rom_row.get_path()
        else:
            # Base __init__ calls _current_config before our ROM row exists.
            config.rom_image = getattr(self.config, "rom_image", "")
        return config

    def _profile_changed(self, *args):
        result = super()._profile_changed(*args)
        if hasattr(self, "rom_row"):
            self.rom_row.set_sensitive(self.profile.get_selected() == 0)
        return result

    def _capture_window_state(self) -> WindowState:
        width, height = self.get_default_size()
        paned_position = (
            self._state_paned.get_position()
            if self._state_paned is not None
            else WindowState().paned_position
        )
        return WindowState(
            width=width,
            height=height,
            maximized=self.is_maximized(),
            paned_position=paned_position,
        ).validated()

    def _close_request(self, *args):
        try:
            save_window_state(self._capture_window_state())
        except OSError:
            pass
        return super()._close_request(*args)


# TargetSimApplication.do_activate() is defined in core_app and resolves its
# TargetSimWindow global at runtime, so replace that global with our subclass.
_core.TargetSimWindow = TargetSimWindow

# Re-export the public core module names so existing tests/importers that use
# `import app as target_gui` keep working unchanged.
for _name in dir(_core):
    if not _name.startswith("_") and _name != "TargetSimWindow":
        globals()[_name] = getattr(_core, _name)


def main() -> int:
    return _core.main()


if __name__ == "__main__":
    raise SystemExit(main())
