# Entry point: wires the recognition module and data module together.
#
# Detects and recognizes every face in the frame at once — this naturally covers single-person
# use as well as multiple students (a small group, then a whole classroom) since a frame with
# just one face simply produces a list of length one.

from __future__ import annotations

import threading
from typing import NamedTuple

import cv2

import database
import recognition

# Requesting a bigger capture resolution than the camera's default (often 640x480) lets more
# people fit in frame, and gives faces farther from the camera more pixels to work with.
CAPTURE_WIDTH = 1280
CAPTURE_HEIGHT = 720

# Recognition is the slow step in this pipeline, but it runs on a background thread (see
# RecognitionWorker below, and the session recognizer in webapp.py), so the video never waits for it.
# That lets detection run on the full frame: the face detector can't find faces smaller than about
# 40 px, and at 1280x720 a face 2 m from a typical webcam is only ~70 px — halving the frame (the
# old 0.5 setting) shrank it to ~35 px, so anyone past about 1.5 m was never found at all.
# Full resolution finds faces out to roughly 3.5 m, at ~0.65 s per pass on a laptop CPU.
RECOGNITION_RESIZE_FACTOR = 1.0


class Recognition(NamedTuple):
    """One face found in a frame: who it is (student_id None if nobody matched), the label to
    draw, where it is, and the match distance (lower = surer; None if no match).
    """

    student_id: int | None
    label: str
    location: tuple[int, int, int, int]
    distance: float | None


def draw_detections(frame, detections: list[tuple[str, tuple[int, int, int, int]]]) -> None:
    """Draw a green box and name label on `frame` (in place) for each (label, face_location) pair.

    Shared between the terminal app below and the GUI (gui.py), so both draw detections the same
    way instead of duplicating this loop.
    """
    for label, (top, right, bottom, left) in detections:
        cv2.rectangle(frame, (left, top), (right, bottom), (0, 255, 0), 2)
        cv2.putText(frame, label, (left, max(top - 10, 0)), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)


def recognize_frame(
    frame, students: list[tuple[int, str, bytes]], cnn_fallback: bool = False
) -> list[Recognition]:
    """Find every face in one frame and match each against `students`, without logging anything.
    Faces that match nobody come back with student_id None and the label "Unknown".

    `cnn_fallback` is passed through to recognition.get_all_face_encodings() — only for a single
    uploaded photo (see webapp.py), never in the live loop.
    """
    names = {sid: name for sid, name, _ in students}
    results = []
    faces = recognition.get_all_face_encodings(
        frame, resize_factor=RECOGNITION_RESIZE_FACTOR, cnn_fallback=cnn_fallback
    )
    for encoding, location in faces:
        student_id, distance = recognition.match_face_with_distance(encoding, students)
        label = "Unknown" if student_id is None else names[student_id]
        results.append(Recognition(student_id, label, location, distance))
    return results


def process_frame(
    frame,
    students: list[tuple[int, str, bytes]],
    cnn_fallback: bool = False,
    session_name: str = "General",
    session_id: int | None = None,
) -> list[tuple[str, tuple[int, int, int, int]]]:
    """Recognize every face in one frame (see recognize_frame) and return (label, face_location)
    for each. Returns an empty list if no faces are found.

    Also logs attendance for every matched student straight away: into the course session
    `session_id` when one is given (at most once per student per session, with the match distance
    as confidence), otherwise into the legacy named `session_name`.
    """
    detections = recognize_frame(frame, students, cnn_fallback=cnn_fallback)
    for d in detections:
        if d.student_id is None:
            continue
        if session_id is not None:
            database.log_session_attendance(session_id, d.student_id, d.distance)
        else:
            database.log_attendance(d.student_id, session_name=session_name)
    return [(d.label, d.location) for d in detections]


class RecognitionWorker:
    """Runs process_frame() on a background thread against whatever the latest frame is, so a
    slow recognition pass never blocks the video display loop.

    The main loop calls submit_frame() every time it grabs a new frame, and reads whatever the
    most recently finished result is via get_detections() — the two run independently, so the
    on-screen video stays smooth even if recognition is still working on an older frame.
    """

    def __init__(self, students: list[tuple[int, str, bytes]]):
        self._students = students
        self._lock = threading.Lock()
        self._latest_frame = None
        self._detections: list[tuple[str, tuple[int, int, int, int]]] = []
        self._running = True
        # Raised by submit_frame() whenever a new frame is ready, so _run() can sleep in between
        # instead of spinning in a tight loop and hogging the CPU (which was starving the main
        # video-display thread and causing stutter even though recognition runs "in the background").
        self._new_frame_event = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def submit_frame(self, frame) -> None:
        with self._lock:
            self._latest_frame = frame
        self._new_frame_event.set()

    def get_detections(self) -> list[tuple[str, tuple[int, int, int, int]]]:
        with self._lock:
            return self._detections

    def stop(self) -> None:
        self._running = False
        self._new_frame_event.set()  # wake the thread up so it can notice _running is False
        self._thread.join(timeout=1)

    def _run(self) -> None:
        while self._running:
            # Block here (using no CPU) until submit_frame() raises the flag. The timeout just
            # makes sure we periodically re-check self._running so stop() can't hang forever.
            self._new_frame_event.wait(timeout=0.1)
            self._new_frame_event.clear()

            with self._lock:
                frame = self._latest_frame
            if frame is None:
                continue

            detections = process_frame(frame, self._students)
            with self._lock:
                self._detections = detections


def run() -> None:
    database.init_db()
    students = database.get_all_students()
    print(f"Loaded {len(students)} enrolled student(s). Press 'q' to quit.")

    worker = RecognitionWorker(students)
    try:
        for frame in recognition.frames_from_webcam(width=CAPTURE_WIDTH, height=CAPTURE_HEIGHT):
            worker.submit_frame(frame.copy())

            draw_detections(frame, worker.get_detections())

            cv2.imshow("Attendance - press q to quit", frame)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break
    finally:
        worker.stop()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    run()
