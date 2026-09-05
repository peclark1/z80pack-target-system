#!/usr/bin/env python3
"""Shared GTK dialogs and display helpers for the emulator image library."""

from __future__ import annotations

from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk  # noqa: E402

try:
    from image_library import ImageLibrary, MasterImage
except ImportError:  # pragma: no cover
    from .image_library import ImageLibrary, MasterImage

PROFILE_NAMES = {
    "target": "Target System",
    "dsi-compat": "DSI Compatibility",
    "dsi-vti": "DSI + Polymorphic VTI",
    "fdcplus-vti": "FDC+ + Polymorphic VTI",
}


def profile_name(value: str) -> str:
    return PROFILE_NAMES.get(value, value or "Unspecified")


def profile_for_row(row) -> str:
    root = row.get_root()
    selector = getattr(root, "_selected_profile", None) if root else None
    if callable(selector):
        try:
            return selector() or ""
        except Exception:
            pass
    config = getattr(root, "config", None) if root else None
    return getattr(config, "profile", "") if config else ""


def media_type(row) -> str:
    getter = getattr(row, "media_type", None)
    value = getter() if callable(getter) else getter
    if value in {"cf", "floppy"}:
        return value
    return "cf" if getattr(row, "title", "").startswith("CF") else "floppy"


def show_error(parent, text: str) -> None:
    alert = Gtk.AlertDialog(message="Image Library", detail=text)
    alert.show(parent)


def library_summary_for_path(path: str | Path, repo_root: Path) -> str:
    if not path:
        return ""
    try:
        library = ImageLibrary(repo_root)
        master = library.master_for_path(path)
        work = library.work_copy_for_path(path)
    except OSError:
        return ""
    if master is None:
        return ""
    profile = f" · {profile_name(master.profile)}" if master.profile else ""
    desc = f" — {master.description}" if master.description else ""
    if work:
        note = f" · {work.note}" if work.note else ""
        return f"Working copy of {master.filename}{profile}{desc}{note}"
    return f"Library master{profile}{desc}"


class MetadataDialog(Gtk.Dialog):
    def __init__(self, parent, *, filename, media_type, profile="", description="",
                 title="Image Metadata", primary="Save", unmanaged=False, callback=None):
        super().__init__(title=title, transient_for=parent, modal=True)
        self.callback = callback
        self.add_button("Cancel", Gtk.ResponseType.CANCEL)
        if unmanaged:
            self.add_button("Unmanaged Copy", Gtk.ResponseType.NO)
        self.add_button(primary, Gtk.ResponseType.OK)
        self.set_default_response(Gtk.ResponseType.OK)
        self.set_default_size(520, 320)
        box = self.get_content_area()
        box.set_spacing(8)
        for name in ("top", "bottom", "start", "end"):
            getattr(box, f"set_margin_{name}")(14)
        heading = Gtk.Label(label=filename, xalign=0)
        heading.add_css_class("heading")
        box.append(heading)
        kind = Gtk.Label(label="CF image" if media_type == "cf" else "Floppy image", xalign=0)
        kind.add_css_class("dim-label")
        box.append(kind)
        box.append(Gtk.Label(label="Profile", xalign=0))
        self.profile = Gtk.Entry(text=profile or "")
        self.profile.set_placeholder_text("target, dsi-compat, dsi-vti, fdcplus-vti")
        box.append(self.profile)
        box.append(Gtk.Label(label="Description", xalign=0))
        self.description = Gtk.TextView(vexpand=True, wrap_mode=Gtk.WrapMode.WORD_CHAR)
        self.description.get_buffer().set_text(description or "")
        scroll = Gtk.ScrolledWindow(min_content_height=120)
        scroll.set_child(self.description)
        box.append(scroll)
        self.connect("response", self._response)

    def _response(self, _dialog, response):
        buf = self.description.get_buffer()
        description = buf.get_text(buf.get_start_iter(), buf.get_end_iter(), True).strip()
        profile = self.profile.get_text().strip()
        callback = self.callback
        self.destroy()
        if callback:
            callback(response, profile, description)


class NoteDialog(Gtk.Dialog):
    def __init__(self, parent, master: MasterImage, callback):
        super().__init__(title="Create Working Copy", transient_for=parent, modal=True)
        self.callback = callback
        self.add_button("Cancel", Gtk.ResponseType.CANCEL)
        self.add_button("Create", Gtk.ResponseType.OK)
        box = self.get_content_area()
        box.set_spacing(8)
        for name in ("top", "bottom", "start", "end"):
            getattr(box, f"set_margin_{name}")(14)
        box.append(Gtk.Label(label=f"Master: {master.filename}", xalign=0))
        self.note = Gtk.Entry()
        self.note.set_placeholder_text("Optional note, e.g. BIOS testing")
        box.append(self.note)
        self.connect("response", self._response)

    def _response(self, _dialog, response):
        note = self.note.get_text().strip()
        callback = self.callback
        self.destroy()
        if response == Gtk.ResponseType.OK:
            callback(note)
