import redis
import json
import time
import random
import uuid
from datetime import datetime, timezone

import os
redis_host = os.getenv("REDIS_HOST", "localhost")
redis_port = int(os.getenv("REDIS_PORT", "6389"))
r = redis.Redis(host=redis_host, port=redis_port, decode_responses=True)

# Koordinat di sekitar Jakarta untuk simulasi
JAKARTA_LOCATIONS = [
    {"lat": -6.216600, "lng": 106.801000, "camera_id": "cam-001", "name": "Gelora"},
    {"lat": -6.213300, "lng": 106.811500, "camera_id": "cam-002", "name": "Bendungan Hilir"},
    {"lat": -6.184300, "lng": 106.802800, "camera_id": "cam-003", "name": "Jati Pulo"},
    {"lat": -6.242800, "lng": 106.855400, "camera_id": "cam-004", "name": "Cikoko"},
]

VIOLATION_TYPES = ["illegal_parking", "busway_violation", "congestion", "wrong_way", "hazard_lights"]
SEVERITIES = ["low", "medium", "high"]

SNAPSHOTS = {
    "illegal_parking": "/snapshots/illegal_parking.png",
    "busway_violation": "/snapshots/busway_violation.png",
    "congestion": "/snapshots/congestion.png",
    "wrong_way": "/snapshots/wrong_way.png",
    "hazard_lights": "/snapshots/default.png",
}

def generate_violation():
    location = random.choice(JAKARTA_LOCATIONS)
    # Tambahkan sedikit noise agar posisi tidak persis sama
    lat_noise = random.uniform(-0.001, 0.001)
    lng_noise = random.uniform(-0.001, 0.001)
    v_type = random.choice(VIOLATION_TYPES)

    return {
        "type": "violation",
        "payload": {
            "id": str(uuid.uuid4()),
            "camera_id": location["camera_id"],
            "type": v_type,
            "lat": location["lat"] + lat_noise,
            "lng": location["lng"] + lng_noise,
            "severity": random.choice(SEVERITIES),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "snapshot_url": SNAPSHOTS.get(v_type, "/snapshots/default.png"),
            "confidence_score": round(random.uniform(0.75, 0.98), 2),
        }
    }

print("🚦 Simulator berjalan... Tekan Ctrl+C untuk stop")
print("   Mengirim data ke Redis topic: traffic.violation")
print("   Interval: 60 detik\n")

try:
    while True:
        data = generate_violation()
        r.publish("traffic.violation", json.dumps(data))
        print(f"  ✅ Published: {data['payload']['type']} di {data['payload']['camera_id']}")
        time.sleep(60)
except KeyboardInterrupt:
    print("\nSimulator dihentikan.")
