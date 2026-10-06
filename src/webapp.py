# Web app module
# Owns: a small Flask server exposing enrollment, "take a snapshot and recognize" attendance, and
# the attendance log/export as a JSON API, with a single dashboard page as the frontend.
#
# This module doesn't add new attendance logic of its own — same as gui.py, it only wires together
# the modules that already own that logic: enrollment.py, recognition.py, database.py, export.py,
# and main.py's process_frame(). There's no browser webcam involved: "Take Attendance" is a button
# that tells this server (which runs on the same machine as the camera) to grab one frame from the
# webcam itself, exactly like the terminal app does.
#
# Enrollment and attendance can also be done from an uploaded photo instead of the webcam (e.g. a
# student's ID photo for enrollment, or a class group photo for attendance). The uploaded image is
# decoded into the same kind of array the webcam gives us, so the rest of the pipeline is identical.

from __future__ import annotations

import cv2
import numpy as np
from flask import Flask, jsonify, render_template, request, send_file

import database
import enrollment
import export
import main
import recognition

app = Flask(__name__)

# Reject uploads bigger than this before they're even read — a phone photo is usually 2-8 MB.
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024

# Phone photos can be 4000+ pixels wide, which makes face detection take many seconds. Shrinking
# anything larger down to this keeps it fast while leaving faces plenty of detail to recognize.
MAX_PHOTO_SIDE = 1600


def _read_uploaded_photo():
    """Decode the uploaded "photo" file into a BGR image array (the same format the webcam gives),
    or return None if no file was sent or it isn't a readable image.
    """
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


@app.route("/api/enroll", methods=["POST"])
def api_enroll():
    """Enroll the person currently in front of the (server's) webcam under the given name.

    Body: {"name": "..."}. This blocks for a moment — enroll_student() retries a few times against
    the webcam if a face isn't found immediately, same as the terminal script.
    """
    data = request.get_json(silent=True) or {}
    name = data.get("name", "")

    result = enrollment.enroll_student(name)
    return jsonify(result._asdict())


@app.route("/api/enroll/photo", methods=["POST"])
def api_enroll_photo():
    """Enroll a student from an uploaded photo instead of the webcam.

    Form data: "name" (text) and "photo" (image file). The photo should show one person — if it
    has several faces, only the first one found is used. If the fast face detector misses the face,
    a slower, more accurate one is tried, so this can take ~10-20 seconds for an unusual photo.
    """
    name = request.form.get("name", "")
    image = _read_uploaded_photo()
    if image is None:
        return jsonify({"student_id": None, "error": "Please choose a valid image file (JPG or PNG)."}), 400

    result = enrollment.enroll_from_frame(name, image, cnn_fallback=True)
    return jsonify(result._asdict())


@app.route("/api/students")
def api_students():
    """List enrolled students (id + name only — the face encoding isn't useful to a browser)."""
    students = database.get_all_students()
    return jsonify([{"student_id": sid, "name": name} for sid, name, _ in students])


@app.route("/api/attendance/capture", methods=["POST"])
def api_attendance_capture():
    """The "Take Attendance" button: capture one frame from the webcam, recognize every face in
    it, and log attendance for each match (same duplicate-window rule as everywhere else).

    Returns a JSON list of {"name": ..., "box": [top, right, bottom, left]} — one per face found.
    An empty list means no face was in frame; the dashboard just reports that so the tutor can
    click the button again rather than treating it as an error.
    """
    frame = recognition.capture_frame_from_webcam()
    if frame is None:
        return jsonify({"error": "Could not access the webcam."}), 503

    students = database.get_all_students()
    detections = main.process_frame(frame, students)
    return jsonify([{"name": name, "box": list(box)} for name, box in detections])


@app.route("/api/attendance/photo", methods=["POST"])
def api_attendance_photo():
    """Take attendance from an uploaded photo (e.g. a group photo of the class): recognize every
    face in it and log attendance for each match. Same response format as /api/attendance/capture.
    """
    image = _read_uploaded_photo()
    if image is None:
        return jsonify({"error": "Please choose a valid image file (JPG or PNG)."}), 400

    students = database.get_all_students()
    detections = main.process_frame(image, students, cnn_fallback=True)
    return jsonify([{"name": name, "box": list(box)} for name, box in detections])


@app.route("/api/attendance")
def api_attendance():
    """The full attendance log as JSON, most recent first."""
    rows = database.get_attendance_log()
    return jsonify([{"student": name, "timestamp": timestamp} for name, timestamp in rows])


@app.route("/api/attendance/export.csv")
def api_attendance_export():
    """Download the attendance log as a CSV file (reuses export.py's writer)."""
    path = export.export_attendance_csv()
    return send_file(path, as_attachment=True, download_name=path.name)


def run() -> None:
    database.init_db()
    app.run(debug=True)


if __name__ == "__main__":
    run()
