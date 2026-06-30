import os
from typing import Optional, Tuple
import cv2
import numpy as np
from ultralytics import YOLO
from ai.utils.config import Config
from ai.trackers.tracker_interface import BBox

class PlateDetector:
    def __init__(self, config: Config):
        self.use_plate_model = bool(config.get("models.use_plate_model", False))
        self.model_path = config.get("models.plate_model_path", "models/indonesian_plate.pt")
        self.model = None

        if self.use_plate_model:
            if os.path.exists(self.model_path):
                try:
                    print(f"[INFO] Loading Plate YOLO model: {self.model_path}")
                    self.model = YOLO(self.model_path)
                except Exception as exc:
                    print(f"[WARN] Failed to load plate YOLO model from {self.model_path}: {exc}. Will use fallback cropping.")
                    self.model = None
            else:
                print(f"[WARN] Plate YOLO model file not found at {self.model_path}. Will use fallback cropping.")
                self.model = None

    def detect_plate(self, frame: np.ndarray, vehicle_bbox: BBox) -> Tuple[Optional[np.ndarray], float, Optional[BBox]]:
        """
        Detects plate inside the vehicle bounding box.
        Returns (plate_crop, plate_confidence, plate_bbox_relative_to_frame)
        """
        # If plate model is active and successfully loaded
        if self.model is not None:
            try:
                vx1, vy1, vx2, vy2 = vehicle_bbox
                h, w = frame.shape[:2]
                vx1 = max(0, min(w - 1, vx1))
                vx2 = max(0, min(w - 1, vx2))
                vy1 = max(0, min(h - 1, vy1))
                vy2 = max(0, min(h - 1, vy2))
                
                vehicle_crop = frame[vy1:vy2, vx1:vx2]
                if vehicle_crop.size > 0:
                    results = self.model.predict(vehicle_crop, conf=0.25, verbose=False)
                    if results and results[0].boxes is not None and len(results[0].boxes) > 0:
                        # Find box with highest confidence
                        best_box = max(results[0].boxes, key=lambda b: float(b.conf[0]))
                        px1, py1, px2, py2 = best_box.xyxy[0].detach().cpu().numpy().astype(int).tolist()
                        conf = float(best_box.conf[0])
                        
                        # Extract crop
                        plate_crop = vehicle_crop[py1:py2, px1:px2]
                        
                        # Apply perspective correction (deskewing) for side-view/oblique angles
                        plate_crop = self.deskew_plate(plate_crop)
                        
                        # Convert bbox relative to original frame
                        abs_bbox = (vx1 + px1, vy1 + py1, vx1 + px2, vy1 + py2)
                        return plate_crop, conf, abs_bbox
            except Exception as exc:
                print(f"[WARN] Plate YOLO inference failed: {exc}. Falling back to crop.")
        
        # Fallback to cropping lower part of the vehicle bounding box
        fallback_crop = self.crop_plate_fallback(frame, vehicle_bbox)
        if fallback_crop is not None:
            # For fallback, return mock plate bbox representing the lower crop region
            vx1, vy1, vx2, vy2 = vehicle_bbox
            vh = vy2 - vy1
            crop_y1 = vy1 + int(vh * 0.55)
            crop_y2 = vy1 + int(vh * 0.95)
            return fallback_crop, 0.0, (vx1, crop_y1, vx2, crop_y2)

        return None, 0.0, None

    def deskew_plate(self, plate_crop: np.ndarray) -> np.ndarray:
        """
        Applies perspective transformation to deskew license plate crop from oblique/side angles.
        """
        if plate_crop is None or plate_crop.size == 0:
            return plate_crop

        try:
            h, w = plate_crop.shape[:2]
            # Convert to grayscale
            gray = cv2.cvtColor(plate_crop, cv2.COLOR_BGR2GRAY)
            
            # Adaptive thresholding to find plate boundaries
            thresh = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2)
            
            # Find contours
            contours, _ = cv2.findContours(thresh, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
            
            best_quad = None
            max_area = 0
            
            # Look for the largest quadrilateral contour representing the plate boundary
            for cnt in contours:
                area = cv2.contourArea(cnt)
                if area < w * h * 0.1:  # Must cover at least 10% of crop area
                    continue
                
                # Approximate contour to polygon
                peri = cv2.arcLength(cnt, True)
                approx = cv2.approxPolyDP(cnt, 0.02 * peri, True)
                
                # If the approximated polygon has 4 vertices, it's a quad
                if len(approx) == 4:
                    if area > max_area:
                        max_area = area
                        best_quad = approx

            if best_quad is not None:
                # Reorder points: top-left, top-right, bottom-right, bottom-left
                pts = best_quad.reshape(4, 2)
                rect = np.zeros((4, 2), dtype="float32")
                
                # top-left point has the smallest sum, bottom-right has the largest sum
                s = pts.sum(axis=1)
                rect[0] = pts[np.argmin(s)]
                rect[2] = pts[np.argmax(s)]
                
                # top-right has smallest difference, bottom-left has largest difference
                diff = np.diff(pts, axis=1)
                rect[1] = pts[np.argmin(diff)]
                rect[3] = pts[np.argmax(diff)]
                
                # Calculate destination dimensions
                (tl, tr, br, bl) = rect
                widthA = np.sqrt(((br[0] - bl[0]) ** 2) + ((br[1] - bl[1]) ** 2))
                widthB = np.sqrt(((tr[0] - tl[0]) ** 2) + ((tr[1] - tl[1]) ** 2))
                maxWidth = max(int(widthA), int(widthB))
                
                heightA = np.sqrt(((tr[1] - br[1]) ** 2) + ((tr[0] - br[0]) ** 2))
                heightB = np.sqrt(((tl[1] - bl[1]) ** 2) + ((tl[0] - bl[0]) ** 2))
                maxHeight = max(int(heightA), int(heightB))
                
                # Ensure bounds and aspect ratios are reasonable (plates are wide)
                if maxWidth > 30 and maxHeight > 10:
                    dst = np.array([
                        [0, 0],
                        [maxWidth - 1, 0],
                        [maxWidth - 1, maxHeight - 1],
                        [0, maxHeight - 1]], dtype="float32")
                    
                    # Apply perspective transform
                    M = cv2.getPerspectiveTransform(rect, dst)
                    warped = cv2.warpPerspective(plate_crop, M, (maxWidth, maxHeight))
                    return warped
                    
        except Exception as exc:
            print(f"[WARN] Deskewing failed: {exc}. Using raw crop.")
            
        return plate_crop

    @staticmethod
    def crop_plate_fallback(frame: np.ndarray, bbox: BBox) -> Optional[np.ndarray]:
        height, width = frame.shape[:2]
        x1, y1, x2, y2 = bbox
        x1 = max(0, min(width - 1, x1))
        x2 = max(0, min(width - 1, x2))
        y1 = max(0, min(height - 1, y1))
        y2 = max(0, min(height - 1, y2))

        if x2 <= x1 or y2 <= y1:
            return None

        box_h = y2 - y1
        box_w = x2 - x1
        crop_y1 = int(y1 + box_h * 0.40)
        crop_y2 = int(y1 + box_h * 0.90)
        crop_x1 = int(x1 + box_w * 0.10)
        crop_x2 = int(x1 + box_w * 0.90)
        
        crop_y1 = max(0, min(height - 1, crop_y1))
        crop_y2 = max(0, min(height - 1, crop_y2))
        crop_x1 = max(0, min(width - 1, crop_x1))
        crop_x2 = max(0, min(width - 1, crop_x2))

        if crop_x2 <= crop_x1 or crop_y2 <= crop_y1:
            return None

        crop = frame[crop_y1:crop_y2, crop_x1:crop_x2]

        if crop.size == 0:
            return None
        return crop
