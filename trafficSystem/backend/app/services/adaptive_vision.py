import base64
import json
import os
import re
from typing import Any, Dict, Tuple

import cv2
import httpx
import numpy as np


class AdaptiveImageEnhancer:
    """Restores low-light, low-contrast, hazy, or rain-streaked frames."""

    def enhance(self, frame: np.ndarray) -> Tuple[np.ndarray, Dict[str, Any]]:
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        brightness = float(np.mean(gray))
        contrast = float(np.std(gray))
        laplacian_variance = float(cv2.Laplacian(gray, cv2.CV_64F).var())

        modes = []
        enhanced = frame.copy()

        if brightness < 85:
            gamma = 0.55 if brightness < 45 else 0.72
            lut = np.array(
                [((value / 255.0) ** gamma) * 255 for value in range(256)],
                dtype=np.uint8,
            )
            enhanced = cv2.LUT(enhanced, lut)
            modes.append("low_light")

        if contrast < 48:
            lab = cv2.cvtColor(enhanced, cv2.COLOR_BGR2LAB)
            lightness, channel_a, channel_b = cv2.split(lab)
            clahe = cv2.createCLAHE(clipLimit=2.2, tileGridSize=(8, 8))
            lightness = clahe.apply(lightness)
            enhanced = cv2.cvtColor(
                cv2.merge((lightness, channel_a, channel_b)), cv2.COLOR_LAB2BGR
            )
            modes.append("contrast_haze")

        # Edge-preserving cleanup helps rain/noise without erasing plate characters.
        if laplacian_variance < 90 or brightness < 65:
            cleaned = cv2.bilateralFilter(enhanced, 7, 45, 45)
            blurred = cv2.GaussianBlur(cleaned, (0, 0), 1.0)
            enhanced = cv2.addWeighted(cleaned, 1.35, blurred, -0.35, 0)
            modes.append("denoise_sharpen")

        return enhanced, {
            "applied": bool(modes),
            "modes": modes,
            "brightness": round(brightness, 1),
            "contrast": round(contrast, 1),
            "sharpness": round(laplacian_variance, 1),
        }


class ContextualBehaviorReasoner:
    EXEMPT_CLASSES = {"ambulance", "fire_truck", "police", "emergency_vehicle"}
    PUBLIC_TRANSPORT_CLASSES = {
        "bus",
        "jaklingko",
        "angkot",
        "angkot_merah",
        "angkot_hijau",
        "angkot_biru",
        "transjakarta",
        "metrotrans",
        "bus_transjakarta",
    }

    def __init__(self) -> None:
        self.api_key = os.getenv("KIMI_API_KEY") or os.getenv("MOONSHOT_API_KEY")
        self.base_url = os.getenv("KIMI_BASE_URL", "https://api.moonshot.ai/v1")
        self.model = os.getenv("KIMI_MODEL", "kimi-k2.6")
        self.enabled = os.getenv("ENABLE_KIMI_VISION_REASONING", "true").lower() == "true"
        self.timeout = float(os.getenv("KIMI_TIMEOUT_SECONDS", "8"))

    def local_assessment(self, track: Any, violation_type: str) -> Dict[str, Any]:
        vehicle_class = str(track.class_name).lower()
        duration = float(getattr(track, "stationary_seconds", 0.0))
        track_age = max(0.0, float(track.last_seen_at - track.first_seen_at))

        if vehicle_class in self.EXEMPT_CLASSES:
            return self._result(False, "emergency_vehicle", 0.98, "Kendaraan darurat dikecualikan.")
        if duration < 2.0 and violation_type in {"illegal_parking", "restricted_area_stop"}:
            return self._result(False, "brief_stop", 0.92, "Durasi berhenti terlalu singkat.")
        if vehicle_class in self.PUBLIC_TRANSPORT_CLASSES and duration < 12.0:
            return self._result(False, "passenger_activity", 0.72, "Kemungkinan aktivitas naik-turun penumpang singkat.")
        return self._result(True, "probable_violation", 0.68, "Pola durasi dan posisi konsisten dengan kandidat pelanggaran.", track_age)

    def assess(self, frame: np.ndarray, track: Any, violation_type: str) -> Dict[str, Any]:
        local = self.local_assessment(track, violation_type)
        if not local["is_violation"] or not self.enabled or not self.api_key:
            local["reasoning_source"] = "local"
            return local

        x1, y1, x2, y2 = map(int, track.bbox)
        height, width = frame.shape[:2]
        pad = 48
        crop = frame[max(0, y1 - pad):min(height, y2 + pad), max(0, x1 - pad):min(width, x2 + pad)]
        if crop.size == 0:
            return local

        ok, encoded = cv2.imencode(".jpg", crop, [cv2.IMWRITE_JPEG_QUALITY, 75])
        if not ok:
            return local
        image_url = "data:image/jpeg;base64," + base64.b64encode(encoded).decode("ascii")
        prompt = (
            "Evaluate this Jakarta traffic violation candidate. Return JSON only with keys "
            "is_violation (boolean), behavior (string), confidence (0-1), reason (Indonesian string), "
            "exemption (one of none, emergency_vehicle, mechanical_breakdown, passenger_activity). "
            f"Candidate={violation_type}; vehicle={track.class_name}; "
            f"stationary_seconds={getattr(track, 'stationary_seconds', 0):.1f}. "
            "Do not infer identity. Treat emergency response, visible breakdown, or brief legitimate "
            "passenger activity as non-violations."
        )
        try:
            response = httpx.post(
                f"{self.base_url.rstrip('/')}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={
                    "model": self.model,
                    "temperature": 0.1,
                    "messages": [{"role": "user", "content": [
                        {"type": "image_url", "image_url": {"url": image_url}},
                        {"type": "text", "text": prompt},
                    ]}],
                },
                timeout=self.timeout,
            )
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
            match = re.search(r"\{.*\}", content, re.DOTALL)
            result = json.loads(match.group(0) if match else content)
            return {
                "is_violation": bool(result.get("is_violation", True)),
                "behavior": str(result.get("behavior", "unknown"))[:80],
                "confidence": max(0.0, min(1.0, float(result.get("confidence", 0.5)))),
                "reason": str(result.get("reason", ""))[:300],
                "exemption": str(result.get("exemption", "none"))[:50],
                "reasoning_source": "kimi",
            }
        except Exception as exc:
            local["reasoning_source"] = "local_fallback"
            local["reasoning_error"] = str(exc)[:160]
            return local

    @staticmethod
    def _result(is_violation: bool, behavior: str, confidence: float, reason: str, track_age: float = 0.0) -> Dict[str, Any]:
        return {
            "is_violation": is_violation,
            "behavior": behavior,
            "confidence": confidence,
            "reason": reason,
            "exemption": "none" if is_violation else behavior,
            "track_age_seconds": round(track_age, 2),
        }
