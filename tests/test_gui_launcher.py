from pathlib import Path
import json
import tempfile
import unittest

from gui.image_info import IBM3740_SIZE
from gui.launcher import (
    FLOPPY_DSI,
    FLOPPY_FDCPLUS,
    FLOPPY_NONE,
    PROFILE_DSI_COMPAT,
    PROFILE_TARGET,
    LaunchConfig,
    load_config,
    save_config,
)
from gui.rom_image import ROM_SIZE


class GuiLauncherTests(unittest.TestCase):
    def test_target_fdcplus_command_suppresses_dsi(self):
        cfg = LaunchConfig(
            profile=PROFILE_TARGET,
            floppy_controller=FLOPPY_FDCPLUS,
            rom_image="/tmp/monitor.bin",
            cf0="/tmp/a.img",
            cf1="/tmp/b.img",
            dsi0="/tmp/dsi.img",
            fdcplus0="/tmp/fdcplus0.img",
            fdcplus1="/tmp/fdcplus1.img",
            ide_trace=True,
            dsi_trace=True,
            dsi_write=True,
            dsi_bootstrap=True,
            fdcplus_trace=True,
            fdcplus_write=True,
            fp_port="02",
            cpu_mhz=8,
        )
        argv = cfg.make_argv(Path("/repo"))
        self.assertEqual(argv[:4], ["make", "-C", "/repo", "run"])
        self.assertIn("ROM_IMAGE=/tmp/monitor.bin", argv)
        self.assertIn("CF0=/tmp/a.img", argv)
        self.assertIn("FDCPLUS0=/tmp/fdcplus0.img", argv)
        self.assertIn("FDCPLUS1=/tmp/fdcplus1.img", argv)
        self.assertIn("DSI0=", argv)
        self.assertNotIn("DSI0=/tmp/dsi.img", argv)
        self.assertIn("DSI_TRACE=0", argv)
        self.assertIn("DSI_WRITE=0", argv)
        self.assertIn("DSI_BOOTSTRAP=0", argv)
        self.assertIn("FDCPLUS_TRACE=1", argv)
        self.assertIn("FDCPLUS_WRITE=1", argv)
        self.assertIn("FP_PORT=02", argv)
        self.assertIn("CPU_MHZ=8", argv)

    def test_target_dsi_command_suppresses_fdcplus(self):
        cfg = LaunchConfig(
            profile=PROFILE_TARGET,
            floppy_controller=FLOPPY_DSI,
            dsi0="/tmp/dsi.img",
            fdcplus0="/tmp/fdcplus.img",
            dsi_trace=True,
            fdcplus_trace=True,
        )
        argv = cfg.make_argv(Path("/repo"))
        self.assertIn("DSI0=/tmp/dsi.img", argv)
        self.assertIn("DSI_TRACE=1", argv)
        self.assertIn("FDCPLUS0=", argv)
        self.assertNotIn("FDCPLUS0=/tmp/fdcplus.img", argv)
        self.assertIn("FDCPLUS_TRACE=0", argv)

    def test_none_controller_suppresses_both_floppy_backends(self):
        cfg = LaunchConfig(
            profile=PROFILE_TARGET,
            floppy_controller=FLOPPY_NONE,
            cf0="/tmp/cf.img",
            dsi0="/tmp/dsi.img",
            fdcplus0="/tmp/fdcplus.img",
        )
        argv = cfg.make_argv(Path("/repo"))
        self.assertIn("DSI0=", argv)
        self.assertIn("FDCPLUS0=", argv)
        self.assertNotIn("DSI0=/tmp/dsi.img", argv)
        self.assertNotIn("FDCPLUS0=/tmp/fdcplus.img", argv)

    def test_target_command_can_explicitly_use_current_rom_and_disable_cf(self):
        cfg = LaunchConfig(
            profile=PROFILE_TARGET,
            floppy_controller=FLOPPY_DSI,
            dsi0="/tmp/dsi.img",
        )
        argv = cfg.make_argv(Path("/repo"))
        self.assertIn("ROM_IMAGE=", argv)
        self.assertIn("CF0=", argv)
        self.assertIn("CF1=", argv)
        self.assertIn("FDCPLUS0=", argv)
        self.assertIn("FDCPLUS3=", argv)

    def test_dsi_compat_forces_dsi_and_no_rom_or_fdcplus_units(self):
        cfg = LaunchConfig(
            profile=PROFILE_DSI_COMPAT,
            floppy_controller=FLOPPY_FDCPLUS,
            rom_image="/tmp/ignored.bin",
            dsi0="/tmp/dsi.img",
            fdcplus0="/tmp/ignored-fdcplus.img",
        )
        argv = cfg.make_argv(Path("/repo"))
        self.assertEqual(argv[:4], ["make", "-C", "/repo", "dsi-compat"])
        self.assertFalse(any(item.startswith("ROM_IMAGE=") for item in argv))
        self.assertNotIn("CF0=", argv)
        self.assertIn("DSI0=/tmp/dsi.img", argv)
        self.assertFalse(any(item.startswith("FDCPLUS0=") for item in argv))

    def test_validation_accepts_fdcplus_only_target(self):
        with tempfile.TemporaryDirectory() as directory:
            disk = Path(directory) / "fdcplus.img"
            with disk.open("wb") as handle:
                handle.truncate(IBM3740_SIZE)
            cfg = LaunchConfig(
                profile=PROFILE_TARGET,
                floppy_controller=FLOPPY_FDCPLUS,
                fdcplus0=str(disk),
            )
            self.assertEqual(cfg.validate(), [])

    def test_validation_ignores_inactive_floppy_paths(self):
        with tempfile.NamedTemporaryFile() as dsi:
            cfg = LaunchConfig(
                profile=PROFILE_TARGET,
                floppy_controller=FLOPPY_DSI,
                dsi0=dsi.name,
                fdcplus0="/path/that/does/not/exist.img",
            )
            self.assertEqual(cfg.validate(), [])

    def test_validation_rejects_wrong_sized_fdcplus_image(self):
        with tempfile.TemporaryDirectory() as directory:
            disk = Path(directory) / "bad-fdcplus.img"
            disk.write_bytes(b"not an IBM 3740 image")
            cfg = LaunchConfig(
                profile=PROFILE_TARGET,
                floppy_controller=FLOPPY_FDCPLUS,
                fdcplus0=str(disk),
            )
            self.assertTrue(any("256,256-byte" in error for error in cfg.validate()))

    def test_validation_rejects_bad_front_panel_value(self):
        with tempfile.NamedTemporaryFile() as disk:
            cfg = LaunchConfig(
                profile=PROFILE_TARGET,
                floppy_controller=FLOPPY_DSI,
                dsi0=disk.name,
                fp_port="XYZ",
            )
            self.assertTrue(any("front-panel" in error for error in cfg.validate()))

    def test_validation_rejects_wrong_sized_rom(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            disk = root / "disk.img"
            disk.write_bytes(b"disk")
            rom = root / "bad.bin"
            rom.write_bytes(b"x" * (ROM_SIZE - 1))
            cfg = LaunchConfig(
                profile=PROFILE_TARGET,
                floppy_controller=FLOPPY_DSI,
                dsi0=str(disk),
                rom_image=str(rom),
            )
            self.assertTrue(any("ROM image" in error for error in cfg.validate()))

    def test_settings_round_trip_but_write_authorizations_reset(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "gui.json"
            cfg = LaunchConfig(
                profile=PROFILE_TARGET,
                floppy_controller=FLOPPY_FDCPLUS,
                rom_image="monitor.bin",
                dsi0="disk.img",
                fdcplus0="fdcplus.img",
                cpu_mhz=6,
                dsi_write=True,
                fdcplus_trace=True,
                fdcplus_write=True,
            )
            save_config(cfg, path)
            loaded = load_config(path)
            self.assertEqual(loaded.profile, PROFILE_TARGET)
            self.assertEqual(loaded.floppy_controller, FLOPPY_FDCPLUS)
            self.assertEqual(loaded.rom_image, "monitor.bin")
            self.assertEqual(loaded.dsi0, "disk.img")
            self.assertEqual(loaded.fdcplus0, "fdcplus.img")
            self.assertEqual(loaded.cpu_mhz, 6)
            self.assertTrue(loaded.fdcplus_trace)
            self.assertFalse(loaded.dsi_write)
            self.assertFalse(loaded.fdcplus_write)
            self.assertFalse(load_config(path).fdcplus_write)

    def test_old_settings_infer_fdcplus_controller(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "gui.json"
            path.write_text(
                json.dumps({"profile": PROFILE_TARGET, "fdcplus0": "disk.img"}),
                encoding="utf-8",
            )
            self.assertEqual(load_config(path).floppy_controller, FLOPPY_FDCPLUS)

    def test_old_settings_infer_dsi_controller(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "gui.json"
            path.write_text(
                json.dumps({"profile": PROFILE_TARGET, "dsi0": "disk.img"}),
                encoding="utf-8",
            )
            self.assertEqual(load_config(path).floppy_controller, FLOPPY_DSI)


if __name__ == "__main__":
    unittest.main()
