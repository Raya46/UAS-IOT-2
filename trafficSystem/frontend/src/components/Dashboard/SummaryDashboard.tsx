import { useState, useEffect, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import axios from "axios";
import {
  AreaChart, Area, PieChart, Pie, Cell,
  XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
} from "recharts";
import { getTrafficCounts, getTrafficMetrics, getParkingStatus } from "../../services/api";

const API = import.meta.env.VITE_API_BASE_URL;

const TYPE_LABELS: Record<string, string> = {
  illegal_parking: "Parkir Liar",
  busway_violation: "Busway",
  congestion: "Kemacetan",
  wrong_way: "Lawan Arah",
  hazard_lights: "Lampu Hazard",
  red_light_violation: "Lampu Merah",
  illegal_u_turn: "Putar Arah",
  unsafe_lane_change: "Potong Lajur",
  shoulder_violation: "Bahu Jalan",
};

const TYPE_COLORS = ["#f97316", "#22c55e", "#ef4444", "#eab308", "#06b6d4", "#8b5cf6"];

const trafficTrend = [
  { time: "08:00", vehicles: 18, events: 1 },
  { time: "09:00", vehicles: 26, events: 3 },
  { time: "10:00", vehicles: 21, events: 2 },
  { time: "11:00", vehicles: 34, events: 4 },
  { time: "12:00", vehicles: 29, events: 3 },
  { time: "13:00", vehicles: 38, events: 5 },
];

const aiModules = [
  { title: "License Plate Recognition", detail: "Crop, upscale, denoise, OCR", status: "Ready", icon: "badge", color: "text-cyan-600" },
  { title: "Night Mode ANPR", detail: "Brightness-aware crop enhancement", status: "MVP", icon: "dark_mode", color: "text-indigo-600" },
  { title: "Context Reasoning", detail: "Zone, duration, class, source profile", status: "Active", icon: "psychology", color: "text-emerald-600" },
];

const decisionPipeline = [
  { label: "YOLO Detection", value: "Vehicle + Plate + Sign models", icon: "radar" },
  { label: "Plate LPR", value: "EasyOCR with preprocessing", icon: "badge" },
  { label: "Centroid Tracking", value: "Movement + stationary detection", icon: "track_changes" },
  { label: "Rule Engine", value: "6 violation rule modules", icon: "rule" },
  { label: "Evidence Export", value: "CSV / JSONL / E-TLE", icon: "file_present" },
];

export function SummaryDashboard() {
  const [trafficCounts, setTrafficCounts] = useState<any>(null);
  const [trafficMetrics, setTrafficMetrics] = useState<any>(null);
  const [parkingStatus, setParkingStatus] = useState<any>(null);

  const { data: stats } = useQuery<any>({
    queryKey: ["summary-stats"],
    queryFn: () => axios.get(`${API}/api/analytics/stats/summary?days=7`).then((r) => r.data),
    refetchInterval: 60000,
  });

  useEffect(() => {
    const fetchCCTV = () => {
      getTrafficCounts().then(setTrafficCounts).catch(() => {});
      getTrafficMetrics().then(setTrafficMetrics).catch(() => {});
      getParkingStatus().then(setParkingStatus).catch(() => {});
    };
    fetchCCTV();
    const interval = setInterval(fetchCCTV, 5000);
    return () => clearInterval(interval);
  }, []);

  const resolutionRate = stats
    ? Math.round((stats.resolved / Math.max(stats.total_incidents, 1)) * 100) : 0;

  const totalCrossings = useMemo(() => {
    if (!trafficCounts) return 0;
    let total = 0;
    Object.values(trafficCounts).forEach((line: any) => {
      total += (line.forward?.total || 0) + (line.backward?.total || 0);
    });
    return total;
  }, [trafficCounts]);

  const typeData = useMemo(() => {
    if (!stats?.by_type) return [];
    return Object.entries(stats.by_type).map(([name, count]) => ({
      name: TYPE_LABELS[name] || name,
      value: count as number,
    }));
  }, [stats]);

  return (
    <div className="flex-1 overflow-y-auto h-full">
      <div className="p-6 pb-4 border-b border-outline-variant flex-shrink-0">
        <div className="flex items-center gap-2 mb-1">
          <span className="material-symbols-outlined text-primary text-[20px]">dashboard</span>
          <h2 className="text-[14px] font-bold uppercase tracking-tight text-on-surface">Executive Summary</h2>
        </div>
        <p className="text-[11px] text-on-surface-variant">Ringkasan 7 hari — violation evidence & AI analytics</p>
      </div>

      <div className="p-6 flex flex-col gap-6">
        {/* KPI Cards */}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          {[
            { label: "Total Insiden", value: stats?.total_incidents ?? "—", icon: "shield", color: "text-orange-600", bg: "bg-orange-50" },
            { label: "Tingkat Selesai", value: `${resolutionRate}%`, icon: "check_circle", color: "text-emerald-600", bg: "bg-emerald-50" },
            { label: "Severity Tinggi", value: stats?.high_severity ?? "—", icon: "warning", color: "text-red-600", bg: "bg-red-50" },
            { label: "Avg Confidence", value: stats ? `${(stats.avg_confidence * 100).toFixed(0)}%` : "—", icon: "analytics", color: "text-blue-600", bg: "bg-blue-50" },
          ].map((metric) => (
            <div key={metric.label} className="bg-white border border-outline-variant rounded-2xl p-4 shadow-sm">
              <div className="flex items-center justify-between mb-2">
                <span className="text-[10px] font-semibold text-on-surface-variant uppercase tracking-wider">{metric.label}</span>
                <span className={`material-symbols-outlined text-[18px] ${metric.color}`}>{metric.icon}</span>
              </div>
              <span className="text-[22px] font-bold text-on-surface font-mono">{metric.value}</span>
            </div>
          ))}
        </div>

        {/* Real-time CCTV Analytics */}
        <div>
          <div className="flex items-center gap-2 mb-3">
            <span className="material-symbols-outlined text-[18px] text-primary">videocam</span>
            <h3 className="text-[12px] font-bold uppercase tracking-tight text-on-surface">Real-time CCTV & Traffic Analytics</h3>
          </div>
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
            <div className="bg-white border border-outline-variant rounded-2xl p-4 shadow-sm">
              <div className="flex items-center justify-between mb-2">
                <span className="text-[10px] font-semibold text-on-surface-variant uppercase">Traffic Density</span>
                <span className="material-symbols-outlined text-[18px] text-cyan-600">speed</span>
              </div>
              <span className="text-[20px] font-bold text-on-surface">{trafficMetrics?.density_level || "LOW"}</span>
              <div className="text-[10px] text-on-surface-variant mt-1">
                Speed: <span className="font-semibold text-cyan-700">{trafficMetrics?.average_speed ? `${Math.round(trafficMetrics.average_speed)} px/s` : "0 px/s"}</span>
              </div>
            </div>

            <div className="bg-white border border-outline-variant rounded-2xl p-4 shadow-sm">
              <div className="flex items-center justify-between mb-2">
                <span className="text-[10px] font-semibold text-on-surface-variant uppercase">Line Crossing</span>
                <span className="material-symbols-outlined text-[18px] text-emerald-600">trending_up</span>
              </div>
              <span className="text-[20px] font-bold text-on-surface">{totalCrossings}</span>
              <div className="text-[10px] text-on-surface-variant mt-1">Vehicles crossed</div>
            </div>

            <div className="bg-white border border-outline-variant rounded-2xl p-4 shadow-sm">
              <div className="flex items-center justify-between mb-2">
                <span className="text-[10px] font-semibold text-on-surface-variant uppercase">Parking Occupancy</span>
                <span className="material-symbols-outlined text-[18px] text-amber-600">local_parking</span>
              </div>
              <span className="text-[20px] font-bold text-on-surface">{parkingStatus?.occupancy_percentage || "0.0"}%</span>
              <div className="text-[10px] text-on-surface-variant mt-1">
                {parkingStatus?.occupied_spots || 0}/{parkingStatus?.total_spots || 1} occupied
              </div>
            </div>

            <div className="bg-white border border-outline-variant rounded-2xl p-4 shadow-sm">
              <div className="flex items-center justify-between mb-2">
                <span className="text-[10px] font-semibold text-on-surface-variant uppercase">Total Vehicles</span>
                <span className="material-symbols-outlined text-[18px] text-violet-600">directions_car</span>
              </div>
              <span className="text-[20px] font-bold text-on-surface">{trafficMetrics?.vehicle_count || 0}</span>
              <div className="text-[10px] text-on-surface-variant mt-1">In current view</div>
            </div>
          </div>
        </div>

        {/* Charts */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <div className="bg-white border border-outline-variant rounded-2xl p-5 shadow-sm">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-[12px] font-bold uppercase text-on-surface">Traffic Activity</h3>
              <span className="material-symbols-outlined text-[16px] text-primary">timeline</span>
            </div>
            <div className="h-[260px]">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={trafficTrend}>
                  <defs>
                    <linearGradient id="vFill" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#06b6d4" stopOpacity={0.3} />
                      <stop offset="95%" stopColor="#06b6d4" stopOpacity={0} />
                    </linearGradient>
                    <linearGradient id="eFill" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#f97316" stopOpacity={0.25} />
                      <stop offset="95%" stopColor="#f97316" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid stroke="#e2e8f0" strokeDasharray="4 4" vertical={false} />
                  <XAxis dataKey="time" tick={{ fill: "#64748b", fontSize: 11 }} axisLine={false} tickLine={false} />
                  <YAxis tick={{ fill: "#64748b", fontSize: 11 }} axisLine={false} tickLine={false} />
                  <Tooltip contentStyle={{ background: "#fff", border: "1px solid #e2e8f0", borderRadius: "8px", fontSize: 12 }} />
                  <Area type="monotone" dataKey="vehicles" stroke="#06b6d4" fill="url(#vFill)" strokeWidth={2} isAnimationActive={false} />
                  <Area type="monotone" dataKey="events" stroke="#f97316" fill="url(#eFill)" strokeWidth={2} isAnimationActive={false} />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          </div>

          <div className="bg-white border border-outline-variant rounded-2xl p-5 shadow-sm">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-[12px] font-bold uppercase text-on-surface">Violation Distribution</h3>
              <span className="material-symbols-outlined text-[16px] text-primary">pie_chart</span>
            </div>
            <div className="h-[260px]">
              {typeData.length > 0 ? (
                <ResponsiveContainer width="100%" height="100%">
                  <PieChart>
                    <Pie data={typeData} dataKey="value" nameKey="name" innerRadius={58} outerRadius={90} paddingAngle={3} isAnimationActive={false}>
                      {typeData.map((_, i) => (
                        <Cell key={i} fill={TYPE_COLORS[i % TYPE_COLORS.length]} />
                      ))}
                    </Pie>
                    <Tooltip contentStyle={{ background: "#fff", border: "1px solid #e2e8f0", borderRadius: "8px", fontSize: 12 }} />
                  </PieChart>
                </ResponsiveContainer>
              ) : (
                <div className="h-full flex items-center justify-center text-[12px] text-on-surface-variant">No data</div>
              )}
            </div>
          </div>
        </div>

        {/* AI Modules & Decision Pipeline */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <div className="bg-white border border-outline-variant rounded-2xl p-5 shadow-sm">
            <h3 className="text-[12px] font-bold uppercase text-on-surface mb-4">AI Modules</h3>
            <div className="flex flex-col gap-3">
              {aiModules.map((mod) => (
                <div key={mod.title} className="flex items-start gap-3 p-3 bg-slate-50 border border-slate-200 rounded-xl">
                  <span className={`material-symbols-outlined text-[20px] ${mod.color}`}>{mod.icon}</span>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-[12px] font-bold text-on-surface">{mod.title}</span>
                      <span className="text-[10px] font-bold text-emerald-700 bg-emerald-50 border border-emerald-200 px-2 py-0.5 rounded-md">{mod.status}</span>
                    </div>
                    <p className="text-[11px] text-on-surface-variant mt-0.5">{mod.detail}</p>
                  </div>
                </div>
              ))}
            </div>
          </div>

          <div className="bg-white border border-outline-variant rounded-2xl p-5 shadow-sm">
            <h3 className="text-[12px] font-bold uppercase text-on-surface mb-4">Decision Pipeline</h3>
            <div className="flex flex-col gap-3">
              {decisionPipeline.map((step, i) => (
                <div key={step.label} className="flex items-center gap-3 p-3 bg-slate-50 border border-slate-200 rounded-xl">
                  <span className="flex items-center justify-center w-7 h-7 rounded-lg bg-primary/10 text-primary text-[11px] font-bold">{i + 1}</span>
                  <span className="material-symbols-outlined text-[18px] text-primary">{step.icon}</span>
                  <div className="min-w-0 flex-1">
                    <span className="text-[12px] font-bold text-on-surface block">{step.label}</span>
                    <span className="text-[10px] text-on-surface-variant">{step.value}</span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
