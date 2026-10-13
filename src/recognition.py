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

import os
from concurrent.futures import Executor, ProcessPoolExecutor

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


def get_face_encoding(
    image: np.ndarray, resize_factor: float = 1.0, cnn_fallback: bool = False, num_jitters: int = 1
) -> bytes | None:
    """Given an image (as returned by capture_frame_from_webcam), find the first face in it and
    return its encoding as raw bytes, ready to be stored in the database.

    `resize_factor` shrinks the image before detection (e.g. 0.25 = quarter size). Face detection
    is the slow part of this whole pipeline, and its cost grows with pixel count, so a live
    recognition loop should pass a smaller factor to stay smooth. Leave it at 1.0 (full
    resolution, the default) for enrollment, where a one-time accurate encoding matters more than
    speed.

    `cnn_fallback=True` retries with the slower but more accurate "cnn" face detector if the default
    "hog" detector finds nothing. HOG sometimes misses perfectly good faces — e.g. a tightly cropped
    ID-style photo where the face fills most of the image. CNN can take 10+ seconds on a CPU, so this
    is only worth it for one-off enrollment photos, never for a live recognition loop.

    `num_jitters` encodes the face that many times with small random shifts and averages the
    results. The stored reference then depends less on the exact framing of one photo, so live
    matches are more consistent. Each jitter costs a full encoding (~0.4 s on a laptop CPU), so 10
    takes about 4 s — fine for enrolling a student once, far too slow for live recognition.

    Returns None if no face is found in the image.
    """
    if resize_factor != 1.0:
        image = cv2.resize(image, (0, 0), fx=resize_factor, fy=resize_factor)

    # face_recognition expects RGB images; OpenCV gives us BGR, so we convert.
    rgb_image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)

    face_locations = face_recognition.face_locations(rgb_image)
    if not face_locations and cnn_fallback:
        face_locations = face_recognition.face_locations(rgb_image, model="cnn")
    if not face_locations:
        return None

    encodings = face_recognition.face_encodings(
        rgb_image, known_face_locations=face_locations[:1], num_jitters=num_jitters
    )
    if not encodings:
        return None

    # Only handle the first detected face — enrollment assumes one person per photo.
    return encodings[0].astype(ENCODING_DTYPE).tobytes()


def create_encoder_pool(workers: int | None = None) -> ProcessPoolExecutor:
    """A pool of worker processes for get_all_face_encodings(pool=...).

    Encoding a face takes ~0.45 s, and dlib doesn't let other Python threads run meanwhile, so a
    frame with 30 faces would take ~14 s on one core. Separate processes do run in parallel
    (measured 6.8x faster with 8 workers). Each worker loads the dlib models (~100 MB), so the
    default stays well below the core count. The models load when each worker starts, so the first
    pass is a little slower.
    """
    return ProcessPoolExecutor(max_workers=workers or default_encoder_workers())


def default_encoder_workers() -> int:
    """Half the CPU cores, at most 8: plenty of speed without loading the models too many times."""
    return max(1, min(8, (os.cpu_count() or 2) // 2))


def warm_up_encoder_pool(pool: ProcessPoolExecutor, workers: int) -> None:
    """Start the workers and load the models in them now (without waiting), instead of during the
    first recognition pass."""
    for _ in range(workers):
        pool.submit(_warm_up_worker)


def _warm_up_worker() -> None:
    """Runs in a worker; importing this module there has already loaded face_recognition's models."""


# A crop around a face, with this much extra margin (relative to the face size) on each side, is
# enough for dlib to find the landmarks it aligns the face with — and far less to send to a worker
# process than the whole frame.
_CROP_MARGIN = 0.6


def _encode_face_crop(crop: np.ndarray, location: tuple[int, int, int, int]) -> np.ndarray:
    """Worker-process side of the pool: encode the one face at `location` inside `crop` (RGB)."""
    return face_recognition.face_encodings(crop, known_face_locations=[location])[0]


def _encode_faces_in_parallel(
    rgb: np.ndarray, locations: list[tuple[int, int, int, int]], pool: Executor
) -> list[np.ndarray]:
    height, width = rgb.shape[:2]
    jobs = []
    for top, right, bottom, left in locations:
        margin = int(max(bottom - top, right - left) * _CROP_MARGIN)
        y0, x0 = max(0, top - margin), max(0, left - margin)
        y1, x1 = min(height, bottom + margin), min(width, right + margin)
        crop = np.ascontiguousarray(rgb[y0:y1, x0:x1])
        jobs.append(pool.submit(_encode_face_crop, crop, (top - y0, right - x0, bottom - y0, left - x0)))
    return [job.result() for job in jobs]


def get_all_face_encodings(
    image: np.ndarray, resize_factor: float = 1.0, cnn_fallback: bool = False, pool: Executor | None = None
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

    `cnn_fallback` works the same as in get_face_encoding — only use it for a single uploaded
    photo, never per-frame in a live loop.

    `pool` (from create_encoder_pool) encodes the faces in parallel; without it they are encoded
    one after another. The results are the same either way.
    """
    small_image = image
    if resize_factor != 1.0:
        small_image = cv2.resize(image, (0, 0), fx=resize_factor, fy=resize_factor)

    small_rgb = cv2.cvtColor(small_image, cv2.COLOR_BGR2RGB)
    small_face_locations = face_recognition.face_locations(small_rgb)
    if not small_face_locations and cnn_fallback:
        small_face_locations = face_recognition.face_locations(small_rgb, model="cnn")
    if not small_face_locations:
        return []

    scale = 1.0 / resize_factor
    original_locations = [
        (int(top * scale), int(right * scale), int(bottom * scale), int(left * scale))
        for top, right, bottom, left in small_face_locations
    ]

    original_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    if pool is not None and len(original_locations) > 1:
        encodings = _encode_faces_in_parallel(original_rgb, original_locations, pool)
    else:
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
    tolerance: float = 0.5,
    min_margin: float = 0.08,
) -> int | None:
    """Return the matched student_id, or None. See match_face_with_distance for the rules."""
    student_id, _ = match_face_with_distance(encoding, known_students, tolerance, min_margin)
    return student_id


def match_face_with_distance(
    encoding: bytes,
    known_students: list[tuple[int, str, bytes]],
    tolerance: float = 0.5,
    min_margin: float = 0.08,
) -> tuple[int | None, float | None]:
    """Compare a live face encoding against every enrolled student and return
    (student_id, distance) for the closest match, or (None, None) if nobody is close enough (or the
    match is too ambiguous — see below). The distance is saved with attendance as its confidence:
    lower means a surer match.

    `known_students` is a list of (student_id, name, encoding_bytes), e.g. from
    database.get_all_face_encodings(). A student may appear several times (one row per reference
    photo): each student is scored by their closest photo, so extra photos only help.

    `tolerance` is the max "distance" allowed to count as a match — lower is stricter. The
    `face_recognition` library's own commonly-cited default is 0.6, but with only a small number of
    students enrolled (a class, not a country), being stricter here matters more than the risk of an
    occasional false "Unknown" for a genuine match taken in poor lighting.

    `min_margin` guards against two different enrolled students being confused for each other: if the
    best match and the second-best match are too close together, the encoding doesn't clearly belong
    to one person more than the other (this is what "two students recognized as each other" looks
    like numerically), so we return None rather than guessing. With only one student enrolled there's
    nothing to compare against, so the margin check is skipped.
    """
    if not known_students:
        return None, None

    live_encoding = bytes_to_encoding(encoding)
    known_encodings = [bytes_to_encoding(student_encoding) for _, _, student_encoding in known_students]

    # face_distance gives one number per known encoding: how far it is from the live one.
    # Lower means more similar, so the closest match is the smallest distance.
    distances = face_recognition.face_distance(known_encodings, live_encoding)

    # Each student's score is their closest photo. Comparing per student (not per photo) matters for
    # the margin check: two photos of the SAME student are naturally close to each other, and must
    # not count as "two different people who look alike".
    closest: dict[int, float] = {}
    for (student_id, _, _), distance in zip(known_students, distances):
        closest[student_id] = min(float(distance), closest.get(student_id, float("inf")))
    ranked = sorted(closest.items(), key=lambda item: item[1])

    best_student_id, best_distance = ranked[0]
    if best_distance > tolerance:
        return None, None

    if len(ranked) > 1 and ranked[1][1] - best_distance < min_margin:
        return None, None

    return best_student_id, best_distance


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
