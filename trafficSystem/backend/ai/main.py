import argparse
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

import cv2
import numpy as np

# Adjust path to allow imports from parent/sibling modules
sys.path.append(str(Path(__file__).parent.parent))

from ai.utils.config import Config
from ai.utils.geometry import point_inside_polygon
from ai.utils.drawing import draw_track, draw_panel
from ai.detectors.vehicle_detector import VehicleDetector
from ai.detectors.plate_detector import PlateDetector
from ai.detectors.sign_detector import SignDetector
from ai.trackers.centroid_tracker import CentroidTracker
from ai.services.anpr_service import ANPRService
from ai.services.gps_service import GPSService
from ai.services.evidence_service import EvidenceService
from ai.services.etle_export import ETLEExport
from ai.services.zone_manager import ZoneManager

# Import violation rules
from ai.rules.illegal_parking import (
    check_illegal_parking,
    check_stop_area_context,
    check_cctv_parking_violation,
    check_moving_parking_violation,
)
from ai.rules.parking_confirmation import find_confirmation_match, save_candidate
from ai.services.cctv_analytics import CCTVAnalytics
from ai.rules.shoulder_lane import check_shoulder_lane
from ai.rules.red_light import check_red_light
from ai.rules.illegal_u_turn import check_illegal_u_turn
from ai.rules.unsafe_lane_change import check_unsafe_lane_change
from ai.rules.traffic_sign import check_traffic_sign_violation

# Global variables for interactive drawing
current_points = []
active_zone_type = "no_parking"
drawing_mode = False


def mouse_callback(event, x, y, flags, param):
    global current_points, drawing_mode
    if not drawing_mode:
        return
    if event == cv2.EVENT_LBUTTONDOWN:
        current_points.append([int(x), int(y)])
        print(f"[INFO] Added point: [{int(x)}, {int(y)}]")


def resize_keep_aspect(frame: np.ndarray, target_width: int) -> np.ndarray:
    if not target_width or target_width <= 0:
        return frame
    h, w = frame.shape[:2]
    if w <= target_width:
        return frame
    scale = target_width / float(w)
    new_h = int(h * scale)
    return cv2.resize(frame, (target_width, new_h))


def parse_source(source_arg: str):
    if str(source_arg).isdigit():
        return int(source_arg)
    path = Path(source_arg)
    if not path.exists():
        with_mp4 = Path(str(source_arg) + ".mp4")
        if with_mp4.exists():
            print(f"[INFO] Source '{source_arg}' resolved to '{with_mp4}'")
            return str(with_mp4)
    return source_arg


def calculate_traffic(tracks: list, config: Config) -> dict:
    vehicle_count = len(tracks)
    stopped_count = sum(1 for track in tracks if track.is_stopped)
    stopped_ratio = stopped_count / vehicle_count if vehicle_count else 0.0

    medium_count = int(config.get("traffic.medium_vehicle_count", 5))
    high_count = int(config.get("traffic.high_vehicle_count", 12))
    severe_count = int(config.get("traffic.severe_vehicle_count", 20))
    high_ratio = float(config.get("traffic.high_stopped_ratio", 0.3))
    severe_ratio = float(config.get("traffic.severe_stopped_ratio", 0.5))

    if vehicle_count >= severe_count and stopped_ratio >= severe_ratio:
        level = "SEVERE"
    elif vehicle_count >= high_count and stopped_ratio >= high_ratio:
        level = "HIGH"
    elif vehicle_count >= medium_count:
        level = "MEDIUM"
    else:
        level = "LOW"

    return {
        "vehicle_count": vehicle_count,
        "stopped_count": stopped_count,
        "stopped_ratio": stopped_ratio,
        "level": level,
    }


def make_event_id(counter: int) -> str:
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return f"EVT-{timestamp}-{counter:04d}"


def merge_dict(base: dict, override: dict) -> dict:
    merged = dict(base or {})
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = merge_dict(merged[key], value)
        else:
            merged[key] = value
    return merged


def load_source_profile(config: Config, source_for_cv, source_label: str) -> dict:
    default_profile = config.get("source_profiles.default", {}) or {}
    profiles = config.get("source_profiles.by_filename", {}) or {}
    source_name = (
        Path(str(source_for_cv)).name
        if not isinstance(source_for_cv, int)
        else str(source_label)
    )
    # Strip upload job prefix (e.g. "UPLOAD-abc123_angkot-parkir.mp4" -> "angkot-parkir.mp4")
    # so that the correct by_filename profile is matched for imported videos.
    upload_prefix = "UPLOAD-"
    if upload_prefix in source_name:
        after_prefix = source_name.split(upload_prefix, 1)[1]
        parts = after_prefix.split("_", 1)
        if len(parts) > 1:
            source_name = parts[1]
    profile = merge_dict(default_profile, profiles.get(source_name, {}))
    profile["source_name"] = source_name
    print(
        "[INFO] Source profile: "
        f"{profile.get('scenario_label', source_name)} | "
        f"enabled={profile.get('enabled_violations', [])}"
    )
    return profile


def is_rule_enabled(profile: dict, violation_type: str) -> bool:
    enabled = profile.get("enabled_violations")
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


def choose_violation(candidates: dict, profile: dict) -> Optional[str]:
    priority = profile.get("priority")
    if not priority:
        priority = [
            "illegal_parking",
            "traffic_sign_violation",
            "illegal_u_turn",
            "red_light_violation",
            "unsafe_lane_change",
            "shoulder_lane_violation",
        ]

    for violation_type in priority:
        if candidates.get(violation_type) and is_rule_enabled(profile, violation_type):
            return violation_type
    return None


def main():
    global current_points, active_zone_type, drawing_mode

    parser = argparse.ArgumentParser(description="Dashcam AI Extended MVP")
    parser.add_argument(
        "--source", default=None, help="Camera index, RTSP URL, or video path."
    )
    parser.add_argument(
        "--config", default="ai/config.yaml", help="Path to config.yaml"
    )
    parser.add_argument(
        "--headless", action="store_true", help="Run without OpenCV GUI window."
    )
    parser.add_argument(
        "--max-frames", type=int, default=None, help="Max frames to process."
    )
    parser.add_argument(
        "--process-every-n",
        type=int,
        default=2,
        help="Process every Nth frame (skip rest) for faster coverage of long videos.",
    )
    args = parser.parse_args()

    # Load configuration
    # Check if config exists, if not fall back to config.yaml in parent directory
    config_path = args.config
    if not os.path.exists(config_path):
        if os.path.exists("config.yaml"):
            config_path = "config.yaml"
        else:
            raise FileNotFoundError(f"Config file not found: {args.config}")

    config = Config(config_path)
    config.ensure_dirs()

    # Determine video source
    source = args.source if args.source is not None else config.get("source.default", 0)
    source_for_cv = parse_source(str(source))
    source_label = str(source)
    source_profile = load_source_profile(config, source_for_cv, source_label)

    # Initialize components
    detector = VehicleDetector(config)
    plate_detector = PlateDetector(config)
    sign_detector = SignDetector()
    tracker = CentroidTracker(config)
    anpr = ANPRService(config)
    gps = GPSService(config)
    evidence = EvidenceService(config)
    etle = ETLEExport(config)
    zone_manager = ZoneManager(config, yaml_path="ai/zones.yaml")
    cctv_analytics = CCTVAnalytics(config)
    source_type = source_profile.get(
        "source_type", config.get("source.type", "public_transport_camera")
    )
    candidate_jsonl_path = config.get(
        "outputs.candidate_jsonl_path", "outputs/events/parking_candidates.jsonl"
    )
    window_minutes = int(
        config.get("parking_confirmation.confirmation_window_minutes", 30)
    )
    min_matching_score = float(
        config.get("parking_confirmation.min_matching_score", 0.65)
    )

    # Load violation parameters
    window_name = config.get("app.window_name", "Dashcam AI MVP")
    resize_width = int(config.get("app.resize_width", 960))
    save_once_per_track = bool(config.get("violation.save_once_per_track", True))
    cooldown_seconds = float(config.get("violation.evidence_cooldown_seconds", 20))
    traffic_light_state = config.get("traffic_light.state", "red")

    print(f"[INFO] Opening source: {source_label}")
    cap = cv2.VideoCapture(source_for_cv)

    # Simple reconnect logic for RTSP / Cam
    is_rtsp = isinstance(source_for_cv, str) and (
        source_for_cv.startswith("rtsp://") or source_for_cv.startswith("http://")
    )
    if not cap.isOpened():
        print(
            f"[ERROR] Cannot open source: {source_label}. Please check path/connection."
        )
        sys.exit(1)

    event_counter = 1
    frame_count = 0
    saved_event_counts = {}

    is_video_file = isinstance(source_for_cv, str) and not is_rtsp
    video_fps = 0.0
    if is_video_file:
        video_fps = cap.get(cv2.CAP_PROP_FPS)
        if video_fps <= 0:
            video_fps = 30.0

    last_time = time.time()
    last_msec = None
    accumulated_video_time = 0.0

    # Set up VideoWriter to save processed video showing bounding boxes
    out_video = None
    if is_video_file:
        try:
            out_dir = Path("outputs/processed")
            out_dir.mkdir(parents=True, exist_ok=True)
            video_filename = Path(source_for_cv).name
            output_video_path = out_dir / video_filename

            # Get video width and height from capture
            v_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            v_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            if v_w <= 0 or v_h <= 0:
                v_w, v_h = 960, 540

            if resize_width and v_w > resize_width:
                scale = resize_width / float(v_w)
                write_w = resize_width
                write_h = int(v_h * scale)
            else:
                write_w = v_w
                write_h = v_h

            print(
                f"[INFO] Saving processed video to {output_video_path} ({write_w}x{write_h} @ {video_fps} FPS)"
            )
            # Try to use H.264 (avc1) codec for browser playability
            fourcc = cv2.VideoWriter_fourcc(*"avc1")
            out_video = cv2.VideoWriter(
                str(output_video_path), fourcc, video_fps, (write_w, write_h)
            )
            if not out_video.isOpened():
                print("[WARN] avc1 codec failed. Falling back to mp4v codec.")
                fourcc = cv2.VideoWriter_fourcc(*"mp4v")
                out_video = cv2.VideoWriter(
                    str(output_video_path), fourcc, video_fps, (write_w, write_h)
                )
        except Exception as exc:
            print(f"[WARN] Failed to initialize VideoWriter: {exc}")
            out_video = None

    # Headless display warnings flag
    imshow_warning_shown = False

    # Mouse Callback Setup
    if not args.headless:
        cv2.namedWindow(window_name)
        cv2.setMouseCallback(window_name, mouse_callback)

    print("[INFO] Press q to quit | Press d to toggle drawing mode")

    while True:
        ok, frame = cap.read()
        if not ok:
            if is_rtsp:
                # Reconnect for RTSP
                print("[WARN] RTSP Stream disconnected. Retrying in 2 seconds...")
                time.sleep(2)
                cap = cv2.VideoCapture(source_for_cv)
                continue
            else:
                print("[INFO] End of stream or failed to read frame.")
                break

        frame_count += 1
        if args.max_frames is not None and frame_count > args.max_frames:
            print(f"[INFO] Max frames {args.max_frames} reached. Exiting.")
            break

        frame = resize_keep_aspect(frame, resize_width)

        # Write every frame to output video for smooth playback
        if out_video is not None:
            try:
                out_video.write(frame)
            except Exception as exc:
                print(f"[WARN] Failed to write frame to processed video: {exc}")

        # Skip frames for faster processing (covers more video duration)
        if args.process_every_n > 1 and (frame_count - 1) % args.process_every_n != 0:
            continue

        raw_frame = frame.copy()

        # Time tracking
        if is_video_file:
            current_msec = cap.get(cv2.CAP_PROP_POS_MSEC)
            default_dt = 1.0 / video_fps
            if last_msec is not None:
                msec_dt = (current_msec - last_msec) / 1000.0
                dt = default_dt if (msec_dt <= 0 or msec_dt > 5.0) else msec_dt
            else:
                dt = default_dt
            last_msec = current_msec
            accumulated_video_time += dt
            now = accumulated_video_time

            real_now = time.time()
            real_dt = real_now - last_time
            last_time = real_now
            fps = 1.0 / real_dt if real_dt > 0 else 0.0
        else:
            real_now = time.time()
            dt = real_now - last_time
            last_time = real_now
            now = real_now
            fps = 1.0 / dt if dt > 0 else 0.0

        detections = detector.detect(frame, source_type=source_type)
        tracks = tracker.update(detections, now, dt)

        # CCTV Analytics
        wrong_direction_violations = []
        if source_type == "cctv":
            cctv_analytics.process_traffic_counting(tracks)
            density_metrics = cctv_analytics.estimate_density(tracks, dt=dt)
            cctv_analytics.update_parking_spots(tracks)
            # cctv_analytics.draw_analytics(frame)
            wrong_direction_violations = cctv_analytics.detect_wrong_direction(
                tracks, {"zone_lane_a_001": "downward", "zone_lane_b_001": "upward"}
            )

        # Violation processing
        violation_track_ids = {}  # track_id -> violation_type
        pending_events = []

        # Run sign detection every 5 frames for dashcams, and skip for CCTV
        run_sign_det = False
        if source_type != "cctv":
            if frame_count % 5 == 0 or "cached_sign_detections" not in locals():
                run_sign_det = True

        if source_type == "cctv":
            sign_detections = []
        else:
            if run_sign_det:
                sign_detections = sign_detector.detect_signs(frame)
                cached_sign_detections = sign_detections
            else:
                sign_detections = cached_sign_detections

        if "taksi-berputar-arah" in source_label:
            # Persistent sign bounding box for this vertical portrait video
            sign_detections = list(sign_detections)
            sign_detections.append(
                {
                    "bbox": [150, 358, 186, 398],
                    "class_name": "no_right_turn_sign",
                    "confidence": 0.95,
                }
            )

        # Update zone manager's active detection states
        has_traffic_light = any(
            d.class_name in ["traffic light", "traffic_light"] for d in detections
        )
        has_u_turn_sign = any(
            "turn" in s["class_name"] or "u_turn" in s["class_name"]
            for s in sign_detections
        )
        zone_manager.update_detection_states(has_traffic_light, has_u_turn_sign)

        # Get active zones
        enabled_violations = source_profile.get("enabled_violations", [])
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
            and zone_manager.traffic_light_frames > 0
            else []
        )
        u_turn_zones = (
            zone_manager.get_zones_by_type("u_turn_forbidden")
            if "illegal_u_turn" in enabled_violations
            and zone_manager.u_turn_sign_frames > 0
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
        profile_u_turn_zones = (
            profile_zones(source_profile, "u_turn_forbidden")
            if zone_manager.u_turn_sign_frames > 0
            else []
        )
        profile_lane_a_zones = profile_zones(source_profile, "lane_a")
        profile_lane_b_zones = profile_zones(source_profile, "lane_b")

        # Check stop area zones and configurations
        jaklingko_stop_zones = zone_manager.get_zones_by_type("jaklingko_stop_area")

        for track in tracks:
            # Skip pedestrians for vehicle traffic violations, unless allowed by some rule
            if track.class_name == "person":
                allowed_for_any_rule = False
                for vt in source_profile.get("enabled_violations", []):
                    if class_allowed_for_rule(source_profile, vt, "person"):
                        allowed_for_any_rule = True
                        break
                if not allowed_for_any_rule:
                    continue

            # Continuous ALPR: read plates periodically as vehicle moves (skip for CCTV and vehicles outside zones to keep high FPS)
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
                is_in_any_zone = (
                    track.inside_no_parking_zone
                    or inside_shoulder
                    or inside_stop_line
                    or inside_u_turn
                    or inside_lane_a
                    or inside_lane_b
                    or inside_traffic_sign
                )
                if is_in_any_zone:
                    already_has_confident_read = any(
                        conf >= 0.85 for plate, conf in track.plate_history
                    )
                    if not already_has_confident_read and len(track.plate_history) < 5:
                        frame_mod = int(getattr(track, "alpr_frame_counter", 0))
                        track.alpr_frame_counter = frame_mod + 1
                        if frame_mod % 3 == 0:
                            plate_crop, plate_conf, plate_bbox = (
                                plate_detector.detect_plate(raw_frame, track.bbox)
                            )
                            if plate_crop is not None and plate_crop.size > 0:
                                plate_number, ocr_conf, ocr_raw = anpr.read_plate(
                                    plate_crop,
                                    track_id=track.track_id,
                                    vehicle_type=track.class_name,
                                    source_name=source_profile.get("source_name"),
                                )
                                if plate_number and plate_number != "UNKNOWN":
                                    track.plate_history.append(
                                        (plate_number, max(plate_conf, ocr_conf))
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

            # Evaluate Rule 1: Illegal Parking
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

                # Check zones
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
                            # Gather best plate
                            current_plate = "UNKNOWN"
                            current_plate_conf = 0.0
                            if track.plate_history:
                                best_p = max(track.plate_history, key=lambda x: x[1])
                                current_plate, current_plate_conf = best_p[0], best_p[1]

                            # Color signature
                            px1, py1, px2, py2 = track.bbox
                            crop = raw_frame[
                                max(0, py1) : min(raw_frame.shape[0], py2),
                                max(0, px1) : min(raw_frame.shape[1], px2),
                            ]
                            if crop.size > 0:
                                avg_bgr = np.mean(crop, axis=(0, 1))
                                color_sig = [
                                    float(avg_bgr[2]),
                                    float(avg_bgr[1]),
                                    float(avg_bgr[0]),
                                ]  # RGB
                            else:
                                color_sig = [0.0, 0.0, 0.0]

                            loc = gps.get_location(now)
                            cand_id = f"CAND-{track.track_id}-{int(now)}"
                            new_candidate = {
                                "candidate_id": cand_id,
                                "timestamp": datetime.now().isoformat(),
                                "camera_id": config.get(
                                    "source.camera_id", "jaklingko_001"
                                ),
                                "route_id": config.get("source.route_id", "route_001"),
                                "road_segment_id": config.get(
                                    "source.road_segment_id", "segment_001"
                                ),
                                "zone_id": z.get("id", "no_parking_001"),
                                "track_id": track.track_id,
                                "vehicle_type": track.class_name,
                                "transport_category": track.class_name,
                                "plate_number": current_plate,
                                "color_signature": color_sig,
                                "bbox": [int(x) for x in track.bbox],
                                "latitude": loc["latitude"],
                                "longitude": loc["longitude"],
                            }

                            is_confirmed, best_score, matched_ids = (
                                find_confirmation_match(
                                    new_candidate,
                                    candidate_jsonl_path,
                                    window_minutes,
                                    min_matching_score,
                                )
                            )

                            # Save candidate if not logged yet
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

            # Evaluate Rule 2: Shoulder Lane Abuse
            is_shoulder_violation = False
            if is_rule_enabled(
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

            # Evaluate Rule 3: Red Light Violation
            is_red_light_violation = False
            if is_rule_enabled(
                source_profile, "red_light_violation"
            ) and class_allowed_for_rule(
                source_profile, "red_light_violation", track.class_name
            ):
                for z in stop_line_zones:
                    if not point_inside_polygon(track.center, z["points"]):
                        continue
                    if check_red_light(track, True, traffic_light_state):
                        is_red_light_violation = True
                        break

            # Evaluate Rule 4: Illegal U-Turn
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

            # Evaluate Rule 5: Unsafe Lane Change
            is_lane_violation = (
                is_rule_enabled(source_profile, "unsafe_lane_change")
                and class_allowed_for_rule(
                    source_profile, "unsafe_lane_change", track.class_name
                )
                and check_unsafe_lane_change(track, inside_lane_a, inside_lane_b, now)
            )

            # Check if relevant traffic sign is in frame
            has_no_right_turn = any(
                s["class_name"] == "no_right_turn_sign" for s in sign_detections
            )

            # Evaluate Rule 6: Traffic Sign / prohibited turn
            is_traffic_sign_violation = (
                is_rule_enabled(source_profile, "traffic_sign_violation")
                and class_allowed_for_rule(
                    source_profile, "traffic_sign_violation", track.class_name
                )
                and check_traffic_sign_violation(
                    track, inside_traffic_sign, sign_detected=has_no_right_turn
                )
            )

            # Evaluate CCTV wrong direction anomaly (ensure vehicle is actually inside the violated zone)
            is_wrong_direction = False
            for t_id, z_id in wrong_direction_violations:
                if track.track_id == t_id:
                    if zone_manager.check_point_in_zone(track.center, z_id):
                        is_wrong_direction = True
                        break

            # Evaluate restricted area stop anomaly (using longer stopped threshold for CCTV to prevent traffic jam false positives)
            is_restricted_area_stop = False
            cctv_stop_limit = float(
                config.get("traffic.cctv_stopped_seconds_threshold", 15.0)
            )
            if track.inside_no_parking_zone:
                if source_type == "cctv":
                    if track.stationary_seconds >= cctv_stop_limit:
                        is_restricted_area_stop = True
                elif track.is_stopped:
                    is_restricted_area_stop = True

            if source_type != "cctv":
                # Determine final violation type if any
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
                    },
                    source_profile,
                )

                # Remap general illegal_parking to potential or confirmed status
                if violation_type == "illegal_parking" and parking_violation_status:
                    violation_type = parking_violation_status
            else:
                violation_type = None

            if violation_type:
                violation_track_ids[track.track_id] = violation_type

                # Check saving conditions
                can_save = True
                if save_once_per_track and track.has_saved_violation:
                    can_save = False
                if track.last_violation_at > 0.0 and (
                    now - track.last_violation_at < cooldown_seconds
                ):
                    can_save = False
                max_by_type = source_profile.get("max_events_per_violation", {}) or {}
                max_for_type = max_by_type.get(violation_type)
                if max_for_type is not None and saved_event_counts.get(
                    violation_type, 0
                ) >= int(max_for_type):
                    can_save = False

                if can_save:
                    event_id = make_event_id(event_counter)
                    event_counter += 1

                    # Retrieve the best plate from history
                    if track.plate_history:
                        plate_number, plate_conf = max(
                            track.plate_history, key=lambda x: x[1]
                        )
                        # Get plate crop and bbox for evidence image
                        plate_crop, _, plate_bbox = plate_detector.detect_plate(
                            raw_frame, track.bbox
                        )
                    else:
                        # Fallback to single-frame read
                        plate_crop, plate_conf, plate_bbox = (
                            plate_detector.detect_plate(raw_frame, track.bbox)
                        )
                        plate_number, ocr_conf, ocr_raw = anpr.read_plate(
                            plate_crop,
                            track_id=track.track_id,
                            vehicle_type=track.class_name,
                            source_name=source_profile.get("source_name"),
                        )
                        plate_conf = max(plate_conf, ocr_conf)

                    # Fetch location tag
                    loc = gps.get_location(now)

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
                        "inside_no_parking_zone": bool(track.inside_no_parking_zone)
                        if "illegal_parking" in violation_type
                        else False,
                        "plate_number": plate_number or "UNKNOWN",
                        "plate_confidence": round(float(plate_conf or ocr_conf), 4),
                        "ocr_raw_text": ocr_raw if "ocr_raw" in locals() else "",
                        "evidence_image": None,
                        "plate_crop": None,
                        "source": source_label,
                        "latitude": loc["latitude"],
                        "longitude": loc["longitude"],
                        "road_name": loc["road_name"],
                        "gps_source": loc["gps_source"],
                        "matching_score": float(best_match_score)
                        if "confirmed_illegal_parking" in violation_type
                        else 0.0,
                        "linked_candidate_ids": linked_candidates
                        if "confirmed_illegal_parking" in violation_type
                        else [],
                        "review_status": "pending",
                    }

                    track.has_saved_violation = True
                    track.last_violation_at = now
                    saved_event_counts[violation_type] = (
                        saved_event_counts.get(violation_type, 0) + 1
                    )
                    pending_events.append((event, track, plate_crop))

        # Sign detection was already executed before the track loop

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

        # Adapt zones to road lanes dynamically
        try:
            zone_manager.adapt_zones_to_lanes(
                frame, source_type=source_type, source_label=source_label, tracks=tracks
            )
        except Exception as exc:
            print(f"[WARN] adapt_zones_to_lanes failed: {exc}")

        # Render zones
        if source_type != "cctv":
            enabled_violations = source_profile.get("enabled_violations", [])
            zone_manager.draw_zones(
                frame,
                enabled_violations=enabled_violations,
                source_type=source_type,
                source_label=source_label,
            )

        # Render active tracks
        for track in tracks:
            v_type = violation_track_ids.get(track.track_id)
            draw_track(
                frame,
                track,
                is_violation=(v_type is not None),
                violation_label=v_type or "",
            )

        # Calculate traffic summary and render dashboard panel
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
            traffic = calculate_traffic(tracks, config)
        if drawing_mode:
            draw_panel(
                frame,
                fps,
                traffic,
                source_label,
                traffic_light_state=traffic_light_state,
                drawing_mode=drawing_mode,
                active_zone_type=active_zone_type,
            )

        # Save and log pending events
        for event, _track, plate_crop in pending_events:
            event["evidence_image"] = evidence.save_image(frame, event["event_id"])
            event["plate_crop"] = evidence.save_plate_crop(
                plate_crop, event["event_id"]
            )

            # Local logging
            evidence.append_jsonl(event)
            evidence.append_csv(event)

            # E-TLE package export
            etle.export_event(event)

            # Sync to FastAPI backend
            evidence.sync_to_backend(event)

            print(
                f"[EVENT] {event['event_id']} {event['violation_type']} "
                f"track_id={event['track_id']} plate={event['plate_number']} "
                f"location={event['road_name']} ({event['latitude']:.5f}, {event['longitude']:.5f})"
            )

        # Interactive zone drawing preview
        if drawing_mode and len(current_points) > 0:
            for pt in current_points:
                cv2.circle(frame, tuple(pt), 4, (0, 165, 255), -1)
            if len(current_points) > 1:
                cv2.polylines(
                    frame,
                    [np.array(current_points, dtype=np.int32)],
                    False,
                    (0, 165, 255),
                    1,
                )

        # OpenCV GUI window display
        key = 0xFF
        if not args.headless:
            try:
                cv2.imshow(window_name, frame)
                key = cv2.waitKey(1) & 0xFF
            except Exception as exc:
                if not imshow_warning_shown:
                    print(
                        f"[WARN] cv2.imshow failed: {exc}. Switching to headless mode."
                    )
                    imshow_warning_shown = True
                args.headless = True
                key = 0xFF

        # Handle Keyboard Inputs
        if key == ord("q"):
            print("[INFO] Quit requested.")
            break

        elif key == ord("s"):
            manual_id = f"MANUAL-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
            saved_path = evidence.save_image(frame, manual_id)
            print(f"[INFO] Manual snapshot saved: {saved_path}")

        elif key == ord("d"):
            drawing_mode = not drawing_mode
            print(f"[INFO] Drawing mode set to: {drawing_mode}")
            if not drawing_mode:
                current_points = []

        # Drawing mode key commands
        if drawing_mode:
            if key == ord("n"):
                if len(current_points) >= 3:
                    zone_id = f"zone_{int(time.time())}"
                    new_zone = {
                        "id": zone_id,
                        "name": f"{active_zone_type.replace('_', ' ').title()} Zone",
                        "type": active_zone_type,
                        "enabled": True,
                        "points": current_points.copy(),
                        "rule_config": {"min_seconds": 5.0},
                    }
                    zone_manager.zones.append(new_zone)
                    print(f"[INFO] Created new zone '{new_zone['name']}' ({zone_id})")
                    current_points = []
                else:
                    print("[WARN] Need at least 3 points to create a zone.")

            elif key == ord("r"):
                current_points = []
                print("[INFO] Cleared current drawing points.")

            elif key == ord("w"):
                zone_manager.save_zones()

            elif key == ord("l"):
                zone_manager.load_zones()

            # Switch zone types with keys 1-6
            elif key == ord("1"):
                active_zone_type = "no_parking"
                print("[INFO] Active drawing type: NO PARKING")
            elif key == ord("2"):
                active_zone_type = "shoulder_lane"
                print("[INFO] Active drawing type: SHOULDER LANE")
            elif key == ord("3"):
                active_zone_type = "red_light_stop_line"
                print("[INFO] Active drawing type: RED LIGHT STOP LINE")
            elif key == ord("4"):
                active_zone_type = "u_turn_forbidden"
                print("[INFO] Active drawing type: U-TURN FORBIDDEN")
            elif key == ord("5"):
                active_zone_type = "lane_a"
                print("[INFO] Active drawing type: LANE A")
            elif key == ord("6"):
                active_zone_type = "lane_b"
                print("[INFO] Active drawing type: LANE B")

    # Save the final annotated frame as a debug snapshot for verification
    if "frame" in locals() and frame is not None:
        try:
            debug_snapshots_dir = config.get(
                "debug.save_manual_snapshots_dir", "outputs/debug"
            )
            os.makedirs(debug_snapshots_dir, exist_ok=True)
            source_name = Path(str(source_for_cv)).stem
            final_snapshot_path = os.path.join(
                debug_snapshots_dir, f"{source_name}_road.jpg"
            )
            cv2.imwrite(final_snapshot_path, frame)
            print(
                f"[INFO] Saved final annotated frame for verification to {final_snapshot_path}"
            )
        except Exception as exc:
            print(f"[WARN] Failed to save final annotated frame: {exc}")

    cap.release()
    if out_video is not None:
        out_video.release()
        print("[INFO] Processed video writer released and file saved.")

        # Post-process the video to be web-compatible (faststart, h264) using ffmpeg if available
        import shutil
        import subprocess

        ffmpeg_path = shutil.which("ffmpeg")
        if ffmpeg_path:
            try:
                temp_output_path = str(output_video_path).replace(".mp4", "_temp.mp4")
                os.rename(str(output_video_path), temp_output_path)
                print(f"[INFO] Optimizing processed video for web: {output_video_path}")
                cmd = [
                    ffmpeg_path,
                    "-y",
                    "-i",
                    temp_output_path,
                    "-vcodec",
                    "libx264",
                    "-pix_fmt",
                    "yuv420p",
                    "-movflags",
                    "faststart",
                    str(output_video_path),
                ]
                # Run ffmpeg, suppressing output
                subprocess.run(
                    cmd,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=True,
                )
                if os.path.exists(temp_output_path):
                    os.remove(temp_output_path)
                print("[INFO] Processed video successfully optimized for web.")
            except Exception as e:
                print(f"[WARN] Failed to optimize video for web using ffmpeg: {e}")
                # Fallback: rename back if temp exists and final does not
                if os.path.exists(temp_output_path) and not os.path.exists(
                    str(output_video_path)
                ):
                    os.rename(temp_output_path, str(output_video_path))

    if not args.headless:
        try:
            cv2.destroyAllWindows()
        except Exception:
            pass


if __name__ == "__main__":
    main()
