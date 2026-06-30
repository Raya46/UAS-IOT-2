import numpy as np
from ai.trackers.tracker_interface import Track

def check_illegal_u_turn(track: Track, inside_u_turn_zone: bool, min_history_points: int = 15) -> bool:
    """
    Rule: Vehicle enters the u-turn forbidden zone, and its trajectory direction
    changes by approximately 120 to 180 degrees.
    """
    if not inside_u_turn_zone:
        return False

    history = track.history
    if len(history) < min_history_points:
        return False

    # Extract start, middle, and end points of the trajectory
    p_start = history[0]
    p_mid = history[len(history) // 2]
    p_end = history[-1]

    # Calculate vectors
    v1 = np.array([p_mid[0] - p_start[0], p_mid[1] - p_start[1]], dtype=float)
    v2 = np.array([p_end[0] - p_mid[0], p_end[1] - p_mid[1]], dtype=float)

    norm_v1 = np.linalg.norm(v1)
    norm_v2 = np.linalg.norm(v2)

    # Avoid division by zero and tiny movements (noise)
    if norm_v1 < 15 or norm_v2 < 15:
        return False

    # Calculate angle between the two motion vectors
    dot_product = np.dot(v1, v2)
    cos_angle = np.clip(dot_product / (norm_v1 * norm_v2), -1.0, 1.0)
    angle_deg = np.degrees(np.arccos(cos_angle))

    # For U-turn, vectors v1 and v2 point in opposite directions, so the angle
    # between them is between 120 and 180 degrees.
    return 120.0 <= angle_deg <= 180.0
