#!/usr/bin/env python3
"""Terminal clipboard integration for the GTK4/VTE emulator window."""

from __future__ import annotations

from gi.repository import Gio, Vte

COPY_ACTION = "terminal-copy"
PASTE_ACTION = "terminal-paste"
COPY_ACCEL = "<Primary><Shift>c"
PASTE_ACCEL = "<Primary><Shift>v"


def install_terminal_clipboard(window_class) -> None:
    """Add copy/paste actions, shortcuts, and a VTE context menu to a window class.

    The accelerator choices deliberately leave plain Ctrl-C and Ctrl-V alone so
    CP/M and other guest software continue to receive normal control characters.
    """
    if getattr(window_class, "_terminal_clipboard_installed", False):
        return

    original_init = window_class.__init__

    def init_with_terminal_clipboard(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        _install_on_window(self)

    window_class.__init__ = init_with_terminal_clipboard
    window_class._terminal_clipboard_installed = True


def _install_on_window(window) -> None:
    terminal = getattr(window, "terminal", None)
    if terminal is None:
        return

    copy_action = Gio.SimpleAction.new(COPY_ACTION, None)
    paste_action = Gio.SimpleAction.new(PASTE_ACTION, None)

    copy_action.set_enabled(bool(terminal.get_has_selection()))
    copy_action.connect("activate", _copy_selection, terminal)
    paste_action.connect("activate", _paste_clipboard, terminal)

    window.add_action(copy_action)
    window.add_action(paste_action)

    terminal.connect("selection-changed", _selection_changed, copy_action)

    # VTE builds its own right-click popover from this model. Keeping the menu
    # on the terminal also means keyboard shortcuts and the context menu share
    # the exact same actions.
    if hasattr(terminal, "set_context_menu_model"):
        menu = Gio.Menu()
        menu.append("Copy", f"win.{COPY_ACTION}")
        menu.append("Paste", f"win.{PASTE_ACTION}")
        terminal.set_context_menu_model(menu)
        window._terminal_clipboard_menu = menu

    app = window.get_application()
    if app is not None:
        app.set_accels_for_action(f"win.{COPY_ACTION}", [COPY_ACCEL])
        app.set_accels_for_action(f"win.{PASTE_ACTION}", [PASTE_ACCEL])

    # Retain references for the life of the window and for lightweight tests.
    window._terminal_copy_action = copy_action
    window._terminal_paste_action = paste_action


def _selection_changed(terminal, copy_action) -> None:
    copy_action.set_enabled(bool(terminal.get_has_selection()))


def _copy_selection(_action, _parameter, terminal) -> None:
    if terminal.get_has_selection():
        terminal.copy_clipboard_format(Vte.Format.TEXT)


def _paste_clipboard(_action, _parameter, terminal) -> None:
    terminal.paste_clipboard()
