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

# app.py imports this module after loading VTE.  Normalize Ubuntu 24.04's
# byte-array feed_child() binding so the GUI can send Ctrl-] as a Python str.
install_feed_child_string_compat()

PROFILE_TARGET = "target"
PROFILE_DSI_COMPAT = "dsi-compat"


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
    ide_trace: bool = False
    dsi_trace: bool = False
    dsi_write: bool = False
    dsi_bootstrap: bool = False
    fdcplus_trace: bool = False
    fdcplus_write: bool = False
    fp_port: str = "00"
    cpu_mhz: int = 4

    def validate(self) -> list[str]:
        errors: list[str] = []

        if self.profile not in {PROFILE_TARGET, PROFILE_DSI_COMPAT}:
            errors.append(f"unknown profile: {self.profile}")

        try:
            panel = int(self.fp_port, 16)
            if not 0 <= panel <= 0xFF:
                raise ValueError
        except ValueError:
            errors.append("front-panel value must be hexadecimal 00-FF")

        if not 1 <= int(self.cpu_mhz) <= 100:
            errors.append("CPU speed must be between 1 and 100 MHz")

        for label, value in (
            ("CF0", self.cf0),
            ("CF1", self.cf1),
            ("DSI0", self.dsi0),
            ("DSI1", self.dsi1),
            ("FDCPLUS0", self.fdcplus0),
            ("FDCPLUS1", self.fdcplus1),
            ("FDCPLUS2", self.fdcplus2),
            ("FDCPLUS3", self.fdcplus3),
        ):
            if value and not Path(value).expanduser().is_file():
                errors.append(f"{label} image not found: {value}")

        if self.profile == PROFILE_TARGET and self.rom_image:
            try:
                inspect_rom(self.rom_image)
            except (OSError, ValueError) as exc:
                errors.append(f"ROM image is not a valid 4K F000H image: {exc}")

        if self.profile == PROFILE_DSI_COMPAT and not self.dsi0:
            errors.append("DSI compatibility mode requires a DSI0 image")

        if self.profile == PROFILE_TARGET and not self.cf0 and not self.dsi0 and not self.fdcplus0:
            errors.append("target mode requires at least CF0, DSI0, or FDCPLUS0")

        return errors

    def make_argv(self, repo_root: Path) -> list[str]:
        """Return the Makefile command used by the GUI.

        The GUI deliberately drives the same Make targets used interactively so
        command-line and graphical sessions exercise identical emulator setup.
        """
        repo_root = repo_root.resolve()
        target = "dsi-compat" if self.profile == PROFILE_DSI_COMPAT else "run"
        argv = ["make", "-C", str(repo_root), target]

        if self.profile == PROFILE_TARGET:
            # Explicit empty values suppress Makefile defaults when the user
            # intentionally wants a non-IDE target session. An empty ROM_IMAGE
            # means use the pinned/current build/target-monitor.hex.
            argv.extend(
                [
                    f"ROM_IMAGE={self.rom_image}",
                    f"CF0={self.cf0}",
                    f"CF1={self.cf1}",
                    f"FDCPLUS0={self.fdcplus0}",
                    f"FDCPLUS1={self.fdcplus1}",
                    f"FDCPLUS2={self.fdcplus2}",
                    f"FDCPLUS3={self.fdcplus3}",
                ]
            )

        argv.extend(
            [
                f"DSI0={self.dsi0}",
                f"DSI1={self.dsi1}",
                f"IDE_TRACE={int(self.ide_trace)}",
                f"DSI_TRACE={int(self.dsi_trace)}",
                f"DSI_WRITE={int(self.dsi_write)}",
                f"DSI_BOOTSTRAP={int(self.dsi_bootstrap)}",
                f"FDCPLUS_TRACE={int(self.fdcplus_trace)}",
                f"FDCPLUS_WRITE={int(self.fdcplus_write)}",
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
