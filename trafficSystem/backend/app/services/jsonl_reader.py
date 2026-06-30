import json
import os
from typing import Any, Optional
from app.services.redis_client import redis_get_json


HAYDEN_OUTPUTS_DIR = os.getenv(
    "HAYDEN_OUTPUTS_DIR",
    os.path.join(
        os.path.dirname(__file__),
        "..",
        "..",
        "outputs",
        "events",
    ),
)


def read_latest_jsonl(filename: str, default: Any = None) -> Any:
    filepath = os.path.join(HAYDEN_OUTPUTS_DIR, filename)
    if not os.path.exists(filepath):
        return default
    try:
        with open(filepath) as f:
            lines = f.readlines()
        if not lines:
            return default
        last_line = lines[-1].strip()
        if not last_line:
            return default
        return json.loads(last_line)
    except Exception:
        return default


def read_all_jsonl(filename: str) -> list[dict]:
    """Read all lines from a JSONL file and return as a list of dicts."""
    filepath = os.path.join(HAYDEN_OUTPUTS_DIR, filename)
    if not os.path.exists(filepath):
        return []
    try:
        results = []
        with open(filepath) as f:
            for line in f:
                stripped = line.strip()
                if stripped:
                    results.append(json.loads(stripped))
        return results
    except Exception:
        return []


def read_traffic_counts() -> dict:
    return redis_get_json("traffic:counts", default={})


def read_traffic_metrics() -> dict:
    return redis_get_json("traffic:metrics", default={})


def read_parking_status() -> dict:
    return redis_get_json("traffic:parking", default={})


def read_sign_detections() -> list:
    return read_latest_jsonl("sign_detections.jsonl", default=[])
