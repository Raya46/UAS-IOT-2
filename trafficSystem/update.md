# Traffic Intelligence Dashboard — V2 Development Specification

**Dokumen ini ditujukan untuk AI code agent. Setiap modul berisi konteks, skema data, kode yang harus ditulis/dimodifikasi, dan acceptance criteria yang terukur. Eksekusi modul secara berurutan.**

Referensi codebase: lihat `traffic-dashboard-setup-guide.md` (V1).
Stack yang sudah berjalan: React + TypeScript · Mapbox GL JS · FastAPI · Redis Pub/Sub · PostgreSQL + PostGIS.

---

## Daftar Isi

1. [Konteks & Scope V2](#1-konteks--scope-v2)
2. [Perubahan Database Schema](#2-perubahan-database-schema)
3. [Modul A — Confidence Scoring & Alert Deduplication](#3-modul-a--confidence-scoring--alert-deduplication)
4. [Modul B — Incident Lifecycle Management](#4-modul-b--incident-lifecycle-management)
5. [Modul C — Violation Heatmap Dashboard (Spasial-Temporal)](#5-modul-c--violation-heatmap-dashboard-spasial-temporal)
6. [Modul D — Placement Simulator (E-TLE & Petugas)](#6-modul-d--placement-simulator-e-tle--petugas)
7. [Modul E — Executive Summary & Reporting](#7-modul-e--executive-summary--reporting)
8. [Modul F — Dynamic Congestion Prediction (Event Integration)](#8-modul-f--dynamic-congestion-prediction-event-integration)
9. [Modul G — Risk Profiling Layer](#9-modul-g--risk-profiling-layer)
10. [Modul H — Operator Workflow UI (Incident Single-View)](#10-modul-h--operator-workflow-ui-incident-single-view)
11. [Integrasi External Data Sources](#11-integrasi-external-data-sources)
12. [Acceptance Criteria Keseluruhan](#12-acceptance-criteria-keseluruhan)

---

## 1. Konteks & Scope V2

### Yang sudah ada di V1 (jangan dihapus, akan diextend):
- `backend/app/routers/cameras.py` — endpoint GET /api/cameras
- `backend/app/routers/zones.py` — endpoint GET /api/zones
- `backend/app/routers/events.py` — endpoint GET /api/events + GET /api/events/{id}/mitigation
- `backend/app/routers/websocket.py` — WebSocket `/ws` + Redis listener
- `backend/app/models/schemas.py` — Pydantic schemas: Camera, Zone, Violation, Event, Mitigation
- `backend/app/services/redis_client.py` — async Redis client
- `frontend/src/components/Map/` — MapContainer, CameraMarkers, ViolationMarkers, ZonePolygons
- `frontend/src/components/Dashboard/` — NotificationPanel, EventMitigationPanel, StatusBar
- `frontend/src/components/Modals/CCTVModal.tsx`
- `frontend/src/hooks/useWebSocket.ts` + `useNotifications.ts`
- `frontend/src/services/api.ts`
- `frontend/src/types/index.ts`

### Yang ditambahkan di V2:
- Confidence scoring pada setiap alert dari CV worker
- Alert deduplication: multi-sinyal → satu incident terkonsolidasi
- Incident lifecycle: `detected → confirmed → dispatched → resolved`
- Violation heatmap: spasial-temporal dengan filter jam/hari/tipe
- Placement simulator: rekomendasi titik E-TLE / petugas berbasis risk score
- Executive summary: laporan harian PDF + ringkasan untuk stakeholder
- Dynamic congestion prediction: integrasi event portal Jakarta
- Risk profiling layer: heatmap titik rawan berbasis historical data

---

## 2. Perubahan Database Schema

**File:** `backend/schema_v2.sql`

Jalankan setelah schema V1 sudah ada. Semua adalah `ALTER TABLE` atau tabel baru; tidak ada yang drop.

```sql
-- =============================================================
-- EXTENSION (sudah ada dari V1, pastikan aktif)
-- =============================================================
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- =============================================================
-- TAMBAHAN KOLOM KE TABEL violations (V1)
-- =============================================================
ALTER TABLE violations
  ADD COLUMN IF NOT EXISTS confidence_score   FLOAT DEFAULT 0.5,
  ADD COLUMN IF NOT EXISTS source_count       INTEGER DEFAULT 1,
  ADD COLUMN IF NOT EXISTS status             VARCHAR(20) DEFAULT 'detected',
  ADD COLUMN IF NOT EXISTS assigned_officer   VARCHAR(100),
  ADD COLUMN IF NOT EXISTS resolved_at        TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS resolution_notes   TEXT,
  ADD COLUMN IF NOT EXISTS parent_incident_id UUID REFERENCES violations(id),
  ADD COLUMN IF NOT EXISTS duplicate_of       UUID REFERENCES violations(id);

-- Index untuk lifecycle queries
CREATE INDEX IF NOT EXISTS violations_status_idx ON violations (status);
CREATE INDEX IF NOT EXISTS violations_location_idx ON violations USING GIST (location);

-- =============================================================
-- TABEL BARU: incidents (agregasi dari violations)
-- =============================================================
CREATE TABLE IF NOT EXISTS incidents (
  id                UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  title             VARCHAR(300) NOT NULL,
  type              VARCHAR(50) NOT NULL,
  location          GEOGRAPHY(POINT, 4326) NOT NULL,
  severity          VARCHAR(20) NOT NULL DEFAULT 'medium',
  confidence_score  FLOAT NOT NULL DEFAULT 0.5,
  status            VARCHAR(20) NOT NULL DEFAULT 'detected',
  -- Status lifecycle: detected → confirmed → dispatched → resolved → closed
  source_violations UUID[] DEFAULT '{}',
  source_count      INTEGER DEFAULT 1,
  assigned_officer  VARCHAR(100),
  assigned_at       TIMESTAMPTZ,
  resolved_at       TIMESTAMPTZ,
  resolution_notes  TEXT,
  snapshot_url      TEXT,
  camera_id         VARCHAR(50) REFERENCES cameras(id),
  occurred_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS incidents_status_idx ON incidents (status);
CREATE INDEX IF NOT EXISTS incidents_occurred_at_idx ON incidents (occurred_at DESC);
CREATE INDEX IF NOT EXISTS incidents_location_idx ON incidents USING GIST (location);
CREATE INDEX IF NOT EXISTS incidents_type_idx ON incidents (type);

-- =============================================================
-- TABEL BARU: risk_zones (hasil kalkulasi risk profiling)
-- =============================================================
CREATE TABLE IF NOT EXISTS risk_zones (
  id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  name            VARCHAR(200),
  location        GEOGRAPHY(POINT, 4326) NOT NULL,
  risk_score      FLOAT NOT NULL DEFAULT 0.0,  -- 0.0 sampai 1.0
  violation_types TEXT[] DEFAULT '{}',          -- tipe pelanggaran dominan
  incident_count  INTEGER DEFAULT 0,
  peak_hours      INTEGER[] DEFAULT '{}',        -- jam-jam rawan (0-23)
  peak_days       INTEGER[] DEFAULT '{}',        -- hari rawan (0=Senin, 6=Minggu)
  radius_m        FLOAT DEFAULT 100.0,
  calculated_at   TIMESTAMPTZ DEFAULT NOW(),
  CONSTRAINT risk_score_range CHECK (risk_score >= 0.0 AND risk_score <= 1.0)
);

CREATE INDEX IF NOT EXISTS risk_zones_score_idx ON risk_zones (risk_score DESC);
CREATE INDEX IF NOT EXISTS risk_zones_location_idx ON risk_zones USING GIST (location);

-- =============================================================
-- TABEL BARU: placement_recommendations
-- =============================================================
CREATE TABLE IF NOT EXISTS placement_recommendations (
  id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  location            GEOGRAPHY(POINT, 4326) NOT NULL,
  recommendation_type VARCHAR(20) NOT NULL,  -- 'camera_etle' | 'officer'
  priority_rank       INTEGER NOT NULL,
  risk_score          FLOAT NOT NULL,
  violation_types     TEXT[] DEFAULT '{}',
  coverage_radius_m   FLOAT DEFAULT 150.0,
  rationale           TEXT,
  generated_at        TIMESTAMPTZ DEFAULT NOW(),
  is_active           BOOLEAN DEFAULT true
);

-- =============================================================
-- TABEL BARU: daily_reports
-- =============================================================
CREATE TABLE IF NOT EXISTS daily_reports (
  id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  report_date         DATE NOT NULL UNIQUE,
  total_incidents     INTEGER DEFAULT 0,
  by_type             JSONB DEFAULT '{}',    -- {"busway_violation": 12, "illegal_parking": 34}
  by_severity         JSONB DEFAULT '{}',    -- {"high": 5, "medium": 20, "low": 21}
  by_hour             JSONB DEFAULT '{}',    -- {"0": 2, "1": 1, ..., "23": 8}
  top_locations       JSONB DEFAULT '[]',    -- [{lat, lng, count, type}]
  avg_response_time_s INTEGER,
  resolved_count      INTEGER DEFAULT 0,
  pdf_url             TEXT,
  generated_at        TIMESTAMPTZ DEFAULT NOW()
);

-- =============================================================
-- TABEL BARU: event_predictions (output dari congestion predictor)
-- =============================================================
CREATE TABLE IF NOT EXISTS event_predictions (
  id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  event_id            VARCHAR(50) NOT NULL,
  event_name          VARCHAR(300) NOT NULL,
  predicted_at        TIMESTAMPTZ DEFAULT NOW(),
  impact_start        TIMESTAMPTZ NOT NULL,
  impact_end          TIMESTAMPTZ NOT NULL,
  affected_segments   JSONB DEFAULT '[]',  -- [{segment_id, congestion_level, coordinates}]
  mitigation_actions  JSONB DEFAULT '[]',  -- [{action, location, priority}]
  confidence          FLOAT DEFAULT 0.7
);

-- =============================================================
-- TABEL BARU: external_events (dari scraper portal Jakarta)
-- =============================================================
CREATE TABLE IF NOT EXISTS external_events (
  id                UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  external_id       VARCHAR(200) UNIQUE,
  source            VARCHAR(50),            -- 'tiket_com' | 'loket_com' | 'manual' | 'jakartago'
  name              VARCHAR(500) NOT NULL,
  venue             VARCHAR(300),
  location          GEOGRAPHY(POINT, 4326),
  event_date        DATE NOT NULL,
  event_time        TIME,
  end_time          TIME,
  estimated_crowd   INTEGER DEFAULT 0,
  category          VARCHAR(100),           -- 'concert' | 'sports' | 'marathon' | 'fair'
  raw_data          JSONB DEFAULT '{}',
  scraped_at        TIMESTAMPTZ DEFAULT NOW(),
  is_verified       BOOLEAN DEFAULT false
);

CREATE INDEX IF NOT EXISTS external_events_date_idx ON external_events (event_date);
CREATE INDEX IF NOT EXISTS external_events_location_idx ON external_events USING GIST (location);

-- =============================================================
-- VIEW: violation_heatmap_data (untuk modul C)
-- =============================================================
CREATE OR REPLACE VIEW violation_heatmap_data AS
SELECT
  ST_X(location::geometry)                    AS lng,
  ST_Y(location::geometry)                    AS lat,
  type,
  severity,
  confidence_score,
  EXTRACT(HOUR FROM occurred_at)::INTEGER      AS hour_of_day,
  EXTRACT(DOW FROM occurred_at)::INTEGER       AS day_of_week,
  DATE(occurred_at)                            AS incident_date,
  occurred_at
FROM incidents
WHERE occurred_at >= NOW() - INTERVAL '90 days';

-- =============================================================
-- FUNCTION: calculate_risk_zones (dijalankan via cron harian)
-- =============================================================
CREATE OR REPLACE FUNCTION calculate_risk_zones()
RETURNS void AS $$
BEGIN
  DELETE FROM risk_zones;

  INSERT INTO risk_zones (location, risk_score, violation_types, incident_count, peak_hours, peak_days, radius_m)
  SELECT
    ST_Centroid(ST_Collect(location::geometry))::geography AS location,
    LEAST(COUNT(*)::float / 50.0, 1.0)                     AS risk_score,
    ARRAY_AGG(DISTINCT type)                                AS violation_types,
    COUNT(*)                                                AS incident_count,
    ARRAY_AGG(DISTINCT EXTRACT(HOUR FROM occurred_at)::INTEGER) AS peak_hours,
    ARRAY_AGG(DISTINCT EXTRACT(DOW FROM occurred_at)::INTEGER)  AS peak_days,
    100.0                                                   AS radius_m
  FROM incidents
  WHERE occurred_at >= NOW() - INTERVAL '30 days'
  GROUP BY ST_SnapToGrid(location::geometry, 0.001)
  HAVING COUNT(*) >= 3;
END;
$$ LANGUAGE plpgsql;
```

---

## 3. Modul A — Confidence Scoring & Alert Deduplication

### Konteks
Lanternn mengkonsolidasi 134 sinyal menjadi 1 incident dengan confidence score. Saat ini sistem hanya forward setiap pesan Redis mentah ke frontend. Modul ini menambahkan layer deduplikasi sebelum data sampai ke WebSocket.

### 3.1 Backend: Service Baru

**Buat file:** `backend/app/services/incident_aggregator.py`

```python
import asyncio
import json
import uuid
from datetime import datetime, timezone, timedelta
from math import radians, cos, sin, asin, sqrt
from typing import Optional
from app.services.redis_client import get_redis
from app.models.schemas import Violation, IncidentPayload

# Radius dalam meter untuk menggabungkan sinyal yang dianggap satu insiden
DEDUP_RADIUS_M = 150
# Jendela waktu dalam detik untuk deduplication
DEDUP_WINDOW_S = 120

# Cache in-memory: key = incident_id, value = {lat, lng, type, count, first_seen, confidence}
_active_incidents: dict[str, dict] = {}

def _haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Jarak haversine dalam meter antara dua koordinat."""
    R = 6371000
    lat1, lng1, lat2, lng2 = map(radians, [lat1, lng1, lat2, lng2])
    dlat = lat2 - lat1
    dlng = lng2 - lng1
    a = sin(dlat/2)**2 + cos(lat1)*cos(lat2)*sin(dlng/2)**2
    return R * 2 * asin(sqrt(a))

def _find_existing_incident(lat: float, lng: float, v_type: str) -> Optional[str]:
    """Cari incident aktif dalam radius DEDUP_RADIUS_M dan tipe yang sama."""
    now = datetime.now(timezone.utc)
    expired_keys = []

    for inc_id, inc_data in _active_incidents.items():
        age_s = (now - inc_data["first_seen"]).total_seconds()
        if age_s > DEDUP_WINDOW_S:
            expired_keys.append(inc_id)
            continue
        if inc_data["type"] != v_type:
            continue
        dist = _haversine_m(lat, lng, inc_data["lat"], inc_data["lng"])
        if dist <= DEDUP_RADIUS_M:
            return inc_id

    for k in expired_keys:
        _active_incidents.pop(k, None)
    return None

def _calculate_confidence(source_count: int, severity: str) -> float:
    """
    Confidence score 0.0–1.0:
    - Setiap sumber tambahan meningkatkan confidence
    - Severity high menambah bobot
    """
    base = min(0.4 + (source_count - 1) * 0.2, 0.9)
    severity_bonus = {"high": 0.1, "medium": 0.05, "low": 0.0}.get(severity, 0.0)
    return min(base + severity_bonus, 1.0)

async def process_violation(violation: Violation) -> Optional[IncidentPayload]:
    """
    Terima raw violation dari CV worker, lakukan deduplication,
    kembalikan IncidentPayload terkonsolidasi atau None jika duplikat.
    """
    existing_id = _find_existing_incident(violation.lat, violation.lng, violation.type)

    if existing_id:
        # Ini duplikat — update count dan confidence, jangan publish event baru
        _active_incidents[existing_id]["source_count"] += 1
        _active_incidents[existing_id]["confidence"] = _calculate_confidence(
            _active_incidents[existing_id]["source_count"],
            violation.severity,
        )
        # Publish update confidence ke channel terpisah
        redis = await get_redis()
        update_payload = {
            "type": "incident_update",
            "payload": {
                "incident_id": existing_id,
                "source_count": _active_incidents[existing_id]["source_count"],
                "confidence_score": _active_incidents[existing_id]["confidence"],
            }
        }
        await redis.publish("traffic.incident_update", json.dumps(update_payload))
        return None

    # Ini incident baru
    incident_id = str(uuid.uuid4())
    confidence = _calculate_confidence(1, violation.severity)
    now = datetime.now(timezone.utc)

    _active_incidents[incident_id] = {
        "lat": violation.lat,
        "lng": violation.lng,
        "type": violation.type,
        "source_count": 1,
        "first_seen": now,
        "confidence": confidence,
    }

    return IncidentPayload(
        id=incident_id,
        camera_id=violation.camera_id,
        type=violation.type,
        lat=violation.lat,
        lng=violation.lng,
        severity=violation.severity,
        confidence_score=confidence,
        source_count=1,
        status="detected",
        timestamp=now.isoformat(),
        snapshot_url=violation.snapshot_url,
    )
```

### 3.2 Tambahkan Schema Baru

**Edit file:** `backend/app/models/schemas.py` — tambahkan class berikut:

```python
class IncidentPayload(BaseModel):
    id: str
    camera_id: str
    type: Literal["illegal_parking", "busway_violation", "congestion", "wrong_way", "hazard_lights"]
    lat: float
    lng: float
    severity: Literal["low", "medium", "high"]
    confidence_score: float          # 0.0–1.0
    source_count: int                # berapa banyak sinyal yang digabungkan
    status: Literal["detected", "confirmed", "dispatched", "resolved", "closed"]
    timestamp: str
    snapshot_url: Optional[str] = None

class IncidentStatusUpdate(BaseModel):
    incident_id: str
    status: Literal["confirmed", "dispatched", "resolved", "closed"]
    assigned_officer: Optional[str] = None
    resolution_notes: Optional[str] = None

class IncidentListResponse(BaseModel):
    items: list[IncidentPayload]
    total: int
    page: int
    page_size: int
```

### 3.3 Modifikasi WebSocket Router

**Edit file:** `backend/app/routers/websocket.py` — ubah `redis_listener` agar pakai aggregator:

```python
# Tambahkan import
from app.services.incident_aggregator import process_violation
from app.models.schemas import Violation, IncidentPayload
import json

# Ganti SUBSCRIBED_TOPICS
SUBSCRIBED_TOPICS = [
    "traffic.violation",       # masuk dari CV worker (raw)
    "traffic.incident_update", # update confidence dari aggregator
    "traffic.congestion",
    "traffic.alert",
    "traffic.event_prediction",
]

# Ubah redis_listener untuk proses violation sebelum broadcast
async def redis_listener():
    redis = await get_redis()
    pubsub = redis.pubsub()
    await pubsub.subscribe(*SUBSCRIBED_TOPICS)

    async for message in pubsub.listen():
        if message["type"] != "message":
            continue

        raw = message["data"]
        try:
            parsed = json.loads(raw)
        except Exception:
            continue

        # Proses violation melalui aggregator
        if parsed.get("type") == "violation" and parsed.get("payload"):
            violation = Violation(**parsed["payload"])
            consolidated = await process_violation(violation)
            if consolidated is None:
                continue  # duplikat, skip
            # Publish incident terkonsolidasi sebagai event baru
            broadcast_msg = json.dumps({
                "type": "incident",
                "payload": consolidated.model_dump()
            })
            await broadcast(broadcast_msg)
        else:
            # Tipe lain (congestion, alert, dll) langsung broadcast
            await broadcast(raw)
```

### 3.4 Frontend: Update Types & Notification

**Edit file:** `frontend/src/types/index.ts` — tambahkan:

```typescript
export interface Incident {
  id: string;
  camera_id: string;
  type: "illegal_parking" | "busway_violation" | "congestion" | "wrong_way" | "hazard_lights";
  lat: number;
  lng: number;
  severity: "low" | "medium" | "high";
  confidence_score: number;        // 0.0–1.0
  source_count: number;
  status: "detected" | "confirmed" | "dispatched" | "resolved" | "closed";
  timestamp: string;
  snapshot_url?: string;
}

export type WSMessageType =
  | { type: "incident"; payload: Incident }
  | { type: "incident_update"; payload: { incident_id: string; source_count: number; confidence_score: number } }
  | { type: "congestion"; payload: CongestionUpdate }
  | { type: "alert"; payload: AlertPayload }
  | { type: "event_prediction"; payload: EventPrediction }
  | { type: "ping" };

export interface EventPrediction {
  event_id: string;
  event_name: string;
  impact_start: string;
  impact_end: string;
  affected_segments: Array<{
    segment_id: string;
    congestion_level: "medium" | "high" | "critical";
    coordinates: [number, number][];
    color: string;
  }>;
  mitigation_actions: Array<{
    action: string;
    location?: { lat: number; lng: number };
    priority: number;
  }>;
}
```

**Edit file:** `frontend/src/components/Dashboard/NotificationPanel.tsx` — tambahkan tampilan confidence score:

```typescript
// Dalam JSX kartu notifikasi, tambahkan confidence bar setelah timestamp:
<div style={{ marginTop: 6, marginLeft: 16 }}>
  <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
    <span style={{ color: "#555", fontSize: 10 }}>Confidence</span>
    <div style={{
      flex: 1, height: 3, background: "#222", borderRadius: 2, overflow: "hidden"
    }}>
      <div style={{
        width: `${(notification.confidence_score ?? 0.5) * 100}%`,
        height: "100%",
        background: notification.confidence_score > 0.7 ? "#ff4500"
          : notification.confidence_score > 0.4 ? "#ffa500" : "#888",
        transition: "width 0.3s ease",
      }} />
    </div>
    <span style={{ color: "#666", fontSize: 10, minWidth: 32 }}>
      {Math.round((notification.confidence_score ?? 0.5) * 100)}%
    </span>
  </div>
  {notification.source_count > 1 && (
    <span style={{ color: "#666", fontSize: 10 }}>
      {notification.source_count} sinyal digabungkan
    </span>
  )}
</div>
```

---

## 4. Modul B — Incident Lifecycle Management

### Konteks
Lanternn memiliki full lifecycle: deteksi → validasi → dispatch → resolusi. Operator dapat update status langsung dari dashboard.

### 4.1 Backend: Router Baru

**Buat file:** `backend/app/routers/incidents.py`

```python
from fastapi import APIRouter, HTTPException, Query
from typing import Optional
import asyncpg
import os
import json
from datetime import datetime, timezone
from app.models.schemas import IncidentPayload, IncidentStatusUpdate, IncidentListResponse
from app.services.redis_client import get_redis

router = APIRouter(prefix="/api/incidents", tags=["incidents"])

async def get_db():
    conn = await asyncpg.connect(os.getenv("DATABASE_URL").replace("+asyncpg", ""))
    try:
        yield conn
    finally:
        await conn.close()

@router.get("/", response_model=IncidentListResponse)
async def list_incidents(
    status: Optional[str] = Query(None),
    type: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """Daftar incidents dengan filter dan pagination."""
    conn = await asyncpg.connect(os.getenv("DATABASE_URL").replace("+asyncpg", ""))
    try:
        where_clauses = []
        params = []
        idx = 1

        if status:
            where_clauses.append(f"status = ${idx}")
            params.append(status)
            idx += 1
        if type:
            where_clauses.append(f"type = ${idx}")
            params.append(type)
            idx += 1

        where_sql = "WHERE " + " AND ".join(where_clauses) if where_clauses else ""
        offset = (page - 1) * page_size

        total = await conn.fetchval(f"SELECT COUNT(*) FROM incidents {where_sql}", *params)

        rows = await conn.fetch(
            f"""
            SELECT id, camera_id, type, severity, confidence_score, source_count,
                   status, assigned_officer, snapshot_url,
                   ST_Y(location::geometry) as lat, ST_X(location::geometry) as lng,
                   occurred_at
            FROM incidents {where_sql}
            ORDER BY occurred_at DESC
            LIMIT {page_size} OFFSET {offset}
            """,
            *params
        )

        items = [
            IncidentPayload(
                id=str(row["id"]),
                camera_id=row["camera_id"] or "",
                type=row["type"],
                lat=row["lat"],
                lng=row["lng"],
                severity=row["severity"],
                confidence_score=row["confidence_score"],
                source_count=row["source_count"],
                status=row["status"],
                timestamp=row["occurred_at"].isoformat(),
                snapshot_url=row["snapshot_url"],
            )
            for row in rows
        ]
        return IncidentListResponse(items=items, total=total, page=page, page_size=page_size)
    finally:
        await conn.close()

@router.patch("/{incident_id}/status")
async def update_incident_status(incident_id: str, update: IncidentStatusUpdate):
    """Update status lifecycle sebuah incident. Publish ke WebSocket setelah update."""
    conn = await asyncpg.connect(os.getenv("DATABASE_URL").replace("+asyncpg", ""))
    try:
        now = datetime.now(timezone.utc)
        resolved_at = now if update.status in ("resolved", "closed") else None

        result = await conn.execute(
            """
            UPDATE incidents SET
                status = $1,
                assigned_officer = COALESCE($2, assigned_officer),
                assigned_at = CASE WHEN $1 = 'dispatched' THEN $4 ELSE assigned_at END,
                resolved_at = COALESCE($3, resolved_at),
                resolution_notes = COALESCE($5, resolution_notes),
                updated_at = $4
            WHERE id = $6
            """,
            update.status,
            update.assigned_officer,
            resolved_at,
            now,
            update.resolution_notes,
            incident_id,
        )

        if result == "UPDATE 0":
            raise HTTPException(status_code=404, detail="Incident tidak ditemukan")

        # Broadcast status update ke semua client WebSocket
        redis = await get_redis()
        await redis.publish("traffic.incident_update", json.dumps({
            "type": "incident_status_change",
            "payload": {
                "incident_id": incident_id,
                "status": update.status,
                "assigned_officer": update.assigned_officer,
                "updated_at": now.isoformat(),
            }
        }))

        return {"success": True, "incident_id": incident_id, "new_status": update.status}
    finally:
        await conn.close()

@router.get("/{incident_id}")
async def get_incident_detail(incident_id: str):
    """Detail lengkap satu incident termasuk timeline status."""
    conn = await asyncpg.connect(os.getenv("DATABASE_URL").replace("+asyncpg", ""))
    try:
        row = await conn.fetchrow(
            """
            SELECT id, camera_id, type, severity, confidence_score, source_count,
                   status, assigned_officer, assigned_at, resolved_at, resolution_notes,
                   snapshot_url, occurred_at, updated_at,
                   ST_Y(location::geometry) as lat, ST_X(location::geometry) as lng
            FROM incidents WHERE id = $1
            """,
            incident_id,
        )
        if not row:
            raise HTTPException(status_code=404, detail="Incident tidak ditemukan")
        return dict(row)
    finally:
        await conn.close()
```

**Edit file:** `backend/app/main.py` — tambahkan router:

```python
from app.routers import cameras, zones, events, websocket, incidents

app.include_router(incidents.router)
```

### 4.2 Frontend: Incident Panel Component

**Buat file:** `frontend/src/components/Dashboard/IncidentPanel.tsx`

```typescript
import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import axios from "axios";
import type { Incident } from "../../types";

const STATUS_CONFIG = {
  detected:   { label: "Terdeteksi",   color: "#FF4500", bg: "#1a0800" },
  confirmed:  { label: "Dikonfirmasi", color: "#FFA500", bg: "#1a1400" },
  dispatched: { label: "Dikirim",      color: "#00BFFF", bg: "#001a2e" },
  resolved:   { label: "Selesai",      color: "#00FF88", bg: "#001a0f" },
  closed:     { label: "Ditutup",      color: "#666",    bg: "#111"    },
};

const NEXT_STATUS: Record<string, string> = {
  detected: "confirmed",
  confirmed: "dispatched",
  dispatched: "resolved",
  resolved: "closed",
};

const NEXT_STATUS_LABEL: Record<string, string> = {
  detected: "Konfirmasi",
  confirmed: "Dispatch Petugas",
  dispatched: "Tandai Selesai",
  resolved: "Tutup",
};

const TYPE_LABELS: Record<string, string> = {
  illegal_parking: "Parkir Liar",
  busway_violation: "Pelanggaran Busway",
  congestion: "Kemacetan",
  wrong_way: "Lawan Arah",
  hazard_lights: "Lampu Hazard",
};

interface Props {
  onIncidentSelect?: (incident: Incident) => void;
}

export function IncidentPanel({ onIncidentSelect }: Props) {
  const [statusFilter, setStatusFilter] = useState<string>("detected");
  const [officerInput, setOfficerInput] = useState<Record<string, string>>({});
  const queryClient = useQueryClient();

  const { data, isLoading } = useQuery({
    queryKey: ["incidents", statusFilter],
    queryFn: () =>
      axios
        .get(`${import.meta.env.VITE_API_BASE_URL}/api/incidents/?status=${statusFilter}&page_size=20`)
        .then((r) => r.data),
    refetchInterval: 10000,
  });

  const updateStatus = useMutation({
    mutationFn: ({ incidentId, status, officer }: { incidentId: string; status: string; officer?: string }) =>
      axios.patch(`${import.meta.env.VITE_API_BASE_URL}/api/incidents/${incidentId}/status`, {
        incident_id: incidentId,
        status,
        assigned_officer: officer || null,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["incidents"] });
    },
  });

  return (
    <div style={{ padding: 16, display: "flex", flexDirection: "column", gap: 12 }}>
      {/* Filter tab */}
      <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
        {Object.entries(STATUS_CONFIG).map(([key, cfg]) => (
          <button
            key={key}
            onClick={() => setStatusFilter(key)}
            style={{
              padding: "4px 10px",
              border: `1px solid ${statusFilter === key ? cfg.color : "#333"}`,
              background: statusFilter === key ? cfg.bg : "transparent",
              color: statusFilter === key ? cfg.color : "#666",
              borderRadius: 6,
              fontSize: 11,
              cursor: "pointer",
            }}
          >
            {cfg.label}
          </button>
        ))}
      </div>

      {/* Daftar incidents */}
      {isLoading && <div style={{ color: "#555", fontSize: 12 }}>Memuat...</div>}
      <div style={{ display: "flex", flexDirection: "column", gap: 8, maxHeight: 420, overflowY: "auto" }}>
        {(data?.items ?? []).map((inc: Incident) => {
          const cfg = STATUS_CONFIG[inc.status];
          const nextStatus = NEXT_STATUS[inc.status];
          return (
            <div
              key={inc.id}
              style={{
                background: cfg.bg,
                border: `1px solid ${cfg.color}40`,
                borderLeft: `3px solid ${cfg.color}`,
                borderRadius: 8,
                padding: "10px 12px",
                cursor: "pointer",
              }}
              onClick={() => onIncidentSelect?.(inc)}
            >
              {/* Header */}
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <span style={{ color: "#fff", fontSize: 12, fontWeight: 600 }}>
                  {TYPE_LABELS[inc.type] || inc.type}
                </span>
                <span style={{
                  color: cfg.color, fontSize: 10, padding: "2px 6px",
                  border: `1px solid ${cfg.color}60`, borderRadius: 4,
                }}>
                  {cfg.label}
                </span>
              </div>

              {/* Confidence + source */}
              <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 6 }}>
                <div style={{ flex: 1, height: 3, background: "#222", borderRadius: 2, overflow: "hidden" }}>
                  <div style={{
                    width: `${inc.confidence_score * 100}%`,
                    height: "100%",
                    background: inc.confidence_score > 0.7 ? "#ff4500" : "#ffa500",
                  }} />
                </div>
                <span style={{ color: "#777", fontSize: 10 }}>
                  {Math.round(inc.confidence_score * 100)}% · {inc.source_count} sinyal
                </span>
              </div>

              {/* Waktu & kamera */}
              <div style={{ color: "#555", fontSize: 10, marginTop: 4 }}>
                {new Date(inc.timestamp).toLocaleString("id-ID")} · {inc.camera_id}
              </div>

              {/* Action */}
              {nextStatus && (
                <div
                  style={{ marginTop: 8, display: "flex", alignItems: "center", gap: 6 }}
                  onClick={(e) => e.stopPropagation()}
                >
                  {nextStatus === "dispatched" && (
                    <input
                      placeholder="Nama petugas..."
                      value={officerInput[inc.id] || ""}
                      onChange={(e) => setOfficerInput(prev => ({ ...prev, [inc.id]: e.target.value }))}
                      style={{
                        flex: 1, background: "#0a0a0f", border: "1px solid #333",
                        color: "#fff", borderRadius: 4, padding: "3px 8px", fontSize: 11,
                      }}
                    />
                  )}
                  <button
                    onClick={() => updateStatus.mutate({
                      incidentId: inc.id,
                      status: nextStatus,
                      officer: officerInput[inc.id],
                    })}
                    style={{
                      background: cfg.color + "22",
                      border: `1px solid ${cfg.color}60`,
                      color: cfg.color,
                      borderRadius: 4,
                      padding: "3px 10px",
                      fontSize: 11,
                      cursor: "pointer",
                    }}
                  >
                    {NEXT_STATUS_LABEL[inc.status]}
                  </button>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
```

---

## 5. Modul C — Violation Heatmap Dashboard (Spasial-Temporal)

### Konteks
Heatmap spasial-temporal menampilkan konsentrasi pelanggaran berdasarkan lokasi, jam, hari, dan tipe — serupa dengan analitik di Lanternn.

### 5.1 Backend: Endpoint Heatmap

**Buat file:** `backend/app/routers/analytics.py`

```python
from fastapi import APIRouter, Query
from typing import Optional
import asyncpg
import os
from datetime import datetime, date, timedelta

router = APIRouter(prefix="/api/analytics", tags=["analytics"])

@router.get("/heatmap")
async def get_heatmap_data(
    days: int = Query(30, ge=1, le=90),
    hour_from: int = Query(0, ge=0, le=23),
    hour_to: int = Query(23, ge=0, le=23),
    day_of_week: Optional[int] = Query(None, ge=0, le=6),  # 0=Minggu, 6=Sabtu
    violation_type: Optional[str] = Query(None),
):
    """Data heatmap untuk Mapbox GL JS heatmap layer."""
    conn = await asyncpg.connect(os.getenv("DATABASE_URL").replace("+asyncpg", ""))
    try:
        params = [days, hour_from, hour_to]
        where = [
            "incident_date >= CURRENT_DATE - $1 * INTERVAL '1 day'",
            "hour_of_day >= $2",
            "hour_of_day <= $3",
        ]
        idx = 4

        if day_of_week is not None:
            where.append(f"day_of_week = ${idx}")
            params.append(day_of_week)
            idx += 1

        if violation_type:
            where.append(f"type = ${idx}")
            params.append(violation_type)
            idx += 1

        where_sql = " AND ".join(where)

        rows = await conn.fetch(
            f"""
            SELECT lat, lng, type, severity, COUNT(*) as weight
            FROM violation_heatmap_data
            WHERE {where_sql}
            GROUP BY lat, lng, type, severity
            """,
            *params,
        )

        # Format GeoJSON FeatureCollection untuk Mapbox heatmap layer
        features = [
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [row["lng"], row["lat"]]},
                "properties": {
                    "weight": row["weight"],
                    "type": row["type"],
                    "severity": row["severity"],
                },
            }
            for row in rows
        ]

        return {
            "type": "FeatureCollection",
            "features": features,
            "meta": {"total_points": len(features), "days": days}
        }
    finally:
        await conn.close()

@router.get("/stats/by-hour")
async def get_stats_by_hour(days: int = Query(30, ge=1, le=90)):
    """Distribusi pelanggaran per jam untuk chart di Executive Summary."""
    conn = await asyncpg.connect(os.getenv("DATABASE_URL").replace("+asyncpg", ""))
    try:
        rows = await conn.fetch(
            """
            SELECT EXTRACT(HOUR FROM occurred_at)::INTEGER as hour,
                   COUNT(*) as count,
                   type
            FROM incidents
            WHERE occurred_at >= NOW() - $1 * INTERVAL '1 day'
            GROUP BY hour, type
            ORDER BY hour
            """,
            days,
        )
        result: dict[int, dict] = {h: {} for h in range(24)}
        for row in rows:
            result[row["hour"]][row["type"]] = row["count"]
        return result
    finally:
        await conn.close()

@router.get("/stats/summary")
async def get_summary_stats(days: int = Query(7, ge=1, le=90)):
    """Statistik ringkasan untuk Executive Summary panel."""
    conn = await asyncpg.connect(os.getenv("DATABASE_URL").replace("+asyncpg", ""))
    try:
        row = await conn.fetchrow(
            """
            SELECT
                COUNT(*)                                          AS total_incidents,
                COUNT(*) FILTER (WHERE severity = 'high')        AS high_severity,
                COUNT(*) FILTER (WHERE status = 'resolved')      AS resolved,
                AVG(confidence_score)                             AS avg_confidence,
                COUNT(DISTINCT DATE(occurred_at))                 AS active_days,
                EXTRACT(EPOCH FROM AVG(resolved_at - occurred_at))::INTEGER AS avg_response_s
            FROM incidents
            WHERE occurred_at >= NOW() - $1 * INTERVAL '1 day'
            """,
            days,
        )

        by_type = await conn.fetch(
            """
            SELECT type, COUNT(*) as count
            FROM incidents
            WHERE occurred_at >= NOW() - $1 * INTERVAL '1 day'
            GROUP BY type ORDER BY count DESC
            """,
            days,
        )

        return {
            "total_incidents": row["total_incidents"],
            "high_severity": row["high_severity"],
            "resolved": row["resolved"],
            "avg_confidence": round(float(row["avg_confidence"] or 0), 2),
            "avg_response_seconds": row["avg_response_s"],
            "by_type": {r["type"]: r["count"] for r in by_type},
        }
    finally:
        await conn.close()
```

### 5.2 Frontend: ViolationHeatmapLayer Component

**Buat file:** `frontend/src/components/Map/ViolationHeatmapLayer.tsx`

```typescript
import { useState, useEffect } from "react";
import { Source, Layer } from "react-map-gl";
import axios from "axios";

interface HeatmapFilters {
  days: number;
  hourFrom: number;
  hourTo: number;
  dayOfWeek?: number;
  violationType?: string;
}

interface Props {
  filters: HeatmapFilters;
  visible: boolean;
}

export function ViolationHeatmapLayer({ filters, visible }: Props) {
  const [geojson, setGeojson] = useState<GeoJSON.FeatureCollection | null>(null);

  useEffect(() => {
    if (!visible) return;
    const params = new URLSearchParams({
      days: String(filters.days),
      hour_from: String(filters.hourFrom),
      hour_to: String(filters.hourTo),
    });
    if (filters.dayOfWeek !== undefined) params.set("day_of_week", String(filters.dayOfWeek));
    if (filters.violationType) params.set("violation_type", filters.violationType);

    axios
      .get(`${import.meta.env.VITE_API_BASE_URL}/api/analytics/heatmap?${params}`)
      .then((r) => setGeojson(r.data));
  }, [filters, visible]);

  if (!visible || !geojson) return null;

  return (
    <Source id="violation-heatmap" type="geojson" data={geojson}>
      <Layer
        id="violation-heatmap-layer"
        type="heatmap"
        paint={{
          "heatmap-weight": ["interpolate", ["linear"], ["get", "weight"], 0, 0, 10, 1],
          "heatmap-intensity": ["interpolate", ["linear"], ["zoom"], 8, 1, 14, 3],
          "heatmap-color": [
            "interpolate", ["linear"], ["heatmap-density"],
            0, "rgba(0,0,255,0)",
            0.2, "rgb(0,200,255)",
            0.4, "rgb(0,255,100)",
            0.6, "rgb(255,200,0)",
            0.8, "rgb(255,100,0)",
            1, "rgb(255,0,0)",
          ],
          "heatmap-radius": ["interpolate", ["linear"], ["zoom"], 8, 15, 14, 30],
          "heatmap-opacity": 0.7,
        }}
      />
    </Source>
  );
}
```

**Buat file:** `frontend/src/components/Dashboard/HeatmapControls.tsx`

```typescript
import { useState } from "react";

const VIOLATION_TYPES = [
  { value: "", label: "Semua Tipe" },
  { value: "illegal_parking", label: "Parkir Liar" },
  { value: "busway_violation", label: "Pelanggaran Busway" },
  { value: "congestion", label: "Kemacetan" },
  { value: "wrong_way", label: "Lawan Arah" },
];

const DAY_LABELS = ["Min", "Sen", "Sel", "Rab", "Kam", "Jum", "Sab"];

interface HeatmapFilters {
  days: number;
  hourFrom: number;
  hourTo: number;
  dayOfWeek?: number;
  violationType?: string;
}

interface Props {
  filters: HeatmapFilters;
  onFiltersChange: (f: HeatmapFilters) => void;
  visible: boolean;
  onVisibilityToggle: () => void;
}

export function HeatmapControls({ filters, onFiltersChange, visible, onVisibilityToggle }: Props) {
  return (
    <div style={{
      padding: 12, background: "#0a0a0f",
      border: "1px solid #222", borderRadius: 8,
    }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 10 }}>
        <span style={{ color: "#FF6B00", fontSize: 12, fontWeight: 600 }}>🔥 Violation Heatmap</span>
        <button
          onClick={onVisibilityToggle}
          style={{
            background: visible ? "#FF6B0022" : "transparent",
            border: `1px solid ${visible ? "#FF6B00" : "#333"}`,
            color: visible ? "#FF6B00" : "#666",
            borderRadius: 4, padding: "2px 8px", fontSize: 11, cursor: "pointer",
          }}
        >
          {visible ? "Aktif" : "Non-aktif"}
        </button>
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
        {/* Rentang hari */}
        <div>
          <label style={{ color: "#777", fontSize: 10 }}>Rentang: {filters.days} hari terakhir</label>
          <input
            type="range" min={7} max={90} value={filters.days}
            onChange={(e) => onFiltersChange({ ...filters, days: +e.target.value })}
            style={{ width: "100%", marginTop: 2 }}
          />
        </div>

        {/* Filter jam */}
        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <label style={{ color: "#777", fontSize: 10, minWidth: 36 }}>Jam:</label>
          <select
            value={filters.hourFrom}
            onChange={(e) => onFiltersChange({ ...filters, hourFrom: +e.target.value })}
            style={{ background: "#111", color: "#fff", border: "1px solid #333", borderRadius: 4, fontSize: 11, padding: "2px 4px" }}
          >
            {Array.from({ length: 24 }, (_, i) => (
              <option key={i} value={i}>{String(i).padStart(2, "0")}:00</option>
            ))}
          </select>
          <span style={{ color: "#555", fontSize: 10 }}>s/d</span>
          <select
            value={filters.hourTo}
            onChange={(e) => onFiltersChange({ ...filters, hourTo: +e.target.value })}
            style={{ background: "#111", color: "#fff", border: "1px solid #333", borderRadius: 4, fontSize: 11, padding: "2px 4px" }}
          >
            {Array.from({ length: 24 }, (_, i) => (
              <option key={i} value={i}>{String(i).padStart(2, "0")}:00</option>
            ))}
          </select>
        </div>

        {/* Filter hari */}
        <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
          <button
            onClick={() => onFiltersChange({ ...filters, dayOfWeek: undefined })}
            style={{
              background: filters.dayOfWeek === undefined ? "#333" : "transparent",
              border: "1px solid #444", color: "#aaa",
              borderRadius: 4, padding: "2px 6px", fontSize: 10, cursor: "pointer",
            }}
          >
            Semua
          </button>
          {DAY_LABELS.map((label, idx) => (
            <button
              key={idx}
              onClick={() => onFiltersChange({ ...filters, dayOfWeek: filters.dayOfWeek === idx ? undefined : idx })}
              style={{
                background: filters.dayOfWeek === idx ? "#FF6B0033" : "transparent",
                border: `1px solid ${filters.dayOfWeek === idx ? "#FF6B00" : "#333"}`,
                color: filters.dayOfWeek === idx ? "#FF6B00" : "#777",
                borderRadius: 4, padding: "2px 6px", fontSize: 10, cursor: "pointer",
              }}
            >
              {label}
            </button>
          ))}
        </div>

        {/* Filter tipe */}
        <select
          value={filters.violationType || ""}
          onChange={(e) => onFiltersChange({ ...filters, violationType: e.target.value || undefined })}
          style={{
            background: "#111", color: "#fff", border: "1px solid #333",
            borderRadius: 4, fontSize: 11, padding: "4px 8px",
          }}
        >
          {VIOLATION_TYPES.map((t) => (
            <option key={t.value} value={t.value}>{t.label}</option>
          ))}
        </select>
      </div>
    </div>
  );
}
```

---

## 6. Modul D — Placement Simulator (E-TLE & Petugas)

### Konteks
Berdasarkan risk score dan pola pelanggaran, sistem merekomendasikan titik optimal untuk penempatan kamera E-TLE atau petugas lapangan.

### 6.1 Backend: Placement Calculator Service

**Buat file:** `backend/app/services/placement_calculator.py`

```python
import asyncpg
import os
from typing import Literal

async def calculate_placements(
    placement_type: Literal["camera_etle", "officer"],
    top_n: int = 10,
) -> list[dict]:
    """
    Hitung rekomendasi titik penempatan berdasarkan risk_zones.
    Harus dijalankan setelah calculate_risk_zones() berjalan.
    """
    conn = await asyncpg.connect(os.getenv("DATABASE_URL").replace("+asyncpg", ""))
    try:
        rows = await conn.fetch(
            """
            SELECT
                ST_Y(location::geometry) AS lat,
                ST_X(location::geometry) AS lng,
                risk_score,
                violation_types,
                incident_count,
                peak_hours,
                peak_days,
                radius_m
            FROM risk_zones
            ORDER BY risk_score DESC
            LIMIT $1
            """,
            top_n,
        )

        results = []
        for rank, row in enumerate(rows, start=1):
            v_types = list(row["violation_types"] or [])
            peak_hours = list(row["peak_hours"] or [])

            # Buat rationale berdasarkan data
            hour_desc = ""
            if peak_hours:
                peak_hours_sorted = sorted(peak_hours)
                hour_desc = f"puncak jam {peak_hours_sorted[0]:02d}:00–{peak_hours_sorted[-1]:02d}:00"

            rationale = (
                f"Titik dengan {row['incident_count']} insiden dalam 30 hari. "
                f"Dominan: {', '.join(v_types)}. {hour_desc}. "
                f"Risk score: {row['risk_score']:.2f}."
            )

            # Tentukan coverage radius berdasarkan tipe
            coverage = 150.0 if placement_type == "camera_etle" else 300.0

            results.append({
                "location": {"lat": row["lat"], "lng": row["lng"]},
                "recommendation_type": placement_type,
                "priority_rank": rank,
                "risk_score": row["risk_score"],
                "violation_types": v_types,
                "coverage_radius_m": coverage,
                "rationale": rationale,
                "peak_hours": peak_hours,
            })

        return results
    finally:
        await conn.close()
```

**Buat file:** `backend/app/routers/simulator.py`

```python
from fastapi import APIRouter, Query
from typing import Literal
from app.services.placement_calculator import calculate_placements

router = APIRouter(prefix="/api/simulator", tags=["simulator"])

@router.get("/placements")
async def get_placement_recommendations(
    type: Literal["camera_etle", "officer"] = Query("camera_etle"),
    top_n: int = Query(10, ge=1, le=50),
):
    """
    Rekomendasi titik penempatan E-TLE atau petugas lapangan.
    Respons: list titik dengan risk score, rationale, dan violation types.
    """
    results = await calculate_placements(placement_type=type, top_n=top_n)
    return {
        "type": type,
        "recommendations": results,
        "total": len(results),
    }
```

**Edit** `backend/app/main.py`:

```python
from app.routers import cameras, zones, events, websocket, incidents, analytics, simulator

app.include_router(analytics.router)
app.include_router(simulator.router)
```

### 6.2 Frontend: Simulator Panel & Map Layer

**Buat file:** `frontend/src/components/Map/PlacementLayer.tsx`

```typescript
import { useState } from "react";
import { Marker, Popup } from "react-map-gl";
import { useQuery } from "@tanstack/react-query";
import axios from "axios";

interface Placement {
  location: { lat: number; lng: number };
  recommendation_type: "camera_etle" | "officer";
  priority_rank: number;
  risk_score: number;
  violation_types: string[];
  coverage_radius_m: number;
  rationale: string;
  peak_hours: number[];
}

interface Props {
  type: "camera_etle" | "officer";
  visible: boolean;
}

export function PlacementLayer({ type, visible }: Props) {
  const [selected, setSelected] = useState<Placement | null>(null);

  const { data } = useQuery({
    queryKey: ["placements", type],
    queryFn: () =>
      axios
        .get(`${import.meta.env.VITE_API_BASE_URL}/api/simulator/placements?type=${type}&top_n=15`)
        .then((r) => r.data.recommendations as Placement[]),
    enabled: visible,
  });

  if (!visible) return null;

  const icon = type === "camera_etle" ? "📸" : "👮";
  const color = type === "camera_etle" ? "#00d4ff" : "#FFD700";

  return (
    <>
      {(data ?? []).map((placement, idx) => (
        <Marker
          key={idx}
          longitude={placement.location.lng}
          latitude={placement.location.lat}
          anchor="center"
          onClick={(e) => {
            e.originalEvent.stopPropagation();
            setSelected(placement);
          }}
        >
          <div
            style={{
              background: "#0f1117",
              border: `2px solid ${color}`,
              borderRadius: "50%",
              width: 32, height: 32,
              display: "flex", alignItems: "center", justifyContent: "center",
              fontSize: 14, cursor: "pointer",
              boxShadow: `0 0 10px ${color}66`,
            }}
            title={`Prioritas #${placement.priority_rank} — Risk ${Math.round(placement.risk_score * 100)}%`}
          >
            {icon}
          </div>
        </Marker>
      ))}

      {selected && (
        <Popup
          longitude={selected.location.lng}
          latitude={selected.location.lat}
          anchor="bottom"
          onClose={() => setSelected(null)}
          style={{ maxWidth: 280 }}
        >
          <div style={{ background: "#0f1117", color: "#fff", padding: 12, borderRadius: 8, fontSize: 12 }}>
            <div style={{ color, fontWeight: 600, marginBottom: 6 }}>
              {icon} Rekomendasi #{selected.priority_rank} — {type === "camera_etle" ? "E-TLE" : "Petugas"}
            </div>
            <div style={{ color: "#aaa", marginBottom: 4 }}>
              Risk score: <span style={{ color }}>{Math.round(selected.risk_score * 100)}%</span>
            </div>
            <div style={{ color: "#888", fontSize: 11, marginBottom: 6 }}>
              {selected.rationale}
            </div>
            <div style={{ color: "#666", fontSize: 10 }}>
              Coverage: {selected.coverage_radius_m}m radius
            </div>
          </div>
        </Popup>
      )}
    </>
  );
}
```

---

## 7. Modul E — Executive Summary & Reporting

### Konteks
Panel ringkasan untuk stakeholder: statistik harian, tren, dan laporan PDF untuk pelaporan rutin.

### 7.1 Backend: Report Generator

**Tambahkan ke** `requirements.txt`:
```
reportlab==4.2.0
```

**Buat file:** `backend/app/services/report_generator.py`

```python
import asyncpg
import os
from datetime import date, timedelta
from io import BytesIO
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm

async def generate_daily_report_pdf(report_date: date) -> bytes:
    """Generate laporan PDF harian untuk stakeholder."""
    conn = await asyncpg.connect(os.getenv("DATABASE_URL").replace("+asyncpg", ""))
    try:
        # Ambil statistik hari itu
        stats = await conn.fetchrow(
            """
            SELECT
                COUNT(*) AS total,
                COUNT(*) FILTER (WHERE severity = 'high')    AS high,
                COUNT(*) FILTER (WHERE severity = 'medium')  AS medium,
                COUNT(*) FILTER (WHERE severity = 'low')     AS low,
                COUNT(*) FILTER (WHERE status = 'resolved')  AS resolved,
                AVG(confidence_score) AS avg_confidence
            FROM incidents
            WHERE DATE(occurred_at) = $1
            """,
            report_date,
        )

        by_type = await conn.fetch(
            """
            SELECT type, COUNT(*) as count
            FROM incidents WHERE DATE(occurred_at) = $1
            GROUP BY type ORDER BY count DESC
            """,
            report_date,
        )

        top_hours = await conn.fetch(
            """
            SELECT EXTRACT(HOUR FROM occurred_at)::INTEGER as hour, COUNT(*) as count
            FROM incidents WHERE DATE(occurred_at) = $1
            GROUP BY hour ORDER BY count DESC LIMIT 5
            """,
            report_date,
        )

    finally:
        await conn.close()

    # Buat PDF
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=2*cm, leftMargin=2*cm,
                             topMargin=2*cm, bottomMargin=2*cm)
    styles = getSampleStyleSheet()
    story = []

    title_style = ParagraphStyle("title", parent=styles["Heading1"],
                                  fontSize=18, spaceAfter=6)
    subtitle_style = ParagraphStyle("subtitle", parent=styles["Normal"],
                                     fontSize=10, textColor=colors.grey, spaceAfter=20)
    section_style = ParagraphStyle("section", parent=styles["Heading2"],
                                    fontSize=13, spaceAfter=8, spaceBefore=14)

    story.append(Paragraph("Laporan Harian Pemantauan Lalu Lintas", title_style))
    story.append(Paragraph(f"Tanggal: {report_date.strftime('%d %B %Y')}", subtitle_style))

    # Ringkasan
    story.append(Paragraph("Ringkasan Eksekutif", section_style))
    summary_data = [
        ["Metrik", "Nilai"],
        ["Total Insiden Terdeteksi", str(stats["total"] or 0)],
        ["Insiden Selesai Ditangani", str(stats["resolved"] or 0)],
        ["Tingkat Penyelesaian", f"{(stats['resolved'] or 0) / max(stats['total'] or 1, 1) * 100:.1f}%"],
        ["Severity Tinggi", str(stats["high"] or 0)],
        ["Severity Sedang", str(stats["medium"] or 0)],
        ["Severity Rendah", str(stats["low"] or 0)],
        ["Rata-rata Confidence Score", f"{(stats['avg_confidence'] or 0) * 100:.1f}%"],
    ]
    summary_table = Table(summary_data, colWidths=[10*cm, 6*cm])
    summary_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1a1a2e")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#333")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8f8f8")]),
    ]))
    story.append(summary_table)

    # Distribusi per tipe
    story.append(Paragraph("Distribusi Per Tipe Pelanggaran", section_style))
    type_labels = {
        "illegal_parking": "Parkir Liar",
        "busway_violation": "Pelanggaran Busway",
        "congestion": "Kemacetan",
        "wrong_way": "Lawan Arah",
        "hazard_lights": "Lampu Hazard",
    }
    type_data = [["Tipe Pelanggaran", "Jumlah"]]
    for row in by_type:
        type_data.append([type_labels.get(row["type"], row["type"]), str(row["count"])])

    if len(type_data) > 1:
        type_table = Table(type_data, colWidths=[10*cm, 6*cm])
        type_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#FF6B00")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#ccc")),
        ]))
        story.append(type_table)

    # Jam rawan
    story.append(Paragraph("Jam Rawan (Top 5)", section_style))
    hour_data = [["Jam", "Jumlah Insiden"]]
    for row in top_hours:
        hour_data.append([f"{row['hour']:02d}:00 – {row['hour']:02d}:59", str(row["count"])])

    if len(hour_data) > 1:
        hour_table = Table(hour_data, colWidths=[10*cm, 6*cm])
        hour_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#9B59B6")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#ccc")),
        ]))
        story.append(hour_table)

    story.append(Spacer(1, 20))
    story.append(Paragraph(
        "Dokumen ini digenerate secara otomatis oleh sistem Traffic Intelligence Dashboard.",
        ParagraphStyle("footer", parent=styles["Normal"], fontSize=8, textColor=colors.grey),
    ))

    doc.build(story)
    return buffer.getvalue()
```

**Buat file:** `backend/app/routers/reports.py`

```python
from fastapi import APIRouter
from fastapi.responses import Response
from datetime import date
from app.services.report_generator import generate_daily_report_pdf

router = APIRouter(prefix="/api/reports", tags=["reports"])

@router.get("/daily/{report_date}")
async def get_daily_report_pdf(report_date: date):
    """Download laporan PDF harian. Format tanggal: YYYY-MM-DD."""
    pdf_bytes = await generate_daily_report_pdf(report_date)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="laporan_{report_date}.pdf"'
        },
    )
```

**Tambahkan** ke `backend/app/main.py`:
```python
from app.routers import reports
app.include_router(reports.router)
```

### 7.2 Frontend: Executive Summary Panel

**Buat file:** `frontend/src/components/Dashboard/ExecutiveSummaryPanel.tsx`

```typescript
import { useQuery } from "@tanstack/react-query";
import axios from "axios";
import { format, subDays } from "date-fns";
import { id } from "date-fns/locale";

interface SummaryStats {
  total_incidents: number;
  high_severity: number;
  resolved: number;
  avg_confidence: number;
  avg_response_seconds: number;
  by_type: Record<string, number>;
}

const TYPE_LABELS: Record<string, string> = {
  illegal_parking: "Parkir Liar",
  busway_violation: "Pelanggaran Busway",
  congestion: "Kemacetan",
  wrong_way: "Lawan Arah",
};

export function ExecutiveSummaryPanel() {
  const today = format(new Date(), "yyyy-MM-dd");

  const { data: stats } = useQuery<SummaryStats>({
    queryKey: ["summary-stats"],
    queryFn: () =>
      axios
        .get(`${import.meta.env.VITE_API_BASE_URL}/api/analytics/stats/summary?days=7`)
        .then((r) => r.data),
    refetchInterval: 60000,
  });

  const resolutionRate = stats
    ? Math.round((stats.resolved / Math.max(stats.total_incidents, 1)) * 100)
    : 0;

  const avgResponseMin = stats?.avg_response_seconds
    ? Math.round(stats.avg_response_seconds / 60)
    : null;

  return (
    <div style={{ padding: 16, display: "flex", flexDirection: "column", gap: 12 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <span style={{ color: "#9B59B6", fontSize: 12, fontWeight: 600 }}>
          📊 Ringkasan 7 Hari
        </span>
        <a
          href={`${import.meta.env.VITE_API_BASE_URL}/api/reports/daily/${today}`}
          target="_blank"
          rel="noreferrer"
          style={{
            color: "#9B59B6", fontSize: 10,
            textDecoration: "none", border: "1px solid #9B59B660",
            padding: "2px 8px", borderRadius: 4,
          }}
        >
          ↓ PDF Hari Ini
        </a>
      </div>

      {/* Metric cards */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
        {[
          { label: "Total Insiden", value: stats?.total_incidents ?? "—", color: "#fff" },
          { label: "Tingkat Selesai", value: `${resolutionRate}%`, color: "#00FF88" },
          { label: "Severity Tinggi", value: stats?.high_severity ?? "—", color: "#FF4500" },
          { label: "Avg Response", value: avgResponseMin ? `${avgResponseMin} menit` : "—", color: "#00BFFF" },
        ].map((metric) => (
          <div
            key={metric.label}
            style={{
              background: "#0a0a0f", border: "1px solid #222",
              borderRadius: 8, padding: "10px 12px",
            }}
          >
            <div style={{ color: metric.color, fontSize: 18, fontWeight: 700 }}>
              {metric.value}
            </div>
            <div style={{ color: "#555", fontSize: 10, marginTop: 2 }}>{metric.label}</div>
          </div>
        ))}
      </div>

      {/* Distribusi tipe */}
      {stats?.by_type && (
        <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
          <span style={{ color: "#777", fontSize: 10 }}>Distribusi pelanggaran</span>
          {Object.entries(stats.by_type).map(([type, count]) => {
            const pct = Math.round((count / Math.max(stats.total_incidents, 1)) * 100);
            return (
              <div key={type}>
                <div style={{ display: "flex", justifyContent: "space-between", fontSize: 10, color: "#aaa", marginBottom: 2 }}>
                  <span>{TYPE_LABELS[type] || type}</span>
                  <span>{count} ({pct}%)</span>
                </div>
                <div style={{ height: 4, background: "#111", borderRadius: 2, overflow: "hidden" }}>
                  <div style={{ width: `${pct}%`, height: "100%", background: "#FF6B00", borderRadius: 2 }} />
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
```

---

## 8. Modul F — Dynamic Congestion Prediction (Event Integration)

### Konteks
Prediksi kemacetan dinamis berdasarkan event yang akan datang. Sistem mengintegrasikan data dari sumber eksternal (Tiket.com scraper, data.jakarta.go.id) dan menampilkan prediksi rute terdampak sebagai overlay di peta.

### 8.1 Backend: Event Scraper Worker

**Buat file:** `backend/app/services/event_scraper.py`

```python
import asyncio
import asyncpg
import os
import httpx
from datetime import date, timedelta

# -------------------------------------------------------
# Sumber 1: data.jakarta.go.id open data
# Dataset titik rawan kemacetan tersedia di:
# https://data.jakarta.go.id/dataset/titik-rawan-kemacetan-di-dki-jakarta
# -------------------------------------------------------
JAKARTA_OPENDATA_BASE = "https://data.jakarta.go.id"

# -------------------------------------------------------
# Sumber 2: Google Places API untuk venue events
# (opsional — membutuhkan API key di .env sebagai GOOGLE_PLACES_KEY)
# -------------------------------------------------------

# -------------------------------------------------------
# Seed data: event-event besar Jakarta yang berulang tahunan
# Update manual daftar ini setiap kuartal
# -------------------------------------------------------
RECURRING_EVENTS = [
    {
        "external_id": "jakarta-fair-annual",
        "source": "manual",
        "name": "Pekan Raya Jakarta (Jakarta Fair)",
        "venue": "Jakarta International Expo Kemayoran",
        "lat": -6.146, "lng": 106.845,
        "estimated_crowd": 100000,
        "category": "fair",
    },
    {
        "external_id": "jakarta-marathon-annual",
        "source": "manual",
        "name": "Jakarta Marathon",
        "venue": "Monas & sekitar Sudirman",
        "lat": -6.1754, "lng": 106.8272,
        "estimated_crowd": 31000,
        "category": "marathon",
    },
    {
        "external_id": "gbk-concert-template",
        "source": "manual",
        "name": "Konser GBK (template)",
        "venue": "Gelora Bung Karno",
        "lat": -6.2183, "lng": 106.8018,
        "estimated_crowd": 80000,
        "category": "concert",
    },
    {
        "external_id": "jis-concert-template",
        "source": "manual",
        "name": "Jakarta International Stadium (template)",
        "venue": "Jakarta International Stadium",
        "lat": -6.1275, "lng": 106.8676,
        "estimated_crowd": 50000,
        "category": "concert",
    },
]

async def scrape_and_store_events():
    """
    Tugas scraping harian. Jalankan melalui cron job atau APScheduler.
    Saat ini menggunakan seed data manual. Tambahkan integrasi API sesuai kebutuhan.
    
    Untuk integrasi Tiket.com / Loket.com:
    - Cek terms of service sebelum scraping
    - Alternatif: gunakan Google Calendar API untuk venue resmi
    - Atau: integrasi manual input via admin panel
    """
    conn = await asyncpg.connect(os.getenv("DATABASE_URL").replace("+asyncpg", ""))
    try:
        for event in RECURRING_EVENTS:
            await conn.execute(
                """
                INSERT INTO external_events
                    (external_id, source, name, venue, location, estimated_crowd, category, is_verified)
                VALUES
                    ($1, $2, $3, $4, ST_SetSRID(ST_MakePoint($6, $5), 4326)::geography, $7, $8, true)
                ON CONFLICT (external_id) DO UPDATE SET
                    name = EXCLUDED.name,
                    scraped_at = NOW()
                """,
                event["external_id"],
                event["source"],
                event["name"],
                event["venue"],
                event["lat"],
                event["lng"],
                event["estimated_crowd"],
                event["category"],
            )
    finally:
        await conn.close()
```

### 8.2 Backend: Dynamic Congestion Predictor

**Buat file:** `backend/app/services/congestion_predictor.py`

```python
import asyncpg
import os
import json
from datetime import datetime, timezone, timedelta
from math import radians, cos, sin, asin, sqrt

def _haversine_km(lat1, lng1, lat2, lng2) -> float:
    R = 6371
    lat1, lng1, lat2, lng2 = map(radians, [lat1, lng1, lat2, lng2])
    dlat = lat2 - lat1
    dlng = lng2 - lng1
    a = sin(dlat/2)**2 + cos(lat1)*cos(lat2)*sin(dlng/2)**2
    return R * 2 * asin(sqrt(a))

# Konfigurasi dampak berdasarkan jumlah massa
IMPACT_CONFIG = {
    "critical": {"min_crowd": 50000, "radius_km": 2.5, "hours_before": 3, "hours_after": 2},
    "high":     {"min_crowd": 20000, "radius_km": 1.5, "hours_before": 2, "hours_after": 1},
    "medium":   {"min_crowd": 5000,  "radius_km": 1.0, "hours_before": 1, "hours_after": 1},
}

# Titik rawan kemacetan di Jakarta (dari data.jakarta.go.id) — seed statis
# Update dari: https://data.jakarta.go.id/dataset/titik-rawan-kemacetan-di-dki-jakarta
CONGESTION_HOTSPOTS = [
    {"name": "Bundaran HI", "lat": -6.1944, "lng": 106.8229},
    {"name": "Semanggi", "lat": -6.2088, "lng": 106.8228},
    {"name": "Blok M", "lat": -6.2441, "lng": 106.7993},
    {"name": "Tanah Abang", "lat": -6.1867, "lng": 106.8226},
    {"name": "Grogol", "lat": -6.1676, "lng": 106.7965},
    {"name": "Cawang", "lat": -6.2432, "lng": 106.8678},
    {"name": "Pancoran", "lat": -6.2418, "lng": 106.8339},
    {"name": "Kuningan", "lat": -6.2289, "lng": 106.8284},
    {"name": "Mampang", "lat": -6.2540, "lng": 106.8204},
    {"name": "TB Simatupang", "lat": -6.2993, "lng": 106.7964},
    {"name": "Tanjung Priok", "lat": -6.1082, "lng": 106.8795},
    {"name": "Kemayoran", "lat": -6.1574, "lng": 106.8454},
]

def _get_impact_level(crowd: int) -> str:
    if crowd >= IMPACT_CONFIG["critical"]["min_crowd"]:
        return "critical"
    if crowd >= IMPACT_CONFIG["high"]["min_crowd"]:
        return "high"
    if crowd >= IMPACT_CONFIG["medium"]["min_crowd"]:
        return "medium"
    return "low"

def predict_event_congestion(event: dict) -> dict:
    """
    Hitung prediksi kemacetan untuk sebuah event.
    Return: prediction payload siap publish ke Redis.
    """
    crowd = event.get("estimated_crowd", 0)
    level = _get_impact_level(crowd)

    if level == "low":
        return None

    cfg = IMPACT_CONFIG[level]
    event_lat = event["lat"]
    event_lng = event["lng"]

    # Filter hotspot yang berada dalam radius dampak
    affected_segments = []
    for hotspot in CONGESTION_HOTSPOTS:
        dist = _haversine_km(event_lat, event_lng, hotspot["lat"], hotspot["lng"])
        if dist <= cfg["radius_km"]:
            congestion_level = "critical" if dist <= cfg["radius_km"] * 0.4 else \
                               "high" if dist <= cfg["radius_km"] * 0.7 else "medium"
            color = {"critical": "#FF0000", "high": "#FF4500", "medium": "#FFA500"}[congestion_level]

            affected_segments.append({
                "name": hotspot["name"],
                "lat": hotspot["lat"],
                "lng": hotspot["lng"],
                "congestion_level": congestion_level,
                "color": color,
                "distance_km": round(dist, 2),
            })

    # Buat rekomendasi mitigasi
    mitigation_actions = [
        {"action": f"Siagakan petugas di radius {cfg['radius_km']} km dari {event.get('venue', 'venue')}", "priority": 1},
        {"action": f"Aktifkan rekayasa lalu lintas H-{cfg['hours_before']} jam sebelum acara", "priority": 2},
        {"action": "Tambah armada TransJakarta koridor terdekat", "priority": 3},
    ]
    for seg in affected_segments[:3]:
        mitigation_actions.append({
            "action": f"Pantau titik {seg['name']} — estimasi dampak {seg['congestion_level']}",
            "priority": 4,
            "location": {"lat": seg["lat"], "lng": seg["lng"]},
        })

    # Waktu dampak
    now = datetime.now(timezone.utc)
    event_time_str = event.get("event_time") or "19:00"
    impact_start = now  # simplified — dalam produksi parse dari event date+time
    impact_end = impact_start + timedelta(hours=cfg["hours_before"] + cfg["hours_after"])

    return {
        "type": "event_prediction",
        "payload": {
            "event_id": event.get("id", "unknown"),
            "event_name": event.get("name", ""),
            "impact_level": level,
            "impact_start": impact_start.isoformat(),
            "impact_end": impact_end.isoformat(),
            "affected_segments": affected_segments,
            "mitigation_actions": mitigation_actions,
            "confidence": 0.75 if level == "critical" else 0.6,
        }
    }
```

**Edit** `backend/app/routers/events.py` — tambahkan endpoint prediksi dinamis:

```python
# Tambahkan import
from app.services.congestion_predictor import predict_event_congestion
from app.services.redis_client import get_redis
import json

@router.post("/{event_id}/trigger-prediction")
async def trigger_event_prediction(event_id: str):
    """
    Trigger prediksi kemacetan untuk event tertentu dan publish ke WebSocket.
    Dipanggil manual oleh operator atau otomatis oleh scheduler.
    """
    event = next((e.model_dump() for e in EVENTS if e.id == event_id), None)
    if not event:
        return {"error": "Event tidak ditemukan"}

    # Tambahkan lat/lng ke event dict
    event_dict = {**event, "lat": event["lat"], "lng": event["lng"]}
    prediction = predict_event_congestion(event_dict)

    if prediction:
        redis = await get_redis()
        await redis.publish("traffic.event_prediction", json.dumps(prediction))
        return {"success": True, "prediction": prediction["payload"]}

    return {"success": False, "message": "Event terlalu kecil untuk prediksi"}
```

### 8.3 Frontend: EventPrediction Map Overlay

**Buat file:** `frontend/src/components/Map/EventPredictionOverlay.tsx`

```typescript
import { Marker, Popup } from "react-map-gl";
import { useState } from "react";
import type { EventPrediction } from "../../types";

const CONGESTION_COLORS = {
  critical: "#FF0000",
  high: "#FF4500",
  medium: "#FFA500",
};

interface Props {
  predictions: EventPrediction[];
}

export function EventPredictionOverlay({ predictions }: Props) {
  const [selected, setSelected] = useState<any>(null);

  if (!predictions.length) return null;

  return (
    <>
      {predictions.flatMap((pred) =>
        pred.affected_segments.map((seg: any, idx: number) => (
          <Marker
            key={`${pred.event_id}-${idx}`}
            longitude={seg.lng}
            latitude={seg.lat}
            anchor="center"
            onClick={(e) => {
              e.originalEvent.stopPropagation();
              setSelected({ pred, seg });
            }}
          >
            <div
              style={{
                width: 20, height: 20, borderRadius: "50%",
                background: CONGESTION_COLORS[seg.congestion_level as keyof typeof CONGESTION_COLORS] + "44",
                border: `2px solid ${CONGESTION_COLORS[seg.congestion_level as keyof typeof CONGESTION_COLORS]}`,
                animation: "pulse 2s infinite",
              }}
            />
          </Marker>
        ))
      )}

      {selected && (
        <Popup
          longitude={selected.seg.lng}
          latitude={selected.seg.lat}
          anchor="bottom"
          onClose={() => setSelected(null)}
          maxWidth="260px"
        >
          <div style={{ background: "#0f1117", color: "#fff", padding: 12, borderRadius: 8, fontSize: 11 }}>
            <div style={{ color: CONGESTION_COLORS[selected.seg.congestion_level as keyof typeof CONGESTION_COLORS], fontWeight: 600, marginBottom: 4 }}>
              ⚠ {selected.seg.name}
            </div>
            <div style={{ color: "#aaa", marginBottom: 4 }}>
              Dampak dari: {selected.pred.event_name}
            </div>
            <div style={{ color: "#666", fontSize: 10 }}>
              Level: {selected.seg.congestion_level.toUpperCase()} · {selected.seg.distance_km} km dari venue
            </div>
          </div>
        </Popup>
      )}
    </>
  );
}
```

---

## 9. Modul G — Risk Profiling Layer

### Konteks
Heatmap titik rawan berdasarkan akumulasi data historis. Berbeda dari violation heatmap (live), risk profiling adalah output yang dikomputasi secara periodik dan menampilkan potensi risiko ke depan.

### 9.1 Backend: Risk Profiling API

**Tambahkan ke** `backend/app/routers/analytics.py`:

```python
@router.get("/risk-zones")
async def get_risk_zones():
    """Titik rawan hasil kalkulasi risk profiling."""
    conn = await asyncpg.connect(os.getenv("DATABASE_URL").replace("+asyncpg", ""))
    try:
        rows = await conn.fetch(
            """
            SELECT
                ST_Y(location::geometry) AS lat,
                ST_X(location::geometry) AS lng,
                risk_score,
                violation_types,
                incident_count,
                peak_hours
            FROM risk_zones
            ORDER BY risk_score DESC
            LIMIT 100
            """
        )

        features = [
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [row["lng"], row["lat"]]},
                "properties": {
                    "risk_score": row["risk_score"],
                    "violation_types": list(row["violation_types"] or []),
                    "incident_count": row["incident_count"],
                    "peak_hours": list(row["peak_hours"] or []),
                    "weight": row["risk_score"],
                },
            }
            for row in rows
        ]

        return {"type": "FeatureCollection", "features": features}
    finally:
        await conn.close()

@router.post("/risk-zones/recalculate")
async def recalculate_risk_zones():
    """
    Trigger kalkulasi ulang risk zones. Panggil dari scheduler harian (misal jam 02:00 WIB).
    Atau panggil manual dari admin panel.
    """
    conn = await asyncpg.connect(os.getenv("DATABASE_URL").replace("+asyncpg", ""))
    try:
        await conn.execute("SELECT calculate_risk_zones()")
        count = await conn.fetchval("SELECT COUNT(*) FROM risk_zones")
        return {"success": True, "risk_zones_count": count}
    finally:
        await conn.close()
```

### 9.2 Frontend: Risk Zone Layer

**Buat file:** `frontend/src/components/Map/RiskZoneLayer.tsx`

```typescript
import { useState, useEffect } from "react";
import { Source, Layer } from "react-map-gl";
import axios from "axios";

interface Props {
  visible: boolean;
}

export function RiskZoneLayer({ visible }: Props) {
  const [geojson, setGeojson] = useState<GeoJSON.FeatureCollection | null>(null);

  useEffect(() => {
    if (!visible) return;
    axios
      .get(`${import.meta.env.VITE_API_BASE_URL}/api/analytics/risk-zones`)
      .then((r) => setGeojson(r.data));
  }, [visible]);

  if (!visible || !geojson) return null;

  return (
    <Source id="risk-zones" type="geojson" data={geojson}>
      <Layer
        id="risk-zones-heatmap"
        type="heatmap"
        paint={{
          "heatmap-weight": ["get", "weight"],
          "heatmap-intensity": 1.5,
          "heatmap-color": [
            "interpolate", ["linear"], ["heatmap-density"],
            0, "rgba(100, 0, 200, 0)",
            0.3, "rgba(150, 0, 255, 0.4)",
            0.6, "rgba(200, 50, 200, 0.6)",
            0.8, "rgba(255, 50, 50, 0.7)",
            1, "rgba(255, 0, 0, 0.9)",
          ],
          "heatmap-radius": 30,
          "heatmap-opacity": 0.6,
        }}
      />
    </Source>
  );
}
```

---

## 10. Modul H — Operator Workflow UI (Incident Single-View)

### Konteks
Saat incident diklik di peta atau di panel, membuka tampilan terpusat: info incident, CCTV feed kamera terkait, tombol aksi lifecycle, dan log aktivitas — semua dalam satu modal.

**Buat file:** `frontend/src/components/Modals/IncidentDetailModal.tsx`

```typescript
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import ReactPlayer from "react-player";
import axios from "axios";
import type { Incident } from "../../types";

const TYPE_LABELS: Record<string, string> = {
  illegal_parking: "Parkir Liar",
  busway_violation: "Pelanggaran Busway",
  congestion: "Kemacetan",
  wrong_way: "Lawan Arah",
  hazard_lights: "Lampu Hazard",
};

const STATUS_CONFIG: Record<string, { label: string; color: string }> = {
  detected:   { label: "Terdeteksi",   color: "#FF4500" },
  confirmed:  { label: "Dikonfirmasi", color: "#FFA500" },
  dispatched: { label: "Dikirim",      color: "#00BFFF" },
  resolved:   { label: "Selesai",      color: "#00FF88" },
  closed:     { label: "Ditutup",      color: "#666" },
};

const NEXT_STATUS: Record<string, string> = {
  detected: "confirmed",
  confirmed: "dispatched",
  dispatched: "resolved",
  resolved: "closed",
};

interface Props {
  incident: Incident;
  cameras: Array<{ id: string; name: string; stream_url?: string }>;
  onClose: () => void;
}

export function IncidentDetailModal({ incident, cameras, onClose }: Props) {
  const queryClient = useQueryClient();

  const { data: detail } = useQuery({
    queryKey: ["incident-detail", incident.id],
    queryFn: () =>
      axios
        .get(`${import.meta.env.VITE_API_BASE_URL}/api/incidents/${incident.id}`)
        .then((r) => r.data),
  });

  const updateStatus = useMutation({
    mutationFn: (status: string) =>
      axios.patch(`${import.meta.env.VITE_API_BASE_URL}/api/incidents/${incident.id}/status`, {
        incident_id: incident.id,
        status,
      }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["incidents"] }),
  });

  const camera = cameras.find((c) => c.id === incident.camera_id);
  const cfg = STATUS_CONFIG[incident.status] || STATUS_CONFIG["detected"];
  const nextStatus = NEXT_STATUS[incident.status];

  return (
    <div
      onClick={onClose}
      style={{
        position: "absolute", inset: 0,
        background: "rgba(0,0,0,0.8)",
        display: "flex", alignItems: "center", justifyContent: "center",
        zIndex: 2000,
      }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          background: "#0f1117",
          border: `1px solid ${cfg.color}40`,
          borderTop: `3px solid ${cfg.color}`,
          borderRadius: 12,
          padding: 20,
          width: 580,
          maxHeight: "90vh",
          overflowY: "auto",
        }}
      >
        {/* Header */}
        <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 16 }}>
          <div>
            <div style={{ color: "#fff", fontWeight: 600, fontSize: 16 }}>
              {TYPE_LABELS[incident.type] || incident.type}
            </div>
            <div style={{ color: "#555", fontSize: 11, marginTop: 2 }}>
              ID: {incident.id.substring(0, 8)}... · {new Date(incident.timestamp).toLocaleString("id-ID")}
            </div>
          </div>
          <div style={{ display: "flex", gap: 8, alignItems: "flex-start" }}>
            <span style={{
              color: cfg.color, fontSize: 11, padding: "3px 8px",
              border: `1px solid ${cfg.color}60`, borderRadius: 4,
            }}>
              {cfg.label}
            </span>
            <button
              onClick={onClose}
              style={{ background: "none", border: "1px solid #333", color: "#666", borderRadius: 4, padding: "3px 8px", cursor: "pointer", fontSize: 11 }}
            >
              ✕
            </button>
          </div>
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
          {/* Kiri: Info incident */}
          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            {/* Confidence */}
            <div style={{ background: "#111", borderRadius: 8, padding: 12 }}>
              <div style={{ color: "#777", fontSize: 11, marginBottom: 6 }}>Confidence Score</div>
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <div style={{ flex: 1, height: 6, background: "#222", borderRadius: 3, overflow: "hidden" }}>
                  <div style={{
                    width: `${incident.confidence_score * 100}%`,
                    height: "100%",
                    background: incident.confidence_score > 0.7 ? "#ff4500" : "#ffa500",
                    borderRadius: 3,
                  }} />
                </div>
                <span style={{ color: "#fff", fontSize: 14, fontWeight: 600 }}>
                  {Math.round(incident.confidence_score * 100)}%
                </span>
              </div>
              <div style={{ color: "#555", fontSize: 10, marginTop: 4 }}>
                {incident.source_count} sinyal digabungkan
              </div>
            </div>

            {/* Detail */}
            {[
              { label: "Kamera", value: camera?.name || incident.camera_id },
              { label: "Severity", value: incident.severity.toUpperCase() },
              { label: "Koordinat", value: `${incident.lat.toFixed(5)}, ${incident.lng.toFixed(5)}` },
              ...(detail?.assigned_officer ? [{ label: "Petugas", value: detail.assigned_officer }] : []),
              ...(detail?.resolved_at ? [{ label: "Diselesaikan", value: new Date(detail.resolved_at).toLocaleString("id-ID") }] : []),
            ].map(({ label, value }) => (
              <div key={label} style={{ display: "flex", justifyContent: "space-between", fontSize: 11 }}>
                <span style={{ color: "#555" }}>{label}</span>
                <span style={{ color: "#aaa", textAlign: "right", maxWidth: 160 }}>{value}</span>
              </div>
            ))}

            {/* Aksi lifecycle */}
            {nextStatus && (
              <button
                onClick={() => updateStatus.mutate(nextStatus)}
                disabled={updateStatus.isPending}
                style={{
                  background: cfg.color + "22",
                  border: `1px solid ${cfg.color}`,
                  color: cfg.color,
                  borderRadius: 6, padding: "8px 12px",
                  fontSize: 12, cursor: "pointer", fontWeight: 600,
                }}
              >
                {updateStatus.isPending ? "Memproses..." : `→ ${STATUS_CONFIG[nextStatus]?.label}`}
              </button>
            )}
          </div>

          {/* Kanan: CCTV feed */}
          <div>
            <div style={{ color: "#777", fontSize: 11, marginBottom: 6 }}>
              Live Feed — {camera?.name || "Kamera tidak diketahui"}
            </div>
            {camera?.stream_url ? (
              <ReactPlayer
                url={camera.stream_url}
                playing muted loop
                width="100%" height="160px"
                style={{ borderRadius: 6, overflow: "hidden", background: "#000" }}
              />
            ) : (
              <div style={{
                height: 160, background: "#111", borderRadius: 6,
                display: "flex", alignItems: "center", justifyContent: "center",
                color: "#444", fontSize: 12,
              }}>
                Feed tidak tersedia
              </div>
            )}

            {/* Snapshot jika ada */}
            {incident.snapshot_url && (
              <div style={{ marginTop: 8 }}>
                <div style={{ color: "#777", fontSize: 10, marginBottom: 4 }}>Snapshot saat deteksi</div>
                <img
                  src={incident.snapshot_url}
                  alt="Snapshot"
                  style={{ width: "100%", borderRadius: 6, objectFit: "cover", maxHeight: 120 }}
                />
              </div>
            )}
          </div>
        </div>

        {/* Resolution notes */}
        {incident.status === "dispatched" && (
          <div style={{ marginTop: 16 }}>
            <textarea
              placeholder="Catatan resolusi..."
              style={{
                width: "100%", background: "#111", border: "1px solid #333",
                color: "#fff", borderRadius: 6, padding: "8px 10px",
                fontSize: 11, resize: "vertical", minHeight: 60,
                boxSizing: "border-box",
              }}
            />
          </div>
        )}
      </div>
    </div>
  );
}
```

---

## 11. Integrasi External Data Sources

### 11.1 Scheduler (APScheduler)

**Tambahkan ke** `requirements.txt`:
```
apscheduler==3.10.4
```

**Edit** `backend/app/main.py` — tambahkan scheduler:

```python
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from app.services.event_scraper import scrape_and_store_events
import asyncpg, os

scheduler = AsyncIOScheduler()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Jalankan Redis listener
    redis_task = asyncio.create_task(redis_listener())

    # Jadwal scraping event — setiap hari jam 03:00 WIB
    scheduler.add_job(scrape_and_store_events, "cron", hour=3, minute=0)

    # Jadwal kalkulasi risk zones — setiap hari jam 02:00 WIB
    async def recalc_risk():
        conn = await asyncpg.connect(os.getenv("DATABASE_URL").replace("+asyncpg", ""))
        await conn.execute("SELECT calculate_risk_zones()")
        await conn.close()

    scheduler.add_job(recalc_risk, "cron", hour=2, minute=0)
    scheduler.start()

    yield

    redis_task.cancel()
    scheduler.shutdown()
```

### 11.2 Sumber Data Jakarta yang Bisa Diintegrasikan

| Sumber | URL | Data | Cara Akses |
|--------|-----|------|-----------|
| Open Data Jakarta | `satudata.jakarta.go.id` | Titik rawan kemacetan | Download CSV manual atau HTTP |
| BMKG | `data.bmkg.go.id/api/v1/stasiun/` | Cuaca real-time | REST API publik |
| Transjakarta | `transjakarta.co.id` | Jadwal & kepadatan | Hubungi pengelola untuk API |
| Google Maps Distance Matrix | via `maps.googleapis.com` | Estimasi kepadatan rute | API Key berbayar |

---

## 12. Acceptance Criteria Keseluruhan

Setiap item harus diverifikasi sebelum dokumen ini dianggap selesai dieksekusi.

### Modul A — Confidence Scoring
- [ ] Violation dari CV worker dengan koordinat dalam 150m dan tipe sama digabungkan jadi satu incident
- [ ] Field `confidence_score` muncul di payload WebSocket, nilai antara 0.0–1.0
- [ ] Field `source_count` bertambah ketika duplikat diterima
- [ ] Confidence bar tampil di `NotificationPanel` dan berubah warna berdasarkan nilai

### Modul B — Incident Lifecycle
- [ ] `GET /api/incidents/` mengembalikan list dengan filter `status`
- [ ] `PATCH /api/incidents/{id}/status` mengubah status dan broadcast ke WebSocket
- [ ] `IncidentPanel` menampilkan tombol aksi sesuai status saat ini
- [ ] Status change terbroadcast dan panel update tanpa refresh halaman

### Modul C — Violation Heatmap
- [ ] `GET /api/analytics/heatmap` mengembalikan GeoJSON FeatureCollection
- [ ] Filter hari, jam, tipe, dan rentang waktu berfungsi
- [ ] Layer heatmap tampil di peta Mapbox saat toggle diaktifkan
- [ ] `HeatmapControls` dapat mengubah filter dan heatmap update

### Modul D — Placement Simulator
- [ ] `GET /api/simulator/placements?type=camera_etle` mengembalikan rekomendasi
- [ ] Marker simulator tampil di peta dengan ikon berbeda per tipe
- [ ] Klik marker menampilkan popup dengan rationale dan risk score

### Modul E — Executive Summary
- [ ] `GET /api/analytics/stats/summary` mengembalikan statistik 7 hari
- [ ] `ExecutiveSummaryPanel` menampilkan metric cards dan distribusi tipe
- [ ] `GET /api/reports/daily/YYYY-MM-DD` mengunduh PDF valid
- [ ] PDF berisi ringkasan, distribusi tipe, dan jam rawan

### Modul F — Event Prediction
- [ ] `POST /api/events/{id}/trigger-prediction` mempublish ke Redis `traffic.event_prediction`
- [ ] Frontend menerima event prediction via WebSocket dan update state
- [ ] `EventPredictionOverlay` menampilkan marker berwarna di titik terdampak
- [ ] Klik marker menampilkan popup dengan nama event dan level dampak

### Modul G — Risk Profiling
- [ ] `SELECT calculate_risk_zones()` dapat dijalankan tanpa error
- [ ] `GET /api/analytics/risk-zones` mengembalikan GeoJSON FeatureCollection
- [ ] `RiskZoneLayer` tampil di peta sebagai heatmap ungu-merah saat toggle aktif
- [ ] `POST /api/analytics/risk-zones/recalculate` berjalan tanpa error

### Modul H — Operator Workflow
- [ ] Klik marker di peta membuka `IncidentDetailModal`
- [ ] Modal menampilkan confidence score, status, dan CCTV feed
- [ ] Tombol aksi dalam modal mengubah status dan menutup modal setelah sukses
- [ ] Modal tidak menutup saat diklik di dalam area konten

---

*Dokumen ini bersifat living document. Update field `seed data` untuk events dan congestion hotspots secara berkala sesuai kondisi lapangan Jakarta.*