# Enrollment module (Person A + B, Sprint 1)
# Owns: capturing a student's photo(s) and computing their face encoding, then saving them via
# the data module. This is the glue between recognition.py (camera + encoding) and database.py
# (storage) for the FR-1 "enroll a student" requirement.

from __future__ import annotations

import time
from typing import NamedTuple

import database
import recognition

# Face detection can occasionally miss on a single frame (bad angle, blink, motion blur), so we
# give it a few tries before giving up, rather than failing the whole enrollment on one bad frame.
MAX_CAPTURE_ATTEMPTS = 5
SECONDS_BETWEEN_ATTEMPTS = 1.0

# A guard against garbage input (e.g. a name field accidentally receiving something like a
# pasted command line instead of an actual name) rather than a real limit on name length.
MAX_NAME_LENGTH = 100


class EnrollmentResult(NamedTuple):
    """Result of enroll_student(): student_id is the new row on success, or None on failure — in
    which case `error` explains why (invalid name, no face found, or already enrolled), so callers
    like the GUI can show the right message instead of a generic "failed".
    """

    student_id: int | None
    error: str | None


def _validate_name(name: str) -> str | None:
    """Returns an error message if `name` is invalid, or None if it's fine to enroll."""
    if not name or len(name) > MAX_NAME_LENGTH:
        return f"Invalid name: must be non-empty and at most {MAX_NAME_LENGTH} characters."
    return None


def _finish_enrollment(name: str, encoding: bytes, students: list[tuple[int, str, bytes]]) -> EnrollmentResult:
    """Given an already-captured face encoding, check it's not a duplicate and save it.

    Shared by enroll_student() (which owns the webcam itself) and enroll_from_frame() (which takes
    a frame from a camera someone else is already holding open) so the duplicate-check/save logic
    lives in exactly one place.
    """
    # Same matching logic used during live recognition — if this face already matches someone
    # enrolled, refuse instead of silently creating a duplicate student record.
    existing_id = recognition.match_face(encoding, students)
    if existing_id is not None:
        existing_name = next(n for sid, n, _ in students if sid == existing_id)
        message = f"Already enrolled as '{existing_name}' (student_id={existing_id})."
        print(message)
        return EnrollmentResult(None, message)

    student_id = database.save_student(name, encoding)
    print(f"Enrolled '{name}' as student_id={student_id}.")
    return EnrollmentResult(student_id, None)


def enroll_student(name: str) -> EnrollmentResult:
    """Capture the person currently in front of the webcam, compute their face encoding, and save
    them as a new student named `name` — unless that face already matches an existing student, in
    which case enrollment is refused (see EnrollmentResult).

    Opens and closes the webcam itself (via capture_frame_from_webcam), retrying up to
    MAX_CAPTURE_ATTEMPTS times if no face is found yet. Fine for a single one-off enrollment (e.g.
    the terminal script below), but reopening the camera per attempt — and again for every student
    — is slow when enrolling many people back to back. For that case, see enroll_from_frame(),
    which reuses one already-open camera stream across many students.
    """
    name = name.strip()
    error = _validate_name(name)
    if error is not None:
        print(error)
        return EnrollmentResult(None, error)

    database.init_db()
    students = database.get_all_students()

    for attempt in range(1, MAX_CAPTURE_ATTEMPTS + 1):
        frame = recognition.capture_frame_from_webcam()
        if frame is None:
            message = "Could not access the webcam."
            print(message)
            return EnrollmentResult(None, message)

        encoding = recognition.get_face_encoding(frame)
        if encoding is not None:
            return _finish_enrollment(name, encoding, students)

        print(f"No face detected (attempt {attempt}/{MAX_CAPTURE_ATTEMPTS}). Make sure your face is visible.")
        if attempt < MAX_CAPTURE_ATTEMPTS:
            time.sleep(SECONDS_BETWEEN_ATTEMPTS)

    message = f"Giving up: no face detected after {MAX_CAPTURE_ATTEMPTS} attempts."
    print(message)
    return EnrollmentResult(None, message)


def enroll_from_frame(name: str, frame) -> EnrollmentResult:
    """Like enroll_student(), but works from a frame the caller already captured (e.g. the latest
    frame off a live preview) instead of opening the webcam itself.

    This is what makes enrolling many students quickly practical: the GUI opens the camera stream
    once and keeps it open across the whole enrollment session, showing a live preview so the
    operator can see the framing is good *before* capturing — no blind retries, and no per-student
    camera reopen cost.
    """
    name = name.strip()
    error = _validate_name(name)
    if error is not None:
        print(error)
        return EnrollmentResult(None, error)

    database.init_db()
    encoding = recognition.get_face_encoding(frame)
    if encoding is None:
        message = "No face detected. Make sure your face is clearly visible and try again."
        print(message)
        return EnrollmentResult(None, message)

    students = database.get_all_students()
    return _finish_enrollment(name, encoding, students)


if __name__ == "__main__":
    # Quick manual test: enroll yourself by name via the webcam. Run with: python src/enrollment.py
    student_name = input("Enter the student's name to enroll: ").strip()
    enroll_student(student_name)
