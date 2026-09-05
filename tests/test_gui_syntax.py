from pathlib import Path
import py_compile
import unittest


class GuiSyntaxTests(unittest.TestCase):
    def test_gui_source_compiles(self):
        root = Path(__file__).resolve().parents[1]
        for name in (
            "app.py",
            "app_base.py",
            "image_library.py",
            "image_library_dialogs.py",
            "image_library_ui.py",
            "image_library_window.py",
            "managed_image_row.py",
        ):
            with self.subTest(name=name):
                py_compile.compile(str(root / "gui" / name), doraise=True)


if __name__ == "__main__":
    unittest.main()
