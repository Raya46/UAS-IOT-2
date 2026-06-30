import os
from typing import Any

import asyncpg
from fastapi import APIRouter
from app.models.schemas import Event
from app.services.event_predictor import generate_mitigation
from app.services.congestion_predictor import predict_event_congestion
from app.services.event_scraper import scrape_and_store_events
from app.services.redis_client import get_redis
import json

router = APIRouter(prefix="/api/events", tags=["events"])

# Seed data event Jakarta — isi manual untuk prototype
EVENTS: list[Event] = [
    Event(
        id="evt-001",
        name="Konser Coldplay Jakarta",
        venue="GBK",
        lat=-6.2183,
        lng=106.8018,
        date="2026-07-15",
        time="19:00",
        estimated_crowd=80000,
        impact_radius_km=2.5,
        category="concert",
        crowd_zone="red",
        officer_min=100,
        officer_max=300,
        crowd_reason="Demo konser stadion berskala besar.",
    ),
    Event(
        id="evt-002",
        name="Final Piala Indonesia",
        venue="JIS",
        lat=-6.1275,
        lng=106.8676,
        date="2026-07-20",
        time="20:00",
        estimated_crowd=50000,
        impact_radius_km=2.0,
        category="sports",
        crowd_zone="red",
        officer_min=100,
        officer_max=300,
        crowd_reason="Demo final olahraga di stadion besar.",
    ),
]

@router.get("/", response_model=list[Event])
async def get_events():
    events = await _load_external_events()
    return events or EVENTS


@router.post("/refresh-external")
async def refresh_external_events():
    """
    Trigger manual crawling Enjoy Jakarta. Dipakai operator saat butuh data terbaru
    tanpa menunggu scheduler harian.
    """
    return await scrape_and_store_events()

@router.get("/{event_id}/mitigation")
async def get_event_mitigation(event_id: str):
    event = await _get_event(event_id)
    if not event:
        return {"error": "Event tidak ditemukan"}
    return generate_mitigation(event)

@router.post("/{event_id}/trigger-prediction")
async def trigger_event_prediction(event_id: str):
    """
    Trigger prediksi kemacetan untuk event tertentu dan publish ke WebSocket.
    Dipanggil manual oleh operator atau otomatis oleh scheduler.
    """
    event_model = await _get_event(event_id)
    event = event_model.model_dump() if event_model else None
    if not event:
        return {"error": "Event tidak ditemukan"}

    # Tambahkan lat/lng ke event dict
    event_dict = {**event, "lat": event["lat"], "lng": event["lng"]}
    prediction = predict_event_congestion(event_dict)

    if prediction:
        redis = get_redis()
        redis.publish("traffic.event_prediction", json.dumps(prediction))
        return {"success": True, "prediction": prediction["payload"]}

    return {"success": False, "message": "Event terlalu kecil untuk prediksi"}


async def _get_event(event_id: str) -> Event | None:
    external_events = await _load_external_events()
    event = next((e for e in external_events if e.id == event_id), None)
    if event:
        return event
    return next((e for e in EVENTS if e.id == event_id), None)


async def _load_external_events() -> list[Event]:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        return []

    conn = None
    try:
        conn = await asyncpg.connect(database_url.replace("+asyncpg", ""))
        rows = await conn.fetch(
            """
            SELECT
                external_id,
                source,
                name,
                COALESCE(venue, 'Jakarta') AS venue,
                ST_Y(location::geometry) AS lat,
                ST_X(location::geometry) AS lng,
                event_date::text AS date,
                COALESCE(to_char(event_time, 'HH24:MI'), '19:00') AS time,
                COALESCE(estimated_crowd, 0) AS estimated_crowd,
                COALESCE(category, 'general') AS category,
                COALESCE(raw_data, '{}'::jsonb) AS raw_data
            FROM external_events
            WHERE event_date >= CURRENT_DATE - INTERVAL '1 day'
            ORDER BY event_date ASC, event_time ASC NULLS LAST, scraped_at DESC
            LIMIT 100
            """
        )
    except Exception:
        return []
    finally:
        if conn:
            await conn.close()

    return [_row_to_event(row) for row in rows]


def _row_to_event(row: asyncpg.Record) -> Event:
    raw_data = _raw_dict(row["raw_data"])
    crowd = raw_data.get("crowd") or {}
    return Event(
        id=row["external_id"],
        name=row["name"],
        venue=row["venue"],
        lat=float(row["lat"]),
        lng=float(row["lng"]),
        date=row["date"],
        time=row["time"],
        end_date=raw_data.get("end_date"),
        estimated_crowd=int(row["estimated_crowd"] or 0),
        impact_radius_km=float(crowd.get("impact_radius_km") or 1.5),
        source=row["source"],
        source_url=raw_data.get("source_url"),
        category=row["category"],
        crowd_zone=crowd.get("zone"),
        officer_min=crowd.get("officer_min"),
        officer_max=crowd.get("officer_max"),
        crowd_confidence=crowd.get("confidence"),
        crowd_reason=crowd.get("reason"),
        estimation_source=crowd.get("estimation_source"),
    )


def _raw_dict(value: Any) -> dict:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}
