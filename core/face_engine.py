"""
Face Engine - 128-d Vector Generation & Roster Matching
Dii Portal Face Recognition Attendance System
"""

import cv2
import numpy as np
import face_recognition
from typing import Optional, List, Tuple, Union
from pathlib import Path
from config import FACE_MATCH_THRESHOLD


def load_and_preprocess_image(image_input: Union[str, Path, np.ndarray]) -> np.ndarray:
    """
    Loads an image from path or accepts an existing numpy array,
    normalizes color format to RGB, and resizes if overly large.

    Why RGB conversion is mandatory:
    - OpenCV loads images in BGR format (Blue, Green, Red).
    - dlib and face_recognition neural networks expect RGB (Red, Green, Blue).
    - Feeding BGR directly into face_recognition degrades embedding accuracy!
    """
    if isinstance(image_input, (str, Path)):
        path_str = str(image_input)
        # Read image with OpenCV
        img = cv2.imread(path_str)
        if img is None:
            raise ValueError(f"Could not read image file at: {path_str}")
        rgb_img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    elif isinstance(image_input, np.ndarray):
        if len(image_input.shape) == 2:
            # Grayscale -> RGB
            rgb_img = cv2.cvtColor(image_input, cv2.COLOR_GRAY2RGB)
        elif image_input.shape[2] == 4:
            # RGBA -> RGB
            rgb_img = cv2.cvtColor(image_input, cv2.COLOR_BGRA2RGB)
        elif image_input.shape[2] == 3:
            # Assume BGR if coming from cv2 capture
            rgb_img = cv2.cvtColor(image_input, cv2.COLOR_BGR2RGB)
        else:
            rgb_img = image_input
    else:
        raise TypeError(f"Unsupported image input type: {type(image_input)}")

    # Downscale overly large photos to max 1280px on longest edge to boost inference speed
    max_dim = 1280
    h, w = rgb_img.shape[:2]
    if max(h, w) > max_dim:
        scale = max_dim / float(max(h, w))
        new_w, new_h = int(w * scale), int(h * scale)
        rgb_img = cv2.resize(rgb_img, (new_w, new_h), interpolation=cv2.INTER_AREA)

    return rgb_img


def extract_face_embedding(
    image_input: Union[str, Path, np.ndarray],
    model: str = "hog"
) -> Optional[np.ndarray]:
    """
    Detects a face in the image and generates a 128-dimensional ResNet embedding vector.

    - model: 'hog' (fast, CPU-friendly) or 'cnn' (GPU-accelerated, slower on CPU).
    - If multiple faces exist in an ID photo, selects the largest face bounding box.
    - Returns: 128-d numpy array of shape (128,) with float64 values, or None if no face found.
    """
    rgb_img = load_and_preprocess_image(image_input)

    # 1. Detect face bounding boxes: [(top, right, bottom, left), ...]
    face_locations = face_recognition.face_locations(rgb_img, model=model)
    
    # Retry with upsampling if no face found on first pass (helps with smaller or angled faces)
    if not face_locations:
        face_locations = face_recognition.face_locations(rgb_img, number_of_times_to_upsample=2, model=model)
        
    if not face_locations:
        return None

    # 2. If multiple faces exist, pick the primary subject (largest area)
    if len(face_locations) > 1:
        face_locations = sorted(
            face_locations,
            key=lambda loc: (loc[2] - loc[0]) * (loc[1] - loc[3]),
            reverse=True
        )

    primary_face = [face_locations[0]]

    # 3. Compute 128-dimensional embedding vector
    encodings = face_recognition.face_encodings(rgb_img, known_face_locations=primary_face)
    if not encodings:
        return None

    return encodings[0].astype(np.float64)


def compute_euclidean_distance(vector_a: np.ndarray, vector_b: np.ndarray) -> float:
    """
    Calculates Euclidean Distance between two 128-dimensional face vectors:
        distance = sqrt( sum( (a_i - b_i)^2 ) )

    Interpretation:
    - Distance == 0.0: Exact identical face
    - Distance < 0.50: Strong match (same person)
    - Distance >= 0.50: Different person (impostor)
    """
    return float(np.linalg.norm(vector_a - vector_b))


def match_face_against_roster(
    live_embedding: np.ndarray,
    roster: List[Tuple[int, str, str, np.ndarray]],
    threshold: float = FACE_MATCH_THRESHOLD
) -> Optional[Tuple[int, str, str, float]]:
    """
    Compares a live face embedding against the course roster.

    Parameters:
    - live_embedding: 128-d vector from current camera frame.
    - roster: List of tuples (student_id, student_code, full_name, stored_vector).
    - threshold: Cutoff distance (default 0.50).

    Returns:
    - (student_id, student_code, full_name, min_distance) if a valid match is found below threshold.
    - None if no student in the roster matches within threshold.
    """
    if not roster:
        return None

    best_match = None
    min_dist = float("inf")

    for s_id, s_code, full_name, stored_vector in roster:
        dist = compute_euclidean_distance(live_embedding, stored_vector)
        if dist < min_dist:
            min_dist = dist
            best_match = (s_id, s_code, full_name, min_dist)

    if best_match and min_dist <= threshold:
        return best_match

    return None
