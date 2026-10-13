# Unit tests for src/portal_import.py. Real face detection is replaced by fake encodings, so these
# test the import rules (grouping, linking, skipping) without needing photos of real people.

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np

SRC_DIR = Path(__file__).resolve().parent.parent / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import database
import portal_import


def fake_face(seed: int, shift: float = 0.0) -> bytes:
    """A deterministic 'face' per seed; a small shift makes another photo of the same person."""
    v = np.random.RandomState(seed).randn(128)
    v = v / np.linalg.norm(v)
    v[0] += shift
    return v.astype(np.float64).tobytes()


class TestNameParsing(unittest.TestCase):
    def test_extra_photo_suffixes_map_to_the_same_name(self):
        for file_name in ["Kabirova Omina.jpg", "Kabirova Omina(1).jpg", "Kabirova Omina (2).png",
                          "Kabirova Omina NEW.jpg", "Kabirova Omina - Copy.jpg"]:
            self.assertEqual(portal_import.name_from_filename(Path(file_name)), "Kabirova Omina")

    def test_ordinary_names_are_kept(self):
        self.assertEqual(portal_import.name_from_filename(Path("Haq  Zain ul.jpg")), "Haq Zain ul")


class TestImportFolder(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        root = Path(self.temp_dir.name)
        self.original_db_path = database.DB_PATH
        database.DB_PATH = root / "test.db"
        database.init_db()

        self.photos = root / "photos"
        self.photos.mkdir()
        # file name -> the fake face "in" that photo (None = no face found)
        self.faces = {
            "Timurov Ayub.jpg": fake_face(1),
            "Kabirova Omina.jpg": fake_face(2),
            "Kabirova Omina(1).jpg": fake_face(2, shift=0.05),
            "Blurry Person.jpg": None,
        }
        for file_name in self.faces:
            (self.photos / file_name).write_bytes(b"not really an image")

        # Ayub was enrolled from the webcam earlier, under another spelling.
        self.ayub = database.save_student("Ayub Timurov", fake_face(1, shift=0.1))

        def fake_encode(image):
            face = self.faces[self._current]
            return (face, None) if face is not None else (None, "no face found")

        def fake_load(path):
            self._current = path.name
            return object()

        patches = [
            mock.patch.object(portal_import, "load_image", side_effect=fake_load),
            mock.patch.object(portal_import, "encode_photo", side_effect=fake_encode),
            mock.patch("builtins.print"),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def tearDown(self):
        database.DB_PATH = self.original_db_path
        self.temp_dir.cleanup()

    def test_dry_run_changes_nothing(self):
        report = portal_import.import_folder(self.photos, dry_run=True)
        self.assertEqual(len(report.created), 1)
        self.assertEqual(len(report.linked), 1)
        self.assertEqual([n for _, n, _ in database.get_all_students()], ["Ayub Timurov"])

    def test_import_links_creates_groups_and_reports(self):
        report = portal_import.import_folder(self.photos)

        students = {name: sid for sid, name, _ in database.get_all_students()}
        self.assertEqual(set(students), {"Timurov Ayub", "Kabirova Omina"})
        self.assertEqual(students["Timurov Ayub"], self.ayub)  # linked, not duplicated

        faces_per_student = {}
        for sid, _, _ in database.get_all_face_encodings():
            faces_per_student[sid] = faces_per_student.get(sid, 0) + 1
        self.assertEqual(faces_per_student[self.ayub], 2)  # webcam face + portal face
        self.assertEqual(faces_per_student[students["Kabirova Omina"]], 2)  # both of her photos

        self.assertEqual(report.problems, ["Blurry Person.jpg: no face found"])

    def test_rerun_skips_imported_photos(self):
        portal_import.import_folder(self.photos)
        report = portal_import.import_folder(self.photos)
        self.assertEqual(report.already_imported, 3)
        self.assertEqual(report.created, [])
        self.assertEqual(len(database.get_all_students()), 2)

    def test_course_option_adds_everyone(self):
        course_id = database.create_course("CS 301", "Databases")
        portal_import.import_folder(self.photos, course_code="cs 301")
        self.assertEqual(len(database.get_course_students(course_id)), 2)


if __name__ == "__main__":
    unittest.main()
