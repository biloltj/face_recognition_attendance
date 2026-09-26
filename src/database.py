# Data module (Person B, Sprint 1-3)
# Owns: the SQLite schema, storing enrolled students, and logging attendance.
#
# Interface contract with recognition.py / main.py (see docs/05_collaboration_workflow.md):
#   init_db() -> None
#   save_student(name, encoding) -> int
#   get_all_students() -> list[tuple[int, str, bytes]]
#   log_attendance(student_id) -> bool
#   get_attendance_log() -> list[tuple[str, str]]
#
# Schema (see docs/06_technical_specification.md, section 3.3):
#   students(student_id PK, name, face_encoding BLOB)
#   attendance(id PK, student_id FK, timestamp ISO datetime)

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "attendance.db"

# FR-5: don't log the same student twice within this many minutes of their last entry.
DUPLICATE_WINDOW_MINUTES = 10


def _get_connection() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(DB_PATH)


def init_db() -> None:
    """Create the students and attendance tables if they don't already exist."""
    with _get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS students (
                student_id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                face_encoding BLOB NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS attendance (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id INTEGER NOT NULL,
                timestamp TEXT NOT NULL,
                FOREIGN KEY (student_id) REFERENCES students(student_id)
            )
            """
        )


def save_student(name: str, encoding: bytes) -> int:
    """Enroll a new student: store their name and face encoding, return the new student_id."""
    with _get_connection() as conn:
        cursor = conn.execute(
            "INSERT INTO students (name, face_encoding) VALUES (?, ?)",
            (name, encoding),
        )
        return cursor.lastrowid


def get_all_students() -> list[tuple[int, str, bytes]]:
    """Return every enrolled student as (student_id, name, face_encoding), for recognition.py to
    compare a live face against.
    """
    with _get_connection() as conn:
        cursor = conn.execute("SELECT student_id, name, face_encoding FROM students")
        return cursor.fetchall()


def log_attendance(student_id: int) -> bool:
    """Record attendance for student_id at the current time.

    Applies the FR-5 duplicate rule: if this student was already logged within the last
    DUPLICATE_WINDOW_MINUTES, skip the insert and return False. Otherwise insert a new
    attendance row and return True.
    """
    now = datetime.now()
    with _get_connection() as conn:
        cursor = conn.execute(
            "SELECT timestamp FROM attendance WHERE student_id = ? ORDER BY timestamp DESC LIMIT 1",
            (student_id,),
        )
        row = cursor.fetchone()
        if row is not None:
            last_timestamp = datetime.fromisoformat(row[0])
            if now - last_timestamp < timedelta(minutes=DUPLICATE_WINDOW_MINUTES):
                return False

        conn.execute(
            "INSERT INTO attendance (student_id, timestamp) VALUES (?, ?)",
            (student_id, now.isoformat()),
        )
        return True


def get_attendance_log() -> list[tuple[str, str]]:
    """Return the full attendance log as (student_name, timestamp) rows, most recent first — for
    FR-6 (view/export the attendance log).
    """
    with _get_connection() as conn:
        cursor = conn.execute(
            """
            SELECT students.name, attendance.timestamp
            FROM attendance
            JOIN students ON students.student_id = attendance.student_id
            ORDER BY attendance.timestamp DESC
            """
        )
        return cursor.fetchall()


if __name__ == "__main__":
    # Quick manual test: create the tables, enroll a fake student, and log attendance twice in a
    # row to confirm the duplicate rule kicks in. Run with: python src/database.py
    print(f"Initializing database at {DB_PATH} ...")
    init_db()

    student_id = save_student("Test Student", b"fake-encoding-bytes")
    print(f"Saved test student with student_id={student_id}")

    print("Enrolled students:", get_all_students())

    print("First log_attendance call:", log_attendance(student_id), "(expected True)")
    print("Immediate second call:", log_attendance(student_id), "(expected False, duplicate)")
