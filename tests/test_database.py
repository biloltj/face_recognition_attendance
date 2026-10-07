"""
Unit Tests for Database Schema & Roster Operations
Dii Portal Face Recognition Attendance System
"""

import unittest
import sqlite3
import numpy as np
from database.db import (
    init_db,
    add_course,
    register_student,
    enroll_student_in_course,
    get_roster_for_course,
    create_session,
    end_session,
    mark_attendance,
    get_session_attendance,
)


class TestDatabase(unittest.TestCase):
    def setUp(self):
        """Set up an isolated in-memory SQLite database for each test."""
        self.db_path = f"file:memdb_{id(self)}?mode=memory&cache=shared"
        init_db(db_path=self.db_path)

    def test_schema_initialization(self):
        """Verify that all 5 tables are created."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = {row[0] for row in cursor.fetchall()}
        expected = {"students", "courses", "course_students", "sessions", "attendance"}
        self.assertTrue(expected.issubset(tables))
        conn.close()

    def test_student_registration_and_vector_roundtrip(self):
        """Verify that a 128-d face embedding vector is stored and retrieved losslessly."""
        test_vector = np.random.rand(128).astype(np.float64)
        s_id = register_student(
            student_code="U211005",
            full_name="Bilol Arzykulov",
            face_encoding=test_vector,
            db_path=self.db_path,
        )
        self.assertGreater(s_id, 0)

        add_course("CS401", "Computer Vision", db_path=self.db_path)
        enroll_student_in_course("CS401", s_id, db_path=self.db_path)

        roster = get_roster_for_course("CS401", db_path=self.db_path)
        self.assertEqual(len(roster), 1)
        retrieved_id, code, name, retrieved_vector = roster[0]
        self.assertEqual(retrieved_id, s_id)
        self.assertEqual(code, "U211005")
        self.assertEqual(name, "Bilol Arzykulov")
        self.assertTrue(np.allclose(test_vector, retrieved_vector))

    def test_course_roster_isolation(self):
        """Verify that students in CS401 are isolated from students in MATH201."""
        vec1 = np.random.rand(128).astype(np.float64)
        vec2 = np.random.rand(128).astype(np.float64)

        s1_id = register_student("U1", "Student One", vec1, db_path=self.db_path)
        s2_id = register_student("U2", "Student Two", vec2, db_path=self.db_path)

        add_course("CS401", "Computer Vision", db_path=self.db_path)
        add_course("MATH201", "Calculus", db_path=self.db_path)

        enroll_student_in_course("CS401", s1_id, db_path=self.db_path)
        enroll_student_in_course("MATH201", s2_id, db_path=self.db_path)

        cs_roster = get_roster_for_course("CS401", db_path=self.db_path)
        math_roster = get_roster_for_course("MATH201", db_path=self.db_path)

        self.assertEqual(len(cs_roster), 1)
        self.assertEqual(cs_roster[0][1], "U1")

        self.assertEqual(len(math_roster), 1)
        self.assertEqual(math_roster[0][1], "U2")

    def test_attendance_logging_and_duplicate_prevention(self):
        """Verify session attendance logging and duplicate prevention."""
        vec = np.random.rand(128).astype(np.float64)
        s_id = register_student("U211005", "Bilol Arzykulov", vec, db_path=self.db_path)
        add_course("CS401", "Computer Vision", db_path=self.db_path)
        enroll_student_in_course("CS401", s_id, db_path=self.db_path)

        session_id = "SESS_CS401_20261007_0900"
        create_session(session_id, "CS401", db_path=self.db_path)

        # First log should succeed
        first_logged = mark_attendance(session_id, s_id, confidence_score=0.28, db_path=self.db_path)
        self.assertTrue(first_logged)

        # Duplicate attempt within same session should return False (debounced)
        second_logged = mark_attendance(session_id, s_id, confidence_score=0.25, db_path=self.db_path)
        self.assertFalse(second_logged)

        records = get_session_attendance(session_id, db_path=self.db_path)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["student_code"], "U211005")
        self.assertEqual(records[0]["status"], "PRESENT")

        end_session(session_id, db_path=self.db_path)


if __name__ == "__main__":
    unittest.main()
