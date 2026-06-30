import { useState, useEffect, useCallback, useMemo } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { createIncident, getCameras } from "./services/api";
import { MapContainer } from "./components/Map/MapContainer";
import { EventMitigationPanel } from "./components/Dashboard/EventMitigationPanel";
import { useWebSocket } from "./hooks/useWebSocket";
import type { Camera, Incident, WSMessage, EventPrediction } from "./types";
import { IncidentDetailModal } from "./components/Modals/IncidentDetailModal";
import { EventDetailModal } from "./components/Modals/EventDetailModal";
import { CCTVModal } from "./components/Modals/CCTVModal";
import { PatrolVideoModal } from "./components/Modals/PatrolVideoModal";
import { PATROL_VEHICLES } from "./components/Map/PatrolMarkers";
import type { PatrolVehicle } from "./components/Map/PatrolMarkers";
import type { PatrolGeneratedViolation, PatrolRuntimePosition } from "./components/Map/PatrolMarkers";
import { NotificationPanel } from "./components/Dashboard/NotificationPanel";
import { useNotifications } from "./hooks/useNotifications";
import { IncidentPanel } from "./components/Dashboard/IncidentPanel";
import { SummaryDashboard } from "./components/Dashboard/SummaryDashboard";
import { ExecutiveSummaryPanel } from "./components/Dashboard/ExecutiveSummaryPanel";
import { HeatmapControls } from "./components/Dashboard/HeatmapControls";
import { NotificationHistoryPanel } from "./components/Dashboard/NotificationHistoryPanel";
import { VideoUploadPanel } from "./components/Dashboard/VideoUploadPanel";
import { LiveCamPanel } from "./components/Dashboard/LiveCamPanel";
import { ActivityPanel } from "./components/Dashboard/ActivityPanel";
import type { ActivityItem } from "./components/Dashboard/ActivityPanel";
import { MitigationTasksPanel } from "./components/Dashboard/MitigationTasksPanel";
import type { TaskItem, TeamItem } from "./components/Dashboard/MitigationTasksPanel";
import axios from "axios";
import { getViolationEvents } from "./services/api";
import {
  enrichIncidentWithEvidence,
  getEvidenceMetadataForSnapshot,
  getEvidenceMetadataForVideo,
  getIncidentSnapshotUrl,
} from "./utils/incidentSnapshots";

const DEFAULT_LIVE_VIOLATION_LOCATION = { lat: -6.2088, lng: 106.8456 };

const RANDOM_PATROL_VIOLATION_RULES: Array<{
  type: Incident["type"];
  title: string;
  description: string;
  icon: string;
  snapshots: string[];
  vehicleType?: string;
}> = [
  {
    type: "illegal_parking",
    title: "Angkot Berhenti Sembarangan",
    description: "Angkot berhenti sembarangan dan mengganggu arus kendaraan.",
    icon: "local_parking",
    snapshots: [
      "/snapshots/angkot-berhenti-sembarangan.png",
      "/snapshots/angkot-parkir-sembarangan.png",
    ],
    vehicleType: "angkot",
  },
  {
    type: "shoulder_violation",
    title: "Prima Jasa Menyalip Dari Bahu Jalan",
    description: "Bus Prima Jasa menyalip dari bahu jalan dan memaksa masuk ke lajur kendaraan.",
    icon: "directions_bus",
    snapshots: [
      "/snapshots/prima-jasa-nyalip-dari-bahu-jalan.png",
      "/snapshots/toyota-camry-nyalip-dari-bahu-jalan.png",
    ],
    vehicleType: "bus",
  },
  {
    type: "illegal_u_turn",
    title: "Motor Putar Arah Sembarangan",
    description: "Motor melakukan putar arah sembarangan di ruas jalan.",
    icon: "wrong_location",
    snapshots: [
      "/snapshots/motor-putar-arah-sembarangan.png",
      "/snapshots/motor-putar-arah-sembarangan-plat-nomor.png",
    ],
    vehicleType: "motorcycle",
  },
  {
    type: "unsafe_lane_change",
    title: "Motor Potong Lajur",
    description: "Motor memotong lajur mobil dari kanan ke kiri.",
    icon: "swap_horiz",
    snapshots: [
      "/snapshots/motor-potong-lajur-mobil-dari-arah-kanan-ke-kiri.png",
    ],
    vehicleType: "motorcycle",
  },
  {
    type: "red_light_violation",
    title: "Mobil Putih Menerobos Lampu Merah",
    description: "Mobil putih menerobos lampu merah dari arah depan.",
    icon: "traffic",
    snapshots: [
      "/snapshots/mobil-putih-nerobos-lampu-merah-dari-arah-depan.png",
    ],
    vehicleType: "car",
  },
  {
    type: "illegal_u_turn",
    title: "Taksi Melanggar Rambu",
    description: "Taksi berbelok kanan atau berputar arah meski terdapat rambu larangan.",
    icon: "local_taxi",
    snapshots: [
      "/snapshots/taksi-melanggar-rambu-dilarang-belok-kanan.png",
    ],
    vehicleType: "taxi",
  },
];

interface RuntimeViolationLog {
  source: string;
  type: string;
  detail: string;
  plate?: string;
  vehicleType?: string;
  evidenceImage?: string;
  evidenceSize?: [number, number];
  plateCrop?: string;
  plateBbox?: [number, number, number, number];
  plateConfidence?: number;
  plateNote?: string;
  videoTimeSeconds?: number;
  videoFile?: string;
}

function pickRandom<T>(items: T[]): T {
  return items[Math.floor(Math.random() * items.length)];
}

function isUuid(value: string): boolean {
  return /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(value);
}

function getLiveViolationLocation(videoFile?: string) {
  const patrol = PATROL_VEHICLES.find((vehicle) => vehicle.videoFile === videoFile);
  if (!patrol) return DEFAULT_LIVE_VIOLATION_LOCATION;

  const waypoint = patrol.waypoints[Math.floor(patrol.waypoints.length / 2)];
  if (!waypoint) return DEFAULT_LIVE_VIOLATION_LOCATION;
  return { lng: waypoint[0], lat: waypoint[1] };
}

export default function App() {
  const queryClient = useQueryClient();
  const { notifications, addFromWSMessage, dismissNotification } = useNotifications();
  const [theme, setTheme] = useState<"light" | "dark">(() => {
    if (typeof window === "undefined") return "light";
    const saved = window.localStorage.getItem("traffic-theme");
    return saved === "dark" || saved === "light" ? saved : "light";
  });

  // Queries
  const { data: cameras = [], isLoading: loadingCams } = useQuery({
    queryKey: ["cameras"],
    queryFn: getCameras,
  });


  // Query for all active incidents to render on the map
  const { data: incidentsResponse } = useQuery({
    queryKey: ["active-incidents-list"],
    queryFn: () =>
      axios
        .get(`${import.meta.env.VITE_API_BASE_URL}/api/incidents/?page_size=100`)
        .then((r) => r.data),
    refetchInterval: 10000,
  });

  const incidentsWithSnapshots = useMemo(
    () => (incidentsResponse?.items ?? []).map((inc: Incident) =>
      enrichIncidentWithEvidence({
        ...inc,
        snapshot_url: getIncidentSnapshotUrl(inc),
      }),
    ),
    [incidentsResponse?.items],
  );

  const activeIncidents = incidentsWithSnapshots.filter(
    (inc: Incident) => inc.status !== "resolved" && inc.status !== "closed"
  );

  // UI States
  const [leftSidebarOpen, setLeftSidebarOpen] = useState(true);
  const [leftTab, setLeftTab] = useState<"incidents" | "sensors" | "cameras" | "officers">("incidents");
  const [rightSidebarOpen, setRightSidebarOpen] = useState(true);
  const [rightTab, setRightTab] = useState<"events" | "analytics" | "simulator" | "summary" | "notifications" | "upload" | "livecam" | "tasks" | "activities">("events");

  // Search state
  const [searchQuery, setSearchQuery] = useState("");
  const [isSearchFocused, setIsSearchFocused] = useState(false);

  // Custom interactive tasks and team assignments
  const [tasks, setTasks] = useState<TaskItem[]>([]);
  const [teams, setTeams] = useState<TeamItem[]>([]);

  // Sync dispatched incidents to active tasks and teams
  useEffect(() => {
    const dispatchedIncidents = activeIncidents.filter((inc: Incident) => inc.status === "dispatched" && inc.assigned_officer);

    dispatchedIncidents.forEach((inc: Incident) => {
      const taskId = `task-inc-${inc.id}`;
      setTasks(prev => {
        if (prev.some(t => t.id === taskId)) return prev;
        return [
          {
            id: taskId,
            title: `Incident Response: Dispatch to ${inc.type.replace("_", " ")}`,
            status: "In Progress",
            progress: 30
          },
          ...prev
        ];
      });

      const teamId = `team-inc-${inc.id}`;
      setTeams(prev => {
        if (prev.some(t => t.id === teamId)) return prev;
        return [
          {
            id: teamId,
            name: inc.assigned_officer || "Unit Patroli",
            type: "Emergency Response",
            status: "En Route",
            icon: "warning"
          },
          ...prev
        ];
      });
    });
  }, [activeIncidents]);

  const [selectedCamera, setSelectedCamera] = useState<Camera | null>(null);
  const [cameraSearch, setCameraSearch] = useState("");
  const [selectedIncident, setSelectedIncident] = useState<Incident | null>(null);
  const [selectedViolationEvent, setSelectedViolationEvent] = useState<string | null>(null);
  const [liveClock, setLiveClock] = useState("");

  // Notification History State
  const [notificationHistory, setNotificationHistory] = useState<Incident[]>([]);

  // Seed and update notification history from DB response
  useEffect(() => {
    if (incidentsWithSnapshots.length > 0) {
      setNotificationHistory((prev) => {
        const combined = [...prev, ...incidentsWithSnapshots];
        const seen = new Set<string>();
        return combined
          .filter((item) => {
            if (seen.has(item.id)) return false;
            seen.add(item.id);
            return true;
          })
          .sort((a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime());
      });
    }
  }, [incidentsWithSnapshots]);

  // Fetch violation events from hayden AI pipeline for notification history
  const mapViolationType = (vt: string): Incident["type"] => {
    const MAP: Record<string, string> = {
      confirmed_illegal_parking: "illegal_parking",
      illegal_parking: "illegal_parking",
      parking_violation: "illegal_parking",
      shoulder_violation: "shoulder_violation",
      red_light_violation: "red_light_violation",
      illegal_u_turn: "illegal_u_turn",
      traffic_sign_violation: "busway_violation",
      unsafe_lane_change: "unsafe_lane_change",
      hazard_lights_violation: "hazard_lights",
      congestion: "congestion",
      busway_violation: "busway_violation",
    };
    return (MAP[vt] || "illegal_parking") as Incident["type"];
  };

  useEffect(() => {
    getViolationEvents().then((events) => {
      if (!events?.length) return;
      const mapped = events.map((ev: any) => ({
        id: ev.event_id,
        camera_id: ev.source || ev.road_name || "CCTV",
        type: mapViolationType(ev.violation_type),
        lat: ev.latitude,
        lng: ev.longitude,
        severity: (ev.confidence > 0.8 ? "high" : ev.confidence > 0.6 ? "medium" : "low") as "low" | "medium" | "high",
        confidence_score: ev.confidence,
        source_count: 1,
        status: "detected" as const,
        timestamp: ev.timestamp,
      }));
      setNotificationHistory((prev) => {
        const combined = [...mapped, ...prev];
        const seen = new Set<string>();
        return combined
          .filter((item) => {
            if (seen.has(item.id)) return false;
            seen.add(item.id);
            return true;
          })
          .sort((a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime());
      });
    }).catch(() => {});
  }, []);

  // Activity Log State & Helpers
  const [activities, setActivities] = useState<ActivityItem[]>([]);

  // Live dashcam violations are shown through the existing incident stepper modal.
  const [liveViolationIncidents, setLiveViolationIncidents] = useState<Incident[]>([]);

  const addActivity = useCallback((type: "incident" | "task" | "team", action: string, title: string, description: string, icon: string, color: string, referenceId?: string) => {
    const newAct: ActivityItem = {
      id: `${type}-${action}-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`,
      type,
      action,
      title,
      description,
      timestamp: new Date(),
      icon,
      color,
      referenceId
    };
    setActivities(prev => [newAct, ...prev]);
  }, []);

  const handlePanelActivityLog = useCallback((type: "incident" | "task" | "team", action: string, title: string, description: string, icon: string, color: string) => {
    addActivity(type, action, title, description, icon, color);
  }, [addActivity]);

  // Seed activities from DB response initially
  useEffect(() => {
    if (incidentsWithSnapshots.length > 0 && activities.length === 0) {
      const initialActivities: ActivityItem[] = [];
      incidentsWithSnapshots.forEach((inc: Incident) => {
        const time = new Date(inc.timestamp);
        const typeLabel = inc.type.replace("_", " ");

        // 1. Detected Activity
        initialActivities.push({
          id: `inc-det-${inc.id}`,
          type: "incident",
          action: "detected",
          title: `Deteksi Insiden`,
          description: `Pelanggaran ${typeLabel} terdeteksi pada kamera ${inc.camera_id.toUpperCase()}`,
          timestamp: time,
          icon: "warning",
          color: "bg-error/10 text-error",
          referenceId: inc.id
        });

        // 2. Confirmed Activity (if not detected)
        if (inc.status !== "detected") {
          initialActivities.push({
            id: `inc-conf-${inc.id}`,
            type: "incident",
            action: "confirmed",
            title: `Insiden Terkonfirmasi`,
            description: `Pelanggaran ${typeLabel} telah divalidasi oleh operator`,
            timestamp: new Date(time.getTime() + 30000),
            icon: "rule",
            color: "bg-primary/10 text-primary",
            referenceId: inc.id
          });
        }

        // 3. Dispatched Activity
        if (inc.status === "dispatched" || inc.status === "resolved" || inc.status === "closed") {
          initialActivities.push({
            id: `inc-disp-${inc.id}`,
            type: "incident",
            action: "dispatched",
            title: `Petugas Dikirim`,
            description: `Petugas ${inc.assigned_officer || "Unit Patroli"} dikirim ke lokasi`,
            timestamp: new Date(time.getTime() + 90000),
            icon: "local_shipping",
            color: "bg-secondary-container text-secondary",
            referenceId: inc.id
          });
        }

        // 4. Resolved Activity
        if (inc.status === "resolved" || inc.status === "closed") {
          initialActivities.push({
            id: `inc-res-${inc.id}`,
            type: "incident",
            action: "resolved",
            title: `Kasus Selesai`,
            description: `Insiden diselesaikan oleh ${inc.assigned_officer || "petugas"}. Catatan: ${inc.resolution_notes || "Lalu lintas kembali normal"}`,
            timestamp: new Date(time.getTime() + 600000),
            icon: "task_alt",
            color: "bg-emerald-50 text-emerald-700",
            referenceId: inc.id
          });
        }
      });

      initialActivities.sort((a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime());
      setActivities(initialActivities);
    }
  }, [incidentsWithSnapshots, activities.length]);

  // V2 Overlay States
  const [showCameras, setShowCameras] = useState(true);
  const [showIncidents, setShowIncidents] = useState(true);
  const [showHeatmap, setShowHeatmap] = useState(false);
  const [showRiskZones, setShowRiskZones] = useState(false);
  const [showPlacements, setShowPlacements] = useState(false);
  const [showPatrol, setShowPatrol] = useState(true);
  const [selectedPatrol, setSelectedPatrol] = useState<PatrolVehicle | null>(null);
  const [patrolPositions, setPatrolPositions] = useState<Record<string, PatrolRuntimePosition>>({});
  const [placementType, setPlacementType] = useState<"camera_etle" | "officer">("camera_etle");

  const [eventPredictions, setEventPredictions] = useState<EventPrediction[]>([]);
  const [heatmapFilters, setHeatmapFilters] = useState<any>({
    days: 30,
    hourFrom: 0,
    hourTo: 23,
    dayOfWeek: undefined,
    violationType: undefined,
  });

  // Live ticking clock in header
  useEffect(() => {
    const updateTime = () => {
      const now = new Date();
      setLiveClock(now.toLocaleTimeString("en-US", {
        hour12: false,
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit"
      }));
    };
    updateTime();
    const interval = setInterval(updateTime, 1000);
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    document.documentElement.classList.toggle("dark", theme === "dark");
    window.localStorage.setItem("traffic-theme", theme);
  }, [theme]);

  // Listen to live violations/incidents from WebSocket
  const handleWSMessage = useCallback((msg: WSMessage) => {
    // Invalidate React Query caches to trigger UI update
    if (
      msg.type === "incident" ||
      msg.type === "incident_update" ||
      msg.type === "incident_status_change"
    ) {
      queryClient.invalidateQueries({ queryKey: ["incidents"] });
      queryClient.invalidateQueries({ queryKey: ["active-incidents-list"] });
      queryClient.invalidateQueries({ queryKey: ["summary-stats"] });

      // Also trigger browser notification panel
      if (msg.type === "incident") {
        addFromWSMessage(msg);

        // Add to notification history (deduplicated)
        setNotificationHistory((prev) => {
          const filtered = prev.filter((item) => item.id !== msg.payload.id);
          return [msg.payload, ...filtered];
        });

        // Log to Activity Log
        addActivity(
          "incident",
          "detected",
          "Deteksi Insiden",
          `Pelanggaran ${msg.payload.type.replace("_", " ")} terdeteksi pada kamera ${msg.payload.camera_id.toUpperCase()}`,
          "warning",
          "bg-error/10 text-error",
          msg.payload.id
        );
      } else if (msg.type === "incident_status_change" && msg.payload) {
        setNotificationHistory((prev) => {
          const updated = prev.map((item) =>
            item.id === msg.payload.incident_id
              ? { ...item, status: msg.payload.status }
              : item
          );

          // Log status change to activities using the updated / existing incident type
          const existingInc = updated.find(item => item.id === msg.payload.incident_id);
          const typeStr = existingInc ? existingInc.type.replace("_", " ") : "lalu lintas";
          const officerStr = msg.payload.assigned_officer || (existingInc ? existingInc.assigned_officer : "Unit Patroli");
          const notesStr = msg.payload.resolution_notes || (existingInc ? existingInc.resolution_notes : "Arus kembali normal");

          const statusLabels: Record<string, { title: string; desc: string; icon: string; color: string }> = {
            confirmed: { title: "Insiden Terkonfirmasi", desc: `Pelanggaran ${typeStr} telah divalidasi oleh operator`, icon: "rule", color: "bg-primary/10 text-primary" },
            dispatched: { title: "Petugas Dikirim", desc: `Petugas ${officerStr} dikerahkan ke lokasi`, icon: "local_shipping", color: "bg-secondary-container text-secondary" },
            resolved: { title: "Kasus Selesai", desc: `Insiden dinyatakan selesai. Catatan: ${notesStr}`, icon: "task_alt", color: "bg-emerald-50 text-emerald-700" },
            closed: { title: "Kasus Ditutup", desc: "Kasus telah ditutup dan diarsipkan", icon: "folder_zip", color: "bg-slate-100 text-slate-700" }
          };

          const info = statusLabels[msg.payload.status];
          if (info) {
            addActivity("incident", msg.payload.status, info.title, info.desc, info.icon, info.color, msg.payload.incident_id);
          }

          return updated;
        });
      } else if (msg.type === "incident_update" && msg.payload) {
        setNotificationHistory((prev) =>
          prev.map((item) =>
            item.id === msg.payload.incident_id
              ? {
                  ...item,
                  source_count: msg.payload.source_count,
                  confidence_score: msg.payload.confidence_score,
                }
              : item
          )
        );
      }
    } else if (msg.type === "event_prediction" && msg.payload) {
      const pred = msg.payload as EventPrediction;
      setEventPredictions((prev) => {
        const filtered = prev.filter((p) => p.event_id !== pred.event_id);
        return [pred, ...filtered];
      });
      alert(`Peringatan dampak kemacetan baru untuk event "${pred.event_name}" diterima!`);
    }
  }, [queryClient, addFromWSMessage, addActivity, notificationHistory]);

  useWebSocket(handleWSMessage);

  const isLoading = loadingCams;
  const normalizedCameraSearch = cameraSearch.trim().toLowerCase();
  const filteredCameras = normalizedCameraSearch
    ? cameras.filter((camera: Camera) => {
        const haystack = [
          camera.id,
          camera.name,
          camera.lat.toFixed(4),
          camera.lng.toFixed(4),
          camera.stream_url || "",
        ].join(" ").toLowerCase();
        return haystack.includes(normalizedCameraSearch);
      })
    : cameras;

  const getLiveViolationLocationForVideo = useCallback((videoFile?: string) => {
    const patrol = PATROL_VEHICLES.find((vehicle) => vehicle.videoFile === videoFile);
    const runtimePosition = patrol ? patrolPositions[patrol.id] : undefined;
    if (runtimePosition) {
      return { lng: runtimePosition.lng, lat: runtimePosition.lat };
    }
    return getLiveViolationLocation(videoFile);
  }, [patrolPositions]);

  const addRuntimeIncident = useCallback((incident: Incident) => {
    setLiveViolationIncidents((prev) => [
      incident,
      ...prev.filter((item) => item.id !== incident.id),
    ].slice(0, 80));
    setNotificationHistory((prev) => [
      incident,
      ...prev.filter((item) => item.id !== incident.id),
    ].slice(0, 120));
  }, []);

  const createPersistedIncident = useCallback(async (
    payload: Omit<Incident, "id"> & { id?: string; camera_name?: string; broadcast?: boolean },
  ) => {
    const saved = await createIncident(payload);
    const enriched = enrichIncidentWithEvidence({
      ...saved,
      snapshot_url: getIncidentSnapshotUrl(saved),
    });

    addRuntimeIncident(enriched);
    queryClient.invalidateQueries({ queryKey: ["incidents"] });
    queryClient.invalidateQueries({ queryKey: ["active-incidents-list"] });
    queryClient.invalidateQueries({ queryKey: ["summary-stats"] });
    return enriched;
  }, [addRuntimeIncident, queryClient]);

  const handleRandomPatrolViolation = useCallback(async (event: PatrolGeneratedViolation) => {
    const config = pickRandom(RANDOM_PATROL_VIOLATION_RULES);
    const timestamp = new Date(event.generatedAt);
    const snapshotUrl = pickRandom(config.snapshots);
    const evidence = getEvidenceMetadataForSnapshot(snapshotUrl);
    const sourceCount = 1 + Math.floor(Math.random() * 4);
    const confidence = 0.78 + Math.random() * 0.17;
    const description = `${evidence.description || config.description} Sumber: ${event.vehicle.label}. Evidence: ${snapshotUrl.replace("/snapshots/", "")}.`;

    try {
      const incident = await createPersistedIncident({
        camera_id: event.vehicle.id,
        camera_name: event.vehicle.label,
        type: config.type,
        lat: event.position.lat,
        lng: event.position.lng,
        severity: confidence > 0.88 ? "high" : "medium",
        confidence_score: confidence,
        source_count: sourceCount,
        status: "detected",
        timestamp: timestamp.toISOString(),
        snapshot_url: snapshotUrl,
        description,
        vehicle_type: evidence.vehicle_type || config.vehicleType,
        plate_number: evidence.plate_number,
        plate_note: evidence.plate_note,
        broadcast: true,
      });

      addActivity(
        "incident",
        config.type,
        config.title,
        `[${event.vehicle.label}] ${incident.description}`,
        config.icon,
        "bg-primary-fixed/20 text-primary",
        incident.id,
      );
    } catch (error) {
      console.error("[Incident] Failed to persist random patrol violation", error);
    }
  }, [addActivity, createPersistedIncident]);

  const handleRuntimeViolationDetected = useCallback(async (v: RuntimeViolationLog) => {
    const iconMap: Record<string, string> = {
      traffic_sign: "signpost",
      traffic_sign_detected: "signpost",
      red_light: "traffic",
      red_light_detected: "traffic",
      plate_read: "badge",
      plate_number_read: "badge",
      high_traffic: "directions_car",
      high_traffic_density: "directions_car",
      pedestrian_on_road: "directions_walk",
      bicycle_in_vehicle_lane: "pedal_bike",
      illegal_parking: "local_parking",
      shoulder_violation: "alt_route",
      red_light_violation: "traffic",
      illegal_u_turn: "u_turn_right",
      unsafe_lane_change: "swap_horiz",
      violation: "warning",
    };
    const colorMap: Record<string, string> = {
      traffic_sign: "bg-amber-50 text-amber-700",
      traffic_sign_detected: "bg-amber-50 text-amber-700",
      red_light: "bg-red-50 text-red-700",
      red_light_detected: "bg-red-50 text-red-700",
      plate_read: "bg-blue-50 text-blue-700",
      plate_number_read: "bg-blue-50 text-blue-700",
      high_traffic: "bg-orange-50 text-orange-700",
      high_traffic_density: "bg-orange-50 text-orange-700",
      pedestrian_on_road: "bg-purple-50 text-purple-700",
      bicycle_in_vehicle_lane: "bg-teal-50 text-teal-700",
      illegal_parking: "bg-red-50 text-red-700",
      shoulder_violation: "bg-red-50 text-red-700",
      red_light_violation: "bg-red-50 text-red-700",
      illegal_u_turn: "bg-red-50 text-red-700",
      unsafe_lane_change: "bg-red-50 text-red-700",
      violation: "bg-error/10 text-error",
    };
    const titleMap: Record<string, string> = {
      traffic_sign: "Rambu Lalu Lintas",
      traffic_sign_detected: "Rambu Lalu Lintas",
      red_light: "Lampu Merah",
      red_light_detected: "Lampu Merah",
      plate_read: "Plat Nomor Terbaca",
      plate_number_read: "Plat Nomor Terbaca",
      high_traffic: "Kepadatan Tinggi",
      high_traffic_density: "Kepadatan Tinggi",
      pedestrian_on_road: "Pejalan Kaki di Jalan",
      bicycle_in_vehicle_lane: "Sepeda di Lajur Kendaraan",
      illegal_parking: "Parkir Sembarangan",
      shoulder_violation: "Pelanggaran Bahu Jalan",
      red_light_violation: "Menerobos Lampu Merah",
      illegal_u_turn: "Putar Arah Terlarang",
      unsafe_lane_change: "Potong Lajur Berbahaya",
      violation: "Pelanggaran",
    };

    const timestampSeconds = Date.now() / 1000;
    const location = getLiveViolationLocationForVideo(v.videoFile);
    const evidence = getEvidenceMetadataForVideo(v.videoFile);
    const patrol = PATROL_VEHICLES.find((vehicle) => vehicle.videoFile === v.videoFile);

    try {
      const liveIncident = await createPersistedIncident({
        camera_id: patrol?.id || v.source.replace(/[^a-z0-9_-]+/gi, "_").toLowerCase().slice(0, 48) || "dashcam",
        camera_name: v.source,
        type: mapViolationType(v.type),
        lat: location.lat,
        lng: location.lng,
        severity: "high",
        confidence_score: 0.85,
        source_count: 1,
        status: "detected",
        timestamp: new Date(timestampSeconds * 1000).toISOString(),
        snapshot_url: evidence.snapshot_url || v.evidenceImage,
        snapshot_size: v.evidenceSize,
        description: evidence.description || v.detail,
        vehicle_type: evidence.vehicle_type || v.vehicleType,
        plate_number: evidence.plate_number || v.plate,
        plate_crop: v.plateCrop,
        plate_bbox: v.plateBbox,
        plate_confidence: v.plateConfidence,
        plate_note: evidence.plate_note || v.plateNote,
        video_time_seconds: v.videoTimeSeconds,
        broadcast: true,
      });

      addActivity(
        "incident",
        v.type,
        titleMap[v.type] || v.type.replace(/_/g, " "),
        `[${v.source}] ${liveIncident.description || v.detail}${liveIncident.plate_number ? ` - Plat: ${liveIncident.plate_number}` : ""}`,
        iconMap[v.type] || "warning",
        colorMap[v.type] || "bg-error/10 text-error",
        liveIncident.id,
      );
    } catch (error) {
      console.error("[Incident] Failed to persist live dashcam violation", error);
    }
  }, [addActivity, createPersistedIncident, getLiveViolationLocationForVideo, mapViolationType]);

  const mapIncidents = useMemo(() => {
    const persistedIds = new Set(activeIncidents.map((incident: Incident) => incident.id));
    return [
      ...activeIncidents,
      ...liveViolationIncidents.filter((incident) => !persistedIds.has(incident.id)),
    ];
  }, [activeIncidents, liveViolationIncidents]);

  return (
    <div className="w-screen h-screen relative overflow-hidden bg-background text-on-surface font-body-md selection:bg-primary-fixed-dim/20">
      {/* Loading Overlay */}
      {isLoading && (
        <div className="absolute inset-0 bg-background/90 flex items-center justify-center z-[9999] text-primary transition-all pointer-events-none">
          <div className="flex flex-col items-center gap-3">
            <span className="material-symbols-outlined text-[32px] animate-spin">sync</span>
            <span className="text-[12px] font-bold tracking-wider uppercase">Memuat Sistem Taktis...</span>
          </div>
        </div>
      )}

      {/* Mapbox Layer */}
      <div className="absolute inset-0 z-0">
        <MapContainer
          cameras={filteredCameras}
          setSelectedCamera={setSelectedCamera}
          activeIncidents={mapIncidents}
          showHeatmap={showHeatmap}
          heatmapFilters={heatmapFilters}
          showRiskZones={showRiskZones}
          showPlacements={showPlacements}
          placementType={placementType}
          eventPredictions={eventPredictions}
          showCameras={showCameras}
          showIncidents={showIncidents}
          showPatrol={showPatrol}
          onIncidentClick={async (incident) => {
            if (!isUuid(incident.id)) {
              try {
                const persisted = await createPersistedIncident({
                  ...enrichIncidentWithEvidence(incident),
                  camera_name: incident.camera_id,
                  broadcast: false,
                });
                setSelectedIncident(persisted);
              } catch (error) {
                console.error("[Incident] Failed to persist map marker before opening detail", error);
              }
              return;
            }
            const liveIncident = liveViolationIncidents.find((item) => item.id === incident.id);
            setSelectedIncident(liveIncident || incident);
          }}
          onPatrolClick={setSelectedPatrol}
          onPatrolPositionsUpdate={setPatrolPositions}
          onRandomPatrolViolation={handleRandomPatrolViolation}
          theme={theme}
        />
      </div>

      {/* Real-time alerts sliding toasts */}
      <NotificationPanel notifications={notifications} onDismiss={dismissNotification} />

      {/* TOP NAVIGATION BAR */}
      <header className="fixed top-0 left-0 w-full z-50 h-14 bg-surface-matte/90 backdrop-blur-md border-b border-outline-variant flex items-center justify-between px-lg shadow-sm">
        <div className="flex items-center gap-8">
          <div className="flex items-center gap-3">
            <img
              src={theme === "dark" ? "/artery_dark.png" : "/artery.png"}
              alt="artery"
              className="h-8 w-8 rounded-lg border border-outline-variant bg-surface-bright object-contain shadow-sm"
            />
            <h1 className="text-[15px] font-black tracking-tight text-on-surface">Artery</h1>
          </div>
          <nav className="hidden lg:flex items-center gap-6">
            <a className="text-[12px] font-bold text-primary border-b-2 border-primary py-4" href="#" onClick={(e) => e.preventDefault()}>Dashboard</a>
            <a className="text-[12px] font-medium text-on-surface-variant hover:text-on-surface transition-colors py-4" href="#" onClick={(e) => { e.preventDefault(); setRightTab("analytics"); setRightSidebarOpen(true); }}>Analytics</a>
            <a className="text-[12px] font-medium text-on-surface-variant hover:text-on-surface transition-colors py-4" href="#" onClick={(e) => { e.preventDefault(); setRightTab("analytics"); setRightSidebarOpen(true); }}>Simulation</a>
            <a className="text-[12px] font-medium text-on-surface-variant hover:text-on-surface transition-colors py-4" href="#" onClick={(e) => { e.preventDefault(); setRightTab("analytics"); setRightSidebarOpen(true); }}>Executive summary</a>
          </nav>
        </div>
        <div className="flex items-center gap-6">
          <div className="relative z-50">
            <div className="flex items-center bg-surface-container/50 border border-outline-variant rounded-full px-3 py-1.5 transition-all focus-within:ring-2 focus-within:ring-primary/20 focus-within:border-primary">
              <span className="material-symbols-outlined text-[18px] text-on-surface-variant mr-2">search</span>
              <input
                type="text"
                placeholder="Cari CCTV (Ketik nama/ID)..."
                className="bg-transparent border-none outline-none text-[12px] w-64 text-on-surface placeholder:text-on-surface-variant/70"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                onFocus={() => setIsSearchFocused(true)}
                onBlur={() => setTimeout(() => setIsSearchFocused(false), 200)}
              />
              {searchQuery && (
                <button
                  onClick={() => setSearchQuery("")}
                  className="material-symbols-outlined text-[16px] text-on-surface-variant hover:text-on-surface ml-2"
                >
                  close
                </button>
              )}
            </div>
            {isSearchFocused && searchQuery && (
              <div className="absolute top-full right-0 mt-2 w-[320px] bg-white border border-outline-variant rounded-2xl shadow-xl overflow-hidden flex flex-col max-h-[300px] overflow-y-auto">
                {cameras.filter(c => c.name.toLowerCase().includes(searchQuery.toLowerCase()) || c.id.toLowerCase().includes(searchQuery.toLowerCase())).map(cam => (
                  <button
                    key={cam.id}
                    className="text-left px-4 py-3 hover:bg-slate-50 border-b border-outline-variant/50 last:border-b-0 transition-colors flex items-center gap-3"
                    onClick={() => {
                      setSelectedCamera(cam);
                      setSearchQuery("");
                    }}
                  >
                    <div className="w-10 h-10 rounded-lg bg-slate-100 flex items-center justify-center flex-shrink-0">
                      <span className="material-symbols-outlined text-primary">videocam</span>
                    </div>
                    <div>
                      <div className="text-[12px] font-bold text-on-surface">{cam.name}</div>
                      <div className="text-[10px] text-on-surface-variant">{cam.id}</div>
                    </div>
                  </button>
                ))}
                {cameras.filter(c => c.name.toLowerCase().includes(searchQuery.toLowerCase()) || c.id.toLowerCase().includes(searchQuery.toLowerCase())).length === 0 && (
                  <div className="px-4 py-6 text-center">
                    <span className="material-symbols-outlined text-on-surface-variant text-[24px] mb-2">search_off</span>
                    <div className="text-[12px] font-bold text-on-surface">Tidak ditemukan</div>
                    <div className="text-[10px] text-on-surface-variant mt-1">CCTV dengan kata kunci "{searchQuery}" tidak ada.</div>
                  </div>
                )}
              </div>
            )}
          </div>

          <div className="flex items-center gap-6 pr-6 border-r border-outline-variant h-6">
            <div className="flex flex-col items-end">
              <span className="text-[10px] text-on-surface-variant leading-none">SYSTEM HEALTH</span>
              <span className="text-[12px] font-semibold text-primary leading-tight">
                {cameras.length > 0 ? "100%" : "94%"}
              </span>
            </div>
            <div className="flex flex-col items-end">
              <span className="text-[10px] text-on-surface-variant leading-none">JAKARTA</span>
              <span className="text-[12px] font-semibold text-on-surface leading-tight" id="live-clock">{liveClock}</span>
            </div>
          </div>
          <div className="flex items-center gap-4">
            <div
              className="flex h-8 items-center gap-1 rounded-full border border-outline-variant bg-surface-container-low px-1.5 shadow-sm"
            >
              <button
                onClick={() => setTheme("light")}
                title="Switch to light mode"
                aria-label="Switch to light mode"
                className={`material-symbols-outlined flex h-5 w-5 items-center justify-center rounded-full text-[14px] transition-colors cursor-pointer ${
                  theme === "light" ? "bg-primary text-on-primary" : "text-on-surface-variant hover:text-on-surface"
                }`}
              >light_mode</button>
              <button
                onClick={() => setTheme("dark")}
                title="Switch to dark mode"
                aria-label="Switch to dark mode"
                className={`material-symbols-outlined flex h-5 w-5 items-center justify-center rounded-full text-[14px] transition-colors cursor-pointer ${
                  theme === "dark" ? "bg-primary text-on-primary" : "text-on-surface-variant hover:text-on-surface"
                }`}
              >dark_mode</button>
            </div>
            <button
              onClick={() => {
                setRightTab("activities");
                setRightSidebarOpen(true);
              }}
              className="material-symbols-outlined text-on-surface-variant hover:text-on-surface text-[20px] relative"
            >
              notifications
              {activeIncidents.length > 0 && (
                <span className="absolute top-0 right-0 w-2 h-2 bg-error rounded-full" />
              )}
            </button>
            <button
              onClick={() => alert("Pengaturan Peta: Gunakan panel kanan untuk mengaktifkan heatmap atau simulator penempatan.")}
              className="material-symbols-outlined text-on-surface-variant hover:text-on-surface text-[20px]"
            >
              settings
            </button>
            <div className="w-7 h-7 rounded-full bg-surface-container border border-outline-variant overflow-hidden shadow-sm">
              <img alt="User profile" className="w-full h-full object-cover" src="https://lh3.googleusercontent.com/aida-public/AB6AXuBe7tiUvA_EBnagUuWcgYJVPJGvxKMUmGj3IX700HrrxGvouKzK6U6BakoNgd0Ww49IrzwHANtS1Zo2HEWmdySSJ2eFlMRkhEoivG7jnhs315DEqNAECFE7p361enW6TXQGirtLWn4I1Drl4J9G_RAfAB1O7Wvb7QPgQ-0phIKLpJuxlTAwa5gRJ3rajonaT-F2MeaBrA6wlbmwJ_KuzLw9LqGcxk9m7EGXjt21W8ImLE9gjZckzMxqhz17f1EBh_6Jn6yD-YnEyg" />
            </div>
          </div>
        </div>
      </header>

      {/* LEFT SIDEBAR: LIVE AI DETECTIONS */}
      <aside className="fixed left-lg top-20 w-16 z-40 flex flex-col gap-2">
        <button
          onClick={() => setLeftSidebarOpen(!leftSidebarOpen)}
          className="bg-white/40 backdrop-blur-md border border-white/20 rounded-full w-16 h-16 flex items-center justify-center hover:bg-white/60 transition-all shadow-xl text-on-surface-variant"
        >
          <span className="material-symbols-outlined">
            {leftSidebarOpen ? "chevron_left" : "chevron_right"}
          </span>
        </button>
        <div className="bg-white/40 backdrop-blur-md border border-white/20 rounded-full flex-1 flex flex-col items-center py-6 gap-8 overflow-hidden shadow-2xl">
          {[
            { key: "incidents", icon: "warning", title: "Live Incidents", hasDot: activeIncidents.length > 0 },
            { key: "sensors", icon: "sensors", title: "Sensor Status", hasDot: true },
            { key: "cameras", icon: "videocam", title: "CCTV Cameras", hasDot: false },
            { key: "officers", icon: "groups", title: "Officer Units", hasDot: true },
          ].map((item) => (
            <button
              key={item.key}
              title={item.title}
              onClick={() => {
                setLeftTab(item.key as "incidents" | "sensors" | "cameras" | "officers");
                setLeftSidebarOpen(true);
              }}
              className={`relative w-10 h-10 rounded-full flex items-center justify-center transition-all ${
                leftSidebarOpen && leftTab === item.key
                  ? "bg-primary/10 text-primary"
                  : "text-on-surface-variant hover:text-on-surface hover:bg-white/40"
              }`}
            >
              <span className="material-symbols-outlined">{item.icon}</span>
              {item.hasDot && (
                <span className="absolute top-1 right-1 w-2 h-2 bg-primary rounded-full" />
              )}
            </button>
          ))}
        </div>
      </aside>

      {/* LEFT EXPANDED DRAWER: LIVE INCIDENTS / CAMERA FEEDS LIST */}
      {leftSidebarOpen && (
        <aside className="fixed left-[calc(24px+64px+12px)] top-20 bottom-lg w-80 z-40 bg-white/80 backdrop-blur-md border border-white/20 rounded-3xl shadow-2xl flex flex-col overflow-hidden transition-all animate-in slide-in-from-left-4 duration-300">
          <div className="p-6 border-b border-outline-variant flex items-center justify-between flex-shrink-0">
            <div className="flex items-center gap-2">
              <span className="material-symbols-outlined text-primary">
                {leftTab === "incidents" ? "warning" : leftTab === "sensors" ? "sensors" : leftTab === "cameras" ? "videocam" : "groups"}
              </span>
              <h2 className="text-[14px] font-bold uppercase tracking-tight text-on-surface">
                {leftTab === "incidents" ? "Live Incidents" : leftTab === "sensors" ? "Sensor Status" : leftTab === "cameras" ? "CCTV Cameras" : "Officer Units"}
              </h2>
            </div>
            <span className={`text-[10px] font-bold px-2 py-1 rounded-full ${
              leftTab === "incidents" ? "bg-error/10 text-error" : "bg-primary/10 text-primary"
            }`}>
              {leftTab === "incidents" ? `${activeIncidents.length} ACTIVE` : leftTab === "cameras" ? `${filteredCameras.length}/${cameras.length} CCTV` : "ONLINE"}
            </span>
          </div>

          <div className="flex-1 overflow-y-auto">
            {leftTab === "incidents" && <IncidentPanel onIncidentSelect={setSelectedIncident} />}

            {leftTab === "sensors" && (
              <div className="p-4 flex flex-col gap-3">
                {["Radar traffic", "ANPR detector", "CCTV stream", "Redis websocket"].map((name) => (
                  <div key={name} className="p-3 bg-white/70 border border-outline-variant rounded-xl flex items-center justify-between">
                    <div>
                      <div className="text-[12px] font-bold text-on-surface">{name}</div>
                      <div className="text-[10px] text-on-surface-variant">Sinkronisasi normal</div>
                    </div>
                    <span className="text-[10px] font-bold text-primary bg-primary/10 px-2 py-1 rounded-full">ONLINE</span>
                  </div>
                ))}
              </div>
            )}

            {leftTab === "cameras" && (
              <div className="p-4 flex flex-col gap-3">
                <div className="relative">
                  <span className="material-symbols-outlined absolute left-3 top-1/2 -translate-y-1/2 text-[17px] text-on-surface-variant">search</span>
                  <input
                    type="search"
                    value={cameraSearch}
                    onChange={(e) => setCameraSearch(e.target.value)}
                    placeholder="Cari nama, ID, atau koordinat kamera"
                    className="w-full rounded-xl border border-outline-variant bg-white/80 py-2.5 pl-9 pr-9 text-[12px] font-semibold text-on-surface outline-none transition-all placeholder:font-normal placeholder:text-on-surface-variant focus:border-primary focus:bg-white focus:ring-2 focus:ring-primary/10"
                  />
                  {cameraSearch && (
                    <button
                      onClick={() => setCameraSearch("")}
                      className="absolute right-2 top-1/2 -translate-y-1/2 rounded-lg p-1 text-on-surface-variant hover:bg-surface-container-high hover:text-on-surface"
                      aria-label="Clear camera search"
                    >
                      <span className="material-symbols-outlined text-[16px]">close</span>
                    </button>
                  )}
                </div>

                {filteredCameras.map((camera) => (
                  <button
                    key={camera.id}
                    onClick={() => setSelectedCamera(camera)}
                    className="p-3 bg-white/70 hover:bg-white border border-outline-variant rounded-xl text-left transition-all"
                  >
                    <div className="text-[12px] font-bold text-on-surface">{camera.name}</div>
                    <div className="text-[10px] text-on-surface-variant">{camera.id} · {camera.lat.toFixed(4)}, {camera.lng.toFixed(4)}</div>
                  </button>
                ))}
                {filteredCameras.length === 0 && (
                  <div className="rounded-xl border border-dashed border-outline-variant bg-white/50 p-4 text-[12px] text-on-surface-variant">
                    {cameras.length === 0 ? "Kamera belum tersedia." : "Tidak ada kamera yang cocok."}
                  </div>
                )}
              </div>
            )}

            {leftTab === "officers" && (
              <div className="p-4 flex flex-col gap-3">
                {[
                  { name: "Unit Pengurai Kemacetan", count: 8, status: "Siaga" },
                  { name: "Unit ETLE Mobile", count: 4, status: "Patroli" },
                  { name: "Unit Crowd Control", count: 6, status: "Siaga" },
                ].map((unit) => (
                  <div key={unit.name} className="p-3 bg-white/70 border border-outline-variant rounded-xl">
                    <div className="flex items-center justify-between">
                      <div className="text-[12px] font-bold text-on-surface">{unit.name}</div>
                      <span className="text-[10px] font-bold text-primary">{unit.count} unit</span>
                    </div>
                    <div className="text-[10px] text-on-surface-variant mt-1">{unit.status}</div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </aside>
      )}

      {/* RIGHT SIDEBAR: EXPAND COLLAPSE BUTTON & DOCK */}
      <aside className="fixed right-lg top-20 w-16 z-40 flex flex-col gap-2">
        <button
          onClick={() => setRightSidebarOpen(!rightSidebarOpen)}
          className="bg-white/40 backdrop-blur-md border border-white/20 rounded-full w-16 h-16 flex items-center justify-center hover:bg-white/60 transition-all shadow-xl text-on-surface-variant"
        >
          <span className="material-symbols-outlined">
            {rightSidebarOpen ? "chevron_right" : "chevron_left"}
          </span>
        </button>

        {/* Floating dock for tab selection */}
        <div className="bg-white/40 backdrop-blur-md border border-white/20 rounded-full flex flex-col items-center py-6 gap-8 shadow-2xl h-fit">
          <button
            onClick={() => { setRightTab("events"); setRightSidebarOpen(true); }}
            title="Upcoming Events"
            className={`relative p-2 rounded-full transition-colors ${rightSidebarOpen && rightTab === "events" ? "text-primary bg-primary/10" : "text-on-surface-variant hover:text-on-surface"}`}
          >
            <span className="material-symbols-outlined">event</span>
          </button>

          <button
            onClick={() => { setRightTab("analytics"); setRightSidebarOpen(true); }}
            title="Analytics & Planning"
            className={`relative p-2 rounded-full transition-colors ${rightSidebarOpen && rightTab === "analytics" ? "text-primary bg-primary/10" : "text-on-surface-variant hover:text-on-surface"}`}
          >
            <span className="material-symbols-outlined">bar_chart</span>
            <span className="absolute -top-1 -right-1 w-2 h-2 bg-primary rounded-full"></span>
          </button>

          <button
            onClick={() => { setRightTab("tasks"); setRightSidebarOpen(true); }}
            title="Mitigation Tasks"
            className={`relative p-2 rounded-full transition-colors ${rightSidebarOpen && rightTab === "tasks" ? "text-primary bg-primary/10" : "text-on-surface-variant hover:text-on-surface"}`}
          >
            <span className="material-symbols-outlined">playlist_add_check</span>
            {tasks.length > 0 && (
              <span className="absolute -top-1 -right-1 w-2 h-2 bg-primary-fixed-dim rounded-full animate-pulse" />
            )}
          </button>

          <button
            onClick={() => { setRightTab("activities"); setRightSidebarOpen(true); }}
            title="Activity Log"
            className={`relative p-2 rounded-full transition-colors ${rightSidebarOpen && rightTab === "activities" ? "text-primary bg-primary/10" : "text-on-surface-variant hover:text-on-surface"}`}
          >
            <span className="material-symbols-outlined">history</span>
            {activeIncidents.length > 0 && (
              <span className="absolute -top-1 -right-1 w-2 h-2 bg-error rounded-full animate-pulse" />
            )}
          </button>

          <button
            onClick={() => { setRightTab("upload"); setRightSidebarOpen(true); }}
            title="Import Video"
            className={`relative p-2 rounded-full transition-colors ${rightSidebarOpen && rightTab === "upload" ? "text-primary bg-primary/10" : "text-on-surface-variant hover:text-on-surface"}`}
          >
            <span className="material-symbols-outlined">upload_file</span>
          </button>

          <button
            onClick={() => { setRightTab("livecam"); setRightSidebarOpen(true); }}
            title="Live Cam & Dashcam"
            className={`relative p-2 rounded-full transition-colors ${rightSidebarOpen && rightTab === "livecam" ? "text-primary bg-primary/10" : "text-on-surface-variant hover:text-on-surface"}`}
          >
            <span className="material-symbols-outlined">videocam</span>
          </button>
        </div>
      </aside>

      {/* RIGHT EXPANDED DRAWER: EVENTS & ANALYTICS */}
      {rightSidebarOpen && (
        <aside className={`fixed right-[calc(24px+64px+12px)] top-20 bottom-lg z-40 bg-white/80 backdrop-blur-md border border-white/20 rounded-3xl shadow-2xl flex flex-col overflow-hidden transition-all animate-in slide-in-from-right-4 duration-300 ${rightTab === "summary" ? "w-[640px]" : rightTab === "tasks" ? "w-[340px]" : "w-80"}`}>
          {rightTab === "events" && <EventMitigationPanel />}

          {rightTab === "summary" && <SummaryDashboard />}

          {rightTab === "analytics" && (
            <div className="flex-1 flex flex-col h-full overflow-hidden bg-white/50">
              {/* Header */}
              <div className="p-6 border-b border-outline-variant flex items-center justify-between flex-shrink-0">
                <div className="flex items-center gap-2">
                  <span className="material-symbols-outlined text-primary text-[20px]">bar_chart</span>
                  <h2 className="text-[14px] font-bold uppercase tracking-tight text-on-surface">Analytics & Planning</h2>
                </div>
                <button
                  onClick={() => setRightSidebarOpen(false)}
                  className="text-on-surface-variant/60 hover:text-on-surface transition-colors flex items-center justify-center p-1 rounded-full hover:bg-slate-100"
                  title="Tutup Panel"
                >
                  <span className="material-symbols-outlined text-[20px]">close</span>
                </button>
              </div>

              {/* Scrollable Content */}
              <div className="flex-1 overflow-y-auto p-4 space-y-4">
                {/* 1. Executive Summary */}
                <div className="bg-white border border-outline-variant rounded-2xl shadow-sm overflow-hidden">
                  <ExecutiveSummaryPanel />
                </div>

                {/* 2. Heatmap Controls */}
                <div className="bg-white border border-outline-variant rounded-2xl shadow-sm p-4">
                  <HeatmapControls
                    filters={heatmapFilters}
                    onFiltersChange={setHeatmapFilters}
                    visible={showHeatmap}
                    onVisibilityToggle={() => setShowHeatmap(!showHeatmap)}
                  />
                </div>

                {/* 3. Risk Profiling Layer */}
                <div className="bg-white border border-outline-variant rounded-2xl shadow-sm p-4">
                  <div className="flex justify-between items-center mb-2">
                    <span className="flex items-center gap-1.5 text-primary text-[12px] font-bold">
                      <span className="material-symbols-outlined text-[16px]">shield</span>
                      Risk Profiling Layer
                    </span>
                    <button
                      onClick={() => setShowRiskZones(!showRiskZones)}
                      className={`px-2.5 py-1 text-[11px] font-bold rounded-lg border transition-colors ${showRiskZones ? "bg-primary/10 border-primary text-primary" : "bg-white border-slate-200 text-slate-500 hover:bg-slate-50"}`}
                    >
                      {showRiskZones ? "Aktif" : "Non-aktif"}
                    </button>
                  </div>
                  <p className="text-[10px] text-slate-500 leading-relaxed font-medium">
                    Menampilkan tingkat risiko rawan pelanggaran secara berkala berdasarkan kalkulasi data historis 30 hari.
                  </p>
                </div>

                {/* 4. Placement Simulator */}
                <div className="bg-white border border-outline-variant rounded-2xl shadow-sm p-4">
                  <div className="flex justify-between items-center mb-3">
                    <span className="flex items-center gap-1.5 text-secondary text-[12px] font-bold">
                      <span className="material-symbols-outlined text-[16px]">route</span>
                      Placement Simulator
                    </span>
                    <button
                      onClick={() => setShowPlacements(!showPlacements)}
                      className={`px-2.5 py-1 text-[11px] font-bold rounded-lg border transition-colors ${showPlacements ? "bg-secondary/10 border-secondary text-secondary" : "bg-white border-slate-200 text-slate-500 hover:bg-slate-50"}`}
                    >
                      {showPlacements ? "Aktif" : "Non-aktif"}
                    </button>
                  </div>
                  <div className="flex flex-col gap-2">
                    <label className="text-[10px] text-slate-500 font-semibold">Tipe Penempatan:</label>
                    <div className="flex gap-2">
                      <button
                        onClick={() => setPlacementType("camera_etle")}
                        className={`flex-1 py-1.5 text-[11px] font-bold rounded-lg border transition-all flex items-center justify-center gap-1.5 ${placementType === "camera_etle" ? "bg-secondary/10 border-secondary text-secondary" : "bg-white border-slate-200 text-slate-500 hover:bg-slate-50"}`}
                      >
                        <span className="material-symbols-outlined text-[15px]">photo_camera</span>
                        Kamera E-TLE
                      </button>
                      <button
                        onClick={() => setPlacementType("officer")}
                        className={`flex-1 py-1.5 text-[11px] font-bold rounded-lg border transition-all flex items-center justify-center gap-1.5 ${placementType === "officer" ? "bg-primary-fixed/20 border-primary-fixed text-primary" : "bg-white border-slate-200 text-slate-500 hover:bg-slate-50"}`}
                      >
                        <span className="material-symbols-outlined text-[15px]">groups</span>
                        Petugas Lapangan
                      </button>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          )}

          {rightTab === "notifications" && (
            <NotificationHistoryPanel
              notifications={notificationHistory}
              onIncidentClick={(item) => {
                if (item.id.startsWith("EVT-")) {
                  setSelectedViolationEvent(item.id);
                } else {
                  setSelectedIncident(item);
                }
              }}
            />
          )}

          {rightTab === "activities" && (
            <ActivityPanel
              activities={activities}
              onIncidentClick={(incidentId) => {
                const found = incidentsWithSnapshots.find((item: Incident) => item.id === incidentId);
                if (found) {
                  setSelectedIncident(found);
                } else {
                  const liveIncident = liveViolationIncidents.find((item) => item.id === incidentId);
                  if (liveIncident) {
                    setSelectedIncident(liveIncident);
                    return;
                  }
                  alert("Detail insiden tidak ditemukan");
                }
              }}
              onClose={() => setRightSidebarOpen(false)}
            />
          )}

          {rightTab === "tasks" && (
            <MitigationTasksPanel
              tasks={tasks}
              setTasks={setTasks}
              teams={teams}
              setTeams={setTeams}
              onClose={() => setRightSidebarOpen(false)}
              onActivityLog={handlePanelActivityLog}
            />
          )}

          {rightTab === "upload" && <VideoUploadPanel />}

          {rightTab === "livecam" && (
            <LiveCamPanel
              onViolationDetected={handleRuntimeViolationDetected}
            />
          )}
        </aside>
      )}

      {/* BOTTOM TOOLBAR */}
      <nav className="fixed bottom-lg left-1/2 -translate-x-1/2 z-50 flex items-center p-1.5 gap-1.5 bg-white/90 backdrop-blur-md border border-outline-variant rounded-full shadow-2xl">
        <span className="text-[10px] font-bold uppercase tracking-wider text-on-surface-variant/60 pl-4 pr-2 border-r border-outline-variant select-none">
          Layer Filter
        </span>

        {/* Toggle CCTV Cameras */}
        <button
          onClick={() => setShowCameras(!showCameras)}
          className={`flex items-center gap-2 px-4 py-2 rounded-full transition-all ${
            showCameras
              ? "bg-primary/10 text-primary border border-primary/20 font-bold"
              : "text-on-surface-variant/70 hover:text-on-surface hover:bg-slate-100 border border-transparent"
          }`}
          title="Tampilkan / Sembunyikan CCTV"
        >
          <span className="material-symbols-outlined text-[18px]">videocam</span>
          <span className="text-[11px] uppercase tracking-wider">CCTV</span>
        </button>

        {/* Toggle Active Incidents */}
        <button
          onClick={() => setShowIncidents(!showIncidents)}
          className={`flex items-center gap-2 px-4 py-2 rounded-full transition-all ${
            showIncidents
              ? "bg-primary/10 text-primary border border-primary/20 font-bold"
              : "text-on-surface-variant/70 hover:text-on-surface hover:bg-slate-100 border border-transparent"
          }`}
          title="Tampilkan / Sembunyikan Insiden"
        >
          <span className="material-symbols-outlined text-[18px]">warning</span>
          <span className="text-[11px] uppercase tracking-wider">Incidents</span>
        </button>

        {/* Toggle Risk profiling */}
        <button
          onClick={() => setShowRiskZones(!showRiskZones)}
          className={`flex items-center gap-2 px-4 py-2 rounded-full transition-all ${
            showRiskZones
              ? "bg-primary/10 text-primary border border-primary/20 font-bold"
              : "text-on-surface-variant/70 hover:text-on-surface hover:bg-slate-100 border border-transparent"
          }`}
          title="Tampilkan / Sembunyikan Risk Zones Heatmap"
        >
          <span className="material-symbols-outlined text-[18px]">shield</span>
          <span className="text-[11px] uppercase tracking-wider">Risk Zones</span>
        </button>

        {/* Toggle Placement Simulator */}
        <button
          onClick={() => setShowPlacements(!showPlacements)}
          className={`flex items-center gap-2 px-4 py-2 rounded-full transition-all ${
            showPlacements
              ? "bg-primary/10 text-primary border border-primary/20 font-bold"
              : "text-on-surface-variant/70 hover:text-on-surface hover:bg-slate-100 border border-transparent"
          }`}
          title="Tampilkan / Sembunyikan Simulator Penempatan"
        >
          <span className="material-symbols-outlined text-[18px]">timeline</span>
          <span className="text-[11px] uppercase tracking-wider">Placements</span>
        </button>

        {/* Toggle Patrol Simulation */}
        <button
          onClick={() => setShowPatrol(!showPatrol)}
          className={`flex items-center gap-2 px-4 py-2 rounded-full transition-all ${
            showPatrol
              ? "bg-primary-fixed/20 text-primary border border-primary-fixed/40 font-bold"
              : "text-on-surface-variant/70 hover:text-on-surface hover:bg-slate-100 border border-transparent"
          }`}
          title="Tampilkan / Sembunyikan Simulasi Patroli Dashcam"
        >
          <span className="material-symbols-outlined text-[18px]">directions_bus</span>
          <span className="text-[11px] uppercase tracking-wider">Patrol</span>
        </button>
      </nav>

      {/* Modal CCTV — muncul saat kamera diklik */}
      {selectedCamera && (
        <CCTVModal
          camera={selectedCamera}
          onClose={() => setSelectedCamera(null)}
        />
      )}

      {/* Modal Detail Insiden — muncul saat insiden diklik */}
      {selectedIncident && (
        <IncidentDetailModal
          incident={selectedIncident}
          cameras={cameras}
          onClose={() => setSelectedIncident(null)}
        />
      )}

      {/* Modal Detail Pelanggaran — muncul saat violation event diklik */}
      {selectedViolationEvent && (
        <EventDetailModal
          eventId={selectedViolationEvent}
          onClose={() => setSelectedViolationEvent(null)}
          onStatusChange={(id, status) => {
            setNotificationHistory((prev) =>
              prev.map((item) =>
                item.id === id ? { ...item, status: status === "approved" ? "resolved" : "closed" } : item
              )
            );
          }}
        />
      )}
      {/* Modal Video Patroli Dashcam */}
      <PatrolVideoModal
        patrol={selectedPatrol}
        onClose={() => setSelectedPatrol(null)}
        onViolationDetected={handleRuntimeViolationDetected}
      />


    </div>
  );
}
