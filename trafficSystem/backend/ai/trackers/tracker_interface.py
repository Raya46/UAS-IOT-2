from dataclasses import dataclass
from typing import Tuple

Point = Tuple[int, int]
BBox = Tuple[int, int, int, int]

@dataclass
class Detection:
    class_name: str
    confidence: float
    bbox: BBox
    center: Point

@dataclass
class Track:
    track_id: int
    class_name: str
    confidence: float
    bbox: BBox
    center: Point
    last_center: Point
    first_seen_at: float
    last_seen_at: float
    stationary_seconds: float = 0.0
    is_stopped: bool = False
    inside_no_parking_zone: bool = False
    has_saved_violation: bool = False
    last_violation_at: float = 0.0
    movement_pixels: float = 0.0
    matched: bool = False
    
    # Trajectory tracking for rules like U-turn and red-light
    history: list = None
    
    def __post_init__(self):
        if self.history is None:
            self.history = [self.center]
        self.plate_history = []  # List of dicts: {"text": str, "conf": float, "crop": np.ndarray}
        self.stop_anchor = None
