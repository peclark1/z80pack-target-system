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


class GuiLauncherTests(unittest.TestCase):
    def test_target_command_uses_make_interface(self):
        cfg = LaunchConfig(
            profile=PROFILE_TARGET,
            cf0="/tmp/a.img",
            cf1="/tmp/b.img",
            dsi0="/tmp/dsi.img",
            ide_trace=True,
            dsi_write=True,
            dsi_bootstrap=True,
            fp_port="02",
            cpu_mhz=8,
        )
        argv = cfg.make_argv(Path("/repo"))
        self.assertEqual(argv[:4], ["make", "-C", "/repo", "run"])
        self.assertIn("CF0=/tmp/a.img", argv)
        self.assertIn("IDE_TRACE=1", argv)
        self.assertIn("DSI_WRITE=1", argv)
        self.assertIn("DSI_BOOTSTRAP=1", argv)
        self.assertIn("FP_PORT=02", argv)
        self.assertIn("CPU_MHZ=8", argv)

    def test_target_command_can_explicitly_disable_cf(self):
        cfg = LaunchConfig(profile=PROFILE_TARGET, dsi0="/tmp/dsi.img")
        argv = cfg.make_argv(Path("/repo"))
        self.assertIn("CF0=", argv)
        self.assertIn("CF1=", argv)

    def test_dsi_compat_uses_dsi_compat_target(self):
        cfg = LaunchConfig(profile=PROFILE_DSI_COMPAT, dsi0="/tmp/dsi.img")
        argv = cfg.make_argv(Path("/repo"))
        self.assertEqual(argv[:4], ["make", "-C", "/repo", "dsi-compat"])
        self.assertNotIn("CF0=", argv)

    def test_validation_rejects_bad_front_panel_value(self):
        with tempfile.NamedTemporaryFile() as disk:
            cfg = LaunchConfig(profile=PROFILE_TARGET, dsi0=disk.name, fp_port="XYZ")
            self.assertTrue(any("front-panel" in error for error in cfg.validate()))

    def test_settings_round_trip(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "gui.json"
            cfg = LaunchConfig(profile=PROFILE_DSI_COMPAT, dsi0="disk.img", cpu_mhz=6)
            save_config(cfg, path)
            loaded = load_config(path)
            self.assertEqual(loaded.profile, PROFILE_DSI_COMPAT)
            self.assertEqual(loaded.dsi0, "disk.img")
            self.assertEqual(loaded.cpu_mhz, 6)


if __name__ == "__main__":
    unittest.main()
