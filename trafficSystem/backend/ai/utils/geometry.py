from typing import List, Tuple
import cv2
import numpy as np

Point = Tuple[int, int]

def point_inside_polygon(point: Point, polygon: List[List[int]]) -> bool:
    if not polygon or len(polygon) < 3:
        return False
    contour = np.array(polygon, dtype=np.int32)
    return cv2.pointPolygonTest(contour, (float(point[0]), float(point[1])), False) >= 0
