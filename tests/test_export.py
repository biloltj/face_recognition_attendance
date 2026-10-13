# Unit tests for src/export.py (see docs/01_requirements.md: FR-6, docs/04_test_plan.md: IT-5)

from __future__ import annotations

import csv
import sys
import tempfile
import unittest
from pathlib import Path

# Ensure src/ is on sys.path
SRC_DIR = Path(__file__).resolve().parent.parent / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import database
import export


class TestExport(unittest.TestCase):
    def setUp(self):
        """Use isolated temporary database and temporary export path."""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.original_db_path = database.DB_PATH
        database.DB_PATH = Path(self.temp_dir.name) / "test_attendance.db"
        database.init_db()

    def tearDown(self):
        """Restore original database path and cleanup directory."""
        database.DB_PATH = self.original_db_path
        self.temp_dir.cleanup()

    def test_export_empty_attendance_to_csv(self):
        """Verify export on empty database writes headers with Session column."""
        export_path = Path(self.temp_dir.name) / "output.csv"
        result_path = export.export_attendance_csv(export_path)

        self.assertTrue(result_path.exists())
        with open(result_path, "r", newline="", encoding="utf-8") as f:
            reader = list(csv.reader(f))
            self.assertEqual(len(reader), 1)
            self.assertEqual(reader[0], ["Student", "Timestamp", "Session"])

    def test_export_with_records(self):
        """Verify exported CSV matches students, timestamps, and session names."""
        student_id = database.save_student("Bilol Arzykulov", b"fake-encoding")
        database.log_attendance(student_id, session_name="Physics 101")

        export_path = Path(self.temp_dir.name) / "attendance.csv"
        export.export_attendance_csv(export_path)

        with open(export_path, "r", newline="", encoding="utf-8") as f:
            rows = list(csv.reader(f))
            self.assertEqual(len(rows), 2)  # Header + 1 record
            self.assertEqual(rows[0], ["Student", "Timestamp", "Session"])
            self.assertEqual(rows[1][0], "Bilol Arzykulov")
            self.assertEqual(rows[1][2], "Physics 101")

    def test_export_filtered_by_session(self):
        """Verify export with session_name only outputs records for that session."""
        sid1 = database.save_student("Student A", b"encA")
        sid2 = database.save_student("Student B", b"encB")
        database.log_attendance(sid1, session_name="Lab 1")
        database.log_attendance(sid2, session_name="Lab 2")

        export_path = Path(self.temp_dir.name) / "lab1_attendance.csv"
        export.export_attendance_csv(export_path, session_name="Lab 1")

        with open(export_path, "r", newline="", encoding="utf-8") as f:
            rows = list(csv.reader(f))
            self.assertEqual(len(rows), 2)  # Header + 1 record from Lab 1
            self.assertEqual(rows[1][0], "Student A")
            self.assertEqual(rows[1][2], "Lab 1")


if __name__ == "__main__":
    unittest.main()
