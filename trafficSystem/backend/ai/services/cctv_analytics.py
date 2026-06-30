import json
import numpy as np
import cv2
from datetime import datetime
from typing import List, Dict, Any, Tuple, Set
from ai.trackers.tracker_interface import Track
from ai.utils.config import Config
from ai.utils.geometry import point_inside_polygon
from app.services.redis_client import redis_set_json


def ccw(A: Tuple[int, int], B: Tuple[int, int], C: Tuple[int, int]) -> bool:
    """Helper to check counter-clockwise order of three points."""
    return (C[1] - A[1]) * (B[0] - A[0]) > (B[1] - A[1]) * (C[0] - A[0])


def line_intersection(
    A: Tuple[int, int], B: Tuple[int, int], C: Tuple[int, int], D: Tuple[int, int]
) -> bool:
    """Checks if line segment AB intersects line segment CD."""
    return ccw(A, C, D) != ccw(B, C, D) and ccw(A, B, C) != ccw(A, B, D)


class CCTVAnalytics:
    def __init__(self, config: Config):
        self.config = config
        self.counted_tracks: Set[Tuple[int, str]] = set()  # (track_id, line_id)

        # Count storage: {line_id: {direction: {vehicle_class: count}}}
        self.counts: Dict[str, Dict[str, Dict[str, int]]] = {}

        # Load counting lines from config
        self.counting_lines = config.get("counting_lines", [])
        for line in self.counting_lines:
            line_id = line["id"]
            self.counts[line_id] = {"forward": {}, "backward": {}}

        # Load parking spots from config
        self.parking_spots = config.get("parking_spots", [])
        self.spot_occupancy: Dict[str, Dict[str, Any]] = {}
        for spot in self.parking_spots:
            self.spot_occupancy[spot["id"]] = {
                "occupied": False,
                "vehicle_id": None,
                "vehicle_type": None,
            }

    def process_traffic_counting(self, tracks: List[Track]) -> Dict[str, Any]:
        """
        Evaluates active tracks against virtual counting lines and updates counts.
        """
        for track in tracks:
            if len(track.history) < 2:
                continue

            # Previous position and current position
            A = track.last_center
            B = track.center

            for line in self.counting_lines:
                line_id = line["id"]
                line_points = line["points"]
                if len(line_points) < 2:
                    continue

                C = tuple(line_points[0])
                D = tuple(line_points[1])

                # Check for crossing
                if (track.track_id, line_id) not in self.counted_tracks:
                    if line_intersection(A, B, C, D):
                        # Determine direction using vector math
                        # Vector CD (counting line)
                        cd_dx = D[0] - C[0]
                        cd_dy = D[1] - C[1]

                        # Vector AB (vehicle movement)
                        ab_dx = B[0] - A[0]
                        ab_dy = B[1] - A[1]

                        # Cross product to determine crossing direction
                        cross_product = ab_dx * cd_dy - ab_dy * cd_dx

                        # Set default direction based on cross product sign
                        if cross_product > 0:
                            direction = "forward"
                        else:
                            direction = "backward"

                        # Update counter
                        v_type = track.class_name
                        self.counts[line_id][direction][v_type] = (
                            self.counts[line_id][direction].get(v_type, 0) + 1
                        )
                        self.counted_tracks.add((track.track_id, line_id))

                        print(
                            f"[CCTV COUNT] Vehicle {v_type} #{track.track_id} crossed {line_id} in {direction} direction."
                        )

        # Prepare summary count
        summary = {}
        for line_id, dirs in self.counts.items():
            line_sum = {}
            for direction, classes in dirs.items():
                total = sum(classes.values())
                line_sum[direction] = {"total": total, "classes": classes}
            summary[line_id] = line_sum

        # Save to Redis
        redis_set_json("traffic:counts", summary, ttl=300)

        return summary

    def estimate_density(
        self, tracks: List[Track], dt: float = 0.033
    ) -> Dict[str, Any]:
        """
        Estimates real-time traffic density, average vehicle speed, queue length, and dominant direction.
        """
        vehicles = [t for t in tracks if t.class_name != "person"]
        vehicle_count = len(vehicles)
        stopped_count = sum(1 for t in vehicles if t.is_stopped)
        stopped_ratio = stopped_count / vehicle_count if vehicle_count > 0 else 0.0

        # Calculate average speed in pixels per second
        speeds = []
        for t in vehicles:
            if dt > 0:
                # speed = movement in pixels / time elapsed
                speed = t.movement_pixels / dt
                speeds.append(speed)

        avg_speed = np.mean(speeds) if speeds else 0.0

        # Determine Congestion / Density Level based on both Vehicle Count and Average Speed
        if vehicle_count == 0:
            level = "FREE FLOW"
        else:
            # If average speed is extremely low (< 50 px/s) and there are at least 4 vehicles
            if avg_speed < 50.0 and vehicle_count >= 4:
                level = "TRAFFIC JAM"
            # If multiple vehicles are stopped together and there are at least 3 vehicles
            elif stopped_ratio >= 0.5 and vehicle_count >= 3:
                level = "TRAFFIC JAM"
            # If average speed is slow (< 90 px/s) and there are at least 8 vehicles
            elif avg_speed < 90.0 and vehicle_count >= 8:
                level = "TRAFFIC JAM"
            # If vehicle count is high or speed is moderate-low
            elif vehicle_count >= 15 or (vehicle_count >= 8 and avg_speed < 120.0):
                level = "HEAVY TRAFFIC"
            elif vehicle_count >= 6:
                level = "MODERATE"
            else:
                level = "FREE FLOW"

        # Calculate average movement direction angle
        moving_tracks = [
            t for t in vehicles if not t.is_stopped and len(t.history) >= 2
        ]
        angles = []
        for t in moving_tracks:
            dx = t.center[0] - t.last_center[0]
            dy = t.center[1] - t.last_center[1]
            if dx != 0 or dy != 0:
                angle = (
                    np.arctan2(-dy, dx) * 180 / np.pi
                )  # Invert dy to match standard Cartesian coordinates
                angles.append(angle if angle >= 0 else angle + 360)

        dominant_dir = "STATIONARY"
        if angles:
            avg_angle = np.mean(angles)
            # Map angle to cardinal directions
            if 45 <= avg_angle < 135:
                dominant_dir = "NORTH"
            elif 135 <= avg_angle < 225:
                dominant_dir = "WEST"
            elif 225 <= avg_angle < 315:
                dominant_dir = "SOUTH"
            else:
                dominant_dir = "EAST"

        metrics = {
            "vehicle_count": vehicle_count,
            "stopped_vehicle_count": stopped_count,
            "queue_length_estimate": stopped_count,  # Approximate metric
            "density_level": level,
            "average_speed": round(float(avg_speed), 2),
            "dominant_direction": dominant_dir,
            "timestamp": datetime.now().isoformat(),
        }

        # Save to Redis
        redis_set_json("traffic:metrics", metrics, ttl=300)

        return metrics

    def detect_wrong_direction(
        self, tracks: List[Track], expected_directions: Dict[str, str]
    ) -> List[Tuple[int, str]]:
        """
        Checks if vehicle is driving in the wrong direction of a configured lane zone.
        expected_directions maps zone_id -> direction string ('upward', 'downward', 'leftward', 'rightward')
        Returns list of (track_id, zone_id) that violate the rule.
        """
        violations = []
        for track in tracks:
            if len(track.history) < 5:
                continue

            # Check movement direction over last 5 frames
            start_pt = track.history[-5]
            end_pt = track.center

            dx = end_pt[0] - start_pt[0]
            dy = end_pt[1] - start_pt[1]

            for zone_id, expected in expected_directions.items():
                # For simplified logic: check if track center is inside
                # (We will use the actual zone manager in the main loop, here we verify movement direction)

                is_wrong = False
                if expected == "downward" and dy < -4:  # Moving upward (decreasing y)
                    is_wrong = True
                elif expected == "upward" and dy > 4:  # Moving downward (increasing y)
                    is_wrong = True
                elif (
                    expected == "leftward" and dx > 4
                ):  # Moving rightward (increasing x)
                    is_wrong = True
                elif (
                    expected == "rightward" and dx < -4
                ):  # Moving leftward (decreasing x)
                    is_wrong = True

                if is_wrong:
                    violations.append((track.track_id, zone_id))

        return violations

    def update_parking_spots(self, tracks: List[Track]) -> Dict[str, Any]:
        """
        Evaluates parking spot occupancy by checking if any vehicle overlaps with the spot polygon.
        """
        # Reset spot occupancy
        for spot_id in self.spot_occupancy:
            self.spot_occupancy[spot_id] = {
                "occupied": False,
                "vehicle_id": None,
                "vehicle_type": None,
            }

        # Check occupancy
        for spot in self.parking_spots:
            spot_id = spot["id"]
            spot_pts = spot["points"]

            for track in tracks:
                if track.class_name == "person":
                    continue
                # Use vehicle bottom center for spot overlap test
                # BBox is (x1, y1, x2, y2)
                bottom_center = (track.center[0], track.bbox[3])

                if point_inside_polygon(bottom_center, spot_pts):
                    self.spot_occupancy[spot_id] = {
                        "occupied": True,
                        "vehicle_id": track.track_id,
                        "vehicle_type": track.class_name,
                    }
                    break  # Spot occupied, move to next spot

        # Prepare summary
        total_spots = len(self.parking_spots)
        occupied_count = sum(
            1 for spot in self.spot_occupancy.values() if spot["occupied"]
        )
        free_count = total_spots - occupied_count
        percentage = (occupied_count / total_spots * 100.0) if total_spots > 0 else 0.0

        summary = {
            "total_spots": total_spots,
            "occupied_spots": occupied_count,
            "free_spots": free_count,
            "occupancy_percentage": round(percentage, 1),
            "spots": self.spot_occupancy,
            "timestamp": datetime.now().isoformat(),
        }

        # Save to Redis
        redis_set_json("traffic:parking", summary, ttl=300)

        return summary

    def draw_analytics(self, frame: np.ndarray) -> None:
        """Draws virtual counting lines and parking spots on the frame."""
        # Draw counting lines
        for line in self.counting_lines:
            line_points = line["points"]
            if len(line_points) >= 2:
                p1 = tuple(line_points[0])
                p2 = tuple(line_points[1])
                cv2.line(frame, p1, p2, (255, 128, 0), 3)
                cv2.putText(
                    frame,
                    f"Count Line: {line['name']}",
                    (p1[0], p1[1] - 8),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.5,
                    (255, 128, 0),
                    2,
                    cv2.LINE_AA,
                )

        # Draw parking spots
        for spot in self.parking_spots:
            spot_id = spot["id"]
            pts = np.array(spot["points"], dtype=np.int32)
            occupied = self.spot_occupancy.get(spot_id, {}).get("occupied", False)
            color = (0, 0, 255) if occupied else (0, 255, 0)

            cv2.polylines(frame, [pts], True, color, 2)
            p_label = spot["points"][0]
            status_text = "OCCUPIED" if occupied else "FREE"
            cv2.putText(
                frame,
                f"Spot {spot_id}: {status_text}",
                (int(p_label[0]), int(p_label[1]) - 8),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.45,
                color,
                1,
                cv2.LINE_AA,
            )
