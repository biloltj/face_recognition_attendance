# Recognition module (Person A)
# Owns: reading the webcam feed, detecting faces, and matching them to enrolled students.
#
# Interface contract with database.py / main.py (see docs/05_collaboration_workflow.md):
#   get_face_encoding(image) -> bytes | None
#   match_face(encoding, known_students) -> int | None
#
# A face encoding is a list of 128 numbers that describes a face; two encodings from the same
# person come out numerically close together, two different people's come out far apart. We store
# it as raw bytes (float64 array) since that's what fits in the database's BLOB column.

from __future__ import annotations

import cv2
import face_recognition
import numpy as np

ENCODING_DTYPE = np.float64  # face_recognition always returns float64 arrays of length 128


def capture_frame_from_webcam(camera_index: int = 0) -> np.ndarray | None:
    """Open the webcam, grab a single frame, and return it as a BGR image array (OpenCV's format).

    Returns None if the camera can't be opened or a frame can't be read.
    """
    cap = cv2.VideoCapture(camera_index, cv2.CAP_DSHOW)
    if not cap.isOpened():
        cap.release()
        return None

    ok, frame = cap.read()
    cap.release()

    if not ok or frame is None:
        return None
    return frame


def frames_from_webcam(camera_index: int = 0, width: int | None = None, height: int | None = None):
    """Open the webcam once and yield frames continuously, for an efficient real-time loop.

    Unlike capture_frame_from_webcam (which opens/closes the camera per call — fine for a single
    enrollment photo), this keeps the camera open across frames. Stop iterating (e.g. `break`) to
    close the camera. Yields nothing if the camera can't be opened.

    `width`/`height` request a capture resolution from the camera (e.g. 1280x720 instead of its
    default, often 640x480) — more pixels means more people fit in frame, and faces farther from
    the camera still have enough detail to recognize. The camera may not honor the exact values;
    OpenCV falls back to the closest resolution it supports.
    """
    cap = cv2.VideoCapture(camera_index, cv2.CAP_DSHOW)
    if not cap.isOpened():
        cap.release()
        return

    if width is not None:
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
    if height is not None:
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)

    try:
        while True:
            ok, frame = cap.read()
            if not ok or frame is None:
                break
            yield frame
    finally:
        cap.release()


def get_face_encoding(image: np.ndarray, resize_factor: float = 1.0) -> bytes | None:
    """Given an image (as returned by capture_frame_from_webcam), find the first face in it and
    return its encoding as raw bytes, ready to be stored in the database.

    `resize_factor` shrinks the image before detection (e.g. 0.25 = quarter size). Face detection
    is the slow part of this whole pipeline, and its cost grows with pixel count, so a live
    recognition loop should pass a smaller factor to stay smooth. Leave it at 1.0 (full
    resolution, the default) for enrollment, where a one-time accurate encoding matters more than
    speed.

    Returns None if no face is found in the image.
    """
    if resize_factor != 1.0:
        image = cv2.resize(image, (0, 0), fx=resize_factor, fy=resize_factor)

    # face_recognition expects RGB images; OpenCV gives us BGR, so we convert.
    rgb_image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)

    face_locations = face_recognition.face_locations(rgb_image)
    if not face_locations:
        return None

    encodings = face_recognition.face_encodings(rgb_image, known_face_locations=face_locations)
    if not encodings:
        return None

    # Only handle the first detected face — enrollment assumes one person per photo.
    return encodings[0].astype(ENCODING_DTYPE).tobytes()


def get_all_face_encodings(
    image: np.ndarray, resize_factor: float = 1.0
) -> list[tuple[bytes, tuple[int, int, int, int]]]:
    """Like get_face_encoding, but finds and encodes every face in the image — for recognizing
    multiple students (e.g. a group, or a whole classroom) in a single frame.

    Returns a list of (encoding_bytes, face_location) tuples, one per detected face. Each
    face_location is (top, right, bottom, left) in the ORIGINAL image's coordinates — already
    scaled back up if resize_factor < 1.0 — so it can be used to draw a box around that face.
    Returns an empty list if no faces are found.

    Detection runs on the shrunk image for speed, but encoding runs on the full-resolution
    original — an encoding computed from a tiny, low-detail crop doesn't match well against a
    full-resolution enrollment photo, so shrinking before encoding (not just before detection)
    would make recognition unreliable.
    """
    small_image = image
    if resize_factor != 1.0:
        small_image = cv2.resize(image, (0, 0), fx=resize_factor, fy=resize_factor)

    small_rgb = cv2.cvtColor(small_image, cv2.COLOR_BGR2RGB)
    small_face_locations = face_recognition.face_locations(small_rgb)
    if not small_face_locations:
        return []

    scale = 1.0 / resize_factor
    original_locations = [
        (int(top * scale), int(right * scale), int(bottom * scale), int(left * scale))
        for top, right, bottom, left in small_face_locations
    ]

    original_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    encodings = face_recognition.face_encodings(original_rgb, known_face_locations=original_locations)

    return [
        (encoding.astype(ENCODING_DTYPE).tobytes(), location)
        for encoding, location in zip(encodings, original_locations)
    ]


def bytes_to_encoding(encoding_bytes: bytes) -> np.ndarray:
    """Reverse of get_face_encoding's byte conversion — turns stored bytes back into a usable array."""
    return np.frombuffer(encoding_bytes, dtype=ENCODING_DTYPE)


def match_face(
    encoding: bytes,
    known_students: list[tuple[int, str, bytes]],
    tolerance: float = 0.6,
) -> int | None:
    """Compare a live face encoding against every enrolled student and return the closest match's
    student_id, or None if nobody is close enough.

    `known_students` is the list returned by database.get_all_students(): (student_id, name, encoding_bytes).
    `tolerance` is the max "distance" allowed to count as a match — lower is stricter. 0.6 is the
    commonly recommended default for the face_recognition library.
    """
    if not known_students:
        return None

    live_encoding = bytes_to_encoding(encoding)
    known_encodings = [bytes_to_encoding(student_encoding) for _, _, student_encoding in known_students]

    # face_distance gives one number per known encoding: how far it is from the live one.
    # Lower means more similar, so the closest match is the smallest distance.
    distances = face_recognition.face_distance(known_encodings, live_encoding)
    best_index = int(np.argmin(distances))

    if distances[best_index] > tolerance:
        return None

    student_id, _, _ = known_students[best_index]
    return student_id


if __name__ == "__main__":
    # Quick manual test: capture your own face from the webcam and confirm an encoding is produced.
    # Run with: python src/recognition.py
    print("Capturing a frame from the webcam...")
    frame = capture_frame_from_webcam()
    if frame is None:
        print("Could not access the webcam.")
    else:
        print(f"Captured frame with shape {frame.shape}. Looking for a face...")
        encoding = get_face_encoding(frame)
        if encoding is None:
            print("No face detected. Make sure your face is visible to the camera and try again.")
        else:
            array = bytes_to_encoding(encoding)
            print(f"Face detected. Encoding has {len(array)} numbers, e.g. first 5: {array[:5]}")
