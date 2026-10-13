// Modern Face Recognition Attendance Dashboard Client

// ------------------------------------------------------------------ UI Helpers
function showToast(message, type = "info") {
  const container = document.getElementById("toast-container");
  const toast = document.createElement("div");
  toast.className = `toast toast-${type}`;
  toast.textContent = message;
  container.appendChild(toast);

  setTimeout(() => {
    toast.style.transition = "opacity 0.3s ease";
    toast.style.opacity = "0";
    setTimeout(() => toast.remove(), 300);
  }, 4000);
}

// Names and session labels come from user input. Escape them before putting them inside an
// innerHTML template, so text like "<img onerror=...>" is shown as text instead of being run.
function escapeHtml(value) {
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

async function apiRequest(url, options = {}) {
  try {
    const res = await fetch(url, options);
    if (!res.ok) {
      const errData = await res.json().catch(() => ({}));
      throw new Error(errData.error || `Request failed with status ${res.status}`);
    }
    return await res.json();
  } catch (err) {
    showToast(err.message, "error");
    throw err;
  }
}

// ------------------------------------------------------------------ Tab Switching
const tabs = document.querySelectorAll(".nav-tab");
const tabPanes = document.querySelectorAll(".tab-pane");

tabs.forEach((tab) => {
  tab.addEventListener("click", () => {
    tabs.forEach((t) => t.classList.remove("active"));
    tabPanes.forEach((p) => p.classList.remove("active"));

    tab.classList.add("active");
    const target = tab.dataset.tab;
    const targetPane = document.getElementById(target);
    if (targetPane) targetPane.classList.add("active");

    // Refresh tab-specific data
    if (target === "tab-records") loadAttendanceRecords();
    if (target === "tab-roster") loadStudentsRoster();
    if (target === "tab-courses") loadCourses().then(loadCourseRoster);
    if (target === "tab-results") loadSessionHistory();
  });
});

// ------------------------------------------------------------------ State & Badges
let currentSession = null; // the running attendance session from /api/sessions/current, or null
let sessionPollTimer = null;
let countdownTimer = null;
let sessionDeadline = 0; // local Date.now() value at which the running session ends
let endingByTeacher = false; // true while our own End Session request is in flight

function updateCameraBadge(isRunning) {
  const dot = document.getElementById("camera-status-dot");
  const text = document.getElementById("badge-camera-status");
  const btnStart = document.getElementById("btn-start-stream");
  const btnStop = document.getElementById("btn-stop-stream");

  if (isRunning) {
    dot.classList.add("active");
    text.textContent = currentSession ? "Taking Attendance" : "Preview Active";
  } else {
    dot.classList.remove("active");
    text.textContent = "Camera Inactive";
  }
  // While a session runs, the camera belongs to it: use End Session to stop.
  btnStart.disabled = isRunning || currentSession !== null;
  btnStop.disabled = !isRunning || currentSession !== null;
}

// ------------------------------------------------------------------ Attendance Sessions
const courseSelect = document.getElementById("course-select");
const btnTakeAttendance = document.getElementById("btn-take-attendance");
const btnEndSession = document.getElementById("btn-end-session");
const sessionInfo = document.getElementById("session-info");
const sessionPresent = document.getElementById("session-present");
const sessionCountdown = document.getElementById("session-countdown");
const sessionCountdownText = document.getElementById("session-countdown-text");
const sessionCountdownBar = document.getElementById("session-countdown-bar");

function updateCountdown() {
  if (!currentSession) return;
  const secondsLeft = Math.max(0, Math.round((sessionDeadline - Date.now()) / 1000));
  const minutes = Math.floor(secondsLeft / 60);
  const seconds = String(secondsLeft % 60).padStart(2, "0");
  sessionCountdownText.textContent = secondsLeft > 0 ? `⏱ ${minutes}:${seconds} left` : "⏱ Finishing…";
  sessionCountdownText.classList.toggle("ending", secondsLeft <= 60);
  sessionCountdownBar.style.width = `${(secondsLeft / currentSession.duration_seconds) * 100}%`;
}

function renderSession(session) {
  const previous = currentSession;
  currentSession = session.active ? session : null;
  const active = currentSession !== null;

  // The server closes the session when time is up; the next poll notices it ended without us.
  if (previous && !active && !endingByTeacher) {
    showToast(
      `Time is up: ${previous.course_code} session ended with ${previous.present.length} of ${previous.roster_size} present`,
      "success"
    );
    updateCameraBadge(false);
    loadSessions();
    loadAttendanceRecords();
    loadSessionHistory();
  }

  sessionCountdown.hidden = !active;
  if (active) {
    // Rebuilt from the server's seconds_left on every poll, so the countdown never drifts far.
    sessionDeadline = Date.now() + session.seconds_left * 1000;
    updateCountdown();
    if (countdownTimer === null) countdownTimer = setInterval(updateCountdown, 1000);
  } else if (countdownTimer !== null) {
    clearInterval(countdownTimer);
    countdownTimer = null;
  }

  document.getElementById("badge-active-session").textContent = active ? session.course_code : "None";
  btnTakeAttendance.disabled = active;
  btnEndSession.disabled = !active;
  courseSelect.disabled = active;
  btnSingleCapture.disabled = !active;
  btnRecognizePhoto.disabled = !active || !attendancePhotoFile.files[0];

  sessionPresent.innerHTML = "";
  if (!active) {
    sessionInfo.textContent = "No attendance session running.";
  } else {
    const started = new Date(session.started_at).toLocaleTimeString();
    sessionInfo.textContent =
      `Session #${session.session_id} · ${session.course_code} – ${session.course_name} · ` +
      `started ${started} · ${session.present.length} of ${session.roster_size} present`;

    session.present.forEach((p) => {
      const badge = document.createElement("div");
      badge.className = "result-badge known";
      const name = document.createElement("strong");
      name.textContent = p.name;
      const time = document.createElement("span");
      time.textContent = new Date(p.timestamp).toLocaleTimeString();
      badge.append(name, time);
      sessionPresent.appendChild(badge);
    });
  }

  // Poll while a session runs so newly recognized students appear without refreshing.
  if (active && sessionPollTimer === null) {
    sessionPollTimer = setInterval(loadCurrentSession, 3000);
  } else if (!active && sessionPollTimer !== null) {
    clearInterval(sessionPollTimer);
    sessionPollTimer = null;
  }
}

async function loadCurrentSession() {
  try {
    renderSession(await apiRequest("/api/sessions/current"));
  } catch (e) {}
}

btnTakeAttendance.addEventListener("click", async () => {
  if (!courseSelect.value) {
    showToast("Please choose a course first", "error");
    return;
  }

  btnTakeAttendance.disabled = true;
  try {
    const session = await apiRequest("/api/sessions/start", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ course_id: Number(courseSelect.value) }),
    });
    renderSession(session);
    updateCameraBadge(true);
    videoStream.src = `/video_feed?t=${Date.now()}`;
    showToast(`Taking attendance for ${session.course_code}`, "success");
  } catch (e) {
    btnTakeAttendance.disabled = false;
  }
});

btnEndSession.addEventListener("click", async () => {
  btnEndSession.disabled = true;
  endingByTeacher = true;
  try {
    const res = await apiRequest("/api/sessions/stop", { method: "POST" });
    renderSession({ active: false });
    updateCameraBadge(false);
    showToast(`Session ended: ${res.present_count} of ${res.roster_size} students present`, "success");
    loadSessions();
    loadAttendanceRecords();
    openTab("tab-results");
    showSessionResults(res.session_id);
  } catch (e) {
    endingByTeacher = false; // e.g. the timer already ended it: let the poll report that instead
    loadCurrentSession();
  } finally {
    endingByTeacher = false;
  }
});

// Fills the Attendance History filter with the session names found in the log.
async function loadSessions() {
  try {
    const data = await apiRequest("/api/sessions");
    const filterSelect = document.getElementById("records-session-filter");
    const selected = filterSelect.value;
    filterSelect.innerHTML = '<option value="ALL">All Sessions</option>';
    data.sessions.forEach((s) => {
      const opt = document.createElement("option");
      opt.value = s;
      opt.textContent = s;
      if (s === selected) opt.selected = true;
      filterSelect.appendChild(opt);
    });
  } catch (e) {
    console.error("Failed to load sessions:", e);
  }
}

// ------------------------------------------------------------------ Session Results
const resultsCourseFilter = document.getElementById("results-course-filter");
const sessionsTableBody = document.querySelector("#sessions-table tbody");
const sessionResultsTableBody = document.querySelector("#session-results-table tbody");
let selectedResultsSessionId = null;

function textCell(value, className) {
  const td = document.createElement("td");
  td.textContent = value;
  if (className) td.className = className;
  return td;
}

async function loadSessionHistory() {
  const courseId = resultsCourseFilter.value;
  try {
    const sessions = await apiRequest(`/api/sessions/history${courseId ? `?course_id=${courseId}` : ""}`);
    sessionsTableBody.innerHTML = "";
    if (sessions.length === 0) {
      sessionsTableBody.innerHTML = '<tr><td colspan="4" class="text-center">No sessions yet.</td></tr>';
      return;
    }

    sessions.forEach((s) => {
      const tr = document.createElement("tr");
      if (s.session_id === selectedResultsSessionId) tr.classList.add("selected");
      const started = new Date(s.started_at);
      const running = s.status === "open" ? " (running)" : "";
      tr.append(
        textCell(`${started.toLocaleDateString()} ${started.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}`),
        textCell(s.course_code + running),
        textCell(`${s.present_count} / ${s.expected_count}`)
      );

      const actionCell = document.createElement("td");
      const viewBtn = document.createElement("button");
      viewBtn.className = "btn btn-secondary";
      viewBtn.style.cssText = "padding: 0.25rem 0.6rem; font-size: 0.8rem;";
      viewBtn.textContent = "View";
      viewBtn.addEventListener("click", () => showSessionResults(s.session_id));
      actionCell.appendChild(viewBtn);
      tr.appendChild(actionCell);

      sessionsTableBody.appendChild(tr);
    });
  } catch (e) {
    sessionsTableBody.innerHTML = '<tr><td colspan="4" class="text-center">Failed to load sessions.</td></tr>';
  }
}

async function showSessionResults(sessionId) {
  selectedResultsSessionId = sessionId;
  try {
    const r = await apiRequest(`/api/sessions/${sessionId}/results`);
    const started = new Date(r.started_at);
    const ended = r.ended_at ? new Date(r.ended_at).toLocaleTimeString() : "still running";

    document.getElementById("results-title").textContent = `${r.course_code} – ${r.course_name}`;
    document.getElementById("results-subtitle").textContent =
      `Session #${r.session_id} · ${started.toLocaleDateString()} · ${started.toLocaleTimeString()} – ${ended}`;
    document.getElementById("results-stats").hidden = false;
    document.getElementById("results-present").textContent = r.present_count;
    document.getElementById("results-absent").textContent = r.absent_count;
    const total = r.present_count + r.absent_count;
    document.getElementById("results-rate").textContent = total ? `${Math.round((r.present_count / total) * 100)}%` : "–";

    const exportBtn = document.getElementById("btn-export-session");
    exportBtn.href = `/api/sessions/${sessionId}/export.csv`;
    exportBtn.hidden = false;

    sessionResultsTableBody.innerHTML = "";
    if (r.students.length === 0) {
      sessionResultsTableBody.innerHTML = '<tr><td colspan="3" class="text-center">No students were expected in this session.</td></tr>';
    }
    r.students.forEach((s) => {
      const tr = document.createElement("tr");
      tr.append(
        textCell(s.name),
        textCell(s.present ? "✅ Present" : "❌ Absent", s.present ? "status-present" : "status-absent"),
        textCell(s.timestamp ? new Date(s.timestamp).toLocaleTimeString() : "—")
      );
      sessionResultsTableBody.appendChild(tr);
    });

    loadSessionHistory(); // rebuilds the list so the selected row is highlighted
  } catch (e) {}
}

resultsCourseFilter.addEventListener("change", loadSessionHistory);

function openTab(tabId) {
  document.querySelector(`.nav-tab[data-tab="${tabId}"]`).click();
}

// ------------------------------------------------------------------ Courses
const courseRosterSelect = document.getElementById("course-roster-select");
const coursesTableBody = document.querySelector("#courses-table tbody");
const courseRosterTableBody = document.querySelector("#course-roster-table tbody");

function fillCourseSelect(select, courses, emptyLabel) {
  const selected = select.value;
  select.innerHTML = "";
  if (courses.length === 0) {
    const opt = document.createElement("option");
    opt.value = "";
    opt.textContent = emptyLabel;
    select.appendChild(opt);
    return;
  }
  courses.forEach((c) => {
    const opt = document.createElement("option");
    opt.value = c.course_id;
    opt.textContent = `${c.code} – ${c.name} (${c.student_count} students)`;
    if (String(c.course_id) === selected) opt.selected = true;
    select.appendChild(opt);
  });
}

async function loadCourses() {
  try {
    const courses = await apiRequest("/api/courses");
    fillCourseSelect(courseSelect, courses, "No courses yet – create one in the Courses tab");
    fillCourseSelect(courseRosterSelect, courses, "No courses yet");
    const selectedFilter = resultsCourseFilter.value;
    resultsCourseFilter.innerHTML = '<option value="">All courses</option>';
    courses.forEach((c) => {
      const opt = document.createElement("option");
      opt.value = c.course_id;
      opt.textContent = `${c.code} – ${c.name}`;
      if (String(c.course_id) === selectedFilter) opt.selected = true;
      resultsCourseFilter.appendChild(opt);
    });

    coursesTableBody.innerHTML = "";
    if (courses.length === 0) {
      coursesTableBody.innerHTML = '<tr><td colspan="3" class="text-center">No courses yet.</td></tr>';
    }
    courses.forEach((c) => {
      const tr = document.createElement("tr");
      [c.code, c.name, c.student_count].forEach((value) => {
        const td = document.createElement("td");
        td.textContent = value;
        tr.appendChild(td);
      });
      coursesTableBody.appendChild(tr);
    });
  } catch (e) {
    console.error("Failed to load courses:", e);
  }
}

async function loadCourseRoster() {
  const courseId = courseRosterSelect.value;
  if (!courseId) {
    courseRosterTableBody.innerHTML = '<tr><td colspan="3" class="text-center">Create a course first.</td></tr>';
    return;
  }

  try {
    const [students, members] = await Promise.all([
      apiRequest("/api/students"),
      apiRequest(`/api/courses/${courseId}/students`),
    ]);
    const memberIds = new Set(members.map((m) => m.student_id));

    courseRosterTableBody.innerHTML = "";
    if (students.length === 0) {
      courseRosterTableBody.innerHTML = '<tr><td colspan="3" class="text-center">No students enrolled yet.</td></tr>';
      return;
    }

    students.forEach((s) => {
      const tr = document.createElement("tr");
      const checkCell = document.createElement("td");
      const checkbox = document.createElement("input");
      checkbox.type = "checkbox";
      checkbox.checked = memberIds.has(s.student_id);
      checkbox.addEventListener("change", async () => {
        checkbox.disabled = true;
        try {
          await apiRequest(`/api/courses/${courseId}/students/${s.student_id}`, {
            method: checkbox.checked ? "POST" : "DELETE",
          });
          loadCourses();
        } catch (e) {
          checkbox.checked = !checkbox.checked;
        } finally {
          checkbox.disabled = false;
        }
      });
      checkCell.appendChild(checkbox);

      const idCell = document.createElement("td");
      idCell.textContent = `#${s.student_id}`;
      const nameCell = document.createElement("td");
      nameCell.textContent = s.name;
      tr.append(checkCell, idCell, nameCell);
      courseRosterTableBody.appendChild(tr);
    });
  } catch (e) {
    courseRosterTableBody.innerHTML = '<tr><td colspan="3" class="text-center">Failed to load students.</td></tr>';
  }
}

courseRosterSelect.addEventListener("change", loadCourseRoster);

document.getElementById("btn-create-course").addEventListener("click", async () => {
  const codeInput = document.getElementById("course-code");
  const nameInput = document.getElementById("course-name");
  const code = codeInput.value.trim();
  const name = nameInput.value.trim();
  if (!code || !name) {
    showToast("Please enter both a course code and a course name", "error");
    return;
  }

  try {
    const course = await apiRequest("/api/courses", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ code, name }),
    });
    showToast(`Created course ${course.code}`, "success");
    codeInput.value = "";
    nameInput.value = "";
    await loadCourses();
    courseRosterSelect.value = String(course.course_id);
    loadCourseRoster();
  } catch (e) {}
});

// ------------------------------------------------------------------ Live Stream & Controls
const btnStartStream = document.getElementById("btn-start-stream");
const btnStopStream = document.getElementById("btn-stop-stream");
const btnSingleCapture = document.getElementById("btn-single-capture");
const liveDetectionStatus = document.getElementById("live-detection-status");
const videoStream = document.getElementById("video-stream");

async function checkCameraStatus() {
  try {
    const status = await apiRequest("/api/camera/status");
    updateCameraBadge(status.running);
  } catch (e) {}
}

btnStartStream.addEventListener("click", async () => {
  try {
    btnStartStream.disabled = true;
    const res = await apiRequest("/api/camera/start", { method: "POST" });
    updateCameraBadge(res.running);
    if (res.running) {
      videoStream.src = `/video_feed?t=${Date.now()}`;
      showToast("Camera preview started", "success");
    } else {
      showToast("Could not access webcam. Ensure no other app is using it.", "error");
    }
  } catch (e) {
    btnStartStream.disabled = false;
  }
});

btnStopStream.addEventListener("click", async () => {
  try {
    await apiRequest("/api/camera/stop", { method: "POST" });
    updateCameraBadge(false);
    showToast("Camera preview stopped", "info");
  } catch (e) {}
});

btnSingleCapture.addEventListener("click", async () => {
  liveDetectionStatus.textContent = "Scanning faces...";
  btnSingleCapture.disabled = true;

  try {
    const res = await apiRequest("/api/attendance/capture", { method: "POST" });

    if (res.length === 0) {
      liveDetectionStatus.textContent = "No face detected in snapshot.";
      showToast("No face detected in snapshot", "info");
    } else {
      const names = res.map((d) => d.name).join(", ");
      liveDetectionStatus.textContent = `Recognized: ${names}`;
      showToast(`Recognized: ${names}`, "success");
      loadCurrentSession();
    }
  } catch (e) {
    liveDetectionStatus.textContent = "";
  } finally {
    btnSingleCapture.disabled = currentSession === null;
  }
});

// ------------------------------------------------------------------ Classroom Photo Attendance
const attendanceDropZone = document.getElementById("attendance-drop-zone");
const attendancePhotoFile = document.getElementById("attendance-photo-file");
const attendancePhotoPreview = document.getElementById("attendance-photo-preview");
const btnRecognizePhoto = document.getElementById("btn-recognize-photo");
const photoRecognitionResults = document.getElementById("photo-recognition-results");

function handleFilePreview(input, previewElement, submitButton) {
  const file = input.files[0];
  if (file) {
    const reader = new FileReader();
    reader.onload = (e) => {
      previewElement.src = e.target.result;
      previewElement.style.display = "block";
      const dropContent = previewElement.previousElementSibling;
      if (dropContent) dropContent.style.display = "none";
      if (submitButton) submitButton.disabled = false;
    };
    reader.readAsDataURL(file);
  }
}

attendancePhotoFile.addEventListener("change", () => {
  // The button only becomes usable while a session is running (see renderSession).
  handleFilePreview(attendancePhotoFile, attendancePhotoPreview, currentSession ? btnRecognizePhoto : null);
});

btnRecognizePhoto.addEventListener("click", async () => {
  const file = attendancePhotoFile.files[0];
  if (!file) return;

  btnRecognizePhoto.disabled = true;
  photoRecognitionResults.innerHTML = "<em>Analyzing photo with face recognition engine...</em>";

  const formData = new FormData();
  formData.append("photo", file);

  try {
    const detections = await apiRequest("/api/attendance/photo", {
      method: "POST",
      body: formData,
    });

    photoRecognitionResults.innerHTML = "";
    if (detections.length === 0) {
      photoRecognitionResults.innerHTML = '<div class="result-badge unknown">No faces recognized in photo</div>';
      showToast("No faces detected in the photo", "info");
    } else {
      detections.forEach((d) => {
        const badge = document.createElement("div");
        badge.className = `result-badge ${d.name === "Unknown" ? "unknown" : "known"}`;
        badge.innerHTML = `<span><strong>${escapeHtml(d.name)}</strong></span><span>${d.name === "Unknown" ? "Not in this course" : "Marked Present"}</span>`;
        photoRecognitionResults.appendChild(badge);
      });
      showToast(`Recognized ${detections.length} face(s)`, "success");
      loadCurrentSession();
    }
  } finally {
    btnRecognizePhoto.disabled = currentSession === null;
  }
});

// ------------------------------------------------------------------ Student Enrollment
const btnEnrollCam = document.getElementById("btn-enroll-cam");
const enrollCamName = document.getElementById("enroll-cam-name");
const enrollCamStatus = document.getElementById("enroll-cam-status");

btnEnrollCam.addEventListener("click", async () => {
  const name = enrollCamName.value.trim();
  if (!name) {
    showToast("Please enter student name", "error");
    return;
  }

  btnEnrollCam.disabled = true;
  enrollCamStatus.textContent = `Capturing face for '${name}'...`;

  try {
    const res = await apiRequest("/api/enroll", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name }),
    });

    if (res.student_id) {
      showToast(`Enrolled '${name}' (ID: ${res.student_id}) successfully!`, "success");
      enrollCamStatus.textContent = `✅ Successfully enrolled ${name}`;
      enrollCamName.value = "";
      loadStudentsRoster();
    } else {
      enrollCamStatus.textContent = `❌ ${res.error || "Enrollment failed"}`;
      showToast(res.error || "Enrollment failed", "error");
    }
  } finally {
    btnEnrollCam.disabled = false;
  }
});

const enrollDropZone = document.getElementById("enroll-drop-zone");
const enrollPhotoFile = document.getElementById("enroll-photo-file");
const enrollPhotoPreview = document.getElementById("enroll-photo-preview");
const btnEnrollPhoto = document.getElementById("btn-enroll-photo");
const enrollPhotoName = document.getElementById("enroll-photo-name");
const enrollPhotoStatus = document.getElementById("enroll-photo-status");

enrollPhotoFile.addEventListener("change", () => {
  handleFilePreview(enrollPhotoFile, enrollPhotoPreview, btnEnrollPhoto);
});

btnEnrollPhoto.addEventListener("click", async () => {
  const name = enrollPhotoName.value.trim();
  const file = enrollPhotoFile.files[0];
  if (!name) {
    showToast("Please enter student name", "error");
    return;
  }
  if (!file) {
    showToast("Please choose a student portrait image", "error");
    return;
  }

  btnEnrollPhoto.disabled = true;
  enrollPhotoStatus.textContent = `Extracting face features for '${name}'...`;

  const formData = new FormData();
  formData.append("name", name);
  formData.append("photo", file);

  try {
    const res = await apiRequest("/api/enroll/photo", {
      method: "POST",
      body: formData,
    });

    if (res.student_id) {
      showToast(`Enrolled '${name}' from photo successfully!`, "success");
      enrollPhotoStatus.textContent = `✅ Enrolled as student ID: ${res.student_id}`;
      enrollPhotoName.value = "";
      enrollPhotoFile.value = "";
      enrollPhotoPreview.style.display = "none";
      const dropContent = enrollPhotoPreview.previousElementSibling;
      if (dropContent) dropContent.style.display = "block";
      btnEnrollPhoto.disabled = true;
      loadStudentsRoster();
    } else {
      enrollPhotoStatus.textContent = `❌ ${res.error || "Enrollment failed"}`;
      showToast(res.error || "Enrollment failed", "error");
    }
  } finally {
    btnEnrollPhoto.disabled = false;
  }
});

// ------------------------------------------------------------------ Attendance Records
const filterSessionSelect = document.getElementById("records-session-filter");
const btnRefreshRecords = document.getElementById("btn-refresh-records");
const btnExportCsv = document.getElementById("btn-export-csv");
const recordsTableBody = document.querySelector("#records-table tbody");

async function loadAttendanceRecords() {
  const sessionFilter = filterSessionSelect.value;
  btnExportCsv.href = `/api/attendance/export.csv${sessionFilter !== "ALL" ? `?session=${encodeURIComponent(sessionFilter)}` : ""}`;

  recordsTableBody.innerHTML = '<tr><td colspan="4" class="text-center">Loading records...</td></tr>';

  try {
    const records = await apiRequest(
      `/api/attendance${sessionFilter !== "ALL" ? `?session=${encodeURIComponent(sessionFilter)}` : ""}`
    );

    // Update stats
    document.getElementById("stat-filtered-records").textContent = records.length;
    const uniqueStudents = new Set(records.map((r) => r.student));
    document.getElementById("stat-unique-students").textContent = uniqueStudents.size;

    // Fetch total count
    const allRecords = sessionFilter === "ALL" ? records : await apiRequest("/api/attendance");
    document.getElementById("stat-total-records").textContent = allRecords.length;

    recordsTableBody.innerHTML = "";
    if (records.length === 0) {
      recordsTableBody.innerHTML = '<tr><td colspan="4" class="text-center">No attendance records found.</td></tr>';
      return;
    }

    records.forEach((r, idx) => {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td>${idx + 1}</td>
        <td><strong>${escapeHtml(r.student)}</strong></td>
        <td><span class="stat-pill" style="padding: 0.2rem 0.5rem; font-size: 0.8rem;">${escapeHtml(r.session || "General")}</span></td>
        <td>${new Date(r.timestamp).toLocaleString()}</td>
      `;
      recordsTableBody.appendChild(tr);
    });
  } catch (e) {
    recordsTableBody.innerHTML = '<tr><td colspan="4" class="text-center">Failed to load records.</td></tr>';
  }
}

filterSessionSelect.addEventListener("change", loadAttendanceRecords);
btnRefreshRecords.addEventListener("click", () => {
  loadAttendanceRecords();
  showToast("Attendance records refreshed", "info");
});

// ------------------------------------------------------------------ Students Roster
const rosterTableBody = document.querySelector("#roster-table tbody");
const btnRefreshRoster = document.getElementById("btn-refresh-roster");

async function loadStudentsRoster() {
  rosterTableBody.innerHTML = '<tr><td colspan="4" class="text-center">Loading students...</td></tr>';

  try {
    const students = await apiRequest("/api/students");
    document.getElementById("badge-enrolled-count").textContent = students.length;

    rosterTableBody.innerHTML = "";
    if (students.length === 0) {
      rosterTableBody.innerHTML = '<tr><td colspan="4" class="text-center">No students enrolled yet.</td></tr>';
      return;
    }

    students.forEach((s) => {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td>#${s.student_id}</td>
        <td><strong>${escapeHtml(s.name)}</strong></td>
        <td><span class="status-dot active"></span> Enrolled & Active</td>
        <td><button class="btn btn-danger btn-delete-student" data-id="${s.student_id}" data-name="${escapeHtml(s.name)}" style="padding: 0.25rem 0.6rem; font-size: 0.8rem;">Delete</button></td>
      `;
      rosterTableBody.appendChild(tr);
    });

    document.querySelectorAll(".btn-delete-student").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const studentId = btn.dataset.id;
        const studentName = btn.dataset.name;
        if (confirm(`Are you sure you want to delete '${studentName}' (ID: ${studentId}) and their records?`)) {
          try {
            await apiRequest(`/api/students/${studentId}`, { method: "DELETE" });
            showToast(`Deleted '${studentName}' successfully`, "info");
            loadStudentsRoster();
            loadAttendanceRecords();
            loadCourses();
          } catch (e) {}
        }
      });
    });
  } catch (e) {
    rosterTableBody.innerHTML = '<tr><td colspan="4" class="text-center">Failed to load students.</td></tr>';
  }
}

btnRefreshRoster.addEventListener("click", () => {
  loadStudentsRoster();
  showToast("Students roster refreshed", "info");
});

// ------------------------------------------------------------------ Initialization
window.addEventListener("DOMContentLoaded", () => {
  loadSessions();
  loadCourses();
  loadCurrentSession().then(checkCameraStatus);
  loadStudentsRoster();
  loadAttendanceRecords();
});
