#!/usr/bin/env python3
"""Work-copy workflow and entry points for the emulator image library."""

from __future__ import annotations

from pathlib import Path
import subprocess

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk  # noqa: E402

try:
    from image_library import ImageLibrary
    from image_library_dialogs import (
        MetadataDialog,
        NoteDialog,
        library_summary_for_path,
        media_type,
        profile_for_row,
    )
    from image_library_window import LibraryWindow
except ImportError:  # pragma: no cover
    from .image_library import ImageLibrary
    from .image_library_dialogs import (
        MetadataDialog,
        NoteDialog,
        library_summary_for_path,
        media_type,
        profile_for_row,
    )
    from .image_library_window import LibraryWindow


def open_library_for_row(row, *, select_master_id=None):
    LibraryWindow(row, select_master_id=select_master_id).present()


def _create_first_copy(row, library, master, parent):
    existing = library.list_work_copies(master.id)
    if existing:
        open_library_for_row(row, select_master_id=master.id)
        return

    def create(note):
        try:
            path = row.work_copy(master.path)
            work = library.register_work_copy(master.id, path, note)
            library.touch_work_copy(work.id)
        except (OSError, ValueError, subprocess.CalledProcessError) as exc:
            row.info.set_text(f"Work-copy error: {exc}")
            return
        row.set_path(str(work.path))
        row.refresh_info()

    NoteDialog(parent, master, create).present()


def begin_managed_work_copy(row):
    """Create/reuse a managed work copy, with an unmanaged compatibility path."""
    if not row.work_copy:
        return
    source_text = row.get_path()
    if not source_text:
        row.info.set_text("Select a source image first")
        return
    source = Path(source_text).expanduser().resolve()
    if not source.is_file():
        row.info.set_text("Image not found")
        return

    library = ImageLibrary(Path(__file__).resolve().parents[1])
    parent = row.get_root()
    if source in library.untracked_work_images(media_type(row)):
        row.info.set_text(
            "This is an untracked working copy. Use Library… to link it to its master or reuse it."
        )
        open_library_for_row(row)
        return
    master = library.master_for_path(source)
    if master:
        _create_first_copy(row, library, master, parent)
        return

    def response(result, profile, description):
        if result == Gtk.ResponseType.NO:
            try:
                destination = row.work_copy(source)
            except (OSError, ValueError, subprocess.CalledProcessError) as exc:
                row.info.set_text(f"Work-copy error: {exc}")
                return
            row.set_path(str(destination))
            row.info.set_text(f"Unmanaged working copy: {destination}")
            return
        if result != Gtk.ResponseType.OK:
            return
        try:
            master = library.add_master(
                source,
                media_type(row),
                profile=profile,
                description=description,
            )
        except (OSError, ValueError) as exc:
            row.info.set_text(f"Library error: {exc}")
            return
        _create_first_copy(row, library, master, parent)

    MetadataDialog(
        parent,
        filename=source.name,
        media_type=media_type(row),
        profile=profile_for_row(row),
        title="Add Master Before Creating Work Copy",
        primary="Add to Library",
        unmanaged=True,
        callback=response,
    ).present()


__all__ = [
    "begin_managed_work_copy",
    "library_summary_for_path",
    "open_library_for_row",
]
