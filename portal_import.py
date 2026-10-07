"""
Portal Photo Ingestion & Vector Encoding Pipeline
Dii Portal Face Recognition Attendance System
"""

import sys
import pickle
import argparse
from pathlib import Path
from typing import Optional, Dict, Any

from config import DATA_DIR, LOCAL_DB_PATH
from database.db import (
    init_db,
    add_course,
    register_student,
    enroll_student_in_course,
)
from core.face_engine import extract_face_embedding

ENCODINGS_CACHE_PATH = DATA_DIR / "encodings.pkl"


def load_embeddings_cache() -> Dict[str, Any]:
    """Loads existing precomputed embeddings cache from pickle if available."""
    if ENCODINGS_CACHE_PATH.exists():
        try:
            with open(ENCODINGS_CACHE_PATH, "rb") as f:
                return pickle.load(f)
        except Exception:
            return {}
    return {}


def save_embeddings_cache(cache: Dict[str, Any]) -> None:
    """Saves embedding dictionary to pickle for fast in-memory lookups."""
    ENCODINGS_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(ENCODINGS_CACHE_PATH, "wb") as f:
        pickle.dump(cache, f, protocol=pickle.HIGHEST_PROTOCOL)


def import_student_photo(
    photo_path: Path,
    student_code: str,
    full_name: str,
    course_id: Optional[str] = None,
    db_path: Optional[str] = None
) -> bool:
    """
    Ingests a single student photo:
    1. Extracts 128-d face embedding vector via ResNet.
    2. Registers student in SQLite database.
    3. Enrolls student in target course roster (if specified).
    4. Updates local pickle cache.
    """
    print(f"[*] Processing {full_name} ({student_code}) from {photo_path.name}...")
    
    embedding = extract_face_embedding(photo_path)
    if embedding is None:
        print(f"    [!] WARNING: No face detected in {photo_path.name}! Skipping.")
        return False

    # 1. Register in SQLite database
    s_id = register_student(
        student_code=student_code,
        full_name=full_name,
        face_encoding=embedding,
        db_path=db_path
    )

    # 2. Enroll in course if specified
    if course_id:
        enroll_student_in_course(course_id, s_id, db_path=db_path)

    # 3. Update pickle cache
    cache = load_embeddings_cache()
    cache[student_code] = {
        "student_id": s_id,
        "full_name": full_name,
        "course_id": course_id,
        "embedding": embedding
    }
    save_embeddings_cache(cache)

    print(f"    [+] Successfully enrolled {full_name} (ID: {s_id}) with 128-d vector.")
    return True


def bulk_import_from_directory(
    photos_dir: Path,
    course_id: str = "CS401",
    course_name: str = "Computer Vision & Attendance",
    db_path: Optional[str] = None
) -> int:
    """
    Scans a folder of photos (e.g. photos/) and enrolls all students found.
    Derives student_code and full_name from filenames:
    'Ayub.png' -> student_code: 'U_AYUB', full_name: 'Ayub'
    """
    if not photos_dir.is_dir():
        print(f"[!] Directory not found: {photos_dir}")
        return 0

    init_db(db_path)
    add_course(course_id, course_name, db_path)

    valid_extensions = {".png", ".jpg", ".jpeg", ".webp"}
    photo_files = [f for f in photos_dir.iterdir() if f.suffix.lower() in valid_extensions]

    if not photo_files:
        print(f"[!] No valid image files found in {photos_dir}")
        return 0

    success_count = 0
    print(f"=== Starting Bulk Enrollment for Course [{course_id}: {course_name}] ===")
    for idx, photo_file in enumerate(photo_files, start=1):
        clean_name = photo_file.stem.replace("_", " ").title()
        student_code = f"U21{idx:04d}"  # e.g., U210001, U210002

        success = import_student_photo(
            photo_path=photo_file,
            student_code=student_code,
            full_name=clean_name,
            course_id=course_id,
            db_path=db_path
        )
        if success:
            success_count += 1

    print(f"\n[OK] Bulk enrollment finished: {success_count}/{len(photo_files)} students enrolled successfully.")
    return success_count


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Dii Portal Photo Ingestion Pipeline")
    parser.add_argument("--photos", type=str, default="photos", help="Path to photos directory")
    parser.add_argument("--course", type=str, default="CS401", help="Target Course ID (e.g., CS401)")
    parser.add_argument("--course-name", type=str, default="Computer Vision", help="Course Name")
    args = parser.parse_args()

    photos_path = Path(args.photos).resolve()
    bulk_import_from_directory(photos_path, course_id=args.course, course_name=args.course_name)
