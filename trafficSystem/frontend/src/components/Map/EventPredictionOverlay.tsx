import { Marker, Popup } from "react-map-gl/mapbox";
import { useState } from "react";
import type { EventPrediction } from "../../types";

const CONGESTION_COLORS = {
  critical: "#FF0000",
  high: "#FF4500",
  medium: "#FFA500",
};

const ZONE_LABELS: Record<string, string> = {
  red: "MERAH",
  orange: "ORANYE",
  yellow: "KUNING",
  green: "HIJAU",
};

interface Props {
  predictions: EventPrediction[];
}

export function EventPredictionOverlay({ predictions }: Props) {
  const [selected, setSelected] = useState<any>(null);

  if (!predictions.length) return null;

  return (
    <>
      {predictions.flatMap((pred) =>
        (pred.affected_segments ?? []).map((seg: any, idx: number) => (
          <Marker
            key={`${pred.event_id}-${idx}`}
            longitude={seg.lng}
            latitude={seg.lat}
            anchor="center"
            onClick={(e: any) => {
              e.originalEvent.stopPropagation();
              setSelected({ pred, seg });
            }}
          >
            <div
              style={{
                width: 20, height: 20, borderRadius: "50%",
                background: (CONGESTION_COLORS[seg.congestion_level as keyof typeof CONGESTION_COLORS] || "#FFA500") + "44",
                border: `2px solid ${CONGESTION_COLORS[seg.congestion_level as keyof typeof CONGESTION_COLORS] || "#FFA500"}`,
                animation: "pulse 2s infinite",
                cursor: "pointer",
              }}
            />
          </Marker>
        ))
      )}

      {selected && (
        <Popup
          longitude={selected.seg.lng}
          latitude={selected.seg.lat}
          anchor="bottom"
          onClose={() => setSelected(null)}
          maxWidth="260px"
        >
          <div style={{ background: "rgb(var(--color-surface-matte))", color: "rgb(var(--color-on-surface))", padding: 12, borderRadius: 12, fontSize: 11, border: "1px solid rgb(var(--color-outline-variant))", boxShadow: "0 10px 25px -5px rgba(0, 0, 0, 0.18), 0 8px 10px -6px rgba(0, 0, 0, 0.12)" }}>
            <div style={{ color: CONGESTION_COLORS[selected.seg.congestion_level as keyof typeof CONGESTION_COLORS] || "#FFA500", fontWeight: 700, marginBottom: 4, display: "flex", alignItems: "center", gap: 4 }}>
              <span className="material-symbols-outlined" style={{ fontSize: 15 }}>warning</span>
              {selected.seg.name}
            </div>
            <div style={{ color: "rgb(var(--color-on-surface-variant))", marginBottom: 4, fontWeight: 500 }}>
              Dampak dari: <span style={{ fontWeight: 600, color: "rgb(var(--color-on-surface))" }}>{selected.pred.event_name}</span>
            </div>
            <div style={{ color: "rgb(var(--color-on-surface-variant))", fontSize: 10 }}>
              Level: <span style={{ fontWeight: 600 }}>{selected.seg.congestion_level.toUpperCase()}</span> · {selected.seg.distance_km} km dari venue
            </div>
            {selected.pred.crowd_zone && (
              <div style={{ color: "rgb(var(--color-on-surface))", fontSize: 10, marginTop: 6, display: "flex", justifyContent: "space-between", gap: 8 }}>
                <span>Zona {ZONE_LABELS[selected.pred.crowd_zone] || selected.pred.crowd_zone}</span>
                <span style={{ fontWeight: 700 }}>{selected.pred.officer_min}-{selected.pred.officer_max} petugas</span>
              </div>
            )}
            {selected.pred.estimated_crowd && (
              <div style={{ color: "rgb(var(--color-on-surface-variant))", fontSize: 10, marginTop: 2 }}>
                Estimasi massa: <span style={{ fontWeight: 700, color: "rgb(var(--color-on-surface))" }}>~{selected.pred.estimated_crowd.toLocaleString()} orang</span>
              </div>
            )}
          </div>
        </Popup>
      )}
    </>
  );
}
