import os
import json
from datetime import datetime, timedelta
from typing import List, Dict, Any, Tuple, Optional

def calculate_matching_score(cand1: Dict[str, Any], cand2: Dict[str, Any]) -> float:
    """
    Computes a matching score (0.0 to 1.0) between two parking candidates.
    Matches are based on:
    - Same road segment: +0.25
    - Same zone: +0.20
    - Same plate number and not UNKNOWN: +0.35
    - Same vehicle type/category: +0.10
    - Similar color signature: +0.10
    - Different camera or later pass: +0.10
    """
    score = 0.0

    # 1. Road Segment
    if cand1.get("road_segment_id") == cand2.get("road_segment_id"):
        score += 0.25

    # 2. Zone ID
    if cand1.get("zone_id") == cand2.get("zone_id"):
        score += 0.20

    # 3. Plate Number
    p1 = str(cand1.get("plate_number", "UNKNOWN")).strip().upper()
    p2 = str(cand2.get("plate_number", "UNKNOWN")).strip().upper()
    if p1 != "UNKNOWN" and p2 != "UNKNOWN" and p1 != "" and p2 != "" and p1 == p2:
        score += 0.35

    # 4. Vehicle Type / Transport Category
    v1 = cand1.get("vehicle_type")
    v2 = cand2.get("vehicle_type")
    tc1 = cand1.get("transport_category")
    tc2 = cand2.get("transport_category")
    if v1 == v2 or (tc1 and tc2 and tc1 == tc2):
        score += 0.10

    # 5. Color Signature Similarity
    c1 = cand1.get("color_signature")
    c2 = cand2.get("color_signature")
    if c1 and c2:
        try:
            # Simple Euclidean distance
            dist = sum((float(a) - float(b))**2 for a, b in zip(c1, c2))**0.5
            if dist < 45.0:  # Threshold for color match
                score += 0.10
        except Exception:
            pass

    # 6. Different Camera or Later Pass
    cam1 = cand1.get("camera_id")
    cam2 = cand2.get("camera_id")
    if cam1 != cam2:
        score += 0.10
    else:
        # Check time gap for later pass (must be > 10 seconds to not match the same pass)
        t1 = cand1.get("timestamp")
        t2 = cand2.get("timestamp")
        if t1 and t2:
            try:
                dt1 = datetime.fromisoformat(t1.replace("Z", ""))
                dt2 = datetime.fromisoformat(t2.replace("Z", ""))
                if abs((dt1 - dt2).total_seconds()) > 10.0:
                    score += 0.10
            except Exception:
                pass

    return round(score, 3)

def load_recent_candidates(filepath: str, window_minutes: int = 30) -> List[Dict[str, Any]]:
    """Loads candidates from jsonl file within the last window_minutes."""
    if not os.path.exists(filepath):
        return []

    recent_candidates = []
    cutoff_time = datetime.now() - timedelta(minutes=window_minutes)

    try:
        with open(filepath, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    cand = json.loads(line)
                    t_str = cand.get("timestamp")
                    if t_str:
                        dt = datetime.fromisoformat(t_str.replace("Z", ""))
                        if dt >= cutoff_time:
                            recent_candidates.append(cand)
                except Exception:
                    continue
    except Exception as exc:
        print(f"[WARN] Failed to load parking candidates: {exc}")

    return recent_candidates

def save_candidate(filepath: str, candidate: Dict[str, Any]) -> None:
    """Appends a new parking candidate to the JSONL candidate log."""
    try:
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, "a", encoding="utf-8") as f:
            f.write(json.dumps(candidate) + "\n")
    except Exception as exc:
        print(f"[WARN] Failed to save parking candidate: {exc}")

def find_confirmation_match(
    new_candidate: Dict[str, Any],
    filepath: str,
    window_minutes: int = 30,
    min_score: float = 0.65
) -> Tuple[bool, float, List[str]]:
    """
    Compares the new candidate against historical candidates in the log.
    Returns (is_confirmed, best_score, matched_candidate_ids).
    """
    candidates = load_recent_candidates(filepath, window_minutes=window_minutes)
    if not candidates:
        return False, 0.0, []

    best_score = 0.0
    matched_ids = []
    
    # Exclude candidates with the same track_id in the exact same camera session (same camera, very close timestamp)
    for cand in candidates:
        # Skip comparing with itself
        if cand.get("candidate_id") == new_candidate.get("candidate_id"):
            continue
            
        # If it's the exact same tracking session pass (same track_id and same camera, close time)
        if cand.get("camera_id") == new_candidate.get("camera_id") and cand.get("track_id") == new_candidate.get("track_id"):
            continue

        score = calculate_matching_score(new_candidate, cand)
        if score >= min_score:
            if score > best_score:
                best_score = score
            matched_ids.append(cand.get("candidate_id"))

    is_confirmed = len(matched_ids) > 0
    return is_confirmed, best_score, matched_ids
