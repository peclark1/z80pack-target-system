from pathlib import Path
import tempfile
import unittest

from gui.rom_image import ROM_ORIGIN, ROM_SIZE, binary_to_ihex, inspect_rom, stage_rom


class RomImageTests(unittest.TestCase):
    def test_binary_rom_is_valid_and_stages_at_f000(self):
        image = bytes((index & 0xFF) for index in range(ROM_SIZE))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "monitor.bin"
            source.write_bytes(image)
            info = inspect_rom(source)
            self.assertEqual(info.format, "binary")
            staged = stage_rom(source, root / "run-rom")
            text = staged.read_text(encoding="ascii")
            self.assertTrue(text.startswith(f":10{ROM_ORIGIN:04X}00"))
            self.assertTrue(text.rstrip().endswith(":00000001FF"))

    def test_generated_ihex_is_accepted(self):
        image = bytes([0xA5]) * ROM_SIZE
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "monitor.hex"
            source.write_text(binary_to_ihex(image), encoding="ascii")
            self.assertEqual(inspect_rom(source).format, "Intel HEX")

    def test_wrong_binary_size_is_rejected(self):
        with tempfile.NamedTemporaryFile() as source:
            source.write(b"x" * (ROM_SIZE - 1))
            source.flush()
            with self.assertRaises(ValueError):
                inspect_rom(source.name)

    def test_ihex_outside_f000_ffff_is_rejected(self):
        image = bytes([0x5A]) * ROM_SIZE
        text = binary_to_ihex(image).replace(":10F00000", ":10E00000", 1)
        # The address change invalidates the checksum; either condition is a
        # valid rejection of a ROM that is not our exact F000H-FFFFH image.
        with tempfile.NamedTemporaryFile(mode="w", encoding="ascii") as source:
            source.write(text)
            source.flush()
            with self.assertRaises(ValueError):
                inspect_rom(source.name)


if __name__ == "__main__":
    unittest.main()
