import { useState } from "react";
import type { ViolationDetail } from "../Modals/ViolationDetailModal";

const VIOLATION_TYPE_CONFIG: Record<string, { icon: string; label: string; color: string; bg: string }> = {
  traffic_sign_detected: { icon: "signpost", label: "Rambu Lalu Lintas", color: "#d97706", bg: "rgba(217, 119, 6, 0.08)" },
  traffic_sign:          { icon: "signpost", label: "Rambu Lalu Lintas", color: "#d97706", bg: "rgba(217, 119, 6, 0.08)" },
  red_light_detected:    { icon: "traffic", label: "Lampu Merah",       color: "#dc2626", bg: "rgba(220, 38, 38, 0.08)" },
  red_light:             { icon: "traffic", label: "Lampu Merah",       color: "#dc2626", bg: "rgba(220, 38, 38, 0.08)" },
  plate_number_read:     { icon: "badge", label: "Plat Nomor Terbaca", color: "#30318b", bg: "rgba(48, 49, 139, 0.08)" },
  plate_read:            { icon: "badge", label: "Plat Nomor Terbaca", color: "#30318b", bg: "rgba(48, 49, 139, 0.08)" },
  high_traffic_density:  { icon: "directions_car", label: "Kepadatan Tinggi", color: "#ea580c", bg: "rgba(234, 88, 12, 0.08)" },
  high_traffic:          { icon: "directions_car", label: "Kepadatan Tinggi", color: "#ea580c", bg: "rgba(234, 88, 12, 0.08)" },
  pedestrian_on_road:    { icon: "directions_walk", label: "Pejalan Kaki", color: "#7c3aed", bg: "rgba(124, 58, 237, 0.08)" },
  bicycle_in_vehicle_lane: { icon: "pedal_bike", label: "Sepeda di Lajur", color: "#0d9488", bg: "rgba(13, 148, 136, 0.08)" },
  violation:             { icon: "warning", label: "Pelanggaran", color: "#dc2626", bg: "rgba(220, 38, 38, 0.08)" },
};

interface ViolationFeedProps {
  violations: ViolationDetail[];
  onViolationClick?: (v: ViolationDetail) => void;
}

export function ViolationFeedPanel({ violations, onViolationClick }: ViolationFeedProps) {
  const [decisions, setDecisions] = useState<Record<string, "approved" | "rejected">>({});

  const handleApprove = (eventId: string) => {
    setDecisions((prev) => ({ ...prev, [eventId]: "approved" }));
  };

  const handleReject = (eventId: string) => {
    setDecisions((prev) => ({ ...prev, [eventId]: "rejected" }));
  };

  return (
    <div style={{ padding: "12px 16px 0 16px", display: "flex", flexDirection: "column", gap: 10, height: "100%", overflow: "hidden" }}>
      <div style={{ display: "flex", flexDirection: "column", gap: 8, flex: 1, overflowY: "auto", paddingBottom: 12 }}>
        {violations.map((v) => {
          const cfg = VIOLATION_TYPE_CONFIG[v.violation_type] || VIOLATION_TYPE_CONFIG.violation;
          const decision = decisions[v.event_id];
          const borderColor =
            decision === "approved" ? "#10b981" :
            decision === "rejected" ? "#9ca3af" :
            cfg.color + "25";
          const borderLeftColor =
            decision === "approved" ? "#10b981" :
            decision === "rejected" ? "#9ca3af" :
            cfg.color;

          return (
            <div
              key={v.event_id}
              style={{
                background: "#ffffff",
                border: `1px solid ${borderColor}`,
                borderLeft: `4px solid ${borderLeftColor}`,
                borderRadius: 12,
                padding: "12px 14px",
                cursor: "pointer",
                boxShadow: "0 1px 3px rgba(0, 0, 0, 0.02), 0 1px 2px rgba(0, 0, 0, 0.04)",
                opacity: decision === "rejected" ? 0.6 : 1,
                transition: "all 0.2s",
              }}
              onClick={() => onViolationClick?.(v)}
            >
              {/* Header: icon + label + type badge */}
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                  <span className="material-symbols-outlined" style={{ fontSize: 16, color: cfg.color }}>{cfg.icon}</span>
                  <span style={{ color: "#0f172a", fontSize: 12, fontWeight: 700 }}>
                    {cfg.label}
                  </span>
                </div>
                <span
                  style={{
                    color: cfg.color,
                    fontSize: 10,
                    padding: "2px 6px",
                    border: `1px solid ${cfg.color}35`,
                    borderRadius: 6,
                    background: cfg.bg,
                    fontWeight: 600,
                  }}
                >
                  {v.violation_type.replace(/_/g, " ")}
                </span>
              </div>

              {/* Description */}
              <div style={{ color: "#334155", fontSize: 11, marginTop: 6, lineHeight: 1.4 }}>
                {v.description}
              </div>

              {/* Source + Plate */}
              <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 6, flexWrap: "wrap" }}>
                <span style={{ color: "#64748b", fontSize: 10, fontWeight: 500, display: "flex", alignItems: "center", gap: 3 }}>
                  <span className="material-symbols-outlined" style={{ fontSize: 13 }}>videocam</span>
                  {v.source}
                </span>
                {v.plate_number && (
                  <span
                    style={{
                      color: "#1e40af",
                      fontSize: 10,
                      fontWeight: 700,
                      fontFamily: "monospace",
                      background: "rgba(37, 99, 235, 0.08)",
                      padding: "1px 6px",
                      borderRadius: 4,
                      border: "1px solid rgba(37, 99, 235, 0.2)",
                      display: "flex",
                      alignItems: "center",
                      gap: 3,
                    }}
                  >
                    <span className="material-symbols-outlined" style={{ fontSize: 12 }}>badge</span>
                    {v.plate_number}
                  </span>
                )}
              </div>

              {/* Timestamp */}
              <div style={{ color: "#94a3b8", fontSize: 10, marginTop: 4, display: "flex", alignItems: "center", gap: 3 }}>
                <span className="material-symbols-outlined" style={{ fontSize: 13 }}>calendar_month</span>
                {new Date(v.timestamp * 1000).toLocaleString("id-ID")}
              </div>

              {/* Decision result or approve/reject buttons */}
              {decision ? (
                <div
                  style={{
                    marginTop: 8,
                    fontSize: 11,
                    fontWeight: 600,
                    color: decision === "approved" ? "#059669" : "#6b7280",
                    display: "flex",
                    alignItems: "center",
                    gap: 4,
                  }}
                >
                  <span className="material-symbols-outlined" style={{ fontSize: 14 }}>
                    {decision === "approved" ? "check_circle" : "cancel"}
                  </span>
                  <span>{decision === "approved" ? "Disetujui" : "Ditolak"}</span>
                </div>
              ) : (
                <div
                  style={{ marginTop: 8, display: "flex", gap: 6 }}
                  onClick={(e) => e.stopPropagation()}
                >
                  <button
                    onClick={() => handleApprove(v.event_id)}
                    style={{
                      flex: 1,
                      background: "rgba(16, 185, 129, 0.08)",
                      border: "1px solid rgba(16, 185, 129, 0.3)",
                      color: "#059669",
                      borderRadius: 8,
                      padding: "4px 10px",
                      fontSize: 11,
                      fontWeight: 600,
                      cursor: "pointer",
                      transition: "all 0.15s",
                    }}
                  >
                    <span className="material-symbols-outlined" style={{ fontSize: 13, verticalAlign: "text-bottom", marginRight: 4 }}>check_circle</span>
                    Approve
                  </button>
                  <button
                    onClick={() => handleReject(v.event_id)}
                    style={{
                      flex: 1,
                      background: "rgba(239, 68, 68, 0.06)",
                      border: "1px solid rgba(239, 68, 68, 0.25)",
                      color: "#dc2626",
                      borderRadius: 8,
                      padding: "4px 10px",
                      fontSize: 11,
                      fontWeight: 600,
                      cursor: "pointer",
                      transition: "all 0.15s",
                    }}
                  >
                    <span className="material-symbols-outlined" style={{ fontSize: 13, verticalAlign: "text-bottom", marginRight: 4 }}>cancel</span>
                    Reject
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
