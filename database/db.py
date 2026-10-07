"""
Database Layer - SQLite Relational Schema
Dii Portal Face Recognition Attendance System
"""

import sqlite3
import numpy as np
from typing import Optional, List, Tuple
from config import LOCAL_DB_PATH


def get_connection(db_path: Optional[str] = None) -> sqlite3.Connection:
    """
    Establish a connection to SQLite database.
    Enforces SQLite foreign key constraints by executing PRAGMA foreign_keys = ON.
    """
    path = db_path or str(LOCAL_DB_PATH)
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def init_db(db_path: Optional[str] = None) -> None:
    """
    Initializes the 5 core relational tables:
    1. students: Registered students with 128-d face vector embeddings.
    2. courses: University courses (e.g., CS401).
    3. course_students: Junction table linking students to courses (Many-to-Many).
    4. sessions: Individual 10-minute lecture slots tied to a course.
    5. attendance: Verified attendance logs with unique constraint per session.
    """
    with get_connection(db_path) as conn:
        cursor = conn.cursor()

        # 1. Students Table
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS students (
                student_id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_code TEXT UNIQUE NOT NULL,
                full_name TEXT NOT NULL,
                face_encoding BLOB NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
            );
            """
        )

        # 2. Courses Table
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS courses (
                course_id TEXT PRIMARY KEY,
                course_name TEXT NOT NULL
            );
            """
        )

        # 3. Course-Students Junction Table (Course Rosters)
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS course_students (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                course_id TEXT NOT NULL,
                student_id INTEGER NOT NULL,
                FOREIGN KEY (course_id) REFERENCES courses(course_id) ON DELETE CASCADE,
                FOREIGN KEY (student_id) REFERENCES students(student_id) ON DELETE CASCADE,
                UNIQUE(course_id, student_id)
            );
            """
        )

        # 4. Sessions Table (10-minute active lecture windows)
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                session_id TEXT PRIMARY KEY,
                course_id TEXT NOT NULL,
                started_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
                ended_at TEXT,
                status TEXT NOT NULL DEFAULT 'ACTIVE',
                FOREIGN KEY (course_id) REFERENCES courses(course_id) ON DELETE CASCADE
            );
            """
        )

        # 5. Attendance Table (Logs attendance per session)
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS attendance (
                attendance_id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                student_id INTEGER NOT NULL,
                marked_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
                confidence_score REAL,
                status TEXT NOT NULL DEFAULT 'PRESENT',
                FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE CASCADE,
                FOREIGN KEY (student_id) REFERENCES students(student_id) ON DELETE CASCADE,
                UNIQUE(session_id, student_id)
            );
            """
        )

        conn.commit()


# ==========================================
# Helper CRUD Operations
# ==========================================

def add_course(course_id: str, course_name: str, db_path: Optional[str] = None) -> None:
    """Inserts or ignores a course."""
    with get_connection(db_path) as conn:
        conn.execute(
            "INSERT OR IGNORE INTO courses (course_id, course_name) VALUES (?, ?);",
            (course_id, course_name)
        )


def register_student(
    student_code: str,
    full_name: str,
    face_encoding: np.ndarray,
    db_path: Optional[str] = None
) -> int:
    """
    Registers a student and stores their 128-d vector embedding as raw bytes.
    Returns the generated student_id.
    """
    encoding_bytes = face_encoding.astype(np.float64).tobytes()
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO students (student_code, full_name, face_encoding)
            VALUES (?, ?, ?)
            ON CONFLICT(student_code) DO UPDATE SET
                full_name=excluded.full_name,
                face_encoding=excluded.face_encoding;
            """,
            (student_code, full_name, encoding_bytes)
        )
        cursor.execute("SELECT student_id FROM students WHERE student_code = ?;", (student_code,))
        return cursor.fetchone()[0]


def enroll_student_in_course(course_id: str, student_id: int, db_path: Optional[str] = None) -> None:
    """Links a student to a specific course roster."""
    with get_connection(db_path) as conn:
        conn.execute(
            "INSERT OR IGNORE INTO course_students (course_id, student_id) VALUES (?, ?);",
            (course_id, student_id)
        )


def get_roster_for_course(
    course_id: str,
    db_path: Optional[str] = None
) -> List[Tuple[int, str, str, np.ndarray]]:
    """
    Retrieves students enrolled in a specific course.
    Returns a list of tuples: (student_id, student_code, full_name, face_encoding_numpy_array)
    """
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT s.student_id, s.student_code, s.full_name, s.face_encoding
            FROM students s
            JOIN course_students cs ON s.student_id = cs.student_id
            WHERE cs.course_id = ?;
            """,
            (course_id,)
        )
        rows = cursor.fetchall()
        roster = []
        for s_id, s_code, name, enc_bytes in rows:
            # Reconstruct the 128-d numpy float64 array from stored bytes
            arr = np.frombuffer(enc_bytes, dtype=np.float64)
            roster.append((s_id, s_code, name, arr))
        return roster


def create_session(session_id: str, course_id: str, db_path: Optional[str] = None) -> None:
    """Creates a new active lecture session."""
    with get_connection(db_path) as conn:
        conn.execute(
            "INSERT INTO sessions (session_id, course_id, status) VALUES (?, ?, 'ACTIVE');",
            (session_id, course_id)
        )


def end_session(session_id: str, db_path: Optional[str] = None) -> None:
    """Marks a lecture session as COMPLETED and records the end timestamp."""
    with get_connection(db_path) as conn:
        conn.execute(
            """
            UPDATE sessions
            SET status = 'COMPLETED', ended_at = datetime('now', 'localtime')
            WHERE session_id = ?;
            """,
            (session_id,)
        )


def mark_attendance(
    session_id: str,
    student_id: int,
    confidence_score: float = 0.0,
    db_path: Optional[str] = None
) -> bool:
    """
    Logs attendance for a student in a session.
    Enforces uniqueness: if the student was already marked in this session,
    the insert is ignored and returns False.
    Returns True if successfully logged.
    """
    try:
        with get_connection(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO attendance (session_id, student_id, confidence_score)
                VALUES (?, ?, ?);
                """,
                (session_id, student_id, confidence_score)
            )
            return True
    except sqlite3.IntegrityError:
        # Already logged in this session
        return False


def get_session_attendance(session_id: str, db_path: Optional[str] = None) -> List[dict]:
    """Retrieves all students marked present for a specific session."""
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT s.student_code, s.full_name, a.marked_at, a.confidence_score, a.status
            FROM attendance a
            JOIN students s ON a.student_id = s.student_id
            WHERE a.session_id = ?
            ORDER BY a.marked_at ASC;
            """,
            (session_id,)
        )
        results = []
        for code, name, marked_at, conf, status in cursor.fetchall():
            results.append({
                "student_code": code,
                "full_name": name,
                "marked_at": marked_at,
                "confidence_score": conf,
                "status": status
            })
        return results
