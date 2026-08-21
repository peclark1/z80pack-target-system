from pathlib import Path
import tempfile
import unittest

from gui.window_state import WindowState, load_window_state, save_window_state


class WindowStateTests(unittest.TestCase):
    def test_round_trip(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "window.json"
            expected = WindowState(width=1440, height=900, maximized=True, paned_position=520)
            save_window_state(expected, path)
            self.assertEqual(load_window_state(path), expected)

    def test_bad_values_fall_back_to_safe_defaults(self):
        state = WindowState(width=10, height=99999, paned_position=1).validated()
        self.assertEqual(state.width, 1280)
        self.assertEqual(state.height, 800)
        self.assertEqual(state.paned_position, 450)

    def test_missing_file_uses_defaults(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "missing.json"
            self.assertEqual(load_window_state(path), WindowState())


if __name__ == "__main__":
    unittest.main()
