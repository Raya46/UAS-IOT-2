import math
from typing import Dict, List, Optional
from ai.utils.config import Config
from ai.trackers.tracker_interface import Detection, Track, Point

class CentroidTracker:
    # Group classes by category for more robust matching
    _CATEGORY_MAP = {
        "car": "vehicle", "truck": "vehicle", "bus": "vehicle",
        "motorcycle": "vehicle", "angkot": "vehicle", "bus_transjakarta": "vehicle",
        "person": "person", "pedestrian": "person",
        "bicycle": "bicycle",
    }

    def __init__(self, config: Config):
        self.config = config
        self.next_id = 1
        self.tracks: Dict[int, Track] = {}
        self.max_distance = float(config.get("tracking.max_match_distance_pixels", 120))
        self.max_disappeared = float(config.get("tracking.max_disappeared_seconds", 1.5))
        self.movement_threshold = float(config.get("tracking.movement_threshold_pixels", 8))
        self.stopped_threshold = float(config.get("tracking.stopped_seconds_threshold", 5))

    @staticmethod
    def _get_category(class_name: str) -> str:
        return CentroidTracker._CATEGORY_MAP.get(class_name, class_name)

    @staticmethod
    def distance(a: Point, b: Point) -> float:
        return math.sqrt((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2)

    def update(self, detections: List[Detection], now: float, dt: float) -> List[Track]:
        for track in self.tracks.values():
            track.matched = False

        for detection in detections:
            best_track_id: Optional[int] = None
            best_distance = float("inf")
            det_cat = self._get_category(detection.class_name)

            for track_id, track in self.tracks.items():
                if track.matched:
                    continue
                # Match by category instead of exact class_name
                if self._get_category(track.class_name) != det_cat:
                    continue
                distance = self.distance(track.center, detection.center)
                if distance < best_distance and distance <= self.max_distance:
                    best_distance = distance
                    best_track_id = track_id

            if best_track_id is None:
                track = Track(
                    track_id=self.next_id,
                    class_name=detection.class_name,
                    confidence=detection.confidence,
                    bbox=detection.bbox,
                    center=detection.center,
                    last_center=detection.center,
                    first_seen_at=now,
                    last_seen_at=now,
                    matched=True,
                )
                self.tracks[self.next_id] = track
                self.next_id += 1
                continue

            track = self.tracks[best_track_id]
            movement = self.distance(track.center, detection.center)
            time_elapsed = max(now - track.last_seen_at, 0.0)

            track.last_center = track.center
            track.center = detection.center
            track.bbox = detection.bbox
            track.confidence = detection.confidence
            track.last_seen_at = now
            track.movement_pixels = movement
            track.matched = True

            # Track history trajectory
            track.history.append(detection.center)
            if len(track.history) > 50:  # Keep last 50 points
                track.history.pop(0)

            # Check for stationarity using stop_anchor
            if not hasattr(track, 'stop_anchor'):
                track.stop_anchor = None

            if track.stop_anchor is None:
                # If movement is small, set stop anchor
                if movement < self.movement_threshold:
                    track.stop_anchor = detection.center
                    track.stationary_seconds += time_elapsed
                else:
                    track.stationary_seconds = 0.0
            else:
                # We have a stop anchor. Check distance to anchor
                dist_to_anchor = self.distance(track.stop_anchor, detection.center)
                drift_threshold = float(self.config.get("tracking.stationary_drift_pixels", 25))
                
                if dist_to_anchor < drift_threshold:
                    track.stationary_seconds += time_elapsed
                    # Slowly drift stop anchor position towards centroid to accommodate actual slow shifts
                    track.stop_anchor = (
                        int(0.95 * track.stop_anchor[0] + 0.05 * detection.center[0]),
                        int(0.95 * track.stop_anchor[1] + 0.05 * detection.center[1])
                    )
                else:
                    # Moved too far, break stop anchor
                    track.stop_anchor = None
                    track.stationary_seconds = 0.0

            track.is_stopped = track.stationary_seconds >= self.stopped_threshold

        stale_ids = [
            track_id
            for track_id, track in self.tracks.items()
            if now - track.last_seen_at > self.max_disappeared
        ]
        for track_id in stale_ids:
            del self.tracks[track_id]

        return list(self.tracks.values())
