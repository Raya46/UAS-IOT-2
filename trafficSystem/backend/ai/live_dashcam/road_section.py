from typing import List, Optional, Tuple

import numpy as np


class RoadSectionAnalyzer:
    def __init__(self, frame_width: int = 960, frame_height: int = 540):
        self.frame_width = frame_width
        self.frame_height = frame_height

        self.left_lane_zone: Optional[List[List[int]]] = None
        self.right_lane_zone: Optional[List[List[int]]] = None

        self._build_default_zones()

    def _build_default_zones(self) -> None:
        w, h = self.frame_width, self.frame_height
        horizon_y = int(h * 0.45)
        bottom_y = h

        center_x = w // 2
        margin = int(w * 0.08)

        self.left_lane_zone = [
            [margin, horizon_y],
            [center_x - 10, horizon_y],
            [center_x - 20, bottom_y],
            [margin + 20, bottom_y],
        ]
        self.right_lane_zone = [
            [center_x + 10, horizon_y],
            [w - margin, horizon_y],
            [w - margin - 20, bottom_y],
            [center_x + 20, bottom_y],
        ]

    def set_zones_from_config(
        self, left_polygon: List[List[int]], right_polygon: List[List[int]]
    ) -> None:
        self.left_lane_zone = left_polygon
        self.right_lane_zone = right_polygon

    def set_frame_size(self, width: int, height: int) -> None:
        if width != self.frame_width or height != self.frame_height:
            self.frame_width = width
            self.frame_height = height
            self._build_default_zones()

    def classify_point(self, point: Tuple[int, int]) -> Optional[str]:
        if self.left_lane_zone and self._point_in_polygon(point, self.left_lane_zone):
            return "left"
        if self.right_lane_zone and self._point_in_polygon(point, self.right_lane_zone):
            return "right"
        return None

    def classify_bbox(self, bbox: Tuple[int, int, int, int]) -> Optional[str]:
        x1, y1, x2, y2 = bbox
        cx = (x1 + x2) // 2
        cy = (y1 + y2) // 2
        return self.classify_point((cx, cy))

    def draw_zones(self, frame: np.ndarray) -> None:
        pass

    @staticmethod
    def _point_in_polygon(point: Tuple[int, int], polygon: List[List[int]]) -> bool:
        x, y = point
        n = len(polygon)
        inside = False
        j = n - 1
        for i in range(n):
            yi, yj = polygon[i][1], polygon[j][1]
            xi, xj = polygon[i][0], polygon[j][0]
            if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi) + xi):
                inside = not inside
            j = i
        return inside
