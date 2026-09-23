# Enrollment module (Person A + B, Sprint 1)
# Owns: capturing a student's photo(s) and computing their face encoding, then saving them via
# the data module. This is the glue between recognition.py (camera + encoding) and database.py
# (storage) for the FR-1 "enroll a student" requirement.

from __future__ import annotations

import time

import database
import recognition

# Face detection can occasionally miss on a single frame (bad angle, blink, motion blur), so we
# give it a few tries before giving up, rather than failing the whole enrollment on one bad frame.
MAX_CAPTURE_ATTEMPTS = 5
SECONDS_BETWEEN_ATTEMPTS = 1.0

# A guard against garbage input (e.g. a name field accidentally receiving something like a
# pasted command line instead of an actual name) rather than a real limit on name length.
MAX_NAME_LENGTH = 100


def enroll_student(name: str) -> int | None:
    """Capture the person currently in front of the webcam, compute their face encoding, and save
    them as a new student named `name`.

    Returns the new student_id on success, or None if the name is invalid, or if no face could be
    captured after several attempts (e.g. camera unavailable, or nobody in frame).
    """
    name = name.strip()
    if not name or len(name) > MAX_NAME_LENGTH:
        print(f"Invalid name: must be non-empty and at most {MAX_NAME_LENGTH} characters.")
        return None

    database.init_db()

    for attempt in range(1, MAX_CAPTURE_ATTEMPTS + 1):
        frame = recognition.capture_frame_from_webcam()
        if frame is None:
            print("Could not access the webcam.")
            return None

        encoding = recognition.get_face_encoding(frame)
        if encoding is not None:
            student_id = database.save_student(name, encoding)
            print(f"Enrolled '{name}' as student_id={student_id}.")
            return student_id

        print(f"No face detected (attempt {attempt}/{MAX_CAPTURE_ATTEMPTS}). Make sure your face is visible.")
        if attempt < MAX_CAPTURE_ATTEMPTS:
            time.sleep(SECONDS_BETWEEN_ATTEMPTS)

    print(f"Giving up: no face detected after {MAX_CAPTURE_ATTEMPTS} attempts.")
    return None


if __name__ == "__main__":
    # Quick manual test: enroll yourself by name via the webcam. Run with: python src/enrollment.py
    student_name = input("Enter the student's name to enroll: ").strip()
    enroll_student(student_name)
