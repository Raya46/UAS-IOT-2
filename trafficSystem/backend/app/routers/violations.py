from fastapi import APIRouter, Query, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional
from app.services.jsonl_reader import read_all_jsonl
import os
import json

router = APIRouter(prefix="/api/violation-events", tags=["violation-events"])

VIOLATIONS_DB_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "data", "violation_reviews.json"
)

HAYDEN_EVIDENCE_DIR = os.getenv(
    "HAYDEN_OUTPUTS_DIR",
    os.path.join(
        os.path.dirname(__file__),
        "..",
        "..",
        "..",
        "..",
        "hayden-ai-clone",
        "outputs",
        "events",
    ),
)  # This is the events dir; evidence sits one level up
HAYDEN_EVIDENCE_BASE = os.path.normpath(os.path.join(HAYDEN_EVIDENCE_DIR, os.pardir))


class ViolationEvent(BaseModel):
    event_id: str
    timestamp: str
    violation_type: str
    track_id: int
    vehicle_type: str
    plate_number: str
    confidence: float
    latitude: float
    longitude: float
    road_name: str
    duration_seconds: float
    source: str
    review_status: str = "pending"
    evidence_image: Optional[str] = None
    plate_crop: Optional[str] = None
    plate_confidence: Optional[float] = None


class ViolationStatusUpdate(BaseModel):
    review_status: str  # "approved" | "rejected"


def load_reviews() -> dict:
    if not os.path.exists(VIOLATIONS_DB_PATH):
        return {}
    try:
        with open(VIOLATIONS_DB_PATH) as f:
            return json.load(f)
    except Exception:
        return {}


def save_review(event_id: str, status: str) -> None:
    reviews = load_reviews()
    reviews[event_id] = status
    os.makedirs(os.path.dirname(VIOLATIONS_DB_PATH), exist_ok=True)
    with open(VIOLATIONS_DB_PATH, "w") as f:
        json.dump(reviews, f)


@router.get("/", response_model=list[ViolationEvent])
async def list_violation_events(
    violation_type: Optional[str] = Query(None),
    review_status: Optional[str] = Query(None),
    plate_number: Optional[str] = Query(None),
    source: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    all_events = read_all_jsonl("events.jsonl")
    if not all_events:
        return []

    reviews = load_reviews()

    filtered = []
    for r in all_events:
        if violation_type and r.get("violation_type") != violation_type:
            continue
        if plate_number:
            pn = r.get("plate_number", "").lower()
            if plate_number.lower() not in pn:
                continue
        if source:
            src = r.get("source", "").lower()
            if source.lower() not in src:
                continue

        status = reviews.get(r["event_id"], "pending")
        if review_status and status != review_status:
            continue

        filtered.append(
            ViolationEvent(
                event_id=r["event_id"],
                timestamp=r["timestamp"],
                violation_type=r["violation_type"],
                track_id=r["track_id"],
                vehicle_type=r["vehicle_type"],
                plate_number=r.get("plate_number", "UNKNOWN"),
                confidence=r["confidence"],
                latitude=r["latitude"],
                longitude=r["longitude"],
                road_name=r.get("road_name", ""),
                duration_seconds=r.get("duration_seconds", 0.0),
                source=r.get("source", ""),
                review_status=status,
                evidence_image=r.get("evidence_image"),
                plate_crop=r.get("plate_crop"),
                plate_confidence=r.get("plate_confidence"),
            )
        )

    filtered.reverse()
    return filtered[offset:][:limit]


@router.get("/{event_id}", response_model=ViolationEvent)
async def get_violation_event(event_id: str):
    all_events = read_all_jsonl("events.jsonl")
    reviews = load_reviews()
    for r in all_events:
        if r["event_id"] == event_id:
            return ViolationEvent(
                event_id=r["event_id"],
                timestamp=r["timestamp"],
                violation_type=r["violation_type"],
                track_id=r["track_id"],
                vehicle_type=r["vehicle_type"],
                plate_number=r.get("plate_number", "UNKNOWN"),
                confidence=r["confidence"],
                latitude=r["latitude"],
                longitude=r["longitude"],
                road_name=r.get("road_name", ""),
                duration_seconds=r.get("duration_seconds", 0.0),
                source=r.get("source", ""),
                review_status=reviews.get(event_id, "pending"),
                evidence_image=r.get("evidence_image"),
                plate_crop=r.get("plate_crop"),
                plate_confidence=r.get("plate_confidence"),
            )
    raise HTTPException(status_code=404, detail="Event not found")


@router.patch("/{event_id}/status")
async def update_violation_status(event_id: str, update: ViolationStatusUpdate):
    if update.review_status not in ("approved", "rejected"):
        raise HTTPException(
            status_code=400, detail="Status must be 'approved' or 'rejected'"
        )

    all_events = read_all_jsonl("events.jsonl")
    exists = any(r["event_id"] == event_id for r in all_events)
    if not exists:
        raise HTTPException(status_code=404, detail="Event not found")

    save_review(event_id, update.review_status)
    return {
        "success": True,
        "event_id": event_id,
        "review_status": update.review_status,
    }


@router.get("/evidence/{filename}")
async def serve_evidence(filename: str):
    images_dir = os.path.join(HAYDEN_EVIDENCE_BASE, "evidence", "images")
    plates_dir = os.path.join(HAYDEN_EVIDENCE_BASE, "evidence", "plates")

    for directory in (images_dir, plates_dir):
        filepath = os.path.join(directory, filename)
        if os.path.exists(filepath):
            return FileResponse(filepath)

    raise HTTPException(status_code=404, detail="Evidence file not found")
