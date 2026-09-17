# 🎓 Face Recognition Attendance System

![Python](https://img.shields.io/badge/Python-3.9+-3776AB?logo=python&logoColor=white)
![OpenCV](https://img.shields.io/badge/OpenCV-webcam%20%26%20vision-5C3EE8?logo=opencv&logoColor=white)
![SQLite](https://img.shields.io/badge/SQLite-local%20storage-003B57?logo=sqlite&logoColor=white)
![Status](https://img.shields.io/badge/status-Sprint%203%20in%20progress-yellow)

A capstone project built in my 3rd year at DII: a webcam-based system that automatically takes class
attendance by recognizing students' faces, instead of a teacher calling out names or passing around a
sign-in sheet.

---

## 🧩 About This Project

Manually taking attendance is slow, and easy to cheat (one student can answer for an absent friend).
This project solves that with a normal webcam and free, open-source face recognition — no special
hardware, and no cloud service.

> 💡 **The idea in one sentence:** enroll each student's face once, then point a webcam at the class
> and the system recognizes who's present and writes it down automatically.

---

## ⚙️ How It Works

The system is three steps, matching the three files in `src/`:

### 1️⃣ Enroll a student — `enrollment.py`
A student sits in front of the webcam once. The system captures a photo, finds their face, and
converts it into a **face encoding**: a list of 128 numbers that acts like a numeric "fingerprint" for
that specific face. This encoding (not the photo itself) is saved to the database along with the
student's name.

### 2️⃣ Recognize faces live — `recognition.py` + `main.py`
While the webcam runs, every frame is scanned for faces. Each face found is converted into the same
kind of 128-number encoding, then compared against every enrolled student's stored encoding. Two
encodings from the *same* person's face always come out numerically close together; two *different*
people's come out far apart — so whichever enrolled student is numerically closest (and close enough
to count as a real match, not just the "least wrong" guess) is who the system decides that face
belongs to. ✅ This works for **multiple faces in the same frame at once**, not just one person at a
time.

### 3️⃣ Log attendance — `database.py`
Once a face is matched to a student, their name, ID, and the current time are saved to a local SQLite
database (a simple database that lives in a single file, no server needed). A duplicate-prevention
rule stops the same student from being logged over and over again within a few minutes of walking past
the camera once.

> 🔒 **Privacy note:** no photos or face data ever leave the local machine — everything (recognition
> and storage) runs entirely offline.

---

## 👥 Team

| Member | Originally Assigned | Notes |
|---|---|---|
| **Bilol Arzykulov** | Recognition module | 🛠️ Ended up implementing **all four modules** — see note below |
| **Ayub Timurov** | Data module & documentation | — |

> **Note:** Both modules (`recognition.py` and `database.py`), plus `enrollment.py` and `main.py`, were
> implemented by Bilol Arzykulov. The role split above reflects the original plan in
> [`05_collaboration_workflow.md`](docs/05_collaboration_workflow.md).

---

## 📚 Project Documents

See the [`docs/`](docs) folder for the full software-engineering documentation:

| Doc | Contents |
|---|---|
| 📋 [`01_requirements.md`](docs/01_requirements.md) | Functional & non-functional requirements |
| 🏗️ [`02_design.md`](docs/02_design.md) | Architecture, tech stack, database schema |
| 🗓️ [`03_sprint_plan.md`](docs/03_sprint_plan.md) | Agile sprint plan |
| ✅ [`04_test_plan.md`](docs/04_test_plan.md) | Test plan and results |
| 🤝 [`05_collaboration_workflow.md`](docs/05_collaboration_workflow.md) | Git branching workflow & module integration contract |
| 📄 [`06_technical_specification.md`](docs/06_technical_specification.md) | Full technical specification (for course submission) |

---

## 📁 Folder Structure

```
face_recognition_attendance/
├── docs/                  📚 Software engineering documentation
├── src/                   💻 Application source code
│   ├── enrollment.py      🧑 Capture & store a student's face
│   ├── recognition.py     👁️ Detect & recognize faces from the webcam
│   ├── database.py        🗄️ SQLite schema + attendance logging
│   └── main.py            🚀 Entry point
├── tests/                 🧪 Unit tests (mirrors src/)
├── data/                  💾 Local runtime data (ignored by git, except folder structure)
│   └── enrolled_photos/   📸 Captured enrollment photos (not committed — personal data)
├── requirements.txt       📦 Python dependencies
└── README.md
```

---

## 🛠️ Setup

1. Install Python 3.9+ and a webcam-equipped machine.
2. Create and activate a virtual environment:
   ```
   python -m venv venv
   venv\Scripts\activate   (Windows)
   ```
3. Install dependencies:
   ```
   pip install -r requirements.txt
   pip install --no-deps face_recognition face_recognition_models Click
   ```
   (Two steps because `face_recognition` normally depends on compiling `dlib` from source on Windows,
   which needs CMake + a C++ compiler. `requirements.txt` installs a pre-compiled `dlib-bin` instead, and
   the second command installs `face_recognition` itself without letting it try to pull the real `dlib`
   on top. See `docs/02_design.md` if you hit install errors.)
4. Run the application:
   ```
   python src/main.py
   ```

---

## ✅ Status

| Sprint | Goal | Status |
|---|---|---|
| **Sprint 1** | Foundations & Enrollment | ✅ Done — schema, webcam capture, and enrollment flow all working |
| **Sprint 2** | Detection & Recognition | ✅ Done — real-time single-face and multi-face recognition confirmed working live, including a fix for encoding accuracy at reduced frame size |
| **Sprint 3** | Attendance Logging, Testing & Report | 🚧 In progress |

**Sprint 3 breakdown:**
- ✅ Attendance logging with duplicate-prevention (FR-5)
- ⬜ Log export (FR-6) — not started
- ⬜ Automated unit tests in `tests/` — not started (behavior has been manually/script-verified so far)
- ⬜ Test plan execution (`docs/04_test_plan.md`) and final report — not started

🎉 All four `src/` modules (`enrollment.py`, `recognition.py`, `database.py`, `main.py`) are implemented
and have been tested live with multiple enrolled students recognized in a single frame.
