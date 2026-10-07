"""
Core Computer Vision & Session Engine Package
Dii Portal Face Recognition Attendance System
"""

from core.face_engine import (
    load_and_preprocess_image,
    extract_face_embedding,
    compute_euclidean_distance,
    match_face_against_roster,
)
from core.session_manager import (
    ActiveSession,
    SessionManager,
    session_manager,
)
from core.liveness import (
    calculate_eye_aspect_ratio,
    BlinkDetector,
)
from core.camera import ThreadedCamera

__all__ = [
    "load_and_preprocess_image",
    "extract_face_embedding",
    "compute_euclidean_distance",
    "match_face_against_roster",
    "ActiveSession",
    "SessionManager",
    "session_manager",
    "calculate_eye_aspect_ratio",
    "BlinkDetector",
    "ThreadedCamera",
]
