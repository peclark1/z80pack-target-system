import tempfile
import unittest
from pathlib import Path

from tools.bin2ihex import ROM_ORIGIN, ROM_SIZE, convert, record


class Bin2IHexTests(unittest.TestCase):
    def test_known_record_checksum(self):
        self.assertEqual(
            record(0xF000, 0x00, bytes(16)),
            ":10F000000000000000000000000000000000000000",
        )
        self.assertEqual(record(0x0000, 0x01, b""), ":00000001FF")

    def test_convert_maps_exactly_4k_at_f000(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            source = tmpdir / "monitor.bin"
            output = tmpdir / "monitor.hex"
            source.write_bytes(bytes((i & 0xFF) for i in range(ROM_SIZE)))

            convert(source, output)
            lines = output.read_text(encoding="ascii").splitlines()

            self.assertEqual(len(lines), (ROM_SIZE // 16) + 1)
            self.assertTrue(lines[0].startswith(f":10{ROM_ORIGIN:04X}00"))
            self.assertTrue(lines[-2].startswith(":10FFF000"))
            self.assertEqual(lines[-1], ":00000001FF")

    def test_rejects_physical_8k_programmer_image(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            source = tmpdir / "wrong.bin"
            output = tmpdir / "wrong.hex"
            source.write_bytes(bytes(8192))

            with self.assertRaises(SystemExit):
                convert(source, output)


if __name__ == "__main__":
    unittest.main()
