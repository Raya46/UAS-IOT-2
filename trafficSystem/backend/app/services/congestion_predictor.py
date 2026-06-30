import asyncpg
import os
import json
from datetime import datetime, timezone, timedelta
from math import radians, cos, sin, asin, sqrt

from app.services.event_crowd_estimator import classify_crowd

def _haversine_km(lat1, lng1, lat2, lng2) -> float:
    R = 6371
    lat1, lng1, lat2, lng2 = map(radians, [lat1, lng1, lat2, lng2])
    dlat = lat2 - lat1
    dlng = lng2 - lng1
    a = sin(dlat/2)**2 + cos(lat1)*cos(lat2)*sin(dlng/2)**2
    return R * 2 * asin(sqrt(a))

# Konfigurasi dampak berdasarkan jumlah massa
IMPACT_CONFIG = {
    "critical": {"min_crowd": 50000, "radius_km": 5.0, "hours_before": 3, "hours_after": 2},
    "high":     {"min_crowd": 20000, "radius_km": 3.0, "hours_before": 2, "hours_after": 1},
    "medium":   {"min_crowd": 5000,  "radius_km": 2.0, "hours_before": 1, "hours_after": 1},
}

# Titik rawan kemacetan di Jakarta (dari data.jakarta.go.id) — seed statis
# Update dari: https://data.jakarta.go.id/dataset/titik-rawan-kemacetan-di-dki-jakarta
CONGESTION_HOTSPOTS = [
    {"name": "Bundaran HI", "lat": -6.1944, "lng": 106.8229},
    {"name": "Semanggi", "lat": -6.2088, "lng": 106.8228},
    {"name": "Blok M", "lat": -6.2441, "lng": 106.7993},
    {"name": "Tanah Abang", "lat": -6.1867, "lng": 106.8226},
    {"name": "Grogol", "lat": -6.1676, "lng": 106.7965},
    {"name": "Cawang", "lat": -6.2432, "lng": 106.8678},
    {"name": "Pancoran", "lat": -6.2418, "lng": 106.8339},
    {"name": "Kuningan", "lat": -6.2289, "lng": 106.8284},
    {"name": "Mampang", "lat": -6.2540, "lng": 106.8204},
    {"name": "TB Simatupang", "lat": -6.2993, "lng": 106.7964},
    {"name": "Tanjung Priok", "lat": -6.1082, "lng": 106.8795},
    {"name": "Kemayoran", "lat": -6.1574, "lng": 106.8454},
]

def _get_impact_level(crowd: int) -> str:
    if crowd >= IMPACT_CONFIG["critical"]["min_crowd"]:
        return "critical"
    if crowd >= IMPACT_CONFIG["high"]["min_crowd"]:
        return "high"
    if crowd >= IMPACT_CONFIG["medium"]["min_crowd"]:
        return "medium"
    return "low"

def predict_event_congestion(event: dict) -> dict:
    """
    Hitung prediksi kemacetan untuk sebuah event.
    Return: prediction payload siap publish ke Redis.
    """
    crowd = event.get("estimated_crowd", 0)
    profile = classify_crowd(crowd, event.get("category") or "general")
    level = {
        "red": "critical",
        "orange": "high",
        "yellow": "medium",
        "green": "low",
    }.get(profile["crowd_zone"], _get_impact_level(crowd))

    if level == "low":
        return None

    cfg = IMPACT_CONFIG[level]
    cfg = {
        **cfg,
        "radius_km": event.get("impact_radius_km") or profile["impact_radius_km"],
    }
    event_lat = event["lat"]
    event_lng = event["lng"]

    # Filter hotspot yang berada dalam radius dampak
    affected_segments = []
    for hotspot in CONGESTION_HOTSPOTS:
        dist = _haversine_km(event_lat, event_lng, hotspot["lat"], hotspot["lng"])
        if dist <= cfg["radius_km"]:
            congestion_level = "critical" if dist <= cfg["radius_km"] * 0.4 else \
                               "high" if dist <= cfg["radius_km"] * 0.7 else "medium"
            color = {"critical": "#FF0000", "high": "#FF4500", "medium": "#FFA500"}[congestion_level]

            affected_segments.append({
                "name": hotspot["name"],
                "lat": hotspot["lat"],
                "lng": hotspot["lng"],
                "congestion_level": congestion_level,
                "color": color,
                "distance_km": round(dist, 2),
            })

    # Buat rekomendasi mitigasi
    mitigation_actions = [
        {
            "action": (
                f"Turunkan {profile['officer_min']}-{profile['officer_max']} petugas "
                f"untuk crowd zone {profile['crowd_zone'].upper()}"
            ),
            "priority": 1,
        },
        {"action": f"Siagakan petugas di radius {cfg['radius_km']} km dari {event.get('venue', 'venue')}", "priority": 2},
        {"action": f"Aktifkan rekayasa lalu lintas H-{cfg['hours_before']} jam sebelum acara", "priority": 2},
        {"action": "Tambah armada TransJakarta koridor terdekat", "priority": 3},
    ]
    for seg in affected_segments[:3]:
        mitigation_actions.append({
            "action": f"Pantau titik {seg['name']} — estimasi dampak {seg['congestion_level']}",
            "priority": 4,
            "location": {"lat": seg["lat"], "lng": seg["lng"]},
        })

    # Waktu dampak
    impact_start = _event_datetime(event) or datetime.now(timezone.utc)
    impact_start = impact_start - timedelta(hours=cfg["hours_before"])
    impact_end = impact_start + timedelta(hours=cfg["hours_before"] + cfg["hours_after"])

    return {
        "type": "event_prediction",
        "payload": {
            "event_id": event.get("id", "unknown"),
            "event_name": event.get("name", ""),
            "impact_level": level,
            "crowd_zone": profile["crowd_zone"],
            "estimated_crowd": crowd,
            "officer_min": profile["officer_min"],
            "officer_max": profile["officer_max"],
            "impact_radius_km": cfg["radius_km"],
            "impact_start": impact_start.isoformat(),
            "impact_end": impact_end.isoformat(),
            "affected_segments": affected_segments,
            "mitigation_actions": mitigation_actions,
            "confidence": 0.75 if level == "critical" else 0.6,
        }
    }


def _event_datetime(event: dict) -> datetime | None:
    event_date = event.get("date") or event.get("event_date")
    event_time = event.get("time") or event.get("event_time") or "19:00"
    if not event_date:
        return None
    try:
        value = datetime.fromisoformat(f"{event_date}T{str(event_time)[:5]}:00")
    except ValueError:
        return None
    return value.replace(tzinfo=timezone.utc)
