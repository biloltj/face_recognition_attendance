# Unit tests for src/enrollment.py (see docs/04_test_plan.md: UT-5, FR-1)

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
import numpy as np

# Ensure src/ is on sys.path
SRC_DIR = Path(__file__).resolve().parent.parent / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import database
import enrollment


class TestEnrollment(unittest.TestCase):
    def setUp(self):
        """Use isolated temporary database for enrollment tests."""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.original_db_path = database.DB_PATH
        database.DB_PATH = Path(self.temp_dir.name) / "test_attendance.db"
        database.init_db()

    def tearDown(self):
        """Restore original database path and cleanup directory."""
        database.DB_PATH = self.original_db_path
        self.temp_dir.cleanup()

    def test_name_validation(self):
        """Verify empty and excessively long names are rejected."""
        self.assertIsNotNone(enrollment._validate_name(""))
        self.assertIsNotNone(enrollment._validate_name("   "))
        self.assertIsNotNone(enrollment._validate_name("A" * 101))
        self.assertIsNone(enrollment._validate_name("Bilol Arzykulov"))

    def test_finish_enrollment_new_student(self):
        """UT-5: Enrolling a new face successfully creates student record."""
        encoding = np.zeros(128, dtype=np.float64).tobytes()
        students = database.get_all_students()

        result = enrollment._finish_enrollment("New Student", encoding, students)
        self.assertIsNotNone(result.student_id)
        self.assertIsNone(result.error)

        # Student should now be in the database
        all_students = database.get_all_students()
        self.assertEqual(len(all_students), 1)
        self.assertEqual(all_students[0][1], "New Student")

    def test_finish_enrollment_duplicate_face_rejected(self):
        """Verify attempting to enroll an already enrolled face is rejected."""
        encoding = np.zeros(128, dtype=np.float64).tobytes()
        # Save first student
        database.save_student("First Student", encoding)
        students = database.get_all_students()

        # Try to enroll another student with the identical face
        result = enrollment._finish_enrollment("Second Student", encoding, students)
        self.assertIsNone(result.student_id)
        self.assertIn("Already enrolled", result.error)


if __name__ == "__main__":
    unittest.main()
