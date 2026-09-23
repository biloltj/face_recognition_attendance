# Export module (Person B, Sprint 3)
# Owns: viewing and exporting the attendance log (FR-6).

from __future__ import annotations

import csv
import sys
from pathlib import Path

import database

DEFAULT_CSV_PATH = Path(__file__).resolve().parent.parent / "data" / "attendance_export.csv"


def print_attendance_table() -> None:
    """Print the full attendance log as a readable table, most recent first."""
    rows = database.get_attendance_log()
    if not rows:
        print("No attendance has been recorded yet.")
        return

    name_width = max(len("Student"), max(len(name) for name, _ in rows))
    print(f"{'Student'.ljust(name_width)}  Timestamp")
    print(f"{'-' * name_width}  ---------")
    for name, timestamp in rows:
        print(f"{name.ljust(name_width)}  {timestamp}")


def export_attendance_csv(path: Path = DEFAULT_CSV_PATH) -> Path:
    """Write the full attendance log to a CSV file and return the path written to."""
    rows = database.get_attendance_log()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Student", "Timestamp"])
        writer.writerows(rows)
    return path


if __name__ == "__main__":
    # Run with: python src/export.py        -> prints the table
    #           python src/export.py --csv  -> prints the table AND saves a CSV file
    print_attendance_table()
    if "--csv" in sys.argv:
        csv_path = export_attendance_csv()
        print(f"\nExported to {csv_path}")
