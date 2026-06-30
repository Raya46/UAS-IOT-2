from typing import Dict, List


class TrafficStats:
    def __init__(self):
        self.history: List[Dict] = []
        self.max_history = 300

    def update(self, stats: Dict) -> None:
        self.history.append(stats)
        if len(self.history) > self.max_history:
            self.history.pop(0)

    @property
    def average_vehicle_count(self) -> float:
        if not self.history:
            return 0.0
        return sum(h["vehicle_count"] for h in self.history) / len(self.history)

    @property
    def average_pedestrian_count(self) -> float:
        if not self.history:
            return 0.0
        return sum(h.get("pedestrian_count", 0) for h in self.history) / len(
            self.history
        )

    def get_density_level(self, vehicle_count: int) -> str:
        avg = self.average_vehicle_count
        if vehicle_count > avg * 1.5 and vehicle_count > 8:
            return "HEAVY"
        elif vehicle_count > avg * 1.2 and vehicle_count > 4:
            return "MODERATE"
        else:
            return "LIGHT"
