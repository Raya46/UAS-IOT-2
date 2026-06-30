def check_shoulder_lane(track, inside_shoulder: bool, dt: float, threshold: float = 2.0) -> bool:
    """
    Rule: Vehicle is moving inside the shoulder lane polygon for longer than the threshold.
    """
    if not hasattr(track, "shoulder_seconds"):
        track.shoulder_seconds = 0.0

    if inside_shoulder:
        # We only count moving vehicles to distinguish from illegal parking
        is_moving = not track.is_stopped
        if is_moving:
            track.shoulder_seconds += dt
        else:
            track.shoulder_seconds = 0.0
    else:
        track.shoulder_seconds = 0.0

    return track.shoulder_seconds >= threshold
