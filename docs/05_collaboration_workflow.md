# 🤝 Collaboration & Git Workflow

## 1. 👥 Roles Recap
- **Bilol Arzykulov (Recognition + Integration):** webcam capture, face detection, face matching, and
  wiring everything together in `main.py`.
- **Ayub Timurov (Data + Documentation):** SQLite schema, enrollment storage, attendance
  logging with duplicate-prevention, and keeping the `docs/` files up to date.

Full detail on each module is in [`02_design.md`](02_design.md).

## 2. 🔗 The Integration Contract
Because you're each writing separate files, you both agree on these exact function signatures *before*
writing the internals. As long as each function takes the agreed inputs and returns the agreed outputs,
you can build and test your parts independently and they will connect with no surprises.

**🗄️ Provided by `database.py` (Ayub Timurov) — called by Bilol Arzykulov / `main.py`:**
| Function | Input | Output | Purpose |
|---|---|---|---|
| `init_db()` | — | — | Creates the SQLite tables if they don't exist yet. |
| `save_student(name, encoding)` | student's name, face encoding (bytes) | new `student_id` | Enrolls a new student. |
| `get_all_students()` | — | list of `(student_id, name, encoding)` | Everyone Bilol Arzykulov needs to compare a live face against. |
| `log_attendance(student_id)` | `student_id` | `True`/`False` (logged or skipped as duplicate) | Records attendance, applying the 5-minute duplicate rule. |

**👁️ Provided by `recognition.py` (Bilol Arzykulov) — called by Ayub Timurov / `main.py`:**
| Function | Input | Output | Purpose |
|---|---|---|---|
| `get_face_encoding(image)` | a captured image | encoding (bytes) or `None` | Turns a photo into the numeric face "fingerprint". Used both for enrollment and live recognition. |
| `match_face(encoding, known_students)` | a live encoding + the list from `get_all_students()` | matching `student_id` or `None` | Finds which enrolled student (if any) the live face belongs to. |

**🚀 `main.py` glue (roughly):**
```python
students = database.get_all_students()
encoding = recognition.get_face_encoding(frame)
if encoding is not None:
    student_id = recognition.match_face(encoding, students)
    if student_id is not None:
        database.log_attendance(student_id)
```

⚠️ If either of you needs to change a function's inputs/outputs, say so to the other person first — don't
change the contract silently, since the other person's code depends on it staying the same.

## 3. 🌿 Git Branching Workflow
Repeat these steps for every task/feature you work on:

1. **🔄 Sync with the shared code first:**
   ```
   git checkout main
   git pull
   ```
2. **🌱 Create your own branch**, named after the task:
   ```
   git checkout -b feature/face-detection
   ```
3. **💾 Work and commit in small logical steps:**
   ```
   git add src/recognition.py
   git commit -m "Add real-time face detection loop"
   ```
4. **⬆️ Push your branch to GitHub:**
   ```
   git push -u origin feature/face-detection
   ```
5. **📬 Open a Pull Request (PR)** on GitHub: open the repo page, click "Compare & pull request", write a
   short description of what you did, and create it. A PR is a request to merge your branch into `main`,
   giving your teammate a chance to review before it becomes official.
6. **👀 Teammate reviews** the PR (reads the diff, comments if something looks off).
7. Once approved, click **✅ Merge pull request** on GitHub.
8. **🔄 Both of you resync:**
   ```
   git checkout main
   git pull
   ```

## 4. 🗂️ Suggested Branches per Sprint Task
| Sprint | Task | Branch name | Owner |
|---|---|---|---|
| 1 | SQLite schema + student storage | `feature/db-schema` | Ayub Timurov |
| 1 | Enrollment (capture + save) | `feature/enrollment` | Both |
| 2 | Real-time face detection | `feature/face-detection` | Bilol Arzykulov |
| 2 | Face matching logic | `feature/face-matching` | Bilol Arzykulov |
| 3 | Attendance logging + duplicate rule | `feature/attendance-logging` | Ayub Timurov |
| 3 | Log export | `feature/export` | Ayub Timurov |
| 3 | Wire modules together in `main.py` | `feature/integration` | Both |

## 5. ⚠️ If You Hit a Merge Conflict
This should be rare since you're mostly editing different files, but if git says there's a conflict:
- Open the file — git marks the disputed section like this:
  ```
  <<<<<<< HEAD
  (code currently on main)
  =======
  (your incoming code)
  >>>>>>> feature/your-branch
  ```
- Manually edit the file to keep the correct combination of both, delete the `<<<<<<<`/`=======`/`>>>>>>>`
  marker lines, then:
  ```
  git add <the file>
  git commit
  ```

## 6. 💬 Message to Send Your Teammate
Copy-paste this to get him set up:

> Hey — repo's ready. Here's how to get started:
> 1. Accept the GitHub collaborator invite (check your email).
> 2. Clone it: `git clone git@github.com:<username>/face_recognition_attendance.git`
> 3. Inside the folder: create a virtual environment and install dependencies:
>    ```
>    python -m venv venv
>    venv\Scripts\activate
>    pip install -r requirements.txt
>    ```
> 4. Read `docs/02_design.md` for what your module (`database.py`) needs to do, and
>    `docs/05_collaboration_workflow.md` for our branch workflow — follow the steps there for every task
>    instead of committing straight to `main`.
> 5. Start with the `feature/db-schema` branch (see the task table in that file).
