"""
Main Application Entry Point - Dii Portal Face Recognition Attendance System
"""

import sys
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from database.db import init_db
from api.routes import router

# 1. Initialize SQLite Database Schema
init_db()

# 2. Initialize FastAPI Application
app = FastAPI(
    title="Dii Portal Face Recognition Attendance System",
    description="Automated contactless biometric attendance tracking with dynamic roster isolation and 10-minute session capture.",
    version="1.0.0"
)

# 3. Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 4. Include Web & API Endpoints
app.include_router(router)

if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("  DII PORTAL FACE RECOGNITION ATTENDANCE SYSTEM")
    print("  Lecturer Portal: http://127.0.0.1:8000")
    print("=" * 60 + "\n")
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
