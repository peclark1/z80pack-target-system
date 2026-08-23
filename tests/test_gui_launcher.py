from pathlib import Path
import tempfile
import unittest

from gui.launcher import (
    PROFILE_DSI_COMPAT,
    PROFILE_TARGET,
    LaunchConfig,
    load_config,
    save_config,
)
from gui.rom_image import ROM_SIZE


class GuiLauncherTests(unittest.TestCase):
    def test_target_command_uses_make_interface(self):
        cfg = LaunchConfig(
            profile=PROFILE_TARGET,
            rom_image="/tmp/monitor.bin",
            cf0="/tmp/a.img",
            cf1="/tmp/b.img",
            dsi0="/tmp/dsi.img",
            fdcplus0="/tmp/fdcplus0.img",
            fdcplus1="/tmp/fdcplus1.img",
            ide_trace=True,
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
        self.assertIn("IDE_TRACE=1", argv)
        self.assertIn("DSI_WRITE=1", argv)
        self.assertIn("DSI_BOOTSTRAP=1", argv)
        self.assertIn("FDCPLUS_TRACE=1", argv)
        self.assertIn("FDCPLUS_WRITE=1", argv)
        self.assertIn("FP_PORT=02", argv)
        self.assertIn("CPU_MHZ=8", argv)

    def test_target_command_can_explicitly_use_current_rom_and_disable_cf(self):
        cfg = LaunchConfig(profile=PROFILE_TARGET, dsi0="/tmp/dsi.img")
        argv = cfg.make_argv(Path("/repo"))
        self.assertIn("ROM_IMAGE=", argv)
        self.assertIn("CF0=", argv)
        self.assertIn("CF1=", argv)
        self.assertIn("FDCPLUS0=", argv)
        self.assertIn("FDCPLUS3=", argv)

    def test_dsi_compat_uses_dsi_compat_target_and_no_rom_or_fdcplus_units(self):
        cfg = LaunchConfig(
            profile=PROFILE_DSI_COMPAT,
            rom_image="/tmp/ignored.bin",
            dsi0="/tmp/dsi.img",
            fdcplus0="/tmp/ignored-fdcplus.img",
        )
        argv = cfg.make_argv(Path("/repo"))
        self.assertEqual(argv[:4], ["make", "-C", "/repo", "dsi-compat"])
        self.assertFalse(any(item.startswith("ROM_IMAGE=") for item in argv))
        self.assertNotIn("CF0=", argv)
        self.assertFalse(any(item.startswith("FDCPLUS0=") for item in argv))

    def test_validation_accepts_fdcplus_only_target(self):
        with tempfile.NamedTemporaryFile() as disk:
            cfg = LaunchConfig(profile=PROFILE_TARGET, fdcplus0=disk.name)
            self.assertFalse(any("requires at least" in error for error in cfg.validate()))

    def test_validation_rejects_bad_front_panel_value(self):
        with tempfile.NamedTemporaryFile() as disk:
            cfg = LaunchConfig(profile=PROFILE_TARGET, dsi0=disk.name, fp_port="XYZ")
            self.assertTrue(any("front-panel" in error for error in cfg.validate()))

    def test_validation_rejects_wrong_sized_rom(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            disk = root / "disk.img"
            disk.write_bytes(b"disk")
            rom = root / "bad.bin"
            rom.write_bytes(b"x" * (ROM_SIZE - 1))
            cfg = LaunchConfig(profile=PROFILE_TARGET, dsi0=str(disk), rom_image=str(rom))
            self.assertTrue(any("ROM image" in error for error in cfg.validate()))

    def test_settings_round_trip_but_write_authorizations_reset(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "gui.json"
            cfg = LaunchConfig(
                profile=PROFILE_TARGET,
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
            self.assertEqual(loaded.rom_image, "monitor.bin")
            self.assertEqual(loaded.dsi0, "disk.img")
            self.assertEqual(loaded.fdcplus0, "fdcplus.img")
            self.assertEqual(loaded.cpu_mhz, 6)
            self.assertTrue(loaded.fdcplus_trace)
            self.assertFalse(loaded.dsi_write)
            self.assertFalse(loaded.fdcplus_write)
            self.assertFalse(load_config(path).fdcplus_write)


if __name__ == "__main__":
    unittest.main()
