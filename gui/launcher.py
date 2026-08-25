#!/usr/bin/env python3
"""Pure-Python launch configuration helpers for the GTK front end."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
import json
import shlex
from typing import Any

try:
    from vte_compat import install_feed_child_string_compat
except ImportError:
    # Package import used by host-side tests.
    from .vte_compat import install_feed_child_string_compat

try:
    from rom_image import inspect_rom
except ImportError:
    from .rom_image import inspect_rom

try:
    from image_info import IBM3740_SIZE
except ImportError:
    from .image_info import IBM3740_SIZE

# app.py imports this module after loading VTE. Normalize Ubuntu 24.04's
# byte-array feed_child() binding so the GUI can send Ctrl-] as a Python str.
install_feed_child_string_compat()

PROFILE_TARGET = "target"
PROFILE_DSI_COMPAT = "dsi-compat"
PROFILE_DSI_VTI = "dsi-vti"
PROFILES = {PROFILE_TARGET, PROFILE_DSI_COMPAT, PROFILE_DSI_VTI}

FLOPPY_NONE = "none"
FLOPPY_DSI = "dsi"
FLOPPY_FDCPLUS = "fdcplus"
FLOPPY_CONTROLLERS = {FLOPPY_NONE, FLOPPY_DSI, FLOPPY_FDCPLUS}


@dataclass
class LaunchConfig:
    profile: str = PROFILE_TARGET
    rom_image: str = ""
    cf0: str = ""
    cf1: str = ""
    dsi0: str = ""
    dsi1: str = ""
    fdcplus0: str = ""
    fdcplus1: str = ""
    fdcplus2: str = ""
    fdcplus3: str = ""
    floppy_controller: str = FLOPPY_NONE
    ide_trace: bool = False
    dsi_trace: bool = False
    dsi_write: bool = False
    dsi_bootstrap: bool = False
    fdcplus_trace: bool = False
    fdcplus_write: bool = False
    fp_port: str = "00"
    cpu_mhz: int = 4

    def active_floppy_controller(self) -> str:
        """Return the controller used for this launch.

        Both compatibility profiles are inherently DSI machines. Target mode
        uses the explicit GUI selection and never attaches DSI and FDC+
        together.
        """
        if self.profile in {PROFILE_DSI_COMPAT, PROFILE_DSI_VTI}:
            return FLOPPY_DSI
        return self.floppy_controller

    def validate(self) -> list[str]:
        errors: list[str] = []

        if self.profile not in PROFILES:
            errors.append(f"unknown profile: {self.profile}")

        if self.floppy_controller not in FLOPPY_CONTROLLERS:
            errors.append(f"unknown floppy controller: {self.floppy_controller}")

        try:
            panel = int(self.fp_port, 16)
            if not 0 <= panel <= 0xFF:
                raise ValueError
        except ValueError:
            errors.append("front-panel value must be hexadecimal 00-FF")

        if not 1 <= int(self.cpu_mhz) <= 100:
            errors.append("CPU speed must be between 1 and 100 MHz")

        controller = self.active_floppy_controller()

        if self.profile == PROFILE_TARGET:
            for label, value in (("CF0", self.cf0), ("CF1", self.cf1)):
                if value and not Path(value).expanduser().is_file():
                    errors.append(f"{label} image not found: {value}")

            if self.rom_image:
                try:
                    inspect_rom(self.rom_image)
                except (OSError, ValueError) as exc:
                    errors.append(f"ROM image is not a valid 4K F000H image: {exc}")

        if controller == FLOPPY_DSI:
            for label, value in (("DSI0", self.dsi0), ("DSI1", self.dsi1)):
                if value and not Path(value).expanduser().is_file():
                    errors.append(f"{label} image not found: {value}")

        if controller == FLOPPY_FDCPLUS:
            for number, value in enumerate(
                (self.fdcplus0, self.fdcplus1, self.fdcplus2, self.fdcplus3)
            ):
                if not value:
                    continue
                path = Path(value).expanduser()
                if not path.is_file():
                    errors.append(f"FDCPLUS{number} image not found: {value}")
                    continue
                if path.stat().st_size != IBM3740_SIZE:
                    errors.append(
                        f"FDCPLUS{number} must be a 256,256-byte IBM-3740 77x26x128 image"
                    )

        if self.profile in {PROFILE_DSI_COMPAT, PROFILE_DSI_VTI} and not self.dsi0:
            errors.append("DSI compatibility mode requires a DSI0 image")

        if self.profile == PROFILE_TARGET:
            floppy0 = ""
            if controller == FLOPPY_DSI:
                floppy0 = self.dsi0
            elif controller == FLOPPY_FDCPLUS:
                floppy0 = self.fdcplus0
            if not self.cf0 and not floppy0:
                errors.append("target mode requires CF0 or drive 0 on the selected floppy controller")

        return errors

    def make_argv(self, repo_root: Path) -> list[str]:
        """Return the Makefile command used by the GUI.

        The GUI deliberately drives the same Makefile targets used
        interactively. Only the selected floppy controller is passed through,
        so DSI and FDC+ cannot accidentally be attached at the same time.
        """
        repo_root = repo_root.resolve()
        if self.profile == PROFILE_DSI_VTI:
            target = "dsi-vti"
        elif self.profile == PROFILE_DSI_COMPAT:
            target = "dsi-compat"
        else:
            target = "run"
        argv = ["make", "-C", str(repo_root), target]
        controller = self.active_floppy_controller()

        dsi0 = self.dsi0 if controller == FLOPPY_DSI else ""
        dsi1 = self.dsi1 if controller == FLOPPY_DSI else ""
        fdcplus = (
            (self.fdcplus0, self.fdcplus1, self.fdcplus2, self.fdcplus3)
            if controller == FLOPPY_FDCPLUS
            else ("", "", "", "")
        )

        if self.profile == PROFILE_TARGET:
            # Explicit empty values suppress Makefile defaults when the user
            # intentionally wants a non-IDE target session. An empty ROM_IMAGE
            # means use the pinned/current build/target-monitor.hex.
            argv.extend(
                [
                    f"ROM_IMAGE={self.rom_image}",
                    f"CF0={self.cf0}",
                    f"CF1={self.cf1}",
                    f"FDCPLUS0={fdcplus[0]}",
                    f"FDCPLUS1={fdcplus[1]}",
                    f"FDCPLUS2={fdcplus[2]}",
                    f"FDCPLUS3={fdcplus[3]}",
                ]
            )

        argv.extend(
            [
                f"DSI0={dsi0}",
                f"DSI1={dsi1}",
                f"IDE_TRACE={int(self.ide_trace)}",
                f"DSI_TRACE={int(self.dsi_trace) if controller == FLOPPY_DSI else 0}",
                f"DSI_WRITE={int(self.dsi_write) if controller == FLOPPY_DSI else 0}",
                f"DSI_BOOTSTRAP={int(self.dsi_bootstrap) if controller == FLOPPY_DSI else 0}",
                f"FDCPLUS_TRACE={int(self.fdcplus_trace) if controller == FLOPPY_FDCPLUS else 0}",
                f"FDCPLUS_WRITE={int(self.fdcplus_write) if controller == FLOPPY_FDCPLUS else 0}",
                f"FP_PORT={self.fp_port.upper()}",
                f"CPU_MHZ={int(self.cpu_mhz)}",
            ]
        )
        return argv

    def shell_command(self, repo_root: Path) -> str:
        return shlex.join(self.make_argv(repo_root))

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        # Never persist write authorization. Each application launch must
        # explicitly opt in again before an archival disk image can be changed.
        value["dsi_write"] = False
        value["fdcplus_write"] = False
        return value

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "LaunchConfig":
        fields = cls.__dataclass_fields__
        config = cls(**{k: v for k, v in value.items() if k in fields})

        # Backward compatibility with GUI settings written before the explicit
        # floppy-controller selector existed. Prefer FDC+ if one of its images
        # was selected; otherwise preserve an existing DSI selection.
        if "floppy_controller" not in value:
            if any(getattr(config, f"fdcplus{number}") for number in range(4)):
                config.floppy_controller = FLOPPY_FDCPLUS
            elif config.dsi0 or config.dsi1:
                config.floppy_controller = FLOPPY_DSI
            else:
                config.floppy_controller = FLOPPY_NONE

        config.dsi_write = False
        config.fdcplus_write = False
        return config


def config_path() -> Path:
    return Path.home() / ".config" / "z80pack-target-system" / "gui.json"


def load_config(path: Path | None = None) -> LaunchConfig:
    path = path or config_path()
    try:
        return LaunchConfig.from_dict(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, ValueError, TypeError):
        return LaunchConfig()


def save_config(config: LaunchConfig, path: Path | None = None) -> None:
    path = path or config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(config.to_dict(), indent=2) + "\n", encoding="utf-8")
