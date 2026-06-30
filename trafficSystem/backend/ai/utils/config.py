import os
from pathlib import Path
import yaml

class Config:
    def __init__(self, path: str):
        self.path = path
        if not os.path.exists(path):
            raise FileNotFoundError(f"Config file not found: {path}")
        with open(path, "r", encoding="utf-8") as file:
            self.data = yaml.safe_load(file) or {}

    def get(self, dotted_key: str, default=None):
        current = self.data
        for key in dotted_key.split("."):
            if not isinstance(current, dict) or key not in current:
                return default
            current = current[key]
        return current

    def ensure_dirs(self):
        dirs = [
            self.get("outputs.evidence_image_dir", "outputs/evidence/images"),
            self.get("outputs.plate_crop_dir", "outputs/evidence/plates"),
            str(Path(self.get("outputs.event_jsonl_path", "outputs/events/events.jsonl")).parent),
            str(Path(self.get("outputs.event_csv_path", "outputs/events/events.csv")).parent),
            self.get("debug.save_manual_snapshots_dir", "outputs/debug"),
        ]
        for directory in dirs:
            if directory:
                Path(directory).mkdir(parents=True, exist_ok=True)
