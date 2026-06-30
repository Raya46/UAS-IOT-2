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

export interface Incident {
  id: string;
  camera_id: string;
  type:
    | "illegal_parking"
    | "busway_violation"
    | "congestion"
    | "wrong_way"
    | "hazard_lights"
    | "red_light_violation"
    | "illegal_u_turn"
    | "unsafe_lane_change"
    | "shoulder_violation";
  lat: number;
  lng: number;
  severity: "low" | "medium" | "high";
  confidence_score: number;        // 0.0–1.0
  source_count: number;
  status: "detected" | "confirmed" | "dispatched" | "resolved" | "closed";
  timestamp: string;
  snapshot_url?: string;
  snapshot_size?: [number, number];
  assigned_officer?: string;
  resolution_notes?: string;
  description?: string;
  vehicle_type?: string;
  plate_number?: string;
  plate_crop?: string;
  plate_bbox?: [number, number, number, number];
  plate_confidence?: number;
  plate_note?: string;
  video_time_seconds?: number;
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

export interface EventPrediction {
  event_id: string;
  event_name: string;
  impact_level?: "medium" | "high" | "critical";
  crowd_zone?: "green" | "yellow" | "orange" | "red";
  estimated_crowd?: number;
  officer_min?: number;
  officer_max?: number;
  impact_radius_km?: number;
  impact_start: string;
  impact_end: string;
  affected_segments: Array<{
    name?: string;
    segment_id?: string;
    lat?: number;
    lng?: number;
    congestion_level: "medium" | "high" | "critical";
    coordinates?: [number, number][];
    color: string;
    distance_km?: number;
  }>;
  mitigation_actions: Array<{
    action: string;
    location?: { lat: number; lng: number };
    priority: number;
  }>;
}

export type WSMessageType =
  | { type: "violation"; payload: Violation }
  | { type: "incident"; payload: Incident }
  | { type: "incident_update"; payload: { incident_id: string; source_count: number; confidence_score: number } }
  | { type: "congestion"; payload: CongestionUpdate }
  | { type: "alert"; payload: AlertPayload }
  | { type: "event_prediction"; payload: EventPrediction }
  | { type: "ping" };

export interface WSMessage {
  type: "violation" | "incident" | "incident_update" | "congestion" | "alert" | "event_prediction" | "ping" | "incident_status_change";
  payload?: any;
}

export interface Event {
  id: string;
  name: string;
  venue: string;
  lat: number;
  lng: number;
  date: string;
  time: string;
  end_date?: string;
  estimated_crowd: number;
  impact_radius_km: number;
  source?: string;
  source_url?: string;
  category?: string;
  crowd_zone?: "green" | "yellow" | "orange" | "red";
  officer_min?: number;
  officer_max?: number;
  crowd_confidence?: number;
  crowd_reason?: string;
  estimation_source?: string;
}

export interface Mitigation {
  event_id: string;
  event_name: string;
  impact_level: string;
  crowd_zone?: "green" | "yellow" | "orange" | "red";
  zone_color?: string;
  estimated_crowd?: number;
  officer_min?: number;
  officer_max?: number;
  crowd_confidence?: number;
  crowd_reason?: string;
  affected_radius_km: number;
  recommendations: string[];
  predicted_congestion_start: string;
  predicted_congestion_end: string;
}
