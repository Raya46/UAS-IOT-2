import os
import uuid
import asyncio
from datetime import datetime
from fastapi import APIRouter, UploadFile, File, HTTPException
from typing import Optional
from pydantic import BaseModel
from app.services.jsonl_reader import read_all_jsonl

router = APIRouter(prefix="/api/upload-video", tags=["upload-video"])

UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data", "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

JOBS: dict[str, dict] = {}


class UploadJobStatus(BaseModel):
    job_id: str
    status: str
    filename: str
    message: str
    synced_count: int = 0
    error: Optional[str] = None


@router.post("/")
async def upload_video(file: UploadFile = File(...)):
    if not file.filename or not file.filename.lower().endswith(".mp4"):
        raise HTTPException(status_code=400, detail="Only .mp4 files are supported")

    job_id = f"job-{uuid.uuid4().hex[:12]}"
    ext = os.path.splitext(file.filename)[1] or ".mp4"
    save_path = os.path.abspath(os.path.join(UPLOAD_DIR, f"{job_id}{ext}"))

    with open(save_path, "wb") as f:
        content = await file.read()
        f.write(content)

    JOBS[job_id] = {
        "job_id": job_id,
        "status": "queued",
        "filename": file.filename,
        "filepath": save_path,
        "created_at": datetime.utcnow().isoformat(),
        "synced_count": 0,
        "error": None,
    }

    asyncio.create_task(_process_job(job_id))

    return {
        "job_id": job_id,
        "status": "queued",
        "message": "Video uploaded, AI processing started",
    }


@router.get("/status/{job_id}", response_model=UploadJobStatus)
async def get_upload_status(job_id: str):
    job = JOBS.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return UploadJobStatus(
        job_id=job["job_id"],
        status=job["status"],
        filename=job["filename"],
        message="Processing: {}".format(job["status"]),
        synced_count=job.get("synced_count", 0),
        error=job.get("error"),
    )


async def _process_job(job_id: str):
    import sys
    import subprocess

    job = JOBS.get(job_id)
    if not job:
        return

    try:
        job["status"] = "processing"
        filepath = job["filepath"]

        # Read the count of events before processing
        previous_count = len(read_all_jsonl("events.jsonl"))

        # Run the detection command using python interpreter (sys.executable)
        # and working directory set to backend root directory
        backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

        print(f"[UPLOAD JOB] Starting AI processing for {filepath} using sys.executable={sys.executable}")

        cmd = [
            sys.executable,
            "ai/main.py",
            "--source",
            filepath,
            "--headless"
        ]

        # Run subprocess asynchronously using asyncio
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=backend_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )

        stdout, stderr = await proc.communicate()

        if proc.returncode != 0:
            err_msg = stderr.decode().strip()
            raise RuntimeError(f"AI processing script failed with exit code {proc.returncode}: {err_msg}")

        # Read the count of events after processing
        current_count = len(read_all_jsonl("events.jsonl"))

        job["status"] = "completed"
        job["synced_count"] = max(0, current_count - previous_count)
        print(f"[UPLOAD JOB] Finished processing {job_id}. Detected violations: {job['synced_count']}")
    except Exception as e:
        import traceback
        traceback.print_exc()
        job["status"] = "failed"
        job["error"] = str(e)
