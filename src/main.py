# Entry point: wires the recognition module and data module together.
#
# Detects and recognizes every face in the frame at once — this naturally covers single-person
# use as well as multiple students (a small group, then a whole classroom) since a frame with
# just one face simply produces a list of length one.

from __future__ import annotations

import threading

import cv2

import database
import recognition

# Requesting a bigger capture resolution than the camera's default (often 640x480) lets more
# people fit in frame, and gives faces farther from the camera more pixels to work with.
CAPTURE_WIDTH = 1280
CAPTURE_HEIGHT = 720

# Recognition is the slow step in this pipeline. Instead of shrinking the frame aggressively to
# keep it fast (which made distant/smaller faces too low-detail to recognize), recognition now
# runs on its own background thread (see RecognitionWorker below) — so however long it takes, the
# video display keeps updating at the camera's own framerate and never freezes. That lets us
# afford a less aggressive resize for better accuracy.
RECOGNITION_RESIZE_FACTOR = 0.5


def draw_detections(frame, detections: list[tuple[str, tuple[int, int, int, int]]]) -> None:
    """Draw a green box and name label on `frame` (in place) for each (label, face_location) pair.

    Shared between the terminal app below and the GUI (gui.py), so both draw detections the same
    way instead of duplicating this loop.
    """
    for label, (top, right, bottom, left) in detections:
        cv2.rectangle(frame, (left, top), (right, bottom), (0, 255, 0), 2)
        cv2.putText(frame, label, (left, max(top - 10, 0)), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)


def process_frame(
    frame, students: list[tuple[int, str, bytes]]
) -> list[tuple[str, tuple[int, int, int, int]]]:
    """Look for every face in one frame and return (label, face_location) for each: the matched
    student's name, or "Unknown" if a face was found but didn't match anyone. Returns an empty
    list if no faces are found.

    Also logs attendance for every matched student.
    """
    results = []
    for encoding, location in recognition.get_all_face_encodings(frame, resize_factor=RECOGNITION_RESIZE_FACTOR):
        student_id = recognition.match_face(encoding, students)
        if student_id is None:
            results.append(("Unknown", location))
            continue

        database.log_attendance(student_id)
        name = next(name for sid, name, _ in students if sid == student_id)
        results.append((name, location))
    return results


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
