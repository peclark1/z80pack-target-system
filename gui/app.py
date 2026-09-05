#!/usr/bin/env python3
"""Image-library-enabled entry point for the IMSAI target-system GUI."""

from __future__ import annotations

import app_base as _base
import core_app as _core
from managed_image_row import ManagedImageRow
from image_library import ImageLibrary

# app_base defines the state-preserving GUI and patches core_app.TargetSimWindow.
# Its window constructors resolve core_app.ImageRow at runtime, so replacing the
# row here adds managed media to CF, DSI, and FDC+ selectors without duplicating
# the profile/VTI implementation.
_core.ImageRow = ManagedImageRow

# Last-used timestamps should reflect an actual emulator launch, not merely a
# file being highlighted in the library browser. The launch argv contains only
# media active for the selected profile/controller, so it is the cleanest place
# to update usage without marking hidden/stale selectors. Tracking failure must
# never prevent the emulator from starting.
_original_spawn = _base.TargetSimWindow._spawn


def _spawn_with_library_usage(self, argv, label, emulator):
    if emulator:
        try:
            ImageLibrary(_core.REPO_ROOT).touch_launch_arguments(argv)
        except OSError:
            pass
    return _original_spawn(self, argv, label, emulator)


_base.TargetSimWindow._spawn = _spawn_with_library_usage

# Preserve app.py's public import surface for existing tests and callers.
for _name in dir(_base):
    if not _name.startswith("_"):
        globals()[_name] = getattr(_base, _name)

globals()["ManagedImageRow"] = ManagedImageRow


def main() -> int:
    return _base.main()


if __name__ == "__main__":
    raise SystemExit(main())
