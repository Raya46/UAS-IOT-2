import { useState } from "react";

export interface ActivityItem {
  id: string;
  type: "incident" | "task" | "team";
  action: string;
  title: string;
  description: string;
  timestamp: string | Date;
  icon: string;
  color: string;
  referenceId?: string;
}

interface ActivityPanelProps {
  activities: ActivityItem[];
  onIncidentClick: (incidentId: string) => void;
  onClose: () => void;
}

export function ActivityPanel({
  activities,
  onIncidentClick,
  onClose
}: ActivityPanelProps) {
  const [filter, setFilter] = useState<"all" | "incident" | "task" | "team">("all");

  const formatRelativeTime = (timestamp: string | Date) => {
    try {
      const now = new Date();
      const date = new Date(timestamp);
      const diffMs = now.getTime() - date.getTime();
      
      if (diffMs < 0) return "Baru saja"; // fallback for slight clock drift
      
      const diffMins = Math.floor(diffMs / 60000);
      if (diffMins < 1) return "Baru saja";
      if (diffMins < 60) return `${diffMins} mnt lalu`;
      
      const diffHours = Math.floor(diffMins / 60);
      if (diffHours < 24) return `${diffHours} jam lalu`;
      
      return date.toLocaleDateString("id-ID", {
        day: "numeric",
        month: "short",
        hour: "2-digit",
        minute: "2-digit"
      });
    } catch (e) {
      return "Waktu tidak dikenal";
    }
  };

  const filteredActivities = activities.filter((act) => {
    if (filter === "all") return true;
    return act.type === filter;
  });

  return (
    <div className="flex-1 flex flex-col h-full overflow-hidden bg-white/50">
      {/* Header */}
      <div className="p-6 border-b border-outline-variant flex items-center justify-between flex-shrink-0">
        <div className="flex items-center gap-2">
          <span className="material-symbols-outlined text-primary text-[20px]">history</span>
          <h2 className="text-[14px] font-bold uppercase tracking-tight text-on-surface">Activity Log</h2>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-[10px] font-bold bg-primary/10 text-primary px-2 py-1 rounded-full">
            {filteredActivities.length} LOGS
          </span>
          <button
            onClick={onClose}
            className="text-on-surface-variant/60 hover:text-on-surface transition-colors flex items-center justify-center p-1 rounded-full hover:bg-slate-100"
            title="Tutup Panel"
          >
            <span className="material-symbols-outlined text-[20px]">close</span>
          </button>
        </div>
      </div>

      {/* Filter Tabs */}
      <div className="px-6 py-3 border-b border-outline-variant/50 bg-white/30 flex gap-2 flex-shrink-0">
        {(["all", "incident", "task", "team"] as const).map((tab) => (
          <button
            key={tab}
            onClick={() => setFilter(tab)}
            className={`px-3 py-1 text-[10px] font-bold rounded-full border transition-all uppercase tracking-wider ${
              filter === tab
                ? "bg-primary text-white border-primary shadow-sm"
                : "bg-white/60 border-outline-variant text-on-surface-variant/70 hover:text-on-surface hover:bg-white"
            }`}
          >
            {tab === "all" ? "Semua" : tab === "incident" ? "Insiden" : tab === "task" ? "Tugas" : "Tim"}
          </button>
        ))}
      </div>

      {/* Activities Scroll Area */}
      <div className="flex-1 overflow-y-auto p-4 space-y-3">
        {filteredActivities.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-12 text-center text-on-surface-variant/50">
            <span className="material-symbols-outlined text-[36px] mb-2">history_toggle_off</span>
            <p className="text-[11px] italic">Tidak ada aktivitas tercatat untuk kategori ini</p>
          </div>
        ) : (
          filteredActivities.map((act) => {
            const isIncident = act.type === "incident";
            return (
              <div
                key={act.id}
                onClick={() => {
                  if (isIncident && act.referenceId) {
                    onIncidentClick(act.referenceId);
                  }
                }}
                className={`flex items-start gap-3 p-3 bg-white border border-outline-variant rounded-2xl shadow-sm transition-all duration-200 ${
                  isIncident && act.referenceId
                    ? "cursor-pointer hover:shadow-md hover:border-primary/30"
                    : ""
                }`}
              >
                {/* Left: Pastel Icon Block */}
                <div
                  className={`w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0 ${act.color}`}
                >
                  <span className="material-symbols-outlined text-[18px]">
                    {act.icon}
                  </span>
                </div>

                {/* Center Content */}
                <div className="flex-1 min-w-0">
                  <div className="flex justify-between items-start mb-0.5">
                    <span className="font-body-md text-body-md text-on-surface font-semibold truncate pr-2">
                      {act.title}
                    </span>
                    <span className="text-[9px] text-on-surface-variant/50 font-medium flex-shrink-0 pt-0.5">
                      {formatRelativeTime(act.timestamp)}
                    </span>
                  </div>
                  <p className="text-[10px] text-on-surface-variant/70 leading-relaxed font-medium break-words">
                    {act.description}
                  </p>
                  
                  {isIncident && act.referenceId && (
                    <div className={`mt-1.5 flex items-center gap-1 text-[9px] font-bold hover:underline ${
                      act.referenceId.startsWith("VIO-") ? "text-amber-600" : "text-primary"
                    }`}>
                      <span className="material-symbols-outlined text-[10px]">
                        {act.referenceId.startsWith("VIO-") ? "info" : "visibility"}
                      </span>
                      <span>{act.referenceId.startsWith("VIO-") ? "Lihat Detail Violation" : "Lihat Detail Insiden"}</span>
                    </div>
                  )}
                </div>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}
