# Test Plan

## 1. Purpose
This document describes how we will verify the system meets the requirements in `01_requirements.md`.
For a beginner: "testing" here just means writing down specific scenarios and checking the actual result
matches the expected result — some checked automatically with code (unit tests), some checked by hand
(manual tests).

## 2. Unit Tests (automated, checking individual functions)
| Test ID | Function under test | Scenario | Expected result |
|---------|---------------------|----------|------------------|
| UT-1 | Face matching function | Compare two encodings from the *same* person's photos | Reported as a match |
| UT-2 | Face matching function | Compare encodings from two *different* people | Reported as not a match |
| UT-3 | Attendance logging function | Log the same student twice within 5 minutes | Second call is skipped (no duplicate row) |
| UT-4 | Attendance logging function | Log the same student, but more than 5 minutes apart | Both calls create a row |
| UT-5 | Enrollment function | Enroll a student with a valid name/photo | A row appears in the `students` table with the correct name and a non-empty encoding |

## 3. Integration/Manual Tests (checking the whole flow together)
| Test ID | Scenario | Steps | Expected result |
|---------|----------|-------|------------------|
| IT-1 | End-to-end happy path | Enroll a student, then show their face to the webcam | Attendance is logged with correct name/ID and timestamp |
| IT-2 | Unenrolled person | Show a face that was never enrolled | No attendance is logged; system does not crash |
| IT-3 | Multiple students | Enroll 2+ students, show each face in turn | Each is logged under their own correct ID, not confused with each other |
| IT-4 | Poor lighting | Repeat IT-1 in dim lighting | Note actual behavior — document as a known limitation if accuracy drops (per NFR-2) |
| IT-5 | Export | After logging some attendance, run the export/print function | Output matches what is actually stored in the `attendance` table |

## 4. How to record results
For each test run before submission, record: date run, pass/fail, and any notes — this table becomes
evidence for your capstone report that the system was actually verified, not just built.

| Test ID | Date | Result | Notes |
|---------|------|--------|-------|
| | | | |
