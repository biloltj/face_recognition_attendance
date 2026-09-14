# Requirements Document

## 1. Project Overview
This project is a **Face Recognition Attendance System**. Instead of a teacher calling out names, a webcam
detects a student's face, matches it against a list of enrolled students, and automatically records their
attendance with a timestamp.

This is the "basic" scope version: a local Python application with webcam + database. No web dashboard,
no notifications, no user accounts — those are out of scope for this project.

## 2. Functional Requirements
(What the system must *do*. Written as user stories: "As a [user], I want [feature], so that [reason].")

| ID | User Story |
|----|------------|
| FR-1 | As a teacher, I want to **enroll a student's face** (capture a few photos + name/ID) so the system can recognize them later. |
| FR-2 | As a teacher, I want the system to **detect a face** from the webcam feed in real time. |
| FR-3 | As a teacher, I want the system to **recognize which enrolled student** a detected face belongs to. |
| FR-4 | As a teacher, I want the system to **log attendance** (name, ID, timestamp) automatically when a known student is recognized. |
| FR-5 | As a teacher, I want the system to **avoid duplicate log entries** for the same student within a short time window (e.g. 5 minutes). |
| FR-6 | As a teacher, I want to **view/export the attendance log** (e.g. print a table or export to CSV). |

## 3. Non-Functional Requirements
(What quality the system must have, not what feature it has.)

| ID | Requirement |
|----|-------------|
| NFR-1 | **Performance**: A face should be recognized within ~1-2 seconds of appearing on camera. |
| NFR-2 | **Accuracy**: The system should minimize false matches (recognizing the wrong student) as much as reasonably possible for a student project. |
| NFR-3 | **Usability**: The enrollment and attendance process should require no technical knowledge to operate (a teacher just runs the program and points the camera). |
| NFR-4 | **Reliability**: Attendance data must not be lost if the program is closed and reopened (stored persistently in a database, not memory). |

## 4. Out of Scope
To keep this achievable in a few weeks with a 2-person team, the following are explicitly **not** part of
this project:
- Web-based dashboard or remote access
- User accounts / login / permissions
- Email or SMS notifications
- Mobile app version

## 5. Assumptions & Constraints
- A single webcam is available during development and demo.
- Enrollment photos are captured in reasonably good lighting.
- The system runs on one computer (no networked/multi-device setup).
- Team size: 2 people. Timeline: a few weeks, structured as 3 one-week Agile sprints (see `03_sprint_plan.md`).
