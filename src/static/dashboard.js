// Dashboard frontend — wires the three sections (Enroll, Take Attendance, Log) to the JSON API in
// webapp.py via fetch(). No camera code lives here: recognition/enrollment happen server-side
// against the machine's actual webcam, this just triggers them with a button and shows the result.
// The "from Photo" buttons instead upload an image file chosen in the browser.

const nameInput = document.getElementById("name-input");
const enrollButton = document.getElementById("enroll-button");
const enrollStatus = document.getElementById("enroll-status");
const enrollPhotoInput = document.getElementById("enroll-photo-input");
const enrollPhotoButton = document.getElementById("enroll-photo-button");

const captureButton = document.getElementById("capture-button");
const captureStatus = document.getElementById("capture-status");
const attendancePhotoInput = document.getElementById("attendance-photo-input");
const attendancePhotoButton = document.getElementById("attendance-photo-button");

const refreshButton = document.getElementById("refresh-button");
const logTableBody = document.querySelector("#log-table tbody");

async function postJSON(url, body) {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  return response.json();
}

// Sends a file as multipart form data (the format browsers use for file uploads), plus any extra
// text fields like the student's name.
async function postPhoto(url, file, fields = {}) {
  const formData = new FormData();
  formData.append("photo", file);
  for (const [key, value] of Object.entries(fields)) {
    formData.append(key, value);
  }
  const response = await fetch(url, { method: "POST", body: formData });
  return response.json();
}

function showEnrollResult(result, name) {
  if (result.student_id === null || result.student_id === undefined) {
    enrollStatus.textContent = result.error || "Enrollment failed.";
  } else {
    enrollStatus.textContent = `Enrolled '${name}' (student_id=${result.student_id}).`;
    nameInput.value = "";
  }
}

function showAttendanceResult(result, noFaceMessage) {
  if (result.error) {
    captureStatus.textContent = result.error;
  } else if (result.length === 0) {
    captureStatus.textContent = noFaceMessage;
  } else {
    const names = result.map((detection) => detection.name).join(", ");
    captureStatus.textContent = `Recognized: ${names}`;
  }
}

enrollButton.addEventListener("click", async () => {
  const name = nameInput.value.trim();
  if (!name) {
    enrollStatus.textContent = "Please type the student's name first.";
    return;
  }

  enrollButton.disabled = true;
  enrollStatus.textContent = `Capturing '${name}'... look at the webcam.`;

  const result = await postJSON("/api/enroll", { name });

  enrollButton.disabled = false;
  showEnrollResult(result, name);
});

enrollPhotoButton.addEventListener("click", async () => {
  const name = nameInput.value.trim();
  const file = enrollPhotoInput.files[0];
  if (!name) {
    enrollStatus.textContent = "Please type the student's name first.";
    return;
  }
  if (!file) {
    enrollStatus.textContent = "Please choose a photo first.";
    return;
  }

  enrollPhotoButton.disabled = true;
  enrollStatus.textContent = `Enrolling '${name}' from photo...`;

  const result = await postPhoto("/api/enroll/photo", file, { name });

  enrollPhotoButton.disabled = false;
  showEnrollResult(result, name);
  if (result.student_id !== null && result.student_id !== undefined) {
    enrollPhotoInput.value = "";
  }
});

captureButton.addEventListener("click", async () => {
  captureButton.disabled = true;
  captureStatus.textContent = "Capturing...";

  const result = await postJSON("/api/attendance/capture");

  captureButton.disabled = false;
  showAttendanceResult(result, "No face detected — make sure you're in frame and try again.");

  await refreshLog();
});

attendancePhotoButton.addEventListener("click", async () => {
  const file = attendancePhotoInput.files[0];
  if (!file) {
    captureStatus.textContent = "Please choose a photo first.";
    return;
  }

  attendancePhotoButton.disabled = true;
  captureStatus.textContent = "Recognizing faces in photo...";

  const result = await postPhoto("/api/attendance/photo", file);

  attendancePhotoButton.disabled = false;
  showAttendanceResult(result, "No face detected in this photo — try a clearer, front-facing one.");

  await refreshLog();
});

async function refreshLog() {
  const response = await fetch("/api/attendance");
  const rows = await response.json();

  logTableBody.innerHTML = "";
  for (const row of rows) {
    const tr = document.createElement("tr");
    const nameCell = document.createElement("td");
    nameCell.textContent = row.student;
    const timeCell = document.createElement("td");
    timeCell.textContent = row.timestamp;
    tr.append(nameCell, timeCell);
    logTableBody.appendChild(tr);
  }
}

refreshButton.addEventListener("click", refreshLog);

refreshLog();
