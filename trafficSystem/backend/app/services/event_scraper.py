import asyncio
import asyncpg
import os
import httpx
import json
from datetime import date, timedelta

from app.services.event_crowd_estimator import (
    estimate_event_profile,
    estimate_event_profile_with_gemini,
    extract_event_time,
)

# -------------------------------------------------------
# Sumber 1: data.jakarta.go.id open data
# Dataset titik rawan kemacetan tersedia di:
# https://data.jakarta.go.id/dataset/titik-rawan-kemacetan-di-dki-jakarta
# -------------------------------------------------------
JAKARTA_OPENDATA_BASE = "https://data.jakarta.go.id"
ENJOY_JAKARTA_API = (
    "https://disparekraf.jakarta.go.id/jakartatourism-be/api/public/v1/event"
)
ENJOY_JAKARTA_EVENT_URL = "https://enjoy.jakarta.go.id/event-detail/{slug}"

# -------------------------------------------------------
# Seed data: event-event besar Jakarta yang berulang tahunan
# Update manual daftar ini setiap kuartal
# -------------------------------------------------------
RECURRING_EVENTS = [
    {
        "external_id": "jakarta-fair-annual",
        "source": "manual",
        "name": "Pekan Raya Jakarta (Jakarta Fair)",
        "venue": "Jakarta International Expo Kemayoran",
        "lat": -6.146,
        "lng": 106.845,
        "estimated_crowd": 100000,
        "category": "fair",
    },
    {
        "external_id": "jakarta-marathon-annual",
        "source": "manual",
        "name": "Jakarta Marathon",
        "venue": "Monas & sekitar Sudirman",
        "lat": -6.1754,
        "lng": 106.8272,
        "estimated_crowd": 31000,
        "category": "marathon",
    },
    {
        "external_id": "gbk-concert-template",
        "source": "manual",
        "name": "Konser GBK (template)",
        "venue": "Gelora Bung Karno",
        "lat": -6.2183,
        "lng": 106.8018,
        "estimated_crowd": 80000,
        "category": "concert",
    },
    {
        "external_id": "jis-concert-template",
        "source": "manual",
        "name": "Jakarta International Stadium (template)",
        "venue": "Jakarta International Stadium",
        "lat": -6.1275,
        "lng": 106.8676,
        "estimated_crowd": 50000,
        "category": "concert",
    },
]


def _database_url() -> str | None:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        return None
    return database_url.replace("+asyncpg", "")


async def fetch_enjoy_jakarta_events(
    limit: int | None = None,
    pages: int | None = None,
    lang: str = "en",
) -> list[dict]:
    """
    Ambil event dari endpoint resmi yang digunakan halaman enjoy.jakarta.go.id/events.
    Endpoint ini menyediakan tanggal, lokasi, dan koordinat yang lebih akurat daripada
    scraping DOM SPA.
    """
    limit = limit or int(os.getenv("ENJOY_JAKARTA_LIMIT", "48"))
    pages = pages or int(os.getenv("ENJOY_JAKARTA_PAGES", "1"))
    start_date = os.getenv("ENJOY_JAKARTA_START_DATE", date.today().isoformat())
    events: list[dict] = []

    async with httpx.AsyncClient(timeout=20) as client:
        for page in range(1, pages + 1):
            response = await client.get(
                ENJOY_JAKARTA_API,
                headers={"Accept": "application/json"},
                params={
                    "page": page,
                    "limit": limit,
                    "lang": lang,
                    "sort_by": "ASC",
                    "start_date": start_date,
                },
            )
            response.raise_for_status()
            payload = response.json()
            page_items = (payload.get("data") or {}).get("data") or []
            events.extend(item for item in page_items if item.get("start_date"))
            if not ((payload.get("data") or {}).get("next_page_url")):
                break

    return events


async def normalize_enjoy_jakarta_event(event: dict) -> dict | None:
    lat = _to_float(event.get("location_latitude"))
    lng = _to_float(event.get("location_longitude"))
    if lat is None or lng is None:
        return None

    profile = await estimate_event_profile_with_gemini(event)
    event_time = extract_event_time(event, profile["category"])
    slug = event.get("slug") or str(event.get("id"))
    venue = _compact_venue(event.get("location_name"))
    raw_data = {
        "source_url": ENJOY_JAKARTA_EVENT_URL.format(slug=slug),
        "slug": slug,
        "banner_url": event.get("banner_url"),
        "start_date": event.get("start_date"),
        "end_date": event.get("end_date"),
        "location_name": event.get("location_name"),
        "crowd": {
            "zone": profile["crowd_zone"],
            "range_min": profile["crowd_range_min"],
            "range_max": profile["crowd_range_max"],
            "officer_min": profile["officer_min"],
            "officer_max": profile["officer_max"],
            "impact_level": profile["impact_level"],
            "impact_radius_km": profile["impact_radius_km"],
            "confidence": profile["confidence"],
            "reason": profile["reason"],
            "estimation_source": profile["estimation_source"],
        },
    }

    return {
        "external_id": f"enjoy-jakarta-{event.get('id')}",
        "source": "enjoy_jakarta",
        "name": event.get("title") or "Jakarta Event",
        "venue": venue,
        "lat": lat,
        "lng": lng,
        "event_date": event.get("start_date"),
        "event_time": event_time,
        "end_time": None,
        "estimated_crowd": profile["estimated_crowd"],
        "category": profile["category"],
        "raw_data": raw_data,
        "is_verified": True,
    }


def _to_float(value) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _compact_venue(location_name: str | None) -> str:
    if not location_name:
        return "Jakarta"
    parts = [part.strip() for part in location_name.split(",") if part.strip()]
    return parts[0] if parts else location_name[:250]


async def _upsert_external_event(conn: asyncpg.Connection, event: dict):
    await conn.execute(
        """
        INSERT INTO external_events
            (external_id, source, name, venue, location, event_date, event_time, end_time,
             estimated_crowd, category, raw_data, is_verified)
        VALUES
            ($1, $2, $3, $4, ST_SetSRID(ST_MakePoint($6, $5), 4326)::geography,
             $7::date, $8::time, $9::time, $10, $11, $12::jsonb, $13)
        ON CONFLICT (external_id) DO UPDATE SET
            source = EXCLUDED.source,
            name = EXCLUDED.name,
            venue = EXCLUDED.venue,
            location = EXCLUDED.location,
            event_date = EXCLUDED.event_date,
            event_time = EXCLUDED.event_time,
            end_time = EXCLUDED.end_time,
            estimated_crowd = EXCLUDED.estimated_crowd,
            category = EXCLUDED.category,
            raw_data = EXCLUDED.raw_data,
            is_verified = EXCLUDED.is_verified,
            scraped_at = NOW()
        """,
        event["external_id"],
        event["source"],
        event["name"],
        event["venue"],
        event["lat"],
        event["lng"],
        event["event_date"],
        event["event_time"],
        event["end_time"],
        event["estimated_crowd"],
        event["category"],
        json.dumps(event["raw_data"]),
        event["is_verified"],
    )


async def scrape_and_store_events():
    """
    Tugas scraping harian. Mengambil event dari Enjoy Jakarta dan menyimpan
    tanggal/lokasi akurat plus estimasi crowd untuk operasi lalu lintas.
    """
    database_url = _database_url()
    if not database_url:
        return {"success": False, "message": "DATABASE_URL belum diset", "stored": 0}

    conn = await asyncpg.connect(database_url)
    stored = 0
    errors: list[str] = []
    try:
        try:
            raw_events = await fetch_enjoy_jakarta_events()
            for raw_event in raw_events:
                event = await normalize_enjoy_jakarta_event(raw_event)
                if not event:
                    continue
                await _upsert_external_event(conn, event)
                stored += 1
        except Exception as exc:
            errors.append(f"Enjoy Jakarta API gagal: {exc}")

        for event in RECURRING_EVENTS:
            profile = estimate_event_profile(event)
            event = {
                **event,
                "event_date": date.today().isoformat(),
                "event_time": "19:00",
                "raw_data": {
                    "crowd": {
                        "zone": profile["crowd_zone"],
                        "range_min": profile["crowd_range_min"],
                        "range_max": profile["crowd_range_max"],
                        "officer_min": profile["officer_min"],
                        "officer_max": profile["officer_max"],
                        "impact_level": profile["impact_level"],
                        "impact_radius_km": profile["impact_radius_km"],
                        "confidence": profile["confidence"],
                        "reason": profile["reason"],
                        "estimation_source": profile["estimation_source"],
                    }
                },
            }
            await conn.execute(
                """
                INSERT INTO external_events
                    (external_id, source, name, venue, location, estimated_crowd, category,
                     raw_data, is_verified, event_date, event_time)
                VALUES
                    ($1, $2, $3, $4, ST_SetSRID(ST_MakePoint($6, $5), 4326)::geography,
                     $7, $8, $9::jsonb, true, $10::date, $11::time)
                ON CONFLICT (external_id) DO UPDATE SET
                    name = EXCLUDED.name,
                    estimated_crowd = EXCLUDED.estimated_crowd,
                    category = EXCLUDED.category,
                    raw_data = EXCLUDED.raw_data,
                    scraped_at = NOW()
                """,
                event["external_id"],
                event["source"],
                event["name"],
                event["venue"],
                event["lat"],
                event["lng"],
                event["estimated_crowd"],
                event["category"],
                json.dumps(event["raw_data"]),
                event["event_date"],
                event["event_time"],
            )
            stored += 1
    finally:
        await conn.close()

    return {"success": True, "stored": stored, "errors": errors}
