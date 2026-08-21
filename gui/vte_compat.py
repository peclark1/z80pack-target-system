#!/usr/bin/env python3
"""Small PyGObject/VTE compatibility helpers for the GTK front end."""

from __future__ import annotations


def install_feed_child_string_compat() -> bool:
    """Allow Vte.Terminal.feed_child() callers to pass Python strings.

    Ubuntu 24.04's VTE 3.91 introspection binding exposes feed_child() as a
    byte-array/list-of-integers argument. Passing a normal Python ``str`` then
    fails with ``TypeError: Must be number, not str``.  The GUI historically
    passed the Ctrl-] host escape as a string, so normalize strings to UTF-8
    bytes at the binding boundary.

    The helper is safe to import in host-side unit tests where PyGObject/VTE is
    not installed; in that case it simply does nothing and returns False.
    """
    try:
        import gi

        gi.require_version("Vte", "3.91")
        from gi.repository import Vte
    except (ImportError, ValueError):
        return False

    original = Vte.Terminal.feed_child
    if getattr(original, "_imsai_string_compat", False):
        return True

    def feed_child_compat(self, text):
        if isinstance(text, str):
            text = text.encode("utf-8")
        return original(self, text)

    feed_child_compat._imsai_string_compat = True
    Vte.Terminal.feed_child = feed_child_compat
    return True
