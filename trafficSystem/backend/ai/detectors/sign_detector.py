import os
import cv2
import numpy as np
from typing import List, Dict, Optional
from ultralytics import YOLO
from ai.utils.config import Config


class SignDetector:
    def __init__(self, config: Config = None):
        self.model_path = "models/traffic_sign.pt"
        self.use_traffic_sign_model = True

        if config is not None:
            self.model_path = config.get("models.sign_model_path", self.model_path)
            self.use_traffic_sign_model = config.get("models.use_traffic_sign_model", True)

        self.model = None

        # Load traffic sign model
        if os.path.exists(self.model_path):
            try:
                print(f"[INFO] Loading Traffic Sign YOLO model: {self.model_path}")
                self.model = YOLO(self.model_path)
            except Exception as exc:
                print(f"[WARN] Failed to load traffic sign model from {self.model_path}: {exc}")
        else:
            print(f"[WARN] Traffic sign model file not found at {self.model_path}.")

        # Map Turkish/raw class names to readable Indonesian/English labels
        self.class_map = {
            # Speed limits
            "20": "Batas 20 km/h",
            "30": "Batas 30 km/h",
            # Traffic signs
            "dur": "STOP",
            "durak": "Halte Bus",
            "girisyok": "Dilarang Masuk",
            "ilerisag": "Belok Kanan",
            "ilerisol": "Belok Kiri",
            "park": "Parkir",
            "parkyasak": "Dilarang Parkir",
            "parkyasak2": "Dilarang Parkir",
            "sag": "Arah Kanan",
            "sagadonulmez": "Dilarang Belok Kanan",
            "sol": "Arah Kiri",
            "soladonulmez": "Dilarang Belok Kiri",
            "yayagecidi": "Penyeberangan",
            "tasitrafiginekapali": "Jalan Tertutup",
            # Traffic lights (detected as signs by this model)
            "kirmizi": "Lampu Merah",
            "sari": "Lampu Kuning",
            "yesil": "Lampu Hijau",
            # Objects (we skip these — they overlap with main YOLO detector)
            # "arac": vehicle, "yaya": pedestrian, "otobus": bus, "bisikletli": cyclist
            # "yapılar": buildings
        }

        # Classes to skip (already detected by main YOLOv8s model)
        self._skip_classes = {"arac", "yaya", "otobus", "bisikletli", "yapılar"}

    def detect_signs(self, frame: np.ndarray) -> List[Dict]:
        """
        Detects traffic signs in the frame using YOLOv8.
        Returns a list of sign detections: [{"bbox": [x1,y1,x2,y2], "class_name": "...", "confidence": 0.85}]
        """
        detections = []
        if frame is None or frame.size == 0:
            return detections

        if self.model is None:
            return detections

        try:
            results = self.model.predict(frame, conf=0.25, verbose=False)
            if results and results[0].boxes is not None:
                result = results[0]
                names = self.model.names
                for box in result.boxes:
                    cls_id = int(box.cls[0])
                    raw_class = str(names.get(cls_id, cls_id))

                    # Skip classes handled by main detector
                    if raw_class in self._skip_classes:
                        continue

                    # Map to readable label (keep raw name if no mapping)
                    class_name = self.class_map.get(raw_class, raw_class)

                    conf = float(box.conf[0])
                    x1, y1, x2, y2 = box.xyxy[0].detach().cpu().numpy().astype(int).tolist()

                    detections.append({
                        "bbox": [x1, y1, x2, y2],
                        "class_name": class_name,
                        "confidence": round(conf, 2)
                    })
        except Exception as exc:
            print(f"[WARN] Traffic sign detection inference failed: {exc}")

        return detections
