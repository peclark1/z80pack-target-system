from pathlib import Path
import py_compile
import unittest


class GuiSyntaxTests(unittest.TestCase):
    def test_gui_source_compiles(self):
        root = Path(__file__).resolve().parents[1]
        py_compile.compile(str(root / "gui" / "app.py"), doraise=True)


if __name__ == "__main__":
    unittest.main()
