# 📄 Technical Specification Document

**Project Title:** Face Recognition Attendance System
**Course:** [Fill in: Capstone Project / Software Engineering course name]
**Instructor:** [Fill in: Instructor name]
**Team Members:** Bilol Arzykulov, Ayub Timurov
**Date:** [Fill in submission date]

---

## Abstract

Traditional classroom attendance (calling names or passing a sheet) is slow and easy to falsify. This
project implements a **Face Recognition Attendance System**: a webcam-based application that detects a
student's face, matches it against a database of enrolled students, and automatically records their
attendance with a timestamp. The project is developed using an **Agile/Scrum** methodology over three
one-week sprints by a two-person team, and is documented following standard software engineering
practice: requirements specification, system design, sprint planning, and a formal test plan.

---

## 1. 🎯 Introduction

### 1.1 Background and Motivation
Manual attendance-taking is time-consuming and vulnerable to proxy attendance (one student answering for
another). Automating this process with face recognition removes both problems while requiring no special
hardware beyond a standard webcam.

### 1.2 Problem Statement
Design and implement a system that can reliably identify enrolled students from a live camera feed and
maintain an accurate, persistent, duplicate-free attendance record, without requiring manual data entry.

### 1.3 Objectives
1. Allow an instructor to enroll a student's face with minimal effort.
2. Detect and recognize enrolled students from a live webcam feed in real time.
3. Automatically and reliably log attendance, preventing duplicate entries for the same session.
4. Provide a way to review or export the attendance record.

### 1.4 Project Scope
**In scope:** a single-machine, webcam-based desktop application covering enrollment, recognition, and
attendance logging.
**Out of scope (deliberately, to fit a two-person team and short timeline):** a web-based dashboard,
user accounts/permissions, notifications (email/SMS), and a mobile application. These are documented as
possible future work rather than current requirements.

---

## 2. 📋 Requirements Specification

*(Full detail: [`01_requirements.md`](01_requirements.md))*

### 2.1 Functional Requirements

| ID | Requirement |
|----|-------------|
| FR-1 | Enroll a student's face (capture photo(s) + name/ID) for later recognition. |
| FR-2 | Detect a face from the webcam feed in real time. |
| FR-3 | Recognize which enrolled student a detected face belongs to. |
| FR-4 | Automatically log attendance (name, ID, timestamp) when a known student is recognized. |
| FR-5 | Prevent duplicate attendance entries for the same student within a short time window (5 minutes). |
| FR-6 | Allow viewing/exporting the attendance log. |

### 2.2 Non-Functional Requirements

| ID | Requirement |
|----|-------------|
| NFR-1 | **Performance** — recognition completes within ~1–2 seconds. |
| NFR-2 | **Accuracy** — minimize false matches between different students. |
| NFR-3 | **Usability** — operable by a non-technical instructor with no special training. |
| NFR-4 | **Reliability** — attendance data persists across restarts (stored in a database, not memory). |

### 2.3 Assumptions and Constraints
- A single webcam is available during development and demonstration.
- Enrollment is performed under reasonably good lighting.
- The system runs on a single machine; no networked or multi-device deployment is required.
- Team size: 2 people. Timeline: 3 one-week Agile sprints.

---

## 3. 🏗️ System Design

*(Full detail: [`02_design.md`](02_design.md))*

### 3.1 Technology Stack

| Layer | Technology | Rationale |
|-------|-----------|-----------|
| Language | Python | Team proficiency; strong ecosystem for computer vision. |
| Video capture & face detection | OpenCV | Industry-standard, well-documented computer vision library. |
| Face recognition | `face_recognition` (built on `dlib`) | Provides pretrained face-embedding models; avoids the need to train a custom deep learning model from scratch. |
| Data storage | SQLite | Serverless, file-based relational database; sufficient for a single-machine deployment. |

### 3.2 System Architecture

```
 ┌─────────────┐      ┌───────────────────┐      ┌────────────────────┐
 │   Webcam    │ ---> │  Recognition       │ ---> │   Data Module       │
 │ (OpenCV)    │      │  Module            │      │  (SQLite)           │
 │             │      │  - detect face     │      │  - enrolled_students │
 │             │      │  - compute encoding│      │  - attendance_log    │
 │             │      │  - match to student│      │                      │
 └─────────────┘      └───────────────────┘      └────────────────────┘
```

The system follows a **two-module architecture** with a single, well-defined integration point (the
recognized `student_id`), allowing each module to be developed and tested independently — full interface
contract in [`05_collaboration_workflow.md`](05_collaboration_workflow.md).

### 3.3 Database Design

**`students`** — enrolled students and their face data

| Column | Type | Description |
|--------|------|--------------|
| student_id | INTEGER PRIMARY KEY | Unique identifier |
| name | TEXT | Student's full name |
| face_encoding | BLOB | 128-dimension face embedding produced by `face_recognition` |

**`attendance`** — attendance log

| Column | Type | Description |
|--------|------|--------------|
| id | INTEGER PRIMARY KEY AUTOINCREMENT | Row identifier |
| student_id | INTEGER (FK → students.student_id) | Student marked present |
| timestamp | TEXT (ISO datetime) | Time of recognition |

### 3.4 Module Responsibilities

| Module | Owner | Responsibilities |
|--------|-------|-------------------|
| Recognition + Integration | Bilol Arzykulov | Webcam capture, face detection, face-encoding computation, matching against enrolled students, wiring modules together |
| Data + Documentation | Ayub Timurov | Database schema, enrollment storage, attendance logging with duplicate prevention, log export, SE documentation upkeep |

### 3.5 Known Risks and Mitigations

| Risk | Mitigation |
|------|------------|
| Poor lighting reduces recognition accuracy | Capture multiple enrollment photos per student under varied lighting |
| Look-alike false matches | Acceptable known limitation at student-project scale; documented as such |

---

## 4. 🔄 Development Methodology

### 4.1 Process Model
The project follows **Agile/Scrum**, chosen for its short feedback loops and suitability for a small team
under a tight timeline. Work is organized into **3 sprints of approximately one week each**, each ending
in a working, demonstrable increment rather than partially completed features.

### 4.2 Team Roles
- **Bilol Arzykulov** — Recognition & Integration
- **Ayub Timurov** — Data & Documentation

### 4.3 Sprint Plan

*(Full detail, including task-level breakdown: [`03_sprint_plan.md`](03_sprint_plan.md))*

| Sprint | Goal | Key Deliverables |
|--------|------|-------------------|
| **Sprint 1** | Foundations & Enrollment | Finalized requirements/design docs; SQLite schema created; student enrollment (photo capture → face encoding → storage) working (FR-1) |
| **Sprint 2** | Detection & Recognition | Real-time face detection loop; face-matching against enrolled students; threshold tuning (FR-2, FR-3, NFR-2) |
| **Sprint 3** | Attendance Logging & Testing | Attendance logging with duplicate prevention; log export; full module integration; test plan executed; final report written (FR-4, FR-5, FR-6) |

Each sprint concludes with a **Sprint Review** (live demo of the increment) and a **Sprint Retrospective**
(what went well, what to improve), recorded in `03_sprint_plan.md`.

### 4.4 Collaboration Workflow
Development uses a **Git feature-branch workflow**: each task is developed on its own branch, integrated
via Pull Request and code review, then merged into `main`. Full workflow and the module integration
contract are documented in [`05_collaboration_workflow.md`](05_collaboration_workflow.md).

---

## 5. 🧪 Testing Strategy

*(Full detail and results log: [`04_test_plan.md`](04_test_plan.md))*

### 5.1 Unit Testing
Automated tests target individual functions in isolation, e.g. verifying the face-matching function
correctly accepts same-person encodings and rejects different-person encodings, and that attendance
logging correctly applies the duplicate-prevention rule.

### 5.2 Integration Testing
Manual, end-to-end scenarios verify the complete pipeline: enrollment → live recognition → attendance
logging → export, including edge cases such as an unenrolled person appearing on camera, multiple
students in sequence, and degraded lighting conditions.

---

## 6. 🗓️ Project Timeline

| Week | Milestone |
|------|-----------|
| Week 1 | Sprint 1 complete: documentation finalized, enrollment feature working |
| Week 2 | Sprint 2 complete: real-time detection and recognition working |
| Week 3 | Sprint 3 complete: attendance logging, testing, and final report submitted |

---

## 7. 🏁 Conclusion and Expected Outcomes

By the end of the project, the team expects to deliver a working desktop application that automates
attendance-taking via face recognition, backed by a complete set of software engineering artifacts
(requirements, design, sprint records, and test results) demonstrating the process used to build it, in
addition to the software itself.

---

## References
- OpenCV — https://opencv.org/
- `face_recognition` library — https://github.com/ageitgey/face_recognition
- dlib — http://dlib.net/
- SQLite — https://www.sqlite.org/

---

## Appendix A: Repository Structure

```
face_recognition_attendance/
├── docs/                  Software engineering documentation (this document and others)
├── src/                   Application source code
├── tests/                 Unit tests
├── data/                  Local runtime data (not committed to version control)
├── requirements.txt       Python dependencies
└── README.md
```

## Appendix B: Related Documents
- [`01_requirements.md`](01_requirements.md) — Requirements Document
- [`02_design.md`](02_design.md) — System Design Document
- [`03_sprint_plan.md`](03_sprint_plan.md) — Agile Sprint Plan
- [`04_test_plan.md`](04_test_plan.md) — Test Plan
- [`05_collaboration_workflow.md`](05_collaboration_workflow.md) — Collaboration & Git Workflow
