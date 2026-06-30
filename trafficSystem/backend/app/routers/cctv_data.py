import json
import re
from pathlib import Path
from typing import List, Optional
from fastapi import APIRouter, Query
from app.services.jsonl_reader import (
    read_traffic_counts,
    read_traffic_metrics,
    read_parking_status,
    read_sign_detections,
)

router = APIRouter(prefix="/api", tags=["cctv_data"])

CCTV_CAMERAS_PATH = Path(__file__).parent.parent.parent / "data" / "cctv_cameras.json"

_cctv_cameras_cache: Optional[List[dict]] = None


def _load_cctv_cameras() -> List[dict]:
    global _cctv_cameras_cache
    if _cctv_cameras_cache is not None:
        return _cctv_cameras_cache
    if not CCTV_CAMERAS_PATH.exists():
        _cctv_cameras_cache = []
        return _cctv_cameras_cache
    try:
        with open(CCTV_CAMERAS_PATH) as f:
            _cctv_cameras_cache = json.load(f)
    except Exception as exc:
        print(f"[WARN] Failed to load CCTV cameras: {exc}")
        _cctv_cameras_cache = []
    return _cctv_cameras_cache


def _resolve_stream_url(raw_url: str, embed_url: str, parsed) -> Optional[str]:
    if raw_url.startswith("http://") or raw_url.startswith("https://"):
        return raw_url
    if raw_url.startswith("//"):
        return f"{parsed.scheme}:{raw_url}"
    if raw_url.startswith("/"):
        return f"{parsed.scheme}://{parsed.netloc}{raw_url}"
    base_path = "/".join(embed_url.split("/")[:-1])
    return f"{base_path}/{raw_url}"


def _try_balitower_hls_patterns(url: str) -> Optional[str]:
    if "/embed.html" not in url:
        return None
    import urllib.request

    base = url.replace("/embed.html", "").replace("/embed", "")
    for proto in ["https://", "http://"]:
        for suffix in [
            "/hls/playlist.m3u8",
            "/live/playlist.m3u8",
            "/stream.m3u8",
            "/playlist.m3u8",
            ".m3u8",
        ]:
            candidate = base + suffix
            try:
                req = urllib.request.Request(
                    candidate, method="HEAD", headers={"User-Agent": "Mozilla/5.0"}
                )
                resp = urllib.request.urlopen(req, timeout=5)
                if resp.status == 200:
                    ct = resp.headers.get("Content-Type", "")
                    if "mpegurl" in ct or "m3u8" in ct:
                        return candidate
            except Exception:
                continue
    return None


@router.get("/traffic-counts")
async def get_traffic_counts():
    data = read_traffic_counts()
    if data:
        return data
    return {
        "line_001": {
            "forward": {"total": 0, "classes": {}},
            "backward": {"total": 0, "classes": {}},
        }
    }


@router.get("/traffic-metrics")
async def get_traffic_metrics():
    data = read_traffic_metrics()
    if data:
        return data
    return {
        "vehicle_count": 0,
        "stopped_vehicle_count": 0,
        "queue_length_estimate": 0,
        "density_level": "LOW",
        "average_speed": 0.0,
        "dominant_direction": "STATIONARY",
    }


@router.get("/parking-status")
async def get_parking_status():
    data = read_parking_status()
    if data:
        return data
    return {
        "total_spots": 1,
        "occupied_spots": 0,
        "free_spots": 1,
        "occupancy_percentage": 0.0,
        "spots": {},
    }


@router.get("/sign-detections")
async def get_sign_detections():
    data = read_sign_detections()
    return data if data else []


@router.get("/cctv/cameras")
async def list_cctv_cameras():
    cameras = _load_cctv_cameras()
    return {"cameras": [c for c in cameras if c.get("enabled", True)]}


@router.get("/cctv/resolve-stream")
async def resolve_cctv_stream(url: str = Query(..., description="CCTV embed URL")):
    """
    Fetch the balitower CCTV embed page and extract the actual HLS stream URL.
    Falls back to the original URL if resolution fails.
    """
    import urllib.request
    from urllib.parse import urlparse

    parsed = urlparse(url)

    found = _try_balitower_hls_patterns(url)
    if found:
        return {"resolved_url": found, "original_url": url}

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        resp = urllib.request.urlopen(req, timeout=10)
        html = resp.read().decode("utf-8", errors="replace")

        m3u8_candidates = set()

        for match in re.finditer(
            r'["\']([^"\']*\.m3u8[^"\']*)["\']', html, re.IGNORECASE
        ):
            raw = match.group(1)
            resolved = _resolve_stream_url(raw, url, parsed)
            if resolved:
                m3u8_candidates.add(resolved)

        for match in re.finditer(
            r'https?://[^"\'\s<>]+\.m3u8[^"\'\s<>]*', html, re.IGNORECASE
        ):
            m3u8_candidates.add(match.group(0).rstrip(".,;\"'"))

        for candidate in m3u8_candidates:
            try:
                head = urllib.request.Request(
                    candidate, method="HEAD", headers={"User-Agent": "Mozilla/5.0"}
                )
                head_resp = urllib.request.urlopen(head, timeout=5)
                if head_resp.status == 200:
                    return {"resolved_url": candidate, "original_url": url}
            except Exception:
                continue
    except Exception as exc:
        print(f"[CCTV] Failed to fetch embed page {url}: {exc}")

    return {"resolved_url": url, "original_url": url}

