"""
Threaded Camera Capture & Real-Time Recognition Overlay
Dii Portal Face Recognition Attendance System
"""

import cv2
import time
import threading
import numpy as np
import face_recognition
from typing import Optional, Tuple, List, Dict

from config import FACE_MATCH_THRESHOLD, SESSION_DURATION_SECONDS
from core.session_manager import session_manager, ActiveSession
from core.face_engine import match_face_against_roster
from core.liveness import calculate_eye_aspect_ratio, BlinkDetector


class ThreadedCamera:
    """
    Multi-threaded OpenCV camera stream:
    - Background thread continuously acquires webcam frames to prevent buffer latency.
    - Runs face detection and roster matching on throttled frames (every 3rd frame) for high FPS.
    - Renders countdown timer, session banner, and student name bounding boxes.
    - Automatically stops when 10-minute session expires.
    """

    def __init__(self, src: int = 0):
        self.src = src
        self.cap = cv2.VideoCapture(self.src, cv2.CAP_DSHOW) if cv2.CAP_DSHOW else cv2.VideoCapture(self.src)
        self.is_running = False
        self.lock = threading.Lock()
        self.current_frame: Optional[np.ndarray] = None
        self.display_frame: Optional[np.ndarray] = None
        self._thread: Optional[threading.Thread] = None

        # Tracking state
        self.blink_detectors: Dict[str, BlinkDetector] = {}
        self.recent_faces: List[Dict] = []
        self.frame_count = 0

    def start(self) -> None:
        """Starts background frame acquisition thread."""
        if self.is_running:
            return
        if not self.cap.isOpened():
            self.cap.open(self.src)

        self.is_running = True
        self._thread = threading.Thread(target=self._capture_and_process_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Stops camera capture thread and releases device."""
        self.is_running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)
        if self.cap and self.cap.isOpened():
            self.cap.release()

    def _capture_and_process_loop(self) -> None:
        """Background loop continuously reading frames and performing recognition."""
        while self.is_running:
            active_session = session_manager.current_session

            # Check if 10-minute session has auto-expired
            if active_session and active_session.has_expired():
                session_manager.stop_current_session()
                self.is_running = False
                break

            ret, frame = self.cap.read()
            if not ret:
                time.sleep(0.01)
                continue

            self.frame_count += 1
            # Perform neural recognition every 3rd frame to conserve CPU and maintain 30 FPS
            if self.frame_count % 3 == 0 and active_session and active_session.roster:
                self._recognize_faces_in_frame(frame, active_session)

            # Draw visual overlays (countdown, bounding boxes)
            annotated_frame = self._render_overlays(frame.copy(), active_session)

            with self.lock:
                self.current_frame = frame
                self.display_frame = annotated_frame

            time.sleep(0.01)

        if self.cap and self.cap.isOpened():
            self.cap.release()

    def _recognize_faces_in_frame(self, frame: np.ndarray, session: ActiveSession) -> None:
        """Detects faces in frame and compares against active session roster."""
        # Scale frame down to 0.25 size for 4x faster neural processing
        small_frame = cv2.resize(frame, (0, 0), fx=0.25, fy=0.25)
        rgb_small = cv2.cvtColor(small_frame, cv2.COLOR_BGR2RGB)

        face_locations = face_recognition.face_locations(rgb_small, model="hog")
        face_encodings = face_recognition.face_encodings(rgb_small, face_locations)

        detected = []
        for (top, right, bottom, left), face_enc in zip(face_locations, face_encodings):
            # Scale coordinates back up to original frame dimensions
            top *= 4
            right *= 4
            bottom *= 4
            left *= 4

            match = match_face_against_roster(face_enc.astype(np.float64), session.roster, threshold=FACE_MATCH_THRESHOLD)
            if match:
                s_id, s_code, full_name, distance = match
                # Record attendance in database
                is_new = session_manager.record_attendance(s_id, confidence_score=distance)
                detected.append({
                    "box": (top, right, bottom, left),
                    "name": full_name,
                    "code": s_code,
                    "distance": distance,
                    "matched": True,
                    "is_new": is_new
                })
            else:
                detected.append({
                    "box": (top, right, bottom, left),
                    "name": "Unregistered",
                    "code": "N/A",
                    "distance": 1.0,
                    "matched": False,
                    "is_new": False
                })

        self.recent_faces = detected

    def _render_overlays(self, frame: np.ndarray, session: Optional[ActiveSession]) -> np.ndarray:
        """Draws bounding boxes, labels, and 10-minute timer banner onto video frame."""
        h, w = frame.shape[:2]

        # 1. Top HUD Banner
        cv2.rectangle(frame, (0, 0), (w, 50), (20, 20, 20), -1)

        if session and session.is_active:
            mins, secs = divmod(int(session.remaining_seconds), 60)
            timer_text = f"SESSION TIME: {mins:02d}:{secs:02d}"
            info_text = f"Course: {session.course_id} | Session: {session.session_id}"
            timer_color = (0, 255, 0) if session.remaining_seconds > 60 else (0, 0, 255)
        else:
            timer_text = "SESSION: INACTIVE / COMPLETED"
            info_text = "Press 'Start Session' to begin attendance."
            timer_color = (0, 165, 255)

        cv2.putText(frame, timer_text, (20, 35), cv2.FONT_HERSHEY_SIMPLEX, 0.8, timer_color, 2)
        cv2.putText(frame, info_text, (w - 550, 35), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (220, 220, 220), 1)

        # 2. Draw face bounding boxes
        for face in self.recent_faces:
            top, right, bottom, left = face["box"]
            color = (0, 220, 0) if face["matched"] else (0, 0, 230)

            # Draw box around face
            cv2.rectangle(frame, (left, top), (right, bottom), color, 2)

            # Draw label banner
            label = f"{face['name']} ({face['code']})" if face["matched"] else "Unknown Student"
            cv2.rectangle(frame, (left, bottom - 25), (right, bottom), color, -1)
            cv2.putText(frame, label, (left + 6, bottom - 6), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)

        return frame

    def get_latest_frame_bytes(self) -> Optional[bytes]:
        """Encodes latest annotated display frame to JPEG bytes for MJPEG streaming."""
        with self.lock:
            frame = self.display_frame if self.display_frame is not None else self.current_frame

        if frame is None:
            return None

        ret, buffer = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
        if not ret:
            return None
        return buffer.tobytes()
