#!/usr/bin/env python3
"""Managed image-row extension layered on the state-preserving GUI."""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess

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


ANALYZER_COMMAND = "cpm-disk-analyzer-gui"


def _find_analyzer_launcher() -> str | None:
    """Return the installed CP/M Disk Analyzer GUI launcher, if available."""
    launcher = shutil.which(ANALYZER_COMMAND)
    if launcher:
        return launcher

    # The analyzer installer creates this launcher even when ~/.local/bin is
    # not on PATH, so check that standard per-user location explicitly.
    local_launcher = Path.home() / ".local" / "bin" / ANALYZER_COMMAND
    if local_launcher.is_file() and os.access(local_launcher, os.X_OK):
        return str(local_launcher)
    return None


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

            self.analyze_button = _core.Gtk.Button(label="Analyze")
            self.analyze_button.set_tooltip_text(
                "Open this image in CP/M Disk Analyzer. Inspection is safe while mounted; "
                "stop the emulator before modifying the image."
            )
            self.analyze_button.set_sensitive(bool(self.get_path()))
            self.analyze_button.connect("clicked", self._open_analyzer)
            selector.append(self.analyze_button)
        else:
            self.analyze_button = None

    def media_type(self) -> str:
        return "cf" if self.title.startswith("CF") else "floppy"

    def _open_library(self, _button) -> None:
        open_library_for_row(self)

    def _open_analyzer(self, _button) -> None:
        value = self.get_path().strip()
        if not value:
            self.info.set_text("Select an image before opening CP/M Disk Analyzer")
            return

        image = Path(value).expanduser()
        if not image.is_file():
            self.info.set_text(f"Image not found: {image}")
            return

        launcher = _find_analyzer_launcher()
        if launcher is None:
            self.info.set_text(
                "CP/M Disk Analyzer is not installed. Expected "
                "cpm-disk-analyzer-gui on PATH or in ~/.local/bin."
            )
            return

        try:
            subprocess.Popen(
                [launcher, str(image.resolve())],
                start_new_session=True,
            )
        except OSError as exc:
            self.info.set_text(f"Could not open CP/M Disk Analyzer: {exc}")

    def _make_work_copy(self, _button) -> None:
        begin_managed_work_copy(self)

    def refresh_info(self) -> None:
        super().refresh_info()
        analyze_button = getattr(self, "analyze_button", None)
        if analyze_button is not None:
            analyze_button.set_sensitive(bool(self.get_path()))

        value = self.get_path()
        if not value:
            return
        lineage = library_summary_for_path(value, _core.REPO_ROOT)
        if not lineage:
            return
        current = self.info.get_text()
        self.info.set_text(f"{current}\n{lineage}" if current else lineage)
