"""
Unit Tests for FastAPI Endpoints & Session Routes
Dii Portal Face Recognition Attendance System
"""

import unittest
from fastapi.testclient import TestClient
from main import app
from database.db import add_course, register_student, enroll_student_in_course
import numpy as np


class TestAPIRoutes(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        add_course("CS401", "Computer Vision")
        v = np.random.rand(128).astype(np.float64)
        s_id = register_student("U_TEST1", "Test Student", v)
        enroll_student_in_course("CS401", s_id)

    def test_serve_dashboard(self):
        """GET / should serve the Lecturer Dashboard."""
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Dii Portal", response.text)

    def test_session_lifecycle_endpoints(self):
        """Test starting, polling status, and stopping an attendance session."""
        # 1. Start Session
        start_res = self.client.post("/session/start", json={"course_id": "CS401", "duration_seconds": 600})
        self.assertEqual(start_res.status_code, 200)
        start_data = start_res.json()
        self.assertEqual(start_data["status"], "started")
        self.assertEqual(start_data["course_id"], "CS401")

        # 2. Check Status
        status_res = self.client.get("/session/status")
        self.assertEqual(status_res.status_code, 200)
        status_data = status_res.json()
        self.assertTrue(status_data["is_active"])
        self.assertEqual(status_data["course_id"], "CS401")

        # 3. Check Records
        records_res = self.client.get("/session/records")
        self.assertEqual(records_res.status_code, 200)

        # 4. Export CSV
        export_res = self.client.get("/session/export")
        self.assertEqual(export_res.status_code, 200)
        self.assertIn("text/csv", export_res.headers["content-type"])

        # 5. Stop Session
        stop_res = self.client.post("/session/stop")
        self.assertEqual(stop_res.status_code, 200)
        self.assertEqual(stop_res.json()["status"], "stopped")


if __name__ == "__main__":
    unittest.main()
