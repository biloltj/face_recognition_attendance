"""
System Configuration Parameters
Dii Portal Face Recognition Attendance System
"""

import os
from pathlib import Path

# Base Paths
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

# Database Configuration
LOCAL_DB_PATH = DATA_DIR / "local_db.sqlite"

# Attendance & Vision Configuration
SESSION_DURATION_SECONDS = 600  # 10 minutes active window
FACE_MATCH_THRESHOLD = 0.50     # Euclidean distance threshold (lower is stricter)
EAR_BLINK_THRESHOLD = 0.22      # Eye Aspect Ratio threshold for liveness
EAR_CONSEC_FRAMES = 2           # Consecutive frames eye must be below threshold

# Dii IT Portal API Configuration (Simulated / Staging)
DII_PORTAL_BASE_URL = os.getenv("DII_PORTAL_BASE_URL", "https://dii.university.edu/api/v1")
DII_API_KEY = os.getenv("DII_API_KEY", "mock-portal-key-2026")
