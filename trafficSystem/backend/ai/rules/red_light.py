def check_red_light(track, inside_stop_line: bool, traffic_light_state: str) -> bool:
    """
    Rule: Traffic light is red, and the vehicle enters/crosses the stop line zone.
    """
    if traffic_light_state != "red":
        return False

    if not hasattr(track, "was_inside_stop_line"):
        track.was_inside_stop_line = False

    crossed = False
    # Detects the transition of entering the stop line zone
    if inside_stop_line and not track.was_inside_stop_line:
        crossed = True

    track.was_inside_stop_line = inside_stop_line
    return crossed
