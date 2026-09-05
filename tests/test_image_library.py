from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "gui"))

from image_library import ImageLibrary


class ImageLibraryTests(unittest.TestCase):
    def test_add_master_copies_into_emulator_library_and_tracks_metadata(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = root / "incoming" / "cpm3.img"
            source.parent.mkdir()
            source.write_bytes(b"CPM3" * 128)

            library = ImageLibrary(root)
            master = library.add_master(
                source,
                "cf",
                profile="target",
                description="CP/M 3 IDE master",
            )

            self.assertTrue(master.path.is_file())
            self.assertEqual(master.path.parent, root / "disks" / "library" / "masters" / "cf")
            self.assertEqual(master.path.read_bytes(), source.read_bytes())
            self.assertEqual(master.profile, "target")
            self.assertEqual(master.description, "CP/M 3 IDE master")
            self.assertTrue((root / "disks" / "library" / "library.db").is_file())

    def test_identical_master_is_reused(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            first = root / "one.img"
            second = root / "two.img"
            first.write_bytes(b"same-data")
            second.write_bytes(b"same-data")
            library = ImageLibrary(root)

            a = library.add_master(first, "floppy", description="first")
            b = library.add_master(second, "floppy", profile="dsi-compat")

            self.assertEqual(a.id, b.id)
            self.assertEqual(len(library.list_masters()), 1)
            refreshed = library.get_master(a.id)
            self.assertEqual(refreshed.profile, "dsi-compat")
            self.assertEqual(refreshed.description, "first")

    def test_work_copy_lineage_resolves_from_work_path(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = root / "master.img"
            source.write_bytes(b"master")
            work = root / "build" / "cf0-gui-work.img"
            work.parent.mkdir()
            work.write_bytes(b"working")
            library = ImageLibrary(root)
            master = library.add_master(source, "cf", profile="target")

            record = library.register_work_copy(master.id, work, note="everyday system")

            self.assertEqual(library.master_for_path(work).id, master.id)
            self.assertEqual(library.work_copy_for_path(work).id, record.id)
            self.assertEqual(library.list_work_copies(master.id)[0].note, "everyday system")

    def test_untracked_work_images_excludes_registered_files(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = root / "master.img"
            source.write_bytes(b"master")
            build = root / "build"
            build.mkdir()
            tracked = build / "cf0-gui-work.img"
            untracked = build / "cf0-gui-work-2.img"
            ignored = build / "vti-screen.bin"
            tracked.write_bytes(b"tracked")
            untracked.write_bytes(b"untracked")
            ignored.write_bytes(b"not-an-image")
            library = ImageLibrary(root)
            master = library.add_master(source, "cf")
            library.register_work_copy(master.id, tracked)

            self.assertEqual(library.untracked_work_images("cf"), [untracked.resolve()])
            self.assertEqual(library.untracked_work_images("floppy"), [])

    def test_database_paths_are_portable_inside_repo(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = root / "source.img"
            source.write_bytes(b"portable")
            library = ImageLibrary(root)
            master = library.add_master(source, "cf")

            import sqlite3

            with sqlite3.connect(library.database_path) as db:
                stored = db.execute("SELECT path FROM master_images WHERE id = ?", (master.id,)).fetchone()[0]
            self.assertFalse(Path(stored).is_absolute())
            self.assertTrue(stored.startswith("disks/library/masters/cf/"))


if __name__ == "__main__":
    unittest.main()
