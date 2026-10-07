"""
Session Manager - Dynamic Session Generation & Course Roster Isolation
Dii Portal Face Recognition Attendance System
"""

import time
from datetime import datetime
from typing import Optional, List, Tuple, Dict, Any
import numpy as np

from config import SESSION_DURATION_SECONDS
from database.db import (
    create_session,
    end_session,
    get_roster_for_course,
    mark_attendance,
    get_session_attendance,
)


class ActiveSession:
    """
    Represents an in-flight attendance session.
    Keeps the active course roster in memory so the camera loop
    never makes disk/database queries on every frame.
    """

    def __init__(self, session_id: str, course_id: str, roster: List[Tuple[int, str, str, np.ndarray]], duration_seconds: int = SESSION_DURATION_SECONDS):
        self.session_id = session_id
        self.course_id = course_id
        self.roster = roster  # List of (student_id, student_code, full_name, embedding)
        self.duration_seconds = duration_seconds
        self.start_timestamp = time.time()
        self.is_active = True

    @property
    def elapsed_seconds(self) -> float:
        """Seconds elapsed since the professor started attendance."""
        return time.time() - self.start_timestamp

    @property
    def remaining_seconds(self) -> float:
        """Countdown timer: seconds remaining before automatic shutdown."""
        return max(0.0, self.duration_seconds - self.elapsed_seconds)

    def has_expired(self) -> bool:
        """Checks if the 10-minute (600s) window has ended."""
        return self.elapsed_seconds >= self.duration_seconds


class SessionManager:
    """
    Manages lecture session lifecycles:
    - Generates dynamic session_id (e.g. SESS_CS401_20261007_1500)
    - Isolates search space strictly to enrolled course students
    - Manages automatic 10-minute expiration
    """

    def __init__(self):
        self._current_session: Optional[ActiveSession] = None

    @property
    def current_session(self) -> Optional[ActiveSession]:
        """Returns the currently active session, or None."""
        if self._current_session and self._current_session.has_expired():
            self.stop_current_session()
        return self._current_session

    def start_session(
        self,
        course_id: str,
        duration_seconds: int = SESSION_DURATION_SECONDS,
        db_path: Optional[str] = None
    ) -> ActiveSession:
        """
        Starts a new 10-minute session:
        1. Closes any previously active session.
        2. Generates unique session_id: SESS_<course_id>_<YYYYMMDD_HHMMSS>
        3. Fetches enrolled students from SQLite into memory.
        4. Writes session record to SQLite.
        """
        if self._current_session and self._current_session.is_active:
            self.stop_current_session(db_path=db_path)

        # 1. Generate unique session ID
        timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        session_id = f"SESS_{course_id}_{timestamp_str}"

        # 2. Retrieve only students enrolled in this course (Roster Isolation)
        roster = get_roster_for_course(course_id, db_path=db_path)

        # 3. Persist session start in SQLite
        create_session(session_id, course_id, db_path=db_path)

        # 4. Activate in-memory tracking
        self._current_session = ActiveSession(
            session_id=session_id,
            course_id=course_id,
            roster=roster,
            duration_seconds=duration_seconds
        )
        return self._current_session

    def record_attendance(
        self,
        student_id: int,
        confidence_score: float = 0.0,
        db_path: Optional[str] = None
    ) -> bool:
        """
        Records attendance for a student in the active session.
        Returns True if newly recorded, False if already marked or session inactive.
        """
        session = self.current_session
        if not session or not session.is_active:
            return False

        return mark_attendance(
            session_id=session.session_id,
            student_id=student_id,
            confidence_score=confidence_score,
            db_path=db_path
        )

    def stop_current_session(self, db_path: Optional[str] = None) -> Optional[str]:
        """
        Ends the current session, updates the database status to COMPLETED,
        and returns the session_id.
        """
        if not self._current_session:
            return None

        session_id = self._current_session.session_id
        self._current_session.is_active = False
        end_session(session_id, db_path=db_path)
        self._current_session = None
        return session_id

    def get_summary(self, session_id: str, db_path: Optional[str] = None) -> List[Dict[str, Any]]:
        """Retrieves attendance results for a session."""
        return get_session_attendance(session_id, db_path=db_path)


# Global singleton instance
session_manager = SessionManager()
