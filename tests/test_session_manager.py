"""
Unit Tests for Session Manager & Roster Isolation
Dii Portal Face Recognition Attendance System
"""

import unittest
import numpy as np
from database.db import (
    init_db,
    add_course,
    register_student,
    enroll_student_in_course,
)
from core.session_manager import SessionManager


class TestSessionManager(unittest.TestCase):
    def setUp(self):
        self.db_path = f"file:memdb_sess_{id(self)}?mode=memory&cache=shared"
        init_db(db_path=self.db_path)
        self.manager = SessionManager()

        # Seed database: 2 courses, 2 students
        add_course("CS401", "Computer Vision", db_path=self.db_path)
        add_course("MATH201", "Linear Algebra", db_path=self.db_path)

        v1 = np.ones(128, dtype=np.float64)
        v2 = np.zeros(128, dtype=np.float64)
        self.s1_id = register_student("U21001", "Bilol", v1, db_path=self.db_path)
        self.s2_id = register_student("U21002", "Ayub", v2, db_path=self.db_path)

        enroll_student_in_course("CS401", self.s1_id, db_path=self.db_path)
        enroll_student_in_course("MATH201", self.s2_id, db_path=self.db_path)

    def test_session_creation_and_roster_isolation(self):
        """Starting a CS401 session should only load Bilol in memory, ignoring Ayub."""
        session = self.manager.start_session("CS401", duration_seconds=600, db_path=self.db_path)

        self.assertTrue(session.is_active)
        self.assertTrue(session.session_id.startswith("SESS_CS401_"))
        self.assertEqual(len(session.roster), 1)

        student_id, student_code, name, _ = session.roster[0]
        self.assertEqual(student_id, self.s1_id)
        self.assertEqual(student_code, "U21001")
        self.assertEqual(name, "Bilol")

    def test_session_attendance_recording(self):
        """Attendance should be recorded and debounced within the session."""
        session = self.manager.start_session("CS401", duration_seconds=600, db_path=self.db_path)

        # First recording succeeds
        marked = self.manager.record_attendance(self.s1_id, confidence_score=0.21, db_path=self.db_path)
        self.assertTrue(marked)

        # Duplicate recording is rejected
        duplicate = self.manager.record_attendance(self.s1_id, confidence_score=0.19, db_path=self.db_path)
        self.assertFalse(duplicate)

        summary = self.manager.get_summary(session.session_id, db_path=self.db_path)
        self.assertEqual(len(summary), 1)
        self.assertEqual(summary[0]["student_code"], "U21001")

    def test_session_expiration(self):
        """A session with duration 0 seconds should expire immediately."""
        session = self.manager.start_session("CS401", duration_seconds=0, db_path=self.db_path)
        self.assertTrue(session.has_expired())
        self.assertEqual(session.remaining_seconds, 0.0)


if __name__ == "__main__":
    unittest.main()
