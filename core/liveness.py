"""
Liveness Detection - Anti-Spoofing via Eye Aspect Ratio (EAR)
Dii Portal Face Recognition Attendance System
"""

import numpy as np
from typing import List, Tuple, Dict, Any
from config import EAR_BLINK_THRESHOLD, EAR_CONSEC_FRAMES


def calculate_eye_aspect_ratio(eye_landmarks: List[Tuple[int, int]]) -> float:
    """
    Calculates Eye Aspect Ratio (EAR) based on 6 landmark coordinates:
    p1: outer corner, p4: inner corner
    p2, p3: top eyelid points
    p5, p6: bottom eyelid points

    Formula:
        EAR = ( ||p2 - p6|| + ||p3 - p5|| ) / ( 2 * ||p1 - p4|| )

    Interpretation:
    - Open eye: EAR is typically between 0.25 and 0.35
    - Closed eye (blink): EAR drops below EAR_BLINK_THRESHOLD (~0.22)
    """
    if len(eye_landmarks) < 6:
        return 0.0

    p = [np.array(pt, dtype=np.float64) for pt in eye_landmarks]

    # Vertical distances between upper and lower eyelids
    vertical_1 = np.linalg.norm(p[1] - p[5])
    vertical_2 = np.linalg.norm(p[2] - p[4])

    # Horizontal distance between eye corners
    horizontal = np.linalg.norm(p[0] - p[3])

    if horizontal == 0:
        return 0.0

    ear = (vertical_1 + vertical_2) / (2.0 * horizontal)
    return float(ear)


class BlinkDetector:
    """
    Tracks consecutive frames where EAR is below threshold to detect natural blinks.
    Prevents static photo attacks.
    """

    def __init__(self, threshold: float = EAR_BLINK_THRESHOLD, consec_frames: int = EAR_CONSEC_FRAMES):
        self.threshold = threshold
        self.consec_frames = consec_frames
        self.frame_counter = 0
        self.total_blinks = 0

    def update(self, left_eye: List[Tuple[int, int]], right_eye: List[Tuple[int, int]]) -> bool:
        """
        Processes eye landmarks from current frame.
        Returns True if a valid blink was completed on this frame.
        """
        left_ear = calculate_eye_aspect_ratio(left_eye)
        right_ear = calculate_eye_aspect_ratio(right_eye)
        avg_ear = (left_ear + right_ear) / 2.0

        if avg_ear < self.threshold:
            # Eye is closed
            self.frame_counter += 1
        else:
            # Eye is open
            if self.frame_counter >= self.consec_frames:
                self.total_blinks += 1
                self.frame_counter = 0
                return True
            self.frame_counter = 0

        return False

    def is_verified_live(self) -> bool:
        """Returns True if at least 1 natural blink was observed."""
        return self.total_blinks >= 1
