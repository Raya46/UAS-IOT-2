import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useMap } from "react-map-gl/mapbox";
import axios from "axios";
import type { Incident } from "../../types";
import { getIncidentSnapshotUrl } from "../../utils/incidentSnapshots";

const STATUS_CONFIG: Record<string, { label: string; color: string; bg: string }> = {
  detected:   { label: "Terdeteksi",   color: "#ef4444", bg: "rgba(239, 68, 68, 0.08)" },
  confirmed:  { label: "Dikonfirmasi", color: "#f97316", bg: "rgba(249, 115, 22, 0.08)" },
  dispatched: { label: "Dikirim",      color: "#2563eb", bg: "rgba(37, 99, 235, 0.08)" },
  resolved:   { label: "Selesai",      color: "#10b981", bg: "rgba(16, 185, 129, 0.08)" },
  closed:     { label: "Ditutup",      color: "#6b7280", bg: "rgba(107, 114, 128, 0.08)"    },
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
  red_light_violation: "Menerobos Lampu Merah",
  illegal_u_turn: "Putar Arah Sembarangan",
  unsafe_lane_change: "Potong Lajur Berbahaya",
  shoulder_violation: "Pelanggaran Bahu Jalan",
};

interface Props {
  onIncidentSelect?: (incident: Incident) => void;
}

export function IncidentPanel({ onIncidentSelect }: Props) {
  const [statusFilter, setStatusFilter] = useState<string>("detected");
  const [officerInput, setOfficerInput] = useState<Record<string, string>>({});
  const queryClient = useQueryClient();
  const maps = useMap();

  const handleFlyTo = (lat: number, lng: number) => {
    const map = maps.default || Object.values(maps)[0];
    if (map) {
      map.flyTo({
        center: [lng, lat],
        zoom: 15,
        duration: 1500,
        essential: true,
      });
    }
  };

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
    <div style={{ padding: "16px 16px 0 16px", display: "flex", flexDirection: "column", gap: 14, height: "100%", overflow: "hidden" }}>
      {/* Filter tab */}
      <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
        {Object.entries(STATUS_CONFIG).map(([key, cfg]) => (
          <button
            key={key}
            onClick={() => setStatusFilter(key)}
            style={{
              padding: "4px 12px",
              border: `1px solid ${statusFilter === key ? cfg.color : "rgb(var(--color-outline-variant))"}`,
              background: statusFilter === key ? cfg.bg : "rgb(var(--color-surface-container-low))",
              color: statusFilter === key ? cfg.color : "rgb(var(--color-on-surface-variant))",
              borderRadius: 8,
              fontSize: 11,
              fontWeight: 600,
              cursor: "pointer",
              boxShadow: statusFilter === key ? "none" : "0 1px 2px rgba(0,0,0,0.02)",
              transition: "all 0.15s"
            }}
          >
            {cfg.label}
          </button>
        ))}
      </div>

      {/* Daftar incidents */}
      {isLoading && <div style={{ color: "rgb(var(--color-on-surface-variant))", fontSize: 12 }}>Memuat...</div>}
      <div style={{ display: "flex", flexDirection: "column", gap: 8, flex: 1, overflowY: "auto", paddingBottom: 16 }}>
        {(data?.items ?? []).map((rawInc: Incident) => {
          const inc = {
            ...rawInc,
            snapshot_url: getIncidentSnapshotUrl(rawInc),
          };
          const cfg = STATUS_CONFIG[inc.status] || STATUS_CONFIG.detected;
          const nextStatus = NEXT_STATUS[inc.status];
          return (
            <div
              key={inc.id}
              style={{
                background: "rgb(var(--color-surface-matte))",
                border: `1px solid ${cfg.color}25`,
                borderLeft: `4px solid ${cfg.color}`,
                borderRadius: 12,
                padding: "12px 14px",
                cursor: "pointer",
                boxShadow: "0 1px 3px rgba(0, 0, 0, 0.02), 0 1px 2px rgba(0, 0, 0, 0.04)"
              }}
              onClick={() => onIncidentSelect?.(inc)}
            >
              {/* Header */}
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                  <span style={{ color: "rgb(var(--color-on-surface))", fontSize: 12, fontWeight: 700 }}>
                    {TYPE_LABELS[inc.type] || inc.type}
                  </span>
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      handleFlyTo(inc.lat, inc.lng);
                    }}
                    style={{
                      border: "none",
                      background: "none",
                      padding: 2,
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                      color: "rgb(var(--color-on-surface-variant))",
                      cursor: "pointer",
                      borderRadius: 4,
                    }}
                    title="Pusatkan Peta"
                  >
                    <span className="material-symbols-outlined text-[15px]">explore</span>
                  </button>
                </div>
                <span style={{
                  color: cfg.color, fontSize: 10, padding: "2px 6px",
                  border: `1px solid ${cfg.color}35`, borderRadius: 6,
                  background: cfg.bg, fontWeight: 600
                }}>
                  {cfg.label}
                </span>
              </div>

              {/* Confidence + source */}
              <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 8 }}>
                <div style={{ flex: 1, height: 4, background: "rgb(var(--color-surface-container-high))", borderRadius: 2, overflow: "hidden" }}>
                  <div style={{
                    width: `${inc.confidence_score * 100}%`,
                    height: "100%",
                    background: inc.confidence_score > 0.7 ? "#ef4444" : "#f97316",
                  }} />
                </div>
                <span style={{ color: "rgb(var(--color-on-surface-variant))", fontSize: 10, fontWeight: 500, minWidth: 60, textAlign: "right" }}>
                  {Math.round(inc.confidence_score * 100)}% · {inc.source_count} sinyal
                </span>
              </div>

              {/* Waktu & kamera */}
              <div style={{ color: "rgb(var(--color-on-surface-variant))", fontSize: 10, marginTop: 6, display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
                <span style={{ display: "flex", alignItems: "center", gap: 3 }}>
                  <span className="material-symbols-outlined" style={{ fontSize: 13 }}>calendar_month</span>
                  {new Date(inc.timestamp).toLocaleString("id-ID")}
                </span>
                <span>·</span>
                <span style={{ display: "flex", alignItems: "center", gap: 3 }}>
                  <span className="material-symbols-outlined" style={{ fontSize: 13 }}>location_on</span>
                  {inc.camera_id}
                </span>
              </div>

              {/* Action */}
              {nextStatus && (
                <div
                  style={{ marginTop: 10, display: "flex", alignItems: "center", gap: 6 }}
                  onClick={(e) => e.stopPropagation()}
                >
                  {nextStatus === "dispatched" && (
                    <input
                      placeholder="Nama petugas..."
                      value={officerInput[inc.id] || ""}
                      onChange={(e) => setOfficerInput(prev => ({ ...prev, [inc.id]: e.target.value }))}
                      style={{
                        flex: 1, background: "rgb(var(--color-surface-container-low))", border: "1px solid rgb(var(--color-outline-variant))",
                        color: "rgb(var(--color-on-surface))", borderRadius: 8, padding: "4px 8px", fontSize: 11,
                        outline: "none"
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
                      background: cfg.color + "15",
                      border: `1px solid ${cfg.color}50`,
                      color: cfg.color,
                      borderRadius: 8,
                      padding: "4px 12px",
                      fontSize: 11,
                      fontWeight: 600,
                      cursor: "pointer",
                      transition: "all 0.2s"
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
