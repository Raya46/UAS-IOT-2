import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { getEvents, getEventMitigation, refreshExternalEvents } from "../../services/api";
import axios from "axios";
import type { Event } from "../../types";

const IMPACT_COLORS: Record<string, string> = {
  KRITIS: "#e11d48", // matches Tailwind error colors
  TINGGI: "#f97316",
  SEDANG: "#eab308",
  RENDAH: "#22c55e",
};

const ZONE_LABELS: Record<string, string> = {
  red: "MERAH",
  orange: "ORANYE",
  yellow: "KUNING",
  green: "HIJAU",
};

const ZONE_COLORS: Record<string, string> = {
  red: "#e11d48",
  orange: "#f97316",
  yellow: "#eab308",
  green: "#22c55e",
};

export function EventMitigationPanel() {
  const queryClient = useQueryClient();
  const [selectedEvent, setSelectedEvent] = useState<Event | null>(null);

  const { data: events = [] } = useQuery({
    queryKey: ["events"],
    queryFn: async () => {
      const result = await getEvents();
      return Array.isArray(result) ? result : [];
    },
  });

  const { data: mitigation } = useQuery({
    queryKey: ["mitigation", selectedEvent?.id],
    queryFn: () => getEventMitigation(selectedEvent!.id),
    enabled: !!selectedEvent,
  });

  const triggerPrediction = useMutation({
    mutationFn: (eventId: string) =>
      axios.post(`${import.meta.env.VITE_API_BASE_URL}/api/events/${eventId}/trigger-prediction`),
    onSuccess: (res) => {
      if (res.data.success) {
        alert(`Simulasi kemacetan untuk event "${selectedEvent?.name}" berhasil ditrigger!`);
      } else {
        alert(`Gagal men-trigger: ${res.data.message}`);
      }
    }
  });

  const refreshEvents = useMutation({
    mutationFn: refreshExternalEvents,
    onSuccess: (res) => {
      queryClient.invalidateQueries({ queryKey: ["events"] });
      alert(`Sync Enjoy Jakarta selesai. ${res.stored ?? 0} event tersimpan.`);
    },
    onError: () => {
      alert("Sync Enjoy Jakarta gagal. Cek koneksi backend atau konfigurasi DATABASE_URL.");
    },
  });

  return (
    <div className="flex-1 flex flex-col h-full overflow-hidden">
      {/* Header */}
      <div className="p-6 border-b border-outline-variant flex items-center justify-between flex-shrink-0">
        <div className="flex items-center gap-2">
          <span className="material-symbols-outlined text-primary-fixed-dim text-[20px]">event</span>
          <h2 className="text-[14px] font-bold uppercase tracking-tight text-on-surface">Upcoming Events</h2>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => refreshEvents.mutate()}
            disabled={refreshEvents.isPending}
            className="h-7 w-7 rounded-lg border border-outline-variant bg-white text-on-surface-variant hover:text-primary hover:border-primary/40 transition-all flex items-center justify-center disabled:opacity-50"
            title="Sync Enjoy Jakarta events"
          >
            <span className={`material-symbols-outlined text-[16px] ${refreshEvents.isPending ? "animate-spin" : ""}`}>sync</span>
          </button>
          <span className="text-[10px] font-bold bg-primary/10 text-primary px-2 py-1 rounded-full">
            {events.length} ACTIVE
          </span>
        </div>
      </div>

      {/* Content scroll area */}
      <div className="flex-1 overflow-y-auto p-4 flex flex-col gap-3">
        {/* Event List */}
        <div className="flex flex-col gap-3">
          {events.map((event) => (
            <div
              key={event.id}
              onClick={() => setSelectedEvent(event)}
              className={`p-3 border rounded-xl hover:bg-white/80 transition-all cursor-pointer ${
                selectedEvent?.id === event.id
                  ? "bg-primary-fixed-dim/10 border-primary-fixed-dim"
                  : "bg-white/50 border-outline-variant"
              }`}
            >
              <div className="flex justify-between items-start mb-1 gap-2">
                <span className="text-[12px] font-bold text-on-surface leading-tight">{event.name}</span>
                <span className="text-[10px] text-on-surface-variant font-medium flex-shrink-0 flex items-center gap-1">
                  <span className="material-symbols-outlined text-[13px]">location_on</span>
                  {event.venue}
                </span>
              </div>
              <p className="text-[11px] text-on-surface-variant flex items-center gap-1">
                <span className="material-symbols-outlined text-[14px]">calendar_month</span>
                {event.date} · {event.time}
              </p>
              <div className="mt-2 flex justify-between items-center">
                <span className="text-[10px] font-bold text-primary uppercase flex items-center gap-1">
                  <span className="material-symbols-outlined text-[13px]">groups</span>
                  ~{event.estimated_crowd.toLocaleString()} orang
                </span>
                {event.crowd_zone && (
                  <span
                    className="text-[9px] font-black text-white px-2 py-0.5 rounded-full"
                    style={{ background: ZONE_COLORS[event.crowd_zone] }}
                  >
                    ZONA {ZONE_LABELS[event.crowd_zone]}
                  </span>
                )}
              </div>
              <div className="mt-1 flex items-center justify-between gap-2 text-[10px] text-on-surface-variant">
                <span className="truncate">{event.category || "general"} · {event.source || "manual"}</span>
                {event.officer_min && event.officer_max && (
                  <span className="font-bold text-on-surface whitespace-nowrap">{event.officer_min}-{event.officer_max} petugas</span>
                )}
              </div>
            </div>
          ))}
        </div>

        {/* Mitigation Details */}
        {mitigation && selectedEvent && (
          <div className="mt-2 p-3 bg-surface-container-low border border-outline-variant rounded-2xl flex flex-col gap-2">
            <div className="flex justify-between items-center">
              <span className="text-[11px] font-bold uppercase" style={{ color: IMPACT_COLORS[mitigation.impact_level] || "#333" }}>
                <span className="material-symbols-outlined text-[14px] mr-1">warning</span>
                DAMPAK: {mitigation.impact_level}
              </span>
              <span
                className="text-[10px] font-bold text-white px-2 py-0.5 rounded-full"
                style={{ background: mitigation.crowd_zone ? ZONE_COLORS[mitigation.crowd_zone] : "#64748b" }}
              >
                ZONA {mitigation.crowd_zone ? ZONE_LABELS[mitigation.crowd_zone] : "N/A"}
              </span>
            </div>
            <div className="text-[10px] text-on-surface-variant flex items-center gap-1">
              <span className="material-symbols-outlined text-[13px]">schedule</span>
              {mitigation.predicted_congestion_start} → {mitigation.predicted_congestion_end}
            </div>
            <div className="grid grid-cols-2 gap-2">
              <div className="rounded-lg border border-outline-variant bg-white/70 px-2 py-1">
                <div className="text-[9px] font-bold text-on-surface-variant uppercase">Estimasi massa</div>
                <div className="text-[12px] font-black text-on-surface">
                  ~{(mitigation.estimated_crowd ?? selectedEvent.estimated_crowd).toLocaleString()}
                </div>
              </div>
              <div className="rounded-lg border border-outline-variant bg-white/70 px-2 py-1">
                <div className="text-[9px] font-bold text-on-surface-variant uppercase">Aparat</div>
                <div className="text-[12px] font-black text-on-surface">
                  {mitigation.officer_min ?? selectedEvent.officer_min}-{mitigation.officer_max ?? selectedEvent.officer_max}
                </div>
              </div>
            </div>
            {(mitigation.crowd_reason || selectedEvent.crowd_reason) && (
              <div className="text-[10px] text-on-surface-variant leading-snug bg-white/60 border border-outline-variant rounded-lg px-2 py-1">
                {(mitigation.crowd_reason || selectedEvent.crowd_reason)}
              </div>
            )}

            {/* Simulate Congestion Button */}
            <button
              onClick={() => triggerPrediction.mutate(selectedEvent.id)}
              disabled={triggerPrediction.isPending}
              className="mt-2 w-full py-2 bg-error text-white font-bold text-[11px] rounded-lg uppercase tracking-wider hover:bg-error/95 transition-all"
            >
              {triggerPrediction.isPending ? "Simulating..." : "Simulate Congestion"}
            </button>

            <div className="text-[11px] font-bold text-on-surface mt-1 border-t border-outline-variant pt-2">
              Rekomendasi:
            </div>
            <ul className="list-disc pl-4 text-[11px] text-on-surface-variant flex flex-col gap-1">
              {mitigation.recommendations.map((rec, i) => (
                <li key={i}>{rec}</li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </div>
  );
}
