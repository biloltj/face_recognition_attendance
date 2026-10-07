"""
Database package initialization.
"""
from database.db import (
    init_db,
    get_connection,
    add_course,
    register_student,
    enroll_student_in_course,
    get_roster_for_course,
    create_session,
    end_session,
    mark_attendance,
    get_session_attendance,
)

__all__ = [
    "init_db",
    "get_connection",
    "add_course",
    "register_student",
    "enroll_student_in_course",
    "get_roster_for_course",
    "create_session",
    "end_session",
    "mark_attendance",
    "get_session_attendance",
]
