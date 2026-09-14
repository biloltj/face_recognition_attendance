# Agile Sprint Plan

We are using **Scrum**, with 3 sprints of about 1 week each, given a tight overall timeline.
Each sprint should end with something demonstrably working, not half-finished code.

## Sprint 1 — Foundations & Enrollment
**Goal:** Requirements/design docs finalized; a student can be enrolled and stored.

| Task | Owner |
|------|-------|
| Finalize requirements doc (`01_requirements.md`) | Both |
| Finalize design doc (`02_design.md`) | Both |
| Set up Python environment, install `opencv-python` and `face_recognition`, confirm webcam works | Person A |
| Design & create SQLite schema (`students`, `attendance` tables) | Person B |
| Implement enrollment: capture photo(s), compute encoding, save to `students` table (FR-1) | Person A + B |

**Sprint 1 Review:** Demo enrolling one student and confirming their row appears in the database.

## Sprint 2 — Detection & Recognition
**Goal:** Live webcam feed can detect and recognize enrolled students in real time.

| Task | Owner |
|------|-------|
| Implement real-time face detection loop (FR-2) | Person A |
| Implement encoding comparison against all enrolled students (FR-3) | Person A |
| Tune the match-distance threshold to balance false positives/negatives (NFR-2) | Person A |
| Write basic unit tests for the recognition matching function | Person B |

**Sprint 2 Review:** Demo the system correctly identifying an enrolled student live on camera, and correctly
rejecting an unenrolled person.

## Sprint 3 — Attendance Logging, Testing & Report
**Goal:** Full flow works end-to-end; project is tested and documented for submission.

| Task | Owner |
|------|-------|
| Implement attendance logging with duplicate-prevention (FR-4, FR-5) | Person B |
| Implement log export/print (FR-6) | Person B |
| Wire recognition module output into the data module (integration) | Person A + B |
| Write test plan and execute it (`04_test_plan.md`) | Both |
| Write final capstone report, using these docs as source material | Both |

**Sprint 3 Review:** Demo the full flow — enroll, recognize live, see attendance logged and exported.

## Retrospective template (fill in after each sprint)
- What went well this sprint?
- What was harder than expected?
- What will we change for the next sprint?
