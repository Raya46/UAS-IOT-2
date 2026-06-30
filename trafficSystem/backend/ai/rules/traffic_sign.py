from ai.trackers.tracker_interface import Track


def check_traffic_sign_violation(
    track: Track,
    inside_sign_zone: bool,
    sign_detected: bool = False,
    min_history_points: int = 8,
    min_horizontal_delta: float = 35.0,
    max_vertical_delta: float = 220.0,
    min_path_delta: float = 25.0,
) -> bool:
    """
    Rule for a no-right-turn / prohibited-turn sign violation.
    Triggers if vehicle is inside the sign zone ROI OR the physical traffic sign is detected.
    A violation is raised when its trajectory shows a clear rightward turn/move.
    """
    active = inside_sign_zone or sign_detected
    if not active or len(track.history) < min_history_points:
        return False

    if getattr(track, "traffic_sign_violation_triggered", False):
        return False

    start_x, start_y = track.history[0]
    end_x, end_y = track.history[-1]
    dx = float(end_x - start_x)
    dy = float(end_y - start_y)

    moved_enough = (dx * dx + dy * dy) ** 0.5 >= min_path_delta
    rightward_turn = dx >= min_horizontal_delta and abs(dy) <= max_vertical_delta

    if rightward_turn or moved_enough:
        track.traffic_sign_violation_triggered = True
        return True

    return False
