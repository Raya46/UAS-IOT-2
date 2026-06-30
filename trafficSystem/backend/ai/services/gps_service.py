import csv
import os
from typing import Dict, Any
from ai.utils.config import Config

class GPSService:
    def __init__(self, config: Config):
        self.mode = config.get("gps.mode", "static")
        self.static_lat = float(config.get("gps.static.latitude", -6.200000))
        self.static_lon = float(config.get("gps.static.longitude", 106.816666))
        self.static_road = config.get("gps.static.road_name", "Demo Road")
        self.mock_csv_path = config.get("gps.mock_csv_path", "data/gps_mock.csv")
        
        self.mock_coords = []
        if self.mode == "mock_csv":
            self.load_mock_csv()

    def load_mock_csv(self):
        # Create a default mock CSV if it doesn't exist
        if not os.path.exists(self.mock_csv_path):
            os.makedirs(os.path.dirname(self.mock_csv_path) or ".", exist_ok=True)
            with open(self.mock_csv_path, "w", newline="", encoding="utf-8") as file:
                writer = csv.writer(file)
                writer.writerow(["elapsed_seconds", "latitude", "longitude", "road_name"])
                # Add mock trajectory around Jakarta Central
                for i in range(120):
                    writer.writerow([
                        float(i),
                        -6.200000 + (i * 0.00001),
                        106.816666 + (i * 0.000015),
                        "Jl. Sudirman Kav. " + str(10 + i // 10)
                    ])
            print(f"[INFO] Created default mock GPS CSV file: {self.mock_csv_path}")

        try:
            with open(self.mock_csv_path, "r", encoding="utf-8") as file:
                reader = csv.DictReader(file)
                for row in reader:
                    self.mock_coords.append({
                        "elapsed_seconds": float(row["elapsed_seconds"]),
                        "latitude": float(row["latitude"]),
                        "longitude": float(row["longitude"]),
                        "road_name": row.get("road_name", "Mock Road")
                    })
            print(f"[INFO] Loaded {len(self.mock_coords)} GPS points from {self.mock_csv_path}")
        except Exception as exc:
            print(f"[WARN] Failed to load mock GPS CSV: {exc}. Falling back to static GPS.")
            self.mode = "static"

    def get_location(self, elapsed_seconds: float) -> Dict[str, Any]:
        """
        Retrieves current GPS coordinates based on mode and elapsed video/real time.
        """
        if self.mode == "mock_csv" and self.mock_coords:
            # Find the closest timestamped coord
            best_coord = self.mock_coords[0]
            min_diff = float("inf")
            for coord in self.mock_coords:
                diff = abs(coord["elapsed_seconds"] - elapsed_seconds)
                if diff < min_diff:
                    min_diff = diff
                    best_coord = coord
            return {
                "latitude": best_coord["latitude"],
                "longitude": best_coord["longitude"],
                "road_name": best_coord["road_name"],
                "gps_source": "mock_csv"
            }
        
        elif self.mode == "serial":
            # For serial mode, return mock dynamic coordinates or fall back to static
            return {
                "latitude": self.static_lat + 0.0001,
                "longitude": self.static_lon - 0.0001,
                "road_name": f"{self.static_road} (Serial)",
                "gps_source": "serial_future_mock"
            }

        # Static mode (default)
        return {
            "latitude": self.static_lat,
            "longitude": self.static_lon,
            "road_name": self.static_road,
            "gps_source": "static"
        }
