#!/usr/bin/env python3
"""GTK4/VTE front end for the IMSAI z80pack target-system emulator."""

from __future__ import annotations

from pathlib import Path
import os
import shlex
import shutil
import subprocess
import sys

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Vte", "3.91")
from gi.repository import Gio, GLib, Gtk, Vte  # noqa: E402

from front_panel import (  # noqa: E402
    console_name,
    parse_hex_byte,
    switch_states,
    value_from_states,
)
from image_info import DSI_SD_SIZE, inspect_image  # noqa: E402
from launcher import (  # noqa: E402
    PROFILE_DSI_COMPAT,
    PROFILE_TARGET,
    LaunchConfig,
    load_config,
    save_config,
)

APP_ID = "com.peclark.z80pack-target-system"
REPO_ROOT = Path(__file__).resolve().parents[1]
FRONT_PANEL_STATE = REPO_ROOT / "build" / "gui-front-panel.hex"


def next_work_path(prefix: str) -> Path:
    """Return a new build/ work-image path without overwriting prior work."""
    build = REPO_ROOT / "build"
    build.mkdir(parents=True, exist_ok=True)
    first = build / f"{prefix}-work.img"
    if not first.exists():
        return first
    number = 2
    while True:
        candidate = build / f"{prefix}-work-{number}.img"
        if not candidate.exists():
            return candidate
        number += 1


class ImageRow(Gtk.Box):
    def __init__(self, title: str, on_change, work_copy=None):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.on_change = on_change
        self.work_copy = work_copy
        self._file_dialog = None

        label = Gtk.Label(label=title, xalign=0)
        label.add_css_class("heading")
        self.append(label)

        line = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.entry = Gtk.Entry(hexpand=True)
        self.entry.set_placeholder_text("No image selected")
        self.entry.connect("changed", self._changed)
        line.append(self.entry)

        browse = Gtk.Button(label="Browse…")
        browse.connect("clicked", self._browse)
        line.append(browse)

        if work_copy is not None:
            copy_button = Gtk.Button(label="Work Copy")
            copy_button.set_tooltip_text("Create a new writable disposable copy under build/")
            copy_button.connect("clicked", self._make_work_copy)
            line.append(copy_button)

        self.append(line)

        self.info = Gtk.Label(xalign=0)
        self.info.add_css_class("dim-label")
        self.info.set_wrap(True)
        self.append(self.info)

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
            self.info.set_text("")
            return
        try:
            self.info.set_text(inspect_image(value).summary)
        except OSError:
            self.info.set_text("Image not found")

    def _browse(self, _button) -> None:
        """Open GTK4's asynchronous file dialog.

        Gtk.FileChooserNative triggered GTK file-system-model assertions and a
        segfault on a real Ubuntu 24.04 desktop. FileDialog is the GTK4-native
        replacement and avoids the legacy chooser model. Keep a reference on
        the ImageRow until the asynchronous operation finishes.
        """
        dialog = Gtk.FileDialog()
        dialog.set_title("Select disk image")

        current = self.get_path()
        if current:
            candidate = Path(current).expanduser()
            if candidate.is_file():
                dialog.set_initial_file(Gio.File.new_for_path(str(candidate.resolve())))
            elif candidate.parent.is_dir():
                dialog.set_initial_folder(Gio.File.new_for_path(str(candidate.parent.resolve())))

        self._file_dialog = dialog
        dialog.open(self.get_root(), None, self._browse_response)

    def _browse_response(self, dialog, result) -> None:
        try:
            selected = dialog.open_finish(result)
        except GLib.Error:
            # Cancel is reported as a normal GError by the async API.
            return
        finally:
            self._file_dialog = None

        path = selected.get_path() if selected else None
        if path:
            self.set_path(path)

    def _make_work_copy(self, _button) -> None:
        if self.work_copy is None:
            return
        source = self.get_path()
        if not source:
            self.info.set_text("Select a source image first")
            return
        try:
            destination = self.work_copy(Path(source).expanduser().resolve())
        except (OSError, ValueError, subprocess.CalledProcessError) as exc:
            self.info.set_text(f"Work-copy error: {exc}")
            return
        self.set_path(str(destination))
        self.info.set_text(f"New working copy: {destination}")


class TargetSimWindow(Gtk.ApplicationWindow):
    def __init__(self, app: Gtk.Application):
        super().__init__(application=app, title="IMSAI Target System")
        self.set_default_size(1280, 800)
        self.config = load_config()
        self.running = False
        self.pending_restart = False
        self.session_is_emulator = False
        self.initializing = True
        self._syncing_front_panel = False
        self.fp_switch_buttons: dict[int, Gtk.ToggleButton] = {}
        self.fp_switch_state_labels: dict[int, Gtk.Label] = {}
        self.front_panel_state_path = FRONT_PANEL_STATE

        header = Gtk.HeaderBar()
        header.set_show_title_buttons(True)
        self.set_titlebar(header)

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.set_child(root)
        paned = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        paned.set_position(450)
        paned.set_vexpand(True)
        root.append(paned)

        settings_scroll = Gtk.ScrolledWindow()
        settings_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        settings_scroll.set_min_content_width(410)
        paned.set_start_child(settings_scroll)

        settings = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        settings.set_margin_top(14)
        settings.set_margin_bottom(14)
        settings.set_margin_start(14)
        settings.set_margin_end(14)
        settings_scroll.set_child(settings)

        settings.append(self._section_label("Machine"))

        self.profile = Gtk.DropDown.new_from_strings(
            ["Target System — 60K RAM + 4K ROM", "DSI Compatibility — 64K RAM"]
        )
        self.profile.set_selected(1 if self.config.profile == PROFILE_DSI_COMPAT else 0)
        self.profile.connect("notify::selected", self._profile_changed)
        settings.append(self._labeled("Profile", self.profile))

        machine_grid = Gtk.Grid(column_spacing=8, row_spacing=8)
        self.cpu_speed = Gtk.SpinButton.new_with_range(1, 100, 1)
        self.cpu_speed.set_value(self.config.cpu_mhz)
        self.cpu_speed.connect("value-changed", self._controls_changed)
        machine_grid.attach(Gtk.Label(label="CPU MHz", xalign=0), 0, 0, 1, 1)
        machine_grid.attach(self.cpu_speed, 1, 0, 1, 1)

        self.fp_port = Gtk.Entry()
        self.fp_port.set_max_length(2)
        self.fp_port.set_width_chars(4)
        self.fp_port.set_text(self.config.fp_port)
        self.fp_port.set_tooltip_text(
            "IN FFH value. Edit the byte or click the graphical sense switches below."
        )
        self.fp_port.connect("changed", self._fp_entry_changed)
        machine_grid.attach(Gtk.Label(label="Front panel FFH", xalign=0), 0, 1, 1, 1)
        machine_grid.attach(self.fp_port, 1, 1, 1, 1)
        settings.append(machine_grid)

        settings.append(self._build_front_panel_bank())
        self._sync_front_panel_from_entry()

        settings.append(Gtk.Separator())
        settings.append(self._section_label("IDE / CF"))

        self.cf0 = ImageRow("CF0 / Drive A", self._controls_changed, self._cf_work_copy_0)
        self.cf1 = ImageRow("CF1 / Drive B", self._controls_changed, self._cf_work_copy_1)
        default_cf0 = self.config.cf0
        default_cf1 = self.config.cf1
        if not default_cf0 and (REPO_ROOT / "build" / "cf0-work.img").is_file():
            default_cf0 = str(REPO_ROOT / "build" / "cf0-work.img")
        if not default_cf1 and (REPO_ROOT / "build" / "cf1-work.img").is_file():
            default_cf1 = str(REPO_ROOT / "build" / "cf1-work.img")
        self.cf0.set_path(default_cf0)
        self.cf1.set_path(default_cf1)
        settings.append(self.cf0)
        settings.append(self.cf1)

        self.ide_trace = Gtk.CheckButton(label="IDE command trace")
        self.ide_trace.set_active(self.config.ide_trace)
        self.ide_trace.connect("toggled", self._controls_changed)
        settings.append(self.ide_trace)

        settings.append(Gtk.Separator())
        settings.append(self._section_label("Digital Systems FDC-1"))

        self.dsi0 = ImageRow("DSI Drive A", self._controls_changed, self._dsi_work_copy_0)
        self.dsi1 = ImageRow("DSI Drive B", self._controls_changed, self._dsi_work_copy_1)
        self.dsi0.set_path(self.config.dsi0)
        self.dsi1.set_path(self.config.dsi1)
        settings.append(self.dsi0)
        settings.append(self.dsi1)

        self.dsi_bootstrap = Gtk.CheckButton(label="Enable DSI bootstrap")
        self.dsi_bootstrap.set_active(self.config.dsi_bootstrap)
        self.dsi_bootstrap.connect("toggled", self._controls_changed)
        settings.append(self.dsi_bootstrap)

        self.dsi_write = Gtk.CheckButton(label="Allow DSI writes")
        self.dsi_write.set_active(self.config.dsi_write)
        self.dsi_write.set_tooltip_text(
            "Off by default to protect archival images. Prefer Work Copy before enabling writes."
        )
        self.dsi_write.connect("toggled", self._controls_changed)
        settings.append(self.dsi_write)

        safety = Gtk.Label(
            label="DSI media are protected read-only unless “Allow DSI writes” is enabled.",
            xalign=0,
        )
        safety.set_wrap(True)
        safety.add_css_class("dim-label")
        settings.append(safety)

        self.dsi_trace = Gtk.CheckButton(label="DSI command trace")
        self.dsi_trace.set_active(self.config.dsi_trace)
        self.dsi_trace.connect("toggled", self._controls_changed)
        settings.append(self.dsi_trace)

        terminal_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        terminal_box.set_margin_top(8)
        terminal_box.set_margin_bottom(8)
        terminal_box.set_margin_start(8)
        terminal_box.set_margin_end(8)
        paned.set_end_child(terminal_box)

        self.status = Gtk.Label(label="Stopped", xalign=0)
        self.status.add_css_class("heading")
        terminal_box.append(self.status)

        self.command = Gtk.Label(xalign=0)
        self.command.set_selectable(True)
        self.command.set_wrap(True)
        self.command.add_css_class("dim-label")
        terminal_box.append(self.command)

        self.terminal = Vte.Terminal()
        self.terminal.set_hexpand(True)
        self.terminal.set_vexpand(True)
        self.terminal.set_scrollback_lines(10000)
        self.terminal.set_scroll_on_keystroke(True)
        self.terminal.connect("child-exited", self._child_exited)
        terminal_box.append(self.terminal)

        buttons = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        buttons.set_margin_top(8)
        buttons.set_margin_bottom(8)
        buttons.set_margin_start(8)
        buttons.set_margin_end(8)
        root.append(buttons)

        self.build_button = Gtk.Button(label="Build / Update")
        self.build_button.connect("clicked", self._build)
        buttons.append(self.build_button)

        self.start_button = Gtk.Button(label="Start")
        self.start_button.add_css_class("suggested-action")
        self.start_button.connect("clicked", self._start)
        buttons.append(self.start_button)

        self.restart_button = Gtk.Button(label="Restart")
        self.restart_button.connect("clicked", self._restart)
        buttons.append(self.restart_button)

        self.stop_button = Gtk.Button(label="Stop")
        self.stop_button.connect("clicked", self._stop)
        buttons.append(self.stop_button)

        hint = Gtk.Label(label="Ctrl-] cleanly exits targetsim", xalign=1, hexpand=True)
        hint.add_css_class("dim-label")
        buttons.append(hint)

        self.connect("close-request", self._close_request)
        self.initializing = False
        self._profile_changed()
        self._controls_changed()
        self._set_running(False)

    @staticmethod
    def _section_label(text: str) -> Gtk.Label:
        label = Gtk.Label(label=text, xalign=0)
        label.add_css_class("title-4")
        return label

    @staticmethod
    def _labeled(text: str, widget: Gtk.Widget) -> Gtk.Box:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        box.append(Gtk.Label(label=text, xalign=0))
        box.append(widget)
        return box

    def _build_front_panel_bank(self) -> Gtk.Frame:
        frame = Gtk.Frame()
        frame.set_label("IMSAI Sense Switches — IN FFH")

        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        body.set_margin_top(8)
        body.set_margin_bottom(8)
        body.set_margin_start(8)
        body.set_margin_end(8)
        frame.set_child(body)

        hint = Gtk.Label(label="UP = 1     DOWN = 0", xalign=0)
        hint.add_css_class("dim-label")
        body.append(hint)

        bank = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        bank.set_halign(Gtk.Align.START)
        body.append(bank)

        for bit in range(7, -1, -1):
            column = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
            column.set_halign(Gtk.Align.CENTER)

            bit_label = Gtk.Label(label=str(bit))
            bit_label.add_css_class("heading")
            column.append(bit_label)

            switch = Gtk.ToggleButton(label="▼")
            switch.set_size_request(38, 54)
            switch.set_tooltip_text(f"Sense switch {bit}; click to toggle bit {bit}")
            switch.connect("toggled", self._fp_switch_toggled, bit)
            column.append(switch)

            state_label = Gtk.Label(label="0")
            state_label.add_css_class("dim-label")
            column.append(state_label)

            self.fp_switch_buttons[bit] = switch
            self.fp_switch_state_labels[bit] = state_label
            bank.append(column)

        summary = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        self.fp_value_label = Gtk.Label(label="FFH = 00", xalign=0)
        self.fp_value_label.add_css_class("heading")
        summary.append(self.fp_value_label)

        self.fp_console_label = Gtk.Label(label="Console select: Console I/O", xalign=0)
        self.fp_console_label.set_hexpand(True)
        self.fp_console_label.add_css_class("dim-label")
        summary.append(self.fp_console_label)
        body.append(summary)

        live = Gtk.Label(
            label="Switch changes are live while targetsim is running; the next IN FFH reads the new value.",
            xalign=0,
        )
        live.set_wrap(True)
        live.add_css_class("dim-label")
        body.append(live)

        return frame

    def _front_panel_value(self) -> int | None:
        try:
            return parse_hex_byte(self.fp_port.get_text())
        except (ValueError, TypeError):
            return None

    def _write_front_panel_state(self, value: int) -> None:
        try:
            self.front_panel_state_path.parent.mkdir(parents=True, exist_ok=True)
            self.front_panel_state_path.write_text(f"{value:02X}\n", encoding="ascii")
        except OSError:
            # FP_PORT remains the fallback if the live-value file is unavailable.
            pass

    def _sync_front_panel_from_entry(self) -> None:
        value = self._front_panel_value()
        if value is None:
            self.fp_value_label.set_text("FFH = --")
            self.fp_console_label.set_text("Console select: invalid FFH value")
            return

        states = switch_states(value)
        self._syncing_front_panel = True
        try:
            for bit, switch in self.fp_switch_buttons.items():
                active = states[bit]
                switch.set_active(active)
                switch.set_label("▲" if active else "▼")
                self.fp_switch_state_labels[bit].set_text("1" if active else "0")
        finally:
            self._syncing_front_panel = False

        self.fp_value_label.set_text(f"FFH = {value:02X}")
        self.fp_console_label.set_text(f"Console select: {console_name(value)}")
        self._write_front_panel_state(value)

    def _fp_entry_changed(self, *_args) -> None:
        self._sync_front_panel_from_entry()
        self._controls_changed()

    def _fp_switch_toggled(self, button: Gtk.ToggleButton, bit: int) -> None:
        if self._syncing_front_panel:
            return

        button.set_label("▲" if button.get_active() else "▼")
        self.fp_switch_state_labels[bit].set_text("1" if button.get_active() else "0")
        states = {number: switch.get_active() for number, switch in self.fp_switch_buttons.items()}
        value = value_from_states(states)
        self.fp_port.set_text(f"{value:02X}")

    def _current_config(self) -> LaunchConfig:
        return LaunchConfig(
            profile=PROFILE_DSI_COMPAT if self.profile.get_selected() == 1 else PROFILE_TARGET,
            cf0=self.cf0.get_path(),
            cf1=self.cf1.get_path(),
            dsi0=self.dsi0.get_path(),
            dsi1=self.dsi1.get_path(),
            ide_trace=self.ide_trace.get_active(),
            dsi_trace=self.dsi_trace.get_active(),
            dsi_write=self.dsi_write.get_active(),
            dsi_bootstrap=self.dsi_bootstrap.get_active(),
            fp_port=self.fp_port.get_text().strip() or "00",
            cpu_mhz=int(self.cpu_speed.get_value()),
        )

    def _session_argv(self, config: LaunchConfig) -> list[str]:
        argv = config.make_argv(REPO_ROOT)
        argv.append(f"FP_FILE={self.front_panel_state_path}")
        return argv

    def _controls_changed(self, *_args) -> None:
        if self.initializing:
            return
        config = self._current_config()
        self.command.set_text(shlex.join(self._session_argv(config)))
        try:
            save_config(config)
        except OSError:
            pass

    def _profile_changed(self, *_args) -> None:
        if self.initializing:
            return
        compat = self.profile.get_selected() == 1
        self.cf0.set_sensitive(not compat)
        self.cf1.set_sensitive(not compat)
        self.ide_trace.set_sensitive(not compat)
        if compat:
            self.dsi_bootstrap.set_active(True)
            self.dsi_bootstrap.set_sensitive(False)
        else:
            self.dsi_bootstrap.set_sensitive(True)
        self._controls_changed()

    def _set_running(self, value: bool) -> None:
        self.running = value
        self.start_button.set_sensitive(not value)
        self.build_button.set_sensitive(not value)
        self.stop_button.set_sensitive(value and self.session_is_emulator)
        self.restart_button.set_sensitive(value and self.session_is_emulator)
        if not value and self.status.get_text() == "Running":
            self.status.set_text("Stopped")

    def _spawn(self, argv: list[str], label: str, emulator: bool) -> None:
        if self.running:
            return
        self.session_is_emulator = emulator
        self.terminal.reset(True, True)
        self.status.set_text(label)
        self._set_running(True)
        envv = [f"{key}={value}" for key, value in os.environ.items()]
        self.terminal.spawn_async(
            Vte.PtyFlags.DEFAULT,
            str(REPO_ROOT),
            argv,
            envv,
            GLib.SpawnFlags.DEFAULT,
            None,
            None,
            -1,
            None,
            self._spawn_finished,
            None,
        )

    def _spawn_finished(self, _terminal, pid, error, _user_data=None) -> None:
        if error is not None:
            self.status.set_text(f"Start failed: {error.message}")
            self._set_running(False)
        elif pid and pid > 0:
            self.status.set_text("Running" if self.session_is_emulator else "Building…")

    def _child_exited(self, _terminal, status) -> None:
        was_emulator = self.session_is_emulator
        self.session_is_emulator = False
        self._set_running(False)
        if self.pending_restart and was_emulator:
            self.pending_restart = False
            GLib.idle_add(self._start_session)
        elif status == 0:
            self.status.set_text("Stopped" if was_emulator else "Build complete")
        else:
            self.status.set_text(f"Exited ({status})")

    def _start(self, _button) -> None:
        self._start_session()

    def _start_session(self) -> bool:
        config = self._current_config()
        errors = config.validate()
        if errors:
            self.status.set_text(errors[0])
            message = "Configuration error:\r\n  " + "\r\n  ".join(errors) + "\r\n"
            self.terminal.feed(message.encode("utf-8"), -1)
            return False

        value = self._front_panel_value()
        if value is not None:
            self._write_front_panel_state(value)
        self._spawn(self._session_argv(config), "Starting…", True)
        return False

    def _build(self, _button) -> None:
        self._spawn(
            ["make", "-C", str(REPO_ROOT), "build", "current-rom"],
            "Building…",
            False,
        )

    def _stop(self, _button) -> None:
        if self.running and self.session_is_emulator:
            self.terminal.feed_child("\x1d")

    def _restart(self, _button) -> None:
        if self.running and self.session_is_emulator:
            self.pending_restart = True
            self._stop(_button)
        elif not self.running:
            self._start_session()

    def _close_request(self, *_args):
        try:
            save_config(self._current_config())
        except OSError:
            pass
        if self.running and self.session_is_emulator:
            self.terminal.feed_child("\x1d")
        return False

    @staticmethod
    def _dsi_work_copy(source: Path, number: int) -> Path:
        if source.stat().st_size != DSI_SD_SIZE:
            raise ValueError("DSI work copies require a 256,256-byte FDC-1 SD image")
        destination = next_work_path(f"dsi{number}-gui")
        shutil.copy2(source, destination)
        return destination

    def _dsi_work_copy_0(self, source: Path) -> Path:
        return self._dsi_work_copy(source, 0)

    def _dsi_work_copy_1(self, source: Path) -> Path:
        return self._dsi_work_copy(source, 1)

    @staticmethod
    def _cf_work_copy(source: Path, number: int) -> Path:
        destination = next_work_path(f"cf{number}-gui")
        subprocess.run(
            [
                sys.executable,
                str(REPO_ROOT / "tools" / "make_cf_workcopy.py"),
                str(source),
                str(destination),
            ],
            check=True,
        )
        return destination

    def _cf_work_copy_0(self, source: Path) -> Path:
        return self._cf_work_copy(source, 0)

    def _cf_work_copy_1(self, source: Path) -> Path:
        return self._cf_work_copy(source, 1)


class TargetSimApplication(Gtk.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID)

    def do_activate(self) -> None:
        window = self.props.active_window
        if window is None:
            window = TargetSimWindow(self)
        window.present()


def check_runtime() -> None:
    missing = [command for command in ("make", "python3") if shutil.which(command) is None]
    if missing:
        raise SystemExit("Missing required command(s): " + ", ".join(missing))


def main() -> int:
    check_runtime()
    app = TargetSimApplication()
    return app.run(sys.argv)


if __name__ == "__main__":
    raise SystemExit(main())