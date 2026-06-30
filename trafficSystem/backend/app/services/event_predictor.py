from app.models.schemas import Event
from app.services.event_crowd_estimator import classify_crowd

def generate_mitigation(event: Event) -> dict:
    """
    Rule-based predictor untuk prototype.
    Nanti bisa diganti dengan model ML.
    """
    crowd = event.estimated_crowd
    radius = event.impact_radius_km

    crowd_profile = classify_crowd(crowd, event.category or "general")
    impact_level = crowd_profile["impact_level"]
    officer_min = event.officer_min or crowd_profile["officer_min"]
    officer_max = event.officer_max or crowd_profile["officer_max"]
    crowd_zone = event.crowd_zone or crowd_profile["crowd_zone"]

    if crowd >= 50000:
        congestion_hours_before = 3
        congestion_hours_after = 2
    elif crowd >= 20000:
        congestion_hours_before = 2
        congestion_hours_after = 1
    elif crowd >= 5000:
        congestion_hours_before = 1
        congestion_hours_after = 1
    else:
        congestion_hours_before = 1
        congestion_hours_after = 1

    recommendations = [
        f"Turunkan {officer_min}-{officer_max} petugas untuk crowd zone {crowd_zone.upper()}",
        f"Siagakan petugas di radius {radius} km dari {event.venue} mulai H-{congestion_hours_before} jam",
        f"Aktifkan rekayasa lalu lintas di akses utama menuju {event.venue}",
        f"Tambah armada TransJakarta koridor terdekat mulai pukul {event.time.split(':')[0]}:00 WIB",
        "Tempatkan petugas di titik rawan parkir liar di sekitar venue",
        f"Estimasi kemacetan berlangsung hingga H+{congestion_hours_after} jam setelah acara",
    ]

    return {
        "event_id": event.id,
        "event_name": event.name,
        "impact_level": impact_level,
        "crowd_zone": crowd_zone,
        "zone_color": crowd_profile["color"],
        "estimated_crowd": crowd,
        "officer_min": officer_min,
        "officer_max": officer_max,
        "crowd_confidence": event.crowd_confidence,
        "crowd_reason": event.crowd_reason,
        "affected_radius_km": radius,
        "recommendations": recommendations,
        "predicted_congestion_start": f"H-{congestion_hours_before} jam sebelum {event.time}",
        "predicted_congestion_end": f"H+{congestion_hours_after} jam setelah {event.time}",
    }
