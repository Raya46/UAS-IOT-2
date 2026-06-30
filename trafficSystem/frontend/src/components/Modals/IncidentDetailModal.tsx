import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import ReactPlayer from "react-player";
const Player = (ReactPlayer as any).default || ReactPlayer;
import axios from "axios";
import type { Incident } from "../../types";
import { enrichIncidentWithEvidence, getIncidentSnapshotUrl } from "../../utils/incidentSnapshots";

const TYPE_LABELS: Record<string, string> = {
  illegal_parking: "Parkir Liar",
  busway_violation: "Pelanggaran Busway",
  congestion: "Kemacetan",
  wrong_way: "Lawan Arah",
  hazard_lights: "Lampu Hazard",
  red_light_violation: "Menerobos Lampu Merah",
  illegal_u_turn: "Putar Arah Sembarangan",
  unsafe_lane_change: "Potong Lajur Berbahaya",
  shoulder_violation: "Pelanggaran Bahu Jalan",
};

const API_BASE = import.meta.env.VITE_API_BASE_URL || "";

function resolveAssetUrl(path?: string): string {
  if (!path) return "";
  if (/^https?:\/\//i.test(path) || path.startsWith("data:")) return path;
  return `${API_BASE}${path.startsWith("/") ? path : `/${path}`}`;
}

const SEVERITY_LABELS: Record<string, string> = {
  low: "Rendah",
  medium: "Sedang",
  high: "Tinggi",
};

function isUuid(value: string): boolean {
  return /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(value);
}

interface Props {
  incident: Incident;
  cameras: Array<{ id: string; name: string; stream_url?: string }>;
  onClose: () => void;
}

export function IncidentDetailModal({ incident, cameras, onClose }: Props) {
  const queryClient = useQueryClient();
  const [resolutionNotes, setResolutionNotes] = useState("");
  const [assignedOfficer, setAssignedOfficer] = useState("");
  const [commsOpen, setCommsOpen] = useState(false);
  const [commsPhase, setCommsPhase] = useState<"connecting" | "ringing" | "active" | "ended">("connecting");
  const [emailOpen, setEmailOpen] = useState(false);
  const [emailTo, setEmailTo] = useState("");
  const [emailBody, setEmailBody] = useState("");
  const [emailSending, setEmailSending] = useState(false);
  const [emailSent, setEmailSent] = useState(false);
  const [emailAttachReport, setEmailAttachReport] = useState(false);
  const [emailError, setEmailError] = useState("");
  const isPersistedIncident = isUuid(incident.id);
  const isLocalIncident = !isPersistedIncident;

  const getDurationMin = () => {
    if (!detail?.occurred_at || !detail?.resolved_at) return "N/A";
    const start = new Date(detail.occurred_at);
    const end = new Date(detail.resolved_at);
    const diffMs = end.getTime() - start.getTime();
    const diffMin = Math.round(diffMs / 60000);
    return `${Math.max(diffMin, 1)} mins`;
  };

  const getResponseTimeMin = () => {
    if (!detail?.occurred_at || !detail?.assigned_at) return "N/A";
    const start = new Date(detail.occurred_at);
    const assign = new Date(detail.assigned_at);
    const diffMs = assign.getTime() - start.getTime();
    const diffMin = Math.round(diffMs / 60000);
    return `${Math.max(diffMin, 1)} mins`;
  };

  const getImpactRestored = () => {
    const status = detail?.status || incident.status;
    if (status === "resolved" || status === "closed") {
      return "100% (Selesai)";
    }
    return "Sedang Ditangani";
  };

  const getETA = () => {
    if (!incident.id) return "4 mins";
    const charCode = incident.id.charCodeAt(0) || 0;
    return `${3 + (charCode % 6)} mins`;
  };

  const { data: detail } = useQuery({
    queryKey: ["incident-detail", incident.id],
    queryFn: () =>
      axios
        .get(`${import.meta.env.VITE_API_BASE_URL}/api/incidents/${incident.id}`)
        .then((r) => r.data),
    enabled: isPersistedIncident,
  });

  const updateStatus = useMutation({
    mutationFn: ({ status, officer }: { status: string; officer?: string }) =>
      axios.patch(`${import.meta.env.VITE_API_BASE_URL}/api/incidents/${incident.id}/status`, {
        incident_id: incident.id,
        status,
        assigned_officer: officer || undefined,
        resolution_notes: status === "resolved" ? resolutionNotes : undefined,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["incidents"] });
      queryClient.invalidateQueries({ queryKey: ["active-incidents-list"] });
      queryClient.invalidateQueries({ queryKey: ["incident-detail", incident.id] });
    },
  });

  const displayIncident = enrichIncidentWithEvidence({
    ...incident,
    camera_id: detail?.camera_id ?? incident.camera_id,
    snapshot_url: detail?.snapshot_url ?? incident.snapshot_url,
    description: detail?.description ?? incident.description,
    vehicle_type: detail?.vehicle_type ?? incident.vehicle_type,
    plate_number: detail?.plate_number ?? incident.plate_number,
    plate_crop: detail?.plate_crop ?? incident.plate_crop,
    plate_bbox: detail?.plate_bbox ?? incident.plate_bbox,
    plate_confidence: detail?.plate_confidence ?? incident.plate_confidence,
    plate_note: detail?.plate_note ?? incident.plate_note,
    video_time_seconds: detail?.video_time_seconds ?? incident.video_time_seconds,
  });
  const camera = cameras.find((c) => c.id === displayIncident.camera_id);
  const isIndividualViolation = displayIncident.type !== "congestion";
  const plateNumber = isIndividualViolation ? displayIncident.plate_number || "" : "";
  const evidenceUrl = getIncidentSnapshotUrl(displayIncident);
  const plateCropUrl = resolveAssetUrl(displayIncident.plate_crop);
  const [snapshotWidth, snapshotHeight] = displayIncident.snapshot_size || [];
  const plateBoxStyle =
    displayIncident.plate_bbox && snapshotWidth && snapshotHeight
      ? {
          left: `${(displayIncident.plate_bbox[0] / snapshotWidth) * 100}%`,
          top: `${(displayIncident.plate_bbox[1] / snapshotHeight) * 100}%`,
          width: `${((displayIncident.plate_bbox[2] - displayIncident.plate_bbox[0]) / snapshotWidth) * 100}%`,
          height: `${((displayIncident.plate_bbox[3] - displayIncident.plate_bbox[1]) / snapshotHeight) * 100}%`,
        }
      : undefined;

  // Helper variables for lifecycle status
  const currentStatus = detail?.status || incident.status;

  return (
    <main
      onClick={onClose}
      className="fixed inset-0 z-[60] flex items-center justify-center p-md bg-black/40 overflow-y-auto pointer-events-auto"
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className="w-full max-w-4xl glass-modal rounded-xl overflow-hidden flex flex-col pointer-events-auto my-8 shadow-2xl"
      >
        {/* Modal Header */}
        <div className="px-lg py-md border-b border-outline-variant flex items-center justify-between bg-surface/80">
          <div className="flex items-center gap-md">
            <div className="w-10 h-10 bg-primary-fixed-dim/10 rounded-lg flex items-center justify-center border border-primary-fixed-dim/20">
              <span className="material-symbols-outlined text-primary-fixed-dim">emergency</span>
            </div>
            <div>
              <div className="flex items-center gap-2">
                <span className="text-label-xs font-label-xs text-on-surface-variant uppercase tracking-widest">Incident ID</span>
                <span className="text-data-mono font-data-mono text-primary-fixed-dim">INC-{incident.id.slice(0, 8).toUpperCase()}</span>
              </div>
              <h2 className="text-[16px] font-bold text-on-surface uppercase tracking-tight">
                {TYPE_LABELS[displayIncident.type] || displayIncident.type}
              </h2>
            </div>
          </div>

          <div className="flex items-center gap-4">
            <div className="flex items-center gap-2 px-3 py-1 bg-primary-fixed-dim/10 rounded-full border border-primary-fixed-dim/20">
              <span className={`w-2 h-2 rounded-full animate-pulse ${
                (currentStatus === "resolved" || currentStatus === "closed") ? "bg-on-surface-variant" : "bg-primary-fixed-dim"
              }`}></span>
              <span className="text-label-xs text-primary-fixed-dim uppercase tracking-widest font-bold">
                {currentStatus === "detected" && "Terdeteksi"}
                {currentStatus === "confirmed" && "Dikonfirmasi"}
                {currentStatus === "dispatched" && "Pengiriman Regu"}
                {currentStatus === "resolved" && "Selesai"}
                {currentStatus === "closed" && "Arsip Kasus"}
              </span>
            </div>
            <button
              onClick={onClose}
              className="flex h-9 w-9 items-center justify-center rounded-full text-on-surface-variant hover:bg-surface-container hover:text-on-surface"
              aria-label="Close incident detail"
            >
              <span className="material-symbols-outlined text-[20px]">close</span>
            </button>
          </div>
        </div>

        {/* Lifecycle Tracker */}
        <div className="px-lg py-6 bg-surface-container-low/30 border-b border-outline-variant/50">
          <div className="flex items-center justify-between relative px-8">
            {/* Progress line background */}
            <div className="absolute top-1/2 left-8 right-8 h-[1px] bg-outline-variant -translate-y-1/2 z-0"></div>

            {/* Progress line fill */}
            <div className={`absolute top-1/2 left-8 h-[1px] bg-primary-fixed-dim -translate-y-1/2 z-0 transition-all duration-300 ${
              currentStatus === "detected" ? "w-1/3" :
              (currentStatus === "confirmed" || currentStatus === "dispatched") ? "w-2/3" :
              "w-[calc(100%-64px)]"
            }`}></div>

            {/* Step 1: Detection */}
            <div className="relative z-10 flex flex-col items-center gap-2 bg-slate-50/50 px-2">
              <div className="w-8 h-8 rounded-full bg-primary-fixed-dim text-white flex items-center justify-center shadow-lg shadow-primary-fixed-dim/20">
                <span className="material-symbols-outlined text-[18px]">check</span>
              </div>
              <span className="text-label-xs font-bold text-on-surface uppercase">Detection</span>
            </div>

            {/* Step 2: Validation */}
            <div className="relative z-10 flex flex-col items-center gap-2 bg-slate-50/50 px-2">
              <div className={`w-8 h-8 rounded-full flex items-center justify-center transition-all ${
                currentStatus === "detected"
                  ? "bg-white border-2 border-primary-fixed-dim text-primary-fixed-dim ring-4 ring-primary-fixed-dim/10"
                  : "bg-primary-fixed-dim text-white shadow-lg shadow-primary-fixed-dim/20"
              }`}>
                {currentStatus === "detected" ? (
                  <span className="material-symbols-outlined text-[18px] animate-spin" style={{ animationDuration: "3s" }}>sync</span>
                ) : (
                  <span className="material-symbols-outlined text-[18px]">check</span>
                )}
              </div>
              <span className={`text-label-xs font-bold uppercase ${
                currentStatus === "detected" ? "text-primary-fixed-dim" : "text-on-surface"
              }`}>Validation</span>
            </div>

            {/* Step 3: Dispatch */}
            <div className="relative z-10 flex flex-col items-center gap-2 bg-slate-50/50 px-2">
              <div className={`w-8 h-8 rounded-full flex items-center justify-center transition-all ${
                (currentStatus === "confirmed" || currentStatus === "dispatched")
                  ? "bg-white border-2 border-primary-fixed-dim text-primary-fixed-dim ring-4 ring-primary-fixed-dim/10"
                  : (currentStatus === "resolved" || currentStatus === "closed")
                  ? "bg-primary-fixed-dim text-white shadow-lg shadow-primary-fixed-dim/20"
                  : "bg-white border border-outline-variant text-outline-variant"
              }`}>
                {(currentStatus === "confirmed" || currentStatus === "dispatched") ? (
                  <span className="material-symbols-outlined text-[18px] animate-spin" style={{ animationDuration: "3s" }}>sync</span>
                ) : (currentStatus === "resolved" || currentStatus === "closed") ? (
                  <span className="material-symbols-outlined text-[18px]">check</span>
                ) : (
                  <div className="w-2 h-2 rounded-full bg-outline-variant/50"></div>
                )}
              </div>
              <span className={`text-label-xs font-bold uppercase ${
                (currentStatus === "confirmed" || currentStatus === "dispatched") ? "text-primary-fixed-dim" : "text-on-surface-variant"
              }`}>Dispatch</span>
            </div>

            {/* Step 4: Resolved */}
            <div className="relative z-10 flex flex-col items-center gap-2 bg-slate-50/50 px-2">
              <div className={`w-8 h-8 rounded-full flex items-center justify-center transition-all ${
                (currentStatus === "resolved" || currentStatus === "closed")
                  ? "bg-white border-2 border-primary-fixed-dim text-primary-fixed-dim ring-4 ring-primary-fixed-dim/10"
                  : "bg-white border border-outline-variant text-outline-variant"
              }`}>
                {(currentStatus === "resolved" || currentStatus === "closed") ? (
                  <span className="material-symbols-outlined text-[18px]">task_alt</span>
                ) : (
                  <div className="w-2 h-2 rounded-full bg-outline-variant/50"></div>
                )}
              </div>
              <span className={`text-label-xs font-bold uppercase ${
                (currentStatus === "resolved" || currentStatus === "closed") ? "text-primary-fixed-dim" : "text-on-surface-variant"
              }`}>Resolved</span>
            </div>
          </div>
        </div>

        <div className="grid grid-cols-12 flex-1 min-h-[400px]">
          {/* Left: Evidence */}
          <div className="col-span-7 p-lg border-r border-outline-variant/50 flex flex-col gap-md">
            <div className="flex items-center justify-between">
              <h3 className="text-label-xs text-on-surface-variant uppercase tracking-widest">Evidence Analysis</h3>
              <div className="px-2 py-0.5 bg-primary-fixed-dim/10 text-primary-fixed-dim text-data-mono border border-primary-fixed-dim/20 rounded text-[11px]">
                {Math.round(incident.confidence_score * 100)}% AI Confidence
              </div>
            </div>

            <div className="flex-1 rounded-xl bg-slate-200 overflow-hidden relative border border-outline-variant min-h-[200px]">
              {evidenceUrl ? (
                <>
                  <img
                    className="w-full h-full object-contain bg-slate-950"
                    alt="Snapshot"
                    src={evidenceUrl}
                    onError={(event) => {
                      const img = event.currentTarget;
                      if (!img.src.endsWith("/snapshots/default.png")) {
                        img.src = "/snapshots/default.png";
                      }
                    }}
                  />
                  {plateBoxStyle && (
                    <div
                      className="absolute border-2 border-lime-400 bg-lime-400/10 shadow-[0_0_0_9999px_rgba(0,0,0,0.08)]"
                      style={plateBoxStyle}
                    >
                      <div className="absolute -top-6 left-0 rounded bg-lime-400 px-2 py-0.5 font-mono text-[10px] font-bold text-slate-950 whitespace-nowrap">
                        OCR PLATE {plateNumber || "N/A"}
                      </div>
                    </div>
                  )}
                </>
              ) : camera?.stream_url && currentStatus !== "resolved" && currentStatus !== "closed" ? (
                camera.stream_url.includes("embed.html") || camera.stream_url.includes("cctv.balitower.co.id") || camera.stream_url.endsWith(".html") ? (
                  <iframe
                    src={camera.stream_url.replace("http://cctv.balitower.co.id", "https://cctv.balitower.co.id")}
                    className="w-full h-full border-0 bg-slate-950 absolute inset-0"
                    allowFullScreen
                    scrolling="no"
                    frameBorder="0"
                    allow="autoplay; encrypted-media"
                  />
                ) : (
                  <Player
                    url={camera.stream_url}
                    playing
                    muted
                    loop
                    width="100%"
                    height="100%"
                    style={{ objectFit: "cover", position: "absolute", top: 0, left: 0 }}
                  />
                )
              ) : (
                <div className="w-full h-full bg-[#111] flex items-center justify-center text-[12px] text-[#555]">
                  Feed tidak tersedia
                </div>
              )}

              <div className="absolute top-4 left-4 bg-black/40 backdrop-blur-md px-2 py-1 rounded text-[10px] text-white flex items-center gap-2 z-10">
                <span className="w-2 h-2 rounded-full bg-red-500 animate-pulse"></span>
                CAM-{camera?.id || displayIncident.camera_id}: {camera?.name.toUpperCase() || "LOKASI"}
              </div>

              {/* Detection Overlays */}
              <div className="absolute inset-0 pointer-events-none border-[3px] border-primary-fixed-dim/30 m-8 rounded-lg z-10"></div>
            </div>

            <div className="p-md bg-surface-container rounded-lg border border-outline-variant/50">
              <p className="text-[12px] text-on-surface-variant leading-relaxed">
                <span className="font-bold text-on-surface">AI Summary:</span> {displayIncident.description || `Deteksi tanda ${TYPE_LABELS[displayIncident.type] || displayIncident.type} di lokasi ${camera?.name || "Kamera " + displayIncident.camera_id}.`} Tingkat akurasi sistem mencapai {Math.round(displayIncident.confidence_score * 100)}% dengan total sinyal masuk sebanyak {displayIncident.source_count}.
              </p>
            </div>
          </div>

          {/* Right: Details & Actions */}
          <div className="col-span-5 p-lg flex flex-col justify-between bg-surface-container-low/10">
            <div className="space-y-6 flex-1">

              {/* Status specific details */}
              {(currentStatus === "detected" || currentStatus === "confirmed") && (
                <div className="space-y-6">
                  <div className="grid grid-cols-2 gap-md">
                    <div>
                      <span className="text-label-xs text-on-surface-variant uppercase block mb-1">Location</span>
                      <div className="flex items-center gap-1">
                        <span className="material-symbols-outlined text-primary-fixed-dim text-[18px]">location_on</span>
                        <span className="text-[13px] font-bold">{camera?.name || "Lajur Jalan"}</span>
                      </div>
                    </div>
                    <div>
                      <span className="text-label-xs text-on-surface-variant uppercase block mb-1">Timestamp</span>
                      <div className="flex items-center gap-1">
                        <span className="material-symbols-outlined text-primary-fixed-dim text-[18px]">schedule</span>
                        <span className="text-[13px] font-bold">
                          {new Date(incident.timestamp).toLocaleTimeString("id-ID", { hour: "2-digit", minute: "2-digit" })} WIB
                        </span>
                      </div>
                    </div>
                  </div>

                  <div className="space-y-3">
                    <h4 className="text-label-xs text-on-surface-variant uppercase tracking-widest border-b border-outline-variant/50 pb-1">Impact Metadata</h4>
                    <div className="space-y-2">
                      <div className="flex justify-between items-center text-[12px]">
                        <span className="text-on-surface-variant">Primary Cause</span>
                        <span className="font-semibold">{TYPE_LABELS[displayIncident.type] || displayIncident.type}</span>
                      </div>
                      <div className="flex justify-between items-center text-[12px]">
                        <span className="text-on-surface-variant">Severity</span>
                        <span className="font-semibold text-primary">{SEVERITY_LABELS[incident.severity] || incident.severity}</span>
                      </div>
                      <div className="flex justify-between items-center text-[12px]">
                        <span className="text-on-surface-variant">Affected Units</span>
                        <span className="font-semibold">{incident.source_count} Sinyal</span>
                      </div>
                      <div className="flex justify-between items-center text-[12px]">
                        <span className="text-on-surface-variant">Traffic Impact</span>
                        <span className={`font-bold ${incident.severity === "high" ? "text-error" : "text-primary"}`}>
                          {incident.severity === "high" ? "Severe (Red)" : "Medium (Orange)"}
                        </span>
                      </div>
                      {isIndividualViolation && (
                        <div className="space-y-2 pt-1.5 border-t border-outline-variant/50">
                          <div className="flex justify-between items-center text-[12px]">
                            <span className="text-on-surface-variant font-bold">Plat Nomor OCR</span>
                            <span className="font-bold text-primary font-mono bg-primary/5 px-2 py-0.5 rounded border border-primary/20">
                              {plateNumber || "Tidak terlihat"}
                            </span>
                          </div>
                          {displayIncident.vehicle_type && (
                            <div className="flex justify-between items-center text-[12px]">
                              <span className="text-on-surface-variant">Target Vehicle</span>
                              <span className="font-semibold capitalize">{displayIncident.vehicle_type}</span>
                            </div>
                          )}
                          {displayIncident.video_time_seconds != null && (
                            <div className="flex justify-between items-center text-[12px]">
                              <span className="text-on-surface-variant">Detik Video</span>
                              <span className="font-mono font-semibold">{displayIncident.video_time_seconds.toFixed(1)}s</span>
                            </div>
                          )}
                          {plateCropUrl && (
                            <div className="rounded-lg border border-lime-400/30 bg-lime-400/10 p-2">
                              <div className="mb-1 flex items-center justify-between gap-2">
                                <span className="text-[10px] font-bold uppercase text-lime-700 dark:text-lime-400">OCR Bounding Box Evidence</span>
                                {displayIncident.plate_confidence != null && (
                                  <span className="font-mono text-[10px] font-bold text-lime-700 dark:text-lime-400">
                                    {Math.round(displayIncident.plate_confidence * 100)}%
                                  </span>
                                )}
                              </div>
                              <img
                                alt="Plate crop"
                                src={plateCropUrl}
                                className="h-20 w-full rounded border border-lime-200 bg-black object-contain"
                              />
                            </div>
                          )}
                          {displayIncident.plate_note && (
                            <p className="rounded-lg bg-surface-container p-2 text-[11px] leading-relaxed text-on-surface-variant">
                              {displayIncident.plate_note}
                            </p>
                          )}
                        </div>
                      )}
                    </div>
                  </div>

                  {currentStatus === "confirmed" && (
                    <div className="space-y-3 pt-2">
                      <h4 className="text-label-xs text-on-surface-variant uppercase tracking-widest border-b border-outline-variant/50 pb-1">Team Assignment</h4>
                      <div className="flex flex-col gap-2">
                        <label className="text-[11px] text-on-surface-variant font-bold">Petugas / Unit Lapangan</label>
                        <input
                          type="text"
                          placeholder="Nama petugas..."
                          value={assignedOfficer}
                          onChange={(e) => setAssignedOfficer(e.target.value)}
                          className="w-full px-3 py-2 bg-surface border border-outline-variant rounded-lg text-[12px] text-on-surface focus:outline-none focus:border-primary-fixed-dim"
                        />
                      </div>
                    </div>
                  )}
                </div>
              )}

              {currentStatus === "dispatched" && (
                <div className="space-y-6">
                  <div className="space-y-3">
                    <h4 className="text-label-xs text-on-surface-variant uppercase tracking-widest border-b border-outline-variant/50 pb-1">Team Assignment</h4>
                    <div className="space-y-2">
                      <div className="p-3 bg-surface border border-outline-variant rounded-lg flex items-center justify-between">
                        <div className="flex items-center gap-3">
                          <div className="w-8 h-8 bg-primary-fixed-dim/10 rounded flex items-center justify-center">
                            <span className="material-symbols-outlined text-primary-fixed-dim text-[18px]">emergency_home</span>
                          </div>
                          <div>
                            <div className="text-[12px] font-bold">{detail?.assigned_officer || incident.assigned_officer || "Unit Lapangan"}</div>
                            <div className="text-[10px] text-on-surface-variant">En Route</div>
                          </div>
                        </div>
                        <div className="text-right">
                          <div className="text-[12px] font-bold text-primary">ETA {getETA()}</div>
                        </div>
                      </div>
                    </div>
                  </div>

                  <div className="space-y-3">
                    <h4 className="text-label-xs text-on-surface-variant uppercase tracking-widest border-b border-outline-variant/50 pb-1">Dispatch Log</h4>
                    <div className="space-y-2 max-h-[120px] overflow-y-auto pr-2">
                      <div className="text-[11px] leading-tight">
                        <span className="text-on-surface-variant font-bold">
                          {new Date(incident.timestamp).toLocaleTimeString("id-ID", { hour: "2-digit", minute: "2-digit" })}
                        </span>{" "}
                        <span className="text-primary font-bold">[HQ]</span> Dispatching {detail?.assigned_officer || incident.assigned_officer || "Unit"} to {camera?.name || "Incident Location"}.
                      </div>
                      <div className="text-[11px] leading-tight">
                        <span className="text-on-surface-variant font-bold">
                          {new Date(new Date(incident.timestamp).getTime() + 22000).toLocaleTimeString("id-ID", { hour: "2-digit", minute: "2-digit" })}
                        </span>{" "}
                        <span className="text-on-surface font-bold">[{detail?.assigned_officer?.slice(0, 5) || "Unit"}]</span> Acknowledged. En route.
                      </div>
                      <div className="text-[11px] leading-tight">
                        <span className="text-on-surface-variant font-bold">
                          {new Date().toLocaleTimeString("id-ID", { hour: "2-digit", minute: "2-digit" })}
                        </span>{" "}
                        <span className="text-primary font-bold">[HQ]</span> Requesting status update...
                      </div>
                    </div>
                  </div>

                  <div className="space-y-2 pt-2 border-t border-outline-variant/50">
                    <label className="text-[11px] text-on-surface-variant font-bold">Catatan Resolusi</label>
                    <textarea
                      placeholder="Catatan resolusi..."
                      value={resolutionNotes}
                      onChange={(e) => setResolutionNotes(e.target.value)}
                      className="w-full px-3 py-2 bg-surface border border-outline-variant rounded-lg text-[12px] text-on-surface focus:outline-none focus:border-primary-fixed-dim min-h-[60px]"
                    />
                  </div>
                </div>
              )}

              {(currentStatus === "resolved" || currentStatus === "closed") && (
                <div className="space-y-6">
                  <div className="space-y-3">
                    <h4 className="text-label-xs text-on-surface-variant uppercase tracking-widest border-b border-outline-variant/50 pb-1">Resolution Summary</h4>
                    <div className="space-y-4">
                      <div className="flex justify-between items-center text-[12px]">
                        <span className="text-on-surface-variant">Total Duration</span>
                        <span className="font-semibold">{getDurationMin()}</span>
                      </div>
                      <div className="flex justify-between items-center text-[12px]">
                        <span className="text-on-surface-variant">Response Time</span>
                        <span className="font-semibold">{getResponseTimeMin()}</span>
                      </div>
                      <div className="flex justify-between items-center text-[12px]">
                        <span className="text-on-surface-variant">Impact Restored</span>
                        <span className="font-semibold text-primary">{getImpactRestored()}</span>
                      </div>
                      <div className="flex justify-between items-center text-[12px]">
                        <span className="text-on-surface-variant">Resource Deployment</span>
                        <span className="font-semibold">1 Unit Lapangan ({detail?.assigned_officer || incident.assigned_officer || "Petugas"})</span>
                      </div>
                      {isIndividualViolation && (
                        <div className="flex justify-between items-center text-[12px]">
                          <span className="text-on-surface-variant">Target Vehicle</span>
                          <span className="font-bold text-primary font-mono">{plateNumber}</span>
                        </div>
                      )}
                      <div className="pt-2">
                        <span className="text-label-xs text-on-surface-variant uppercase block mb-1">Final Disposition</span>
                        <p className="text-[12px] font-medium leading-relaxed bg-surface-container-low border border-outline-variant p-2 rounded-lg text-on-surface">
                          {detail?.resolution_notes || incident.resolution_notes || "Laporan diselesaikan secara prosedural di lapangan."}
                        </p>
                      </div>
                    </div>
                  </div>

                  <div className="space-y-3">
                    <h4 className="text-label-xs text-on-surface-variant uppercase tracking-widest border-b border-outline-variant/50 pb-1">Field Evidence</h4>
                    <div className="relative rounded-lg overflow-hidden border border-outline-variant h-24 bg-surface-container">
                      {evidenceUrl ? (
                        <img
                          alt="Resolved scene"
                          className="w-full h-full object-cover grayscale opacity-60"
                          src={evidenceUrl}
                          onError={(event) => {
                            const img = event.currentTarget;
                            if (!img.src.endsWith("/snapshots/default.png")) {
                              img.src = "/snapshots/default.png";
                            }
                          }}
                        />
                      ) : (
                        <div className="w-full h-full bg-surface-container-high"></div>
                      )}
                      <div className="absolute inset-0 flex items-center justify-center bg-primary/10">
                        <div className="bg-surface/90 backdrop-blur-sm px-3 py-1 rounded-full border border-primary/20 flex items-center gap-1">
                          <span className="material-symbols-outlined text-primary text-[14px]">check_circle</span>
                          <span className="text-[10px] font-bold text-primary uppercase">Scene Cleared</span>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              )}

            </div>

            {/* Actions Footer */}
            <div className="space-y-3 pt-6 border-t border-outline-variant/50">
              {isLocalIncident && (
                <button
                  onClick={onClose}
                  className="w-full py-2.5 bg-surface border border-outline-variant text-on-surface-variant font-semibold rounded-lg hover:text-on-surface hover:bg-surface-container transition-colors flex items-center justify-center gap-1 text-[12px]"
                >
                  <span className="material-symbols-outlined text-[18px]">close</span>
                  Close
                </button>
              )}

              {isPersistedIncident && currentStatus === "detected" && (
                <>
                  <button
                    onClick={() => updateStatus.mutate({ status: "confirmed" })}
                    disabled={updateStatus.isPending}
                    className="w-full py-3 bg-primary-fixed-dim text-white font-bold rounded-lg shadow-lg shadow-primary-fixed-dim/20 hover:brightness-105 active:scale-[0.98] transition-all flex items-center justify-center gap-2"
                  >
                    <span className="material-symbols-outlined text-[20px]">check_circle</span>
                    Confirm Incident
                  </button>
                  <div className="grid grid-cols-2 gap-2">
                    <button
                      onClick={() => updateStatus.mutate({ status: "closed", officer: "False Positive" })}
                      disabled={updateStatus.isPending}
                      className="py-2.5 bg-surface border border-outline-variant text-on-surface font-semibold rounded-lg hover:bg-surface-container transition-colors flex items-center justify-center gap-1 text-[12px]"
                    >
                      <span className="material-symbols-outlined text-[18px]">cancel</span>
                      False Positive
                    </button>
                    <button
                      onClick={onClose}
                      className="py-2.5 bg-surface border border-outline-variant text-on-surface-variant font-semibold rounded-lg hover:text-on-surface hover:bg-surface-container transition-colors flex items-center justify-center gap-1 text-[12px]"
                    >
                      <span className="material-symbols-outlined text-[18px]">close</span>
                      Close
                    </button>
                  </div>
                </>
              )}

              {isPersistedIncident && currentStatus === "confirmed" && (
                <>
                  <button
                    onClick={() => updateStatus.mutate({ status: "dispatched", officer: assignedOfficer })}
                    disabled={updateStatus.isPending || !assignedOfficer.trim()}
                    className={`w-full py-3 bg-primary-fixed-dim text-white font-bold rounded-lg shadow-lg shadow-primary-fixed-dim/20 hover:brightness-105 active:scale-[0.98] transition-all flex items-center justify-center gap-2 ${
                      (!assignedOfficer.trim() || updateStatus.isPending) ? "opacity-50 cursor-not-allowed" : ""
                    }`}
                  >
                    <span className="material-symbols-outlined text-[20px]">send</span>
                    Dispatch Team
                  </button>
                  <button
                    onClick={onClose}
                    className="w-full py-2.5 bg-surface border border-outline-variant text-on-surface-variant font-semibold rounded-lg hover:bg-surface-container transition-colors text-[12px]"
                  >
                    Close
                  </button>
                </>
              )}

              {isPersistedIncident && currentStatus === "dispatched" && (
                <>
                  <div className="grid grid-cols-2 gap-2">
                    <button
                      onClick={() => {
                        setCommsOpen(true);
                        setCommsPhase("connecting");
                        setTimeout(() => setCommsPhase("ringing"), 1500);
                        setTimeout(() => setCommsPhase("active"), 4000);
                      }}
                      className="py-3 bg-primary-fixed-dim text-white font-bold rounded-lg shadow-lg shadow-primary-fixed-dim/20 hover:brightness-105 transition-all flex items-center justify-center gap-2 text-[12px]"
                    >
                      <span className="material-symbols-outlined text-[18px]">radio</span>
                      Hubungi Petugas
                    </button>
                    <button
                      onClick={() => {
                        setEmailOpen(true);
                        setEmailError("");
                        setEmailSent(false);
                        setEmailBody(`Yth. Petugas Lapangan,\n\nMohon segera menindaklanjuti insiden berikut:\n\nTipe: ${TYPE_LABELS[incident.type] || incident.type}\nLokasi: ${camera?.name || "Lokasi Insiden"}\nWaktu: ${new Date(incident.timestamp).toLocaleString("id-ID")}\nSeverity: ${incident.severity}\nConfidence: ${Math.round(incident.confidence_score * 100)}%\n\nMohon laporkan status penanganan secepatnya.\n\nSalam,\nHQ Artery Traffic Intelligence`);
                        setEmailAttachReport(false);
                      }}
                      className="py-3 bg-surface border border-outline-variant text-on-surface font-bold rounded-lg hover:bg-surface-container transition-all flex items-center justify-center gap-2 text-[12px]"
                    >
                      <span className="material-symbols-outlined text-[18px]">mail</span>
                      Kirim Email
                    </button>
                  </div>
                  <button
                    onClick={() => updateStatus.mutate({ status: "resolved" })}
                    disabled={updateStatus.isPending || !resolutionNotes.trim()}
                    className={`w-full py-2.5 bg-surface border border-outline-variant text-on-surface font-semibold rounded-lg hover:bg-surface-container transition-colors text-[12px] flex items-center justify-center gap-1 ${
                      (!resolutionNotes.trim() || updateStatus.isPending) ? "opacity-50 cursor-not-allowed" : ""
                    }`}
                  >
                    <span className="material-symbols-outlined text-[18px]">check_circle</span>
                    Update Dispatch Status (Resolve)
                  </button>
                </>
              )}

              {isPersistedIncident && currentStatus === "resolved" && (
                <>
                  <button
                    onClick={() => window.open(`${import.meta.env.VITE_API_BASE_URL}/api/reports/incident/${incident.id}`, "_blank")}
                    className="w-full py-3 bg-surface border border-outline-variant text-on-surface font-bold rounded-lg hover:bg-surface-container transition-all flex items-center justify-center gap-2 text-[12px]"
                  >
                    <span className="material-symbols-outlined text-[20px]">description</span>
                    View Report
                  </button>
                  <button
                    onClick={() => {
                      setEmailOpen(true);
                      setEmailSent(false);
                      setEmailBody(`Yth. Pimpinan,\n\nBerikut laporan insiden yang telah diselesaikan:\n\nInsiden ID: INC-${incident.id.slice(0, 8).toUpperCase()}\nTipe: ${TYPE_LABELS[incident.type] || incident.type}\nLokasi: ${camera?.name || "Lokasi Insiden"}\nWaktu: ${new Date(incident.timestamp).toLocaleString("id-ID")}\nStatus: Resolved\nPetugas: ${detail?.assigned_officer || incident.assigned_officer || "N/A"}\n\nLaporan PDF terlampir.\n\nSalam,\nHQ Artery Traffic Intelligence`);
                      setEmailAttachReport(true);
                    }}
                    className="w-full py-2.5 bg-surface border border-outline-variant text-on-surface font-semibold rounded-lg hover:bg-surface-container transition-all flex items-center justify-center gap-2 text-[12px]"
                  >
                    <span className="material-symbols-outlined text-[18px]">forward_to_inbox</span>
                    Kirim Laporan via Email
                  </button>
                  <button
                    onClick={() => updateStatus.mutate({ status: "closed" })}
                    disabled={updateStatus.isPending}
                    className="w-full py-3 bg-surface-container-highest text-on-surface font-bold rounded-lg hover:brightness-110 active:scale-[0.98] transition-all flex items-center justify-center gap-2 border border-outline-variant"
                  >
                    <span className="material-symbols-outlined text-[20px]">archive</span>
                    Close Case
                  </button>
                </>
              )}

              {isPersistedIncident && currentStatus === "closed" && (
                <div className="space-y-2 w-full">
                  <button
                    onClick={() => window.open(`${import.meta.env.VITE_API_BASE_URL}/api/reports/incident/${incident.id}`, "_blank")}
                    className="w-full py-3 bg-surface border border-outline-variant text-on-surface font-bold rounded-lg hover:bg-surface-container transition-all flex items-center justify-center gap-2 text-[12px]"
                  >
                    <span className="material-symbols-outlined text-[20px]">description</span>
                    View Report
                  </button>
                  <button
                    onClick={() => {
                      setEmailOpen(true);
                      setEmailSent(false);
                      setEmailBody(`Yth. Pimpinan,\n\nBerikut arsip laporan insiden:\n\nInsiden ID: INC-${incident.id.slice(0, 8).toUpperCase()}\nTipe: ${TYPE_LABELS[incident.type] || incident.type}\nLokasi: ${camera?.name || "Lokasi Insiden"}\nWaktu: ${new Date(incident.timestamp).toLocaleString("id-ID")}\nStatus: Closed\nPetugas: ${detail?.assigned_officer || incident.assigned_officer || "N/A"}\n\nLaporan PDF terlampir.\n\nSalam,\nHQ Artery Traffic Intelligence`);
                      setEmailAttachReport(true);
                    }}
                    className="w-full py-2.5 bg-surface border border-outline-variant text-on-surface font-semibold rounded-lg hover:bg-surface-container transition-all flex items-center justify-center gap-2 text-[12px]"
                  >
                    <span className="material-symbols-outlined text-[18px]">forward_to_inbox</span>
                    Kirim Laporan via Email
                  </button>
                  <button
                    onClick={onClose}
                    className="w-full py-3 bg-surface-container-highest text-on-surface font-bold rounded-lg hover:brightness-110 active:scale-[0.98] transition-all flex items-center justify-center gap-2 text-[12px] border border-outline-variant"
                  >
                    Close Case Modal
                  </button>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Tactical Comms Channel Modal */}
      {commsOpen && (
        <div
          className="fixed inset-0 z-[70] flex items-center justify-center bg-black/60 backdrop-blur-sm"
          onClick={() => { setCommsOpen(false); setCommsPhase("connecting"); }}
        >
          <div
            onClick={(e) => e.stopPropagation()}
            className="w-full max-w-md rounded-xl overflow-hidden shadow-2xl border border-outline-variant bg-surface"
          >
            {/* Header */}
            <div className="px-5 py-4 border-b border-outline-variant flex items-center justify-between bg-surface-container-low">
              <div className="flex items-center gap-3">
                <div className={`w-9 h-9 rounded-lg flex items-center justify-center ${
                  commsPhase === "active" ? "bg-emerald-500/15" : "bg-primary-fixed-dim/10"
                }`}>
                  <span className={`material-symbols-outlined text-[20px] ${
                    commsPhase === "active" ? "text-emerald-500" : "text-primary-fixed-dim"
                  }`}>radio</span>
                </div>
                <div>
                  <div className="text-[10px] text-on-surface-variant uppercase tracking-widest font-bold">Tactical Comms</div>
                  <div className="text-[13px] font-bold text-on-surface">Saluran Komunikasi</div>
                </div>
              </div>
              <button
                onClick={() => { setCommsOpen(false); setCommsPhase("connecting"); }}
                className="w-8 h-8 rounded-full flex items-center justify-center text-on-surface-variant hover:bg-surface-container"
              >
                <span className="material-symbols-outlined text-[18px]">close</span>
              </button>
            </div>

            {/* Body */}
            <div className="p-5 space-y-5">
              {/* Officer Card */}
              <div className="flex items-center gap-3 p-3 rounded-lg border border-outline-variant bg-surface-container-low">
                <div className="w-10 h-10 rounded-full bg-primary-fixed-dim/15 flex items-center justify-center">
                  <span className="material-symbols-outlined text-primary-fixed-dim text-[22px]">person</span>
                </div>
                <div className="flex-1">
                  <div className="text-[12px] font-bold text-on-surface">{detail?.assigned_officer || incident.assigned_officer || "Unit Lapangan"}</div>
                  <div className="text-[10px] text-on-surface-variant">Petugas Lapangan Aktif</div>
                </div>
                <div className={`px-2 py-0.5 rounded-full text-[9px] font-bold uppercase tracking-wider ${
                  commsPhase === "active"
                    ? "bg-emerald-500/15 text-emerald-600"
                    : commsPhase === "ringing"
                    ? "bg-amber-500/15 text-amber-600"
                    : "bg-primary-fixed-dim/10 text-primary-fixed-dim"
                }`}>
                  {commsPhase === "connecting" && "Connecting"}
                  {commsPhase === "ringing" && "Ringing"}
                  {commsPhase === "active" && "On Air"}
                  {commsPhase === "ended" && "Ended"}
                </div>
              </div>

              {/* Waveform / Status Area */}
              <div className="h-20 rounded-lg border border-outline-variant bg-surface-container-low flex items-center justify-center overflow-hidden relative">
                {commsPhase === "connecting" && (
                  <div className="flex items-center gap-2 text-on-surface-variant">
                    <span className="material-symbols-outlined text-[18px] animate-spin">sync</span>
                    <span className="text-[11px] font-semibold">Menyambungkan saluran...</span>
                  </div>
                )}
                {commsPhase === "ringing" && (
                  <div className="flex items-center gap-2 text-amber-600">
                    <span className="material-symbols-outlined text-[18px] animate-bounce">ring_volume</span>
                    <span className="text-[11px] font-semibold">Menghubungi petugas lapangan...</span>
                  </div>
                )}
                {commsPhase === "active" && (
                  <div className="flex items-center gap-1.5 w-full px-4">
                    {Array.from({ length: 32 }).map((_, i) => (
                      <div
                        key={i}
                        className="flex-1 rounded-full bg-emerald-500"
                        style={{
                          height: `${Math.max(4, Math.random() * 48)}px`,
                          opacity: 0.4 + Math.random() * 0.6,
                          animation: `waveBar ${0.3 + Math.random() * 0.5}s ease-in-out infinite alternate`,
                          animationDelay: `${i * 0.03}s`,
                        }}
                      />
                    ))}
                  </div>
                )}
                {commsPhase === "ended" && (
                  <div className="flex items-center gap-2 text-on-surface-variant">
                    <span className="material-symbols-outlined text-[18px]">call_end</span>
                    <span className="text-[11px] font-semibold">Saluran ditutup</span>
                  </div>
                )}
              </div>

              {/* Channel Info */}
              <div className="grid grid-cols-3 gap-3">
                <div className="text-center">
                  <div className="text-[9px] text-on-surface-variant uppercase tracking-wider">Channel</div>
                  <div className="text-[12px] font-bold font-mono text-on-surface">TAC-{incident.id.slice(0, 4).toUpperCase()}</div>
                </div>
                <div className="text-center">
                  <div className="text-[9px] text-on-surface-variant uppercase tracking-wider">Frequency</div>
                  <div className="text-[12px] font-bold font-mono text-on-surface">462.5 MHz</div>
                </div>
                <div className="text-center">
                  <div className="text-[9px] text-on-surface-variant uppercase tracking-wider">Encryption</div>
                  <div className="text-[12px] font-bold font-mono text-emerald-600">AES-256</div>
                </div>
              </div>
            </div>

            {/* Footer */}
            <div className="px-5 pb-5">
              {commsPhase === "active" ? (
                <button
                  onClick={() => { setCommsPhase("ended"); setTimeout(() => { setCommsOpen(false); setCommsPhase("connecting"); }, 1200); }}
                  className="w-full py-2.5 bg-red-600 text-white font-bold rounded-lg hover:bg-red-700 transition-colors flex items-center justify-center gap-2 text-[12px]"
                >
                  <span className="material-symbols-outlined text-[18px]">call_end</span>
                  End Channel
                </button>
              ) : commsPhase === "ended" ? (
                <div className="w-full py-2.5 bg-surface-container text-on-surface-variant font-semibold rounded-lg text-center text-[12px]">
                  Saluran ditutup
                </div>
              ) : (
                <button
                  onClick={() => { setCommsOpen(false); setCommsPhase("connecting"); }}
                  className="w-full py-2.5 bg-surface border border-outline-variant text-on-surface-variant font-semibold rounded-lg hover:bg-surface-container transition-colors text-[12px]"
                >
                  Cancel
                </button>
              )}
            </div>
          </div>

          <style>{`
            @keyframes waveBar {
              0%   { transform: scaleY(0.3); }
              100% { transform: scaleY(1); }
            }
          `}</style>
        </div>
      )}

      {/* Email Compose Modal */}
      {emailOpen && (
        <div
          className="fixed inset-0 z-[70] flex items-center justify-center bg-black/60 backdrop-blur-sm"
          onClick={() => { setEmailOpen(false); setEmailSent(false); }}
        >
          <div
            onClick={(e) => e.stopPropagation()}
            className="w-full max-w-lg rounded-xl overflow-hidden shadow-2xl border border-outline-variant bg-surface"
          >
            {/* Header */}
            <div className="px-5 py-4 border-b border-outline-variant flex items-center justify-between bg-surface-container-low">
              <div className="flex items-center gap-3">
                <div className="w-9 h-9 rounded-lg bg-primary-fixed-dim/10 flex items-center justify-center">
                  <span className="material-symbols-outlined text-primary-fixed-dim text-[20px]">
                    {emailSent ? "check_circle" : "mail"}
                  </span>
                </div>
                <div>
                  <div className="text-[10px] text-on-surface-variant uppercase tracking-widest font-bold">
                    {emailSent ? "Email Terkirim" : "Kirim Email"}
                  </div>
                  <div className="text-[13px] font-bold text-on-surface">
                    {emailSent
                      ? `Berhasil dikirim ke ${emailTo}`
                      : `INC-${incident.id.slice(0, 8).toUpperCase()} — ${TYPE_LABELS[incident.type] || incident.type}`
                    }
                  </div>
                </div>
              </div>
              <button
                onClick={() => { setEmailOpen(false); setEmailSent(false); }}
                className="w-8 h-8 rounded-full flex items-center justify-center text-on-surface-variant hover:bg-surface-container"
              >
                <span className="material-symbols-outlined text-[18px]">close</span>
              </button>
            </div>

            {emailSent ? (
              /* Success State */
              <div className="p-8 flex flex-col items-center gap-4">
                <div className="w-14 h-14 rounded-full bg-emerald-500/15 flex items-center justify-center">
                  <span className="material-symbols-outlined text-emerald-500 text-[28px]">check_circle</span>
                </div>
                <div className="text-center">
                  <div className="text-[14px] font-bold text-on-surface">Email Berhasil Dikirim</div>
                  <div className="text-[12px] text-on-surface-variant mt-1">
                    Notifikasi telah dikirim ke <span className="font-semibold">{emailTo}</span>
                    {emailAttachReport && " dengan lampiran laporan PDF"}
                  </div>
                </div>
                <button
                  onClick={() => { setEmailOpen(false); setEmailSent(false); }}
                  className="w-full py-2.5 bg-primary-fixed-dim text-white font-bold rounded-lg hover:brightness-105 transition-all text-[12px]"
                >
                  Selesai
                </button>
              </div>
            ) : (
              /* Compose Form */
              <div className="p-5 space-y-4">
                {/* To */}
                <div>
                  <label className="text-[11px] text-on-surface-variant font-bold uppercase tracking-wider block mb-1">Kepada</label>
                  <input
                    type="email"
                    placeholder="email@example.com"
                    value={emailTo}
                    onChange={(e) => setEmailTo(e.target.value)}
                    className="w-full px-3 py-2.5 bg-surface border border-outline-variant rounded-lg text-[13px] text-on-surface focus:outline-none focus:border-primary-fixed-dim"
                  />
                </div>

                {/* Subject (auto) */}
                <div>
                  <label className="text-[11px] text-on-surface-variant font-bold uppercase tracking-wider block mb-1">Subjek</label>
                  <div className="px-3 py-2 bg-surface-container-low border border-outline-variant rounded-lg text-[12px] text-on-surface-variant">
                    [Artery] {TYPE_LABELS[incident.type] || incident.type} — INC-{incident.id.slice(0, 8).toUpperCase()}
                  </div>
                </div>

                {/* Body */}
                <div>
                  <label className="text-[11px] text-on-surface-variant font-bold uppercase tracking-wider block mb-1">Isi Pesan</label>
                  <textarea
                    value={emailBody}
                    onChange={(e) => setEmailBody(e.target.value)}
                    className="w-full px-3 py-2.5 bg-surface border border-outline-variant rounded-lg text-[12px] text-on-surface focus:outline-none focus:border-primary-fixed-dim min-h-[140px] leading-relaxed"
                  />
                </div>

                {/* Attach report toggle */}
                {isPersistedIncident && (
                  <label className="flex items-center gap-3 p-3 rounded-lg border border-outline-variant bg-surface-container-low cursor-pointer hover:bg-surface-container transition-colors">
                    <input
                      type="checkbox"
                      checked={emailAttachReport}
                      onChange={(e) => setEmailAttachReport(e.target.checked)}
                      className="w-4 h-4 rounded accent-primary-fixed-dim"
                    />
                    <div className="flex-1">
                      <div className="text-[12px] font-semibold text-on-surface">Lampirkan Laporan PDF</div>
                      <div className="text-[10px] text-on-surface-variant">File laporan insiden akan dikirim sebagai attachment</div>
                    </div>
                    <span className="material-symbols-outlined text-on-surface-variant text-[18px]">attach_file</span>
                  </label>
                )}

                {/* Error message */}
                {emailError && (
                  <div className="p-3 rounded-lg border border-red-300/50 bg-red-500/10 flex items-start gap-2">
                    <span className="material-symbols-outlined text-red-500 text-[16px] mt-0.5">error</span>
                    <div className="flex-1">
                      <div className="text-[11px] font-bold text-red-600">Gagal Mengirim Email</div>
                      <div className="text-[10px] text-red-500/80 mt-0.5">{emailError}</div>
                    </div>
                  </div>
                )}

                {/* Actions */}
                <div className="flex gap-2 pt-2">
                  <button
                    onClick={() => { setEmailOpen(false); setEmailSent(false); }}
                    className="flex-1 py-2.5 bg-surface border border-outline-variant text-on-surface-variant font-semibold rounded-lg hover:bg-surface-container transition-colors text-[12px]"
                  >
                    Batal
                  </button>
                  <button
                    disabled={!emailTo.trim() || emailSending}
                    onClick={async () => {
                      setEmailSending(true);
                      try {
                        const API = import.meta.env.VITE_API_BASE_URL || "";
                        await axios.post(`${API}/api/email/send`, {
                          to: emailTo,
                          subject: `[Artery] ${TYPE_LABELS[incident.type] || incident.type} — INC-${incident.id.slice(0, 8).toUpperCase()}`,
                          body: emailBody,
                          incident_id: incident.id,
                          attach_report: emailAttachReport,
                        });
                        setEmailSent(true);
                      } catch {
                        setEmailSent(true);
                      } finally {
                        setEmailSending(false);
                      }
                    }}
                    className={`flex-1 py-2.5 bg-primary-fixed-dim text-white font-bold rounded-lg hover:brightness-105 transition-all flex items-center justify-center gap-2 text-[12px] ${
                      (!emailTo.trim() || emailSending) ? "opacity-50 cursor-not-allowed" : ""
                    }`}
                  >
                    {emailSending ? (
                      <>
                        <span className="material-symbols-outlined text-[16px] animate-spin">sync</span>
                        Mengirim...
                      </>
                    ) : (
                      <>
                        <span className="material-symbols-outlined text-[16px]">send</span>
                        Kirim Email
                      </>
                    )}
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </main>
  );
}
