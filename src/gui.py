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

        # The separate recognition window, while it's open (see _on_start_click / _on_stop_click).
        self._recognition_window = None

        self._notebook = ttk.Notebook(self)
        self._notebook.pack(fill="both", expand=True)

        self._build_enroll_tab(self._notebook)
        self._build_attendance_tab(self._notebook)
        self._build_log_tab(self._notebook)

    # ------------------------------------------------------------------ Enroll tab
    def _build_enroll_tab(self, notebook: ttk.Notebook) -> None:
        tab = ttk.Frame(notebook, padding=10)
        notebook.add(tab, text="Enroll Student")

        form = ttk.Frame(tab)
        form.pack(fill="x")
        ttk.Label(form, text="Student name:").pack(side="left")
        self._name_entry = ttk.Entry(form, width=30)
        self._name_entry.pack(side="left", padx=10)
        # Pressing Enter in the name field captures too, so a queue of students can be enrolled
        # without reaching for the mouse each time.
        self._name_entry.bind("<Return>", lambda _event: self._on_capture_click())

        buttons = ttk.Frame(tab)
        buttons.pack(fill="x", pady=(5, 0))
        self._enroll_start_button = ttk.Button(buttons, text="Start Camera", command=self._on_enroll_start_click)
        self._enroll_start_button.pack(side="left")
        self._enroll_stop_button = ttk.Button(
            buttons, text="Stop Camera", command=self._on_enroll_stop_click, state="disabled"
        )
        self._enroll_stop_button.pack(side="left", padx=5)
        self._capture_button = ttk.Button(
            buttons, text="Capture && Enroll", command=self._on_capture_click, state="disabled"
        )
        self._capture_button.pack(side="left", padx=5)

        self._enroll_status = ttk.Label(tab, text="Click 'Start Camera', then capture each student in turn.")
        self._enroll_status.pack(fill="x", pady=10, anchor="w")

        self._enroll_video_label = ttk.Label(tab, text="Camera preview appears here.", anchor="center")
        self._enroll_video_label.pack(fill="both", expand=True)

    def _on_enroll_start_click(self) -> None:
        if self._frame_source is not None:
            messagebox.showerror("Camera busy", "Stop 'Take Attendance' first — only one tab can use the webcam.")
            return

        self._enroll_frame_source = recognition.frames_from_webcam(
            width=main.CAPTURE_WIDTH, height=main.CAPTURE_HEIGHT
        )
        self._enroll_start_button.state(["disabled"])
        self._enroll_stop_button.state(["!disabled"])
        self._capture_button.state(["!disabled"])
        self._update_enroll_frame()

    def _update_enroll_frame(self) -> None:
        frame = next(self._enroll_frame_source, None)
        if frame is None:
            messagebox.showerror("Webcam error", "Could not read from the webcam.")
            self._on_enroll_stop_click()
            return

        self._enroll_current_frame = frame

        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        self._enroll_photo = ImageTk.PhotoImage(image=Image.fromarray(rgb_frame))
        self._enroll_video_label.config(image=self._enroll_photo, text="")

        self._enroll_after_id = self.after(FRAME_INTERVAL_MS, self._update_enroll_frame)

    def _on_enroll_stop_click(self) -> None:
        if self._enroll_after_id is not None:
            self.after_cancel(self._enroll_after_id)
            self._enroll_after_id = None
        if self._enroll_frame_source is not None:
            self._enroll_frame_source.close()
            self._enroll_frame_source = None
        self._enroll_current_frame = None

        self._enroll_start_button.state(["!disabled"])
        self._enroll_stop_button.state(["disabled"])
        self._capture_button.state(["disabled"])
        self._enroll_video_label.config(image="", text="Camera preview appears here.")

    def _on_capture_click(self) -> None:
        name = self._name_entry.get().strip()
        if not name:
            messagebox.showerror("Missing name", "Please type the student's name first.")
            return
        if self._enroll_current_frame is None:
            messagebox.showerror("Camera not started", "Click 'Start Camera' first.")
            return

        frame = self._enroll_current_frame.copy()
        self._capture_button.state(["disabled"])
        self._enroll_status.config(text=f"Capturing '{name}'...")

        # get_face_encoding() takes a moment (it's the same dlib computation used everywhere else),
        # so it runs on a background thread to keep the live preview smooth. The camera itself stays
        # open the whole time — that's what makes capturing the next student immediate instead of
        # paying camera-reopen cost per person.
        def worker() -> None:
            result = enrollment.enroll_from_frame(name, frame)
            self.after(0, lambda: self._on_enroll_done(name, result))

        threading.Thread(target=worker, daemon=True).start()

    def _on_enroll_done(self, name: str, result: enrollment.EnrollmentResult) -> None:
        # Re-enable capture only if the camera is still running (operator might have stopped it
        # while a capture was in flight).
        if self._enroll_frame_source is not None:
            self._capture_button.state(["!disabled"])
        if result.student_id is None:
            self._enroll_status.config(text=result.error or "Enrollment failed.")
        else:
            self._enroll_status.config(text=f"Enrolled '{name}' (student_id={result.student_id}). Next student?")
            self._name_entry.delete(0, "end")
            self._name_entry.focus_set()

    # ------------------------------------------------------------- Take Attendance tab
    def _build_attendance_tab(self, notebook: ttk.Notebook) -> None:
        tab = ttk.Frame(notebook, padding=20)
        notebook.add(tab, text="Take Attendance")

        self._start_button = ttk.Button(tab, text="Start", command=self._on_start_click)
        self._start_button.pack(anchor="w")

        ttk.Label(
            tab,
            text="Recognition opens in its own window, and this window hides while it runs.\n"
            "Click 'Stop' there (or close that window) to come back to this one.",
        ).pack(anchor="w", pady=15)

    def _on_start_click(self) -> None:
        if self._enroll_frame_source is not None:
            messagebox.showerror("Camera busy", "Stop the camera on 'Enroll Student' first — only one tab can use the webcam.")
            return

        students = database.get_all_students()
        self._frame_source = recognition.frames_from_webcam(width=main.CAPTURE_WIDTH, height=main.CAPTURE_HEIGHT)
        self._worker = main.RecognitionWorker(students)
        self._start_button.state(["disabled"])

        # Open a separate window for the live feed and hide the main (tabbed) window behind it —
        # per how the user wants this to look, rather than the tabs staying visible alongside it.
        self._recognition_window = tk.Toplevel(self)
        self._recognition_window.title("Take Attendance")
        self._recognition_window.protocol("WM_DELETE_WINDOW", self._on_stop_click)
        self._recognition_window.bind("<Escape>", lambda _event: self._on_stop_click())

        bar = ttk.Frame(self._recognition_window)
        bar.pack(fill="x")
        ttk.Button(bar, text="Stop", command=self._on_stop_click).pack(side="left", padx=10, pady=10)
        ttk.Label(bar, text="Press Esc, or close this window, to stop and return.").pack(side="left")

        self._video_label = ttk.Label(self._recognition_window, anchor="center")
        self._video_label.pack(fill="both", expand=True)

        self.withdraw()
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

        if self._recognition_window is not None:
            self._recognition_window.destroy()
            self._recognition_window = None
            self.deiconify()
            self.lift()

        self._start_button.state(["!disabled"])

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
        self._on_enroll_stop_click()
        self.destroy()


def run() -> None:
    App().mainloop()


if __name__ == "__main__":
    run()
