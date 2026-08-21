from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

import make_cf_workcopy


class MakeCFWorkcopyTests(unittest.TestCase):
    def test_preserves_source_and_extends_destination(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = root / "compact.img"
            destination = root / "work.img"
            payload = bytes(range(256)) * 4  # 1024 bytes, two 512-byte sectors
            source.write_bytes(payload)

            make_cf_workcopy.make_workcopy(
                source,
                destination,
                logical_size=2048,
            )

            self.assertEqual(source.read_bytes(), payload)
            work = destination.read_bytes()
            self.assertEqual(len(work), 2048)
            self.assertEqual(work[: len(payload)], payload)
            self.assertEqual(work[len(payload) :], bytes(2048 - len(payload)))

    def test_rejects_non_sector_aligned_source(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = root / "bad.img"
            destination = root / "work.img"
            source.write_bytes(b"x" * 513)

            with self.assertRaises(ValueError):
                make_cf_workcopy.make_workcopy(
                    source,
                    destination,
                    logical_size=2048,
                )

    def test_rejects_source_larger_than_logical_capacity(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = root / "large.img"
            destination = root / "work.img"
            source.write_bytes(b"x" * 2560)

            with self.assertRaises(ValueError):
                make_cf_workcopy.make_workcopy(
                    source,
                    destination,
                    logical_size=2048,
                )


if __name__ == "__main__":
    unittest.main()
