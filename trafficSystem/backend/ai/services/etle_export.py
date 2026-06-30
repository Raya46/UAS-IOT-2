import csv
import json
import os
from pathlib import Path
from typing import Any, Dict

class ETLEExport:
    def __init__(self, config):
        self.export_dir = Path(config.get("outputs.etle_export_dir", "outputs/exports/etle"))
        self.export_dir.mkdir(parents=True, exist_ok=True)
        self.csv_path = self.export_dir / "etle_violations.csv"

    def export_event(self, event: Dict[str, Any]) -> None:
        """
        Exports a single event into E-TLE compatible formats.
        Saves a JSON package for the individual event and appends to a master CSV log.
        """
        event_id = event.get("event_id")
        
        # Format latitude/longitude into a location string/dict
        lat = event.get("latitude", 0.0)
        lon = event.get("longitude", 0.0)
        road = event.get("road_name", "Unknown Road")
        location_str = f"{road} ({lat:.6f}, {lon:.6f})"

        etle_data = {
            "event_id": event_id,
            "violation_type": event.get("violation_type"),
            "timestamp": event.get("timestamp"),
            "plate_number": event.get("plate_number", "UNKNOWN"),
            "vehicle_type": event.get("vehicle_type"),
            "location": location_str,
            "evidence_image": event.get("evidence_image"),
            "plate_crop": event.get("plate_crop"),
            "source": event.get("source"),
            "duration": event.get("duration_seconds", 0.0),
            "confidence": event.get("confidence", 0.0),
            "review_status": "pending"  # Initial E-TLE state
        }

        # 1. Save individual JSON packet
        json_packet_path = self.export_dir / f"{event_id}_etle.json"
        try:
            with open(json_packet_path, "w", encoding="utf-8") as file:
                json.dump(etle_data, file, indent=2, ensure_ascii=False)
        except Exception as exc:
            print(f"[WARN] Failed to write E-TLE JSON packet: {exc}")

        # 2. Append to master CSV list
        fieldnames = list(etle_data.keys())
        file_exists = self.csv_path.exists() and self.csv_path.stat().st_size > 0
        
        try:
            with open(self.csv_path, "a", newline="", encoding="utf-8") as file:
                writer = csv.DictWriter(file, fieldnames=fieldnames)
                if not file_exists:
                    writer.writeheader()
                writer.writerow(etle_data)
        except Exception as exc:
            print(f"[WARN] Failed to append E-TLE master CSV log: {exc}")
