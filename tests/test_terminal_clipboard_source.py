from pathlib import Path
import unittest


class TerminalClipboardSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).resolve().parents[1]
        cls.source = (root / "gui" / "terminal_clipboard.py").read_text(encoding="utf-8")

    def test_shortcuts_use_ctrl_shift_not_plain_ctrl(self):
        self.assertIn('COPY_ACCEL = "<Primary><Shift>c"', self.source)
        self.assertIn('PASTE_ACCEL = "<Primary><Shift>v"', self.source)

    def test_vte_copy_and_paste_operations_are_used(self):
        self.assertIn("copy_clipboard_format(Vte.Format.TEXT)", self.source)
        self.assertIn("paste_clipboard()", self.source)

    def test_context_menu_exposes_copy_and_paste(self):
        self.assertIn('menu.append("Copy", f"win.{COPY_ACTION}")', self.source)
        self.assertIn('menu.append("Paste", f"win.{PASTE_ACTION}")', self.source)

    def test_backspace_and_delete_bindings_are_explicit(self):
        self.assertIn(
            "set_backspace_binding(Vte.EraseBinding.ASCII_BACKSPACE)", self.source
        )
        self.assertIn(
            "set_delete_binding(Vte.EraseBinding.ASCII_DELETE)", self.source
        )


if __name__ == "__main__":
    unittest.main()
