import { useState } from "react";
import { Marker, Popup } from "react-map-gl/mapbox";
import { useQuery } from "@tanstack/react-query";
import axios from "axios";

interface Placement {
  location: { lat: number; lng: number };
  recommendation_type: "camera_etle" | "officer";
  priority_rank: number;
  risk_score: number;
  violation_types: string[];
  coverage_radius_m: number;
  rationale: string;
  peak_hours: number[];
}

interface Props {
  type: "camera_etle" | "officer";
  visible: boolean;
}

export function PlacementLayer({ type, visible }: Props) {
  const [selected, setSelected] = useState<Placement | null>(null);

  const { data } = useQuery({
    queryKey: ["placements", type],
    queryFn: () =>
      axios
        .get(`${import.meta.env.VITE_API_BASE_URL}/api/simulator/placements?type=${type}&top_n=15`)
        .then((r) => r.data.recommendations as Placement[]),
    enabled: visible,
  });

  if (!visible) return null;

  const icon = type === "camera_etle" ? "photo_camera" : "groups";
  const color = type === "camera_etle" ? "#69adcd" : "#fdd003";
  const textColor = "rgb(var(--color-primary))";

  return (
    <>
      {(data ?? []).map((placement, idx) => (
        <Marker
          key={idx}
          longitude={placement.location.lng}
          latitude={placement.location.lat}
          anchor="center"
          onClick={(e: any) => {
            e.originalEvent.stopPropagation();
            setSelected(placement);
          }}
        >
          <div
            style={{
              background: "#ffffff",
              border: `2px solid ${color}`,
              borderRadius: "50%",
              width: 32, height: 32,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              fontSize: 14, cursor: "pointer",
              color: textColor,
              boxShadow: `0 4px 10px rgba(0, 0, 0, 0.05), 0 0 4px ${color}44`,
            }}
            title={`Prioritas #${placement.priority_rank} — Risk ${Math.round(placement.risk_score * 100)}%`}
          >
            <span className="material-symbols-outlined" style={{ fontSize: 17 }}>{icon}</span>
          </div>
        </Marker>
      ))}

      {selected && (
        <Popup
          longitude={selected.location.lng}
          latitude={selected.location.lat}
          anchor="bottom"
          onClose={() => setSelected(null)}
          style={{ maxWidth: 280 }}
        >
          <div style={{ background: "rgb(var(--color-surface-matte))", color: "rgb(var(--color-on-surface))", padding: 12, borderRadius: 12, fontSize: 12, border: "1px solid rgb(var(--color-outline-variant))", boxShadow: "0 10px 25px -5px rgba(0, 0, 0, 0.18), 0 8px 10px -6px rgba(0, 0, 0, 0.12)" }}>
            <div style={{ color: textColor, fontWeight: 700, marginBottom: 6, display: "flex", alignItems: "center", gap: 4 }}>
              <span className="material-symbols-outlined" style={{ fontSize: 15 }}>{icon}</span>
              Rekomendasi #{selected.priority_rank} — {type === "camera_etle" ? "E-TLE" : "Petugas"}
            </div>
            <div style={{ color: "rgb(var(--color-on-surface-variant))", marginBottom: 4, fontSize: 11, fontWeight: 500 }}>
              Risk score: <span style={{ color: textColor, fontWeight: 700 }}>{Math.round(selected.risk_score * 100)}%</span>
            </div>
            <div style={{ color: "rgb(var(--color-on-surface-variant))", fontSize: 11, marginBottom: 6, lineHeight: 1.4 }}>
              {selected.rationale}
            </div>
            <div style={{ color: "rgb(var(--color-on-surface-variant))", fontSize: 10, fontWeight: 500 }}>
              Coverage: {selected.coverage_radius_m}m radius
            </div>
          </div>
        </Popup>
      )}
    </>
  );
}
