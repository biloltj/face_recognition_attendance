# Unit tests for src/database.py (see docs/04_test_plan.md: UT-3, UT-4, UT-5)

from __future__ import annotations

import sqlite3
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

# Ensure src/ is on sys.path
SRC_DIR = Path(__file__).resolve().parent.parent / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import database


class TestDatabase(unittest.TestCase):
    def setUp(self):
        """Set up an isolated temporary database for each test."""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.original_db_path = database.DB_PATH
        database.DB_PATH = Path(self.temp_dir.name) / "test_attendance.db"
        database.init_db()

    def tearDown(self):
        """Clean up temporary database and restore original DB_PATH."""
        database.DB_PATH = self.original_db_path
        self.temp_dir.cleanup()

    def test_init_db_creates_tables(self):
        """Verify students and attendance tables are created properly."""
        with database._get_connection() as conn:
            tables = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            ).fetchall()
            table_names = [t[0] for t in tables]
            self.assertIn("students", table_names)
            self.assertIn("attendance", table_names)

    def test_ut5_save_and_get_students(self):
        """UT-5: Enrolling/saving a student produces a database row with name and face encoding."""
        fake_encoding = b"mock-128-byte-encoding-data"
        student_id = database.save_student("Bilol Arzykulov", fake_encoding)
        self.assertIsInstance(student_id, int)
        self.assertGreater(student_id, 0)

        students = database.get_all_students()
        self.assertEqual(len(students), 1)
        self.assertEqual(students[0][0], student_id)
        self.assertEqual(students[0][1], "Bilol Arzykulov")
        self.assertEqual(students[0][2], fake_encoding)

    def test_ut3_duplicate_prevention_within_window(self):
        """UT-3: Logging the same student twice within duplicate window skips second insert."""
        fake_encoding = b"test-encoding"
        student_id = database.save_student("Ayub Timurov", fake_encoding)

        # First attendance entry should succeed
        first_result = database.log_attendance(student_id)
        self.assertTrue(first_result)

        # Immediate second entry within window must be rejected
        second_result = database.log_attendance(student_id)
        self.assertFalse(second_result)

        # Database should still contain exactly 1 log record
        log = database.get_attendance_log()
        self.assertEqual(len(log), 1)
        self.assertEqual(log[0][0], "Ayub Timurov")

    def test_ut4_attendance_allowed_after_window(self):
        """UT-4: Logging the same student when previous entry is past the window succeeds."""
        fake_encoding = b"test-encoding"
        student_id = database.save_student("Hikmat", fake_encoding)

        # Insert a backdated attendance row older than DUPLICATE_WINDOW_MINUTES
        past_time = datetime.now() - timedelta(minutes=database.DUPLICATE_WINDOW_MINUTES + 5)
        with database._get_connection() as conn:
            conn.execute(
                "INSERT INTO attendance (student_id, timestamp) VALUES (?, ?)",
                (student_id, past_time.isoformat()),
            )

        # New attendance entry should now be accepted
        new_result = database.log_attendance(student_id)
        self.assertTrue(new_result)

        # Database should now have 2 attendance records
        log = database.get_attendance_log()
        self.assertEqual(len(log), 2)
        self.assertEqual(log[0][0], "Hikmat")
        self.assertEqual(log[1][0], "Hikmat")

    def test_get_attendance_log_empty(self):
        """Verify get_attendance_log returns an empty list when no attendance logged."""
        self.assertEqual(database.get_attendance_log(), [])


class TestCoursesAndSessions(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.original_db_path = database.DB_PATH
        database.DB_PATH = Path(self.temp_dir.name) / "test_attendance.db"
        database.init_db()

        self.course_id = database.create_course("MATH101", "Calculus I")
        self.room_id = database.create_classroom("Room 204", "0")
        self.alice = database.save_student("Alice", b"enc-a", university_id="S001")
        self.bob = database.save_student("Bob", b"enc-b", university_id="S002")
        database.add_student_to_course(self.course_id, self.alice)

    def tearDown(self):
        database.DB_PATH = self.original_db_path
        self.temp_dir.cleanup()

    def test_init_db_creates_new_tables(self):
        with database._get_connection() as conn:
            tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertTrue({"courses", "course_students", "classrooms", "sessions"} <= tables)

    def test_init_db_is_idempotent(self):
        database.init_db()
        self.assertEqual(len(database.get_all_courses()), 1)

    def test_university_id_must_be_unique(self):
        with self.assertRaises(sqlite3.IntegrityError):
            database.save_student("Alice Copy", b"enc", university_id="S001")
        # Students enrolled without a portal ID (webcam enrollment) don't clash with each other.
        database.save_student("No ID 1", b"enc")
        database.save_student("No ID 2", b"enc")

    def test_course_code_must_be_unique(self):
        with self.assertRaises(sqlite3.IntegrityError):
            database.create_course("MATH101", "Duplicate")

    def test_course_roster_only_contains_enrolled_students(self):
        self.assertFalse(database.add_student_to_course(self.course_id, self.alice))  # already enrolled
        roster = database.get_course_students(self.course_id)
        self.assertEqual(roster, [(self.alice, "Alice", b"enc-a")])

    def test_one_record_per_student_per_session(self):
        session_id = database.create_session(self.course_id, self.room_id)
        self.assertTrue(database.log_session_attendance(session_id, self.alice, 0.42))
        self.assertFalse(database.log_session_attendance(session_id, self.alice, 0.40))

        rows = database.get_session_attendance(session_id)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][0], self.alice)
        self.assertAlmostEqual(rows[0][3], 0.42)

    def test_same_student_can_attend_next_session(self):
        first = database.create_session(self.course_id, self.room_id)
        database.log_session_attendance(first, self.alice)
        database.close_session(first)

        second = database.create_session(self.course_id, self.room_id)
        self.assertNotEqual(first, second)
        self.assertTrue(database.log_session_attendance(second, self.alice))

    def test_closed_session_rejects_attendance(self):
        session_id = database.create_session(self.course_id, self.room_id)
        self.assertTrue(database.close_session(session_id))
        self.assertFalse(database.close_session(session_id))  # already closed

        session = database.get_session(session_id)
        self.assertEqual(session[5], "closed")
        self.assertIsNotNone(session[4])
        self.assertFalse(database.log_session_attendance(session_id, self.alice))

    def test_classroom_cannot_have_two_open_sessions(self):
        database.create_session(self.course_id, self.room_id)
        other_course = database.create_course("PHYS101", "Physics I")
        with self.assertRaises(ValueError):
            database.create_session(other_course, self.room_id)

    def test_remove_student_from_course(self):
        self.assertTrue(database.remove_student_from_course(self.course_id, self.alice))
        self.assertFalse(database.remove_student_from_course(self.course_id, self.alice))
        self.assertEqual(database.get_course_students(self.course_id), [])

    def test_close_all_open_sessions(self):
        open_one = database.create_session(self.course_id, self.room_id)
        closed_one = database.create_session(self.course_id)
        database.close_session(closed_one)

        self.assertEqual(database.close_all_open_sessions(), 1)
        self.assertEqual(database.get_session(open_one)[5], "closed")

    def test_session_results_list_present_and_absent(self):
        database.add_student_to_course(self.course_id, self.bob)
        session_id = database.create_session(self.course_id, self.room_id)
        database.log_session_attendance(session_id, self.bob)

        results = database.get_session_results(session_id)
        self.assertEqual([(r[1], r[2]) for r in results], [("Alice", False), ("Bob", True)])
        self.assertIsNone(results[0][3])  # absent: no time
        self.assertIsNotNone(results[1][3])

    def test_session_roster_is_fixed_when_session_starts(self):
        session_id = database.create_session(self.course_id, self.room_id)
        database.close_session(session_id)
        # Bob joins the course after the lesson: he must not show up as absent from it.
        database.add_student_to_course(self.course_id, self.bob)
        names = [r[1] for r in database.get_session_results(session_id)]
        self.assertEqual(names, ["Alice"])

    def test_get_sessions_counts_and_course_filter(self):
        session_id = database.create_session(self.course_id, self.room_id)
        database.log_session_attendance(session_id, self.alice)
        other_course = database.create_course("PHYS101", "Physics I")
        database.create_session(other_course)

        self.assertEqual(len(database.get_sessions()), 2)
        rows = database.get_sessions(self.course_id)
        self.assertEqual(len(rows), 1)
        sid, code, _, _, _, status, present, expected = rows[0]
        self.assertEqual((sid, code, status, present, expected), (session_id, "MATH101", "open", 1, 1))

    def test_delete_student_with_session_history(self):
        session_id = database.create_session(self.course_id, self.room_id)
        database.log_session_attendance(session_id, self.alice)
        self.assertTrue(database.delete_student(self.alice))
        self.assertEqual(database.get_session_results(session_id), [])

    def test_delete_student_removes_enrollments(self):
        database.delete_student(self.alice)
        self.assertEqual(database.get_course_students(self.course_id), [])


class TestMigration(unittest.TestCase):
    def test_old_database_is_upgraded_without_losing_data(self):
        """A database created by the previous schema gains the new columns and keeps its rows."""
        with tempfile.TemporaryDirectory() as temp_dir:
            original_db_path = database.DB_PATH
            database.DB_PATH = Path(temp_dir) / "old.db"
            try:
                with database._get_connection() as conn:
                    conn.execute(
                        "CREATE TABLE students (student_id INTEGER PRIMARY KEY AUTOINCREMENT, "
                        "name TEXT NOT NULL, face_encoding BLOB NOT NULL)"
                    )
                    conn.execute(
                        "CREATE TABLE attendance (id INTEGER PRIMARY KEY AUTOINCREMENT, "
                        "student_id INTEGER NOT NULL, timestamp TEXT NOT NULL, "
                        "session_name TEXT DEFAULT 'General')"
                    )
                    conn.execute("INSERT INTO students (name, face_encoding) VALUES ('Old', x'00')")
                    conn.execute(
                        "INSERT INTO attendance (student_id, timestamp) VALUES (1, '2026-10-01T09:00:00')"
                    )

                database.init_db()

                self.assertEqual(database.get_all_students(), [(1, "Old", b"\x00")])
                self.assertEqual(len(database.get_attendance_log()), 1)
                with database._get_connection() as conn:
                    attendance_columns = database._column_names(conn, "attendance")
                    student_columns = database._column_names(conn, "students")
                self.assertIn("session_id", attendance_columns)
                self.assertIn("confidence", attendance_columns)
                self.assertIn("university_id", student_columns)
            finally:
                database.DB_PATH = original_db_path

    def test_existing_sessions_get_a_roster_when_upgraded(self):
        """Sessions recorded before session_students existed are given the course roster once."""
        with tempfile.TemporaryDirectory() as temp_dir:
            original_db_path = database.DB_PATH
            database.DB_PATH = Path(temp_dir) / "old.db"
            try:
                database.init_db()
                course_id = database.create_course("MATH101", "Calculus I")
                alice = database.save_student("Alice", b"a")
                database.add_student_to_course(course_id, alice)
                session_id = database.create_session(course_id)
                with database._get_connection() as conn:
                    conn.execute("DROP TABLE session_students")  # simulate the previous version

                database.init_db()
                self.assertEqual([r[1] for r in database.get_session_results(session_id)], ["Alice"])
            finally:
                database.DB_PATH = original_db_path


if __name__ == "__main__":
    unittest.main()
