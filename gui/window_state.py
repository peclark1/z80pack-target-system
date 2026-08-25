#!/usr/bin/env python3
"""Persistent GTK window-state helpers."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
import json


@dataclass
class WindowState:
    width: int = 1280
    height: int = 800
    maximized: bool = False
    paned_position: int = 450
    last_rom_directory: str = ""
    last_cf_directory: str = ""
    last_floppy_directory: str = ""

    def validated(self) -> "WindowState":
        """Return sane values if a saved state file is stale or corrupted."""
        width = self.width if 640 <= int(self.width) <= 16384 else 1280
        height = self.height if 480 <= int(self.height) <= 16384 else 800
        paned = self.paned_position if 200 <= int(self.paned_position) <= 4096 else 450
        rom_directory = self.last_rom_directory if isinstance(self.last_rom_directory, str) else ""
        cf_directory = self.last_cf_directory if isinstance(self.last_cf_directory, str) else ""
        floppy_directory = (
            self.last_floppy_directory if isinstance(self.last_floppy_directory, str) else ""
        )
        return WindowState(
            width=int(width),
            height=int(height),
            maximized=bool(self.maximized),
            paned_position=int(paned),
            last_rom_directory=rom_directory,
            last_cf_directory=cf_directory,
            last_floppy_directory=floppy_directory,
        )

    @classmethod
    def from_dict(cls, value: dict) -> "WindowState":
        fields = cls.__dataclass_fields__
        try:
            migrated = dict(value)
            legacy_directory = migrated.get("last_disk_directory", "")
            if isinstance(legacy_directory, str):
                migrated.setdefault("last_cf_directory", legacy_directory)
                migrated.setdefault("last_floppy_directory", legacy_directory)
            state = cls(**{key: item for key, item in migrated.items() if key in fields})
            return state.validated()
        except (TypeError, ValueError):
            return cls()


def window_state_path() -> Path:
    return Path.home() / ".config" / "z80pack-target-system" / "window.json"


def load_window_state(path: Path | None = None) -> WindowState:
    path = path or window_state_path()
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            return WindowState()
        return WindowState.from_dict(value)
    except (OSError, ValueError, TypeError):
        return WindowState()


def save_window_state(state: WindowState, path: Path | None = None) -> None:
    path = path or window_state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(asdict(state.validated()), indent=2) + "\n",
        encoding="utf-8",
    )
