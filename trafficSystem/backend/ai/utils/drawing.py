from typing import Any, Dict, Optional
import cv2
import numpy as np
from ai.trackers.tracker_interface import Track

DASHCAM_CATEGORY_COLORS = {
    "vehicle": (0, 255, 0),
    "pedestrian": (255, 255, 0),
    "bicycle": (255, 165, 0),
    "traffic_light": (0, 0, 255),
    "traffic_sign": (255, 0, 255),
    "unknown": (128, 128, 128),
}

DASHCAM_CATEGORY_LABELS = {
    "vehicle": "VEH",
    "pedestrian": "PED",
    "bicycle": "BIKE",
    "traffic_light": "TL",
    "traffic_sign": "SIGN",
}


def draw_dashcam_detection(
    frame: np.ndarray,
    bbox: tuple,
    class_name: str,
    category: str,
    confidence: float,
    lane: Optional[str] = None,
) -> None:
    color = DASHCAM_CATEGORY_COLORS.get(category, DASHCAM_CATEGORY_COLORS["unknown"])
    x1, y1, x2, y2 = bbox
    cx = (x1 + x2) // 2
    cy = (y1 + y2) // 2

    cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
    cv2.circle(frame, (cx, cy), 3, color, -1)

    short = DASHCAM_CATEGORY_LABELS.get(category, class_name.upper())
    label = f"{short} {confidence:.2f}"
    if lane:
        label += f" [{lane}]"

    (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.45, 2)
    cv2.rectangle(frame, (x1, y1 - th - 6), (x1 + tw, y1), color, -1)
    cv2.putText(
        frame, label, (x1, y1 - 4), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 0), 2
    )

    status_color = (0, 255, 0) if category == "vehicle" else color
    cv2.putText(
        frame,
        class_name.upper(),
        (cx - 10, cy + 4),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.35,
        status_color,
        1,
    )


def draw_track(
    frame: np.ndarray,
    track: Track,
    is_violation: bool = False,
    violation_label: str = "",
) -> None:
    x1, y1, x2, y2 = track.bbox

    # Define color scheme
    if is_violation:
        color = (0, 0, 255)  # Red
    elif track.is_stopped:
        color = (0, 255, 255)  # Yellow
    else:
        color = (0, 255, 0)  # Green

    # Draw rectangle and center point
    cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
    cv2.circle(frame, track.center, 4, color, -1)

    # Label details
    label = f"ID {track.track_id} {track.class_name.upper()} {track.confidence:.2f}"
    cv2.putText(
        frame,
        label,
        (x1, max(20, y1 - 28)),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.5,
        color,
        2,
        cv2.LINE_AA,
    )

    # State details
    state_label = (
        f"STOP {track.stationary_seconds:.1f}s"
        if track.is_stopped
        else f"MOVE {track.movement_pixels:.1f}px"
    )
    cv2.putText(
        frame,
        state_label,
        (x1, max(20, y1 - 8)),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.5,
        color,
        2,
        cv2.LINE_AA,
    )

    # Status indicators below bounding box
    y_offset = y2 + 18
    if track.inside_no_parking_zone:
        cv2.putText(
            frame,
            "IN NO PARKING ZONE",
            (x1, y_offset),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.45,
            (0, 0, 255),
            1,
            cv2.LINE_AA,
        )
        y_offset += 16

    if is_violation and violation_label:
        cv2.putText(
            frame,
            f"VIOLATION: {violation_label.upper()}",
            (x1, y_offset),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (0, 0, 255),
            2,
            cv2.LINE_AA,
        )


def draw_panel(
    frame: np.ndarray,
    fps: float,
    traffic: Dict[str, Any],
    source: str,
    traffic_light_state: str = None,
    drawing_mode: bool = False,
    active_zone_type: str = "no_parking",
) -> None:
    return  # Disable panel drawing completely

    lines = [
        f"Source: {source}",
        f"FPS: {fps:.1f}",
        f"Objects: {traffic['vehicle_count']}",
        f"Stopped: {traffic['stopped_count']}",
        f"Traffic: {traffic['level']}",
    ]

    # Show speed & direction when CCTV analytics are available
    if "average_speed" in traffic:
        lines.append(f"Avg Speed: {traffic['average_speed']:.0f} px/s")
    if "dominant_direction" in traffic:
        lines.append(f"Direction: {traffic['dominant_direction']}")

    if traffic_light_state:
        lines.append(f"Light: {traffic_light_state.upper()}")

    if drawing_mode:
        lines.extend(
            [
                "--- DRAWING MODE ---",
                f"Active Type: {active_zone_type.upper()}",
                "L-Click: Add Point",
                "n: Save current zone",
                "r: Reset current zone",
                "w: Save to zones.yaml",
                "l: Reload zones.yaml",
                "1-6: Switch zone type",
            ]
        )
    else:
        lines.extend(
            [
                "q: Quit | s: Manual Snapshot",
                "d: Enter Zone Drawing Mode",
            ]
        )

    x, y = 15, 30
    line_h = 22
    panel_w = 320
    panel_h = line_h * len(lines) + 20

    cv2.rectangle(frame, (8, 8), (panel_w, panel_h), (20, 20, 20), -1)

    for i, line in enumerate(lines):
        color = (255, 255, 255)
        # Highlight drawing mode or violations in red/orange
        if "DRAWING MODE" in line:
            color = (0, 165, 255)
        elif "Light: RED" in line:
            color = (0, 0, 255)
        elif "Light: GREEN" in line:
            color = (0, 255, 0)

        cv2.putText(
            frame,
            line,
            (x, y + i * line_h),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            color,
            1,
            cv2.LINE_AA,
        )
