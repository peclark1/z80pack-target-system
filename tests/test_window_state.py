from pathlib import Path
import json
import tempfile
import unittest

from gui.window_state import WindowState, load_window_state, save_window_state


class WindowStateTests(unittest.TestCase):
    def test_round_trip(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "window.json"
            expected = WindowState(
                width=1440,
                height=900,
                maximized=True,
                paned_position=520,
                last_rom_directory="/tmp/roms",
                last_cf_directory="/tmp/cf-images",
                last_floppy_directory="/tmp/floppies",
            )
            save_window_state(expected, path)
            self.assertEqual(load_window_state(path), expected)

    def test_bad_values_fall_back_to_safe_defaults(self):
        state = WindowState(
            width=10,
            height=99999,
            paned_position=1,
            last_rom_directory=123,
            last_cf_directory=None,
            last_floppy_directory=456,
        ).validated()
        self.assertEqual(state.width, 1280)
        self.assertEqual(state.height, 800)
        self.assertEqual(state.paned_position, 450)
        self.assertEqual(state.last_rom_directory, "")
        self.assertEqual(state.last_cf_directory, "")
        self.assertEqual(state.last_floppy_directory, "")

    def test_legacy_disk_directory_migrates_to_both_categories(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "window.json"
            path.write_text(
                json.dumps(
                    {
                        "width": 1280,
                        "height": 800,
                        "last_disk_directory": "/tmp/old-disks",
                    }
                ),
                encoding="utf-8",
            )
            state = load_window_state(path)
            self.assertEqual(state.last_cf_directory, "/tmp/old-disks")
            self.assertEqual(state.last_floppy_directory, "/tmp/old-disks")

    def test_missing_file_uses_defaults(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "missing.json"
            self.assertEqual(load_window_state(path), WindowState())


if __name__ == "__main__":
    unittest.main()
