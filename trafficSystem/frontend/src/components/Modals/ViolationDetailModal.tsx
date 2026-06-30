import { useState } from "react";

export interface ViolationDetail {
  event_id: string;
  timestamp: number;
  violation_type: string;
  description: string;
  confidence: number;
  track_id?: number;
  vehicle_type?: string;
  plate_number?: string;
  evidence_image?: string;
  plate_crop?: string;
  plate_confidence?: number;
  plate_note?: string;
  video_time_seconds?: number;
  source: string;
}

const VIOLATION_TYPE_CONFIG: Record<string, { label: string; icon: string; severity: string; color: string; bgColor: string }> = {
  illegal_parking: { label: "Parkir Sembarangan", icon: "local_parking", severity: "high", color: "text-red-700", bgColor: "bg-red-50 border-red-200" },
  shoulder_violation: { label: "Pelanggaran Bahu Jalan", icon: "alt_route", severity: "high", color: "text-red-700", bgColor: "bg-red-50 border-red-200" },
  red_light_violation: { label: "Menerobos Lampu Merah", icon: "traffic", severity: "high", color: "text-red-700", bgColor: "bg-red-50 border-red-200" },
  illegal_u_turn: { label: "Putar Arah Ilegal", icon: "u_turn_left", severity: "high", color: "text-red-700", bgColor: "bg-red-50 border-red-200" },
  unsafe_lane_change: { label: "Potong Lajur Berbahaya", icon: "switch_access_shortcut", severity: "high", color: "text-red-700", bgColor: "bg-red-50 border-red-200" },
  traffic_sign_detected: { label: "Rambu Lalu Lintas", icon: "signpost", severity: "medium", color: "text-amber-700", bgColor: "bg-amber-50 border-amber-200" },
  traffic_sign: { label: "Rambu Lalu Lintas", icon: "signpost", severity: "medium", color: "text-amber-700", bgColor: "bg-amber-50 border-amber-200" },
  red_light_detected: { label: "Lampu Merah Terdeteksi", icon: "traffic", severity: "high", color: "text-red-700", bgColor: "bg-red-50 border-red-200" },
  red_light: { label: "Lampu Merah Terdeteksi", icon: "traffic", severity: "high", color: "text-red-700", bgColor: "bg-red-50 border-red-200" },
  plate_number_read: { label: "Plat Nomor Terbaca", icon: "badge", severity: "info", color: "text-blue-700", bgColor: "bg-blue-50 border-blue-200" },
  plate_read: { label: "Plat Nomor Terbaca", icon: "badge", severity: "info", color: "text-blue-700", bgColor: "bg-blue-50 border-blue-200" },
  high_traffic_density: { label: "Kepadatan Lalu Lintas Tinggi", icon: "directions_car", severity: "high", color: "text-orange-700", bgColor: "bg-orange-50 border-orange-200" },
  high_traffic: { label: "Kepadatan Lalu Lintas Tinggi", icon: "directions_car", severity: "high", color: "text-orange-700", bgColor: "bg-orange-50 border-orange-200" },
  pedestrian_on_road: { label: "Pejalan Kaki di Jalan", icon: "directions_walk", severity: "high", color: "text-purple-700", bgColor: "bg-purple-50 border-purple-200" },
  bicycle_in_vehicle_lane: { label: "Sepeda di Lajur Kendaraan", icon: "pedal_bike", severity: "medium", color: "text-teal-700", bgColor: "bg-teal-50 border-teal-200" },
  violation: { label: "Pelanggaran", icon: "warning", severity: "high", color: "text-red-700", bgColor: "bg-red-50 border-red-200" },
};

const API_BASE = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

function resolveAssetUrl(path?: string) {
  if (!path) return "";
  if (/^https?:\/\//i.test(path)) return path;
  return `${API_BASE}${path.startsWith("/") ? path : `/${path}`}`;
}

const SEVERITY_CONFIG: Record<string, { label: string; color: string; dot: string }> = {
  info: { label: "INFO", color: "text-blue-600 bg-blue-50 border-blue-200", dot: "bg-blue-500" },
  medium: { label: "SEDANG", color: "text-amber-600 bg-amber-50 border-amber-200", dot: "bg-amber-500" },
  high: { label: "TINGGI", color: "text-red-600 bg-red-50 border-red-200", dot: "bg-red-500" },
};

interface Props {
  violation: ViolationDetail;
  onClose: () => void;
}

export function ViolationDetailModal({ violation, onClose }: Props) {
  const [showRaw, setShowRaw] = useState(false);

  const config = VIOLATION_TYPE_CONFIG[violation.violation_type] || VIOLATION_TYPE_CONFIG["violation"];
  const severityConfig = SEVERITY_CONFIG[config.severity] || SEVERITY_CONFIG["medium"];
  const evidenceUrl = resolveAssetUrl(violation.evidence_image);
  const plateCropUrl = resolveAssetUrl(violation.plate_crop);

  const formattedTime = new Date(violation.timestamp * 1000).toLocaleString("id-ID", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });

  return (
    <main
      onClick={onClose}
      className="fixed inset-0 z-[60] flex items-center justify-center p-md bg-black/40 overflow-y-auto pointer-events-auto"
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className="w-full max-w-lg rounded-2xl overflow-hidden flex flex-col pointer-events-auto shadow-2xl bg-white border border-outline-variant"
        style={{ animation: "slideUp 0.25s ease-out" }}
      >
        {/* ── Header ── */}
        <div className={`px-6 py-5 border-b ${config.bgColor} flex items-center justify-between`}>
          <div className="flex items-center gap-3">
            <div className={`w-11 h-11 rounded-xl flex items-center justify-center ${config.bgColor} border ${config.color} shadow-sm`}>
              <span className={`material-symbols-outlined text-[22px] ${config.color}`}>{config.icon}</span>
            </div>
            <div>
              <div className="flex items-center gap-2 mb-0.5">
                <span className="text-[9px] font-bold text-on-surface-variant uppercase tracking-widest">
                  VIO-{violation.event_id.slice(0, 8).toUpperCase()}
                </span>
                <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full border text-[9px] font-bold uppercase tracking-wider ${severityConfig.color}`}>
                  <span className={`w-1.5 h-1.5 rounded-full ${severityConfig.dot}`} />
                  {severityConfig.label}
                </span>
              </div>
              <h2 className="text-[15px] font-bold text-on-surface">{config.label}</h2>
            </div>
          </div>
          <button
            onClick={onClose}
            className="text-on-surface-variant hover:text-on-surface p-1 rounded-full hover:bg-black/5 transition-colors"
          >
            <span className="material-symbols-outlined text-[20px]">close</span>
          </button>
        </div>

        {/* ── Body ── */}
        <div className="px-6 py-5 space-y-5">
          {/* Description card */}
          <div className="p-4 bg-slate-50 border border-slate-200 rounded-xl">
            <div className="flex items-start gap-2">
              <span className="material-symbols-outlined text-[18px] text-slate-500 mt-0.5">description</span>
              <div>
                <p className="text-[10px] font-bold text-slate-500 uppercase tracking-wider mb-1">Deskripsi</p>
                <p className="text-[13px] text-on-surface leading-relaxed font-medium">
                  {violation.description}
                </p>
              </div>
            </div>
          </div>

          {(evidenceUrl || plateCropUrl) && (
            <div className="space-y-3">
              {evidenceUrl && (
                <div>
                  <p className="text-[10px] font-bold text-slate-500 uppercase tracking-wider mb-2">Foto Bukti Pelanggaran</p>
                  <img
                    src={evidenceUrl}
                    alt="Bukti pelanggaran"
                    className="w-full max-h-64 object-contain rounded-xl border border-slate-200 bg-slate-950"
                  />
                </div>
              )}
              {plateCropUrl && (
                <div>
                  <p className="text-[10px] font-bold text-slate-500 uppercase tracking-wider mb-2">Foto Plat / Identitas Kendaraan</p>
                  <img
                    src={plateCropUrl}
                    alt="Crop plat atau identitas kendaraan"
                    className="w-full max-h-40 object-contain rounded-xl border border-blue-200 bg-slate-950"
                  />
                </div>
              )}
            </div>
          )}

          {/* Metadata Grid */}
          <div className="grid grid-cols-2 gap-3">
            {/* Source */}
            <div className="p-3 bg-white border border-outline-variant rounded-xl">
              <div className="flex items-center gap-1.5 mb-1">
                <span className="material-symbols-outlined text-[14px] text-slate-400">videocam</span>
                <p className="text-[9px] font-bold text-slate-500 uppercase tracking-wider">Sumber</p>
              </div>
              <p className="text-[12px] font-bold text-on-surface">{violation.source}</p>
            </div>

            {/* Timestamp */}
            <div className="p-3 bg-white border border-outline-variant rounded-xl">
              <div className="flex items-center gap-1.5 mb-1">
                <span className="material-symbols-outlined text-[14px] text-slate-400">schedule</span>
                <p className="text-[9px] font-bold text-slate-500 uppercase tracking-wider">Waktu</p>
              </div>
              <p className="text-[12px] font-bold text-on-surface">{formattedTime}</p>
            </div>

            {/* Confidence */}
            <div className="p-3 bg-white border border-outline-variant rounded-xl">
              <div className="flex items-center gap-1.5 mb-1">
                <span className="material-symbols-outlined text-[14px] text-slate-400">speed</span>
                <p className="text-[9px] font-bold text-slate-500 uppercase tracking-wider">Confidence</p>
              </div>
              <div className="flex items-center gap-2">
                <p className="text-[12px] font-bold text-on-surface">{Math.round(violation.confidence * 100)}%</p>
                <div className="flex-1 h-1.5 bg-slate-200 rounded-full overflow-hidden">
                  <div
                    className={`h-full rounded-full transition-all ${
                      violation.confidence > 0.8 ? "bg-green-500" : violation.confidence > 0.5 ? "bg-amber-500" : "bg-red-500"
                    }`}
                    style={{ width: `${Math.round(violation.confidence * 100)}%` }}
                  />
                </div>
              </div>
            </div>

            {/* Track ID */}
            <div className="p-3 bg-white border border-outline-variant rounded-xl">
              <div className="flex items-center gap-1.5 mb-1">
                <span className="material-symbols-outlined text-[14px] text-slate-400">pin</span>
                <p className="text-[9px] font-bold text-slate-500 uppercase tracking-wider">Track ID</p>
              </div>
              <p className="text-[12px] font-bold text-on-surface">
                {violation.track_id != null ? `#${violation.track_id}` : "—"}
              </p>
            </div>

            {violation.video_time_seconds != null && (
              <div className="p-3 bg-white border border-outline-variant rounded-xl">
                <div className="flex items-center gap-1.5 mb-1">
                  <span className="material-symbols-outlined text-[14px] text-slate-400">timer</span>
                  <p className="text-[9px] font-bold text-slate-500 uppercase tracking-wider">Detik Video</p>
                </div>
                <p className="text-[12px] font-bold text-on-surface">{violation.video_time_seconds.toFixed(1)}s</p>
              </div>
            )}
          </div>

          {/* Plate + Vehicle Type (if available) */}
          {(violation.plate_number || violation.vehicle_type || violation.plate_note) && (
            <div className="flex gap-3">
              <div className="flex-1 p-3 bg-blue-50 border border-blue-200 rounded-xl">
                <div className="flex items-center gap-1.5 mb-1.5">
                  <span className="material-symbols-outlined text-[14px] text-blue-500">badge</span>
                  <p className="text-[9px] font-bold text-blue-600 uppercase tracking-wider">Hasil Ekstraksi Plat</p>
                </div>
                <p className="text-[16px] font-black text-blue-800 font-mono tracking-wider">
                  {violation.plate_number || "Tidak terlihat"}
                </p>
                {violation.plate_confidence != null && (
                  <p className="text-[9px] font-semibold text-blue-700 mt-1">
                    Confidence {Math.round(violation.plate_confidence * 100)}%
                  </p>
                )}
                {violation.plate_note && (
                  <p className="text-[10px] text-blue-700 mt-2 leading-relaxed">
                    {violation.plate_note}
                  </p>
                )}
              </div>
              {violation.vehicle_type && (
                <div className="flex-1 p-3 bg-white border border-outline-variant rounded-xl">
                  <div className="flex items-center gap-1.5 mb-1.5">
                    <span className="material-symbols-outlined text-[14px] text-slate-400">local_shipping</span>
                    <p className="text-[9px] font-bold text-slate-500 uppercase tracking-wider">Tipe Kendaraan</p>
                  </div>
                  <p className="text-[14px] font-bold text-on-surface capitalize">{violation.vehicle_type}</p>
                </div>
              )}
            </div>
          )}

          {/* Raw data toggle */}
          <div>
            <button
              onClick={() => setShowRaw(!showRaw)}
              className="text-[10px] text-slate-500 hover:text-slate-700 font-bold uppercase tracking-wider flex items-center gap-1 transition-colors"
            >
              <span className="material-symbols-outlined text-[14px]">{showRaw ? "expand_less" : "expand_more"}</span>
              {showRaw ? "Sembunyikan" : "Tampilkan"} Data Mentah
            </button>
            {showRaw && (
              <pre className="mt-2 p-3 bg-slate-900 text-green-400 text-[10px] rounded-xl overflow-x-auto font-mono leading-relaxed border border-slate-700">
                {JSON.stringify(violation, null, 2)}
              </pre>
            )}
          </div>
        </div>

        {/* ── Footer ── */}
        <div className="px-6 py-4 border-t border-outline-variant bg-slate-50 flex gap-3">
          <button
            onClick={onClose}
            className="flex-1 py-2.5 bg-white border border-outline-variant text-on-surface font-semibold rounded-xl hover:bg-slate-100 transition-colors text-[12px] flex items-center justify-center gap-2"
          >
            <span className="material-symbols-outlined text-[18px]">close</span>
            Tutup
          </button>
        </div>
      </div>

      <style>{`
        @keyframes slideUp {
          from { opacity: 0; transform: translateY(20px) scale(0.97); }
          to { opacity: 1; transform: translateY(0) scale(1); }
        }
      `}</style>
    </main>
  );
}
