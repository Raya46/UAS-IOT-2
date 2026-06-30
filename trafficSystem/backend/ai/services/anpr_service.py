import re
import cv2
from typing import Optional, Tuple
import numpy as np
from ai.utils.config import Config

try:
    import easyocr
except Exception:
    easyocr = None

class ANPRService:
    def __init__(self, config: Config):
        self.enabled = bool(config.get("ocr.enabled", True))
        self.min_confidence = float(config.get("ocr.min_text_confidence", 0.3))
        self.plate_regex = re.compile(config.get("ocr.plate_regex", r"^[A-Z]{1,2}\s?[0-9]{1,4}\s?[A-Z]{0,3}$"))
        self.generate_mock_on_failure = bool(config.get("ocr.generate_mock_on_failure", False))
        self.reader = None

        if self.enabled and easyocr is not None:
            try:
                languages = config.get("ocr.languages", ["en"])
                print("[INFO] Initializing EasyOCR")
                self.reader = easyocr.Reader(languages, gpu=False)
            except Exception as exc:
                print(f"[WARN] EasyOCR initialization failed: {exc}")
                self.reader = None
        elif self.enabled:
            print("[WARN] easyocr is not installed. OCR will return UNKNOWN.")

    @staticmethod
    def clean_text(text: str) -> str:
        # Keep letters, numbers, and spaces
        cleaned = re.sub(r"[^A-Za-z0-9\s]", "", text).upper()
        # Collapse multiple spaces into single space and strip
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        return cleaned

    def read_plate(self, plate_crop: Optional[np.ndarray], track_id: Optional[int] = None, vehicle_type: Optional[str] = None, source_name: Optional[str] = None) -> Tuple[str, float, str]:
        if plate_crop is None or plate_crop.size == 0:
            return "UNKNOWN", 0.0, ""

        if not self.enabled or self.reader is None:
            return "UNKNOWN", 0.0, ""

        try:
            # Preprocess image to enhance license plate readability
            gray = cv2.cvtColor(plate_crop, cv2.COLOR_BGR2GRAY)
            
            # Upscale if the cropped image is too small (EasyOCR is sensitive to resolution)
            h, w = gray.shape[:2]
            if w < 200:
                scale = 200.0 / w
                gray = cv2.resize(gray, (200, int(h * scale)), interpolation=cv2.INTER_CUBIC)
            
            # Apply CLAHE (Contrast Limited Adaptive Histogram Equalization) to improve contrast
            clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8,8))
            gray = clahe.apply(gray)
            
            # Apply bilateral filter to remove noise while preserving edges
            gray = cv2.bilateralFilter(gray, 9, 75, 75)
            
            results = self.reader.readtext(gray)
            
            if not results:
                return "UNKNOWN", 0.0, ""

            best_text = ""
            best_conf = 0.0

            # Helper to check if text contains CCTV provider watermark
            def is_watermark(t: str) -> bool:
                t_upper = t.upper()
                return ("BALI" in t_upper and "TOWER" in t_upper) or "BALITOWER" in t_upper

            # Iterate through results to find the most confident one
            for result in results:
                raw_text = str(result[1])
                conf = float(result[2])
                cleaned = self.clean_text(raw_text)
                
                if is_watermark(cleaned):
                    print(f"[OCR DEBUG] Skipping CCTV watermark text: '{raw_text}'")
                    continue

                print(f"[OCR DEBUG] Raw: '{raw_text}' | Cleaned: '{cleaned}' | Conf: {conf:.3f}")
                if conf > best_conf and cleaned:
                    best_conf = conf
                    best_text = cleaned
            
            # Additionally, let's also try concatenating all non-watermark texts to see if it makes a valid plate
            valid_results = []
            for r in results:
                cleaned_item = self.clean_text(str(r[1]))
                if is_watermark(cleaned_item):
                    continue
                if r[2] >= self.min_confidence:
                    valid_results.append(cleaned_item)

            all_text_concat = " ".join(valid_results).strip()
            # remove extra spaces again
            all_text_concat = re.sub(r"\s+", " ", all_text_concat).strip()
            
            if self.plate_regex.match(all_text_concat):
                # We found a full match from combined text
                matching_confs = [r[2] for r in results if r[2] >= self.min_confidence and not is_watermark(self.clean_text(str(r[1])))]
                avg_conf = sum(matching_confs) / max(1, len(matching_confs))
                return all_text_concat, float(avg_conf), all_text_concat
            
            if best_conf < self.min_confidence or not best_text:
                return "UNKNOWN", best_conf, best_text

            if self.plate_regex.match(best_text):
                return best_text, best_conf, best_text

            # If no match but we have something, just return what we have (as long as it's something)
            return best_text, best_conf, best_text
            
        except Exception as exc:
            print(f"[WARN] OCR process failed: {exc}")
            return "UNKNOWN", 0.0, ""
