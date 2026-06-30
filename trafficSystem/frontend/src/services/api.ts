import axios from "axios";
import type { Camera, Zone, Event, Incident, Mitigation } from "../types";

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || "",
});

export const getCameras = (): Promise<Camera[]> =>
  api.get("/api/cameras/").then((r) => r.data);

export const getZones = (): Promise<Zone[]> =>
  api.get("/api/zones/").then((r) => r.data);

export const getEvents = (): Promise<Event[]> =>
  api.get("/api/events/").then((r) => r.data);

export const getEventMitigation = (eventId: string): Promise<Mitigation> =>
  api.get(`/api/events/${eventId}/mitigation`).then((r) => r.data);

export const refreshExternalEvents = (): Promise<{ success: boolean; stored: number; errors?: string[] }> =>
  api.post("/api/events/refresh-external").then((r) => r.data);

export const getTrafficCounts = (): Promise<any> =>
  api.get("/api/traffic-counts").then((r) => r.data);

export const getTrafficMetrics = (): Promise<any> =>
  api.get("/api/traffic-metrics").then((r) => r.data);

export const getParkingStatus = (): Promise<any> =>
  api.get("/api/parking-status").then((r) => r.data);

export const getSignDetections = (): Promise<any[]> =>
  api.get("/api/sign-detections").then((r) => r.data);

export const getViolationEvents = (): Promise<any[]> =>
  api.get("/api/violation-events/?limit=100").then((r) => r.data);

export type IncidentCreatePayload = Omit<Incident, "id"> & {
  id?: string;
  camera_name?: string;
  broadcast?: boolean;
};

export const createIncident = (payload: IncidentCreatePayload): Promise<Incident> =>
  api.post("/api/incidents/", payload).then((r) => r.data);

export const getFilteredViolations = (filters?: {
  violation_type?: string;
  review_status?: string;
  plate_number?: string;
  source?: string;
  limit?: number;
  offset?: number;
}): Promise<any[]> => {
  const params = new URLSearchParams();
  if (filters?.violation_type) params.set("violation_type", filters.violation_type);
  if (filters?.review_status) params.set("review_status", filters.review_status);
  if (filters?.plate_number) params.set("plate_number", filters.plate_number);
  if (filters?.source) params.set("source", filters.source);
  if (filters?.limit) params.set("limit", String(filters.limit));
  if (filters?.offset) params.set("offset", String(filters.offset));
  return api.get(`/api/violation-events/?${params.toString()}`).then((r) => r.data);
};

export const updateViolationStatus = (eventId: string, status: "approved" | "rejected"): Promise<any> =>
  api.patch(`/api/violation-events/${eventId}/status`, { review_status: status }).then((r) => r.data);

export const getViolationDetail = (eventId: string): Promise<any> =>
  api.get(`/api/violation-events/${eventId}`).then((r) => r.data);

export const getEvidenceUrl = (path: string | null): string => {
  if (!path) return "";
  const basename = path.split(/[\\/]/).pop() || path;
  return `${import.meta.env.VITE_API_BASE_URL}/api/violation-events/evidence/${basename}`;
};

export const uploadVideo = (file: File): Promise<{ job_id: string }> => {
  const form = new FormData();
  form.append("file", file);
  return api.post("/api/upload-video/", form).then((r) => r.data);
};

export const getUploadStatus = (jobId: string): Promise<{
  status: string;
  synced_count: number;
  error?: string;
}> => api.get(`/api/upload-video/status/${jobId}`).then((r) => r.data);

export interface DashcamSourceApi {
  id: string;
  name: string;
  route: string;
  description: string;
  color: string;
  video_file: string;
  video_url: string;
  status: "active" | "standby" | "unavailable";
}

export const getDashcamSources = (): Promise<DashcamSourceApi[]> =>
  api.get("/api/dashcam/sources").then((r) => r.data);

export const getDashcamVideoUrl = (videoUrl: string): string =>
  `${import.meta.env.VITE_API_BASE_URL || ""}${videoUrl}`;

export const getCctvCameras = (): Promise<{ name: string; url: string; type: string }[]> =>
  api.get("/api/cctv/cameras").then((r) => r.data.cameras);

export const resolveCctvStream = (embedUrl: string): Promise<{ resolved_url: string }> =>
  api.get("/api/cctv/resolve-stream", { params: { url: embedUrl } }).then((r) => r.data);

export const getWebSocketUrl = (): string => {
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  const host = window.location.host;
  const wsPath = import.meta.env.VITE_WS_URL || `${protocol}//${host}/ws`;
  return `${wsPath}/livecam`;
};
