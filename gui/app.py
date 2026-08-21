#!/usr/bin/env python3
"""State-preserving entry point for the GTK4/VTE target-system GUI."""

from __future__ import annotations

import core_app as _core
from window_state import WindowState, load_window_state, save_window_state

_BaseTargetSimWindow = _core.TargetSimWindow


def _find_main_paned(window):
    """Return the main left/right Gtk.Paned created by core_app, if present."""
    root = window.get_child()
    child = root.get_first_child() if root is not None else None
    return child if isinstance(child, _core.Gtk.Paned) else None


class TargetSimWindow(_BaseTargetSimWindow):
    """Core GUI window with persistent size/maximized/divider state."""

    def __init__(self, *args, **kwargs):
        state = load_window_state()
        super().__init__(*args, **kwargs)

        # GTK recommends get/set_default_size() for persistent window sizing;
        # it retains the normal (unmaximized) dimensions as the user resizes.
        self.set_default_size(state.width, state.height)
        self._state_paned = _find_main_paned(self)
        if self._state_paned is not None:
            self._state_paned.set_position(state.paned_position)
        if state.maximized:
            self.maximize()

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
