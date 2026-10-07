# 🎥 Dii Portal Face Recognition Attendance System

An automated, contactless biometric attendance logging platform engineered for university lectures and deeply integrated with the **Dii University Portal API**.

---

## 📌 Project Overview

The **Dii Portal Face Recognition Attendance System** automates student attendance tracking in university classrooms. Using real-time facial recognition and anti-spoofing verification, the system identifies enrolled students, maps them dynamically to specific course sessions, and automatically syncs attendance records with the university's Dii Portal REST API.

---

## ⚡ Core Operational Workflows

### 1. 🖼 Automatic IT Portal Photo Enrollment & Embedding Sync
Instead of manually collecting student photos locally, the system interfaces directly with the Dii IT Portal photo database:
* **API / Bulk Photo Fetch:** Imports official student profile photos registered in the IT portal for all students enrolled in a target course.
* **Vector Encoding:** Computes 128-dimensional ResNet face embedding vectors upon initial enrollment or scheduled syncs.
* **Local Caching:** Caches vector encodings in a local SQLite database (`database/db.py`) for ultra-fast, offline-capable matching during live streams.

### 2. ⏱ 10-Minute Session-Based Attendance Window
Attendance is captured within focused, timed session windows to prevent proxy attendance and reduce CPU overhead:
* **Lecturer Trigger:** The professor clicks **"Start Attendance"** on the Dii Portal or local web control panel.
* **10-Minute Active Stream:** The background multi-threaded camera module (`core/camera.py`) and recognition engine (`core/face_engine.py`) run for exactly 10 minutes (600 seconds) with an active countdown timer.
* **Real-Time Identification & Debouncing:** Identified students are verified, debounced, and logged once per session for the specific `session_id` and `course_id`.
* **Auto-Lock & Sync:** At the 10-minute mark, the camera stream locks, closes the active capture loop, and transmits final attendance payloads to the Dii Portal.

### 3. 🆔 Dynamic Course & Session Isolation
* **Unique Identification:** Every lecture slot generates a distinct `session_id` tied to a specific `course_id` (e.g., `COURSE_CS401 / SESSION_20261007_0900`).
* **Isolated Match Lists:** During a session, recognition compares live camera frames **only** against students enrolled in that specific course, drastically improving speed, reducing vector search overhead, and eliminating cross-course false positives.
* **Multi-Lecture Support:** Ensures attendance recorded today is strictly isolated from next week's lecture or concurrent classes in adjacent rooms.

---

## 🏗 System Architecture

```text
┌──────────────────────────┐      ┌──────────────────────────┐
│  Dii IT Portal Database  │      │  Lecturer Control Panel  │
│  (Student Profile Photos)│      │  ["Start Attendance"]    │
└─────────────┬────────────┘      └────────────┬─────────────┘
              │ Sync Photos                    │ 10-Min Trigger
              ▼                                ▼
┌──────────────────────────┐      ┌──────────────────────────┐
│ Face Embedding Engine    │      │ Multi-Threaded Camera    │
│ (128-d Vector Generator) │      │ (10-Minute Capture Loop) │
└─────────────┬────────────┘      └────────────┬─────────────┘
              │                                │
              └───────────────┬────────────────┘
                              ▼
                 ┌──────────────────────────┐
                 │ Local Verification Loop  │
                 │ (Vector Distance & EAR)  │
                 └────────────┬─────────────┘
                              │
                              ▼
                 ┌──────────────────────────┐
                 │ Dii Portal Sync Queue    │
                 │ (Session Attendance Log) │
                 └──────────────────────────┘
```

---

## 🛠 Tech Stack

* **Core Language:** Python 3.10+
* **Computer Vision & ML:** OpenCV (`cv2`), `face_recognition` (dlib / ResNet embeddings), NumPy
* **Backend Framework:** FastAPI / Uvicorn (or Flask)
* **Database & Storage:** SQLite3 (Schema: `students`, `courses`, `course_students`, `sessions`, `attendance`)
* **API Communication:** `httpx` / `asyncio` (Async JWT auth, photo downloader, Dii Portal REST poster)

---

## 📂 Repository Directory Structure

```text
face_recognition_attendance/
├── config.py                 # System parameters (10-min duration, thresholds, API endpoints)
├── main.py                   # Main entry point and server initialization
├── core/
│   ├── __init__.py
│   ├── camera.py             # Multi-threaded camera frame capture with 10-min timer
│   ├── face_engine.py        # 128-d vector generation, face matching & roster filtering
│   └── liveness.py           # Anti-spoofing (blink & motion verification)
├── database/
│   ├── __init__.py
│   ├── db.py                 # SQLite schema initialization, migrations, & transactional logs
│   └── models.py             # Data schemas (Student, Course, Session, AttendanceRecord)
├── api/
│   ├── __init__.py
│   ├── dii_client.py         # Dii Portal photo fetcher, JWT auth, & attendance sync poster
│   └── routes.py             # Web endpoints (`POST /session/start`, `GET /stream`, `GET /results`)
├── ui/
│   ├── static/               # Overlay styling, JS timers, and live feed scripts
│   └── templates/            # Lecturer portal with 10-minute countdown dashboard
├── data/
│   ├── encodings.pkl         # Cached student face embedding vectors
│   └── local_db.sqlite       # Local database store
├── tests/                    # Automated unit tests for DB, sessions, and engine
├── requirements.txt          # Project dependencies
└── README.md                 # Complete project documentation
```

---

## 🗓 Accelerated 19-Day Completion Roadmap (Oct 7 – Oct 25, 2026)

### Phase 1: Data Foundation & Portal Photo Enrollment (Oct 7 – Oct 11)
| Date | Day | Deliverable / Task | Milestone |
| :--- | :---: | :--- | :--- |
| **7 Oct** | Wed | Redesign DB schema (`students`, `courses`, `course_students`, `sessions`, `attendance`) in `database/db.py`. | |
| **8 Oct** | Thu | Build `portal_import.py` to ingest student photos/IDs and compute 128-d face embedding vectors. | |
| **9 Oct** | Fri | Implement photo quality controls (resizing, auto-orient, detection retries for unreadable images). | |
| **10 Oct** | Sat | Build vector caching layer (`data/encodings.pkl` + SQLite storage). | |
| **11 Oct** | Sun | **Test bulk enrollment pipeline with 20–30 IT portal photos.** | 🏁 **Milestone 1: Photo Vector Sync** |

### Phase 2: 10-Minute Capture Engine & Roster Isolation (Oct 12 – Oct 16)
| Date | Day | Deliverable / Task | Milestone |
| :--- | :---: | :--- | :--- |
| **12 Oct** | Mon | Build `session_manager.py` for generating dynamic `session_id` and course-specific student isolation. | |
| **13 Oct** | Tue | Implement 10-minute countdown camera thread (`core/camera.py`) with 600s auto-stop. | |
| **14 Oct** | Wed | Connect `core/face_engine.py` to match live frames strictly against active course roster. | |
| **15 Oct** | Thu | Implement liveness check (`core/liveness.py`) & debounced attendance logging per session. | |
| **16 Oct** | Fri | **CLI End-to-End Session Test (10-minute run with local persistence).** | 🏁 **Milestone 2: 10-Min Capture Engine** |

### Phase 3: Lecturer Web Dashboard & Live Overlay UI (Oct 17 – Oct 20)
| Date | Day | Deliverable / Task | Milestone |
| :--- | :---: | :--- | :--- |
| **17 Oct** | Sat | Build FastAPI backend endpoints (`POST /session/start`, `GET /session/status`, `GET /results`). | |
| **18 Oct** | Sun | Implement real-time MJPEG video stream endpoint (`GET /stream`) with live timer overlay. | |
| **19 Oct** | Mon | Create Lecturer Control Dashboard with course dropdown, **"Take Attendance"** button, and live student checklist. | |
| **20 Oct** | Tue | **Add professor manual overrides & CSV/Excel export module.** | 🏁 **Milestone 3: Complete Web UI** |

### Phase 4: Dii Portal REST Sync, Stress Test & Release (Oct 21 – Oct 25)
| Date | Day | Deliverable / Task | Milestone |
| :--- | :---: | :--- | :--- |
| **21 Oct** | Wed | Build `api/dii_client.py` for async JWT authentication and batch attendance posting. | |
| **22 Oct** | Thu | Write automated unit tests in `tests/` for DB integrity, session timers, and vector distance matching. | |
| **23 Oct** | Fri | Classroom trial run: multi-student recognition under classroom lighting & threshold tuning. | |
| **24 Oct** | Sat | Final code polish, documentation freeze, and demonstration video recording. | |
| **25 Oct** | Sun | **PRODUCTION RELEASE & FINAL PROJECT DELIVERY 🎉** | 🚀 **Final Completion** |

---

## 🚦 Quick Start

### 1. Setup Environment
```bash
git clone https://github.com/biloltj/face_recognition_attendance.git
cd face_recognition_attendance
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configuration (`.env`)
```ini
DII_PORTAL_BASE_URL=https://dii.university.edu/api/v1
DII_API_KEY=your_university_api_key_here
SESSION_DURATION_SECONDS=600
FACE_MATCH_THRESHOLD=0.50
LOCAL_DB_PATH=data/local_db.sqlite
```

### 3. Start System
```bash
python main.py
```
Access the lecturer control dashboard at `http://localhost:8000`.

---

## 🤝 Author
* **Author:** Bilol Arzykulov (Bilol T.)
* **Target Completion Date:** October 25, 2026