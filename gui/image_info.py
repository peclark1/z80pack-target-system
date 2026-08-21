#!/usr/bin/env python3
"""Disk-image inspection helpers used by the GTK front end."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import hashlib
import os

DSI_SD_SIZE = 77 * 26 * 128
CF_FULL_SIZE = 64 * 256 * 512


@dataclass(frozen=True)
class ImageInfo:
    path: Path
    size: int
    kind: str
    writable: bool

    @property
    def size_text(self) -> str:
        if self.size >= 1024 * 1024:
            return f"{self.size / (1024 * 1024):.2f} MiB"
        if self.size >= 1024:
            return f"{self.size / 1024:.1f} KiB"
        return f"{self.size} bytes"

    @property
    def summary(self) -> str:
        mode = "writable" if self.writable else "read-only"
        return f"{self.kind} · {self.size_text} · {mode}"


def inspect_image(path: str | Path) -> ImageInfo:
    resolved = Path(path).expanduser().resolve()
    size = resolved.stat().st_size

    if size == DSI_SD_SIZE:
        kind = "DSI FDC-1 SD 77×26×128"
    elif size == CF_FULL_SIZE:
        kind = "IDE/CF full 8 MiB geometry"
    elif size % 512 == 0:
        kind = "IDE/CF sector image"
    else:
        kind = "unrecognized image geometry"

    return ImageInfo(
        path=resolved,
        size=size,
        kind=kind,
        writable=os.access(resolved, os.W_OK),
    )


def sha256_file(path: str | Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with Path(path).expanduser().open("rb") as handle:
        while True:
            chunk = handle.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()
