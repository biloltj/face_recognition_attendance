// Dashboard frontend — wires the three sections (Enroll, Take Attendance, Log) to the JSON API in
// webapp.py via fetch(). No camera code lives here: recognition/enrollment happen server-side
// against the machine's actual webcam, this just triggers them with a button and shows the result.

const nameInput = document.getElementById("name-input");
const enrollButton = document.getElementById("enroll-button");
const enrollStatus = document.getElementById("enroll-status");

const captureButton = document.getElementById("capture-button");
const captureStatus = document.getElementById("capture-status");

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
  if (result.student_id === null || result.student_id === undefined) {
    enrollStatus.textContent = result.error || "Enrollment failed.";
  } else {
    enrollStatus.textContent = `Enrolled '${name}' (student_id=${result.student_id}).`;
    nameInput.value = "";
  }
});

captureButton.addEventListener("click", async () => {
  captureButton.disabled = true;
  captureStatus.textContent = "Capturing...";

  const result = await postJSON("/api/attendance/capture");

  captureButton.disabled = false;
  if (result.error) {
    captureStatus.textContent = result.error;
  } else if (result.length === 0) {
    captureStatus.textContent = "No face detected — make sure you're in frame and try again.";
  } else {
    const names = result.map((detection) => detection.name).join(", ");
    captureStatus.textContent = `Recognized: ${names}`;
  }

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
