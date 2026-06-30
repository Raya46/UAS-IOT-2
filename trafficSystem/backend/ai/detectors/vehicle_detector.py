from typing import List
import numpy as np
import cv2
from ultralytics import YOLO
from ai.utils.config import Config
from ai.trackers.tracker_interface import Detection

class VehicleDetector:
    def __init__(self, config: Config):
        model_path = config.get("models.vehicle_model_path", "models/yolov8s.pt")
        self.confidence = float(config.get("detection.confidence", 0.35))
        self.iou = float(config.get("detection.iou", 0.45))
        self.allowed_classes = set(config.get("detection.allowed_classes", []))
        
        print(f"[INFO] Loading YOLO vehicle model: {model_path}")
        self.model = YOLO(model_path)
        self.names = self.model.names

    def detect(self, frame: np.ndarray, source_type: str = "public_transport_camera") -> List[Detection]:
        if frame is None or frame.size == 0:
            return []

        results = self.model.predict(
            source=frame,
            conf=self.confidence,
            iou=self.iou,
            verbose=False,
        )

        detections: List[Detection] = []
        if not results:
            return detections

        result = results[0]
        if result.boxes is None:
            return detections

        for box in result.boxes:
            cls_id = int(box.cls[0])
            class_name = str(self.names.get(cls_id, cls_id))
            conf = float(box.conf[0])
            x1, y1, x2, y2 = box.xyxy[0].detach().cpu().numpy().astype(int).tolist()
            cx = int((x1 + x2) / 2)
            cy = int((y1 + y2) / 2)

            if class_name not in self.allowed_classes:
                continue

            detections.append(
                Detection(
                    class_name=class_name,
                    confidence=conf,
                    bbox=(x1, y1, x2, y2),
                    center=(cx, cy),
                )
            )

        return detections
