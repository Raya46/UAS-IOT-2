import { useState, useEffect, useRef, useCallback } from "react";
import { Marker } from "react-map-gl/mapbox";

export interface PatrolVehicle {
  id: string;
  label: string;
  icon: string;
  videoSrc: string;
  videoFile: string; // filename for backend dashcam WS
  description: string;
  waypoints: [number, number][]; // [lng, lat][] key waypoints for Directions API
  color: string;
}

export interface PatrolRuntimePosition {
  lng: number;
  lat: number;
  bearing: number;
}

export interface PatrolGeneratedViolation {
  vehicle: PatrolVehicle;
  position: PatrolRuntimePosition;
  generatedAt: number;
}

const API_BASE = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

function dashcamVideoUrl(filename: string) {
  return `${API_BASE}/api/dashcam/videos/${encodeURIComponent(filename)}`;
}

const PATROL_VEHICLES: PatrolVehicle[] = [
  {
    id: "patrol_angkot_parkir",
    label: "Angkot JakLingko 01",
    icon: "directions_bus",
    videoSrc: dashcamVideoUrl("angkot-parkir-sembarangan.mp4"),
    videoFile: "angkot-parkir-sembarangan.mp4",
    description: "Angkot parkir sembarangan",
    color: "#dc2626",
    waypoints: [
      [106.8130, -6.1870],
      [106.8156, -6.1889],
      [106.8180, -6.1905],
      [106.8210, -6.1920],
      [106.8180, -6.1905],
      [106.8156, -6.1889],
    ],
  },
  {
    id: "patrol_bus_prima_jasa",
    label: "Bus Prima Jasa 02",
    icon: "directions_bus",
    videoSrc: dashcamVideoUrl("Bus Prima Jasa dan Toyota Camry, menyalip dari bahu jalan dan memaksa masuk.Entrance Rest A.mp4"),
    videoFile: "Bus Prima Jasa dan Toyota Camry, menyalip dari bahu jalan dan memaksa masuk.Entrance Rest A.mp4",
    description: "Bus Prima Jasa & Toyota Camry — menyalip dari bahu jalan",
    color: "#2563eb",
    waypoints: [
      [106.8019, -6.2275],
      [106.8050, -6.2200],
      [106.8100, -6.2130],
      [106.8200, -6.2088],
      [106.8300, -6.1970],
      [106.8350, -6.1920],
      [106.8300, -6.1960],
      [106.8200, -6.2050],
      [106.8100, -6.2150],
    ],
  },
  {
    id: "patrol_mobil_putih",
    label: "TransJakarta Mikrotrans 03",
    icon: "airport_shuttle",
    videoSrc: dashcamVideoUrl("mobil-putih-menerobos-lampu-merah-dari-arah-depan.mp4"),
    videoFile: "mobil-putih-menerobos-lampu-merah-dari-arah-depan.mp4",
    description: "Mobil putih menerobos lampu merah dari arah depan",
    color: "#059669",
    waypoints: [
      [106.8230, -6.1870],
      [106.8245, -6.1950],
      [106.8260, -6.2040],
      [106.8270, -6.2088],
      [106.8250, -6.2010],
      [106.8235, -6.1930],
    ],
  },
  {
    id: "patrol_motor_putar",
    label: "TransJakarta Patrol 04",
    icon: "directions_bus",
    videoSrc: dashcamVideoUrl("mobil-yang-parkir-pada-kanan-kiri-ruas-jalan-tertib.mp4"),
    videoFile: "mobil-yang-parkir-pada-kanan-kiri-ruas-jalan-tertib.mp4",
    description: "Motor putar arah sembarangan",
    color: "#d97706",
    waypoints: [
      [106.8100, -6.2100],
      [106.8180, -6.2140],
      [106.8260, -6.2110],
      [106.8300, -6.2070],
      [106.8260, -6.2110],
      [106.8180, -6.2150],
    ],
  },
  {
    id: "patrol_motor_potong_lajur",
    label: "TransJakarta Patrol 05",
    icon: "directions_bus",
    videoSrc: dashcamVideoUrl("motor-potong-lajur-mobil-dari-kanan-ke-kiri.mp4"),
    videoFile: "motor-potong-lajur-mobil-dari-kanan-ke-kiri.mp4",
    description: "Motor potong lajur mobil dari kanan ke kiri",
    color: "#7c3aed",
    waypoints: [
      [106.8310, -6.2365],
      [106.8350, -6.2320],
      [106.8400, -6.2260],
      [106.8460, -6.2200],
      [106.8400, -6.2260],
      [106.8350, -6.2320],
    ],
  },
  {
    id: "patrol_taksi_bluebird",
    label: "Taksi Bluebird 06",
    icon: "local_taxi",
    videoSrc: dashcamVideoUrl("taksi-berputar-arah-di-lampu-merah-yang-dilarang.mp4"),
    videoFile: "taksi-berputar-arah-di-lampu-merah-yang-dilarang.mp4",
    description: "Taksi Bluebird berputar arah di lajur lampu merah yang dilarang",
    color: "#0891b2",
    waypoints: [
      [106.8210, -6.1930],
      [106.8228, -6.1944],
      [106.8240, -6.1970],
      [106.8260, -6.2010],
      [106.8240, -6.1970],
      [106.8228, -6.1944],
    ],
  },
];

interface PatrolState {
  lng: number;
  lat: number;
  pointIndex: number;
  progress: number;
  bearing: number;
}

function lerp(a: number, b: number, t: number) {
  return a + (b - a) * t;
}

function calcBearing(lng1: number, lat1: number, lng2: number, lat2: number) {
  const dLng = ((lng2 - lng1) * Math.PI) / 180;
  const y = Math.sin(dLng) * Math.cos((lat2 * Math.PI) / 180);
  const x =
    Math.cos((lat1 * Math.PI) / 180) * Math.sin((lat2 * Math.PI) / 180) -
    Math.sin((lat1 * Math.PI) / 180) *
      Math.cos((lat2 * Math.PI) / 180) *
      Math.cos(dLng);
  return ((Math.atan2(y, x) * 180) / Math.PI + 360) % 360;
}

// Distance between two coordinates in meters (approx)
function haversine(lng1: number, lat1: number, lng2: number, lat2: number): number {
  const R = 6371000;
  const dLat = ((lat2 - lat1) * Math.PI) / 180;
  const dLng = ((lng2 - lng1) * Math.PI) / 180;
  const a =
    Math.sin(dLat / 2) ** 2 +
    Math.cos((lat1 * Math.PI) / 180) * Math.cos((lat2 * Math.PI) / 180) * Math.sin(dLng / 2) ** 2;
  return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}

interface Props {
  onPatrolClick: (patrol: PatrolVehicle) => void;
  onPatrolPositionsUpdate?: (positions: Record<string, PatrolRuntimePosition>) => void;
  onRandomViolation?: (violation: PatrolGeneratedViolation) => void;
}

const ROUTE_CACHE_KEY = "patrol_routes_cache_v3";
const RANDOM_VIOLATION_MIN_DELAY_MS = 60000;
const RANDOM_VIOLATION_JITTER_MS = 660000;
const RANDOM_VIOLATION_GLOBAL_COOLDOWN_MS = 120000;

function getCachedRoutes(): Record<string, [number, number][]> | null {
  try {
    const raw = localStorage.getItem(ROUTE_CACHE_KEY);
    if (raw) {
      const parsed = JSON.parse(raw);
      // Verify all patrol vehicles have cached routes
      const allCached = PATROL_VEHICLES.every(
        (v) => parsed[v.id] && Array.isArray(parsed[v.id]) && parsed[v.id].length > 5
      );
      if (allCached) return parsed;
    }
  } catch {}
  return null;
}

function saveCachedRoutes(routes: Record<string, [number, number][]>) {
  try {
    localStorage.setItem(ROUTE_CACHE_KEY, JSON.stringify(routes));
  } catch {}
}

async function fetchRoute(
  waypoints: [number, number][],
  token: string
): Promise<[number, number][]> {
  const coords = waypoints.map((w) => `${w[0]},${w[1]}`).join(";");
  const url = `https://api.mapbox.com/directions/v5/mapbox/driving/${coords}?geometries=geojson&overview=full&access_token=${token}`;
  try {
    const resp = await fetch(url);
    const data = await resp.json();
    if (data.routes && data.routes[0]) {
      return data.routes[0].geometry.coordinates as [number, number][];
    }
  } catch (e) {
    console.warn("[PatrolMarkers] Directions API failed, using fallback", e);
  }
  return waypoints;
}

export function PatrolMarkers({ onPatrolClick, onPatrolPositionsUpdate, onRandomViolation }: Props) {
  const [positions, setPositions] = useState<Record<string, PatrolState>>({});
  const [routes, setRoutes] = useState<Record<string, [number, number][]>>({});
  const stateRef = useRef<Record<string, PatrolState>>({});
  const routesRef = useRef<Record<string, [number, number][]>>({});
  const rafRef = useRef<number>(0);
  const lastTimeRef = useRef<number>(0);
  const lastPositionPublishRef = useRef(0);
  const lastRandomViolationAtRef = useRef(0);
  const randomTimerRefs = useRef<number[]>([]);
  const onPatrolPositionsUpdateRef = useRef(onPatrolPositionsUpdate);
  const onRandomViolationRef = useRef(onRandomViolation);

  useEffect(() => {
    onPatrolPositionsUpdateRef.current = onPatrolPositionsUpdate;
  }, [onPatrolPositionsUpdate]);

  useEffect(() => {
    onRandomViolationRef.current = onRandomViolation;
  }, [onRandomViolation]);

  // Fetch road-snapped routes — cached in localStorage to save API tokens
  useEffect(() => {
    function initRoutes(routeMap: Record<string, [number, number][]>) {
      const initial: Record<string, PatrolState> = {};
      PATROL_VEHICLES.forEach((v, i) => {
        const c = routeMap[v.id];
        if (!c || c.length < 2) return;
        const startIdx = Math.floor(c.length * i * 0.3) % (c.length - 1);
        initial[v.id] = {
          lng: c[startIdx][0],
          lat: c[startIdx][1],
          pointIndex: startIdx,
          progress: 0,
          bearing: calcBearing(c[startIdx][0], c[startIdx][1], c[startIdx + 1][0], c[startIdx + 1][1]),
        };
      });
      routesRef.current = routeMap;
      stateRef.current = initial;
      setRoutes(routeMap);
      setPositions({ ...initial });
    }

    // 1. Try localStorage cache first (0 API calls)
    const cached = getCachedRoutes();
    if (cached) {
      console.log("[PatrolMarkers] Using cached routes (0 API calls)");
      initRoutes(cached);
      return;
    }

    // 2. Fetch from Mapbox Directions API once per patrol route, then cache.
    const token = (import.meta as any).env?.VITE_MAPBOX_TOKEN || "";
    if (!token) return;

    console.log("[PatrolMarkers] Fetching routes from Mapbox API (will cache for reuse)");
    Promise.all(
      PATROL_VEHICLES.map(async (v) => {
        const roadCoords = await fetchRoute(v.waypoints, token);
        return { id: v.id, coords: roadCoords };
      })
    ).then((results) => {
      const routeMap: Record<string, [number, number][]> = {};
      results.forEach((r) => {
        routeMap[r.id] = r.coords;
      });
      saveCachedRoutes(routeMap);
      initRoutes(routeMap);
    });
  }, []);

  const animate = useCallback((time: number) => {
    if (!lastTimeRef.current) lastTimeRef.current = time;
    const dt = Math.min((time - lastTimeRef.current) / 1000, 0.1);
    lastTimeRef.current = time;

    const curRoutes = routesRef.current;
    if (Object.keys(curRoutes).length === 0) {
      rafRef.current = requestAnimationFrame(animate);
      return;
    }

    // Speed: ~40 km/h = ~11 m/s
    const speedMps = 11;
    const updated = { ...stateRef.current };
    let changed = false;

    PATROL_VEHICLES.forEach((v) => {
      const state = updated[v.id];
      const route = curRoutes[v.id];
      if (!state || !route || route.length < 2) return;

      let { pointIndex, progress } = state;
      const from = route[pointIndex];
      const to = route[(pointIndex + 1) % route.length];
      const segLen = haversine(from[0], from[1], to[0], to[1]);
      const segProgress = segLen > 0 ? (speedMps * dt) / segLen : 1;

      progress += segProgress;

      while (progress >= 1) {
        progress -= 1;
        pointIndex = (pointIndex + 1) % (route.length - 1);
      }

      const cfrom = route[pointIndex];
      const cto = route[(pointIndex + 1) % route.length];

      updated[v.id] = {
        lng: lerp(cfrom[0], cto[0], progress),
        lat: lerp(cfrom[1], cto[1], progress),
        pointIndex,
        progress,
        bearing: calcBearing(cfrom[0], cfrom[1], cto[0], cto[1]),
      };
      changed = true;
    });

    if (changed) {
      stateRef.current = updated;
      setPositions({ ...updated });
      if (time - lastPositionPublishRef.current > 1000) {
        lastPositionPublishRef.current = time;
        const runtimePositions = Object.fromEntries(
          Object.entries(updated).map(([id, pos]) => [
            id,
            { lng: pos.lng, lat: pos.lat, bearing: pos.bearing },
          ]),
        );
        onPatrolPositionsUpdateRef.current?.(runtimePositions);
      }
    }

    rafRef.current = requestAnimationFrame(animate);
  }, []);

  useEffect(() => {
    rafRef.current = requestAnimationFrame(animate);
    return () => cancelAnimationFrame(rafRef.current);
  }, [animate]);

  const routesLoaded = Object.keys(routes).length > 0;

  useEffect(() => {
    if (!routesLoaded) return;

    const scheduleViolation = (vehicle: PatrolVehicle) => {
      const delayMs = RANDOM_VIOLATION_MIN_DELAY_MS + Math.floor(Math.random() * RANDOM_VIOLATION_JITTER_MS);
      const timer = window.setTimeout(() => {
        const pos = stateRef.current[vehicle.id];
        const now = Date.now();
        if (pos && now - lastRandomViolationAtRef.current >= RANDOM_VIOLATION_GLOBAL_COOLDOWN_MS) {
          lastRandomViolationAtRef.current = now;
          onRandomViolationRef.current?.({
            vehicle,
            position: { lng: pos.lng, lat: pos.lat, bearing: pos.bearing },
            generatedAt: now,
          });
        }
        scheduleViolation(vehicle);
      }, delayMs);
      randomTimerRefs.current.push(timer);
    };

    PATROL_VEHICLES.forEach(scheduleViolation);

    return () => {
      randomTimerRefs.current.forEach((timer) => window.clearTimeout(timer));
      randomTimerRefs.current = [];
    };
  }, [routesLoaded]);

  return (
    <>
      {routesLoaded &&
        PATROL_VEHICLES.map((vehicle) => {
          const pos = positions[vehicle.id];
          if (!pos) return null;

          return (
            <Marker
              key={vehicle.id}
              longitude={pos.lng}
              latitude={pos.lat}
              anchor="center"
              onClick={(e: any) => {
                e.originalEvent.stopPropagation();
                onPatrolClick(vehicle);
              }}
            >
              <div
                style={{
                  cursor: "pointer",
                  display: "flex",
                  flexDirection: "column",
                  alignItems: "center",
                  filter: "drop-shadow(0 1px 3px rgba(0,0,0,0.3))",
                }}
              >
                <div
                  style={{
                    width: 32,
                    height: 32,
                    borderRadius: 8,
                    background: vehicle.color,
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    border: "2px solid white",
                    boxShadow: `0 0 0 1px ${vehicle.color}40`,
                    transform: `rotate(${pos.bearing - 90}deg)`,
                    transition: "transform 0.5s ease",
                  }}
                >
                  <span
                    className="material-symbols-outlined"
                    style={{ color: "white", fontSize: 18 }}
                  >
                    {vehicle.icon}
                  </span>
                </div>
                <div
                  style={{
                    marginTop: 4,
                    background: vehicle.color,
                    color: "white",
                    fontSize: 8,
                    fontWeight: 600,
                    padding: "1px 6px",
                    borderRadius: 3,
                    whiteSpace: "nowrap",
                    letterSpacing: "0.3px",
                  }}
                >
                  {vehicle.label}
                </div>
              </div>
            </Marker>
          );
        })}
    </>
  );
}

export { PATROL_VEHICLES };
