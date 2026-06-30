import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import cv2
import numpy as np

BACKEND_DIR = str(Path(__file__).parent.parent)
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from ai.utils.config import Config
from ai.utils.drawing import draw_track, draw_panel
from ai.detectors.vehicle_detector import VehicleDetector
from ai.detectors.plate_detector import PlateDetector
from ai.trackers.centroid_tracker import CentroidTracker
from ai.detectors.sign_detector import SignDetector
from ai.services.anpr_service import ANPRService
from ai.services.evidence_service import EvidenceService
from ai.rules.illegal_parking import (
    check_cctv_parking_violation,
    check_moving_parking_violation,
    check_stop_area_context,
)
from ai.rules.parking_confirmation import find_confirmation_match, save_candidate
from ai.services.cctv_analytics import CCTVAnalytics
from ai.rules.shoulder_lane import check_shoulder_lane
from ai.rules.red_light import check_red_light
from ai.rules.illegal_u_turn import check_illegal_u_turn
from ai.rules.unsafe_lane_change import check_unsafe_lane_change
from ai.rules.traffic_sign import check_traffic_sign_violation
from ai.utils.geometry import point_inside_polygon
from ai.services.zone_manager import ZoneManager
from ai.live_dashcam.dashcam_detector import DashcamDetector
from ai.live_dashcam.scene_analyzer import TrafficStats
from app.services.adaptive_vision import AdaptiveImageEnhancer, ContextualBehaviorReasoner

_shared_detector: Optional[VehicleDetector] = None
_shared_plate_detector: Optional[PlateDetector] = None
_shared_sign_detector: Optional[SignDetector] = None
_shared_anpr: Optional[ANPRService] = None
_shared_config: Optional[Config] = None
_shared_dashcam_detector: Optional[DashcamDetector] = None


def _get_config() -> Config:
    global _shared_config
    if _shared_config is None:
        base = Path(__file__).parent.parent
        for candidate in [
            base / "ai" / "config.yaml",
            base / "config.yaml",
            Path("ai/config.yaml"),
            Path("config.yaml"),
        ]:
            if candidate.exists():
                _shared_config = Config(str(candidate))
                _shared_config.ensure_dirs()
                break
        if _shared_config is None:
            raise FileNotFoundError("Cannot find config.yaml")
    return _shared_config


def _get_detector() -> VehicleDetector:
    global _shared_detector
    if _shared_detector is None:
        _shared_detector = VehicleDetector(_get_config())
    return _shared_detector


def _get_plate_detector() -> PlateDetector:
    global _shared_plate_detector
    if _shared_plate_detector is None:
        _shared_plate_detector = PlateDetector(_get_config())
    return _shared_plate_detector


def _get_anpr() -> ANPRService:
    global _shared_anpr
    if _shared_anpr is None:
        _shared_anpr = ANPRService(_get_config())
    return _shared_anpr


def _get_sign_detector() -> SignDetector:
    global _shared_sign_detector
    if _shared_sign_detector is None:
        _shared_sign_detector = SignDetector(_get_config())
    return _shared_sign_detector


_shared_zone_manager = None


def _get_zone_manager():
    global _shared_zone_manager
    if _shared_zone_manager is None:
        _shared_zone_manager = ZoneManager(_get_config())
    return _shared_zone_manager


def _get_dashcam_detector() -> DashcamDetector:
    global _shared_dashcam_detector
    if _shared_dashcam_detector is None:
        _shared_dashcam_detector = DashcamDetector(_get_config())
    return _shared_dashcam_detector


def is_rule_enabled(profile: dict, violation_type: str) -> bool:
    enabled = profile.get("enabled_violations", [])
    if not enabled:
        return True
    return violation_type in set(enabled)


def class_allowed_for_rule(profile: dict, violation_type: str, class_name: str) -> bool:
    classes_by_rule = profile.get("target_classes", {}) or {}
    allowed = classes_by_rule.get(violation_type)
    if not allowed:
        return class_name != "person"
    return class_name in set(allowed)


def profile_zones(profile: dict, zone_type: str) -> list:
    zones = profile.get("zones", {}) or {}
    return zones.get(zone_type, [])


def profile_rule_config(profile: dict, violation_type: str) -> dict:
    rules = profile.get("rule_config", {}) or {}
    return rules.get(violation_type, {}) or {}


def track_inside_any_zone(track, zones: list) -> bool:
    return any(point_inside_polygon(track.center, points) for points in zones if points)


def _calculate_traffic(tracks: list, config: Config) -> dict:
    vehicle_count = len(tracks)
    stopped_count = sum(1 for t in tracks if t.is_stopped)
    stopped_ratio = stopped_count / vehicle_count if vehicle_count else 0.0
    medium = int(config.get("traffic.medium_vehicle_count", 5))
    high = int(config.get("traffic.high_vehicle_count", 12))
    severe = int(config.get("traffic.severe_vehicle_count", 20))
    high_r = float(config.get("traffic.high_stopped_ratio", 0.3))
    severe_r = float(config.get("traffic.severe_stopped_ratio", 0.5))
    if vehicle_count >= severe and stopped_ratio >= severe_r:
        level = "SEVERE"
    elif vehicle_count >= high and stopped_ratio >= high_r:
        level = "HIGH"
    elif vehicle_count >= medium:
        level = "MEDIUM"
    else:
        level = "LOW"
    return {
        "vehicle_count": vehicle_count,
        "stopped_count": stopped_count,
        "stopped_ratio": round(stopped_ratio, 3),
        "level": level,
    }


def _make_event_id(counter: int) -> str:
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    return f"LIVE-{ts}-{counter:04d}"


class LiveCamSession:
    def __init__(self, session_id: str):
        self.session_id = session_id
        self.config = _get_config()
        self.tracker = CentroidTracker(self.config)
        self.evidence = EvidenceService(self.config)
        self.frame_count = 0
        self.start_time = time.time()
        self.last_time = time.time()
        self.fps = 0.0
        self.event_counter = 1
        self.saved_event_counts: Dict[str, int] = {}
        self.cooldown_seconds = float(
            self.config.get("violation.evidence_cooldown_seconds", 20)
        )
        self.save_once_per_track = bool(
            self.config.get("violation.save_once_per_track", True)
        )
        self.jpeg_quality = 80
        self.resize_width = 960
        self.source_label = "livecam"
        self.cctv_analytics = CCTVAnalytics(self.config)
        self.dashcam_detector = None
        self.dashcam_stats = TrafficStats()
        self._processing = False
        self._detection_counter = 0
        self._detection_interval = int(self.config.get("detection.interval_frames", 5))
        self.image_enhancer = AdaptiveImageEnhancer()
        self.behavior_reasoner = ContextualBehaviorReasoner()
        self.last_enhancement_metrics: Dict[str, Any] = {}
        print(
            f"[LIVECAM] Session {session_id} started (detection every {self._detection_interval} frames)."
        )

    def update_settings(self, settings: dict) -> None:
        if "jpeg_quality" in settings:
            val = int(settings["jpeg_quality"])
            self.jpeg_quality = max(50, min(100, val))
        if "resize_width" in settings:
            val = int(settings["resize_width"])
            self.resize_width = max(480, min(1920, val))
        if "source_label" in settings:
            label = str(settings["source_label"])
            upload_prefix = "UPLOAD-"
            if upload_prefix in label:
                after_prefix = label.split(upload_prefix, 1)[1]
                parts = after_prefix.split("_", 1)
                if len(parts) > 1:
                    label = parts[1]
            self.source_label = label

    def process_frame(self, jpeg_bytes: bytes) -> Dict[str, Any]:
        if self._processing:
            return {"dropped": True}
        self._processing = True
        try:
            arr = np.frombuffer(jpeg_bytes, dtype=np.uint8)
            frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
            if frame is None:
                return {"error": "Failed to decode frame"}
            return self._process_frame_internal(frame)
        finally:
            self._processing = False

    def process_raw_frame(self, frame: np.ndarray) -> Dict[str, Any]:
        if self._processing:
            return {"dropped": True}
        self._processing = True
        try:
            if frame is None or frame.size == 0:
                return {"error": "Empty frame"}
            if not frame.flags.writeable:
                frame = frame.copy()
            return self._process_frame_internal(frame)
        finally:
            self._processing = False

    def stop(self):
        print(
            f"[LIVECAM] Session {self.session_id} stopped after {self.frame_count} frames."
        )

    def _process_frame_internal(self, frame: np.ndarray) -> Dict[str, Any]:
        frame = self._resize(frame)
        frame, enhancement_metrics = self.image_enhancer.enhance(frame)
        self.last_enhancement_metrics = enhancement_metrics
        raw_frame = frame.copy()
        now_real = time.time()
        dt = now_real - self.last_time
        self.last_time = now_real
        self.fps = 1.0 / dt if dt > 0 else 0.0
        self.frame_count += 1
        self._detection_counter += 1
        run_full_detection = (
            self._detection_counter >= self._detection_interval or self.frame_count <= 3
        )
        now = now_real

        by_filename = self.config.get("source_profiles.by_filename", {}) or {}
        source_profile = by_filename.get(
            self.source_label, self.config.get("source_profiles.default", {})
        )
        source_type = source_profile.get(
            "source_type", self.config.get("source.type", "public_transport_camera")
        )

        detector = _get_detector()
        if run_full_detection:
            self._detection_counter = 0
            detections = detector.detect(frame, source_type=source_type)
            if detections and self.frame_count % 30 == 0:
                print(f"[LIVECAM DEBUG] frame={self.frame_count} source={source_type} detections={[(d.class_name, round(d.confidence,2)) for d in detections]} conf_thresh={detector.confidence}")
            if source_type == "cctv":
                allowed_vehicles = {
                    "car", "motorcycle", "bus", "truck", "person", "bicycle",
                    "jaklingko", "angkot_merah", "angkot_hijau", "angkot_biru",
                    "angkot", "bus_transjakarta",
                    "transjakarta", "metrotrans"
                }
                detections = [d for d in detections if d.class_name in allowed_vehicles]
            tracks = self.tracker.update(detections, now, dt)
            self._cached_tracks = tracks
        else:
            tracks = self.tracker.update([], now, dt)

        if source_type != "cctv":
            if self.dashcam_detector is None:
                self.dashcam_detector = _get_dashcam_detector()
            dashcam_analysis = self.dashcam_detector.detect(frame)
            self.dashcam_stats.update(
                {
                    "vehicle_count": dashcam_analysis.vehicle_count if dashcam_analysis else 0,
                    "pedestrian_count": dashcam_analysis.pedestrian_count if dashcam_analysis else 0,
                }
            )
        else:
            dashcam_analysis = None
        wrong_direction_violations = []
        if source_type == "cctv":
            self.cctv_analytics.process_traffic_counting(tracks)
            density_metrics = self.cctv_analytics.estimate_density(tracks, dt=dt)
            self.cctv_analytics.update_parking_spots(tracks)
            # self.cctv_analytics.draw_analytics(frame)
            wrong_direction_violations = self.cctv_analytics.detect_wrong_direction(
                tracks, {"zone_lane_a_001": "downward", "zone_lane_b_001": "upward"}
            )

        pending_events = []
        violation_track_ids: dict = {}

        run_sign_det = False
        if source_type != "cctv":
            if self.frame_count % 5 == 0 or not hasattr(self, "cached_sign_detections"):
                run_sign_det = True

        if run_sign_det:
            sign_detector = _get_sign_detector()
            self.cached_sign_detections = sign_detector.detect_signs(frame)
            sign_detections = self.cached_sign_detections
        else:
            sign_detections = getattr(self, "cached_sign_detections", []) if source_type != "cctv" else []

        zone_manager = _get_zone_manager()
        enabled_violations = source_profile.get("enabled_violations", [])

        if source_type != "cctv":
            try:
                zone_manager.adapt_zones_to_lanes(
                    frame,
                    source_type=source_type,
                    source_label=self.source_label,
                    tracks=tracks,
                )
            except Exception as exc:
                print(f"[WARN] adapt_zones_to_lanes failed: {exc}")

        if source_type != "cctv":
            zone_manager.draw_zones(
                frame,
                enabled_violations=enabled_violations,
                source_type=source_type,
                source_label=self.source_label,
            )

        no_parking_zones = (
            zone_manager.get_zones_by_type("no_parking")
            if "illegal_parking" in enabled_violations
            or "restricted_area_stop" in enabled_violations
            else []
        )
        shoulder_zones = (
            zone_manager.get_zones_by_type("shoulder_lane")
            if "shoulder_lane_violation" in enabled_violations
            else []
        )
        stop_line_zones = (
            zone_manager.get_zones_by_type("red_light_stop_line")
            if "red_light_violation" in enabled_violations
            else []
        )
        u_turn_zones = (
            zone_manager.get_zones_by_type("u_turn_forbidden")
            if "illegal_u_turn" in enabled_violations
            else []
        )
        lane_a_zones = (
            zone_manager.get_zones_by_type("lane_a")
            if "unsafe_lane_change" in enabled_violations
            else []
        )
        lane_b_zones = (
            zone_manager.get_zones_by_type("lane_b")
            if "unsafe_lane_change" in enabled_violations
            else []
        )

        profile_no_parking_zones = profile_zones(source_profile, "no_parking")
        profile_traffic_sign_zones = profile_zones(source_profile, "traffic_sign")
        profile_u_turn_zones = profile_zones(source_profile, "u_turn_forbidden")
        profile_lane_a_zones = profile_zones(source_profile, "lane_a")
        profile_lane_b_zones = profile_zones(source_profile, "lane_b")
        profile_busway_zones = profile_zones(source_profile, "busway")
        jaklingko_stop_zones = zone_manager.get_zones_by_type("jaklingko_stop_area")

        # Draw busway zone overlay for CCTV
        if source_type == "cctv" and profile_busway_zones:
            for bz_pts in profile_busway_zones:
                if bz_pts and len(bz_pts) >= 3:
                    pts_np = np.array(bz_pts, dtype=np.int32)
                    cv2.polylines(frame, [pts_np], True, (0, 0, 255), 2)
                    mid_x = sum(p[0] for p in bz_pts) // len(bz_pts)
                    min_y = min(p[1] for p in bz_pts)
                    cv2.putText(frame, "BUSWAY TJ", (mid_x - 40, min_y - 8),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 2)

        candidate_jsonl_path = self.config.get(
            "outputs.candidate_jsonl_path", "outputs/events/parking_candidates.jsonl"
        )
        window_minutes = int(
            self.config.get("parking_confirmation.confirmation_window_minutes", 30)
        )
        min_matching_score = float(
            self.config.get("parking_confirmation.min_matching_score", 0.65)
        )

        for track in tracks:
            if track.class_name == "person":
                allowed_for_any_rule = False
                for vt in source_profile.get("enabled_violations", []):
                    if class_allowed_for_rule(source_profile, vt, "person"):
                        allowed_for_any_rule = True
                        break
                if not allowed_for_any_rule:
                    continue

            if source_type != "cctv" and track.class_name in [
                "car",
                "bus",
                "truck",
                "motorcycle",
                "jaklingko",
                "angkot_merah",
                "angkot_hijau",
                "angkot_biru",
                "transjakarta",
                "metrotrans",
            ]:
                already_has_confident_read = any(
                    p["conf"] >= 0.85 for p in track.plate_history
                )
                if not already_has_confident_read and len(track.plate_history) < 5:
                    frame_mod = int(getattr(track, "alpr_frame_counter", 0))
                    track.alpr_frame_counter = frame_mod + 1
                    if frame_mod % 3 == 0:
                        plate_detector_inst = _get_plate_detector()
                        plate_crop, plate_conf, plate_bbox = (
                            plate_detector_inst.detect_plate(raw_frame, track.bbox)
                        )
                        if plate_crop is not None and plate_crop.size > 0:
                            anpr_inst = _get_anpr()
                            plate_number, ocr_conf, ocr_raw = anpr_inst.read_plate(
                                plate_crop,
                                track_id=track.track_id,
                                vehicle_type=track.class_name,
                                source_name=self.source_label,
                            )
                            if plate_number and plate_number != "UNKNOWN":
                                track.plate_history.append(
                                    {
                                        "text": plate_number,
                                        "conf": max(plate_conf, ocr_conf),
                                        "crop": plate_crop,
                                    }
                                )

            if source_type != "cctv":
                track.inside_no_parking_zone = any(
                    point_inside_polygon(track.center, z["points"])
                    for z in no_parking_zones
                ) or track_inside_any_zone(track, profile_no_parking_zones)
                inside_shoulder = any(
                    point_inside_polygon(track.center, z["points"]) for z in shoulder_zones
                )
                inside_stop_line = any(
                    point_inside_polygon(track.center, z["points"]) for z in stop_line_zones
                )
                inside_u_turn = any(
                    point_inside_polygon(track.center, z["points"]) for z in u_turn_zones
                ) or track_inside_any_zone(track, profile_u_turn_zones)
                inside_lane_a = any(
                    point_inside_polygon(track.center, z["points"]) for z in lane_a_zones
                ) or track_inside_any_zone(track, profile_lane_a_zones)
                inside_lane_b = any(
                    point_inside_polygon(track.center, z["points"]) for z in lane_b_zones
                ) or track_inside_any_zone(track, profile_lane_b_zones)
                inside_traffic_sign = track_inside_any_zone(
                    track, profile_traffic_sign_zones
                )
                is_in_stop_area = check_stop_area_context(track, jaklingko_stop_zones)
            else:
                track.inside_no_parking_zone = False
                inside_shoulder = False
                inside_stop_line = False
                inside_u_turn = False
                inside_lane_a = False
                inside_lane_b = False
                inside_traffic_sign = False
                is_in_stop_area = False

            # Busway lane violation check (works for CCTV)
            is_busway_violation = False
            _tj_classes = {"bus_transjakarta", "transjakarta", "bus"}
            if (
                is_rule_enabled(source_profile, "busway_lane_violation")
                and class_allowed_for_rule(source_profile, "busway_lane_violation", track.class_name)
                and track.class_name not in _tj_classes
            ):
                for bz_pts in profile_busway_zones:
                    if bz_pts and point_inside_polygon(track.center, bz_pts):
                        is_busway_violation = True
                        break

            is_parking_violation = False
            parking_violation_status = None
            linked_candidates = []
            best_match_score = 0.0

            if (
                not is_in_stop_area
                and is_rule_enabled(source_profile, "illegal_parking")
                and class_allowed_for_rule(
                    source_profile, "illegal_parking", track.class_name
                )
            ):
                parking_rule_config = profile_rule_config(
                    source_profile, "illegal_parking"
                )
                all_parking_zones = no_parking_zones + [
                    {
                        "points": points,
                        "id": "zone_profile_parking",
                        "rule_config": parking_rule_config,
                    }
                    for points in profile_no_parking_zones
                ]
                for z in all_parking_zones:
                    if not point_inside_polygon(track.center, z["points"]):
                        continue
                    if source_type == "cctv":
                        limit = float(
                            z.get("rule_config", {}).get("min_seconds", 5.0)
                            if z.get("rule_config")
                            else 5.0
                        )
                        is_traffic_jam = (
                            density_metrics.get("density_level")
                            in ["TRAFFIC JAM", "HEAVY TRAFFIC"]
                            if "density_metrics" in locals()
                            else False
                        )
                        if check_cctv_parking_violation(
                            track, limit, is_traffic_jam=is_traffic_jam
                        ):
                            is_parking_violation = True
                            parking_violation_status = "confirmed_illegal_parking"
                            break
                    else:
                        limit = float(
                            z.get("rule_config", {}).get(
                                "moving_camera_potential_seconds", 1.0
                            )
                            if z.get("rule_config")
                            else 1.0
                        )
                        if check_moving_parking_violation(track, limit):
                            current_plate = "UNKNOWN"
                            current_plate_conf = 0.0
                            if track.plate_history:
                                best_p = max(
                                    track.plate_history, key=lambda x: x["conf"]
                                )
                                current_plate, current_plate_conf = (
                                    best_p["text"],
                                    best_p["conf"],
                                )
                            px1, py1, px2, py2 = track.bbox
                            crop = raw_frame[
                                max(0, py1) : min(raw_frame.shape[0], py2),
                                max(0, px1) : min(raw_frame.shape[1], px2),
                            ]
                            color_sig = (
                                [
                                    float(np.mean(crop, axis=(0, 1))[2]),
                                    float(np.mean(crop, axis=(0, 1))[1]),
                                    float(np.mean(crop, axis=(0, 1))[0]),
                                ]
                                if crop.size > 0
                                else [0.0, 0.0, 0.0]
                            )
                            cand_id = f"CAND-{track.track_id}-{int(now)}"
                            new_candidate = {
                                "candidate_id": cand_id,
                                "timestamp": datetime.now().isoformat(),
                                "camera_id": self.config.get(
                                    "source.camera_id", "livecam_001"
                                ),
                                "route_id": self.config.get(
                                    "source.route_id", "route_001"
                                ),
                                "road_segment_id": self.config.get(
                                    "source.road_segment_id", "segment_001"
                                ),
                                "zone_id": z.get("id", "no_parking_001"),
                                "track_id": track.track_id,
                                "vehicle_type": track.class_name,
                                "transport_category": track.class_name,
                                "plate_number": current_plate,
                                "color_signature": color_sig,
                                "bbox": [int(x) for x in track.bbox],
                                "latitude": 0.0,
                                "longitude": 0.0,
                            }
                            is_confirmed, best_score, matched_ids = (
                                find_confirmation_match(
                                    new_candidate,
                                    candidate_jsonl_path,
                                    window_minutes,
                                    min_matching_score,
                                )
                            )
                            if not getattr(track, "logged_candidate", False):
                                save_candidate(candidate_jsonl_path, new_candidate)
                                track.logged_candidate = True
                            is_parking_violation = True
                            parking_violation_status = (
                                "confirmed_illegal_parking"
                                if is_confirmed
                                else "potential_illegal_parking"
                            )
                            linked_candidates = matched_ids
                            best_match_score = best_score
                            break

            is_shoulder_violation = False
            if source_type != "cctv" and is_rule_enabled(
                source_profile, "shoulder_lane_violation"
            ) and class_allowed_for_rule(
                source_profile, "shoulder_lane_violation", track.class_name
            ):
                for z in shoulder_zones:
                    if not point_inside_polygon(track.center, z["points"]):
                        continue
                    limit = (
                        z["rule_config"].get("min_seconds", 2.0)
                        if z.get("rule_config")
                        else 2.0
                    )
                    if check_shoulder_lane(track, True, dt, limit):
                        is_shoulder_violation = True
                        break

            is_red_light_violation = False
            if is_rule_enabled(
                source_profile, "red_light_violation"
            ) and class_allowed_for_rule(
                source_profile, "red_light_violation", track.class_name
            ):
                traffic_light_state = self.config.get("traffic_light.state", "red")
                for z in stop_line_zones:
                    if not point_inside_polygon(track.center, z["points"]):
                        continue
                    if check_red_light(track, True, traffic_light_state):
                        is_red_light_violation = True
                        break

            is_u_turn_violation = False
            if is_rule_enabled(
                source_profile, "illegal_u_turn"
            ) and class_allowed_for_rule(
                source_profile, "illegal_u_turn", track.class_name
            ):
                all_u_turn_zones = u_turn_zones + [
                    {"points": points} for points in profile_u_turn_zones
                ]
                for z in all_u_turn_zones:
                    if not point_inside_polygon(track.center, z["points"]):
                        continue
                    if check_illegal_u_turn(track, True):
                        is_u_turn_violation = True
                        break

            is_lane_violation = (
                is_rule_enabled(source_profile, "unsafe_lane_change")
                and class_allowed_for_rule(
                    source_profile, "unsafe_lane_change", track.class_name
                )
                and check_unsafe_lane_change(track, inside_lane_a, inside_lane_b, now)
            )

            has_no_right_turn = any(
                s["class_name"] == "no_right_turn_sign" for s in sign_detections
            )
            is_traffic_sign_violation = (
                is_rule_enabled(source_profile, "traffic_sign_violation")
                and class_allowed_for_rule(
                    source_profile, "traffic_sign_violation", track.class_name
                )
                and check_traffic_sign_violation(
                    track, inside_traffic_sign, sign_detected=has_no_right_turn
                )
            )

            is_wrong_direction = False
            for t_id, z_id in wrong_direction_violations:
                if track.track_id == t_id:
                    if zone_manager.check_point_in_zone(track.center, z_id):
                        is_wrong_direction = True
                        break

            is_restricted_area_stop = False
            cctv_stop_limit = float(
                self.config.get("traffic.cctv_stopped_seconds_threshold", 15.0)
            )
            if track.inside_no_parking_zone:
                if source_type == "cctv":
                    if track.stationary_seconds >= cctv_stop_limit:
                        is_restricted_area_stop = True
                elif track.is_stopped:
                    is_restricted_area_stop = True

            def choose_violation(flags: dict, profile: dict) -> Optional[str]:
                priority = profile.get("priority", [])
                for v_type in priority:
                    if flags.get(v_type):
                        return v_type
                for v_type in [
                    "busway_lane_violation",
                    "illegal_parking",
                    "traffic_sign_violation",
                    "illegal_u_turn",
                    "red_light_violation",
                    "unsafe_lane_change",
                    "shoulder_lane_violation",
                    "wrong_direction",
                    "restricted_area_stop",
                ]:
                    if flags.get(v_type):
                        return v_type
                return None

            if source_type != "cctv":
                violation_type = choose_violation(
                    {
                        "illegal_parking": is_parking_violation,
                        "shoulder_lane_violation": is_shoulder_violation,
                        "red_light_violation": is_red_light_violation,
                        "illegal_u_turn": is_u_turn_violation,
                        "unsafe_lane_change": is_lane_violation,
                        "traffic_sign_violation": is_traffic_sign_violation,
                        "wrong_direction": is_wrong_direction,
                        "restricted_area_stop": is_restricted_area_stop,
                        "busway_lane_violation": is_busway_violation,
                    },
                    source_profile,
                )

                if violation_type == "illegal_parking" and parking_violation_status:
                    violation_type = parking_violation_status
            else:
                # CCTV mode: check busway + restricted area violations
                violation_type = choose_violation(
                    {
                        "busway_lane_violation": is_busway_violation,
                        "restricted_area_stop": is_restricted_area_stop,
                        "wrong_direction": is_wrong_direction,
                    },
                    source_profile,
                )

            track.active_violation = violation_type
            if violation_type:
                contextual_reasoning = self.behavior_reasoner.local_assessment(
                    track, violation_type
                )
                if not contextual_reasoning["is_violation"]:
                    track.active_violation = None
                    continue
                violation_track_ids[track.track_id] = violation_type
                can_save = True
                if self.save_once_per_track and track.has_saved_violation:
                    can_save = False
                if track.last_violation_at > 0.0 and (
                    now - track.last_violation_at < self.cooldown_seconds
                ):
                    can_save = False
                if can_save:
                    contextual_reasoning = self.behavior_reasoner.assess(
                        raw_frame, track, violation_type
                    )
                    if not contextual_reasoning["is_violation"]:
                        track.active_violation = None
                        violation_track_ids.pop(track.track_id, None)
                        continue
                    event_id = _make_event_id(self.event_counter)
                    self.event_counter += 1
                    plate_detector = _get_plate_detector()
                    if track.plate_history:
                        best_plate = max(track.plate_history, key=lambda x: x["conf"])
                        plate_number = best_plate["text"]
                        plate_conf = best_plate["conf"]
                        plate_crop = best_plate["crop"]
                    else:
                        plate_crop, plate_conf, _ = plate_detector.detect_plate(
                            raw_frame, track.bbox
                        )
                        anpr = _get_anpr()
                        plate_number, ocr_conf, ocr_raw = anpr.read_plate(
                            plate_crop,
                            track_id=track.track_id,
                            vehicle_type=track.class_name,
                            source_name=self.source_label,
                        )
                        plate_conf = max(plate_conf, ocr_conf)
                    event = {
                        "event_id": event_id,
                        "timestamp": datetime.now().isoformat(timespec="seconds"),
                        "violation_type": violation_type,
                        "track_id": track.track_id,
                        "vehicle_type": track.class_name,
                        "confidence": round(track.confidence, 4),
                        "bbox": list(map(int, track.bbox)),
                        "duration_seconds": round(track.stationary_seconds, 2)
                        if "illegal_parking" in violation_type
                        else 0.0,
                        "plate_number": plate_number or "UNKNOWN",
                        "plate_confidence": round(float(plate_conf), 4),
                        "evidence_image": None,
                        "plate_crop": None,
                        "source": f"{self.source_label}-{self.session_id}",
                        "latitude": 0.0,
                        "longitude": 0.0,
                        "road_name": "livecam",
                        "matching_score": float(best_match_score)
                        if "confirmed_illegal_parking" in violation_type
                        else 0.0,
                        "linked_candidate_ids": linked_candidates
                        if "confirmed_illegal_parking" in violation_type
                        else [],
                        "review_status": "pending",
                        "contextual_reasoning": contextual_reasoning,
                        "image_enhancement": enhancement_metrics,
                    }
                    track.has_saved_violation = True
                    track.last_violation_at = now
                    self.saved_event_counts[violation_type] = (
                        self.saved_event_counts.get(violation_type, 0) + 1
                    )
                    pending_events.append((event, track, plate_crop))

        for sign in sign_detections:
            sx1, sy1, sx2, sy2 = sign["bbox"]
            cv2.rectangle(frame, (sx1, sy1), (sx2, sy2), (0, 0, 255), 2)
            cv2.putText(
                frame,
                f"{sign['class_name'].replace('_', ' ').title()} ({int(sign['confidence'] * 100)}%)",
                (sx1, sy1 - 5),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.45,
                (0, 0, 255),
                2,
            )

        if source_type != "cctv" and dashcam_analysis is not None:
            if self.dashcam_detector is None:
                self.dashcam_detector = _get_dashcam_detector()
            self.dashcam_detector.draw_detections(frame, dashcam_analysis)

        if tracks and self.frame_count % 30 == 0:
            print(f"[LIVECAM DEBUG] Drawing {len(tracks)} tracks: {[(t.track_id, t.class_name) for t in tracks]}")
        for track in tracks:
            v_type = violation_track_ids.get(track.track_id)
            draw_track(
                frame,
                track,
                is_violation=(v_type is not None),
                violation_label=v_type or "",
            )

        if source_type == "cctv":
            traffic = {
                "vehicle_count": density_metrics["vehicle_count"],
                "stopped_count": density_metrics["stopped_vehicle_count"],
                "stopped_ratio": round(
                    density_metrics["stopped_vehicle_count"]
                    / density_metrics["vehicle_count"]
                    if density_metrics["vehicle_count"]
                    else 0.0,
                    3,
                ),
                "level": density_metrics["density_level"],
                "average_speed": density_metrics["average_speed"],
                "dominant_direction": density_metrics["dominant_direction"],
            }
        else:
            traffic = _calculate_traffic(tracks, self.config)
        # draw_panel(frame, self.fps, traffic, f"Live Camera", drawing_mode=False)

        new_events = []
        for event, _track, plate_crop in pending_events:
            event["evidence_image"] = self.evidence.save_image(frame, event["event_id"])
            event["plate_crop"] = self.evidence.save_plate_crop(
                plate_crop, event["event_id"]
            )
            self.evidence.append_jsonl(event)
            new_events.append(event)
            print(
                f"[LIVECAM EVENT] {event['event_id']} {event['violation_type']} track={event['track_id']} plate={event['plate_number']}"
            )

        encode_params = [cv2.IMWRITE_JPEG_QUALITY, self.jpeg_quality]
        _, jpeg_out = cv2.imencode(".jpg", frame, encode_params)
        frame_bytes = jpeg_out.tobytes()

        detection_list = []
        for track in tracks:
            detection_list.append(
                {
                    "track_id": track.track_id,
                    "class_name": track.class_name,
                    "confidence": round(track.confidence, 3),
                    "bbox": list(map(int, track.bbox)),
                    "is_stopped": track.is_stopped,
                    "stationary_seconds": round(track.stationary_seconds, 1),
                    "violation": violation_track_ids.get(track.track_id),
                    "contextual_behavior": getattr(track, "active_violation", None),
                }
            )

        for i, sign in enumerate(sign_detections):
            detection_list.append(
                {
                    "track_id": -(i + 1),
                    "class_name": sign["class_name"],
                    "confidence": round(sign["confidence"], 3),
                    "bbox": list(map(int, sign["bbox"])),
                    "is_stopped": False,
                    "stationary_seconds": 0.0,
                    "violation": None,
                }
            )

        self.last_traffic_metrics = traffic
        self.last_detections_list = detection_list

        return {
            "frame_bytes": frame_bytes,
            "metadata": {
                "frame_count": self.frame_count,
                "fps": round(self.fps, 1),
                "detections": detection_list,
                "traffic": traffic,
                "new_events": new_events,
                "image_enhancement": enhancement_metrics,
                "session_duration": round(now_real - self.start_time, 1),
                "signs": sign_detections,
                "dashcam": dashcam_analysis.to_dict() if dashcam_analysis is not None else None,
            },
        }

    def process_fast_frame(self, frame: np.ndarray) -> Dict[str, Any]:
        if self._processing:
            return {"dropped": True}
        self._processing = True
        try:
            if frame is None or frame.size == 0:
                return {"error": "Empty frame"}
            frame = self._resize(frame)
            now_real = time.time()
            dt = now_real - self.last_time
            self.last_time = now_real
            self.fps = 1.0 / dt if dt > 0 else 0.0
            self.frame_count += 1
            by_filename = self.config.get("source_profiles.by_filename", {}) or {}
            source_profile = by_filename.get(
                self.source_label, self.config.get("source_profiles.default", {})
            )
            source_type = source_profile.get(
                "source_type", self.config.get("source.type", "public_transport_camera")
            )
            zone_manager = _get_zone_manager()
            enabled_violations = source_profile.get("enabled_violations", [])
            if source_type != "cctv":
                zone_manager.draw_zones(
                    frame,
                    enabled_violations=enabled_violations,
                    source_type=source_type,
                    source_label=self.source_label,
                )
            if source_type == "cctv":
                # self.cctv_analytics.draw_analytics(frame)
                pass
            sign_detections = getattr(self, "cached_sign_detections", []) if source_type != "cctv" else []
            for sign in sign_detections:
                sx1, sy1, sx2, sy2 = sign["bbox"]
                cv2.rectangle(frame, (sx1, sy1), (sx2, sy2), (0, 0, 255), 2)
                cv2.putText(
                    frame,
                    f"{sign['class_name'].replace('_', ' ').title()} ({int(sign['confidence'] * 100)}%)",
                    (sx1, sy1 - 5),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.45,
                    (0, 0, 255),
                    2,
                )
            tracks = list(self.tracker.tracks.values())
            for track in tracks:
                if track.class_name == "person":
                    continue
                v_type = getattr(track, "active_violation", None)
                draw_track(
                    frame,
                    track,
                    is_violation=(v_type is not None),
                    violation_label=v_type or "",
                )
            if source_type == "cctv" and hasattr(self, "last_traffic_metrics"):
                traffic = self.last_traffic_metrics
            else:
                traffic = _calculate_traffic(tracks, self.config)
            # draw_panel(frame, self.fps, traffic, f"Live Camera", drawing_mode=False)
            encode_params = [cv2.IMWRITE_JPEG_QUALITY, self.jpeg_quality]
            _, jpeg_out = cv2.imencode(".jpg", frame, encode_params)
            frame_bytes = jpeg_out.tobytes()
            return {
                "frame_bytes": frame_bytes,
                "metadata": {
                    "frame_count": self.frame_count,
                    "fps": round(self.fps, 1),
                    "detections": getattr(self, "last_detections_list", []),
                    "traffic": traffic,
                    "new_events": [],
                    "session_duration": round(now_real - self.start_time, 1),
                    "signs": sign_detections,
                },
            }
        finally:
            self._processing = False

    def _resize(self, frame: np.ndarray) -> np.ndarray:
        h, w = frame.shape[:2]
        if w <= self.resize_width:
            if not frame.flags.writeable:
                return frame.copy()
            return frame
        scale = self.resize_width / float(w)
        new_h = int(h * scale)
        return cv2.resize(frame, (self.resize_width, new_h))
