#!/usr/bin/env python3
"""Managed image-row extension layered on the state-preserving GUI."""

from __future__ import annotations

import app_base as _base
import core_app as _core

try:
    from image_library_ui import (
        begin_managed_work_copy,
        library_summary_for_path,
        open_library_for_row,
    )
except ImportError:  # pragma: no cover - package import compatibility
    from .image_library_ui import (
        begin_managed_work_copy,
        library_summary_for_path,
        open_library_for_row,
    )


class ManagedImageRow(_base.RememberingImageRow):
    """Image selector with a local master library and work-copy lineage."""

    def __init__(self, title: str, on_change, work_copy=None):
        self.title = title
        super().__init__(title, on_change, work_copy)

        # Base layout is: heading label, horizontal selector row, info label.
        heading = self.get_first_child()
        selector = heading.get_next_sibling() if heading is not None else None
        if isinstance(selector, _core.Gtk.Box):
            library = _core.Gtk.Button(label="Library…")
            library.set_tooltip_text(
                "Browse emulator master images, descriptions, and existing working copies"
            )
            library.connect("clicked", self._open_library)
            selector.append(library)

    def media_type(self) -> str:
        return "cf" if self.title.startswith("CF") else "floppy"

    def _open_library(self, _button) -> None:
        open_library_for_row(self)

    def _make_work_copy(self, _button) -> None:
        begin_managed_work_copy(self)

    def refresh_info(self) -> None:
        super().refresh_info()
        value = self.get_path()
        if not value:
            return
        lineage = library_summary_for_path(value, _core.REPO_ROOT)
        if not lineage:
            return
        current = self.info.get_text()
        self.info.set_text(f"{current}\n{lineage}" if current else lineage)
