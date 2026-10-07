"""
API Routes - Lecturer Portal, Session Controls & MJPEG Stream
Dii Portal Face Recognition Attendance System
"""

import io
import csv
import time
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, Response, HTTPException, status
from fastapi.responses import StreamingResponse, HTMLResponse
from pydantic import BaseModel

from config import SESSION_DURATION_SECONDS, BASE_DIR
from database.db import get_roster_for_course, get_session_attendance, mark_attendance
from core.session_manager import session_manager
from core.camera import ThreadedCamera
from api.dii_client import dii_client

router = APIRouter()

# Global camera instance
camera_instance: Optional[ThreadedCamera] = None


def get_camera() -> ThreadedCamera:
    """Provides singleton camera instance."""
    global camera_instance
    if camera_instance is None:
        camera_instance = ThreadedCamera(src=0)
    return camera_instance


class SessionStartRequest(BaseModel):
    course_id: str = "CS401"
    duration_seconds: int = SESSION_DURATION_SECONDS


class OverrideRequest(BaseModel):
    student_id: int
    status: str = "PRESENT"


@router.get("/", response_class=HTMLResponse)
async def serve_dashboard():
    """Serves the Lecturer Dashboard HTML interface."""
    template_path = BASE_DIR / "ui" / "templates" / "index.html"
    if template_path.exists():
        with open(template_path, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse(content="<h1>Lecturer Dashboard Template Not Found</h1>", status_code=404)


@router.post("/session/start")
async def start_attendance_session(payload: SessionStartRequest):
    """
    Starts a new timed attendance window for the specified course:
    - Isolates search space to course roster.
    - Boots background threaded camera with HUD overlay.
    """
    roster = get_roster_for_course(payload.course_id)
    if not roster:
        # Check if course exists, or provide informative response
        pass

    session = session_manager.start_session(
        course_id=payload.course_id,
        duration_seconds=payload.duration_seconds
    )

    cam = get_camera()
    cam.start()

    return {
        "status": "started",
        "session_id": session.session_id,
        "course_id": session.course_id,
        "duration_seconds": session.duration_seconds,
        "enrolled_count": len(session.roster)
    }


@router.post("/session/stop")
async def stop_attendance_session():
    """Manually stops the current attendance session, turns off camera, and syncs to Dii Portal."""
    session = session_manager.current_session
    session_id = session.session_id if session else None
    course_id = session.course_id if session else "UNKNOWN"

    # Stop session and camera
    stopped_id = session_manager.stop_current_session()
    cam = get_camera()
    cam.stop()

    sync_result = {}
    if stopped_id:
        records = session_manager.get_summary(stopped_id)
        sync_result = await dii_client.sync_session_attendance(
            session_id=stopped_id,
            course_id=course_id,
            records=records
        )

    return {
        "status": "stopped",
        "session_id": stopped_id or session_id,
        "portal_sync": sync_result
    }


@router.get("/session/status")
async def get_session_status():
    """Returns real-time status of the active session and countdown timer."""
    session = session_manager.current_session
    if not session or not session.is_active:
        return {
            "is_active": False,
            "session_id": None,
            "course_id": None,
            "remaining_seconds": 0,
            "records_count": 0
        }

    records = session_manager.get_summary(session.session_id)
    return {
        "is_active": True,
        "session_id": session.session_id,
        "course_id": session.course_id,
        "remaining_seconds": int(session.remaining_seconds),
        "total_enrolled": len(session.roster),
        "records_count": len(records)
    }


@router.get("/session/records")
async def get_attendance_records():
    """Retrieves live list of students recognized and marked present."""
    session = session_manager.current_session
    if not session:
        return {"records": []}
    records = session_manager.get_summary(session.session_id)
    return {"records": records}


@router.post("/session/override")
async def manual_override(payload: OverrideRequest):
    """Allows lecturer to manually log or adjust attendance for a student."""
    session = session_manager.current_session
    if not session or not session.is_active:
        raise HTTPException(status_code=400, detail="No active attendance session.")

    marked = session_manager.record_attendance(payload.student_id, confidence_score=0.0)
    return {
        "success": marked,
        "student_id": payload.student_id,
        "status": payload.status
    }


def mjpeg_frame_generator():
    """Continuously yields multipart JPEG frames for browser streaming."""
    cam = get_camera()
    while True:
        frame_bytes = cam.get_latest_frame_bytes()
        if frame_bytes:
            yield (
                b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n\r\n" + frame_bytes + b"\r\n"
            )
        time.sleep(0.033)  # ~30 FPS


@router.get("/stream")
async def live_video_stream():
    """Streams live webcam frames with countdown HUD overlay via MJPEG."""
    return StreamingResponse(
        mjpeg_frame_generator(),
        media_type="multipart/x-mixed-replace; boundary=frame"
    )


@router.get("/session/export")
async def export_attendance_csv(session_id: Optional[str] = None):
    """Generates and downloads a CSV attendance report."""
    target_session_id = session_id
    if not target_session_id:
        active = session_manager.current_session
        if active:
            target_session_id = active.session_id
        else:
            raise HTTPException(status_code=400, detail="No session specified or currently active.")

    records = get_session_attendance(target_session_id)

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Student Code", "Full Name", "Timestamp", "Confidence Distance", "Status"])
    for r in records:
        writer.writerow([
            r["student_code"],
            r["full_name"],
            r["marked_at"],
            f"{r['confidence_score']:.4f}" if r["confidence_score"] else "Manual",
            r["status"]
        ])

    csv_data = output.getvalue()
    return Response(
        content=csv_data,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=attendance_{target_session_id}.csv"}
    )
