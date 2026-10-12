# Export module (Person B, Sprint 3)
# Owns: viewing and exporting the attendance log (FR-6) with session support.

from __future__ import annotations

import csv
import sys
from pathlib import Path

import database

DEFAULT_CSV_PATH = Path(__file__).resolve().parent.parent / "data" / "attendance_export.csv"


def print_attendance_table(session_name: str | None = None) -> None:
    """Print the attendance log as a readable table, most recent first."""
    rows = database.get_attendance_log(session_name=session_name)
    if not rows:
        print("No attendance has been recorded yet.")
        return

    name_width = max(len("Student"), max(len(name) for name, _, _ in rows))
    sess_width = max(len("Session"), max(len(sess) for _, _, sess in rows))
    print(f"{'Student'.ljust(name_width)}  {'Session'.ljust(sess_width)}  Timestamp")
    print(f"{'-' * name_width}  {'-' * sess_width}  -------------------")
    for name, timestamp, sess in rows:
        print(f"{name.ljust(name_width)}  {sess.ljust(sess_width)}  {timestamp}")


def export_attendance_csv(path: Path = DEFAULT_CSV_PATH, session_name: str | None = None) -> Path:
    """Write the attendance log to a CSV file and return the path written to."""
    rows = database.get_attendance_log(session_name=session_name)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Student", "Timestamp", "Session"])
        writer.writerows(rows)
    return path


if __name__ == "__main__":
    # Run with: python src/export.py        -> prints the table
    #           python src/export.py --csv  -> prints the table AND saves a CSV file
    print_attendance_table()
    if "--csv" in sys.argv:
        csv_path = export_attendance_csv()
        print(f"\nExported to {csv_path}")
