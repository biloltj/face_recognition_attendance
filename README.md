# Face Recognition Attendance System

A capstone project: a webcam-based system that recognizes enrolled students' faces and automatically
logs their attendance to a local database.

## Team
- Bilol Arzykulov — Recognition module
- Ayub Timurov — Data module & documentation

## Project Documents
See the [`docs/`](docs) folder for the full software-engineering documentation:
- [`01_requirements.md`](docs/01_requirements.md) — functional & non-functional requirements
- [`02_design.md`](docs/02_design.md) — architecture, tech stack, database schema
- [`03_sprint_plan.md`](docs/03_sprint_plan.md) — Agile sprint plan
- [`04_test_plan.md`](docs/04_test_plan.md) — test plan and results

## Folder Structure
```
face_recognition_attendance/
├── docs/                  Software engineering documentation
├── src/                   Application source code
│   ├── enrollment.py      Capture & store a student's face
│   ├── recognition.py     Detect & recognize faces from the webcam
│   ├── database.py        SQLite schema + attendance logging
│   └── main.py            Entry point
├── tests/                 Unit tests (mirrors src/)
├── data/                  Local runtime data (ignored by git, except folder structure)
│   └── enrolled_photos/   Captured enrollment photos (not committed — personal data)
├── requirements.txt       Python dependencies
└── README.md
```

## Setup
1. Install Python 3.9+ and a webcam-equipped machine.
2. Create and activate a virtual environment:
   ```
   python -m venv venv
   venv\Scripts\activate   (Windows)
   ```
3. Install dependencies:
   ```
   pip install -r requirements.txt
   ```
4. Run the application:
   ```
   python src/main.py
   ```

## Status
Project is in Sprint 1 (see `docs/03_sprint_plan.md`). Core modules are stubs pending implementation.
