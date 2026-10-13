# Unit tests for src/recognition.py (see docs/04_test_plan.md: UT-1, UT-2)

from __future__ import annotations

import sys
from pathlib import Path
import unittest
import numpy as np

# Ensure src/ is on sys.path
SRC_DIR = Path(__file__).resolve().parent.parent / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import recognition


class TestRecognition(unittest.TestCase):
    def setUp(self):
        # Create deterministic synthetic 128-d face encodings (normalized float64 vectors)
        rng = np.random.RandomState(42)
        v1 = rng.randn(128).astype(np.float64)
        self.encoding1 = v1 / np.linalg.norm(v1)

        rng2 = np.random.RandomState(100)
        v2 = rng2.randn(128).astype(np.float64)
        self.encoding2 = v2 / np.linalg.norm(v2)

    def test_bytes_to_encoding_roundtrip(self):
        """Verify byte serialization and deserialization retains 128 float64 values."""
        raw_bytes = self.encoding1.tobytes()
        recovered = recognition.bytes_to_encoding(raw_bytes)
        self.assertEqual(recovered.shape, (128,))
        self.assertEqual(recovered.dtype, np.float64)
        np.testing.assert_allclose(recovered, self.encoding1)

    def test_ut1_match_same_person(self):
        """UT-1: Comparing two encodings from the same person (low distance) returns student_id."""
        known_students = [(1, "Alice", self.encoding1.tobytes())]

        # Create a slightly perturbed vector representing the same person (distance ~ 0.05)
        perturbation = np.zeros(128, dtype=np.float64)
        perturbation[0] = 0.05
        same_person_encoding = self.encoding1 + perturbation
        same_person_bytes = same_person_encoding.tobytes()

        matched_id = recognition.match_face(same_person_bytes, known_students, tolerance=0.5)
        self.assertEqual(matched_id, 1)

    def test_match_face_with_distance_returns_distance(self):
        """The match distance is returned so it can be saved as the attendance confidence."""
        known_students = [(1, "Alice", self.encoding1.tobytes()), (2, "Bob", self.encoding2.tobytes())]
        perturbation = np.zeros(128, dtype=np.float64)
        perturbation[0] = 0.05

        student_id, distance = recognition.match_face_with_distance(
            (self.encoding1 + perturbation).tobytes(), known_students
        )
        self.assertEqual(student_id, 1)
        self.assertAlmostEqual(distance, 0.05, places=6)

        self.assertEqual(recognition.match_face_with_distance(self.encoding2.tobytes(), known_students[:1]), (None, None))

    def test_ut2_reject_different_person(self):
        """UT-2: Comparing encodings from two different people (distance > tolerance) returns None."""
        known_students = [(1, "Alice", self.encoding1.tobytes())]

        # self.encoding2 is a distinct random vector (distance ~ 1.41 > 0.5)
        diff_person_bytes = self.encoding2.tobytes()

        matched_id = recognition.match_face(diff_person_bytes, known_students, tolerance=0.5)
        self.assertIsNone(matched_id)

    def test_ambiguity_margin_guard(self):
        """Verify min_margin rejects recognition when two enrolled students have near-identical distances."""
        # Target face at 0
        target = np.zeros(128, dtype=np.float64)
        target_bytes = target.tobytes()

        # Student 1 distance = 0.30 (within tolerance 0.5)
        s1 = np.zeros(128, dtype=np.float64)
        s1[0] = 0.30

        # Student 2 distance = 0.33 (within tolerance 0.5, but diff is only 0.03 < 0.08 min_margin)
        s2 = np.zeros(128, dtype=np.float64)
        s2[1] = 0.33

        known_students = [
            (10, "Student Ten", s1.tobytes()),
            (20, "Student Twenty", s2.tobytes()),
        ]

        # Should be rejected due to ambiguity
        matched_id = recognition.match_face(
            target_bytes, known_students, tolerance=0.5, min_margin=0.08
        )
        self.assertIsNone(matched_id)

    def test_empty_known_students(self):
        """Verify match_face returns None when no students are enrolled."""
        matched_id = recognition.match_face(self.encoding1.tobytes(), [])
        self.assertIsNone(matched_id)


if __name__ == "__main__":
    unittest.main()
