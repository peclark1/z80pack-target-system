#!/usr/bin/env python3
"""Image-library-enabled entry point for the IMSAI target-system GUI."""

from __future__ import annotations

import app_base as _base
import core_app as _core
from managed_image_row import ManagedImageRow

# app_base defines the state-preserving GUI and patches core_app.TargetSimWindow.
# Its window constructors resolve core_app.ImageRow at runtime, so replacing the
# row here adds managed media to CF, DSI, and FDC+ selectors without duplicating
# the profile/VTI implementation.
_core.ImageRow = ManagedImageRow

# Preserve app.py's public import surface for existing tests and callers.
for _name in dir(_base):
    if not _name.startswith("_"):
        globals()[_name] = getattr(_base, _name)

globals()["ManagedImageRow"] = ManagedImageRow


def main() -> int:
    return _base.main()


if __name__ == "__main__":
    raise SystemExit(main())
