import { useState, useEffect } from "react";
import { getViolationDetail, getEvidenceUrl, updateViolationStatus } from "../../services/api";

interface Props {
  eventId: string;
  onClose: () => void;
  onStatusChange?: (eventId: string, status: "approved" | "rejected") => void;
}

const TYPE_LABELS: Record<string, string> = {
  confirmed_illegal_parking: "Illegal Parking",
  illegal_parking: "Illegal Parking",
  potential_illegal_parking: "Potential Parking",
  wrong_direction: "Wrong Direction",
  restricted_area_stop: "Restricted Stop",
  shoulder_lane_violation: "Shoulder Lane",
  red_light_violation: "Red Light",
  illegal_u_turn: "Illegal U-Turn",
  unsafe_lane_change: "Lane Change",
  traffic_sign_violation: "Traffic Sign",
  hazard_lights_violation: "Hazard Lights",
};

export function EventDetailModal({ eventId, onClose, onStatusChange }: Props) {
  const [event, setEvent] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [evImgError, setEvImgError] = useState(false);
  const [plateImgError, setPlateImgError] = useState(false);

  useEffect(() => {
    getViolationDetail(eventId)
      .then(setEvent)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [eventId]);

  const handleStatus = async (status: "approved" | "rejected") => {
    try {
      await updateViolationStatus(eventId, status);
      setEvent((prev: any) => ({ ...prev, review_status: status }));
      onStatusChange?.(eventId, status);
    } catch {
      // silent
    }
  };

  const evidenceUrl = event ? getEvidenceUrl(event.evidence_image) : "";
  const plateUrl = event ? getEvidenceUrl(event.plate_crop) : "";
  const isPending = event?.review_status === "pending";

  return (
    <div
      className="fixed inset-0 z-[60] flex items-center justify-center p-6 md:p-10 bg-black/40 backdrop-blur-sm overflow-y-auto"
      onClick={onClose}
    >
      <div
        className="w-full max-w-2xl glass-modal rounded-2xl overflow-hidden flex flex-col shadow-2xl animate-in fade-in zoom-in-95 duration-200 my-auto max-h-[95vh]"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="px-lg py-md border-b border-outline-variant flex items-center justify-between bg-white/50 flex-shrink-0">
          <div className="flex items-center gap-md">
            <div className="w-10 h-10 bg-error/10 rounded-lg flex items-center justify-center border border-error/20">
              <span className="material-symbols-outlined text-error text-[20px]">gavel</span>
            </div>
            <div>
              <div className="flex items-center gap-2">
                <span className="text-[10px] font-bold text-on-surface-variant uppercase tracking-widest">Event Detail</span>
                <span className="text-[11px] font-bold text-primary font-mono">{eventId}</span>
              </div>
              <h2 className="text-[14px] font-bold text-on-surface uppercase tracking-tight">
                {event ? (TYPE_LABELS[event.violation_type] || event.violation_type.replace(/_/g, " ")) : "Loading..."}
              </h2>
            </div>
          </div>
          <div className="flex items-center gap-2">
            {event && (
              <span
                className={`text-[10px] font-bold px-2.5 py-1 rounded-full uppercase ${
                  event.review_status === "approved"
                    ? "bg-emerald-50 text-emerald-700 border border-emerald-200"
                    : event.review_status === "rejected"
                    ? "bg-red-50 text-red-700 border border-red-200"
                    : "bg-amber-50 text-amber-700 border border-amber-200"
                }`}
              >
                {event.review_status}
              </span>
            )}
            <button
              onClick={onClose}
              className="p-2 bg-white border border-outline-variant rounded-lg text-on-surface-variant hover:text-on-surface hover:bg-surface-container transition-colors"
            >
              <span className="material-symbols-outlined text-[18px]">close</span>
            </button>
          </div>
        </div>

        {loading ? (
          <div className="flex items-center justify-center py-20">
            <span className="material-symbols-outlined text-[28px] text-primary animate-spin">sync</span>
          </div>
        ) : !event ? (
          <div className="flex flex-col items-center justify-center py-20 text-on-surface-variant gap-2">
            <span className="material-symbols-outlined text-[36px] text-outline">error</span>
            <span className="text-[13px] font-semibold">Event not found</span>
          </div>
        ) : (
          <div className="flex-1 overflow-y-auto p-5 flex flex-col gap-5">
            {/* Evidence Image */}
            <div className="bg-slate-950 rounded-xl overflow-hidden border border-outline-variant">
              {evidenceUrl && !evImgError ? (
                <img
                  src={evidenceUrl}
                  alt="Evidence"
                  className="w-full object-contain max-h-[400px]"
                  onError={() => setEvImgError(true)}
                />
              ) : (
                <div className="flex items-center justify-center h-48 text-on-surface-variant text-[12px] flex-col gap-2">
                  <span className="material-symbols-outlined text-[32px] text-outline">image_not_supported</span>
                  <span>Evidence image not available</span>
                </div>
              )}
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
              {/* Plate OCR */}
              <div className="bg-white border border-outline-variant rounded-xl p-4">
                <h3 className="text-[11px] font-bold uppercase text-on-surface mb-3 flex items-center gap-1.5">
                  <span className="material-symbols-outlined text-[16px] text-primary">badge</span>
                  License Plate OCR
                </h3>
                <div className="flex gap-3">
                  <div className="w-24 h-16 bg-slate-100 rounded-lg border border-outline-variant overflow-hidden flex-shrink-0">
                    {plateUrl && !plateImgError ? (
                      <img
                        src={plateUrl}
                        alt="Plate crop"
                        className="w-full h-full object-contain"
                        onError={() => setPlateImgError(true)}
                      />
                    ) : (
                      <div className="flex items-center justify-center h-full text-on-surface-variant text-[9px]">
                        No crop
                      </div>
                    )}
                  </div>
                  <div className="min-w-0">
                    <div className="text-[20px] font-bold font-mono text-on-surface tracking-wider break-all">
                      {event.plate_number}
                    </div>
                    <div className="flex items-center gap-2 mt-1 text-[11px] text-on-surface-variant">
                      <span>Confidence:</span>
                      <span className="font-bold text-on-surface">
                        {event.plate_confidence != null
                          ? `${(event.plate_confidence * 100).toFixed(0)}%`
                          : "—"}
                      </span>
                    </div>
                  </div>
                </div>
              </div>

              {/* Event Details */}
              <div className="bg-white border border-outline-variant rounded-xl p-4">
                <h3 className="text-[11px] font-bold uppercase text-on-surface mb-3 flex items-center gap-1.5">
                  <span className="material-symbols-outlined text-[16px] text-primary">info</span>
                  Event Details
                </h3>
                <div className="flex flex-col gap-2 text-[11px]">
                  <div className="flex justify-between">
                    <span className="text-on-surface-variant">Vehicle</span>
                    <span className="font-semibold capitalize">{event.vehicle_type}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-on-surface-variant">Confidence</span>
                    <span className="font-bold">{(event.confidence * 100).toFixed(0)}%</span>
                  </div>
                  {event.duration_seconds > 0 && (
                    <div className="flex justify-between">
                      <span className="text-on-surface-variant">Duration</span>
                      <span className="font-mono">{event.duration_seconds.toFixed(1)}s</span>
                    </div>
                  )}
                  <div className="flex justify-between">
                    <span className="text-on-surface-variant">Road</span>
                    <span className="font-semibold text-right max-w-[60%]">{event.road_name || "—"}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-on-surface-variant">Source</span>
                    <span className="text-right max-w-[60%] truncate">{event.source?.split("/").pop() || "—"}</span>
                  </div>
                </div>
              </div>
            </div>

            {/* Location */}
            <div className="bg-white border border-outline-variant rounded-xl p-4">
              <h3 className="text-[11px] font-bold uppercase text-on-surface mb-3 flex items-center gap-1.5">
                <span className="material-symbols-outlined text-[16px] text-primary">location_on</span>
                Location
              </h3>
              <div className="flex items-center gap-4 text-[11px] text-on-surface-variant">
                <span>Lat: <span className="font-mono font-semibold text-on-surface">{event.latitude.toFixed(4)}</span></span>
                <span>Lng: <span className="font-mono font-semibold text-on-surface">{event.longitude.toFixed(4)}</span></span>
                <a
                  href={`https://www.google.com/maps?q=${event.latitude},${event.longitude}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="ml-auto flex items-center gap-1 text-primary hover:underline"
                >
                  <span className="material-symbols-outlined text-[14px]">open_in_new</span>
                  Buka Maps
                </a>
              </div>
            </div>

            {/* Pipeline */}
            <div className="bg-white border border-outline-variant rounded-xl p-4">
              <h3 className="text-[11px] font-bold uppercase text-on-surface mb-3 flex items-center gap-1.5">
                <span className="material-symbols-outlined text-[16px] text-primary">donut_large</span>
                Pipeline
              </h3>
              <div className="grid grid-cols-4 gap-2">
                {[
                  { label: "Detected", icon: "radar", done: true },
                  { label: "Frame", icon: "image", done: !!event.evidence_image },
                  { label: "Plate", icon: "badge", done: !!event.plate_crop },
                  { label: "OCR", icon: "text_fields", done: event.plate_number !== "UNKNOWN" },
                ].map((step) => (
                  <div
                    key={step.label}
                    className={`flex flex-col items-center gap-1.5 p-3 rounded-xl border text-center ${
                      step.done
                        ? "bg-emerald-50 border-emerald-200 text-emerald-700"
                        : "bg-slate-50 border-slate-200 text-on-surface-variant"
                    }`}
                  >
                    <span className="material-symbols-outlined text-[18px]">{step.icon}</span>
                    <span className="text-[9px] font-bold uppercase">{step.label}</span>
                  </div>
                ))}
              </div>
            </div>

            {/* Actions */}
            {isPending && (
              <div className="flex gap-3">
                <button
                  onClick={() => handleStatus("approved")}
                  className="flex-1 flex items-center justify-center gap-2 py-2.5 bg-emerald-600 hover:bg-emerald-700 text-white text-[12px] font-bold rounded-xl transition-all"
                >
                  <span className="material-symbols-outlined text-[16px]">check_circle</span>
                  Setujui
                </button>
                <button
                  onClick={() => handleStatus("rejected")}
                  className="flex-1 flex items-center justify-center gap-2 py-2.5 bg-red-500 hover:bg-red-600 text-white text-[12px] font-bold rounded-xl transition-all"
                >
                  <span className="material-symbols-outlined text-[16px]">cancel</span>
                  Tolak
                </button>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
