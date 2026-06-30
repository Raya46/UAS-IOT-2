import os
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import cv2
import numpy as np
from ultralytics import YOLO

from ai.utils.config import Config
from ai.detectors.sign_detector import SignDetector
from ai.detectors.plate_detector import PlateDetector
from ai.services.anpr_service import ANPRService
from ai.trackers.centroid_tracker import CentroidTracker
from ai.live_dashcam.road_section import RoadSectionAnalyzer


@dataclass
class DashcamDetection:
    class_name: str
    category: str
    confidence: float
    bbox: Tuple[int, int, int, int]
    center: Tuple[int, int]
    lane: Optional[str] = None
    plate_number: Optional[str] = None
    track_id: Optional[int] = None
    movement_pixels: float = 0.0


@dataclass
class TrafficLightState:
    color: str = "unknown"
    confidence: float = 0.0


@dataclass
class SceneAnalysis:
    vehicles: List[DashcamDetection] = field(default_factory=list)
    pedestrians: List[DashcamDetection] = field(default_factory=list)
    traffic_lights: List[DashcamDetection] = field(default_factory=list)
    traffic_signs: List[DashcamDetection] = field(default_factory=list)
    bicycles: List[DashcamDetection] = field(default_factory=list)
    total_objects: int = 0
    left_lane: List[List[int]] = field(default_factory=list)
    right_lane: List[List[int]] = field(default_factory=list)

    @property
    def vehicle_count(self) -> int:
        return len(self.vehicles)

    @property
    def pedestrian_count(self) -> int:
        return len(self.pedestrians)

    @property
    def traffic_light_state(self) -> TrafficLightState:
        for tl in self.traffic_lights:
            color = _classify_traffic_light_color(tl.class_name)
            if color != "unknown":
                return TrafficLightState(color=color, confidence=tl.confidence)
        return TrafficLightState()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "vehicle_count": self.vehicle_count,
            "pedestrian_count": self.pedestrian_count,
            "traffic_light_count": len(self.traffic_lights),
            "traffic_sign_count": len(self.traffic_signs),
            "bicycle_count": len(self.bicycles),
            "total_objects": self.total_objects,
            "traffic_light_state": self.traffic_light_state.color,
            "left_lane": self.left_lane,
            "right_lane": self.right_lane,
            "vehicles": [
                {
                    "class_name": v.class_name,
                    "confidence": round(v.confidence, 3),
                    "bbox": list(v.bbox),
                    "lane": v.lane,
                    "plate_number": v.plate_number,
                    "track_id": v.track_id,
                }
                for v in self.vehicles
            ],
            "pedestrians": [
                {
                    "class_name": p.class_name,
                    "confidence": round(p.confidence, 3),
                    "bbox": list(p.bbox),
                    "lane": p.lane,
                    "track_id": p.track_id,
                }
                for p in self.pedestrians
            ],
            "bicycles": [
                {
                    "class_name": b.class_name,
                    "confidence": round(b.confidence, 3),
                    "bbox": list(b.bbox),
                    "lane": b.lane,
                    "track_id": b.track_id,
                }
                for b in self.bicycles
            ],
            "traffic_lights": [
                {"class_name": t.class_name, "confidence": round(t.confidence, 3), "bbox": list(t.bbox)}
                for t in self.traffic_lights
            ],
            "traffic_signs": [
                {
                    "class_name": s.class_name,
                    "confidence": round(s.confidence, 3),
                    "bbox": list(s.bbox),
                }
                for s in self.traffic_signs
            ],
        }


_COCO_VEHICLE_CLASSES = {"car", "motorcycle", "bus", "truck"}
_COCO_PEDESTRIAN_CLASSES = {"person"}
_COCO_BICYCLE_CLASSES = {"bicycle"}
_COCO_TRAFFIC_LIGHT_CLASSES = {"traffic light", "traffic_light"}

# Custom-trained vehicle classes (angkot & transjakarta)
_CUSTOM_VEHICLE_CLASSES = {"angkot", "bus_transjakarta"}

_TRAFFIC_LIGHT_COLOR_MAP = {
    "traffic light red": "red",
    "traffic light green": "green",
    "traffic light yellow": "yellow",
    "traffic light orange": "yellow",
    "red": "red",
    "green": "green",
    "yellow": "yellow",
}

_OBJECT_CATEGORY_MAP: Dict[str, str] = {}
for cls in _COCO_VEHICLE_CLASSES:
    _OBJECT_CATEGORY_MAP[cls] = "vehicle"
for cls in _CUSTOM_VEHICLE_CLASSES:
    _OBJECT_CATEGORY_MAP[cls] = "vehicle"
for cls in _COCO_PEDESTRIAN_CLASSES:
    _OBJECT_CATEGORY_MAP[cls] = "pedestrian"
for cls in _COCO_BICYCLE_CLASSES:
    _OBJECT_CATEGORY_MAP[cls] = "bicycle"
for cls in _COCO_TRAFFIC_LIGHT_CLASSES:
    _OBJECT_CATEGORY_MAP[cls] = "traffic_light"

CATEGORY_COLORS = {
    "vehicle": (0, 255, 0),
    "angkot": (0, 200, 255),       # Orange-yellow for angkot
    "bus_transjakarta": (255, 100, 0),  # Blue-red for TransJakarta
    "pedestrian": (255, 255, 0),
    "bicycle": (255, 165, 0),
    "traffic_light": (0, 0, 255),
    "traffic_sign": (255, 0, 255),
    "unknown": (128, 128, 128),
}


def _classify_traffic_light_color(class_name: str) -> str:
    lower = class_name.lower().strip()
    for key, color in _TRAFFIC_LIGHT_COLOR_MAP.items():
        if key in lower or lower in key:
            return color
    return "unknown"


def _detect_traffic_light_color(crop: np.ndarray) -> str:
    if crop is None or crop.size == 0:
        return "unknown"
    try:
        hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
        h, w = crop.shape[:2]
        total = h * w
        if total == 0:
            return "unknown"

        lower_red1, upper_red1 = np.array([0, 50, 50]), np.array([10, 255, 255])
        lower_red2, upper_red2 = np.array([170, 50, 50]), np.array([180, 255, 255])
        mask_r1 = cv2.inRange(hsv, lower_red1, upper_red1)
        mask_r2 = cv2.inRange(hsv, lower_red2, upper_red2)
        red_pixels = cv2.countNonZero(mask_r1 | mask_r2)

        lower_green, upper_green = np.array([40, 40, 40]), np.array([80, 255, 255])
        mask_g = cv2.inRange(hsv, lower_green, upper_green)
        green_pixels = cv2.countNonZero(mask_g)

        lower_yellow, upper_yellow = np.array([15, 50, 50]), np.array([35, 255, 255])
        mask_y = cv2.inRange(hsv, lower_yellow, upper_yellow)
        yellow_pixels = cv2.countNonZero(mask_y)

        red_ratio = red_pixels / total
        green_ratio = green_pixels / total
        yellow_ratio = yellow_pixels / total

        if red_ratio > 0.15 and red_ratio > green_ratio and red_ratio > yellow_ratio:
            return "red"
        elif (
            green_ratio > 0.15
            and green_ratio > red_ratio
            and green_ratio > yellow_ratio
        ):
            return "green"
        elif (
            yellow_ratio > 0.15
            and yellow_ratio > red_ratio
            and yellow_ratio > green_ratio
        ):
            return "yellow"
        return "unknown"
    except Exception:
        return "unknown"


class DashcamDetector:
    def __init__(self, config: Optional[Config] = None):
        model_path = "models/yolov8s.pt"
        self.confidence = 0.35
        self.iou = 0.45

        if config is None:
            # Fallback to load config
            for candidate in ["ai/config.yaml", "config.yaml"]:
                if os.path.exists(candidate):
                    config = Config(candidate)
                    break

        self.config = config
        if self.config is not None:
            model_path = self.config.get("models.vehicle_model_path", model_path)
            self.confidence = float(self.config.get("detection.confidence", 0.35))
            self.iou = float(self.config.get("detection.iou", 0.45))

        print(f"[DASHCAM] Loading YOLO model: {model_path}")
        self.model = YOLO(model_path)
        self.names = self.model.names

        self.sign_detector = SignDetector(self.config)
        self.plate_detector = PlateDetector(self.config)
        self.anpr = ANPRService(self.config)
        self.tracker = CentroidTracker(self.config)
        self.road_analyzer = RoadSectionAnalyzer()

        # Custom models (angkot/transjakarta) disabled for dashcam —
        # they produce too many false positives on general dashcam footage.
        # Only used in CCTV mode on known busway corridors.
        self.custom_models = []

        self.frame_width = 960
        self.frame_height = 540
        self.frame_count = 0
        self.cached_left_lane = []
        self.cached_right_lane = []

        # Load Lane Segmentation Model
        self.lane_model = None
        self.use_lane_model = False
        if self.config is not None:
            self.use_lane_model = bool(self.config.get("models.use_lane_model", True))
            lane_model_path = self.config.get("models.lane_model_path", "models/yolov8m-lane-seg.pt")
            if self.use_lane_model and os.path.exists(lane_model_path):
                try:
                    print(f"[DASHCAM] Loading Lane YOLO model: {lane_model_path}")
                    self.lane_model = YOLO(lane_model_path)
                except Exception as exc:
                    print(f"[WARN] Failed to load lane segmentation model: {exc}")

    def set_frame_size(self, width: int, height: int) -> None:
        self.frame_width = width
        self.frame_height = height
        self.road_analyzer.set_frame_size(width, height)

    def detect(self, frame: np.ndarray, now: Optional[float] = None, dt: Optional[float] = None) -> SceneAnalysis:
        if frame is None or frame.size == 0:
            return SceneAnalysis()

        h, w = frame.shape[:2]
        self.set_frame_size(w, h)
        self.frame_count += 1

        if now is None:
            now = time.time()
        if dt is None:
            dt = 0.03

        # 1. Run YOLOv8s vehicle/person/bicycle/traffic_light detection
        results = self.model.predict(
            source=frame,
            conf=self.confidence,
            iou=self.iou,
            verbose=False,
        )

        detections = []
        traffic_lights = []
        if results and results[0].boxes is not None:
            result = results[0]
            for box in result.boxes:
                cls_id = int(box.cls[0])
                class_name = str(self.names.get(cls_id, cls_id)).lower()
                conf = float(box.conf[0])
                x1, y1, x2, y2 = box.xyxy[0].detach().cpu().numpy().astype(int).tolist()
                cx = (x1 + x2) // 2
                cy = (y1 + y2) // 2

                category = _OBJECT_CATEGORY_MAP.get(class_name, "unknown")
                if category in ["vehicle", "pedestrian", "bicycle"]:
                    from ai.trackers.tracker_interface import Detection as TrackerDetection
                    detections.append(TrackerDetection(
                        class_name=class_name,
                        confidence=conf,
                        bbox=(x1, y1, x2, y2),
                        center=(cx, cy)
                    ))
                elif category == "traffic_light":
                    crop = frame[max(0, y1):min(h, y2), max(0, x1):min(w, x2)]
                    color = _detect_traffic_light_color(crop)
                    final_class = f"traffic light {color}" if color != "unknown" else class_name
                    
                    traffic_lights.append(DashcamDetection(
                        class_name=final_class,
                        category="traffic_light",
                        confidence=conf,
                        bbox=(x1, y1, x2, y2),
                        center=(cx, cy)
                    ))

        # 1b. Run custom models (angkot, transjakarta) — higher conf to reduce false positives
        for custom_model in self.custom_models:
            try:
                custom_results = custom_model.predict(
                    source=frame,
                    conf=0.70,
                    iou=self.iou,
                    verbose=False,
                )
                if custom_results and custom_results[0].boxes is not None:
                    c_result = custom_results[0]
                    c_names = custom_model.names
                    for box in c_result.boxes:
                        cls_id = int(box.cls[0])
                        class_name = str(c_names.get(cls_id, cls_id)).lower()
                        conf = float(box.conf[0])
                        x1, y1, x2, y2 = box.xyxy[0].detach().cpu().numpy().astype(int).tolist()
                        cx = (x1 + x2) // 2
                        cy = (y1 + y2) // 2
                        from ai.trackers.tracker_interface import Detection as TrackerDetection
                        detections.append(TrackerDetection(
                            class_name=class_name,
                            confidence=conf,
                            bbox=(x1, y1, x2, y2),
                            center=(cx, cy)
                        ))
            except Exception as exc:
                print(f"[DASHCAM] Custom model error: {exc}")

        # Update Centroid Tracker
        tracks = self.tracker.update(detections, now, dt)

        analysis = SceneAnalysis()
        analysis.traffic_lights = traffic_lights

        # Process each tracked object
        for track in tracks:
            lane = self.road_analyzer.classify_bbox(track.bbox)
            category = _OBJECT_CATEGORY_MAP.get(track.class_name, "unknown")

            plate_number = None
            # NOTE: Plate OCR disabled for dashcam mode — moving camera
            # produces unreliable OCR results. Only enabled for CCTV.

            det = DashcamDetection(
                class_name=track.class_name,
                category=category,
                confidence=track.confidence,
                bbox=track.bbox,
                center=track.center,
                lane=lane,
                plate_number=plate_number,
                track_id=track.track_id,
                movement_pixels=getattr(track, 'movement_pixels', 0.0),
            )

            if category == "vehicle":
                analysis.vehicles.append(det)
            elif category == "pedestrian":
                analysis.pedestrians.append(det)
            elif category == "bicycle":
                analysis.bicycles.append(det)

        # 2. Run Sign Detector
        sign_detections = self.sign_detector.detect_signs(frame)
        for sign in sign_detections:
            sx1, sy1, sx2, sy2 = sign["bbox"]
            analysis.traffic_signs.append(
                DashcamDetection(
                    class_name=sign["class_name"],
                    category="traffic_sign",
                    confidence=sign["confidence"],
                    bbox=(sx1, sy1, sx2, sy2),
                    center=((sx1 + sx2) // 2, (sy1 + sy2) // 2),
                )
            )

        # 3. Dynamic Lane Detection (fit Left & Right Curves)
        lane_interval = 10
        if self.config is not None:
            lane_interval = int(self.config.get("models.lane_process_interval_frames", 10))

        run_lane_seg = self.use_lane_model and self.lane_model is not None and (self.frame_count % lane_interval == 0 or not self.cached_left_lane)
        
        if run_lane_seg:
            try:
                results_lane = self.lane_model(frame, device="cpu", verbose=False)
                if results_lane and len(results_lane) > 0 and results_lane[0].masks is not None:
                    res = results_lane[0]
                    masks = res.masks.data.cpu().numpy()
                    classes = res.boxes.cls.cpu().numpy()
                    
                    left_pts_x, left_pts_y = [], []
                    right_pts_x, right_pts_y = [], []
                    mask_h, mask_w = masks.shape[1:3]
                    scale_y, scale_x = h / mask_h, w / mask_w
                    
                    for i, cls in enumerate(classes):
                        if int(cls) == 0:  # Class 0 represents lane solid boundary
                            mask = masks[i]
                            ys, xs = np.where(mask > 0.5)
                            if len(xs) > 0:
                                orig_xs = xs * scale_x
                                orig_ys = ys * scale_y
                                mean_x = np.mean(orig_xs)
                                if mean_x < w / 2:
                                    left_pts_x.extend(orig_xs)
                                    left_pts_y.extend(orig_ys)
                                else:
                                    right_pts_x.extend(orig_xs)
                                    right_pts_y.extend(orig_ys)
                                    
                    roi_y1 = int(h * 0.45)
                    target_y = np.linspace(roi_y1, h - 20, 20)
                    
                    left_lane_points = []
                    if len(left_pts_x) >= 15:
                        left_fit = np.polyfit(left_pts_y, left_pts_x, 2)
                        left_fitx = left_fit[0] * target_y**2 + left_fit[1] * target_y + left_fit[2]
                        left_lane_points = [[int(x), int(y)] for x, y in zip(left_fitx, target_y) if 0 <= x < w]
                        
                    right_lane_points = []
                    if len(right_pts_x) >= 15:
                        right_fit = np.polyfit(right_pts_y, right_pts_x, 2)
                        right_fitx = right_fit[0] * target_y**2 + right_fit[1] * target_y + right_fit[2]
                        right_lane_points = [[int(x), int(y)] for x, y in zip(right_fitx, target_y) if 0 <= x < w]
                        
                    # Prevent crossing
                    if left_lane_points and right_lane_points:
                        for i in range(min(len(left_lane_points), len(right_lane_points))):
                            if left_lane_points[i][0] >= right_lane_points[i][0] - 10:
                                mid = (left_lane_points[i][0] + right_lane_points[i][0]) / 2
                                left_lane_points[i][0] = int(mid - 5)
                                right_lane_points[i][0] = int(mid + 5)
                                
                    self.cached_left_lane = left_lane_points
                    self.cached_right_lane = right_lane_points
            except Exception as exc:
                print(f"[WARN] Dashcam lane segmentation failed: {exc}")

        # Fallback to defaults from RoadSectionAnalyzer
        if not self.cached_left_lane and self.road_analyzer.left_lane_zone:
            pts = self.road_analyzer.left_lane_zone
            self.cached_left_lane = [pts[1], pts[2]]
        if not self.cached_right_lane and self.road_analyzer.right_lane_zone:
            pts = self.road_analyzer.right_lane_zone
            self.cached_right_lane = [pts[0], pts[3]]

        analysis.left_lane = self.cached_left_lane
        analysis.right_lane = self.cached_right_lane

        analysis.total_objects = (
            len(analysis.vehicles)
            + len(analysis.pedestrians)
            + len(analysis.bicycles)
            + len(analysis.traffic_lights)
            + len(analysis.traffic_signs)
        )

        return analysis

    def draw_detections(self, frame: np.ndarray, analysis: SceneAnalysis) -> None:
        # Ensure frame is writeable
        if not frame.flags.writeable:
            try:
                frame.setflags(write=True)
            except ValueError:
                frame = np.ascontiguousarray(frame)
                frame.setflags(write=True)

        h, w = frame.shape[:2]

        # Scale factor: detection was done at self.frame_width x self.frame_height
        # but we may be drawing on a different sized frame
        sx = w / max(1, self.frame_width)
        sy = h / max(1, self.frame_height)

        def scale_bbox(bbox):
            x1, y1, x2, y2 = bbox
            return (int(x1 * sx), int(y1 * sy), int(x2 * sx), int(y2 * sy))

        def scale_point(pt):
            return (int(pt[0] * sx), int(pt[1] * sy))

        def scale_lane(lane_pts):
            return [[int(p[0] * sx), int(p[1] * sy)] for p in lane_pts]

        # ═══════════════════════════════════════════════════
        # 1. Draw Road Surface / Lane Zone Overlay
        # ═══════════════════════════════════════════════════
        overlay = frame.copy()

        # Draw lane zone polygons (semi-transparent fill) — these are in display coords already
        if self.road_analyzer.left_lane_zone:
            scaled_zone = scale_lane(self.road_analyzer.left_lane_zone)
            pts = np.array(scaled_zone, dtype=np.int32)
            cv2.fillPoly(overlay, [pts], (0, 180, 0))
        if self.road_analyzer.right_lane_zone:
            scaled_zone = scale_lane(self.road_analyzer.right_lane_zone)
            pts = np.array(scaled_zone, dtype=np.int32)
            cv2.fillPoly(overlay, [pts], (180, 120, 0))

        # Fill road surface between detected lane boundaries
        left_scaled = scale_lane(analysis.left_lane) if analysis.left_lane else []
        right_scaled = scale_lane(analysis.right_lane) if analysis.right_lane else []

        if left_scaled and right_scaled and len(left_scaled) > 2 and len(right_scaled) > 2:
            road_polygon = np.array(left_scaled + list(reversed(right_scaled)), dtype=np.int32)
            cv2.fillPoly(overlay, [road_polygon], (60, 60, 60))

        cv2.addWeighted(overlay, 0.2, frame, 0.8, 0, frame)

        # ═══════════════════════════════════════════════════
        # 2. Draw Dynamic Lane Lines (from YOLO lane-seg)
        # ═══════════════════════════════════════════════════
        if left_scaled and len(left_scaled) > 1:
            pts = np.array(left_scaled, dtype=np.int32).reshape((-1, 1, 2))
            cv2.polylines(frame, [pts], False, (0, 255, 255), 3, cv2.LINE_AA)
            for i in range(0, len(left_scaled) - 1, 2):
                p1 = tuple(left_scaled[i])
                p2 = tuple(left_scaled[min(i + 1, len(left_scaled) - 1)])
                cv2.line(frame, p1, p2, (255, 255, 255), 1, cv2.LINE_AA)

        if right_scaled and len(right_scaled) > 1:
            pts = np.array(right_scaled, dtype=np.int32).reshape((-1, 1, 2))
            cv2.polylines(frame, [pts], False, (0, 255, 255), 3, cv2.LINE_AA)
            for i in range(0, len(right_scaled) - 1, 2):
                p1 = tuple(right_scaled[i])
                p2 = tuple(right_scaled[min(i + 1, len(right_scaled) - 1)])
                cv2.line(frame, p1, p2, (255, 255, 255), 1, cv2.LINE_AA)

        # Center divider between lanes
        if left_scaled and right_scaled:
            min_len = min(len(left_scaled), len(right_scaled))
            center_pts = []
            for i in range(min_len):
                cx = (left_scaled[i][0] + right_scaled[i][0]) // 2
                cy = (left_scaled[i][1] + right_scaled[i][1]) // 2
                center_pts.append([cx, cy])
            if len(center_pts) > 1:
                for i in range(0, len(center_pts) - 1, 3):
                    j = min(i + 1, len(center_pts) - 1)
                    cv2.line(frame, tuple(center_pts[i]), tuple(center_pts[j]), (0, 200, 255), 2, cv2.LINE_AA)

        # Lane labels
        if left_scaled and len(left_scaled) > 5:
            mid_idx = len(left_scaled) // 2
            lx, ly = left_scaled[mid_idx]
            cv2.putText(frame, "L", (max(lx - 20, 5), ly), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2, cv2.LINE_AA)
        if right_scaled and len(right_scaled) > 5:
            mid_idx = len(right_scaled) // 2
            rx, ry = right_scaled[mid_idx]
            cv2.putText(frame, "R", (min(rx + 5, w - 20), ry), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2, cv2.LINE_AA)

        # ═══════════════════════════════════════════════════
        # 3. Draw Vehicle / Pedestrian / Bicycle / etc Detections
        # ═══════════════════════════════════════════════════
        for det in (
            analysis.vehicles
            + analysis.pedestrians
            + analysis.bicycles
            + analysis.traffic_lights
            + analysis.traffic_signs
        ):
            # Use specific color for angkot/transjakarta, fallback to category color
            color = CATEGORY_COLORS.get(det.class_name, CATEGORY_COLORS.get(det.category, CATEGORY_COLORS["unknown"]))
            x1, y1, x2, y2 = scale_bbox(det.bbox)
            center = scale_point(det.center)

            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
            cv2.circle(frame, center, 3, color, -1)

            label = f"{det.class_name} {det.confidence:.2f}"
            if det.track_id is not None:
                label = f"ID {det.track_id} {label}"
            if det.lane:
                label += f" [{det.lane}]"
            if getattr(det, 'plate_number', None):
                label += f" ({det.plate_number})"

            (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.45, 2)
            cv2.rectangle(frame, (x1, y1 - th - 6), (x1 + tw, y1), color, -1)
            cv2.putText(
                frame,
                label,
                (x1, y1 - 4),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.45,
                (0, 0, 0),
                1,
                cv2.LINE_AA
            )

    def draw_scene_panel(
        self, frame: np.ndarray, analysis: SceneAnalysis, fps: float, source: str
    ) -> None:
        tl_state = analysis.traffic_light_state

        lines = [
            f"Dashcam: {source}",
            f"FPS: {fps:.1f}",
            f"Vehicles: {analysis.vehicle_count}",
            f"Pedestrians: {analysis.pedestrian_count}",
            f"Bicycles: {len(analysis.bicycles)}",
            f"Traffic Lights: {len(analysis.traffic_lights)}",
            f"Traffic Signs: {len(analysis.traffic_signs)}",
            f"Light State: {tl_state.color.upper()}",
        ]

        x, y = 15, 30
        line_h = 22
        panel_w = 300
        panel_h = line_h * len(lines) + 20

        cv2.rectangle(frame, (8, 8), (panel_w, panel_h), (20, 20, 20), -1)

        for i, line in enumerate(lines):
            text_color = (255, 255, 255)
            if "Light State:" in line:
                if "RED" in line:
                    text_color = (0, 0, 255)
                elif "GREEN" in line:
                    text_color = (0, 255, 0)
                elif "YELLOW" in line:
                    text_color = (0, 255, 255)
            cv2.putText(
                frame,
                line,
                (x, y + i * line_h),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                text_color,
                1,
            )
