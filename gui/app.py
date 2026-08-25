#!/usr/bin/env python3
"""State-preserving entry point for the GTK4/VTE target-system GUI."""

from __future__ import annotations

from pathlib import Path
import os

import cairo
from gi.repository import Gdk

import core_app as _core
from image_info import IBM3740_SIZE
from launcher import (
    FLOPPY_DSI,
    FLOPPY_FDCPLUS,
    FLOPPY_NONE,
    PROFILE_DSI_COMPAT,
    PROFILE_DSI_VTI,
    PROFILE_TARGET,
)
from rom_image import inspect_rom
from window_state import WindowState, load_window_state, save_window_state

_BaseTargetSimWindow = _core.TargetSimWindow
_BaseImageRow = _core.ImageRow

FLOPPY_CHOICES = (
    FLOPPY_NONE,
    FLOPPY_DSI,
    FLOPPY_FDCPLUS,
)
FLOPPY_LABELS = (
    "None — IDE/CF only",
    "Digital Systems FDC-1",
    "Altair FDC+ — Type 8 / iCOM 3712",
)
FLOPPY_DSI_INDEX = FLOPPY_CHOICES.index(FLOPPY_DSI)

PROFILE_CHOICES = (
    PROFILE_TARGET,
    PROFILE_DSI_COMPAT,
    PROFILE_DSI_VTI,
)
PROFILE_LABELS = (
    "Target System — 60K RAM + 4K ROM",
    "DSI Compatibility — 64K RAM",
    "DSI + Polymorphic VTI — 63K RAM + 1K video",
)
PROFILE_DSI_VTI_INDEX = PROFILE_CHOICES.index(PROFILE_DSI_VTI)

VTI_SCREEN_PATH = _core.REPO_ROOT / "build" / "vti-screen.bin"
VTI_KEYBOARD_PATH = _core.REPO_ROOT / "build" / "vti-kbd"
VTI_COLS = 64
VTI_ROWS = 16
VTI_SIZE = VTI_COLS * VTI_ROWS


def _find_main_paned(window):
    """Return the main left/right Gtk.Paned created by core_app, if present."""
    root = window.get_child()
    child = root.get_first_child() if root is not None else None
    return child if isinstance(child, _core.Gtk.Paned) else None


def _find_settings_box(window):
    """Return the public settings container exposed by core_app.

    Older GTK builds may interpose an internal viewport beneath a
    Gtk.ScrolledWindow, so extensions should not depend on walking GTK's
    implementation-specific widget tree. core_app now exposes settings_box
    explicitly; retain the old lookup only as a compatibility fallback.
    """
    settings = getattr(window, "settings_box", None)
    if isinstance(settings, _core.Gtk.Box):
        return settings

    paned = _find_main_paned(window)
    scroll = paned.get_start_child() if paned is not None else None
    child = scroll.get_child() if isinstance(scroll, _core.Gtk.ScrolledWindow) else None
    if isinstance(child, _core.Gtk.Box):
        return child
    if child is not None:
        nested = child.get_first_child()
        if isinstance(nested, _core.Gtk.Box):
            return nested
    return None


def _box_children(box):
    children = []
    child = box.get_first_child()
    while child is not None:
        children.append(child)
        child = child.get_next_sibling()
    return children


def _set_initial_folder(dialog, remembered: str, current: str) -> None:
    """Set a chooser location, preferring the last folder browsed by the user."""
    if remembered:
        folder = Path(remembered).expanduser()
        if folder.is_dir():
            dialog.set_initial_folder(_core.Gio.File.new_for_path(str(folder.resolve())))
            return

    if current:
        candidate = Path(current).expanduser()
        if candidate.is_file():
            dialog.set_initial_file(_core.Gio.File.new_for_path(str(candidate.resolve())))
        elif candidate.parent.is_dir():
            dialog.set_initial_folder(
                _core.Gio.File.new_for_path(str(candidate.parent.resolve()))
            )


def _parent_directory(path: str) -> str:
    return str(Path(path).expanduser().resolve().parent)


class RomRow(_core.Gtk.Frame):
    """Selectable 4K ROM row; empty selection means the current pinned ROM."""

    def __init__(self, on_change, last_directory: str = ""):
        super().__init__()
        self.set_label("4K ROM @ F000H")
        self.on_change = on_change
        self.last_directory = last_directory or ""
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
        _set_initial_folder(dialog, self.last_directory, self.get_path())

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
            self.last_directory = _parent_directory(path)
            self.set_path(path)

    def _use_current(self, _button) -> None:
        self.set_path("")


class RememberingImageRow(_BaseImageRow):
    """Core disk-image row that shares the most recently browsed directory."""

    last_directory = ""

    def _browse(self, _button) -> None:
        dialog = _core.Gtk.FileDialog()
        dialog.set_title("Select disk image")
        _set_initial_folder(dialog, type(self).last_directory, self.get_path())

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
            type(self).last_directory = _parent_directory(path)
            self.set_path(path)


# The base window resolves ImageRow from core_app at runtime. Replacing that
# global here gives CF, DSI and FDC+ rows the same remembered disk directory.
_core.ImageRow = RememberingImageRow


class VtiDisplay(_core.Gtk.Frame):
    """Live 64x16 Polymorphic VTI display with semigraphics and keyboard."""

    def __init__(self):
        super().__init__()
        self.set_label("Polymorphic VTI — 8800H-8BFFH · click display to type")
        self.screen = bytes([0xA0]) * VTI_SIZE

        self.area = _core.Gtk.DrawingArea()
        self.area.set_content_width(768)
        self.area.set_content_height(300)
        self.area.set_hexpand(True)
        self.area.set_focusable(True)
        self.area.set_draw_func(self._draw)
        self.set_child(self.area)

        click = _core.Gtk.GestureClick.new()
        click.connect("pressed", self._clicked)
        self.area.add_controller(click)

        keys = _core.Gtk.EventControllerKey.new()
        keys.connect("key-pressed", self._key_pressed)
        self.area.add_controller(keys)

        self._poll_source = _core.GLib.timeout_add(50, self._poll_screen)

    def shutdown(self) -> None:
        if self._poll_source:
            _core.GLib.source_remove(self._poll_source)
            self._poll_source = 0

    def _clicked(self, *_args) -> None:
        self.area.grab_focus()

    def _poll_screen(self) -> bool:
        try:
            content = VTI_SCREEN_PATH.read_bytes()
        except OSError:
            return True
        if len(content) >= VTI_SIZE:
            current = content[:VTI_SIZE]
            if current != self.screen:
                self.screen = current
                self.area.queue_draw()
        return True

    @staticmethod
    def _ascii_for_key(keyval: int, state) -> int | None:
        special = {
            Gdk.KEY_Return: 0x0D,
            Gdk.KEY_KP_Enter: 0x0D,
            Gdk.KEY_BackSpace: 0x08,
            Gdk.KEY_Tab: 0x09,
            Gdk.KEY_Escape: 0x1B,
            Gdk.KEY_Delete: 0x7F,
        }
        if keyval in special:
            return special[keyval]

        value = Gdk.keyval_to_unicode(keyval)
        if not value or value > 0x7F:
            return None

        if state & Gdk.ModifierType.CONTROL_MASK:
            if ord("a") <= value <= ord("z"):
                value = value - ord("a") + 1
            elif ord("A") <= value <= ord("Z"):
                value = value - ord("A") + 1
        return value & 0x7F

    def _key_pressed(self, _controller, keyval, _keycode, state) -> bool:
        value = self._ascii_for_key(keyval, state)
        if value is None:
            return False
        try:
            fd = os.open(VTI_KEYBOARD_PATH, os.O_WRONLY | os.O_NONBLOCK)
            try:
                os.write(fd, bytes([value]))
            finally:
                os.close(fd)
        except OSError:
            return False
        return True

    def _draw(self, _area, cr, width: int, height: int) -> None:
        cr.set_source_rgb(0.015, 0.02, 0.015)
        cr.paint()

        cell_w = width / VTI_COLS
        cell_h = height / VTI_ROWS
        cr.set_source_rgb(0.68, 1.0, 0.68)
        cr.select_font_face("monospace", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_NORMAL)
        cr.set_font_size(cell_h * 0.72)

        for offset, value in enumerate(self.screen):
            row, col = divmod(offset, VTI_COLS)
            x = col * cell_w
            y = row * cell_h

            if value & 0x80:
                code = value & 0x7F
                if 0x20 <= code <= 0x7E:
                    cr.move_to(x + cell_w * 0.08, y + cell_h * 0.78)
                    cr.show_text(chr(code))
                continue

            # VTI semigraphics divides a character cell into 2x3 blocks.
            # Hardware uses active-low pixel bits: 0 illuminates the block.
            bits = ((5, 2), (4, 1), (3, 0))
            block_w = cell_w / 2.0
            block_h = cell_h / 3.0
            for block_row, pair in enumerate(bits):
                for block_col, bit in enumerate(pair):
                    if not (value & (1 << bit)):
                        cr.rectangle(
                            x + block_col * block_w,
                            y + block_row * block_h,
                            block_w + 0.25,
                            block_h + 0.25,
                        )
                        cr.fill()


class TargetSimWindow(_BaseTargetSimWindow):
    """Core GUI window with ROM/floppy/VTI selection and persistent state."""

    def __init__(self, *args, **kwargs):
        state = load_window_state()
        RememberingImageRow.last_directory = state.last_disk_directory
        super().__init__(*args, **kwargs)

        # Extend the core two-profile selector without duplicating its widgets.
        self.profile.set_model(_core.Gtk.StringList.new(list(PROFILE_LABELS)))
        try:
            profile_index = PROFILE_CHOICES.index(self.config.profile)
        except ValueError:
            profile_index = 0
        self.profile.set_selected(profile_index)

        settings = _find_settings_box(self)
        if not isinstance(settings, _core.Gtk.Box):
            raise RuntimeError("unable to attach extended controls to the GUI settings panel")

        self.rom_row = RomRow(self._controls_changed, state.last_rom_directory)
        self.rom_row.set_path(self.config.rom_image)

        previous = None
        child = settings.get_first_child()
        while child is not None:
            if isinstance(child, _core.Gtk.Separator):
                break
            previous = child
            child = child.get_next_sibling()
        settings.insert_child_after(self.rom_row, previous)

        # Core_app owns the historical DSI widgets. Move that entire section
        # into a revealer so the selected floppy controller is the only panel
        # visible. Leave the separator before it as the fixed section boundary.
        children = _box_children(settings)
        dsi_label = next(
            (
                widget
                for widget in children
                if isinstance(widget, _core.Gtk.Label)
                and widget.get_text() == "Digital Systems FDC-1"
            ),
            None,
        )
        if dsi_label is None:
            raise RuntimeError("unable to locate the DSI settings section")

        dsi_start = children.index(dsi_label)
        dsi_end = children.index(self.dsi_trace)
        if dsi_end < dsi_start:
            raise RuntimeError("invalid DSI settings layout")
        dsi_separator = children[dsi_start - 1] if dsi_start else None

        dsi_box = _core.Gtk.Box(orientation=_core.Gtk.Orientation.VERTICAL, spacing=12)
        for widget in children[dsi_start : dsi_end + 1]:
            settings.remove(widget)
            dsi_box.append(widget)

        self.dsi_revealer = _core.Gtk.Revealer()
        self.dsi_revealer.set_transition_type(_core.Gtk.RevealerTransitionType.SLIDE_DOWN)
        self.dsi_revealer.set_child(dsi_box)

        self.floppy_controller = _core.Gtk.DropDown.new_from_strings(list(FLOPPY_LABELS))
        configured_controller = getattr(self.config, "floppy_controller", FLOPPY_NONE)
        try:
            configured_index = FLOPPY_CHOICES.index(configured_controller)
        except ValueError:
            configured_index = 0
        self._target_floppy_selection = configured_index
        self.floppy_controller.set_selected(configured_index)
        self.floppy_controller.set_tooltip_text(
            "DSI FDC-1 and Altair FDC+ Type 8 are mutually exclusive in one emulator session."
        )
        self.floppy_controller.connect("notify::selected", self._floppy_changed)

        selector_box = _core.Gtk.Box(
            orientation=_core.Gtk.Orientation.VERTICAL,
            spacing=4,
        )
        selector_box.append(_core.Gtk.Label(label="Floppy controller", xalign=0))
        selector_box.append(self.floppy_controller)
        selector_hint = _core.Gtk.Label(
            label="Only the selected floppy controller is attached; its settings expand below.",
            xalign=0,
        )
        selector_hint.set_wrap(True)
        selector_hint.add_css_class("dim-label")
        selector_box.append(selector_hint)

        # Build the FDC+ panel as a separate revealer. The backend supports four
        # Type 8 units, but none are attached while DSI (or None) is selected.
        fdcplus_box = _core.Gtk.Box(orientation=_core.Gtk.Orientation.VERTICAL, spacing=12)
        fdcplus_box.append(self._section_label("Altair FDC+ — Type 8 / iCOM 3712"))

        self.fdcplus_rows = []
        for number in range(4):
            row = _core.ImageRow(
                f"FDC+ Drive {number}",
                self._controls_changed,
                lambda source, unit=number: self._fdcplus_work_copy(source, unit),
            )
            row.set_path(getattr(self.config, f"fdcplus{number}", ""))
            setattr(self, f"fdcplus{number}", row)
            self.fdcplus_rows.append(row)
            fdcplus_box.append(row)

        self.fdcplus_write = _core.Gtk.CheckButton(label="Allow FDC+ writes")
        self.fdcplus_write.set_active(getattr(self.config, "fdcplus_write", False))
        self.fdcplus_write.set_tooltip_text(
            "Off by default to protect disk images. Prefer Work Copy before enabling writes."
        )
        self.fdcplus_write.connect("toggled", self._controls_changed)
        fdcplus_box.append(self.fdcplus_write)

        safety = _core.Gtk.Label(
            label=(
                "FDC+ Type 8 media are attached read-only unless “Allow FDC+ writes” "
                "is enabled. Work Copy creates a disposable IBM-3740 image under build/."
            ),
            xalign=0,
        )
        safety.set_wrap(True)
        safety.add_css_class("dim-label")
        fdcplus_box.append(safety)

        self.fdcplus_trace = _core.Gtk.CheckButton(label="FDC+ command trace")
        self.fdcplus_trace.set_active(getattr(self.config, "fdcplus_trace", False))
        self.fdcplus_trace.connect("toggled", self._controls_changed)
        fdcplus_box.append(self.fdcplus_trace)

        self.fdcplus_revealer = _core.Gtk.Revealer()
        self.fdcplus_revealer.set_transition_type(
            _core.Gtk.RevealerTransitionType.SLIDE_DOWN
        )
        self.fdcplus_revealer.set_child(fdcplus_box)

        insertion_point = dsi_separator
        settings.insert_child_after(selector_box, insertion_point)
        settings.insert_child_after(self.dsi_revealer, selector_box)
        settings.insert_child_after(self.fdcplus_revealer, self.dsi_revealer)

        # The VTI display shares the right pane with the normal Console I/O
        # terminal. Historical VTI software writes directly to its 1 KB memory
        # window, so this view updates independently of serial console output.
        self.vti_display = VtiDisplay()
        self.vti_revealer = _core.Gtk.Revealer()
        self.vti_revealer.set_transition_type(_core.Gtk.RevealerTransitionType.SLIDE_DOWN)
        self.vti_revealer.set_child(self.vti_display)
        main_paned = _find_main_paned(self)
        terminal_box = main_paned.get_end_child() if main_paned is not None else None
        if isinstance(terminal_box, _core.Gtk.Box):
            terminal_box.insert_child_after(self.vti_revealer, self.command)

        # GTK recommends get/set_default_size() for persistent window sizing;
        # it retains the normal (unmaximized) dimensions as the user resizes.
        self.set_default_size(state.width, state.height)
        self._state_paned = _find_main_paned(self)
        if self._state_paned is not None:
            self._state_paned.set_position(state.paned_position)
        if state.maximized:
            self.maximize()

        self._profile_changed()
        self._update_floppy_visibility()
        self._controls_changed()

    @staticmethod
    def _fdcplus_work_copy(source: Path, number: int) -> Path:
        if source.stat().st_size != IBM3740_SIZE:
            raise ValueError(
                "FDC+ Type 8 work copies require a 256,256-byte IBM-3740 77x26x128 image"
            )
        destination = _core.next_work_path(f"fdcplus{number}-gui")
        _core.shutil.copy2(source, destination)
        return destination

    def _selected_profile(self) -> str:
        selected = int(self.profile.get_selected())
        if 0 <= selected < len(PROFILE_CHOICES):
            return PROFILE_CHOICES[selected]
        return PROFILE_TARGET

    def _effective_floppy_index(self) -> int:
        if self._selected_profile() != PROFILE_TARGET:
            return FLOPPY_DSI_INDEX
        return int(self.floppy_controller.get_selected())

    def _update_floppy_visibility(self) -> None:
        if not hasattr(self, "dsi_revealer"):
            return
        selected = self._effective_floppy_index()
        self.dsi_revealer.set_reveal_child(FLOPPY_CHOICES[selected] == FLOPPY_DSI)
        self.fdcplus_revealer.set_reveal_child(
            FLOPPY_CHOICES[selected] == FLOPPY_FDCPLUS
        )

    def _floppy_changed(self, *_args) -> None:
        if self._selected_profile() == PROFILE_TARGET:
            self._target_floppy_selection = int(self.floppy_controller.get_selected())
        self._update_floppy_visibility()
        self._controls_changed()

    def _current_config(self):
        config = super()._current_config()
        config.profile = self._selected_profile()

        if hasattr(self, "rom_row"):
            config.rom_image = self.rom_row.get_path()
        else:
            # Base __init__ calls _current_config before our ROM row exists.
            config.rom_image = getattr(self.config, "rom_image", "")

        for number in range(4):
            name = f"fdcplus{number}"
            row = getattr(self, name, None)
            setattr(
                config,
                name,
                row.get_path() if row is not None else getattr(self.config, name, ""),
            )

        if hasattr(self, "fdcplus_trace"):
            config.fdcplus_trace = self.fdcplus_trace.get_active()
            config.fdcplus_write = self.fdcplus_write.get_active()
        else:
            config.fdcplus_trace = getattr(self.config, "fdcplus_trace", False)
            config.fdcplus_write = getattr(self.config, "fdcplus_write", False)

        if hasattr(self, "_target_floppy_selection"):
            config.floppy_controller = FLOPPY_CHOICES[self._target_floppy_selection]
        else:
            config.floppy_controller = getattr(
                self.config, "floppy_controller", FLOPPY_NONE
            )
        return config

    def _profile_changed(self, *_args):
        if self.initializing:
            return

        profile = self._selected_profile()
        target_mode = profile == PROFILE_TARGET

        self.cf0.set_sensitive(target_mode)
        self.cf1.set_sensitive(target_mode)
        self.ide_trace.set_sensitive(target_mode)
        if target_mode:
            self.dsi_bootstrap.set_sensitive(True)
        else:
            self.dsi_bootstrap.set_active(True)
            self.dsi_bootstrap.set_sensitive(False)

        if hasattr(self, "rom_row"):
            self.rom_row.set_sensitive(target_mode)

        if hasattr(self, "floppy_controller"):
            self.floppy_controller.set_sensitive(target_mode)
            desired = self._target_floppy_selection if target_mode else FLOPPY_DSI_INDEX
            if self.floppy_controller.get_selected() != desired:
                self.floppy_controller.set_selected(desired)
            self._update_floppy_visibility()

        if hasattr(self, "fdcplus_rows"):
            for row in self.fdcplus_rows:
                row.set_sensitive(target_mode)
            self.fdcplus_write.set_sensitive(target_mode)
            self.fdcplus_trace.set_sensitive(target_mode)

        if hasattr(self, "vti_revealer"):
            self.vti_revealer.set_reveal_child(profile == PROFILE_DSI_VTI)

        self._controls_changed()

    def _spawn_finished(self, terminal, pid, error, user_data=None):
        result = super()._spawn_finished(terminal, pid, error, user_data)
        if error is None and pid and pid > 0 and self.session_is_emulator:
            self.terminal.grab_focus()
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
            last_rom_directory=self.rom_row.last_directory,
            last_disk_directory=RememberingImageRow.last_directory,
        ).validated()

    def _close_request(self, *args):
        try:
            save_window_state(self._capture_window_state())
        except OSError:
            pass
        if hasattr(self, "vti_display"):
            self.vti_display.shutdown()
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
