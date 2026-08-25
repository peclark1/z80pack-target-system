from pathlib import Path
import tempfile
import unittest

from gui.launcher import (
    FLOPPY_DSI,
    FLOPPY_FDCPLUS,
    PROFILE_DSI_VTI,
    LaunchConfig,
)


class VtiProfileTests(unittest.TestCase):
    def test_dsi_vti_forces_dsi_and_uses_vti_make_target(self):
        cfg = LaunchConfig(
            profile=PROFILE_DSI_VTI,
            floppy_controller=FLOPPY_FDCPLUS,
            dsi0="/tmp/dsi.img",
            fdcplus0="/tmp/ignored.img",
            dsi_trace=True,
        )
        argv = cfg.make_argv(Path("/repo"))

        self.assertEqual(cfg.active_floppy_controller(), FLOPPY_DSI)
        self.assertEqual(argv[:4], ["make", "-C", "/repo", "dsi-vti"])
        self.assertIn("DSI0=/tmp/dsi.img", argv)
        self.assertIn("DSI_TRACE=1", argv)
        self.assertFalse(any(item.startswith("FDCPLUS0=") for item in argv))
        self.assertFalse(any(item.startswith("ROM_IMAGE=") for item in argv))
        self.assertFalse(any(item.startswith("CF0=") for item in argv))

    def test_dsi_vti_validation_requires_dsi0(self):
        cfg = LaunchConfig(profile=PROFILE_DSI_VTI)
        self.assertTrue(any("DSI0" in error for error in cfg.validate()))

    def test_dsi_vti_validation_accepts_existing_disk(self):
        with tempfile.NamedTemporaryFile() as disk:
            cfg = LaunchConfig(profile=PROFILE_DSI_VTI, dsi0=disk.name)
            self.assertEqual(cfg.validate(), [])


if __name__ == "__main__":
    unittest.main()
