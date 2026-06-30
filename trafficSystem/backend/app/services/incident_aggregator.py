import asyncio
import json
import uuid
import os
import asyncpg
from datetime import datetime, timezone, timedelta
from math import radians, cos, sin, asin, sqrt
from typing import Optional
from app.services.redis_client import get_redis
from app.models.schemas import Violation, IncidentPayload

# Radius dalam meter untuk menggabungkan sinyal yang dianggap satu insiden
DEDUP_RADIUS_M = 150
# Jendela waktu dalam detik untuk deduplication
DEDUP_WINDOW_S = 120

# Cache in-memory: key = incident_id, value = {lat, lng, type, count, first_seen, confidence}
_active_incidents: dict[str, dict] = {}

def _haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Jarak haversine dalam meter antara dua koordinat."""
    R = 6371000
    lat1, lng1, lat2, lng2 = map(radians, [lat1, lng1, lat2, lng2])
    dlat = lat2 - lat1
    dlng = lng2 - lng1
    a = sin(dlat/2)**2 + cos(lat1)*cos(lat2)*sin(dlng/2)**2
    return R * 2 * asin(sqrt(a))

def _find_existing_incident(lat: float, lng: float, v_type: str) -> Optional[str]:
    """Cari incident aktif dalam radius DEDUP_RADIUS_M dan tipe yang sama."""
    now = datetime.now(timezone.utc)
    expired_keys = []

    for inc_id, inc_data in _active_incidents.items():
        age_s = (now - inc_data["first_seen"]).total_seconds()
        if age_s > DEDUP_WINDOW_S:
            expired_keys.append(inc_id)
            continue
        if inc_data["type"] != v_type:
            continue
        dist = _haversine_m(lat, lng, inc_data["lat"], inc_data["lng"])
        if dist <= DEDUP_RADIUS_M:
            return inc_id

    for k in expired_keys:
        _active_incidents.pop(k, None)
    return None

def _calculate_confidence(source_count: int, severity: str) -> float:
    """
    Confidence score 0.0–1.0:
    - Setiap sumber tambahan meningkatkan confidence
    - Severity high menambah bobot
    """
    base = min(0.4 + (source_count - 1) * 0.2, 0.9)
    severity_bonus = {"high": 0.1, "medium": 0.05, "low": 0.0}.get(severity, 0.0)
    return min(base + severity_bonus, 1.0)

async def process_violation(violation: Violation) -> Optional[IncidentPayload]:
    """
    Terima raw violation dari CV worker, lakukan deduplication,
    kembalikan IncidentPayload terkonsolidasi atau None jika duplikat.
    """
    existing_id = _find_existing_incident(violation.lat, violation.lng, violation.type)

    if existing_id:
        # Ini duplikat — update count dan hitung rata-rata confidence, jangan publish event baru
        old_count = _active_incidents[existing_id]["source_count"]
        old_conf = _active_incidents[existing_id]["confidence"]
        new_count = old_count + 1
        new_conf = (old_conf * old_count + violation.confidence_score) / new_count
        
        _active_incidents[existing_id]["source_count"] = new_count
        _active_incidents[existing_id]["confidence"] = round(new_conf, 4)
        
        # Update database record
        conn = await asyncpg.connect(os.getenv("DATABASE_URL").replace("+asyncpg", ""))
        try:
            await conn.execute(
                """
                UPDATE incidents SET
                  source_count = $1,
                  confidence_score = $2,
                  updated_at = NOW()
                WHERE id = $3
                """,
                new_count,
                _active_incidents[existing_id]["confidence"],
                existing_id
            )
        finally:
            await conn.close()

        # Publish update confidence ke channel terpisah
        redis = get_redis()
        update_payload = {
            "type": "incident_update",
            "payload": {
                "incident_id": existing_id,
                "source_count": new_count,
                "confidence_score": _active_incidents[existing_id]["confidence"],
            }
        }
        redis.publish("traffic.incident_update", json.dumps(update_payload))
        return None

    # Ini incident baru
    incident_id = str(uuid.uuid4())
    confidence = violation.confidence_score
    now = datetime.now(timezone.utc)

    _active_incidents[incident_id] = {
        "lat": violation.lat,
        "lng": violation.lng,
        "type": violation.type,
        "source_count": 1,
        "first_seen": now,
        "confidence": confidence,
    }

    title = f"Deteksi {violation.type} di {violation.camera_id}"
    
    # Save new incident to database
    conn = await asyncpg.connect(os.getenv("DATABASE_URL").replace("+asyncpg", ""))
    try:
        await conn.execute(
            """
            INSERT INTO incidents (id, title, type, location, severity, confidence_score, status, source_count, camera_id, occurred_at, updated_at, snapshot_url)
            VALUES ($1, $2, $3, ST_SetSRID(ST_MakePoint($4, $5), 4326)::geography, $6, $7, $8, $9, $10, $11, $11, $12)
            """,
            incident_id,
            title,
            violation.type,
            violation.lng, # ST_MakePoint(lng, lat)
            violation.lat,
            violation.severity,
            confidence,
            "detected",
            1,
            violation.camera_id,
            now,
            violation.snapshot_url
        )
    finally:
        await conn.close()

    return IncidentPayload(
        id=incident_id,
        camera_id=violation.camera_id,
        type=violation.type,
        lat=violation.lat,
        lng=violation.lng,
        severity=violation.severity,
        confidence_score=confidence,
        source_count=1,
        status="detected",
        timestamp=now.isoformat(),
        snapshot_url=violation.snapshot_url,
    )
