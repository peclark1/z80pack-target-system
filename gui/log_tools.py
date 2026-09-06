#!/usr/bin/env python3
"""Emulator-log usability helpers for the GTK/VTE front end."""

from __future__ import annotations

from pathlib import Path
import re

import core_app as _core

LATEST_LOG = _core.REPO_ROOT / "build" / "logs" / "targetsim-latest.log"


def _attach_log_tools(window) -> None:
    terminal = window.terminal
    parent = terminal.get_parent()
    if not isinstance(parent, _core.Gtk.Box):
        return

    previous = terminal.get_prev_sibling()
    parent.remove(terminal)

    scroll = _core.Gtk.ScrolledWindow()
    scroll.set_policy(_core.Gtk.PolicyType.AUTOMATIC, _core.Gtk.PolicyType.AUTOMATIC)
    scroll.set_hexpand(True)
    scroll.set_vexpand(True)
    scroll.set_child(terminal)
    parent.insert_child_after(scroll, previous)
    window.terminal_scroll = scroll

    toolbar = _core.Gtk.Box(orientation=_core.Gtk.Orientation.HORIZONTAL, spacing=6)

    find = _core.Gtk.SearchEntry()
    find.set_hexpand(True)
    find.set_placeholder_text("Find in emulator log…")
    find.set_tooltip_text("Search the in-memory VTE scrollback")
    find.connect("search-changed", window._log_search_changed)
    toolbar.append(find)
    window.log_search_entry = find

    previous_button = _core.Gtk.Button(label="Previous")
    previous_button.set_tooltip_text("Find previous match")
    previous_button.connect("clicked", window._log_find_previous)
    toolbar.append(previous_button)

    next_button = _core.Gtk.Button(label="Next")
    next_button.set_tooltip_text("Find next match")
    next_button.connect("clicked", window._log_find_next)
    toolbar.append(next_button)

    copy_button = _core.Gtk.Button(label="Copy")
    copy_button.set_tooltip_text("Copy selected emulator-log text")
    copy_button.connect("clicked", window._log_copy)
    toolbar.append(copy_button)

    paste_button = _core.Gtk.Button(label="Paste")
    paste_button.set_tooltip_text("Paste clipboard text into the terminal")
    paste_button.connect("clicked", window._log_paste)
    toolbar.append(paste_button)

    open_button = _core.Gtk.Button(label="Open Log")
    open_button.set_tooltip_text(
        "Open build/logs/targetsim-latest.log in the desktop's default text viewer"
    )
    open_button.connect("clicked", window._log_open_file)
    toolbar.append(open_button)

    # Put the tools immediately above the scrollable VTE terminal.
    parent.insert_child_after(toolbar, previous)
    window.log_toolbar = toolbar


def _search_changed(self, entry) -> None:
    text = entry.get_text()
    if not text:
        self.terminal.search_set_regex(None, 0)
        return

    try:
        regex = _core.Vte.Regex.new_for_search(re.escape(text), -1, 0)
    except _core.GLib.Error:
        return

    self.terminal.search_set_regex(regex, 0)
    self.terminal.search_set_wrap_around(True)


def _find_next(self, _button) -> None:
    self.terminal.search_find_next()


def _find_previous(self, _button) -> None:
    self.terminal.search_find_previous()


def _copy(self, _button) -> None:
    if hasattr(self.terminal, "copy_clipboard_format"):
        self.terminal.copy_clipboard_format(_core.Vte.Format.TEXT)
    else:  # pragma: no cover - compatibility with older VTE bindings
        self.terminal.copy_clipboard()


def _paste(self, _button) -> None:
    self.terminal.paste_clipboard()


def _open_file(self, _button) -> None:
    path = Path(LATEST_LOG)
    if not path.exists():
        self.status.set_text("No saved emulator log yet")
        return

    try:
        uri = _core.Gio.File.new_for_path(str(path.resolve())).get_uri()
        _core.Gio.AppInfo.launch_default_for_uri(uri, None)
    except _core.GLib.Error as exc:
        self.status.set_text(f"Could not open emulator log: {exc.message}")


def install_log_tools(window_class) -> None:
    """Layer scrollbar/search/copy/open-log behavior onto TargetSimWindow."""

    original_init = window_class.__init__
    original_update_console_surface = window_class._update_console_surface

    def init_with_log_tools(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        _attach_log_tools(self)
        self._update_console_surface()

    def update_console_surface_with_log_tools(self):
        original_update_console_surface(self)
        if not hasattr(self, "terminal_scroll"):
            return

        # app_base toggles the terminal itself. Move that visibility state to
        # the containing ScrolledWindow so the child remains laid out normally
        # and the vertical scrollbar appears when the log is shown.
        show_log = self.terminal.get_visible()
        self.terminal.set_visible(True)
        self.terminal_scroll.set_visible(show_log)
        self.log_toolbar.set_visible(show_log)

    window_class._log_search_changed = _search_changed
    window_class._log_find_next = _find_next
    window_class._log_find_previous = _find_previous
    window_class._log_copy = _copy
    window_class._log_paste = _paste
    window_class._log_open_file = _open_file
    window_class._update_console_surface = update_console_surface_with_log_tools
    window_class.__init__ = init_with_log_tools
