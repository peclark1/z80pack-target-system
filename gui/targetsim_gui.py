#!/usr/bin/env python3
"""GTK4/VTE front end for the IMSAI z80pack target-system emulator."""

from __future__ import annotations

from pathlib import Path
import os
import shutil
import subprocess
import sys

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Vte", "3.91")
from gi.repository import GLib, Gtk, Vte  # noqa: E402

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


class ImageRow(Gtk.Box):
    def __init__(self, title: str, on_change, work_copy=None):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.on_change = on_change
        self.work_copy = work_copy

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
            copy_button.set_tooltip_text("Create a writable disposable copy in build/")
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
        chooser = Gtk.FileChooserNative.new(
            "Select disk image",
            self.get_root(),
            Gtk.FileChooserAction.OPEN,
            "Select",
            "Cancel",
        )
        chooser.connect("response", self._browse_response)
        chooser.show()

    def _browse_response(self, chooser, response) -> None:
        if response == Gtk.ResponseType.ACCEPT:
            selected = chooser.get_file()
            path = selected.get_path() if selected else None
            if path:
                self.set_path(path)
        chooser.destroy()

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
        self.info.set_text(f"Working copy: {destination}")


class TargetSimWindow(Gtk.ApplicationWindow):
    def __init__(self, app: Gtk.Application):
        super().__init__(application=app, title="IMSAI Target System")
        self.set_default_size(1180, 760)
        self.config = load_config()
        self.running = False
        self.pending_restart = False

        header = Gtk.HeaderBar()
        header.set_show_title_buttons(True)
        self.set_titlebar(header)

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.set_child(root)

        paned = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        paned.set_position(390)
        paned.set_vexpand(True)
        root.append(paned)

        settings_scroll = Gtk.ScrolledWindow()
        settings_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        settings_scroll.set_min_content_width(340)
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
            "IN FFH value. Low bits: 00 Console I/O, 01 Serial I/O A, 02 MIO."
        )
        self.fp_port.connect("changed", self._controls_changed)
        machine_grid.attach(Gtk.Label(label="Front panel FFH", xalign=0), 0, 1, 1, 1)
        machine_grid.attach(self.fp_port, 1, 1, 1, 1)
        settings.append(machine_grid)

        settings.append(Gtk.Separator())
        settings.append(self._section_label("IDE / CF"))

        self.cf0 = ImageRow("CF0 / Drive A", self._controls_changed, self._cf_work_copy_0)
        self.cf1 = ImageRow("CF1 / Drive B", self._controls_changed, self._cf_work_copy_1)
        self.cf0.set_path(self.config.cf0)
        self.cf1.set_path(self.config.cf1)
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
            "Off by default to protect archival images. Prefer a Work Copy before enabling writes."
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

        command_header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.status = Gtk.Label(label="Stopped", xalign=0)
        self.status.add_css_class("heading")
        command_header.append(self.status)
        terminal_box.append(command_header)

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

    def _controls_changed(self, *_args) -> None:
        config = self._current_config()
        self.command.set_text(config.shell_command(REPO_ROOT))
        try:
            save_config(config)
        except OSError:
            pass

    def _profile_changed(self, *_args) -> None:
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
        self.stop_button.set_sensitive(value)
        self.restart_button.set_sensitive(value)
        if not value and self.status.get_text() == "Running":
            self.status.set_text("Stopped")

    def _spawn(self, argv: list[str], label: str) -> None:
        if self.running:
            return
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
            self.status.set_text("Running")

    def _child_exited(self, _terminal, status) -> None:
        self._set_running(False)
        if self.pending_restart:
            self.pending_restart = False
            GLib.idle_add(self._start_session)
        elif status == 0:
            self.status.set_text("Stopped")
        else:
            self.status.set_text(f"Exited ({status})")

    def _start(self, _button) -> None:
        self._start_session()

    def _start_session(self) -> bool:
        config = self._current_config()
        errors = config.validate()
        if errors:
            self.status.set_text(errors[0])
            self.terminal.feed(("Configuration error:\r\n  " + "\r\n  ".join(errors) + "\r\n").encode(), -1)
            return False
        self._spawn(config.make_argv(REPO_ROOT), "Starting…")
        return False

    def _build(self, _button) -> None:
        self._spawn(["make", "-C", str(REPO_ROOT), "build", "current-rom"], "Building…")

    def _stop(self, _button) -> None:
        if self.running:
            # Ctrl-] is the targetsim host escape and follows normal cleanup.
            self.terminal.feed_child("\x1d")

    def _restart(self, _button) -> None:
        if self.running:
            self.pending_restart = True
            self._stop(_button)
        else:
            self._start_session()

    def _close_request(self, *_args):
        try:
            save_config(self._current_config())
        except OSError:
            pass
        if self.running:
            self.terminal.feed_child("\x1d")
        return False

    @staticmethod
    def _copy_file(source: Path, destination: Path) -> Path:
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        return destination

    def _dsi_work_copy(self, source: Path, number: int) -> Path:
        if source.stat().st_size != DSI_SD_SIZE:
            raise ValueError("DSI work copies require a 256,256-byte FDC-1 SD image")
        return self._copy_file(source, REPO_ROOT / "build" / f"dsi{number}-work.img")

    def _dsi_work_copy_0(self, source: Path) -> Path:
        return self._dsi_work_copy(source, 0)

    def _dsi_work_copy_1(self, source: Path) -> Path:
        return self._dsi_work_copy(source, 1)

    @staticmethod
    def _cf_work_copy(source: Path, number: int) -> Path:
        destination = REPO_ROOT / "build" / f"cf{number}-work.img"
        destination.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            [sys.executable, str(REPO_ROOT / "tools" / "make_cf_workcopy.py"), str(source), str(destination)],
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
    missing = []
    for command in ("make", "python3"):
        if shutil.which(command) is None:
            missing.append(command)
    if missing:
        raise SystemExit("Missing required command(s): " + ", ".join(missing))


def main() -> int:
    check_runtime()
    app = TargetSimApplication()
    return app.run(sys.argv)


if __name__ == "__main__":
    raise SystemExit(main())
