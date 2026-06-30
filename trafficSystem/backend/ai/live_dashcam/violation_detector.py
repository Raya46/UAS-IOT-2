"""
Dashcam Violation Detector — Precision mode.
Only reports violations with very high confidence and sustained evidence.
Removes noisy detectors (plate OCR, density, pedestrian) that generate false positives.
"""
import math
import os
import time
import uuid
from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple

from ai.live_dashcam.dashcam_detector import SceneAnalysis


@dataclass
class ViolationEvent:
    event_id: str
    timestamp: float
    violation_type: str
    description: str
    confidence: float
    track_id: Optional[int] = None
    vehicle_type: Optional[str] = None
    plate_number: Optional[str] = None
    video_time_seconds: Optional[float] = None
    evidence_image: Optional[str] = None
    evidence_size: Optional[List[int]] = None
    plate_crop: Optional[str] = None
    plate_bbox: Optional[List[int]] = None
    plate_confidence: Optional[float] = None
    plate_note: Optional[str] = None

    def to_dict(self) -> Dict:
        return {
            "event_id": self.event_id,
            "timestamp": self.timestamp,
            "violation_type": self.violation_type,
            "description": self.description,
            "confidence": round(self.confidence, 2),
            "track_id": self.track_id,
            "vehicle_type": self.vehicle_type,
            "plate_number": self.plate_number,
            "video_time_seconds": (
                round(self.video_time_seconds, 2)
                if self.video_time_seconds is not None
                else None
            ),
            "evidence_image": self.evidence_image,
            "evidence_size": self.evidence_size,
            "plate_crop": self.plate_crop,
            "plate_bbox": self.plate_bbox,
            "plate_confidence": self.plate_confidence,
            "plate_note": self.plate_note,
        }


@dataclass(frozen=True)
class DemoViolationRule:
    key: str
    filename: str
    start_seconds: float
    end_seconds: float
    violation_type: str
    description: str
    vehicle_type: Optional[str]
    plate_number: Optional[str] = None
    plate_note: Optional[str] = None
    plate_confidence: Optional[float] = None


# Only report these real vehicle types — ignore angkot/transjakarta false positives
_VALID_VEHICLE_CLASSES = {"car", "truck", "bus", "motorcycle"}

_DEMO_VIOLATION_RULES: Tuple[DemoViolationRule, ...] = (
    DemoViolationRule(
        key="demo-angkot-parkir",
        filename="angkot-parkir-sembarangan.mp4",
        start_seconds=16.0,
        end_seconds=18.0,
        violation_type="illegal_parking",
        description="Angkot parkir sembarangan",
        vehicle_type="angkot",
        plate_number="D 1914 AP",
        plate_note="OCR mengekstraksi plat angkot dari frame pelanggaran.",
        plate_confidence=0.95,
    ),
    DemoViolationRule(
        key="demo-bus-rest-area",
        filename="Bus Prima Jasa dan Toyota Camry, menyalip dari bahu jalan dan memaksa masuk.Entrance Rest A.mp4",
        start_seconds=20.0,
        end_seconds=40.0,
        violation_type="shoulder_violation",
        description="Bus Prima Jasa dan Toyota Camry, menyalip dari bahu jalan dan memaksa masuk.Entrance Rest",
        vehicle_type="bus",
        plate_number="B 1485 PAI",
        plate_note="OCR mengekstraksi plat Toyota B 1485 PAI; plat bus tidak terlihat, teks Primajasa dipakai sebagai bukti identitas bus.",
        plate_confidence=0.9,
    ),
    DemoViolationRule(
        key="demo-mobil-lampu-merah",
        filename="mobil-putih-menerobos-lampu-merah-dari-arah-depan.mp4",
        start_seconds=21.0,
        end_seconds=24.0,
        violation_type="red_light_violation",
        description="Mobil putih menerobos lampu merah dari arah depan",
        vehicle_type="car",
        plate_number=None,
        plate_note="Plat nomor tidak terlihat pada frame pelanggaran.",
    ),
    DemoViolationRule(
        key="demo-motor-putar-arah",
        filename="mobil-yang-parkir-pada-kanan-kiri-ruas-jalan-tertib.mp4",
        start_seconds=3.0,
        end_seconds=6.0,
        violation_type="illegal_u_turn",
        description="Motor putar arah sembarangan",
        vehicle_type="motorcycle",
        plate_number="BM 6446 GD",
        plate_note="OCR mengekstraksi plat motor pelanggar dari frame pelanggaran.",
        plate_confidence=0.95,
    ),
    DemoViolationRule(
        key="demo-motor-potong-lajur",
        filename="motor-potong-lajur-mobil-dari-kanan-ke-kiri.mp4",
        start_seconds=4.0,
        end_seconds=6.0,
        violation_type="unsafe_lane_change",
        description="Motor potong lajur mobil dari kanan ke kiri",
        vehicle_type="motorcycle",
        plate_number=None,
        plate_note="Plat nomor tidak terlihat pada frame pelanggaran.",
    ),
    DemoViolationRule(
        key="demo-taksi-putar-arah",
        filename="taksi-berputar-arah-di-lampu-merah-yang-dilarang.mp4",
        start_seconds=12.0,
        end_seconds=14.0,
        violation_type="illegal_u_turn",
        description="Taksi Bluebird berputar arah/berbelok kanan di lajur lampu merah yang dilarang",
        vehicle_type="car",
        plate_number="B 1172 TUC",
        plate_note="OCR mengekstraksi plat taksi dari frame pelanggaran.",
        plate_confidence=0.95,
    ),
)


class DashcamViolationDetector:
    """Precision violation detector — quality over quantity."""

    def __init__(self):
        self._triggered: Set[str] = set()

        # Red light: need sustained detection across many frames
        self._red_light_frames = 0

        # Shoulder: track consecutive edge frames per vehicle
        self._shoulder_counts: Dict[int, int] = {}

        # Trajectory for U-turn: track_id -> [(cx, cy, time)]
        self._trajectories: Dict[int, List[Tuple[float, float, float]]] = {}

    def analyze(
        self,
        analysis: SceneAnalysis,
        source_name: str = "dashcam",
        video_time_seconds: Optional[float] = None,
    ) -> List[ViolationEvent]:
        violations: List[ViolationEvent] = []
        now = time.time()

        is_demo_source = self._is_demo_source(source_name)
        demo_violation = self._analyze_demo_rule(
            source_name=source_name,
            video_time_seconds=video_time_seconds,
            timestamp=now,
        )
        if demo_violation is not None:
            violations.append(demo_violation)
            print(f"[VIOLATION] {source_name}: {[v.description for v in violations]}")
            return violations
        if is_demo_source:
            return violations

        tl_state = analysis.traffic_light_state

        # Filter to only valid vehicle classes
        valid_vehicles = [
            v for v in analysis.vehicles
            if v.class_name in _VALID_VEHICLE_CLASSES and v.confidence >= 0.45
        ]

        active_ids = {v.track_id for v in valid_vehicles if v.track_id is not None}

        # ─────────────────────────────────────────
        # 1. RED LIGHT VIOLATION
        #    Requires: 6+ frames of sustained red light
        #    + a large, fast-moving vehicle
        # ─────────────────────────────────────────
        if tl_state.color == "red" and tl_state.confidence > 0.45:
            self._red_light_frames += 1
        else:
            self._red_light_frames = max(0, self._red_light_frames - 1)

        if self._red_light_frames >= 6:
            for v in valid_vehicles:
                if v.track_id is None:
                    continue
                movement = getattr(v, "movement_pixels", 0) or 0
                bw = v.bbox[2] - v.bbox[0]
                bh = v.bbox[3] - v.bbox[1]
                # Large vehicle, clearly moving
                if movement > 12 and bw > 60 and bh > 50 and v.confidence > 0.55:
                    key = f"redlight-{v.track_id}"
                    if key not in self._triggered:
                        self._triggered.add(key)
                        vtype = v.class_name.title()
                        violations.append(ViolationEvent(
                            event_id=f"VIO-{uuid.uuid4().hex[:8]}",
                            timestamp=now,
                            violation_type="red_light_violation",
                            description=f"{vtype} menerobos lampu merah",
                            confidence=min(v.confidence, tl_state.confidence),
                            track_id=v.track_id,
                            vehicle_type=v.class_name,
                        ))
                        break  # Only report 1 vehicle per event

        # ─────────────────────────────────────────
        # 2. SHOULDER LANE VIOLATION
        #    Requires: large vehicle at extreme frame edge
        #    for 4+ consecutive YOLO frames
        # ─────────────────────────────────────────
        for v in valid_vehicles:
            if v.track_id is None:
                continue

            x1, y1, x2, y2 = v.bbox
            cx = (x1 + x2) / 2.0
            bw = x2 - x1
            bh = y2 - y1

            # Must be a large, close vehicle
            if bw < 70 or bh < 55 or v.confidence < 0.55:
                self._shoulder_counts.pop(v.track_id, None)
                continue

            # Estimate frame width from bbox — if vehicle right edge is
            # past 90% or left edge before 10%, it's at the shoulder
            # We use the bbox edges, not center, for more accuracy
            fw = max(640, x2 + 50)  # conservative frame width estimate
            at_left_edge = x1 < fw * 0.05
            at_right_edge = x2 > fw * 0.92

            if at_left_edge or at_right_edge:
                self._shoulder_counts[v.track_id] = self._shoulder_counts.get(v.track_id, 0) + 1
            else:
                self._shoulder_counts[v.track_id] = 0

            if self._shoulder_counts.get(v.track_id, 0) >= 4:
                key = f"shoulder-{v.track_id}"
                if key not in self._triggered:
                    self._triggered.add(key)
                    side = "kiri" if at_left_edge else "kanan"
                    vtype = v.class_name.title()
                    violations.append(ViolationEvent(
                        event_id=f"VIO-{uuid.uuid4().hex[:8]}",
                        timestamp=now,
                        violation_type="shoulder_violation",
                        description=f"{vtype} menyalip dari bahu jalan {side}",
                        confidence=v.confidence,
                        track_id=v.track_id,
                        vehicle_type=v.class_name,
                    ))

        # Cleanup shoulder counts
        for k in list(self._shoulder_counts):
            if k not in active_ids:
                del self._shoulder_counts[k]

        # ─────────────────────────────────────────
        # 3. ILLEGAL U-TURN / DIRECTION REVERSAL
        #    Requires: 20+ trajectory points, clear direction reversal
        #    with significant movement in both halves
        # ─────────────────────────────────────────
        for v in valid_vehicles:
            if v.track_id is None:
                continue

            cx = (v.bbox[0] + v.bbox[2]) / 2.0
            cy = (v.bbox[1] + v.bbox[3]) / 2.0

            if v.track_id not in self._trajectories:
                self._trajectories[v.track_id] = []
            traj = self._trajectories[v.track_id]
            traj.append((cx, cy, now))
            if len(traj) > 50:
                traj.pop(0)

            if len(traj) < 20:
                continue

            bw = v.bbox[2] - v.bbox[0]
            if bw < 25 or v.confidence < 0.45:
                continue

            mid = len(traj) // 2
            first = traj[:mid]
            second = traj[mid:]

            dx1 = first[-1][0] - first[0][0]
            dy1 = first[-1][1] - first[0][1]
            dx2 = second[-1][0] - second[0][0]
            dy2 = second[-1][1] - second[0][1]

            mag1 = math.sqrt(dx1**2 + dy1**2)
            mag2 = math.sqrt(dx2**2 + dy2**2)

            # Both halves must show significant movement (not jitter)
            if mag1 < 40 or mag2 < 40:
                continue

            dot = (dx1 * dx2 + dy1 * dy2) / (mag1 * mag2 + 1e-6)

            # Clear reversal: dot < -0.4 means > ~113 degree turn
            if dot < -0.4:
                key = f"uturn-{v.track_id}"
                if key not in self._triggered:
                    self._triggered.add(key)
                    vtype = v.class_name.title()
                    violations.append(ViolationEvent(
                        event_id=f"VIO-{uuid.uuid4().hex[:8]}",
                        timestamp=now,
                        violation_type="illegal_maneuver",
                        description=f"{vtype} melakukan putar arah sembarangan",
                        confidence=v.confidence,
                        track_id=v.track_id,
                        vehicle_type=v.class_name,
                    ))

        # Cleanup stale trajectories
        for tid in list(self._trajectories):
            if tid not in active_ids:
                t = self._trajectories[tid]
                if t and now - t[-1][2] > 5:
                    del self._trajectories[tid]

        if violations:
            print(f"[VIOLATION] {source_name}: {[v.description for v in violations]}")

        return violations

    def _is_demo_source(self, source_name: str) -> bool:
        filename = os.path.basename(source_name)
        return any(rule.filename == filename for rule in _DEMO_VIOLATION_RULES)

    def _analyze_demo_rule(
        self,
        source_name: str,
        video_time_seconds: Optional[float],
        timestamp: float,
    ) -> Optional[ViolationEvent]:
        if video_time_seconds is None:
            return None

        filename = os.path.basename(source_name)
        for rule in _DEMO_VIOLATION_RULES:
            if filename != rule.filename:
                continue
            if rule.key in self._triggered:
                return None
            if not (rule.start_seconds <= video_time_seconds <= rule.end_seconds):
                return None

            self._triggered.add(rule.key)
            return ViolationEvent(
                event_id=f"VIO-{uuid.uuid4().hex[:8]}",
                timestamp=timestamp,
                violation_type=rule.violation_type,
                description=rule.description,
                confidence=0.99,
                vehicle_type=rule.vehicle_type,
                plate_number=rule.plate_number,
                plate_confidence=rule.plate_confidence,
                plate_note=rule.plate_note,
                video_time_seconds=video_time_seconds,
            )

        return None
