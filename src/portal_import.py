# Portal photo import (plan.md, Week 1)
# Owns: bulk-enrolling students from a folder of portal photos, one file per photo, named after
# the student ("Surname Firstname.jpg"). Extra photos of the same student may carry a suffix:
# "Name NEW.jpg", "Name(1).jpg", "Name (2).png", "Name - Copy.jpg".
#
# Every photo is checked first: photos with no face or several faces are reported and skipped.
# A student can have several photos; all of them are stored as reference faces. If a portal face
# matches a student who is already enrolled (e.g. from the webcam), that student is linked instead
# of duplicated: they get the portal name and photos, and keep their attendance history.
# Re-running the import skips photos that were already imported, so new photos can be added later.
#
# Usage:
#   python src/portal_import.py Photos --dry-run           # show what would happen, change nothing
#   python src/portal_import.py Photos                     # import
#   python src/portal_import.py Photos --course "CS 301"   # import and add everyone to a course

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import face_recognition
import numpy as np

import database
import enrollment
import recognition

PHOTO_EXTENSIONS = {".jpg", ".jpeg", ".png"}
MAX_PHOTO_SIDE = 1600

# Two photos of the same student further apart than this probably aren't the same person.
SAME_PERSON_MAX_DISTANCE = 0.6
# When a new student's closest existing match is nearer than this, but wasn't linked because the
# match was ambiguous, the report mentions it so a person can double-check for a duplicate. (Portal
# photos share one pose and background, so different people commonly sit at 0.52-0.6 from each
# other; warning above 0.5 would flag half the class.)
NEAR_MATCH_DISTANCE = 0.5

# "Kabirova Omina NEW", "Kabirova Omina(1)", "Kabirova Omina (2)", "Kabirova Omina - Copy"
_EXTRA_PHOTO_SUFFIX = re.compile(r"(?:\s+new|\s*\(\d+\)|\s*-?\s*copy)+$", re.IGNORECASE)


@dataclass
class ImportReport:
    created: list[str] = field(default_factory=list)
    linked: list[str] = field(default_factory=list)
    photos_added: int = 0
    already_imported: int = 0
    warnings: list[str] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)

    def print(self, dry_run: bool) -> None:
        heading = "DRY RUN: nothing was saved" if dry_run else "Import finished"
        print(f"\n=== {heading} ===")
        print(f"New students:       {len(self.created)}")
        for line in self.created:
            print(f"  + {line}")
        print(f"Linked to existing: {len(self.linked)}")
        for line in self.linked:
            print(f"  = {line}")
        print(f"Reference photos stored: {self.photos_added}")
        if self.already_imported:
            print(f"Already imported (skipped): {self.already_imported}")
        if self.warnings:
            print(f"\nWarnings ({len(self.warnings)}) - imported, but worth a look:")
            for line in self.warnings:
                print(f"  ! {line}")
        if self.problems:
            print(f"\nProblems ({len(self.problems)}) - NOT imported:")
            for line in self.problems:
                print(f"  x {line}")


def name_from_filename(path: Path) -> str:
    """'Kabirova Omina NEW.jpg' / 'Kabirova Omina(1).jpg' -> 'Kabirova Omina' (spaces collapsed)."""
    return " ".join(_EXTRA_PHOTO_SUFFIX.sub("", path.stem.strip()).split())


def _is_extra_photo(path: Path) -> bool:
    return _EXTRA_PHOTO_SUFFIX.search(path.stem.strip()) is not None


def source_key(path: Path) -> str:
    """The id stored with each imported face, so a re-run recognizes files it already imported."""
    return f"portal:{path.name}"


def load_image(path: Path) -> np.ndarray | None:
    """Read an image as BGR, shrinking very large ones. Works with non-ASCII file names, which
    cv2.imread doesn't on Windows."""
    image = cv2.imdecode(np.fromfile(str(path), dtype=np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        return None
    longest_side = max(image.shape[:2])
    if longest_side > MAX_PHOTO_SIDE:
        scale = MAX_PHOTO_SIDE / longest_side
        image = cv2.resize(image, (0, 0), fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    return image


def encode_photo(image: np.ndarray) -> tuple[bytes | None, str | None]:
    """Return (encoding, None) for a photo with exactly one face, or (None, problem).

    Tries the fast detector on the photo as it is, then rotated (phone photos are sometimes saved
    sideways), then the slower but stronger CNN detector before giving up.
    """
    rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    attempts = [(rgb, "hog")]
    attempts += [(cv2.rotate(rgb, turn), "hog") for turn in
                 (cv2.ROTATE_90_CLOCKWISE, cv2.ROTATE_90_COUNTERCLOCKWISE, cv2.ROTATE_180)]
    attempts.append((rgb, "cnn"))

    for candidate, model in attempts:
        locations = face_recognition.face_locations(candidate, model=model)
        if len(locations) > 1:
            return None, f"{len(locations)} faces found - use a photo of only this student"
        if len(locations) == 1:
            encoding = face_recognition.face_encodings(
                candidate, known_face_locations=locations, num_jitters=enrollment.ENROLLMENT_JITTERS
            )[0]
            return encoding.astype(recognition.ENCODING_DTYPE).tobytes(), None
    return None, "no face found"


def _closest_student(encoding: bytes, known: list[tuple[int, str, bytes]]) -> tuple[int | None, float]:
    """The nearest student (by their closest photo) and that distance, with no threshold applied."""
    if not known:
        return None, float("inf")
    distances = face_recognition.face_distance(
        [recognition.bytes_to_encoding(e) for _, _, e in known], recognition.bytes_to_encoding(encoding)
    )
    best = int(np.argmin(distances))
    return known[best][0], float(distances[best])


def _collect_photos(folder: Path) -> dict[str, list[Path]]:
    """Group photo files by student name; within a student, the plain-named photo comes first."""
    groups: dict[str, list[Path]] = {}
    for path in sorted(folder.iterdir()):
        if path.is_file() and path.suffix.lower() in PHOTO_EXTENSIONS:
            groups.setdefault(name_from_filename(path), []).append(path)
    for paths in groups.values():
        paths.sort(key=lambda p: (_is_extra_photo(p), p.name.lower()))
    return groups


def import_folder(folder: Path, dry_run: bool = False, course_code: str | None = None) -> ImportReport:
    database.init_db()
    report = ImportReport()

    course_id = None
    if course_code is not None:
        course = next((c for c in database.get_all_courses() if c[1].lower() == course_code.strip().lower()), None)
        if course is None:
            raise SystemExit(f"Course '{course_code}' not found. Create it in the web app's Courses tab first.")
        course_id = course[0]

    # Kept up to date as we go (also in a dry run), so later photos are compared against students
    # created or renamed earlier in this same run.
    known = database.get_all_face_encodings()
    names = {sid: name for sid, name, _ in known}
    claimed: dict[int, str] = {}  # student_id -> portal name it was given in this run
    next_fake_id = -1  # dry run: stand-in ids for students that would be created

    groups = _collect_photos(folder)
    total = sum(len(paths) for paths in groups.values())
    done = 0
    for name, paths in groups.items():
        good: list[tuple[Path, bytes]] = []
        for path in paths:
            done += 1
            if database.is_source_file_imported(source_key(path)):
                report.already_imported += 1
                continue
            # Encoding takes a few seconds per photo (see enrollment.ENROLLMENT_JITTERS).
            print(f"  [{done}/{total}] {path.name}", flush=True)
            image = load_image(path)
            if image is None:
                report.problems.append(f"{path.name}: can't read the image file")
                continue
            encoding, problem = encode_photo(image)
            if problem is not None:
                report.problems.append(f"{path.name}: {problem}")
            else:
                good.append((path, encoding))
        if not good:
            continue

        first_path, first_encoding = good[0]
        for path, encoding in good[1:]:
            distance = float(face_recognition.face_distance(
                [recognition.bytes_to_encoding(first_encoding)], recognition.bytes_to_encoding(encoding)
            )[0])
            if distance > SAME_PERSON_MAX_DISTANCE:
                report.warnings.append(
                    f"{path.name} doesn't look much like {first_path.name} (distance {distance:.2f}) - same person?"
                )

        # Which student are these photos of? Same rules as live recognition, so a link is only
        # made when the face clearly belongs to one enrolled student.
        student_id, distance = recognition.match_face_with_distance(first_encoding, known)
        if student_id is not None and student_id in claimed and claimed[student_id] != name:
            report.problems.append(
                f"{first_path.name}: looks like the same person as '{claimed[student_id]}' "
                f"(distance {distance:.2f}) - not imported, please check the photos"
            )
            continue

        if student_id is not None:
            old_name = names[student_id]
            if old_name != name:
                report.linked.append(f"'{old_name}' -> '{name}' (face distance {distance:.2f})")
                if not dry_run:
                    database.rename_student(student_id, name)
            to_store = good
        else:
            near_id, near_distance = _closest_student(first_encoding, known)
            if near_distance < NEAR_MATCH_DISTANCE:
                report.warnings.append(
                    f"'{name}' was created as a new student, but looks a bit like '{names[near_id]}' "
                    f"(distance {near_distance:.2f}) - check they are different people"
                )
            if dry_run:
                student_id, next_fake_id = next_fake_id, next_fake_id - 1
            else:
                student_id = database.save_student(
                    name, first_encoding, source="portal", source_file=source_key(first_path)
                )
            report.created.append(f"{name} ({len(good)} photo{'s' if len(good) > 1 else ''})")
            report.photos_added += 1
            known.append((student_id, name, first_encoding))
            to_store = good[1:]

        for path, encoding in to_store:
            if not dry_run:
                database.add_face_encoding(student_id, encoding, "portal", source_key(path))
            known.append((student_id, name, encoding))
            report.photos_added += 1

        names[student_id] = name
        known = [(sid, names[sid], enc) for sid, _, enc in known]
        claimed[student_id] = name
        if course_id is not None and not dry_run:
            database.add_student_to_course(course_id, student_id)

    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Enroll students from a folder of portal photos.")
    parser.add_argument("folder", type=Path, help="folder with one photo per file, named after the student")
    parser.add_argument("--dry-run", action="store_true", help="check the photos and show what would happen, without saving")
    parser.add_argument("--course", help="also add every imported student to this course (its code, e.g. 'CS 301')")
    args = parser.parse_args(argv)
    # Names like "A’dil" must not crash printing on a Windows console that isn't set to UTF-8.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")

    if not args.folder.is_dir():
        print(f"Folder not found: {args.folder}")
        return 1

    print(f"Checking photos in {args.folder} ...")
    report = import_folder(args.folder, dry_run=args.dry_run, course_code=args.course)
    report.print(dry_run=args.dry_run)
    if args.dry_run:
        print("\nRun again without --dry-run to import.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
