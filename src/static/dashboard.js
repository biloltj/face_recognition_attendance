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
  });
});

// ------------------------------------------------------------------ State & Badges
let currentActiveSession = "General";

function updateCameraBadge(isRunning) {
  const dot = document.getElementById("camera-status-dot");
  const text = document.getElementById("badge-camera-status");
  const btnStart = document.getElementById("btn-start-stream");
  const btnStop = document.getElementById("btn-stop-stream");

  if (isRunning) {
    dot.classList.add("active");
    text.textContent = "Live Stream Active";
    btnStart.disabled = true;
    btnStop.disabled = false;
  } else {
    dot.classList.remove("active");
    text.textContent = "Camera Inactive";
    btnStart.disabled = false;
    btnStop.disabled = true;
  }
}

// ------------------------------------------------------------------ Sessions
async function loadSessions() {
  try {
    const data = await apiRequest("/api/sessions");
    const select = document.getElementById("session-select");
    const filterSelect = document.getElementById("records-session-filter");
    currentActiveSession = data.active || "General";
    document.getElementById("badge-active-session").textContent = currentActiveSession;

    // Populate dropdowns
    select.innerHTML = "";
    filterSelect.innerHTML = '<option value="ALL">All Sessions</option>';

    data.sessions.forEach((s) => {
      const opt1 = document.createElement("option");
      opt1.value = s;
      opt1.textContent = s;
      if (s === currentActiveSession) opt1.selected = true;
      select.appendChild(opt1);

      const opt2 = document.createElement("option");
      opt2.value = s;
      opt2.textContent = s;
      filterSelect.appendChild(opt2);
    });
  } catch (e) {
    console.error("Failed to load sessions:", e);
  }
}

document.getElementById("btn-set-session").addEventListener("click", async () => {
  const newSessionInput = document.getElementById("new-session-input");
  const select = document.getElementById("session-select");
  const sessionToSet = newSessionInput.value.trim() || select.value;

  if (!sessionToSet) {
    showToast("Please enter or select a session name", "error");
    return;
  }

  try {
    const res = await apiRequest("/api/sessions/active", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session: sessionToSet }),
    });
    currentActiveSession = res.active;
    document.getElementById("badge-active-session").textContent = currentActiveSession;
    newSessionInput.value = "";
    showToast(`Active session set to: ${currentActiveSession}`, "success");
    await loadSessions();
    loadAttendanceRecords();
  } catch (e) {
    console.error(e);
  }
});

document.getElementById("session-select").addEventListener("change", (e) => {
  document.getElementById("new-session-input").value = e.target.value;
});

// ------------------------------------------------------------------ Live Stream & Controls
const btnStartStream = document.getElementById("btn-start-stream");
const btnStopStream = document.getElementById("btn-stop-stream");
const chkAutoRec = document.getElementById("chk-auto-recognize");
const btnSingleCapture = document.getElementById("btn-single-capture");
const liveDetectionStatus = document.getElementById("live-detection-status");
const videoStream = document.getElementById("video-stream");

async function checkCameraStatus() {
  try {
    const status = await apiRequest("/api/camera/status");
    updateCameraBadge(status.running);
    chkAutoRec.checked = status.auto_recognize;
  } catch (e) {}
}

btnStartStream.addEventListener("click", async () => {
  try {
    btnStartStream.disabled = true;
    const res = await apiRequest("/api/camera/start", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        session: currentActiveSession,
        auto_recognize: chkAutoRec.checked,
      }),
    });
    updateCameraBadge(res.running);
    if (res.running) {
      videoStream.src = `/video_feed?t=${Date.now()}`;
      showToast("Live stream started", "success");
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
    showToast("Live stream stopped", "info");
  } catch (e) {}
});

chkAutoRec.addEventListener("change", async () => {
  try {
    const res = await apiRequest("/api/camera/toggle_recognition", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        enabled: chkAutoRec.checked,
        session: currentActiveSession,
      }),
    });
    if (res.auto_recognize) {
      showToast("Auto-attendance logging enabled on live stream", "info");
    } else {
      showToast("Auto-attendance logging paused", "info");
    }
  } catch (e) {}
});

btnSingleCapture.addEventListener("click", async () => {
  liveDetectionStatus.textContent = "Scanning faces...";
  btnSingleCapture.disabled = true;

  try {
    const res = await apiRequest("/api/attendance/capture", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session: currentActiveSession }),
    });

    if (res.length === 0) {
      liveDetectionStatus.textContent = "No face detected in snapshot.";
      showToast("No face detected in snapshot", "info");
    } else {
      const names = res.map((d) => d.name).join(", ");
      liveDetectionStatus.textContent = `Recognized: ${names}`;
      showToast(`Logged attendance for: ${names}`, "success");
      loadAttendanceRecords();
    }
  } finally {
    btnSingleCapture.disabled = false;
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
  handleFilePreview(attendancePhotoFile, attendancePhotoPreview, btnRecognizePhoto);
});

btnRecognizePhoto.addEventListener("click", async () => {
  const file = attendancePhotoFile.files[0];
  if (!file) return;

  btnRecognizePhoto.disabled = true;
  photoRecognitionResults.innerHTML = "<em>Analyzing photo with face recognition engine...</em>";

  const formData = new FormData();
  formData.append("photo", file);
  formData.append("session", currentActiveSession);

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
        badge.innerHTML = `<span><strong>${d.name}</strong></span><span>${d.name === "Unknown" ? "Unenrolled" : "Marked Present"}</span>`;
        photoRecognitionResults.appendChild(badge);
      });
      showToast(`Recognized ${detections.length} face(s)`, "success");
      loadAttendanceRecords();
    }
  } finally {
    btnRecognizePhoto.disabled = false;
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
        <td><strong>${r.student}</strong></td>
        <td><span class="stat-pill" style="padding: 0.2rem 0.5rem; font-size: 0.8rem;">${r.session || "General"}</span></td>
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
        <td><strong>${s.name}</strong></td>
        <td><span class="status-dot active"></span> Enrolled & Active</td>
        <td><button class="btn btn-danger btn-delete-student" data-id="${s.student_id}" data-name="${s.name}" style="padding: 0.25rem 0.6rem; font-size: 0.8rem;">Delete</button></td>
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
  checkCameraStatus();
  loadStudentsRoster();
  loadAttendanceRecords();
});
