from ai.trackers.tracker_interface import Track

def check_unsafe_lane_change(track: Track, inside_lane_a: bool, inside_lane_b: bool, now: float, max_transition_seconds: float = 3.0) -> bool:
    """
    Rule: Vehicle moves from lane_a to lane_b (or vice versa) in a duration less than max_transition_seconds.
    """
    if not hasattr(track, "last_seen_lane"):
        track.last_seen_lane = None
        track.lane_change_timestamp = 0.0

    violation_triggered = False

    if inside_lane_a:
        if track.last_seen_lane == "lane_b":
            transition_time = now - track.lane_change_timestamp
            if transition_time <= max_transition_seconds:
                violation_triggered = True
        track.last_seen_lane = "lane_a"
        track.lane_change_timestamp = now

    elif inside_lane_b:
        if track.last_seen_lane == "lane_a":
            transition_time = now - track.lane_change_timestamp
            if transition_time <= max_transition_seconds:
                violation_triggered = True
        track.last_seen_lane = "lane_b"
        track.lane_change_timestamp = now

    return violation_triggered
