# Traffic Dashboard — Project Setup Guide

Stack: React + TypeScript · Mapbox GL JS · FastAPI · Redis · PostgreSQL + PostGIS

> Guide ini fokus pada dashboard, data pipeline real-time, dan simulasi data.
> Integrasi CV Worker dilakukan terpisah dan cukup publish ke Redis topic yang sudah didefinisikan di sini.

---

## Daftar Isi

1. [Prerequisites & Tools](#1-prerequisites--tools)
2. [Struktur Project](#2-struktur-project)
3. [Setup Infrastructure (Docker)](#3-setup-infrastructure-docker)
4. [Setup Backend (FastAPI)](#4-setup-backend-fastapi)
5. [Setup Frontend (React + TypeScript)](#5-setup-frontend-react--typescript)
6. [Konfigurasi Mapbox & Layer Peta](#6-konfigurasi-mapbox--layer-peta)
7. [Real-time Pipeline (Redis → WebSocket → Map)](#7-real-time-pipeline-redis--websocket--map)
8. [Data Simulator (Pengganti CV Worker)](#8-data-simulator-pengganti-cv-worker)
9. [Fitur CCTV Modal](#9-fitur-cctv-modal)
10. [Modul Event & Mitigasi](#10-modul-event--mitigasi)
11. [Notifikasi Real-time](#11-notifikasi-real-time)
12. [Database Schema](#12-database-schema)
13. [Checklist Prototype](#13-checklist-prototype)

---

## 1. Prerequisites & Tools

Install semua tool berikut sebelum mulai:

| Tool | Versi minimum | Cek instalasi |
|---|---|---|
| Node.js | 20.x LTS | `node --version` |
| Python | 3.11+ | `python --version` |
| Docker Desktop | terbaru | `docker --version` |
| Git | terbaru | `git --version` |

Akun yang dibutuhkan:
- **Mapbox** → daftar di mapbox.com, ambil *Public Access Token* dari dashboard (gratis, 50k tile loads/bulan)
- Tidak perlu akun lain untuk prototype

---

## 2. Struktur Project

Buat folder root project, lalu susun seperti ini:

```
traffic-dashboard/
├── backend/               # FastAPI
│   ├── app/
│   │   ├── main.py
│   │   ├── routers/
│   │   │   ├── cameras.py
│   │   │   ├── events.py
│   │   │   ├── zones.py
│   │   │   └── websocket.py
│   │   ├── services/
│   │   │   ├── redis_client.py
│   │   │   └── event_predictor.py
│   │   └── models/
│   │       └── schemas.py
│   ├── requirements.txt
│   └── .env
│
├── frontend/              # React + TypeScript
│   ├── src/
│   │   ├── components/
│   │   │   ├── Map/
│   │   │   │   ├── MapContainer.tsx
│   │   │   │   ├── CameraMarkers.tsx
│   │   │   │   ├── ViolationMarkers.tsx
│   │   │   │   ├── ZonePolygons.tsx
│   │   │   │   └── EventOverlay.tsx
│   │   │   ├── Dashboard/
│   │   │   │   ├── NotificationPanel.tsx
│   │   │   │   ├── EventMitigationPanel.tsx
│   │   │   │   └── StatusBar.tsx
│   │   │   └── Modals/
│   │   │       └── CCTVModal.tsx
│   │   ├── hooks/
│   │   │   ├── useWebSocket.ts
│   │   │   └── useNotifications.ts
│   │   ├── types/
│   │   │   └── index.ts
│   │   ├── services/
│   │   │   └── api.ts
│   │   └── App.tsx
│   ├── .env.local
│   └── package.json
│
├── simulator/             # Data simulator (pengganti CV worker)
│   ├── simulator.py
│   └── requirements.txt
│
└── docker-compose.yml
```

Inisialisasi project dari terminal:

```bash
mkdir traffic-dashboard && cd traffic-dashboard
mkdir -p backend/app/{routers,services,models}
mkdir -p frontend/src/{components/{Map,Dashboard,Modals},hooks,types,services}
mkdir simulator
git init
```

---

## 3. Setup Infrastructure (Docker)

Buat file `docker-compose.yml` di root project. File ini menjalankan Redis dan PostgreSQL sekaligus — tidak perlu install manual.

```yaml
# docker-compose.yml
version: '3.8'

services:
  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data
    command: redis-server --save 60 1

  postgres:
    image: postgis/postgis:16-3.4-alpine
    ports:
      - "5432:5432"
    environment:
      POSTGRES_DB: traffic_db
      POSTGRES_USER: traffic_user
      POSTGRES_PASSWORD: traffic_pass
    volumes:
      - postgres_data:/var/lib/postgresql/data

volumes:
  redis_data:
  postgres_data:
```

Jalankan infrastruktur:

```bash
docker compose up -d

# Verifikasi keduanya running
docker compose ps
```

---

## 4. Setup Backend (FastAPI)

### 4.1 Environment & Dependencies

```bash
cd backend
python -m venv venv
source venv/bin/activate       # Windows: venv\Scripts\activate
```

Buat `requirements.txt`:

```
fastapi==0.111.0
uvicorn[standard]==0.29.0
redis==5.0.4
asyncpg==0.29.0
sqlalchemy[asyncio]==2.0.30
psycopg2-binary==2.9.9
python-dotenv==1.0.1
pydantic==2.7.1
geoalchemy2==0.15.1
```

```bash
pip install -r requirements.txt
```

Buat file `.env` di folder `backend/`:

```env
DATABASE_URL=postgresql+asyncpg://traffic_user:traffic_pass@localhost:5432/traffic_db
REDIS_URL=redis://localhost:6379
ALLOWED_ORIGINS=http://localhost:5173
```

### 4.2 Schemas (Tipe Data)

```python
# backend/app/models/schemas.py
from pydantic import BaseModel
from typing import Optional, Literal
from datetime import datetime

class Camera(BaseModel):
    id: str
    name: str
    lat: float
    lng: float
    stream_url: Optional[str] = None  # URL video MP4 lokal atau HLS stream

class Zone(BaseModel):
    id: str
    name: str
    type: Literal["illegal_parking", "busway_corridor", "event_impact"]
    color: str                        # hex color, misal "#FF6B00"
    coordinates: list[list[float]]    # array of [lng, lat] untuk GeoJSON polygon

class Violation(BaseModel):
    id: str
    camera_id: str
    type: Literal["illegal_parking", "busway_violation", "congestion"]
    lat: float
    lng: float
    severity: Literal["low", "medium", "high"]
    timestamp: datetime
    snapshot_url: Optional[str] = None

class Event(BaseModel):
    id: str
    name: str
    venue: str
    lat: float
    lng: float
    date: str
    time: str
    estimated_crowd: int
    impact_radius_km: float

class CongestionSegment(BaseModel):
    segment_id: str
    score: int                        # 0-100
    color: Literal["green", "yellow", "orange", "red"]
    coordinates: list[list[float]]    # [[lng1,lat1],[lng2,lat2]]
```

### 4.3 Redis Client

```python
# backend/app/services/redis_client.py
import redis.asyncio as aioredis
import os

redis_client: aioredis.Redis = None

async def get_redis() -> aioredis.Redis:
    global redis_client
    if redis_client is None:
        redis_client = await aioredis.from_url(
            os.getenv("REDIS_URL", "redis://localhost:6379"),
            decode_responses=True
        )
    return redis_client
```

### 4.4 WebSocket Router

Ini adalah komponen terpenting: menerima data dari Redis Pub/Sub dan meneruskannya ke semua browser yang terhubung.

```python
# backend/app/routers/websocket.py
import asyncio
import json
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from app.services.redis_client import get_redis

router = APIRouter()

# Menyimpan semua koneksi WebSocket yang aktif
active_connections: list[WebSocket] = []

# Topic Redis yang didengarkan backend
SUBSCRIBED_TOPICS = [
    "traffic.violation",
    "traffic.congestion",
    "traffic.alert",
]

async def broadcast(message: str):
    """Kirim pesan ke semua client yang sedang terhubung."""
    disconnected = []
    for connection in active_connections:
        try:
            await connection.send_text(message)
        except Exception:
            disconnected.append(connection)
    for conn in disconnected:
        active_connections.remove(conn)

async def redis_listener():
    """Background task: subscribe ke Redis dan forward semua pesan ke WebSocket."""
    redis = await get_redis()
    pubsub = redis.pubsub()
    await pubsub.subscribe(*SUBSCRIBED_TOPICS)

    async for message in pubsub.listen():
        if message["type"] == "message":
            await broadcast(message["data"])

@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    active_connections.append(websocket)
    try:
        while True:
            # Tetap jaga koneksi terbuka, data dikirim dari redis_listener
            await asyncio.sleep(30)
            await websocket.send_text(json.dumps({"type": "ping"}))
    except WebSocketDisconnect:
        active_connections.remove(websocket)
```

### 4.5 Router: Cameras & Zones

```python
# backend/app/routers/cameras.py
from fastapi import APIRouter
from app.models.schemas import Camera

router = APIRouter(prefix="/api/cameras", tags=["cameras"])

# Data statis untuk prototype — nanti pindah ke database
CAMERAS: list[Camera] = [
    Camera(id="cam-001", name="Bundaran HI", lat=-6.1944, lng=106.8229,
           stream_url="/videos/cam001.mp4"),
    Camera(id="cam-002", name="Semanggi", lat=-6.2088, lng=106.8228,
           stream_url="/videos/cam002.mp4"),
    Camera(id="cam-003", name="Blok M", lat=-6.2441, lng=106.7993,
           stream_url="/videos/cam003.mp4"),
    Camera(id="cam-004", name="Sarinah", lat=-6.1867, lng=106.8226,
           stream_url="/videos/cam004.mp4"),
]

@router.get("/", response_model=list[Camera])
async def get_cameras():
    return CAMERAS
```

```python
# backend/app/routers/zones.py
from fastapi import APIRouter
from app.models.schemas import Zone

router = APIRouter(prefix="/api/zones", tags=["zones"])

ZONES: list[Zone] = [
    Zone(
        id="zone-busway-1",
        name="Koridor Transjakarta — Sudirman",
        type="busway_corridor",
        color="#FF6B00",
        coordinates=[
            [106.8200, -6.1800], [106.8210, -6.1800],
            [106.8210, -6.2100], [106.8200, -6.2100],
        ]
    ),
    Zone(
        id="zone-parking-1",
        name="Zona Rawan Parkir Liar — Tanah Abang",
        type="illegal_parking",
        color="#FFD700",
        coordinates=[
            [106.8130, -6.1870], [106.8160, -6.1870],
            [106.8160, -6.1900], [106.8130, -6.1900],
        ]
    ),
]

@router.get("/", response_model=list[Zone])
async def get_zones():
    return ZONES
```

### 4.6 Router: Events & Predictor

```python
# backend/app/routers/events.py
from fastapi import APIRouter
from app.models.schemas import Event
from app.services.event_predictor import generate_mitigation

router = APIRouter(prefix="/api/events", tags=["events"])

# Seed data event Jakarta — isi manual untuk prototype
EVENTS: list[Event] = [
    Event(
        id="evt-001",
        name="Konser Coldplay Jakarta",
        venue="GBK",
        lat=-6.2183,
        lng=106.8018,
        date="2026-07-15",
        time="19:00",
        estimated_crowd=80000,
        impact_radius_km=2.5,
    ),
    Event(
        id="evt-002",
        name="Final Piala Indonesia",
        venue="JIS",
        lat=-6.1275,
        lng=106.8676,
        date="2026-07-20",
        time="20:00",
        estimated_crowd=50000,
        impact_radius_km=2.0,
    ),
]

@router.get("/", response_model=list[Event])
async def get_events():
    return EVENTS

@router.get("/{event_id}/mitigation")
async def get_event_mitigation(event_id: str):
    event = next((e for e in EVENTS if e.id == event_id), None)
    if not event:
        return {"error": "Event tidak ditemukan"}
    return generate_mitigation(event)
```

```python
# backend/app/services/event_predictor.py
from app.models.schemas import Event

def generate_mitigation(event: Event) -> dict:
    """
    Rule-based predictor untuk prototype.
    Nanti bisa diganti dengan model ML.
    """
    crowd = event.estimated_crowd
    radius = event.impact_radius_km

    if crowd >= 50000:
        impact_level = "KRITIS"
        congestion_hours_before = 3
        congestion_hours_after = 2
    elif crowd >= 20000:
        impact_level = "TINGGI"
        congestion_hours_before = 2
        congestion_hours_after = 1
    else:
        impact_level = "SEDANG"
        congestion_hours_before = 1
        congestion_hours_after = 1

    recommendations = [
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
        "affected_radius_km": radius,
        "recommendations": recommendations,
        "predicted_congestion_start": f"H-{congestion_hours_before} jam sebelum {event.time}",
        "predicted_congestion_end": f"H+{congestion_hours_after} jam setelah {event.time}",
    }
```

### 4.7 Main Application

```python
# backend/app/main.py
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
import os

from app.routers import cameras, zones, events, websocket
from app.routers.websocket import redis_listener

load_dotenv()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Jalankan Redis listener sebagai background task
    task = asyncio.create_task(redis_listener())
    yield
    task.cancel()

app = FastAPI(title="Traffic Dashboard API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[os.getenv("ALLOWED_ORIGINS", "http://localhost:5173")],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(cameras.router)
app.include_router(zones.router)
app.include_router(events.router)
app.include_router(websocket.router)

@app.get("/health")
async def health():
    return {"status": "ok"}
```

Jalankan backend:

```bash
cd backend
uvicorn app.main:app --reload --port 8000
```

Buka `http://localhost:8000/docs` untuk melihat semua API endpoint tersedia.

---

## 5. Setup Frontend (React + TypeScript)

### 5.1 Inisialisasi Project

```bash
cd frontend
npm create vite@latest . -- --template react-ts
npm install
```

Install dependencies:

```bash
npm install mapbox-gl @types/mapbox-gl
npm install react-map-gl
npm install @tanstack/react-query axios
npm install zustand                      # state management ringan
npm install react-player                 # video player untuk CCTV modal
npm install date-fns                     # utility tanggal untuk modul event
npm install lucide-react                 # icon set
```

### 5.2 Environment Variables

Buat `.env.local` di folder `frontend/`:

```env
VITE_MAPBOX_TOKEN=pk.xxxxxxxxxxxxxxxx    # ganti dengan token Anda dari mapbox.com
VITE_API_BASE_URL=http://localhost:8000
VITE_WS_URL=ws://localhost:8000/ws
```

### 5.3 Type Definitions

```typescript
// frontend/src/types/index.ts

export interface Camera {
  id: string;
  name: string;
  lat: number;
  lng: number;
  stream_url?: string;
}

export interface Zone {
  id: string;
  name: string;
  type: "illegal_parking" | "busway_corridor" | "event_impact";
  color: string;
  coordinates: [number, number][];
}

export interface Violation {
  id: string;
  camera_id: string;
  type: "illegal_parking" | "busway_violation" | "congestion";
  lat: number;
  lng: number;
  severity: "low" | "medium" | "high";
  timestamp: string;
  snapshot_url?: string;
}

export interface WSMessage {
  type: "violation" | "congestion" | "alert" | "ping";
  payload?: Violation | CongestionUpdate | AlertPayload;
}

export interface CongestionUpdate {
  segment_id: string;
  score: number;
  color: "green" | "yellow" | "orange" | "red";
  coordinates: [number, number][];
}

export interface AlertPayload {
  message: string;
  severity: "info" | "warning" | "critical";
}

export interface Event {
  id: string;
  name: string;
  venue: string;
  lat: number;
  lng: number;
  date: string;
  time: string;
  estimated_crowd: number;
  impact_radius_km: number;
}

export interface Mitigation {
  event_id: string;
  event_name: string;
  impact_level: string;
  affected_radius_km: number;
  recommendations: string[];
  predicted_congestion_start: string;
  predicted_congestion_end: string;
}
```

### 5.4 API Service

```typescript
// frontend/src/services/api.ts
import axios from "axios";
import type { Camera, Zone, Event, Mitigation } from "../types";

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL,
});

export const getCameras = (): Promise<Camera[]> =>
  api.get("/api/cameras").then((r) => r.data);

export const getZones = (): Promise<Zone[]> =>
  api.get("/api/zones").then((r) => r.data);

export const getEvents = (): Promise<Event[]> =>
  api.get("/api/events").then((r) => r.data);

export const getEventMitigation = (eventId: string): Promise<Mitigation> =>
  api.get(`/api/events/${eventId}/mitigation`).then((r) => r.data);
```

---

## 6. Konfigurasi Mapbox & Layer Peta

### 6.1 WebSocket Hook

```typescript
// frontend/src/hooks/useWebSocket.ts
import { useEffect, useRef, useCallback } from "react";
import type { WSMessage } from "../types";

export function useWebSocket(onMessage: (msg: WSMessage) => void) {
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeout = useRef<ReturnType<typeof setTimeout>>();

  const connect = useCallback(() => {
    const ws = new WebSocket(import.meta.env.VITE_WS_URL);
    wsRef.current = ws;

    ws.onmessage = (event) => {
      try {
        const data: WSMessage = JSON.parse(event.data);
        if (data.type !== "ping") onMessage(data);
      } catch (e) {
        console.error("WS parse error:", e);
      }
    };

    ws.onclose = () => {
      // Auto-reconnect setelah 3 detik jika koneksi putus
      reconnectTimeout.current = setTimeout(connect, 3000);
    };

    return () => ws.close();
  }, [onMessage]);

  useEffect(() => {
    const cleanup = connect();
    return () => {
      cleanup();
      clearTimeout(reconnectTimeout.current);
    };
  }, [connect]);
}
```

### 6.2 Map Container

```typescript
// frontend/src/components/Map/MapContainer.tsx
import { useState, useCallback } from "react";
import Map, { NavigationControl, ScaleControl } from "react-map-gl";
import "mapbox-gl/dist/mapbox-gl.css";

import { CameraMarkers } from "./CameraMarkers";
import { ViolationMarkers } from "./ViolationMarkers";
import { ZonePolygons } from "./ZonePolygons";
import { CCTVModal } from "../Modals/CCTVModal";
import { useWebSocket } from "../../hooks/useWebSocket";
import type { Camera, Violation, WSMessage } from "../../types";

// Jakarta center
const INITIAL_VIEW = {
  longitude: 106.8456,
  latitude: -6.2088,
  zoom: 12,
};

interface Props {
  cameras: Camera[];
  zones: any[];
}

export function MapContainer({ cameras, zones }: Props) {
  const [violations, setViolations] = useState<Violation[]>([]);
  const [selectedCamera, setSelectedCamera] = useState<Camera | null>(null);

  const handleWSMessage = useCallback((msg: WSMessage) => {
    if (msg.type === "violation" && msg.payload) {
      const violation = msg.payload as Violation;
      setViolations((prev) => {
        // Simpan max 50 violation terakhir di peta
        const updated = [violation, ...prev].slice(0, 50);
        return updated;
      });
    }
  }, []);

  useWebSocket(handleWSMessage);

  return (
    <div style={{ width: "100%", height: "100vh", position: "relative" }}>
      <Map
        mapboxAccessToken={import.meta.env.VITE_MAPBOX_TOKEN}
        initialViewState={INITIAL_VIEW}
        style={{ width: "100%", height: "100%" }}
        mapStyle="mapbox://styles/mapbox/dark-v11"
      >
        <NavigationControl position="top-right" />
        <ScaleControl position="bottom-right" />

        {/* Layer 1: Zona rawan (polygon) */}
        <ZonePolygons zones={zones} />

        {/* Layer 2: Marker kamera CCTV */}
        <CameraMarkers
          cameras={cameras}
          onCameraClick={setSelectedCamera}
        />

        {/* Layer 3: Marker pelanggaran real-time */}
        <ViolationMarkers violations={violations} />
      </Map>

      {/* Modal CCTV — muncul saat kamera diklik */}
      {selectedCamera && (
        <CCTVModal
          camera={selectedCamera}
          onClose={() => setSelectedCamera(null)}
        />
      )}
    </div>
  );
}
```

### 6.3 Zone Polygons

```typescript
// frontend/src/components/Map/ZonePolygons.tsx
import { Source, Layer } from "react-map-gl";
import type { Zone } from "../../types";

// Warna per tipe zona
const ZONE_COLORS: Record<Zone["type"], string> = {
  illegal_parking: "#FFD700",
  busway_corridor: "#FF6B00",
  event_impact: "#9B59B6",
};

interface Props {
  zones: Zone[];
}

export function ZonePolygons({ zones }: Props) {
  return (
    <>
      {zones.map((zone) => {
        const geojson: GeoJSON.Feature = {
          type: "Feature",
          properties: { name: zone.name },
          geometry: {
            type: "Polygon",
            coordinates: [zone.coordinates],
          },
        };

        return (
          <Source key={zone.id} id={zone.id} type="geojson" data={geojson}>
            {/* Fill transparan */}
            <Layer
              id={`${zone.id}-fill`}
              type="fill"
              paint={{
                "fill-color": ZONE_COLORS[zone.type],
                "fill-opacity": 0.15,
              }}
            />
            {/* Border zona */}
            <Layer
              id={`${zone.id}-border`}
              type="line"
              paint={{
                "line-color": ZONE_COLORS[zone.type],
                "line-width": 2,
                "line-dasharray": [2, 1],
              }}
            />
          </Source>
        );
      })}
    </>
  );
}
```

### 6.4 Camera Markers

```typescript
// frontend/src/components/Map/CameraMarkers.tsx
import { Marker } from "react-map-gl";
import type { Camera } from "../../types";

interface Props {
  cameras: Camera[];
  onCameraClick: (camera: Camera) => void;
}

export function CameraMarkers({ cameras, onCameraClick }: Props) {
  return (
    <>
      {cameras.map((camera) => (
        <Marker
          key={camera.id}
          longitude={camera.lng}
          latitude={camera.lat}
          anchor="center"
          onClick={(e) => {
            e.originalEvent.stopPropagation();
            onCameraClick(camera);
          }}
        >
          <div
            title={camera.name}
            style={{
              cursor: "pointer",
              background: "#1a1a2e",
              border: "2px solid #00d4ff",
              borderRadius: "50%",
              width: 28,
              height: 28,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              fontSize: 14,
              transition: "transform 0.15s",
            }}
            onMouseEnter={(e) =>
              (e.currentTarget.style.transform = "scale(1.2)")
            }
            onMouseLeave={(e) => (e.currentTarget.style.transform = "scale(1)")}
          >
            📷
          </div>
        </Marker>
      ))}
    </>
  );
}
```

### 6.5 Violation Markers

```typescript
// frontend/src/components/Map/ViolationMarkers.tsx
import { Marker } from "react-map-gl";
import type { Violation } from "../../types";

const SEVERITY_COLORS = {
  low: "#FFA500",
  medium: "#FF4500",
  high: "#FF0000",
};

interface Props {
  violations: Violation[];
}

export function ViolationMarkers({ violations }: Props) {
  return (
    <>
      {violations.map((v) => (
        <Marker
          key={v.id}
          longitude={v.lng}
          latitude={v.lat}
          anchor="center"
        >
          <div
            style={{
              width: 16,
              height: 16,
              borderRadius: "50%",
              background: SEVERITY_COLORS[v.severity],
              border: "2px solid white",
              boxShadow: `0 0 8px ${SEVERITY_COLORS[v.severity]}`,
              animation: "pulse 1.5s infinite",
            }}
            title={`${v.type} — ${v.severity}`}
          />
        </Marker>
      ))}

      {/* Animasi pulse untuk marker pelanggaran */}
      <style>{`
        @keyframes pulse {
          0%   { transform: scale(1);   opacity: 1; }
          50%  { transform: scale(1.4); opacity: 0.7; }
          100% { transform: scale(1);   opacity: 1; }
        }
      `}</style>
    </>
  );
}
```

---

## 7. Real-time Pipeline (Redis → WebSocket → Map)

Alur datanya:

```
CV Worker / Simulator
        │
        │  redis.publish("traffic.violation", JSON.stringify(payload))
        ▼
   Redis Pub/Sub
        │
        │  Backend (FastAPI) subscribe → redis_listener()
        ▼
   WebSocket Server
        │
        │  ws.send_text(message) ke semua koneksi aktif
        ▼
   Browser (React)
        │
        │  useWebSocket hook → onMessage callback
        ▼
   State update → marker muncul di peta
```

Format payload yang harus dipatuhi oleh CV Worker saat publish ke Redis:

```json
{
  "type": "violation",
  "payload": {
    "id": "viol-uuid-001",
    "camera_id": "cam-001",
    "type": "busway_violation",
    "lat": -6.1944,
    "lng": 106.8229,
    "severity": "high",
    "timestamp": "2026-06-09T10:30:00Z",
    "snapshot_url": "/snapshots/cam001_1234.jpg"
  }
}
```

> **Catatan untuk integrasi CV Worker:** Cukup publish JSON sesuai format di atas ke topic `traffic.violation` di Redis. Dashboard akan otomatis menerima dan menampilkannya.

---

## 8. Data Simulator (Pengganti CV Worker)

Gunakan ini selama CV Worker belum siap. Simulator akan publish data violation palsu ke Redis secara berkala agar bisa test dashboard end-to-end.

```python
# simulator/simulator.py
import redis
import json
import time
import random
import uuid
from datetime import datetime, timezone

r = redis.Redis(host="localhost", port=6379, decode_responses=True)

# Koordinat di sekitar Jakarta untuk simulasi
JAKARTA_LOCATIONS = [
    {"lat": -6.1944, "lng": 106.8229, "camera_id": "cam-001", "name": "Bundaran HI"},
    {"lat": -6.2088, "lng": 106.8228, "camera_id": "cam-002", "name": "Semanggi"},
    {"lat": -6.2441, "lng": 106.7993, "camera_id": "cam-003", "name": "Blok M"},
    {"lat": -6.1867, "lng": 106.8226, "camera_id": "cam-004", "name": "Sarinah"},
]

VIOLATION_TYPES = ["illegal_parking", "busway_violation", "congestion"]
SEVERITIES = ["low", "medium", "high"]

def generate_violation():
    location = random.choice(JAKARTA_LOCATIONS)
    # Tambahkan sedikit noise agar posisi tidak persis sama
    lat_noise = random.uniform(-0.001, 0.001)
    lng_noise = random.uniform(-0.001, 0.001)

    return {
        "type": "violation",
        "payload": {
            "id": str(uuid.uuid4()),
            "camera_id": location["camera_id"],
            "type": random.choice(VIOLATION_TYPES),
            "lat": location["lat"] + lat_noise,
            "lng": location["lng"] + lng_noise,
            "severity": random.choice(SEVERITIES),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    }

print("🚦 Simulator berjalan... Tekan Ctrl+C untuk stop")
print("   Mengirim data ke Redis topic: traffic.violation")
print("   Interval: 5 detik\n")

try:
    while True:
        data = generate_violation()
        r.publish("traffic.violation", json.dumps(data))
        print(f"  ✅ Published: {data['payload']['type']} di {data['payload']['camera_id']}")
        time.sleep(5)
except KeyboardInterrupt:
    print("\nSimulator dihentikan.")
```

Jalankan simulator:

```bash
cd simulator
pip install redis
python simulator.py
```

---

## 9. Fitur CCTV Modal

```typescript
// frontend/src/components/Modals/CCTVModal.tsx
import ReactPlayer from "react-player";
import type { Camera } from "../../types";

interface Props {
  camera: Camera;
  onClose: () => void;
}

export function CCTVModal({ camera, onClose }: Props) {
  return (
    // Backdrop
    <div
      onClick={onClose}
      style={{
        position: "absolute",
        inset: 0,
        background: "rgba(0,0,0,0.7)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        zIndex: 1000,
      }}
    >
      {/* Modal panel — klik di dalam tidak close */}
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          background: "#0f1117",
          border: "1px solid #2a2a3e",
          borderRadius: 12,
          padding: 20,
          minWidth: 520,
          boxShadow: "0 20px 60px rgba(0,0,0,0.8)",
        }}
      >
        {/* Header */}
        <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 12 }}>
          <div>
            <div style={{ color: "#00d4ff", fontWeight: 600, fontSize: 14 }}>
              📷 {camera.name}
            </div>
            <div style={{ color: "#666", fontSize: 12, marginTop: 2 }}>
              ID: {camera.id} · Live Feed
            </div>
          </div>
          <button
            onClick={onClose}
            style={{
              background: "none",
              border: "1px solid #333",
              color: "#aaa",
              borderRadius: 6,
              padding: "4px 10px",
              cursor: "pointer",
              fontSize: 12,
            }}
          >
            ✕ Tutup
          </button>
        </div>

        {/* Video player */}
        {camera.stream_url ? (
          <ReactPlayer
            url={camera.stream_url}
            playing
            loop
            muted
            width="480px"
            height="270px"
            style={{ borderRadius: 8, overflow: "hidden", background: "#000" }}
          />
        ) : (
          <div
            style={{
              width: 480,
              height: 270,
              background: "#111",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              color: "#555",
              borderRadius: 8,
              fontSize: 13,
            }}
          >
            Feed tidak tersedia
          </div>
        )}

        {/* Status bar */}
        <div
          style={{
            marginTop: 10,
            display: "flex",
            gap: 16,
            fontSize: 11,
            color: "#555",
          }}
        >
          <span style={{ color: "#00ff88" }}>● LIVE</span>
          <span>Lat: {camera.lat.toFixed(4)}</span>
          <span>Lng: {camera.lng.toFixed(4)}</span>
        </div>
      </div>
    </div>
  );
}
```

Taruh file video MP4 simulasi di `frontend/public/videos/cam001.mp4`, `cam002.mp4`, dst. File bisa diunduh dari YouTube menggunakan `yt-dlp`:

```bash
pip install yt-dlp
yt-dlp -o "cam001.mp4" -f "best[height<=480]" "URL_VIDEO_YOUTUBE"
```

---

## 10. Modul Event & Mitigasi

```typescript
// frontend/src/components/Dashboard/EventMitigationPanel.tsx
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { getEvents, getEventMitigation } from "../../services/api";
import type { Event, Mitigation } from "../../types";

const IMPACT_COLORS: Record<string, string> = {
  KRITIS: "#FF0000",
  TINGGI: "#FF4500",
  SEDANG: "#FFA500",
};

export function EventMitigationPanel() {
  const [selectedEvent, setSelectedEvent] = useState<Event | null>(null);

  const { data: events = [] } = useQuery({
    queryKey: ["events"],
    queryFn: getEvents,
  });

  const { data: mitigation } = useQuery({
    queryKey: ["mitigation", selectedEvent?.id],
    queryFn: () => getEventMitigation(selectedEvent!.id),
    enabled: !!selectedEvent,
  });

  return (
    <div style={{ padding: 16 }}>
      <h3 style={{ color: "#9B59B6", fontSize: 13, marginBottom: 12 }}>
        🎵 Event Mendatang
      </h3>

      {/* Daftar event */}
      <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
        {events.map((event) => (
          <div
            key={event.id}
            onClick={() => setSelectedEvent(event)}
            style={{
              padding: "10px 12px",
              background: selectedEvent?.id === event.id ? "#1a1a2e" : "#111",
              border: `1px solid ${selectedEvent?.id === event.id ? "#9B59B6" : "#222"}`,
              borderRadius: 8,
              cursor: "pointer",
              transition: "all 0.15s",
            }}
          >
            <div style={{ color: "#fff", fontSize: 12, fontWeight: 600 }}>
              {event.name}
            </div>
            <div style={{ color: "#777", fontSize: 11, marginTop: 3 }}>
              📍 {event.venue} · {event.date} {event.time}
            </div>
            <div style={{ color: "#aaa", fontSize: 11 }}>
              👥 ~{event.estimated_crowd.toLocaleString()} orang
            </div>
          </div>
        ))}
      </div>

      {/* Panel mitigasi */}
      {mitigation && (
        <div
          style={{
            marginTop: 16,
            padding: 12,
            background: "#0a0a0f",
            border: `1px solid ${IMPACT_COLORS[mitigation.impact_level] || "#333"}`,
            borderRadius: 8,
          }}
        >
          <div
            style={{
              color: IMPACT_COLORS[mitigation.impact_level],
              fontWeight: 700,
              fontSize: 12,
              marginBottom: 8,
            }}
          >
            ⚠ DAMPAK: {mitigation.impact_level}
          </div>
          <div style={{ color: "#aaa", fontSize: 11, marginBottom: 8 }}>
            {mitigation.predicted_congestion_start} →{" "}
            {mitigation.predicted_congestion_end}
          </div>
          <div style={{ color: "#888", fontSize: 11, marginBottom: 6 }}>
            Rekomendasi mitigasi:
          </div>
          <ul style={{ margin: 0, paddingLeft: 16 }}>
            {mitigation.recommendations.map((rec, i) => (
              <li key={i} style={{ color: "#ccc", fontSize: 11, marginBottom: 4 }}>
                {rec}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
```

---

## 11. Notifikasi Real-time

```typescript
// frontend/src/hooks/useNotifications.ts
import { useState, useCallback } from "react";
import type { Violation, WSMessage } from "../types";

export interface Notification {
  id: string;
  message: string;
  severity: "low" | "medium" | "high";
  timestamp: Date;
}

const VIOLATION_LABELS: Record<string, string> = {
  illegal_parking: "Parkir Liar",
  busway_violation: "Pelanggaran Jalur Busway",
  congestion: "Kemacetan Terdeteksi",
};

export function useNotifications() {
  const [notifications, setNotifications] = useState<Notification[]>([]);

  const addFromWSMessage = useCallback((msg: WSMessage) => {
    if (msg.type !== "violation" || !msg.payload) return;
    const v = msg.payload as Violation;

    const notif: Notification = {
      id: v.id,
      message: `${VIOLATION_LABELS[v.type] || v.type} terdeteksi di kamera ${v.camera_id}`,
      severity: v.severity,
      timestamp: new Date(),
    };

    setNotifications((prev) => [notif, ...prev].slice(0, 20));

    // Auto-dismiss notifikasi setelah 8 detik
    setTimeout(() => {
      setNotifications((prev) => prev.filter((n) => n.id !== notif.id));
    }, 8000);
  }, []);

  return { notifications, addFromWSMessage };
}
```

```typescript
// frontend/src/components/Dashboard/NotificationPanel.tsx
import type { Notification } from "../../hooks/useNotifications";

const SEVERITY_STYLES: Record<string, { bg: string; border: string; dot: string }> = {
  low:    { bg: "#1a1500", border: "#FFA500", dot: "#FFA500" },
  medium: { bg: "#1a0800", border: "#FF4500", dot: "#FF4500" },
  high:   { bg: "#1a0000", border: "#FF0000", dot: "#FF0000" },
};

interface Props {
  notifications: Notification[];
}

export function NotificationPanel({ notifications }: Props) {
  if (notifications.length === 0) return null;

  return (
    <div
      style={{
        position: "absolute",
        top: 16,
        right: 16,
        zIndex: 500,
        display: "flex",
        flexDirection: "column",
        gap: 8,
        maxWidth: 320,
      }}
    >
      {notifications.map((n) => {
        const style = SEVERITY_STYLES[n.severity];
        return (
          <div
            key={n.id}
            style={{
              background: style.bg,
              border: `1px solid ${style.border}`,
              borderRadius: 8,
              padding: "10px 14px",
              animation: "slideIn 0.2s ease",
            }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <span
                style={{
                  width: 8,
                  height: 8,
                  borderRadius: "50%",
                  background: style.dot,
                  flexShrink: 0,
                  animation: "pulse 1.5s infinite",
                }}
              />
              <span style={{ color: "#fff", fontSize: 12, fontWeight: 600 }}>
                {n.message}
              </span>
            </div>
            <div style={{ color: "#666", fontSize: 10, marginTop: 4, marginLeft: 16 }}>
              {n.timestamp.toLocaleTimeString("id-ID")}
            </div>
          </div>
        );
      })}
      <style>{`
        @keyframes slideIn {
          from { transform: translateX(100%); opacity: 0; }
          to   { transform: translateX(0);    opacity: 1; }
        }
      `}</style>
    </div>
  );
}
```

---

## 12. Database Schema

Jalankan SQL ini sekali untuk inisialisasi tabel di PostgreSQL:

```sql
-- Aktifkan ekstensi PostGIS
CREATE EXTENSION IF NOT EXISTS postgis;

-- Tabel kamera CCTV
CREATE TABLE cameras (
    id          VARCHAR(50) PRIMARY KEY,
    name        VARCHAR(200) NOT NULL,
    location    GEOGRAPHY(POINT, 4326) NOT NULL,
    stream_url  TEXT,
    is_active   BOOLEAN DEFAULT true,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

-- Tabel zona rawan (polygon)
CREATE TABLE zones (
    id          VARCHAR(50) PRIMARY KEY,
    name        VARCHAR(200) NOT NULL,
    type        VARCHAR(50) NOT NULL,
    color       VARCHAR(7)  NOT NULL,
    boundary    GEOGRAPHY(POLYGON, 4326) NOT NULL,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

-- Tabel log pelanggaran (diisi oleh CV worker via backend)
CREATE TABLE violations (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    camera_id   VARCHAR(50) REFERENCES cameras(id),
    type        VARCHAR(50) NOT NULL,
    location    GEOGRAPHY(POINT, 4326) NOT NULL,
    severity    VARCHAR(20) NOT NULL,
    snapshot_url TEXT,
    occurred_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX violations_occurred_at_idx ON violations (occurred_at DESC);

-- Tabel event Jakarta
CREATE TABLE events (
    id                  VARCHAR(50) PRIMARY KEY,
    name                VARCHAR(300) NOT NULL,
    venue               VARCHAR(200) NOT NULL,
    location            GEOGRAPHY(POINT, 4326) NOT NULL,
    event_date          DATE NOT NULL,
    event_time          TIME NOT NULL,
    estimated_crowd     INTEGER NOT NULL,
    impact_radius_km    FLOAT NOT NULL,
    created_at          TIMESTAMPTZ DEFAULT NOW()
);
```

Jalankan via psql:

```bash
docker exec -i traffic-dashboard-postgres-1 \
  psql -U traffic_user -d traffic_db < schema.sql
```

---

## 13. Checklist Prototype

Gunakan checklist ini untuk memverifikasi tiap tahap sebelum lanjut:

**Minggu 1 — Infrastructure**
- [ ] `docker compose up -d` berjalan tanpa error
- [ ] Redis dapat di-ping: `docker exec -it <container> redis-cli ping` → `PONG`
- [ ] PostgreSQL dapat diakses, schema berhasil dijalankan
- [ ] Backend FastAPI jalan di port 8000, endpoint `/health` return `{"status":"ok"}`
- [ ] Endpoint `/api/cameras` dan `/api/zones` return data statis

**Minggu 2 — Real-time Pipeline**
- [ ] Simulator berjalan dan publish data ke Redis setiap 5 detik
- [ ] Backend menerima data dari Redis (cek log di terminal FastAPI)
- [ ] Frontend terhubung ke WebSocket (cek Network tab di browser DevTools)
- [ ] Marker violation muncul di peta setiap kali simulator publish data
- [ ] Notifikasi muncul di pojok kanan atas dashboard

**Minggu 3 — Fitur Map**
- [ ] Zona rawan (polygon kuning & oranye) tampil di peta
- [ ] Ikon kamera CCTV tampil di titik yang benar
- [ ] Klik ikon kamera → modal CCTV terbuka dengan video berjalan
- [ ] Marker pelanggaran beranimasi pulse

**Minggu 4 — Modul Event**
- [ ] Panel event menampilkan daftar event dari database
- [ ] Klik event → panel mitigasi muncul dengan rekomendasi
- [ ] Integrasi CV Worker: publish ke Redis format yang benar → dashboard update otomatis

---

*Guide ini adalah living document — sesuaikan data seed (kamera, zona, event) dengan kawasan spesifik yang menjadi target pilot project Anda.*