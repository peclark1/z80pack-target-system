#!/usr/bin/env python3
"""SQLite-backed master-image and working-copy catalog for the target-system GUI."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
import shutil
import sqlite3
from typing import Iterable


DEFAULT_REPO_ROOT = Path(__file__).resolve().parents[1]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


@dataclass(frozen=True)
class MasterImage:
    id: int
    path: Path
    filename: str
    media_type: str
    profile: str
    description: str
    size: int
    sha256: str
    created_at: str
    updated_at: str
    last_used: str


@dataclass(frozen=True)
class WorkCopy:
    id: int
    master_id: int
    path: Path
    filename: str
    note: str
    created_at: str
    last_used: str

    @property
    def exists(self) -> bool:
        return self.path.is_file()


class ImageLibrary:
    """Manage emulator-only masters under disks/library and lineage under build/."""

    def __init__(self, repo_root: Path | str = DEFAULT_REPO_ROOT):
        self.repo_root = Path(repo_root).expanduser().resolve()
        self.library_root = self.repo_root / "disks" / "library"
        self.master_root = self.library_root / "masters"
        self.database_path = self.library_root / "library.db"
        self.ensure()

    def ensure(self) -> None:
        (self.master_root / "cf").mkdir(parents=True, exist_ok=True)
        (self.master_root / "floppy").mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS master_images (
                    id INTEGER PRIMARY KEY,
                    path TEXT NOT NULL UNIQUE,
                    filename TEXT NOT NULL,
                    media_type TEXT NOT NULL CHECK (media_type IN ('cf', 'floppy')),
                    profile TEXT NOT NULL DEFAULT '',
                    description TEXT NOT NULL DEFAULT '',
                    size INTEGER NOT NULL,
                    sha256 TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    last_used TEXT NOT NULL DEFAULT ''
                );

                CREATE INDEX IF NOT EXISTS master_images_media_idx
                    ON master_images(media_type);
                CREATE INDEX IF NOT EXISTS master_images_profile_idx
                    ON master_images(profile);
                CREATE INDEX IF NOT EXISTS master_images_sha_idx
                    ON master_images(sha256);

                CREATE TABLE IF NOT EXISTS work_copies (
                    id INTEGER PRIMARY KEY,
                    master_id INTEGER NOT NULL REFERENCES master_images(id) ON DELETE CASCADE,
                    path TEXT NOT NULL UNIQUE,
                    filename TEXT NOT NULL,
                    note TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    last_used TEXT NOT NULL DEFAULT ''
                );

                CREATE INDEX IF NOT EXISTS work_copies_master_idx
                    ON work_copies(master_id);
                """
            )
            rows = db.execute("SELECT path FROM master_images").fetchall()
        for row in rows:
            path = self._load_path(row["path"])
            if path.is_file():
                self._protect_master(path)

    def _protect_master(self, path: Path) -> None:
        """Remove write bits from masters stored inside the private library."""
        try:
            path.resolve().relative_to(self.master_root.resolve())
        except ValueError:
            return
        mode = path.stat().st_mode
        path.chmod(mode & ~0o222)

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.database_path)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys = ON")
        return db

    def _store_path(self, path: Path | str) -> str:
        resolved = Path(path).expanduser().resolve()
        try:
            return resolved.relative_to(self.repo_root).as_posix()
        except ValueError:
            return str(resolved)

    def _load_path(self, stored: str) -> Path:
        path = Path(stored)
        return path if path.is_absolute() else self.repo_root / path

    def _master_from_row(self, row: sqlite3.Row) -> MasterImage:
        return MasterImage(
            id=row["id"],
            path=self._load_path(row["path"]),
            filename=row["filename"],
            media_type=row["media_type"],
            profile=row["profile"],
            description=row["description"],
            size=row["size"],
            sha256=row["sha256"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            last_used=row["last_used"],
        )

    def _work_from_row(self, row: sqlite3.Row) -> WorkCopy:
        return WorkCopy(
            id=row["id"],
            master_id=row["master_id"],
            path=self._load_path(row["path"]),
            filename=row["filename"],
            note=row["note"],
            created_at=row["created_at"],
            last_used=row["last_used"],
        )

    @staticmethod
    def _validate_media_type(media_type: str) -> str:
        value = (media_type or "").strip().lower()
        if value not in {"cf", "floppy"}:
            raise ValueError("media type must be 'cf' or 'floppy'")
        return value

    def _unique_master_destination(self, source: Path, media_type: str) -> Path:
        directory = self.master_root / media_type
        destination = directory / source.name
        if not destination.exists():
            return destination
        stem = source.stem
        suffix = source.suffix
        number = 2
        while True:
            candidate = directory / f"{stem}-{number}{suffix}"
            if not candidate.exists():
                return candidate
            number += 1

    def add_master(
        self,
        source: Path | str,
        media_type: str,
        profile: str = "",
        description: str = "",
        *,
        copy_into_library: bool = True,
    ) -> MasterImage:
        source_path = Path(source).expanduser().resolve()
        if not source_path.is_file():
            raise FileNotFoundError(source_path)
        media_type = self._validate_media_type(media_type)
        profile = (profile or "").strip()
        description = (description or "").strip()
        digest = _sha256(source_path)

        # Reuse an identical master already catalogued for this media type.
        with self._connect() as db:
            row = db.execute(
                "SELECT * FROM master_images WHERE sha256 = ? AND media_type = ? ORDER BY id LIMIT 1",
                (digest, media_type),
            ).fetchone()
            if row is not None:
                master = self._master_from_row(row)
                if master.path.is_file():
                    self._protect_master(master.path)
                    self.update_master(
                        master.id,
                        profile=profile or master.profile,
                        description=description or master.description,
                    )
                    return self.get_master(master.id)

        if copy_into_library:
            try:
                source_path.relative_to(self.master_root)
                destination = source_path
            except ValueError:
                destination = self._unique_master_destination(source_path, media_type)
                shutil.copy2(source_path, destination)
        else:
            destination = source_path

        self._protect_master(destination)
        now = _utc_now()
        stored_path = self._store_path(destination)
        size = destination.stat().st_size
        with self._connect() as db:
            cursor = db.execute(
                """
                INSERT INTO master_images
                    (path, filename, media_type, profile, description, size, sha256,
                     created_at, updated_at, last_used)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, '')
                """,
                (
                    stored_path,
                    destination.name,
                    media_type,
                    profile,
                    description,
                    size,
                    digest,
                    now,
                    now,
                ),
            )
            master_id = int(cursor.lastrowid)
        return self.get_master(master_id)

    def get_master(self, master_id: int) -> MasterImage:
        with self._connect() as db:
            row = db.execute("SELECT * FROM master_images WHERE id = ?", (master_id,)).fetchone()
        if row is None:
            raise KeyError(master_id)
        return self._master_from_row(row)

    def update_master(
        self,
        master_id: int,
        *,
        profile: str | None = None,
        description: str | None = None,
    ) -> None:
        current = self.get_master(master_id)
        with self._connect() as db:
            db.execute(
                "UPDATE master_images SET profile = ?, description = ?, updated_at = ? WHERE id = ?",
                (
                    current.profile if profile is None else profile.strip(),
                    current.description if description is None else description.strip(),
                    _utc_now(),
                    master_id,
                ),
            )

    def list_masters(
        self,
        *,
        media_type: str | None = None,
        profile: str | None = None,
        search: str = "",
    ) -> list[MasterImage]:
        clauses: list[str] = []
        params: list[str] = []
        if media_type:
            clauses.append("media_type = ?")
            params.append(self._validate_media_type(media_type))
        if profile:
            clauses.append("profile = ?")
            params.append(profile.strip())
        term = search.strip()
        if term:
            clauses.append("(filename LIKE ? OR profile LIKE ? OR description LIKE ?)")
            like = f"%{term}%"
            params.extend([like, like, like])
        sql = "SELECT * FROM master_images"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY filename COLLATE NOCASE, id"
        with self._connect() as db:
            rows = db.execute(sql, params).fetchall()
        return [self._master_from_row(row) for row in rows]

    def master_for_path(self, path: Path | str) -> MasterImage | None:
        stored = self._store_path(path)
        with self._connect() as db:
            row = db.execute("SELECT * FROM master_images WHERE path = ?", (stored,)).fetchone()
            if row is not None:
                return self._master_from_row(row)
            work = db.execute("SELECT master_id FROM work_copies WHERE path = ?", (stored,)).fetchone()
            if work is None:
                return None
            row = db.execute("SELECT * FROM master_images WHERE id = ?", (work["master_id"],)).fetchone()
        return self._master_from_row(row) if row is not None else None

    def work_copy_for_path(self, path: Path | str) -> WorkCopy | None:
        stored = self._store_path(path)
        with self._connect() as db:
            row = db.execute("SELECT * FROM work_copies WHERE path = ?", (stored,)).fetchone()
        return self._work_from_row(row) if row is not None else None

    def register_work_copy(self, master_id: int, path: Path | str, note: str = "") -> WorkCopy:
        self.get_master(master_id)  # validate foreign key with a useful KeyError
        work_path = Path(path).expanduser().resolve()
        if not work_path.is_file():
            raise FileNotFoundError(work_path)
        stored = self._store_path(work_path)
        now = _utc_now()
        with self._connect() as db:
            row = db.execute("SELECT id FROM work_copies WHERE path = ?", (stored,)).fetchone()
            if row is None:
                cursor = db.execute(
                    """
                    INSERT INTO work_copies
                        (master_id, path, filename, note, created_at, last_used)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (master_id, stored, work_path.name, note.strip(), now, now),
                )
                work_id = int(cursor.lastrowid)
            else:
                work_id = int(row["id"])
                db.execute(
                    """
                    UPDATE work_copies
                    SET master_id = ?, filename = ?, note = ?, last_used = ?
                    WHERE id = ?
                    """,
                    (master_id, work_path.name, note.strip(), now, work_id),
                )
        return self.get_work_copy(work_id)

    def get_work_copy(self, work_id: int) -> WorkCopy:
        with self._connect() as db:
            row = db.execute("SELECT * FROM work_copies WHERE id = ?", (work_id,)).fetchone()
        if row is None:
            raise KeyError(work_id)
        return self._work_from_row(row)

    def list_work_copies(self, master_id: int) -> list[WorkCopy]:
        with self._connect() as db:
            rows = db.execute(
                "SELECT * FROM work_copies WHERE master_id = ? ORDER BY last_used DESC, created_at DESC, id DESC",
                (master_id,),
            ).fetchall()
        return [self._work_from_row(row) for row in rows]

    def touch_master(self, master_id: int) -> None:
        with self._connect() as db:
            db.execute("UPDATE master_images SET last_used = ? WHERE id = ?", (_utc_now(), master_id))

    def touch_work_copy(self, work_id: int) -> None:
        now = _utc_now()
        with self._connect() as db:
            row = db.execute("SELECT master_id FROM work_copies WHERE id = ?", (work_id,)).fetchone()
            if row is None:
                raise KeyError(work_id)
            db.execute("UPDATE work_copies SET last_used = ? WHERE id = ?", (now, work_id))
            db.execute("UPDATE master_images SET last_used = ? WHERE id = ?", (now, row["master_id"]))

    def set_work_note(self, work_id: int, note: str) -> None:
        with self._connect() as db:
            db.execute("UPDATE work_copies SET note = ? WHERE id = ?", (note.strip(), work_id))

    def untracked_work_images(self, media_type: str | None = None) -> list[Path]:
        build = self.repo_root / "build"
        if not build.is_dir():
            return []
        with self._connect() as db:
            registered = {row["path"] for row in db.execute("SELECT path FROM work_copies")}
        if media_type:
            media_type = self._validate_media_type(media_type)
        if media_type == "cf":
            candidates: Iterable[Path] = build.glob("cf*work*.img")
        elif media_type == "floppy":
            candidates = list(build.glob("dsi*work*.img")) + list(build.glob("fdcplus*work*.img"))
        else:
            candidates = build.glob("*work*.img")

        result = []
        for candidate in sorted(candidates):
            if self._store_path(candidate) not in registered:
                result.append(candidate.resolve())
        return result

    def all_profiles(self, media_type: str | None = None) -> list[str]:
        masters = self.list_masters(media_type=media_type)
        return sorted({master.profile for master in masters if master.profile}, key=str.casefold)
