
# Face Recognition Attendance System


## Current Status

Based on the repository (`biloltj/face_recognition_attendance`):

- Sprints 1 and 2 are done:
  - Enrollment from webcam
  - Live multi-face recognition
  - SQLite logging with duplicate prevention
- Log export, tests, and the report are still open.
- Missing for the new requirements:
  - Portal photo enrollment
  - Courses and sessions
  - The 10-minute "Take Attendance" capture

## Assumptions

- No deadline was given, so the plan covers 4 weeks (7 Oct to 4 Nov 2026), with buffer days.
- It is not yet known whether the DII portal has an API or database export for student photos. Week 1 depends on this, so it must be clarified first.
- The camera runs on a classroom computer or server. A teacher's browser can show the stream and press the button.

## Target Logic

1. **Enroll from portal photos:** import each student's portal photo, compute the face encoding, and store it with the student ID.
2. **Courses and sessions:** each lesson (a course on a specific date and time) gets its own `session_id`. Today's lesson and next week's lesson are different sessions of the same course.
3. **Take Attendance:** the teacher clicks the button and a session opens. The camera runs for 10 minutes, then stops automatically.
4. **Recognition:** match faces only against students enrolled in that course. This is faster and more accurate than searching the whole university.
5. **Logging:** one attendance record per student per session. This replaces the current "duplicate within a few minutes" rule.

### Suggested Tables

- `students`
- `courses`
- `course_students`
 - classroom (id, name, cctv)
- `sessions` (`id`, `course_id`, classroom_id, `date`, `start`, `end`, `status`)
- `attendance` (`session_id`, `student_id`, `time`, `confidence`)

Use a unique constraint on `(session_id, student_id)`.

## Schedule

### Week 1: Data Foundation and Portal Photos

| Work to finish |
|---|
| Review the repo against the new requirements and update `01_requirements.md` (portal photos, sessions, 10-minute timer). Ask the university IT office how to get the photos (API, export, or folder). |
| Redesign the database schema (courses, sessions, attendance) and write the migration in `database.py`. |
| Finish and test schema functions: create course, create session, log attendance once per session. |
| Build `portal_import.py`: read student photos and IDs from a folder or CSV (a stand-in until portal access works). |
| Bulk enrollment: compute encodings for all imported photos. Report photos with no face or several faces. |
| Photo quality handling: resize, rotate, retry with a stronger detector for failed photos. |
| Test with 20–30 real portal photos. **MILESTONE 1: bulk enrollment works.** |

### Week 2: Sessions and the 10-Minute Capture

| Work to finish |
|---|
| Build `session_manager.py`: start session, generate `session_id`, store start and end time. |
| Add the 10-minute countdown: the capture loop stops automatically and closes the session. |
| Roster filtering: recognition compares faces only against students in the session's course. |
| Rewrite `recognition.py` to run per session and write to attendance with the session ID. |
| Handle edge cases: camera disconnects, teacher stops early, two sessions never overlap in one room. |
| Integrate and test a full session on a laptop (start, 10 minutes, stop, results saved). |
| Fix bugs. **MILESTONE 2: the end-to-end session works from the command line.** |

### Week 3: Web Interface and Take Attendance Button

| Work to finish |
|---|
| Set up a Flask or FastAPI backend with endpoints to start a session, check status, and fetch results. |
| Stream the live camera feed to the browser (MJPEG) while the session runs. |
| Teacher page: choose course, click Take Attendance, see a countdown timer and live "recognized" list. |
| Attendance results page per session: present, absent, time marked. |
| Teacher manual override: mark a student present or absent after the session, and keep a record of changes. |
| Log export to CSV/Excel per session and per course (FR-6). |
| Connect the pieces and test. **MILESTONE 3: the button-to-result flow works in a browser.** |

### Week 4: Portal Integration, Testing, and Report

| Work to finish |
|---|
| Portal integration: connect to the real portal API or database if allowed. Otherwise finish the scheduled photo import and document how the button embeds in the portal. |
| Write automated unit tests in `tests/` for database, sessions, and recognition logic. |
| Real classroom test with volunteers. Tune the match tolerance and camera placement. |
| Fix accuracy problems found in the classroom test. |
| Execute the test plan in `04_test_plan.md` and record results. |
| Update the README, design doc, and technical specification. Add privacy and consent notes. |
| Final report and demo preparation. |
| **FINAL RELEASE AND DEMO. Buffer for anything that slipped.** |

## Risks to Watch

- **Portal access:** Portal access is the biggest unknown. Without an API or export, the importer has to work from a folder of photos, and the integration becomes a documented step.
- **Photo mismatch:** Portal photos are often old or formal, and the classroom camera is lower quality and at an angle. Place the camera at face height and light the room. If accuracy is low, enroll several photos per student.
- **Privacy:** Student photos are sensitive data. Get written permission from the university and keep everything local, as the README promises.
- **Timing:** If Week 3 slips, drop the manual override first, then the live stream, and keep the button and countdown.

## Open Question

**How can the photos be obtained from the DII portal: an API, a database export, or only the web pages?**

This decides the work planned for portal photo import and portal integration.
