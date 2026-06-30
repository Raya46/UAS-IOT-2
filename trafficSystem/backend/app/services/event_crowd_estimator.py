import json
import os
import re
from html import unescape
from typing import Any

import httpx


GEMINI_ENDPOINT = (
    "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
)

VENUE_CAPACITY = {
    "gelora bung karno": 78000,
    "gbk": 78000,
    "jakarta international stadium": 82000,
    "jis": 82000,
    "jakarta international expo": 100000,
    "jiexpo": 100000,
    "monas": 50000,
    "national monument": 50000,
    "taman mini": 30000,
    "tmii": 30000,
    "ancol": 25000,
    "jakarta convention center": 12000,
    "jcc": 12000,
    "epiwalk": 5000,
    "mall": 4000,
}

KPOP_KEYWORDS = (
    "exo",
    "bts",
    "blackpink",
    "nct",
    "seventeen",
    "twice",
    "enhypen",
    "stray kids",
    "ateez",
    "aespa",
    "red velvet",
    "k-pop",
    "kpop",
    "korean",
)

CATEGORY_RULES = [
    ("concert_kpop", KPOP_KEYWORDS, 65000, (50000, 90000), 0.86),
    (
        "concert",
        ("konser", "concert", "music", "festival musik", "band", "musician", "dj"),
        30000,
        (12000, 70000),
        0.72,
    ),
    (
        "marathon",
        ("marathon", "run", "race", "fun run", "half marathon"),
        24000,
        (8000, 45000),
        0.76,
    ),
    (
        "sports",
        ("final", "match", "tournament", "championship", "sports"),
        22000,
        (7000, 50000),
        0.66,
    ),
    (
        "culinary",
        ("kopi", "coffee", "kuliner", "food", "makanan", "cafe"),
        4500,
        (1500, 12000),
        0.55,
    ),
    (
        "fair",
        ("fair", "expo", "exhibition", "pameran", "bazaar", "market"),
        10000,
        (3000, 25000),
        0.58,
    ),
    (
        "community",
        ("workshop", "seminar", "talkshow", "class", "community"),
        1800,
        (500, 5000),
        0.5,
    ),
]


def strip_html(value: str | None) -> str:
    if not value:
        return ""
    text = re.sub(r"<[^>]+>", " ", value)
    text = unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def _event_text(event: dict[str, Any]) -> str:
    parts = [
        event.get("title") or event.get("name") or "",
        event.get("content") or event.get("description") or "",
        event.get("location_name") or event.get("venue") or "",
        event.get("category") or "",
    ]
    return strip_html(" ".join(str(part) for part in parts)).lower()


def detect_category(event: dict[str, Any]) -> tuple[str, int, tuple[int, int], float]:
    text = _event_text(event)
    for category, keywords, base, crowd_range, confidence in CATEGORY_RULES:
        if any(keyword in text for keyword in keywords):
            return category, base, crowd_range, confidence
    return "general", 2500, (800, 8000), 0.42


def estimate_venue_capacity(venue: str | None) -> int | None:
    if not venue:
        return None
    venue_text = venue.lower()
    for keyword, capacity in VENUE_CAPACITY.items():
        if keyword in venue_text:
            return capacity
    return None


def classify_crowd(crowd: int, category: str = "general") -> dict[str, Any]:
    if crowd >= 50000:
        return {
            "crowd_zone": "red",
            "impact_level": "KRITIS",
            "impact_radius_km": 5.0,
            "officer_min": 100,
            "officer_max": 300,
            "color": "#e11d48",
        }
    if crowd >= 20000:
        return {
            "crowd_zone": "orange",
            "impact_level": "TINGGI",
            "impact_radius_km": 3.0,
            "officer_min": 60,
            "officer_max": 120,
            "color": "#f97316",
        }
    if crowd >= 5000 or category in {"culinary", "fair"}:
        return {
            "crowd_zone": "yellow",
            "impact_level": "SEDANG",
            "impact_radius_km": 2.0,
            "officer_min": 20,
            "officer_max": 60 if crowd >= 10000 else 40,
            "color": "#eab308",
        }
    return {
        "crowd_zone": "green",
        "impact_level": "RENDAH",
        "impact_radius_km": 1.0,
        "officer_min": 6,
        "officer_max": 20,
        "color": "#22c55e",
    }


def estimate_event_profile(event: dict[str, Any]) -> dict[str, Any]:
    category, base, crowd_range, confidence = detect_category(event)
    venue = event.get("location_name") or event.get("venue")
    venue_capacity = estimate_venue_capacity(venue)
    low, high = crowd_range

    if venue_capacity:
        if category in {"concert_kpop", "concert", "sports"}:
            base = min(max(base, int(venue_capacity * 0.65)), venue_capacity)
            high = max(high, venue_capacity)
        elif category in {"fair", "marathon"}:
            base = max(base, int(venue_capacity * 0.25))
            high = max(high, int(venue_capacity * 0.5))

    crowd = max(low, min(base, high))
    profile = classify_crowd(crowd, category)
    profile.update(
        {
            "category": category,
            "estimated_crowd": crowd,
            "crowd_range_min": low,
            "crowd_range_max": high,
            "confidence": confidence,
            "reason": _build_reason(category, venue_capacity, crowd),
            "estimation_source": "rules",
        }
    )
    return profile


def _build_reason(category: str, venue_capacity: int | None, crowd: int) -> str:
    category_label = category.replace("_", " ")
    if venue_capacity:
        return (
            f"Estimasi rule-based dari kategori {category_label}, kapasitas venue "
            f"sekitar {venue_capacity:,}, dan baseline crowd {crowd:,}."
        )
    return f"Estimasi rule-based dari kategori {category_label} dan kata kunci event."


def extract_event_time(event: dict[str, Any], category: str) -> str:
    text = strip_html(str(event.get("content") or event.get("description") or ""))
    match = re.search(
        r"\b([01]?\d|2[0-3])[:.]([0-5]\d)\s*(?:wib|pm|am)?\b", text, re.IGNORECASE
    )
    if match:
        return f"{int(match.group(1)):02d}:{match.group(2)}"
    if category in {"marathon", "sports"}:
        return "06:00" if category == "marathon" else "19:00"
    if category in {"fair", "culinary", "community"}:
        return "10:00"
    return "19:00"


async def estimate_event_profile_with_gemini(event: dict[str, Any]) -> dict[str, Any]:
    profile = estimate_event_profile(event)
    api_key = os.getenv("GEMINI_API_KEY")
    enabled = os.getenv("ENABLE_GEMINI_EVENT_ESTIMATION", "true").lower() in {
        "1",
        "true",
        "yes",
    }
    if not api_key or not enabled:
        return profile

    prompt = (
        "Estimate Jakarta event crowd impact for traffic operations. "
        "Return compact JSON only with keys: estimated_crowd integer, category string, "
        "confidence number 0-1, reason string. Use conservative ranges; K-pop or stadium "
        "concerts can be 50000-90000, coffee/culinary community events are usually 1500-12000.\n\n"
        f"Event title: {event.get('title') or event.get('name')}\n"
        f"Venue/location: {event.get('location_name') or event.get('venue')}\n"
        f"Date: {event.get('start_date') or event.get('date')} - {event.get('end_date') or ''}\n"
        f"Description: {strip_html(str(event.get('content') or event.get('description') or ''))[:1200]}"
    )
    model = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
    url = GEMINI_ENDPOINT.format(model=model)

    try:
        async with httpx.AsyncClient(timeout=12) as client:
            response = await client.post(
                url,
                params={"key": api_key},
                json={"contents": [{"parts": [{"text": prompt}]}]},
            )
            response.raise_for_status()
            data = response.json()
        text = data["candidates"][0]["content"]["parts"][0]["text"]
        gemini_profile = _parse_json_object(text)
        if not gemini_profile:
            return profile

        estimated = int(
            gemini_profile.get("estimated_crowd") or profile["estimated_crowd"]
        )
        estimated = max(300, min(estimated, 100000))
        category = str(gemini_profile.get("category") or profile["category"])
        adjusted = classify_crowd(estimated, category)
        adjusted.update(
            {
                **profile,
                **adjusted,
                "category": category,
                "estimated_crowd": estimated,
                "confidence": float(
                    gemini_profile.get("confidence") or profile["confidence"]
                ),
                "reason": str(gemini_profile.get("reason") or profile["reason"])[:500],
                "estimation_source": "gemini",
            }
        )
        return adjusted
    except Exception:
        return profile


def _parse_json_object(text: str) -> dict[str, Any] | None:
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?", "", cleaned).strip()
    cleaned = re.sub(r"```$", "", cleaned).strip()
    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if match:
        cleaned = match.group(0)
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None
