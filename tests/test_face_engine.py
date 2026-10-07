"""
Unit Tests for Face Engine & Vector Distance Matching
Dii Portal Face Recognition Attendance System
"""

import unittest
import numpy as np
from pathlib import Path
from core.face_engine import (
    compute_euclidean_distance,
    match_face_against_roster,
    extract_face_embedding,
)


class TestFaceEngine(unittest.TestCase):
    def test_euclidean_distance_identical_vectors(self):
        """Distance between identical vectors must be 0.0."""
        v1 = np.ones(128, dtype=np.float64)
        dist = compute_euclidean_distance(v1, v1)
        self.assertAlmostEqual(dist, 0.0, places=6)

    def test_euclidean_distance_known_difference(self):
        """Calculates sqrt(sum(diff^2)). For 128 elements differing by 0.1, distance is sqrt(128 * 0.01)."""
        v1 = np.zeros(128, dtype=np.float64)
        v2 = np.full(128, 0.1, dtype=np.float64)
        expected = np.sqrt(128 * 0.01)
        dist = compute_euclidean_distance(v1, v2)
        self.assertAlmostEqual(dist, expected, places=5)

    def test_match_face_against_roster(self):
        """Tests roster matching with positive and negative matches."""
        target_vector = np.random.rand(128).astype(np.float64)
        other_vector = np.random.rand(128).astype(np.float64)

        # Normalize vectors
        target_vector /= np.linalg.norm(target_vector)
        other_vector /= np.linalg.norm(other_vector)

        roster = [
            (1, "U21001", "Student One", target_vector),
            (2, "U21002", "Student Two", other_vector),
        ]

        # 1. Query with exact target vector
        match = match_face_against_roster(target_vector, roster, threshold=0.50)
        self.assertIsNotNone(match)
        s_id, code, name, dist = match
        self.assertEqual(s_id, 1)
        self.assertEqual(code, "U21001")
        self.assertAlmostEqual(dist, 0.0, places=5)

        # 2. Query with an orthogonal/distant vector beyond threshold
        impostor_vector = -target_vector  # opposite direction
        no_match = match_face_against_roster(impostor_vector, roster, threshold=0.50)
        self.assertIsNone(no_match)

    def test_real_photo_face_extraction(self):
        """Verifies that face detection and 128-d vector extraction works on actual photo if present."""
        sample_photo = Path(__file__).resolve().parent.parent / "photos" / "Ayub.png"
        if sample_photo.exists():
            embedding = extract_face_embedding(sample_photo)
            self.assertIsNotNone(embedding)
            self.assertIsInstance(embedding, np.ndarray)
            self.assertEqual(embedding.shape, (128,))
            self.assertEqual(embedding.dtype, np.float64)


if __name__ == "__main__":
    unittest.main()
