import { useState } from "react";
import type { Incident } from "../../types";

const STATUS_CONFIG: Record<string, { label: string; color: string; bg: string }> = {
  detected:   { label: "Terdeteksi",   color: "#e11d48", bg: "rgba(225, 29, 72, 0.1)" },
  confirmed:  { label: "Dikonfirmasi", color: "#f97316", bg: "rgba(249, 115, 22, 0.1)" },
  dispatched: { label: "Dikirim",      color: "#3b82f6", bg: "rgba(59, 130, 246, 0.1)" },
  resolved:   { label: "Selesai",      color: "#10b981", bg: "rgba(16, 185, 129, 0.1)" },
  closed:     { label: "Ditutup",      color: "#6b7280", bg: "rgba(107, 114, 128, 0.1)" },
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
  notifications: Incident[];
  onIncidentClick?: (incident: Incident) => void;
}

export function NotificationHistoryPanel({ notifications, onIncidentClick }: Props) {
  const [filter, setFilter] = useState<"all" | "active" | "resolved">("all");
  const [search, setSearch] = useState("");

  const filteredNotifications = notifications.filter((notif) => {
    // 1. Filter by Status Tab
    if (filter === "active") {
      if (notif.status === "resolved" || notif.status === "closed") return false;
    } else if (filter === "resolved") {
      if (notif.status !== "resolved" && notif.status !== "closed") return false;
    }

    // 2. Filter by Search Query (type translated, camera_id)
    if (search.trim() !== "") {
      const typeLabel = TYPE_LABELS[notif.type] || notif.type;
      const query = search.toLowerCase();
      const matchType = typeLabel.toLowerCase().includes(query);
      const matchCamera = notif.camera_id.toLowerCase().includes(query);
      return matchType || matchCamera;
    }

    return true;
  });

  return (
    <div className="flex-1 flex flex-col h-full overflow-hidden">
      {/* Header */}
      <div className="p-6 border-b border-outline-variant flex items-center justify-between flex-shrink-0">
        <div className="flex items-center gap-2">
          <span className="material-symbols-outlined text-primary text-[20px]">history</span>
          <h2 className="text-[14px] font-bold uppercase tracking-tight text-on-surface">Riwayat Notifikasi</h2>
        </div>
        <span className="text-[10px] font-bold bg-primary/10 text-primary px-2 py-1 rounded-full">
          {filteredNotifications.length} DATA
        </span>
      </div>

      {/* Filters & Search Input */}
      <div className="p-4 border-b border-outline-variant flex flex-col gap-3 bg-surface-container-low/30">
        {/* Search Bar */}
        <div className="relative">
          <span className="material-symbols-outlined absolute left-3 top-1/2 -translate-y-1/2 text-on-surface-variant text-[18px]">
            search
          </span>
          <input
            type="text"
            placeholder="Cari kamera atau tipe pelanggaran..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full pl-9 pr-4 py-1.5 bg-white border border-outline-variant rounded-xl text-[12px] placeholder:text-on-surface-variant focus:outline-none focus:border-primary transition-all"
          />
        </div>

        {/* Tab Buttons */}
        <div className="flex gap-2">
          <button
            onClick={() => setFilter("all")}
            className={`flex-1 py-1 text-[11px] font-bold rounded-lg border transition-all ${
              filter === "all"
                ? "bg-primary text-white border-primary"
                : "bg-white text-on-surface-variant border-outline-variant hover:bg-slate-50"
            }`}
          >
            Semua
          </button>
          <button
            onClick={() => setFilter("active")}
            className={`flex-1 py-1 text-[11px] font-bold rounded-lg border transition-all ${
              filter === "active"
                ? "bg-primary text-white border-primary"
                : "bg-white text-on-surface-variant border-outline-variant hover:bg-slate-50"
            }`}
          >
            Aktif
          </button>
          <button
            onClick={() => setFilter("resolved")}
            className={`flex-1 py-1 text-[11px] font-bold rounded-lg border transition-all ${
              filter === "resolved"
                ? "bg-primary text-white border-primary"
                : "bg-white text-on-surface-variant border-outline-variant hover:bg-slate-50"
            }`}
          >
            Selesai
          </button>
        </div>
      </div>

      {/* List content */}
      <div className="flex-1 overflow-y-auto p-4 flex flex-col gap-2.5">
        {filteredNotifications.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-12 text-on-surface-variant gap-2">
            <span className="material-symbols-outlined text-[32px] text-outline">notifications_off</span>
            <span className="text-[12px] font-semibold">Tidak ada riwayat notifikasi</span>
          </div>
        ) : (
          filteredNotifications.map((notif) => {
            const statusCfg = STATUS_CONFIG[notif.status] || STATUS_CONFIG.detected;
            const typeLabel = TYPE_LABELS[notif.type] || notif.type;
            const dateObj = new Date(notif.timestamp);

            return (
              <div
                key={notif.id}
                onClick={() => onIncidentClick?.(notif)}
                className="p-3 bg-white hover:bg-slate-50 border border-outline-variant hover:border-primary-fixed rounded-xl transition-all cursor-pointer shadow-sm flex flex-col gap-2"
                style={{
                  borderLeft: `3px solid ${statusCfg.color}`,
                }}
              >
                {/* Header */}
                <div className="flex justify-between items-start gap-2">
                  <div className="flex flex-col">
                    <span className="text-[12px] font-bold text-on-surface leading-tight">
                      {typeLabel}
                    </span>
                    <span className="text-[10px] text-on-surface-variant mt-0.5 font-mono flex items-center gap-1">
                      <span className="material-symbols-outlined text-[13px]">location_on</span>
                      {notif.camera_id}
                    </span>
                  </div>
                  <span
                    className="text-[9px] font-bold px-2 py-0.5 rounded-full uppercase"
                    style={{
                      color: statusCfg.color,
                      backgroundColor: statusCfg.bg,
                    }}
                  >
                    {statusCfg.label}
                  </span>
                </div>

                {/* Confidence Bar */}
                <div className="flex flex-col gap-1">
                  <div className="flex justify-between items-center text-[9px] text-on-surface-variant">
                    <span>Akurasi Deteksi</span>
                    <span className="font-bold">
                      {Math.round((notif.confidence_score ?? 0.5) * 100)}%
                    </span>
                  </div>
                  <div className="w-full h-1.5 bg-slate-100 rounded-full overflow-hidden">
                    <div
                      className="h-full rounded-full transition-all duration-300"
                      style={{
                        width: `${(notif.confidence_score ?? 0.5) * 100}%`,
                        backgroundColor:
                          (notif.confidence_score ?? 0.5) > 0.7
                            ? "#10b981"
                            : (notif.confidence_score ?? 0.5) > 0.4
                            ? "#f97316"
                            : "#ef4444",
                      }}
                    />
                  </div>
                  {notif.source_count > 1 && (
                    <span className="text-[9px] text-on-surface-variant/80 flex items-center gap-1">
                      <span className="material-symbols-outlined text-[11px]">hub</span>
                      {notif.source_count} sinyal digabungkan
                    </span>
                  )}
                </div>

                {/* Footer / Time */}
                <div className="flex justify-between items-center border-t border-slate-50 pt-1.5 mt-0.5 text-[9px] text-on-surface-variant">
                  <span>ID: {notif.id.slice(0, 8)}...</span>
                  <span>
                    {dateObj.toLocaleDateString("id-ID", {
                      day: "2-digit",
                      month: "short",
                    })}{" "}
                    {dateObj.toLocaleTimeString("id-ID", {
                      hour: "2-digit",
                      minute: "2-digit",
                    })}
                  </span>
                </div>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}
