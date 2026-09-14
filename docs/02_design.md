# System Design Document

## 1. Technology Stack
| Layer | Choice | Why |
|-------|--------|-----|
| Language | Python | Team already knows some Python; huge library support for this domain. |
| Video capture & face detection | OpenCV (`opencv-python`) | Standard, well-documented library for reading webcam frames and locating faces in an image. |
| Face recognition | `face_recognition` (built on `dlib`) | Converts a detected face into a numeric "face embedding" and compares it to known students, without needing to train a custom deep learning model. |
| Data storage | SQLite (Python's built-in `sqlite3` module) | A database that lives in a single local file — no server setup, but still supports proper queries and prevents duplicate/inconsistent data better than a plain CSV file. |

## 2. High-Level Architecture

```
 ┌─────────────┐      ┌───────────────────┐      ┌────────────────────┐
 │   Webcam    │ ---> │  Recognition       │ ---> │   Data Module       │
 │ (OpenCV)    │      │  Module            │      │  (SQLite)           │
 │             │      │  - detect face     │      │  - enrolled_students │
 │             │      │  - compute encoding│      │  - attendance_log    │
 │             │      │  - match to student│      │                      │
 └─────────────┘      └───────────────────┘      └────────────────────┘
```

- The **Recognition Module** (owned by Person A) handles everything about the camera and identifying a face.
- The **Data Module** (owned by Person B) handles everything about storing and retrieving information.
- The two modules only talk to each other through one simple handoff: "here is the `student_id` that was just
  recognized" — this lets the two people build and test their parts independently.

## 3. Database Schema (SQLite)

**Table: `students`** (enrolled students and their face data)
| Column | Type | Notes |
|--------|------|-------|
| student_id | INTEGER PRIMARY KEY | Unique ID per student |
| name | TEXT | Student's full name |
| face_encoding | BLOB | The 128-number face "fingerprint" produced by `face_recognition`, stored as bytes |

**Table: `attendance`** (attendance log)
| Column | Type | Notes |
|--------|------|-------|
| id | INTEGER PRIMARY KEY AUTOINCREMENT | Row ID |
| student_id | INTEGER (FOREIGN KEY -> students.student_id) | Who was marked present |
| timestamp | TEXT (ISO datetime) | When they were recognized |

Duplicate-prevention rule (FR-5): before inserting a new attendance row, check whether the same
`student_id` already has a row with a `timestamp` within the last 5 minutes; if so, skip the insert.

## 4. Module Responsibilities

**Recognition Module (Person A)**
- Open the webcam and read frames continuously (OpenCV).
- Detect face locations in each frame.
- Compute the face encoding for each detected face.
- Compare the encoding against all encodings stored in the `students` table and find the closest match
  (if any match is close enough, based on a distance threshold).
- Pass the matched `student_id` to the Data Module.

**Data Module (Person B)**
- Create and manage the SQLite database and its two tables.
- Provide a function to enroll a new student (save name + face encoding).
- Provide a function to log attendance for a given `student_id`, applying the duplicate-prevention rule.
- Provide a function to export/print the attendance log.

## 5. Known Risks
- **Lighting/camera quality** can reduce recognition accuracy — mitigate by capturing multiple enrollment
  photos per student under varied conditions.
- **Look-alike false matches** are possible with any face recognition system at this scale — acceptable for
  a student project, but worth noting as a limitation in the final report.
