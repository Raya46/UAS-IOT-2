from pydantic import BaseModel
from typing import Optional, Literal
from datetime import datetime

IncidentType = Literal[
    "illegal_parking",
    "busway_violation",
    "congestion",
    "wrong_way",
    "hazard_lights",
    "red_light_violation",
    "illegal_u_turn",
    "unsafe_lane_change",
    "shoulder_violation",
]

IncidentStatus = Literal["detected", "confirmed", "dispatched", "resolved", "closed"]

class Camera(BaseModel):
    id: str
    name: str
    lat: float
    lng: float
    stream_url: Optional[str] = None  # URL video MP4 lokal atau HLS stream

class Zone(BaseModel):
    id: str
    name: str
    type: Literal["illegal_parking", "busway_corridor", "event_impact"]
    color: str                        # hex color, misal "#FF6B00"
    coordinates: list[list[float]]    # array of [lng, lat] untuk GeoJSON polygon

class Violation(BaseModel):
    id: str
    camera_id: str
    type: Literal["illegal_parking", "busway_violation", "congestion", "wrong_way", "hazard_lights"]
    lat: float
    lng: float
    severity: Literal["low", "medium", "high"]
    timestamp: datetime
    snapshot_url: Optional[str] = None
    confidence_score: float = 0.8

class Event(BaseModel):
    id: str
    name: str
    venue: str
    lat: float
    lng: float
    date: str
    time: str
    end_date: Optional[str] = None
    estimated_crowd: int
    impact_radius_km: float
    source: Optional[str] = None
    source_url: Optional[str] = None
    category: Optional[str] = None
    crowd_zone: Optional[Literal["green", "yellow", "orange", "red"]] = None
    officer_min: Optional[int] = None
    officer_max: Optional[int] = None
    crowd_confidence: Optional[float] = None
    crowd_reason: Optional[str] = None
    estimation_source: Optional[str] = None

class CongestionSegment(BaseModel):
    segment_id: str
    score: int                        # 0-100
    color: Literal["green", "yellow", "orange", "red"]
    coordinates: list[list[float]]    # [[lng1,lat1],[lng2,lat2]]

class IncidentPayload(BaseModel):
    id: str
    camera_id: str
    type: IncidentType
    lat: float
    lng: float
    severity: Literal["low", "medium", "high"]
    confidence_score: float          # 0.0–1.0
    source_count: int                # berapa banyak sinyal yang digabungkan
    status: IncidentStatus
    timestamp: str
    snapshot_url: Optional[str] = None
    description: Optional[str] = None
    vehicle_type: Optional[str] = None
    plate_number: Optional[str] = None
    plate_crop: Optional[str] = None
    plate_bbox: Optional[list[float]] = None
    plate_confidence: Optional[float] = None
    plate_note: Optional[str] = None
    video_time_seconds: Optional[float] = None
    camera_name: Optional[str] = None

class IncidentCreatePayload(BaseModel):
    id: Optional[str] = None
    camera_id: Optional[str] = None
    camera_name: Optional[str] = None
    type: IncidentType
    lat: float
    lng: float
    severity: Literal["low", "medium", "high"] = "medium"
    confidence_score: float = 0.85
    source_count: int = 1
    status: IncidentStatus = "detected"
    timestamp: Optional[str] = None
    snapshot_url: Optional[str] = None
    description: Optional[str] = None
    vehicle_type: Optional[str] = None
    plate_number: Optional[str] = None
    plate_crop: Optional[str] = None
    plate_bbox: Optional[list[float]] = None
    plate_confidence: Optional[float] = None
    plate_note: Optional[str] = None
    video_time_seconds: Optional[float] = None
    broadcast: bool = True

class IncidentStatusUpdate(BaseModel):
    incident_id: str
    status: Literal["confirmed", "dispatched", "resolved", "closed"]
    assigned_officer: Optional[str] = None
    resolution_notes: Optional[str] = None

class IncidentListResponse(BaseModel):
    items: list[IncidentPayload]
    total: int
    page: int
    page_size: int
