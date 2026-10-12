# Web app module
# Owns: Flask server exposing live video streaming, student enrollment (camera/photo),
# session-based attendance recognition, roster management, and CSV export.

from __future__ import annotations

import threading
import time
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


class CameraManager:
    """Thread-safe webcam manager for live in-browser streaming and recognition."""

    def __init__(self):
        self._cap = None
        self._lock = threading.Lock()
        self._is_running = False
        self._active_session = "General"
        self._auto_recognize = False
        self._last_detections: list[tuple[str, tuple[int, int, int, int]]] = []
        self._frame_count = 0

    def start(self, session: str = "General", auto_recognize: bool = False) -> bool:
        with self._lock:
            self._active_session = (session or "General").strip()
            self._auto_recognize = auto_recognize
            if not self._is_running or self._cap is None:
                self._cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
                self._is_running = self._cap.isOpened()
            return self._is_running

    def stop(self) -> None:
        with self._lock:
            self._is_running = False
            if self._cap is not None:
                self._cap.release()
                self._cap = None
            self._last_detections = []

    def is_running(self) -> bool:
        with self._lock:
            return self._is_running and self._cap is not None and self._cap.isOpened()

    def set_session(self, session: str) -> None:
        with self._lock:
            self._active_session = (session or "General").strip()

    def get_session(self) -> str:
        with self._lock:
            return self._active_session

    def set_auto_recognize(self, enabled: bool) -> None:
        with self._lock:
            self._auto_recognize = enabled

    def get_auto_recognize(self) -> bool:
        with self._lock:
            return self._auto_recognize

    def capture_single_frame(self) -> np.ndarray | None:
        with self._lock:
            if self._cap is not None and self._cap.isOpened():
                ok, frame = self._cap.read()
                if ok and frame is not None:
                    return frame.copy()
        # Fallback to standalone capture if stream not running
        return recognition.capture_frame_from_webcam()

    def get_jpeg_frame(self, students) -> bytes | None:
        with self._lock:
            if not self._is_running or self._cap is None:
                return None
            ok, frame = self._cap.read()
            if not ok or frame is None:
                return None
            self._frame_count += 1
            display_frame = frame.copy()
            auto_rec = self._auto_recognize
            session = self._active_session

        # Run face recognition every 4 frames when auto_recognize is enabled
        if auto_rec and students:
            if self._frame_count % 4 == 0:
                self._last_detections = main.process_frame(
                    display_frame, students, session_name=session
                )
            main.draw_detections(display_frame, self._last_detections)

        ok, jpeg = cv2.imencode(".jpg", display_frame, [int(cv2.IMWRITE_JPEG_QUALITY), 75])
        if not ok:
            return None
        return jpeg.tobytes()


camera_manager = CameraManager()


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

        students = database.get_all_students()
        frame_bytes = camera_manager.get_jpeg_frame(students)
        if frame_bytes is None:
            time.sleep(0.04)
            continue

        yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + frame_bytes + b"\r\n")
        time.sleep(0.03)  # ~30 FPS


@app.route("/video_feed")
def video_feed():
    return Response(_gen_frames(), mimetype="multipart/x-mixed-replace; boundary=frame")


@app.route("/api/camera/start", methods=["POST"])
def api_camera_start():
    data = request.get_json(silent=True) or {}
    session = data.get("session", "General")
    auto_rec = data.get("auto_recognize", False)
    started = camera_manager.start(session=session, auto_recognize=auto_rec)
    return jsonify({
        "running": started,
        "session": camera_manager.get_session(),
        "auto_recognize": camera_manager.get_auto_recognize(),
    })


@app.route("/api/camera/stop", methods=["POST"])
def api_camera_stop():
    camera_manager.stop()
    return jsonify({"running": False})


@app.route("/api/camera/status")
def api_camera_status():
    return jsonify({
        "running": camera_manager.is_running(),
        "session": camera_manager.get_session(),
        "auto_recognize": camera_manager.get_auto_recognize(),
    })


@app.route("/api/camera/toggle_recognition", methods=["POST"])
def api_camera_toggle_recognition():
    data = request.get_json(silent=True) or {}
    enabled = data.get("enabled", True)
    session = data.get("session")
    if session:
        camera_manager.set_session(session)
    camera_manager.set_auto_recognize(enabled)
    return jsonify({
        "auto_recognize": camera_manager.get_auto_recognize(),
        "session": camera_manager.get_session(),
    })


# ------------------------------------------------------------------ Sessions
@app.route("/api/sessions")
def api_sessions():
    sessions = database.get_all_sessions()
    return jsonify({"sessions": sessions, "active": camera_manager.get_session()})


@app.route("/api/sessions/active", methods=["POST"])
def api_set_active_session():
    data = request.get_json(silent=True) or {}
    session = (data.get("session") or "General").strip()
    camera_manager.set_session(session)
    return jsonify({"active": session})


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
    """Take a single snapshot, detect & recognize faces, and log attendance for active session."""
    data = request.get_json(silent=True) or {}
    session = (data.get("session") or camera_manager.get_session()).strip()

    frame = camera_manager.capture_single_frame()
    if frame is None:
        return jsonify({"error": "Could not access the webcam."}), 503

    students = database.get_all_students()
    detections = main.process_frame(frame, students, session_name=session)
    return jsonify([{"name": name, "box": list(box), "session": session} for name, box in detections])


@app.route("/api/attendance/photo", methods=["POST"])
def api_attendance_photo():
    """Take attendance from an uploaded classroom/group photo."""
    session = (request.form.get("session") or camera_manager.get_session()).strip()
    image = _read_uploaded_photo()
    if image is None:
        return jsonify({"error": "Please choose a valid image file (JPG or PNG)."}), 400

    students = database.get_all_students()
    detections = main.process_frame(image, students, cnn_fallback=True, session_name=session)
    return jsonify([{"name": name, "box": list(box), "session": session} for name, box in detections])


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
    app.run(debug=True)


if __name__ == "__main__":
    run()
