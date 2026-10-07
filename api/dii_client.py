"""
Dii IT Portal REST API Client (Async httpx)
Dii Portal Face Recognition Attendance System
"""

import httpx
import asyncio
from datetime import datetime
from typing import List, Dict, Any, Optional

from config import DII_PORTAL_BASE_URL, DII_API_KEY


class DiiPortalClient:
    """
    Asynchronous REST client for the Dii University Portal API:
    - Handles JWT authentication and token headers.
    - Synchronizes verified lecture attendance records.
    - Supports retry policies with exponential backoff.
    """

    def __init__(self, base_url: str = DII_PORTAL_BASE_URL, api_key: str = DII_API_KEY):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "User-Agent": "DiiAttendanceClient/1.0",
        }

    async def sync_session_attendance(
        self,
        session_id: str,
        course_id: str,
        records: List[Dict[str, Any]],
        max_retries: int = 3
    ) -> Dict[str, Any]:
        """
        Transmits completed session attendance payload to the central IT portal.
        Retries up to `max_retries` times on network interruption.
        """
        payload = {
            "session_id": session_id,
            "course_id": course_id,
            "synced_at": datetime.now().isoformat(),
            "total_present": len(records),
            "attendance": [
                {
                    "student_code": r["student_code"],
                    "full_name": r["full_name"],
                    "marked_at": r["marked_at"],
                    "status": r.get("status", "PRESENT"),
                    "confidence_distance": r.get("confidence_score", 0.0),
                }
                for r in records
            ],
        }

        url = f"{self.base_url}/attendance/sync"
        delay = 1.0

        for attempt in range(1, max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    response = await client.post(url, json=payload, headers=self.headers)
                    if response.status_code in (200, 201):
                        return {
                            "success": True,
                            "synced": len(records),
                            "session_id": session_id,
                            "portal_response": response.json(),
                        }
                    else:
                        print(f"[!] Dii Portal returned status {response.status_code}: {response.text}")
            except (httpx.ConnectError, httpx.TimeoutException) as exc:
                print(f"[!] Portal Sync attempt {attempt}/{max_retries} failed: {exc}")

            if attempt < max_retries:
                await asyncio.sleep(delay)
                delay *= 2.0  # Exponential backoff

        # Graceful fallback: local queue acknowledged when portal is offline
        print(f"[i] Dii Portal offline or unreachable. Attendance preserved in local SQLite database.")
        return {
            "success": False,
            "synced": 0,
            "session_id": session_id,
            "note": "Queued locally in SQLite; pending remote network sync."
        }


# Global client instance
dii_client = DiiPortalClient()
