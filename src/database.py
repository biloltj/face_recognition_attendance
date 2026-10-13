# Data module (Person B, Sprint 1-3)
# Owns: the SQLite schema, storing enrolled students, and logging attendance.
#
# Interface contract with recognition.py / main.py (see docs/05_collaboration_workflow.md):
#   init_db() -> None
#   save_student(name, encoding) -> int
#   get_all_students() -> list[tuple[int, str, bytes]]
#   delete_student(student_id) -> bool
#   log_attendance(student_id, session_name) -> bool
#   get_attendance_log(session_name) -> list[tuple[str, str, str]]
#   get_all_sessions() -> list[str]
#
# Course/session interface (plan.md, Week 1):
#   create_course(code, name) -> int
#   get_all_courses() -> list[tuple[int, str, str]]
#   add_student_to_course(course_id, student_id) -> bool
#   remove_student_from_course(course_id, student_id) -> bool
#   get_course_students(course_id) -> list[tuple[int, str, bytes]]
#   create_classroom(name, camera_source) -> int
#   create_session(course_id, classroom_id) -> int
#   close_session(session_id) -> bool
#   close_all_open_sessions() -> int
#   get_session(session_id) -> tuple | None
#   log_session_attendance(session_id, student_id, confidence) -> bool
#   get_session_attendance(session_id) -> list[tuple[int, str, str, float | None]]
#   get_sessions(course_id) -> list[tuple[int, str, str, str, str | None, str, int, int]]
#   get_session_results(session_id) -> list[tuple[int, str, bool, str | None, float | None]]
#
# Schema:
#   students(student_id PK, name, face_encoding BLOB, university_id TEXT UNIQUE)
#   courses(course_id PK, code UNIQUE, name)
#   course_students(course_id FK, student_id FK) PK(course_id, student_id)
#   classrooms(classroom_id PK, name UNIQUE, camera_source)
#   sessions(session_id PK, course_id FK, classroom_id FK, started_at, ended_at, status 'open'|'closed')
#   session_students(session_id FK, student_id FK) PK(session_id, student_id)  -- roster at session start
#   attendance(id PK, student_id FK, timestamp ISO datetime, session_name TEXT,
#              session_id FK, confidence REAL)  UNIQUE(session_id, student_id)
#
# The legacy session_name column is kept so the current GUI/webapp keep working until
# recognition.py is moved over to sessions (plan.md, Week 2). New code should use session_id.

from __future__ import annotations

import sqlite3
from collections.abc import Generator
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "attendance.db"

# FR-5: don't log the same student twice within this many minutes of their last entry in General mode.
DUPLICATE_WINDOW_MINUTES = 10


@contextmanager
def _get_connection() -> Generator[sqlite3.Connection, None, None]:
    """Open a connection that commits on success, rolls back on error, and is always closed.
    (A bare sqlite3 connection used in `with` only commits; leaving it open locks the file on Windows.)
    """
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        with conn:
            yield conn
    finally:
        conn.close()


def _column_names(conn: sqlite3.Connection, table: str) -> list[str]:
    return [col[1] for col in conn.execute(f"PRAGMA table_info({table})").fetchall()]


def init_db() -> None:
    """Create all tables if they don't already exist, and migrate older databases in place."""
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
                session_name TEXT DEFAULT 'General',
                FOREIGN KEY (student_id) REFERENCES students(student_id)
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS courses (
                course_id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT NOT NULL UNIQUE,
                name TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS course_students (
                course_id INTEGER NOT NULL,
                student_id INTEGER NOT NULL,
                PRIMARY KEY (course_id, student_id),
                FOREIGN KEY (course_id) REFERENCES courses(course_id) ON DELETE CASCADE,
                FOREIGN KEY (student_id) REFERENCES students(student_id) ON DELETE CASCADE
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS classrooms (
                classroom_id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                camera_source TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                session_id INTEGER PRIMARY KEY AUTOINCREMENT,
                course_id INTEGER NOT NULL,
                classroom_id INTEGER,
                started_at TEXT NOT NULL,
                ended_at TEXT,
                status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'closed')),
                FOREIGN KEY (course_id) REFERENCES courses(course_id),
                FOREIGN KEY (classroom_id) REFERENCES classrooms(classroom_id)
            )
            """
        )

        # Who was expected at each session, copied from the course roster when the session starts,
        # so later roster changes don't rewrite who was absent from past lessons.
        had_session_students = "session_students" in {
            row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS session_students (
                session_id INTEGER NOT NULL,
                student_id INTEGER NOT NULL,
                PRIMARY KEY (session_id, student_id),
                FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE CASCADE,
                FOREIGN KEY (student_id) REFERENCES students(student_id) ON DELETE CASCADE
            )
            """
        )
        if not had_session_students:
            # Sessions recorded before this table existed: the current course roster is the best
            # record of who was expected.
            conn.execute(
                """
                INSERT OR IGNORE INTO session_students (session_id, student_id)
                SELECT sessions.session_id, course_students.student_id
                FROM sessions JOIN course_students ON course_students.course_id = sessions.course_id
                """
            )

        # Migrations for databases created by earlier versions: add new columns in place so
        # existing students and attendance rows are kept.
        attendance_columns = _column_names(conn, "attendance")
        if "session_name" not in attendance_columns:
            conn.execute("ALTER TABLE attendance ADD COLUMN session_name TEXT DEFAULT 'General'")
        if "session_id" not in attendance_columns:
            conn.execute("ALTER TABLE attendance ADD COLUMN session_id INTEGER REFERENCES sessions(session_id)")
        if "confidence" not in attendance_columns:
            conn.execute("ALTER TABLE attendance ADD COLUMN confidence REAL")
        if "university_id" not in _column_names(conn, "students"):
            # SQLite can't ADD COLUMN ... UNIQUE, so uniqueness comes from the index below.
            conn.execute("ALTER TABLE students ADD COLUMN university_id TEXT")

        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_students_university_id "
            "ON students(university_id) WHERE university_id IS NOT NULL"
        )
        # One attendance record per student per session. Legacy rows (session_id NULL) are exempt.
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_attendance_session_student "
            "ON attendance(session_id, student_id) WHERE session_id IS NOT NULL"
        )


def save_student(name: str, encoding: bytes, university_id: str | None = None) -> int:
    """Enroll a new student: store their name, face encoding and (optional) university ID from the
    portal, return the new student_id. Raises sqlite3.IntegrityError if university_id is already used.
    """
    with _get_connection() as conn:
        cursor = conn.execute(
            "INSERT INTO students (name, face_encoding, university_id) VALUES (?, ?, ?)",
            (name, encoding, university_id),
        )
        return cursor.lastrowid


def delete_student(student_id: int) -> bool:
    """Remove a student, their course enrollments and their attendance history from the database."""
    with _get_connection() as conn:
        conn.execute("DELETE FROM attendance WHERE student_id = ?", (student_id,))
        conn.execute("DELETE FROM course_students WHERE student_id = ?", (student_id,))
        conn.execute("DELETE FROM session_students WHERE student_id = ?", (student_id,))
        cursor = conn.execute("DELETE FROM students WHERE student_id = ?", (student_id,))
        return cursor.rowcount > 0


def get_all_students() -> list[tuple[int, str, bytes]]:
    """Return every enrolled student as (student_id, name, face_encoding), for recognition.py to
    compare a live face against.
    """
    with _get_connection() as conn:
        cursor = conn.execute("SELECT student_id, name, face_encoding FROM students ORDER BY student_id ASC")
        return cursor.fetchall()


def log_attendance(student_id: int, session_name: str = "General") -> bool:
    """Record attendance for student_id at the current time within a session.

    Session duplicate rules:
    - If session_name is a specific lecture/class (not 'General'), prevents logging the same student
      more than once in that session.
    - If session_name is 'General', applies the sliding window (DUPLICATE_WINDOW_MINUTES).
    """
    session_name = (session_name or "General").strip()
    now = datetime.now()
    with _get_connection() as conn:
        cursor = conn.execute(
            """
            SELECT timestamp FROM attendance
            WHERE student_id = ? AND session_name = ?
            ORDER BY timestamp DESC LIMIT 1
            """,
            (student_id, session_name),
        )
        row = cursor.fetchone()
        if row is not None:
            # If in a specific named session, student can only be logged once
            if session_name != "General":
                return False

            # If in General mode, check sliding duplicate window
            last_timestamp = datetime.fromisoformat(row[0])
            if now - last_timestamp < timedelta(minutes=DUPLICATE_WINDOW_MINUTES):
                return False

        conn.execute(
            "INSERT INTO attendance (student_id, timestamp, session_name) VALUES (?, ?, ?)",
            (student_id, now.isoformat(), session_name),
        )
        return True


def get_attendance_log(session_name: str | None = None) -> list[tuple[str, str, str]]:
    """Return the attendance log as (student_name, timestamp, session_name) rows, most recent first.
    If session_name is given, filters records to that specific session.
    """
    with _get_connection() as conn:
        if session_name:
            cursor = conn.execute(
                """
                SELECT students.name, attendance.timestamp, attendance.session_name
                FROM attendance
                JOIN students ON students.student_id = attendance.student_id
                WHERE attendance.session_name = ?
                ORDER BY attendance.timestamp DESC
                """,
                (session_name,),
            )
        else:
            cursor = conn.execute(
                """
                SELECT students.name, attendance.timestamp, COALESCE(attendance.session_name, 'General')
                FROM attendance
                JOIN students ON students.student_id = attendance.student_id
                ORDER BY attendance.timestamp DESC
                """
            )
        return cursor.fetchall()


def get_all_sessions() -> list[str]:
    """Return all distinct session names recorded in the database, newest first."""
    with _get_connection() as conn:
        cursor = conn.execute(
            """
            SELECT DISTINCT session_name FROM attendance
            WHERE session_name IS NOT NULL AND session_name != ''
            ORDER BY timestamp DESC
            """
        )
        sessions = [row[0] for row in cursor.fetchall()]
        if "General" not in sessions:
            sessions.append("General")
        return sessions


def create_course(code: str, name: str) -> int:
    """Create a course (e.g. code 'MATH101', name 'Calculus I') and return its course_id.
    Raises sqlite3.IntegrityError if the code already exists.
    """
    with _get_connection() as conn:
        cursor = conn.execute(
            "INSERT INTO courses (code, name) VALUES (?, ?)",
            (code.strip(), name.strip()),
        )
        return cursor.lastrowid


def get_all_courses() -> list[tuple[int, str, str]]:
    """Return every course as (course_id, code, name), ordered by code."""
    with _get_connection() as conn:
        cursor = conn.execute("SELECT course_id, code, name FROM courses ORDER BY code ASC")
        return cursor.fetchall()


def add_student_to_course(course_id: int, student_id: int) -> bool:
    """Enroll a student in a course. Returns False if they were already enrolled."""
    with _get_connection() as conn:
        cursor = conn.execute(
            "INSERT OR IGNORE INTO course_students (course_id, student_id) VALUES (?, ?)",
            (course_id, student_id),
        )
        return cursor.rowcount > 0


def remove_student_from_course(course_id: int, student_id: int) -> bool:
    """Take a student off a course roster. Their past attendance records are kept."""
    with _get_connection() as conn:
        cursor = conn.execute(
            "DELETE FROM course_students WHERE course_id = ? AND student_id = ?",
            (course_id, student_id),
        )
        return cursor.rowcount > 0


def get_course_students(course_id: int) -> list[tuple[int, str, bytes]]:
    """Return the course roster as (student_id, name, face_encoding), the same shape as
    get_all_students(), so recognition can match faces against this course only.
    """
    with _get_connection() as conn:
        cursor = conn.execute(
            """
            SELECT students.student_id, students.name, students.face_encoding
            FROM course_students
            JOIN students ON students.student_id = course_students.student_id
            WHERE course_students.course_id = ?
            ORDER BY students.student_id ASC
            """,
            (course_id,),
        )
        return cursor.fetchall()


def create_classroom(name: str, camera_source: str | None = None) -> int:
    """Register a classroom and the camera that covers it (a device index like '0' or a stream URL)."""
    with _get_connection() as conn:
        cursor = conn.execute(
            "INSERT INTO classrooms (name, camera_source) VALUES (?, ?)",
            (name.strip(), camera_source),
        )
        return cursor.lastrowid


def create_session(course_id: int, classroom_id: int | None = None) -> int:
    """Open a new attendance session (one lesson of a course) starting now, return its session_id.

    Raises ValueError if the classroom already has an open session, so two lessons can never
    record into the same room at once.
    """
    with _get_connection() as conn:
        if classroom_id is not None:
            busy = conn.execute(
                "SELECT session_id FROM sessions WHERE classroom_id = ? AND status = 'open'",
                (classroom_id,),
            ).fetchone()
            if busy is not None:
                raise ValueError(f"Classroom {classroom_id} already has open session {busy[0]}")

        cursor = conn.execute(
            "INSERT INTO sessions (course_id, classroom_id, started_at, status) VALUES (?, ?, ?, 'open')",
            (course_id, classroom_id, datetime.now().isoformat()),
        )
        session_id = cursor.lastrowid
        conn.execute(
            """
            INSERT INTO session_students (session_id, student_id)
            SELECT ?, student_id FROM course_students WHERE course_id = ?
            """,
            (session_id, course_id),
        )
        return session_id


def close_session(session_id: int) -> bool:
    """Close an open session and record its end time. Returns False if it was not open."""
    with _get_connection() as conn:
        cursor = conn.execute(
            "UPDATE sessions SET status = 'closed', ended_at = ? WHERE session_id = ? AND status = 'open'",
            (datetime.now().isoformat(), session_id),
        )
        return cursor.rowcount > 0


def close_all_open_sessions() -> int:
    """Close every session still marked open, e.g. ones left behind when the server stopped
    mid-lesson. Returns how many were closed.
    """
    with _get_connection() as conn:
        cursor = conn.execute(
            "UPDATE sessions SET status = 'closed', ended_at = ? WHERE status = 'open'",
            (datetime.now().isoformat(),),
        )
        return cursor.rowcount


def get_session(session_id: int) -> tuple[int, int, int | None, str, str | None, str] | None:
    """Return (session_id, course_id, classroom_id, started_at, ended_at, status), or None."""
    with _get_connection() as conn:
        cursor = conn.execute(
            """
            SELECT session_id, course_id, classroom_id, started_at, ended_at, status
            FROM sessions WHERE session_id = ?
            """,
            (session_id,),
        )
        return cursor.fetchone()


def log_session_attendance(session_id: int, student_id: int, confidence: float | None = None) -> bool:
    """Mark a student present in a session. Each student is recorded at most once per session,
    and only while the session is open. Returns True if a new record was written.
    """
    with _get_connection() as conn:
        row = conn.execute(
            """
            SELECT courses.code FROM sessions
            JOIN courses ON courses.course_id = sessions.course_id
            WHERE sessions.session_id = ? AND sessions.status = 'open'
            """,
            (session_id,),
        ).fetchone()
        if row is None:
            return False

        # session_name is filled with the course code so the legacy dashboard can still show the row.
        cursor = conn.execute(
            """
            INSERT OR IGNORE INTO attendance (student_id, timestamp, session_name, session_id, confidence)
            VALUES (?, ?, ?, ?, ?)
            """,
            (student_id, datetime.now().isoformat(), row[0], session_id, confidence),
        )
        return cursor.rowcount > 0


def get_session_attendance(session_id: int) -> list[tuple[int, str, str, float | None]]:
    """Return who was marked present in a session as (student_id, name, timestamp, confidence),
    in the order they were recognized.
    """
    with _get_connection() as conn:
        cursor = conn.execute(
            """
            SELECT students.student_id, students.name, attendance.timestamp, attendance.confidence
            FROM attendance
            JOIN students ON students.student_id = attendance.student_id
            WHERE attendance.session_id = ?
            ORDER BY attendance.timestamp ASC
            """,
            (session_id,),
        )
        return cursor.fetchall()


def get_sessions(course_id: int | None = None) -> list[tuple[int, str, str, str, str | None, str, int, int]]:
    """Return past and running sessions, newest first, as
    (session_id, course_code, course_name, started_at, ended_at, status, present_count, expected_count).
    If course_id is given, only that course's sessions are returned.
    """
    with _get_connection() as conn:
        cursor = conn.execute(
            """
            SELECT sessions.session_id, courses.code, courses.name, sessions.started_at,
                   sessions.ended_at, sessions.status,
                   (SELECT COUNT(*) FROM attendance WHERE attendance.session_id = sessions.session_id),
                   (SELECT COUNT(*) FROM session_students WHERE session_students.session_id = sessions.session_id)
            FROM sessions
            JOIN courses ON courses.course_id = sessions.course_id
            WHERE ? IS NULL OR sessions.course_id = ?
            ORDER BY sessions.started_at DESC
            """,
            (course_id, course_id),
        )
        return cursor.fetchall()


def get_session_results(session_id: int) -> list[tuple[int, str, bool, str | None, float | None]]:
    """Return every student expected at a session, plus anyone marked present, as
    (student_id, name, present, timestamp, confidence), ordered by name. Absent students have
    present=False and no timestamp.
    """
    with _get_connection() as conn:
        cursor = conn.execute(
            """
            SELECT students.student_id, students.name, attendance.id IS NOT NULL,
                   attendance.timestamp, attendance.confidence
            FROM students
            LEFT JOIN attendance
                   ON attendance.student_id = students.student_id AND attendance.session_id = ?
            WHERE attendance.id IS NOT NULL
               OR students.student_id IN (SELECT student_id FROM session_students WHERE session_id = ?)
            ORDER BY students.name COLLATE NOCASE ASC
            """,
            (session_id, session_id),
        )
        return [(sid, name, bool(present), ts, conf) for sid, name, present, ts, conf in cursor.fetchall()]


if __name__ == "__main__":
    print(f"Initializing database at {DB_PATH} ...")
    init_db()

    student_id = save_student("Test Student", b"fake-encoding-bytes")
    print(f"Saved test student with student_id={student_id}")
    print("Enrolled students:", get_all_students())

    print("First log_attendance (General):", log_attendance(student_id), "(expected True)")
    print("Immediate second call (General):", log_attendance(student_id), "(expected False, duplicate window)")

    print("Log under 'Math 101':", log_attendance(student_id, "Math 101"), "(expected True)")
    print("Second log under 'Math 101':", log_attendance(student_id, "Math 101"), "(expected False, session duplicate)")

    print("Sessions recorded:", get_all_sessions())
    print("Attendance log:", get_attendance_log())
