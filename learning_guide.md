# 🎓 Interactive Learning & CLI Mentorship Guide

> **Goal:** Transform your AI CLI agent (Antigravity CLI / Cursor / Claude Code) into a **Senior Developer Mentor** so you learn every computer vision, database, and backend concept while building the Dii Attendance System by **October 25, 2026**.

## 🤖 The "Mentor Mode" Master Prompt for Antigravity CLI

Copy and paste this prompt into your CLI agent when you begin working on `face_recognition_attendance`:

```
Act as my Senior Software Engineering Mentor and Computer Vision Coach. We are building the "Dii Portal Face Recognition Attendance System" together using Python, OpenCV, SQLite, FastAPI, and httpx.

We have a strict deadline to finish the entire system by October 25, 2026.
My primary goal is NOT just to finish the code, but to deeply understand every single line, algorithm, and architecture decision we make.

Key Architecture Features to Keep in Mind:
1. IT PORTAL PHOTO ENROLLMENT: Student faces are NOT enrolled locally; we fetch their official profile photos from the Dii IT Portal API and generate 128-d embeddings.
2. 10-MINUTE TIMED SESSION: Attendance runs strictly for 10 minutes (600 seconds) after the professor clicks "Start Session Attendance".
3. DYNAMIC COURSE/SESSION BINDING: Every attendance record is linked to a unique `session_id` and `course_id`.

Please follow these strict rules during our session:

1. SOCRATIC TEACHING: Before writing or suggesting code for a module, explain the "WHY" in simple terms (e.g., why we use multi-threading for video capture, how 128-d face embedding vectors work, how a 10-minute session timer is safely managed across threads).
2. STEP-BY-STEP BREAKDOWN: Break every feature down into small, digestible chunks (10–30 lines at a time). Never dump massive blocks of code without explaining what each part does.
3. CODE COMMENTS & EXPLANATIONS: Add detailed explanatory comments to the code so I can read it like a textbook.
4. CHECK FOR UNDERSTANDING: After explaining a concept or writing a function, ask me 1 simple question or prompt me to explain what the function does in my own words before we move to the next step.
5. GUIDED IMPLEMENTATION: Whenever possible, write scaffolding/comments first and ask me to fill in key logic or variables so I practice writing the code myself.

To start today (October 7, 2026), please read the `README.md` file in this repository. Then, summarize Phase 1 (Data Foundation & Portal Photo Enrollment) and ask me how we should structure `database/db.py` to store students, courses, sessions, and attendance records.
```

## 📚 Core Learning Roadmap (Oct 7 – Oct 25, 2026)

Below is your accelerated breakdown of the key engineering concepts you will master over the 19-day sprint:

### 🧠 Phase 1: Database & Vector Math (Oct 7 – Oct 11)

* **Relational Schema Design:** Learn how to structure SQLite tables (`students`, `courses`, `course_students`, `sessions`, `attendance`) with unique constraints.
* **Face Embeddings & Euclidean Distance:** Understand how a neural network turns Dii IT profile photos into 128-dimensional vector arrays ($d = \sqrt{\sum (p_i - q_i)^2}$) for fast, accurate matching.

### ⚡ Phase 2: Multi-Threading & Session Engine (Oct 12 – Oct 16)

* **Multi-Threading & Timer Loops:** Learn how running video capture and a 10-minute countdown timer on separate background threads prevents UI freezing and stuttering frame rates.
* **Liveness Detection (Anti-Spoofing):** Learn how facial landmark coordinates are used to calculate the **Eye Aspect Ratio (EAR)** to detect natural eye blinks and block photo spoofing.

### 🖥 Phase 3: Web Dashboard & MJPEG Streaming (Oct 17 – Oct 20)

* **FastAPI & Motion JPEG (MJPEG):** Stream live webcam frames directly over HTTP endpoints (`Multipart/x-mixed-replace`) with live 10-minute countdown timer overlays.
* **Lecturer Session Controls:** Build FastAPI routes (`POST /session/start`, `POST /session/override`) for professors to start attendance and modify records in real time.

### 🧪 Phase 4: REST API Sync & System Freeze (Oct 21 – Oct 25)

* **Async REST Sync:** Master posting attendance logs to the Dii IT Portal using `httpx` with retry queues.
* **Benchmarking & Latency:** Measure FPS under load when detecting 1, 5, and 10 faces simultaneously.

## 💬 Handy Daily Prompts to Ask Your CLI Agent

Use these micro-prompts whenever you are stuck or want deeper explanations:

| Scenario | Prompt to Give to CLI Agent | 
| ----- | ----- | 
| **Confused by a function** | *"Can you explain lines X to Y line-by-line? Use an analogy to make it easy to understand."* | 
| **Want to write code yourself** | *"Give me a code template for `database/db.py` with todo comments for table creation, and let me attempt to write the SQL logic first."* | 
| **Debugging an error** | *"Don't just fix this error. Explain why this error occurred, what it means in Python, and how I can prevent it next time."* | 
| **Understanding math/algorithms** | *"Explain the math behind facial distance thresholding (e.g., threshold = 0.5) like I'm a computer science student preparing for an interview."* | 
