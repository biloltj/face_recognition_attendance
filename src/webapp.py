# Web app module
# Owns: Flask server exposing live video streaming, student enrollment (camera/photo),
# session-based attendance recognition, roster management, and CSV export.

from __future__ import annotations

import os
import sqlite3
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
import cv2
import numpy as np
from flask import Flask, Response, jsonify, render_template, request, send_file

import database
import enrollment
import export
import main
import recognition

app = Flask(__name__)

# Reject uploads bigger than 16 MB
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024
MAX_PHOTO_SIDE = 1600

# A Take Attendance session records for this long, then the server closes it on its own.
SESSION_DURATION_SECONDS = 10 * 60

# Live sessions only mark a student present after matching them in this many recognition passes,
# each no more than CONFIRM_WINDOW_PASSES passes after the previous match — one stray wrong match
# can't mark anybody. The window counts passes, not seconds, because a pass gets longer the more
# faces are in view: a time limit would stop a full classroom from ever being confirmed.
CONFIRMATIONS_REQUIRED = 2
CONFIRM_WINDOW_PASSES = 3


@dataclass(frozen=True)
class ActiveSession:
    """The attendance session currently being recorded, with its course roster loaded once up
    front so the live stream never has to re-read students from the database per frame.
    """

    session_id: int
    course_id: int
    course_code: str
    course_name: str
    started_at: str
    ends_at: datetime
    roster: list[tuple[int, str, bytes]]  # one row per student
    encodings: list[tuple[int, str, bytes]]  # one row per reference photo, for matching


class CameraManager:
    """Thread-safe webcam manager for live in-browser streaming and recognition.

    One reader thread pulls frames off the camera and keeps only the newest. The browser stream
    and the recognizer each take that newest frame, so neither waits for the other, any number of
    browser tabs see the same video, and recognition keeps going even if every tab is closed.

    Without a session the stream is a plain preview (useful for aiming the camera). While a session
    is active, a recognizer thread matches faces against that session's course roster, and marks a
    student present once they have been matched in CONFIRMATIONS_REQUIRED passes (see _recognize_loop).
    """

    def __init__(self):
        self._cap = None
        self._lock = threading.Lock()
        self._is_running = False
        self._reader: threading.Thread | None = None
        self._recognizer: threading.Thread | None = None
        self._latest_frame: np.ndarray | None = None
        self._frame_seq = 0  # increases with every frame read, so consumers can skip repeats
        self._session: ActiveSession | None = None
        self._last_detections: list[tuple[str, tuple[int, int, int, int]]] = []
        self._resolution: tuple[int, int] | None = None

    def start(self) -> bool:
        with self._lock:
            if self._is_running:
                return True
            cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
            if not cap.isOpened():
                cap.release()
                return False
            # MJPG lets most USB webcams deliver 1280x720 at full frame rate over DirectShow; the
            # default raw format often drops to a few frames per second at that size.
            cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, main.CAPTURE_WIDTH)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, main.CAPTURE_HEIGHT)
            self._resolution = (int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)))
            print(f"Camera opened at {self._resolution[0]}x{self._resolution[1]}")

            self._cap = cap
            self._is_running = True
            self._latest_frame = None
            self._reader = threading.Thread(target=self._read_loop, args=(cap,), daemon=True)
            self._reader.start()
            return True

    def stop(self) -> None:
        with self._lock:
            self._is_running = False
            self._session = None  # tells the recognizer thread to finish
            self._last_detections = []
            reader, recognizer, cap = self._reader, self._recognizer, self._cap
            self._reader = self._recognizer = self._cap = None
            self._latest_frame = None

        # Wait for the threads outside the lock (they take it to publish results), and only release
        # the camera once the reader has stopped using it.
        for thread in (reader, recognizer):
            if thread is not None and thread is not threading.current_thread():
                thread.join(timeout=5)
        if cap is not None:
            cap.release()

    def is_running(self) -> bool:
        with self._lock:
            return self._is_running

    def get_resolution(self) -> tuple[int, int] | None:
        with self._lock:
            return self._resolution if self._is_running else None

    def begin_session(self, session: ActiveSession) -> None:
        with self._lock:
            self._session = session
            self._last_detections = []
            self._recognizer = threading.Thread(target=self._recognize_loop, args=(session,), daemon=True)
            self._recognizer.start()

    def get_session(self) -> ActiveSession | None:
        with self._lock:
            return self._session

    def capture_single_frame(self) -> np.ndarray | None:
        with self._lock:
            if self._latest_frame is not None:
                return self._latest_frame.copy()
        # Fallback to standalone capture if stream not running
        return recognition.capture_frame_from_webcam()

    def get_jpeg_frame(self, after_seq: int) -> tuple[int, bytes | None]:
        """Return (seq, jpeg) for the newest frame with the current boxes drawn on it, or
        (after_seq, None) if no frame newer than `after_seq` has arrived yet.
        """
        with self._lock:
            if self._latest_frame is None or self._frame_seq == after_seq:
                return after_seq, None
            seq = self._frame_seq
            display_frame = self._latest_frame.copy()
            detections = list(self._last_detections) if self._session is not None else []

        main.draw_detections(display_frame, detections)
        ok, jpeg = cv2.imencode(".jpg", display_frame, [int(cv2.IMWRITE_JPEG_QUALITY), 75])
        return seq, (jpeg.tobytes() if ok else None)

    def _read_loop(self, cap) -> None:
        while True:
            with self._lock:
                if self._cap is not cap:
                    return
            ok, frame = cap.read()
            if not ok or frame is None:
                time.sleep(0.05)
                continue
            with self._lock:
                self._latest_frame = frame
                self._frame_seq += 1

    def _recognize_loop(self, session: ActiveSession) -> None:
        """Recognize faces on the newest frame, over and over, until this session ends.

        A single pass can occasionally put the wrong name on a face (bad angle, motion blur), so
        nobody is marked present from one pass alone: the same student must be matched again within
        CONFIRM_WINDOW_PASSES passes. Until then their box is labelled "Name?". The saved confidence
        is the best (lowest) distance seen for them.
        """
        matched_count: dict[int, int] = {}
        last_matched_pass: dict[int, int] = {}
        best_distance: dict[int, float] = {}
        confirmed: set[int] = set()
        done_seq = -1
        pass_number = 0

        while True:
            with self._lock:
                if self._session is not session:
                    return
                frame, seq = self._latest_frame, self._frame_seq
            if frame is None or seq == done_seq:
                time.sleep(0.05)
                continue
            done_seq = seq

            detections = main.recognize_frame(frame, session.encodings, pool=get_encoder_pool())
            pass_number += 1
            labelled = []
            for d in detections:
                if d.student_id is None:
                    labelled.append((d.label, d.location))
                    continue
                sid = d.student_id
                best_distance[sid] = min(d.distance, best_distance.get(sid, d.distance))
                # Count each student at most once per pass: two faces given the same name in one
                # frame must not confirm them on their own.
                if last_matched_pass.get(sid) != pass_number:
                    recent = pass_number - last_matched_pass.get(sid, -10**9) <= CONFIRM_WINDOW_PASSES
                    matched_count[sid] = matched_count.get(sid, 0) + 1 if recent else 1
                    last_matched_pass[sid] = pass_number

                if sid not in confirmed and matched_count[sid] >= CONFIRMATIONS_REQUIRED:
                    database.log_session_attendance(session.session_id, sid, best_distance[sid])
                    confirmed.add(sid)
                labelled.append((d.label if sid in confirmed else f"{d.label}?", d.location))

            with self._lock:
                if self._session is session:
                    self._last_detections = labelled


camera_manager = CameraManager()

# Worker processes that encode faces in parallel (see recognition.create_encoder_pool). Started
# with the server so their models are loaded before the first session; created on first use
# otherwise (e.g. in tests).
_encoder_pool = None
_encoder_pool_lock = threading.Lock()


def get_encoder_pool():
    global _encoder_pool
    with _encoder_pool_lock:
        if _encoder_pool is None:
            _encoder_pool = recognition.create_encoder_pool()
        return _encoder_pool

# Held while a session is being started or stopped, so two clicks can't open two sessions at once.
session_lock = threading.Lock()
# Fires _end_session() when the running session's time is up; cancelled if the teacher ends early.
_session_timer: threading.Timer | None = None


def _end_session(expected_session_id: int | None = None) -> ActiveSession | None:
    """Close the running session and turn the camera off. Returns the session that was ended, or
    None if nothing was running.

    The auto-stop timer passes `expected_session_id`, so a timer left over from an earlier session
    can never end a newer one.
    """
    global _session_timer
    with session_lock:
        session = camera_manager.get_session()
        if session is None or (expected_session_id is not None and session.session_id != expected_session_id):
            return None
        if _session_timer is not None:
            _session_timer.cancel()
            _session_timer = None
        database.close_session(session.session_id)
        camera_manager.stop()
        return session


def _find_course(course_id: int) -> tuple[int, str, str] | None:
    return next((c for c in database.get_all_courses() if c[0] == course_id), None)


def _no_session_error():
    return jsonify({"error": "No attendance session is running. Choose a course and click Take Attendance first."}), 409


def _read_uploaded_photo():
    """Decode an uploaded image file into a BGR numpy array, resized if needed."""
    file = request.files.get("photo")
    if file is None:
        return None

    data = np.frombuffer(file.read(), dtype=np.uint8)
    image = cv2.imdecode(data, cv2.IMREAD_COLOR)
    if image is None:
        return None

    height, width = image.shape[:2]
    longest_side = max(height, width)
    if longest_side > MAX_PHOTO_SIDE:
        scale = MAX_PHOTO_SIDE / longest_side
        image = cv2.resize(image, (0, 0), fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    return image


@app.route("/")
def dashboard():
    return render_template("dashboard.html")


# ------------------------------------------------------------------ Live Stream
def _gen_frames():
    """Yield MJPEG video frames for the in-browser live stream."""
    last_seq = -1
    while True:
        if not camera_manager.is_running():
            placeholder = np.zeros((360, 640, 3), dtype=np.uint8)
            cv2.putText(
                placeholder,
                "Camera Inactive - Click 'Start Live Stream'",
                (50, 185),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (180, 180, 180),
                2,
            )
            _, jpeg = cv2.imencode(".jpg", placeholder)
            yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + jpeg.tobytes() + b"\r\n")
            time.sleep(0.3)
            continue

        last_seq, frame_bytes = camera_manager.get_jpeg_frame(last_seq)
        if frame_bytes is None:
            time.sleep(0.01)  # no new frame from the camera yet
            continue

        yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + frame_bytes + b"\r\n")


@app.route("/video_feed")
def video_feed():
    return Response(_gen_frames(), mimetype="multipart/x-mixed-replace; boundary=frame")


@app.route("/api/camera/start", methods=["POST"])
def api_camera_start():
    """Start a preview stream (no recognition) so the teacher can check the camera angle."""
    return jsonify({"running": camera_manager.start()})


@app.route("/api/camera/stop", methods=["POST"])
def api_camera_stop():
    if camera_manager.get_session() is not None:
        return jsonify({"error": "An attendance session is running. Click End Session instead."}), 409
    camera_manager.stop()
    return jsonify({"running": False})


@app.route("/api/camera/status")
def api_camera_status():
    resolution = camera_manager.get_resolution()
    return jsonify({
        "running": camera_manager.is_running(),
        # What the camera actually delivers: below 1280x720, distant faces get too small to detect.
        "resolution": f"{resolution[0]}x{resolution[1]}" if resolution else None,
    })


# ------------------------------------------------------------------ Courses
@app.route("/api/courses")
def api_courses():
    return jsonify([
        {
            "course_id": course_id,
            "code": code,
            "name": name,
            "student_count": len(database.get_course_students(course_id)),
        }
        for course_id, code, name in database.get_all_courses()
    ])


@app.route("/api/courses", methods=["POST"])
def api_create_course():
    data = request.get_json(silent=True) or {}
    code = (data.get("code") or "").strip()
    name = (data.get("name") or "").strip()
    if not code or not name:
        return jsonify({"error": "Please enter both a course code and a course name."}), 400
    try:
        course_id = database.create_course(code, name)
    except sqlite3.IntegrityError:
        return jsonify({"error": f"A course with code '{code}' already exists."}), 409
    return jsonify({"course_id": course_id, "code": code, "name": name})


@app.route("/api/courses/<int:course_id>/students")
def api_course_students(course_id: int):
    if _find_course(course_id) is None:
        return jsonify({"error": "Course not found."}), 404
    students = database.get_course_students(course_id)
    return jsonify([{"student_id": sid, "name": name} for sid, name, _ in students])


@app.route("/api/courses/<int:course_id>/students/<int:student_id>", methods=["POST"])
def api_add_course_student(course_id: int, student_id: int):
    try:
        added = database.add_student_to_course(course_id, student_id)
    except sqlite3.IntegrityError:
        return jsonify({"error": "Course or student not found."}), 404
    return jsonify({"success": added})


@app.route("/api/courses/<int:course_id>/students/<int:student_id>", methods=["DELETE"])
def api_remove_course_student(course_id: int, student_id: int):
    return jsonify({"success": database.remove_student_from_course(course_id, student_id)})


# ------------------------------------------------------------------ Sessions
@app.route("/api/sessions")
def api_sessions():
    """Session names that appear in the attendance log, for the history filter."""
    return jsonify({"sessions": database.get_all_sessions()})


@app.route("/api/sessions/start", methods=["POST"])
def api_session_start():
    """Take Attendance: open a new session for a course and start recognizing its students.
    The session closes by itself after SESSION_DURATION_SECONDS.
    """
    global _session_timer
    data = request.get_json(silent=True) or {}
    try:
        course_id = int(data.get("course_id"))
    except (TypeError, ValueError):
        return jsonify({"error": "Please choose a course."}), 400

    with session_lock:
        if camera_manager.get_session() is not None:
            return jsonify({"error": "A session is already running. End it before starting another."}), 409

        course = _find_course(course_id)
        if course is None:
            return jsonify({"error": "Course not found."}), 404
        roster = database.get_course_students(course_id)
        if not roster:
            return jsonify({"error": f"No students are assigned to {course[1]} yet. Add them in the Courses tab."}), 400

        # Open the camera before creating the session, so a busy webcam doesn't leave an empty session.
        if not camera_manager.start():
            return jsonify({"error": "Could not access the webcam. Make sure no other app is using it."}), 503

        session_id = database.create_session(course_id)
        started_at = database.get_session(session_id)[3]
        ends_at = datetime.fromisoformat(started_at) + timedelta(seconds=SESSION_DURATION_SECONDS)
        camera_manager.begin_session(
            ActiveSession(
                session_id, course_id, course[1], course[2], started_at, ends_at, roster,
                database.get_course_face_encodings(course_id),
            )
        )

        # The timer runs on the server, so the session still ends on time if the browser is closed.
        _session_timer = threading.Timer(SESSION_DURATION_SECONDS, _end_session, args=(session_id,))
        _session_timer.daemon = True
        _session_timer.start()

    return _current_session_json()


@app.route("/api/sessions/stop", methods=["POST"])
def api_session_stop():
    """End Session: the teacher stops the running session before its time is up."""
    session = _end_session()
    if session is None:
        return _no_session_error()

    present = database.get_session_attendance(session.session_id)
    return jsonify({"session_id": session.session_id, "present_count": len(present), "roster_size": len(session.roster)})


@app.route("/api/sessions/current")
def api_session_current():
    return _current_session_json()


@app.route("/api/sessions/history")
def api_session_history():
    """All course sessions, newest first, optionally for one course (?course_id=)."""
    course_id = request.args.get("course_id", type=int)
    return jsonify([
        {
            "session_id": sid,
            "course_code": code,
            "course_name": name,
            "started_at": started_at,
            "ended_at": ended_at,
            "status": status,
            "present_count": present,
            "expected_count": expected,
        }
        for sid, code, name, started_at, ended_at, status, present, expected in database.get_sessions(course_id)
    ])


@app.route("/api/sessions/<int:session_id>/results")
def api_session_results(session_id: int):
    """Present / absent list for one session."""
    session = database.get_session(session_id)
    if session is None:
        return jsonify({"error": "Session not found."}), 404
    _, course_id, _, started_at, ended_at, status = session
    course = _find_course(course_id)
    results = database.get_session_results(session_id)
    present_count = sum(1 for r in results if r[2])
    return jsonify({
        "session_id": session_id,
        "course_code": course[1],
        "course_name": course[2],
        "started_at": started_at,
        "ended_at": ended_at,
        "status": status,
        "present_count": present_count,
        "absent_count": len(results) - present_count,
        "students": [
            {"student_id": sid, "name": name, "present": present, "timestamp": ts,
             "confidence": conf, "source": source}
            for sid, name, present, ts, conf, source in results
        ],
    })


@app.route("/api/sessions/<int:session_id>/export.csv")
def api_session_export(session_id: int):
    """Download one session's present / absent list as CSV."""
    session = database.get_session(session_id)
    if session is None:
        return jsonify({"error": "Session not found."}), 404
    course = _find_course(session[1])
    date = session[3][:10]
    path = export.export_session_csv(session_id)
    download_name = f"attendance_{course[1]}_{date}_session{session_id}.csv".replace(" ", "_")
    return send_file(path, as_attachment=True, download_name=download_name)


def _current_session_json():
    session = camera_manager.get_session()
    if session is None:
        return jsonify({"active": False})

    present = database.get_session_attendance(session.session_id)
    return jsonify({
        "active": True,
        "session_id": session.session_id,
        "course_id": session.course_id,
        "course_code": session.course_code,
        "course_name": session.course_name,
        "started_at": session.started_at,
        "ends_at": session.ends_at.isoformat(),
        # Sent as a count rather than only a clock time, so a wrong clock on the teacher's computer
        # doesn't break the countdown.
        "seconds_left": max(0, round((session.ends_at - datetime.now()).total_seconds())),
        "duration_seconds": SESSION_DURATION_SECONDS,
        "roster_size": len(session.roster),
        "present": [{"student_id": sid, "name": name, "timestamp": ts} for sid, name, ts, _ in present],
    })


# ------------------------------------------------------------------ Students
@app.route("/api/students")
def api_students():
    students = database.get_all_students()
    return jsonify([{"student_id": sid, "name": name} for sid, name, _ in students])


@app.route("/api/students/<int:student_id>", methods=["DELETE"])
def api_delete_student(student_id: int):
    deleted = database.delete_student(student_id)
    return jsonify({"success": deleted})


# ------------------------------------------------------------------ Enrollment
@app.route("/api/enroll", methods=["POST"])
def api_enroll():
    """Enroll student from webcam snapshot."""
    data = request.get_json(silent=True) or {}
    name = data.get("name", "").strip()
    if not name:
        return jsonify({"student_id": None, "error": "Please provide a student name."}), 400

    frame = camera_manager.capture_single_frame()
    if frame is None:
        return jsonify({"student_id": None, "error": "Could not access the webcam."}), 503

    result = enrollment.enroll_from_frame(name, frame)
    return jsonify(result._asdict())


@app.route("/api/enroll/photo", methods=["POST"])
def api_enroll_photo():
    """Enroll a student from an uploaded photo."""
    name = request.form.get("name", "").strip()
    if not name:
        return jsonify({"student_id": None, "error": "Please provide a student name."}), 400

    image = _read_uploaded_photo()
    if image is None:
        return jsonify({"student_id": None, "error": "Please choose a valid image file (JPG or PNG)."}), 400

    result = enrollment.enroll_from_frame(name, image, cnn_fallback=True)
    return jsonify(result._asdict())


# ------------------------------------------------------------------ Attendance
@app.route("/api/attendance/capture", methods=["POST"])
def api_attendance_capture():
    """Take a single snapshot, detect & recognize faces, and log attendance for the running session."""
    session = camera_manager.get_session()
    if session is None:
        return _no_session_error()

    frame = camera_manager.capture_single_frame()
    if frame is None:
        return jsonify({"error": "Could not access the webcam."}), 503

    detections = main.process_frame(frame, session.encodings, session_id=session.session_id, pool=get_encoder_pool())
    return jsonify([{"name": name, "box": list(box), "session": session.course_code} for name, box in detections])


@app.route("/api/attendance/photo", methods=["POST"])
def api_attendance_photo():
    """Take attendance for the running session from an uploaded classroom/group photo."""
    session = camera_manager.get_session()
    if session is None:
        return _no_session_error()

    image = _read_uploaded_photo()
    if image is None:
        return jsonify({"error": "Please choose a valid image file (JPG or PNG)."}), 400

    detections = main.process_frame(
        image, session.encodings, cnn_fallback=True, session_id=session.session_id, pool=get_encoder_pool()
    )
    return jsonify([{"name": name, "box": list(box), "session": session.course_code} for name, box in detections])


@app.route("/api/attendance")
def api_attendance():
    """Attendance log as JSON, optionally filtered by session."""
    session = request.args.get("session")
    if session == "ALL" or not session:
        session = None
    rows = database.get_attendance_log(session_name=session)
    return jsonify([{"student": r[0], "timestamp": r[1], "session": r[2]} for r in rows])


@app.route("/api/attendance/export.csv")
def api_attendance_export():
    """Download attendance log as CSV, optionally filtered by session."""
    session = request.args.get("session")
    if session == "ALL" or not session:
        session = None
    path = export.export_attendance_csv(session_name=session)
    return send_file(path, as_attachment=True, download_name=f"attendance_{session or 'all'}.csv")


def run() -> None:
    database.init_db()
    # The camera stops with the server, so any session still marked open is a leftover.
    database.close_all_open_sessions()
    # Start the face-encoding workers now, so the first session doesn't wait for them to load.
    # In debug mode Flask runs this script twice (a file watcher, then the real server with
    # WERKZEUG_RUN_MAIN set); only the real server needs workers.
    if os.environ.get("WERKZEUG_RUN_MAIN") == "true":
        recognition.warm_up_encoder_pool(get_encoder_pool(), recognition.default_encoder_workers())
    app.run(debug=True)


if __name__ == "__main__":
    run()
