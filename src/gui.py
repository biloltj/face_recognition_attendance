# GUI module
# Owns: a single desktop window (Tkinter) that wraps enrollment, live recognition/attendance, and
# the attendance log/export, so the whole app can be used with buttons and text fields instead of
# running separate scripts from a terminal.
#
# This module doesn't add new attendance logic of its own — it only wires together the modules
# that already own that logic: enrollment.py, recognition.py, database.py, export.py, and the
# RecognitionWorker/draw_detections helpers from main.py.

from __future__ import annotations

import threading
import tkinter as tk
from tkinter import messagebox, ttk

import cv2
from PIL import Image, ImageTk

import database
import enrollment
import export
import main
import recognition

# How often to grab a new webcam frame while the attendance tab is running, in milliseconds.
# 15ms is just a ceiling (~66 frames/second) — the camera's own frame rate is normally the real
# limit, this just makes sure the GUI doesn't wait on itself.
FRAME_INTERVAL_MS = 15


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Face Recognition Attendance")
        self.geometry("960x680")
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        database.init_db()

        # State for the "Take Attendance" tab — only meaningful while recognition is running.
        self._frame_source = None  # the frames_from_webcam() generator, while running
        self._worker = None  # the RecognitionWorker, while running
        self._after_id = None  # id from self.after(), so _on_stop_click can cancel the next tick
        self._photo = None  # keep a reference so Tkinter doesn't garbage-collect the displayed image

        # State for the "Enroll Student" tab's live preview — lets the operator see the framing is
        # good before capturing, and keeps the camera open across many students in a row instead of
        # reopening it (slow) for every single enrollment.
        self._enroll_frame_source = None
        self._enroll_after_id = None
        self._enroll_photo = None
        self._enroll_current_frame = None  # latest preview frame, captured on "Capture & Enroll"

        notebook = ttk.Notebook(self)
        notebook.pack(fill="both", expand=True)

        self._build_enroll_tab(notebook)
        self._build_attendance_tab(notebook)
        self._build_log_tab(notebook)

    # ------------------------------------------------------------------ Enroll tab
    def _build_enroll_tab(self, notebook: ttk.Notebook) -> None:
        tab = ttk.Frame(notebook, padding=20)
        notebook.add(tab, text="Enroll Student")

        ttk.Label(tab, text="Student name:").grid(row=0, column=0, sticky="w")
        self._name_entry = ttk.Entry(tab, width=30)
        self._name_entry.grid(row=0, column=1, padx=10)

        self._enroll_button = ttk.Button(tab, text="Capture && Enroll", command=self._on_enroll_click)
        self._enroll_button.grid(row=0, column=2)

        self._enroll_status = ttk.Label(tab, text="Look at the webcam and click 'Capture & Enroll'.")
        self._enroll_status.grid(row=1, column=0, columnspan=3, pady=15, sticky="w")

    def _on_enroll_click(self) -> None:
        name = self._name_entry.get().strip()
        if not name:
            messagebox.showerror("Missing name", "Please type the student's name first.")
            return

        self._enroll_button.state(["disabled"])
        self._enroll_status.config(text=f"Capturing '{name}'... look at the webcam.")

        # enroll_student() blocks for a second or more (it retries against the webcam if no face is
        # found yet), so it runs on a background thread to keep the window responsive. Tkinter
        # widgets may only be touched from the main thread, so the background thread hands its
        # result back via self.after(0, ...) instead of updating the labels itself.
        def worker() -> None:
            result = enrollment.enroll_student(name)
            self.after(0, lambda: self._on_enroll_done(name, result))

        threading.Thread(target=worker, daemon=True).start()

    def _on_enroll_done(self, name: str, result: enrollment.EnrollmentResult) -> None:
        self._enroll_button.state(["!disabled"])
        if result.student_id is None:
            self._enroll_status.config(text=result.error or "Enrollment failed.")
        else:
            self._enroll_status.config(text=f"Enrolled '{name}' (student_id={result.student_id}).")
            self._name_entry.delete(0, "end")

    # ------------------------------------------------------------- Take Attendance tab
    def _build_attendance_tab(self, notebook: ttk.Notebook) -> None:
        tab = ttk.Frame(notebook, padding=10)
        notebook.add(tab, text="Take Attendance")

        buttons = ttk.Frame(tab)
        buttons.pack(fill="x")
        self._start_button = ttk.Button(buttons, text="Start", command=self._on_start_click)
        self._start_button.pack(side="left")
        self._stop_button = ttk.Button(buttons, text="Stop", command=self._on_stop_click, state="disabled")
        self._stop_button.pack(side="left", padx=5)

        self._video_label = ttk.Label(tab, text="Click 'Start' to begin recognizing faces.", anchor="center")
        self._video_label.pack(fill="both", expand=True, pady=10)

    def _on_start_click(self) -> None:
        students = database.get_all_students()
        self._frame_source = recognition.frames_from_webcam(width=main.CAPTURE_WIDTH, height=main.CAPTURE_HEIGHT)
        self._worker = main.RecognitionWorker(students)
        self._start_button.state(["disabled"])
        self._stop_button.state(["!disabled"])
        self._update_frame()

    def _update_frame(self) -> None:
        frame = next(self._frame_source, None)
        if frame is None:
            messagebox.showerror("Webcam error", "Could not read from the webcam.")
            self._on_stop_click()
            return

        self._worker.submit_frame(frame.copy())
        main.draw_detections(frame, self._worker.get_detections())

        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        self._photo = ImageTk.PhotoImage(image=Image.fromarray(rgb_frame))
        self._video_label.config(image=self._photo, text="")

        self._after_id = self.after(FRAME_INTERVAL_MS, self._update_frame)

    def _on_stop_click(self) -> None:
        if self._after_id is not None:
            self.after_cancel(self._after_id)
            self._after_id = None
        if self._worker is not None:
            self._worker.stop()
            self._worker = None
        if self._frame_source is not None:
            self._frame_source.close()
            self._frame_source = None

        self._start_button.state(["!disabled"])
        self._stop_button.state(["disabled"])
        self._video_label.config(image="", text="Click 'Start' to begin recognizing faces.")

    # ------------------------------------------------------------------- Log tab
    def _build_log_tab(self, notebook: ttk.Notebook) -> None:
        tab = ttk.Frame(notebook, padding=10)
        notebook.add(tab, text="Attendance Log")

        buttons = ttk.Frame(tab)
        buttons.pack(fill="x")
        ttk.Button(buttons, text="Refresh", command=self._refresh_log).pack(side="left")
        ttk.Button(buttons, text="Export to CSV", command=self._on_export_click).pack(side="left", padx=5)

        self._log_tree = ttk.Treeview(tab, columns=("student", "timestamp"), show="headings")
        self._log_tree.heading("student", text="Student")
        self._log_tree.heading("timestamp", text="Timestamp")
        self._log_tree.pack(fill="both", expand=True, pady=10)

        self._refresh_log()

    def _refresh_log(self) -> None:
        self._log_tree.delete(*self._log_tree.get_children())
        for name, timestamp in database.get_attendance_log():
            self._log_tree.insert("", "end", values=(name, timestamp))

    def _on_export_click(self) -> None:
        path = export.export_attendance_csv()
        self._refresh_log()
        messagebox.showinfo("Exported", f"Attendance exported to:\n{path}")

    # ---------------------------------------------------------------------- misc
    def _on_close(self) -> None:
        self._on_stop_click()
        self.destroy()


def run() -> None:
    App().mainloop()


if __name__ == "__main__":
    run()
