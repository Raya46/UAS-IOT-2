import { useQuery } from "@tanstack/react-query";
import axios from "axios";
import { format } from "date-fns";

interface SummaryStats {
  total_incidents: number;
  high_severity: number;
  resolved: number;
  avg_confidence: number;
  avg_response_seconds: number;
  by_type: Record<string, number>;
}

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

export function ExecutiveSummaryPanel() {
  const today = format(new Date(), "yyyy-MM-dd");

  const { data: stats } = useQuery<SummaryStats>({
    queryKey: ["summary-stats"],
    queryFn: () =>
      axios
        .get(`${import.meta.env.VITE_API_BASE_URL}/api/analytics/stats/summary?days=7`)
        .then((r) => r.data),
    refetchInterval: 60000,
  });

  const resolutionRate = stats
    ? Math.round((stats.resolved / Math.max(stats.total_incidents, 1)) * 100)
    : 0;

  const avgResponseMin = stats?.avg_response_seconds
    ? Math.round(stats.avg_response_seconds / 60)
    : null;

  return (
    <div style={{ padding: 16, display: "flex", flexDirection: "column", gap: 14 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <span style={{ color: "rgb(48 49 139)", fontSize: 12, fontWeight: 700, display: "flex", alignItems: "center", gap: 6 }}>
          <span className="material-symbols-outlined" style={{ fontSize: 16 }}>bar_chart</span>
          Ringkasan 7 Hari
        </span>
        <a
          href={`${import.meta.env.VITE_API_BASE_URL}/api/reports/daily/${today}`}
          target="_blank"
          rel="noreferrer"
          style={{
            color: "rgb(48 49 139)", fontSize: 10,
            textDecoration: "none", border: "1px solid rgba(48, 49, 139, 0.25)",
            background: "rgba(253, 208, 3, 0.16)",
            padding: "3px 10px", borderRadius: 6,
            fontWeight: 600
          }}
        >
          ↓ PDF Hari Ini
        </a>
      </div>

      {/* Metric cards */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
        {[
          { label: "Total Insiden", value: stats?.total_incidents ?? "—", color: "#0f172a" },
          { label: "Tingkat Selesai", value: `${resolutionRate}%`, color: "#059669" },
          { label: "Severity Tinggi", value: stats?.high_severity ?? "—", color: "#ef4444" },
          { label: "Avg Response", value: avgResponseMin ? `${avgResponseMin} menit` : "—", color: "#3b82f6" },
        ].map((metric) => (
          <div
            key={metric.label}
            style={{
              background: "#f8fafc", border: "1px solid #e2e8f0",
              borderRadius: 12, padding: "12px 14px",
              boxShadow: "0 1px 2px rgba(0,0,0,0.02)"
            }}
          >
            <div style={{ color: metric.color, fontSize: 18, fontWeight: 700, fontFamily: "monospace" }}>
              {metric.value}
            </div>
            <div style={{ color: "#64748b", fontSize: 10, marginTop: 4, fontWeight: 500 }}>{metric.label}</div>
          </div>
        ))}
      </div>

      {/* Distribusi tipe */}
      {stats?.by_type && (
        <div style={{ display: "flex", flexDirection: "column", gap: 8, marginTop: 4 }}>
          <span style={{ color: "#475569", fontSize: 10, fontWeight: 600 }}>Distribusi Pelanggaran</span>
          {Object.entries(stats.by_type).map(([type, count]) => {
            const pct = Math.round((count / Math.max(stats.total_incidents, 1)) * 100);
            return (
              <div key={type}>
                <div style={{ display: "flex", justifyContent: "space-between", fontSize: 10, color: "#475569", marginBottom: 4 }}>
                  <span style={{ fontWeight: 500 }}>{TYPE_LABELS[type] || type}</span>
                  <span style={{ fontWeight: 600, color: "#0f172a" }}>{count} ({pct}%)</span>
                </div>
                <div style={{ height: 6, background: "#e2e8f0", borderRadius: 3, overflow: "hidden" }}>
                  <div style={{ width: `${pct}%`, height: "100%", background: "rgb(48 49 139)", borderRadius: 3 }} />
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
