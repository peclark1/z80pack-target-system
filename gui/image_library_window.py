#!/usr/bin/env python3
"""GTK browser for emulator master images and managed working copies."""

from __future__ import annotations

from pathlib import Path
import shutil
import subprocess
import sys

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import GLib, Gtk  # noqa: E402

try:
    from image_library import ImageLibrary, MasterImage, WorkCopy
    from image_library_dialogs import (MetadataDialog, NoteDialog, media_type, profile_for_row, profile_name, show_error)
except ImportError:  # pragma: no cover
    from .image_library import ImageLibrary, MasterImage, WorkCopy
    from .image_library_dialogs import (MetadataDialog, NoteDialog, media_type, profile_for_row, profile_name, show_error)

class LibraryWindow(Gtk.Window):
    def __init__(self, row, *, select_master_id=None):
        parent = row.get_root()
        super().__init__(title="Emulator Image Library", transient_for=parent, modal=True)
        self.row = row
        self.parent = parent
        self.library = ImageLibrary(Path(__file__).resolve().parents[1])
        self.media_type = media_type(row)
        self.select_master_id = select_master_id
        self.masters: dict[int, MasterImage] = {}
        self.works: dict[int, WorkCopy] = {}
        self._file_dialog = None
        self.set_default_size(900, 620)

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        for name in ("top", "bottom", "start", "end"):
            getattr(root, f"set_margin_{name}")(12)
        self.set_child(root)

        filters = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.search = Gtk.SearchEntry(hexpand=True, placeholder_text="Search images")
        self.search.connect("search-changed", self._refresh)
        filters.append(self.search)
        self.profile = Gtk.Entry(placeholder_text="Profile filter")
        self.profile.connect("changed", self._refresh)
        filters.append(self.profile)
        add = Gtk.Button(label="Add Image…")
        add.connect("clicked", self._add)
        filters.append(add)
        root.append(filters)

        title = Gtk.Label(label="CF masters" if self.media_type == "cf" else "Floppy masters", xalign=0)
        title.add_css_class("title-4")
        root.append(title)

        panes = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL, vexpand=True)
        panes.set_position(420)
        root.append(panes)
        self.master_list = Gtk.ListBox(selection_mode=Gtk.SelectionMode.SINGLE)
        self.master_list.connect("row-selected", self._master_selected)
        left = Gtk.ScrolledWindow()
        left.set_child(self.master_list)
        panes.set_start_child(left)

        right = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=7)
        right.set_margin_start(8)
        panes.set_end_child(right)
        self.details = Gtk.Label(xalign=0, yalign=0, wrap=True, selectable=True)
        right.append(self.details)
        mbuttons = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
        self.use_master = self._button(mbuttons, "Use Master", self._use_master)
        self.edit = self._button(mbuttons, "Edit Metadata", self._edit)
        self.create = self._button(mbuttons, "Create Work Copy", self._create_work)
        right.append(mbuttons)
        right.append(Gtk.Separator())
        label = Gtk.Label(label="Working Copies", xalign=0)
        label.add_css_class("heading")
        right.append(label)
        self.work_list = Gtk.ListBox(selection_mode=Gtk.SelectionMode.SINGLE)
        self.work_list.connect("row-selected", lambda *_: self._buttons())
        wscroll = Gtk.ScrolledWindow(vexpand=True)
        wscroll.set_child(self.work_list)
        right.append(wscroll)
        wbuttons = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
        self.use_work = self._button(wbuttons, "Use Selected", self._use_work)
        self.reset = self._button(wbuttons, "Reset from Master", self._reset)
        self.link = self._button(wbuttons, "Link Untracked", self._link)
        right.append(wbuttons)
        close = Gtk.Button(label="Close", halign=Gtk.Align.END)
        close.connect("clicked", lambda *_: self.destroy())
        root.append(close)
        self._refresh()

    @staticmethod
    def _button(box, label, callback):
        button = Gtk.Button(label=label)
        button.connect("clicked", callback)
        box.append(button)
        return button

    @staticmethod
    def _clear(box):
        child = box.get_first_child()
        while child:
            nxt = child.get_next_sibling()
            box.remove(child)
            child = nxt

    def _master_row(self, master):
        row = Gtk.ListBoxRow()
        row.master_id = master.id
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        for name in ("top", "bottom", "start", "end"):
            getattr(box, f"set_margin_{name}")(6)
        name = Gtk.Label(label=master.filename, xalign=0)
        name.add_css_class("heading")
        box.append(name)
        meta = Gtk.Label(label=profile_name(master.profile), xalign=0)
        meta.add_css_class("dim-label")
        box.append(meta)
        if master.description:
            desc = Gtk.Label(label=master.description, xalign=0, wrap=True)
            box.append(desc)
        row.set_child(box)
        return row

    def _work_row(self, work):
        row = Gtk.ListBoxRow()
        row.work_id = work.id
        text = work.filename + ("" if work.exists else " [missing]")
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        for name in ("top", "bottom", "start", "end"):
            getattr(box, f"set_margin_{name}")(5)
        box.append(Gtk.Label(label=text, xalign=0))
        if work.note:
            note = Gtk.Label(label=work.note, xalign=0, wrap=True)
            box.append(note)
        activity = Gtk.Label(
            label=f"Created {work.created_at} · Last used {work.last_used or 'never'}",
            xalign=0,
            wrap=True,
        )
        activity.add_css_class("dim-label")
        box.append(activity)
        row.set_child(box)
        return row

    def _untracked_row(self, path):
        row = Gtk.ListBoxRow()
        row.untracked_path = path
        label = Gtk.Label(label=f"{path.name} [untracked]", xalign=0)
        label.set_margin_top(6); label.set_margin_bottom(6); label.set_margin_start(6); label.set_margin_end(6)
        row.set_child(label)
        return row

    def _refresh(self, *_args):
        selected = self.select_master_id
        current = self._master()
        if current:
            selected = current.id
        self._clear(self.master_list)
        profile = self.profile.get_text().strip() if hasattr(self, "profile") else ""
        masters = self.library.list_masters(
            media_type=self.media_type,
            profile=profile or None,
            search=self.search.get_text() if hasattr(self, "search") else "",
        )
        self.masters = {m.id: m for m in masters}
        target = None
        for master in masters:
            row = self._master_row(master)
            self.master_list.append(row)
            if master.id == selected:
                target = row
        if target:
            self.master_list.select_row(target)
        elif masters:
            self.master_list.select_row(self.master_list.get_row_at_index(0))
        else:
            self.details.set_text("No images in this library yet.")
            self._refresh_works(None)
        self._buttons()

    def _master(self):
        row = self.master_list.get_selected_row() if hasattr(self, "master_list") else None
        return self.masters.get(getattr(row, "master_id", -1)) if row else None

    def _work(self):
        row = self.work_list.get_selected_row() if hasattr(self, "work_list") else None
        return self.works.get(getattr(row, "work_id", -1)) if row else None

    def _untracked(self):
        row = self.work_list.get_selected_row() if hasattr(self, "work_list") else None
        return getattr(row, "untracked_path", None) if row else None

    def _master_selected(self, *_args):
        master = self._master()
        if master:
            self.details.set_text(
                f"{master.filename}\nProfile: {profile_name(master.profile)}\n"
                f"Description: {master.description or '—'}\nMaster: {master.path}\n"
                f"Size: {master.size:,} bytes"
            )
        else:
            self.details.set_text("")
        self._refresh_works(master)
        self._buttons()

    def _refresh_works(self, master):
        self._clear(self.work_list)
        works = self.library.list_work_copies(master.id) if master else []
        self.works = {w.id: w for w in works}
        for work in works:
            self.work_list.append(self._work_row(work))
        for path in self.library.untracked_work_images(self.media_type):
            self.work_list.append(self._untracked_row(path))

    def _buttons(self):
        if not hasattr(self, "use_master"):
            return
        master, work, untracked = self._master(), self._work(), self._untracked()
        self.use_master.set_sensitive(bool(master and master.path.is_file()))
        self.edit.set_sensitive(master is not None)
        self.create.set_sensitive(bool(master and master.path.is_file() and self.row.work_copy))
        self.use_work.set_sensitive(bool((work and work.exists) or (untracked and untracked.is_file())))
        self.reset.set_sensitive(bool(master and work and master.path.is_file()))
        self.link.set_sensitive(bool(master and untracked))

    def _select(self, path):
        self.row.set_path(str(path))
        self.destroy()

    def _use_master(self, _button):
        master = self._master()
        if master and master.path.is_file():
            self.library.touch_master(master.id)
            self._select(master.path)

    def _use_work(self, _button):
        work = self._work()
        if work and work.exists:
            self.library.touch_work_copy(work.id)
            self._select(work.path)
            return
        untracked = self._untracked()
        if untracked and untracked.is_file():
            self._select(untracked)

    def _create_work(self, _button):
        master = self._master()
        if not master or not self.row.work_copy:
            return
        def create(note):
            try:
                path = self.row.work_copy(master.path)
                work = self.library.register_work_copy(master.id, path, note)
                self.library.touch_work_copy(work.id)
            except (OSError, ValueError, subprocess.CalledProcessError) as exc:
                show_error(self.parent, f"Work-copy error: {exc}")
                return
            self._select(work.path)
        NoteDialog(self, master, create).present()

    def _reset(self, _button):
        master, work = self._master(), self._work()
        if not master or not work:
            return
        alert = Gtk.AlertDialog(
            message=f"Reset {work.filename} from {master.filename}?",
            detail="All changes in the working copy will be discarded.",
            buttons=["Cancel", "Reset"], cancel_button=0, default_button=0,
        )
        alert.choose(self, None, self._reset_done, (master, work))

    def _reset_done(self, alert, result, data):
        try:
            if alert.choose_finish(result) != 1:
                return
        except GLib.Error:
            return
        master, work = data
        try:
            work.path.parent.mkdir(parents=True, exist_ok=True)
            if master.media_type == "cf":
                subprocess.run([
                    sys.executable,
                    str(self.library.repo_root / "tools" / "make_cf_workcopy.py"),
                    str(master.path), str(work.path),
                ], check=True)
            else:
                shutil.copy2(master.path, work.path)
            self.library.touch_work_copy(work.id)
        except (OSError, ValueError, subprocess.CalledProcessError) as exc:
            show_error(self.parent, f"Reset failed: {exc}")
            return
        self._refresh_works(master)
        self.row.refresh_info()

    def _link(self, _button):
        master, path = self._master(), self._untracked()
        if not master or not path:
            return
        def link(note):
            try:
                self.library.register_work_copy(master.id, path, note)
            except OSError as exc:
                show_error(self.parent, f"Could not link work image: {exc}")
                return
            self._refresh_works(master)
            self._buttons()
        NoteDialog(self, master, link).present()

    def _edit(self, _button):
        master = self._master()
        if not master:
            return
        def save(response, profile, description):
            if response == Gtk.ResponseType.OK:
                self.library.update_master(master.id, profile=profile, description=description)
                self.select_master_id = master.id
                self._refresh()
        MetadataDialog(
            self, filename=master.filename, media_type=master.media_type,
            profile=master.profile, description=master.description,
            title="Edit Image Metadata", callback=save,
        ).present()

    def _add(self, _button):
        dialog = Gtk.FileDialog(title="Add image to emulator library")
        self._file_dialog = dialog
        dialog.open(self, None, self._add_selected)

    def _add_selected(self, dialog, result):
        try:
            selected = dialog.open_finish(result)
        except GLib.Error:
            return
        finally:
            self._file_dialog = None
        path = selected.get_path() if selected else None
        if not path:
            return
        source = Path(path)
        def save(response, profile, description):
            if response != Gtk.ResponseType.OK:
                return
            try:
                master = self.library.add_master(
                    source, self.media_type, profile=profile, description=description
                )
            except (OSError, ValueError) as exc:
                show_error(self.parent, f"Could not add image: {exc}")
                return
            self.select_master_id = master.id
            self._refresh()
        MetadataDialog(
            self, filename=source.name, media_type=self.media_type,
            profile=profile_for_row(self.row), title="Add Image to Library",
            primary="Add", callback=save,
        ).present()
