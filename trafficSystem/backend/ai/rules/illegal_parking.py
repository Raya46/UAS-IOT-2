from ai.trackers.tracker_interface import Track
from ai.utils.geometry import point_inside_polygon

def is_public_transport(class_name: str) -> bool:
    """Checks if the vehicle class name belongs to Jakarta public transit."""
    return class_name in {
        "jaklingko",
        "angkot_merah",
        "angkot_hijau",
        "angkot_biru",
        "transjakarta",
        "metrotrans",
    }

def check_stop_area_context(track: Track, stop_area_zones: list) -> bool:
    """
    Checks if a public transport vehicle is stopping in a valid JakLingko stop area.
    If yes, it is classified as a normal stop.
    """
    if not is_public_transport(track.class_name):
        return False
        
    for zone in stop_area_zones:
        # Support both zone dictionaries and raw points lists
        points = zone["points"] if isinstance(zone, dict) else zone
        if point_inside_polygon(track.center, points):
            return True
            
    return False

def check_illegal_parking(track: Track, zone_points: list, illegal_parking_seconds: float) -> bool:
    """
    Standard Rule: Vehicle is stopped inside the no-parking polygon for longer than the threshold.
    """
    if not zone_points:
        return False
    return (
        track.inside_no_parking_zone
        and track.stationary_seconds >= illegal_parking_seconds
    )

def check_cctv_parking_violation(track: Track, static_confirm_seconds: float, is_traffic_jam: bool = False) -> bool:
    """CCTV Rule: Vehicle remains stationary in no-parking zone for static_confirm_seconds."""
    if is_traffic_jam:
        return False
    return track.inside_no_parking_zone and track.stationary_seconds >= static_confirm_seconds

def check_moving_parking_violation(track: Track, moving_camera_potential_seconds: float) -> bool:
    """Moving Camera Rule: Vehicle appears stopped/stationary for moving_camera_potential_seconds."""
    # For a moving camera, even a brief stop (e.g. 1-2 seconds) indicates a potential illegal parking candidate.
    return track.inside_no_parking_zone and track.stationary_seconds >= moving_camera_potential_seconds
