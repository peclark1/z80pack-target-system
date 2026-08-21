from pathlib import Path
import tempfile
import unittest

from gui.image_info import CF_FULL_SIZE, DSI_SD_SIZE, inspect_image, sha256_file


class GuiImageInfoTests(unittest.TestCase):
    def _image(self, directory: str, name: str, size: int) -> Path:
        path = Path(directory) / name
        with path.open("wb") as handle:
            handle.truncate(size)
        return path

    def test_recognizes_dsi_single_density_image(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self._image(directory, "dsi.img", DSI_SD_SIZE)
            info = inspect_image(path)
            self.assertIn("DSI FDC-1 SD", info.kind)
            self.assertEqual(info.size, 256256)

    def test_recognizes_full_cf_geometry(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self._image(directory, "cf.img", CF_FULL_SIZE)
            info = inspect_image(path)
            self.assertIn("full 8 MiB", info.kind)

    def test_hash_is_deterministic(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "small.img"
            path.write_bytes(b"abc")
            self.assertEqual(
                sha256_file(path),
                "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad",
            )


if __name__ == "__main__":
    unittest.main()
