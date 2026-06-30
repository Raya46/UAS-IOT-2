import csv
import json
import os
from pathlib import Path
from typing import Any, Dict, Optional
import cv2
import numpy as np

try:
    import requests
except Exception:
    requests = None

class EvidenceService:
    def __init__(self, config):
        self.image_dir = Path(config.get("outputs.evidence_image_dir", "outputs/evidence/images"))
        self.plate_dir = Path(config.get("outputs.plate_crop_dir", "outputs/evidence/plates"))
        self.jsonl_path = Path(config.get("outputs.event_jsonl_path", "outputs/events/events.jsonl"))
        self.csv_path = Path(config.get("outputs.event_csv_path", "outputs/events/events.csv"))
        
        self.backend_enabled = bool(config.get("backend.enabled", False))
        self.backend_url = config.get("backend.url", "http://localhost:8000")

        self.image_dir.mkdir(parents=True, exist_ok=True)
        self.plate_dir.mkdir(parents=True, exist_ok=True)
        self.jsonl_path.parent.mkdir(parents=True, exist_ok=True)
        self.csv_path.parent.mkdir(parents=True, exist_ok=True)

    def save_image(self, frame: np.ndarray, event_id: str) -> str:
        path = self.image_dir / f"{event_id}.jpg"
        cv2.imwrite(str(path), frame)
        return str(path)

    def save_plate_crop(self, crop: Optional[np.ndarray], event_id: str) -> str:
        path = self.plate_dir / f"{event_id}_plate.jpg"
        if crop is not None and crop.size > 0:
            cv2.imwrite(str(path), crop)
        return str(path)

    def append_jsonl(self, event: Dict[str, Any]) -> None:
        with self.jsonl_path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(event, ensure_ascii=False) + "\n")

    def append_csv(self, event: Dict[str, Any]) -> None:
        fieldnames = [
            "event_id",
            "timestamp",
            "violation_type",
            "track_id",
            "vehicle_type",
            "confidence",
            "bbox",
            "duration_seconds",
            "inside_no_parking_zone",
            "plate_number",
            "plate_confidence",
            "evidence_image",
            "plate_crop",
            "source",
            "latitude",
            "longitude",
            "road_name",
            "gps_source"
        ]
        file_exists = self.csv_path.exists() and self.csv_path.stat().st_size > 0
        with self.csv_path.open("a", newline="", encoding="utf-8") as file:
            writer = csv.DictWriter(file, fieldnames=fieldnames)
            if not file_exists:
                writer.writeheader()
            
            # Map event dict into fieldnames, replacing missing values with None
            row_data = {key: event.get(key) for key in fieldnames}
            # Convert lists like bbox to string for CSV
            if isinstance(row_data["bbox"], list):
                row_data["bbox"] = json.dumps(row_data["bbox"])
            writer.writerow(row_data)

    def sync_to_backend(self, event: Dict[str, Any]) -> None:
        if not self.backend_enabled or requests is None:
            return

        try:
            url = f"{self.backend_url.rstrip('/')}/events"
            # Send the JSON payload to the backend
            # Note: since we're in local prototype, sending file paths in the JSON payload
            # allows backend to read evidence files directly from workspace folder.
            response = requests.post(url, json=event, timeout=3.0)
            if response.status_code in [200, 201]:
                print(f"[INFO] Synced event {event['event_id']} to backend successfully.")
            else:
                print(f"[WARN] Failed to sync event to backend: HTTP {response.status_code}")
        except Exception as exc:
            print(f"[WARN] Backend sync failed: {exc}. Event remains saved locally.")
