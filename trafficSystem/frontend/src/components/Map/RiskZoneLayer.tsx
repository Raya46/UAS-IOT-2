import { useState, useEffect } from "react";
import { Source, Layer, Marker, Popup } from "react-map-gl/mapbox";
import axios from "axios";

interface Props {
  visible: boolean;
}

export function RiskZoneLayer({ visible }: Props) {
  const [geojson, setGeojson] = useState<GeoJSON.FeatureCollection | null>(null);
  const [selectedZone, setSelectedZone] = useState<any | null>(null);

  useEffect(() => {
    if (!visible) {
      setSelectedZone(null);
      return;
    }
    axios
      .get(`${import.meta.env.VITE_API_BASE_URL}/api/analytics/risk-zones`)
      .then((r) => setGeojson(r.data));
  }, [visible]);

  if (!visible || !geojson) return null;

  // Custom colors based on risk score
  const getRiskColor = (score: number) => {
    if (score >= 0.8) return "#ef4444"; // Red
    if (score >= 0.5) return "#f97316"; // Orange
    if (score >= 0.2) return "#eab308"; // Yellow
    return "#3b82f6"; // Blue
  };

  const getRiskLevel = (score: number) => {
    if (score >= 0.8) return "Kritis (High)";
    if (score >= 0.5) return "Waspada (Medium)";
    if (score >= 0.2) return "Sedang (Low-Medium)";
    return "Rendah (Low)";
  };

  const features = geojson.features || [];

  return (
    <>
      {/* Background Heatmap Source & Layer for visual density */}
      <Source id="risk-zones" type="geojson" data={geojson}>
        <Layer
          id="risk-zones-heatmap"
          type="heatmap"
          paint={{
            "heatmap-weight": ["get", "risk_score"],
            "heatmap-intensity": ["interpolate", ["linear"], ["zoom"], 8, 2, 14, 12],
            "heatmap-color": [
              "interpolate", ["linear"], ["heatmap-density"],
              0, "rgba(105, 173, 205, 0)",
              0.05, "rgba(105, 173, 205, 0.42)",
              0.2, "rgba(253, 208, 3, 0.58)",
              0.5, "rgba(249, 115, 22, 0.72)",
              0.8, "rgba(225, 29, 72, 0.9)",
            ],
            "heatmap-radius": ["interpolate", ["linear"], ["zoom"], 8, 20, 14, 60],
            "heatmap-opacity": 0.65,
          }}
        />
      </Source>

      {/* Interactive Markers for each risk zone */}
      {features.map((feature: any, idx: number) => {
        const [lng, lat] = feature.geometry.coordinates;
        const props = feature.properties || {};
        const score = props.risk_score || 0;
        const color = getRiskColor(score);

        return (
          <Marker
            key={idx}
            longitude={lng}
            latitude={lat}
            anchor="center"
            onClick={(e) => {
              e.originalEvent.stopPropagation();
              setSelectedZone({
                lng,
                lat,
                ...props
              });
            }}
          >
            {/* Custom glowing marker */}
            <div
              className="relative flex items-center justify-center cursor-pointer transition-all duration-300 hover:scale-110"
              style={{
                width: "40px",
                height: "40px",
              }}
              title={`Zona Rawan — Skor: ${(score * 100).toFixed(0)}%`}
            >
              {/* Outer pulsing circle zone */}
              <div
                className="absolute rounded-full opacity-35 animate-ping"
                style={{
                  width: "100%",
                  height: "100%",
                  backgroundColor: color,
                  animationDuration: "3s",
                }}
              />
              <div
                className="absolute rounded-full opacity-20 animate-pulse"
                style={{
                  width: "80%",
                  height: "80%",
                  backgroundColor: color,
                  border: `1.5px solid ${color}`,
                  animationDuration: "2s",
                }}
              />
              {/* Center shield icon */}
              <div
                className="rounded-full shadow-lg flex items-center justify-center border-2 border-white"
                style={{
                  width: "22px",
                  height: "22px",
                  backgroundColor: color,
                  color: "#ffffff",
                }}
              >
                <span className="material-symbols-outlined text-[12px] font-bold">shield</span>
              </div>
            </div>
          </Marker>
        );
      })}

      {/* Popup showing detailed metrics when a zone is clicked */}
      {selectedZone && (
        <Popup
          longitude={selectedZone.lng}
          latitude={selectedZone.lat}
          anchor="bottom"
          onClose={() => setSelectedZone(null)}
          closeButton={true}
          closeOnClick={false}
          style={{ zIndex: 100 }}
        >
          <div
            style={{
              background: "rgb(var(--color-surface-matte))",
              color: "rgb(var(--color-on-surface))",
              padding: "12px",
              borderRadius: "14px",
              fontSize: "11px",
              fontFamily: "system-ui, -apple-system, sans-serif",
              maxWidth: "260px",
              border: "1px solid rgb(var(--color-outline-variant))",
              boxShadow: "0 10px 25px -5px rgba(0, 0, 0, 0.18), 0 8px 10px -6px rgba(0, 0, 0, 0.12)"
            }}
          >
            {/* Title / Risk Level */}
            <div style={{ display: "flex", alignItems: "center", gap: "8px", borderBottom: "1px solid rgb(var(--color-outline-variant))", paddingBottom: "6px", marginBottom: "8px" }}>
              <span className="material-symbols-outlined" style={{ color: getRiskColor(selectedZone.risk_score), fontSize: "16px" }}>
                shield
              </span>
              <div>
                <div style={{ fontSize: "9px", color: "rgb(var(--color-on-surface-variant))", textTransform: "uppercase", letterSpacing: "0.5px", fontWeight: 600 }}>Tingkat Kerawanan</div>
                <div style={{ fontWeight: 700, fontSize: "12px", color: getRiskColor(selectedZone.risk_score) }}>
                  {getRiskLevel(selectedZone.risk_score)}
                </div>
              </div>
            </div>

            {/* Score & Incidents */}
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "8px", background: "rgb(var(--color-surface-container-low))", padding: "8px", borderRadius: "8px", marginBottom: "8px", border: "1px solid rgb(var(--color-outline-variant))", textAlign: "center" }}>
              <div>
                <div style={{ fontSize: "9px", color: "rgb(var(--color-on-surface-variant))", fontWeight: 500 }}>Risk Score</div>
                <div style={{ fontFamily: "monospace", fontWeight: 700, fontSize: "13px", color: getRiskColor(selectedZone.risk_score) }}>
                  {(selectedZone.risk_score * 100).toFixed(0)}%
                </div>
              </div>
              <div>
                <div style={{ fontSize: "9px", color: "rgb(var(--color-on-surface-variant))", fontWeight: 500 }}>Total Pelanggaran</div>
                <div style={{ fontFamily: "monospace", fontWeight: 700, fontSize: "13px", color: "rgb(var(--color-on-surface))" }}>
                  {selectedZone.incident_count}
                </div>
              </div>
            </div>

            {/* Violations */}
            <div style={{ marginBottom: "8px" }}>
              <div style={{ fontWeight: 600, fontSize: "9px", color: "rgb(var(--color-on-surface-variant))", marginBottom: "4px" }}>Jenis Pelanggaran:</div>
              <div style={{ display: "flex", flexWrap: "wrap", gap: "4px" }}>
                {((selectedZone.violation_types) || []).map((type: string) => (
                  <span
                    key={type}
                    style={{
                      padding: "2px 6px",
                      borderRadius: "4px",
                      background: "rgba(48, 49, 139, 0.08)",
                      border: "1px solid rgba(48, 49, 139, 0.18)",
                      fontSize: "8px",
                      fontFamily: "monospace",
                      color: "rgb(var(--color-primary))",
                      fontWeight: 600
                    }}
                  >
                    {type}
                  </span>
                ))}
              </div>
            </div>

            {/* Peak Hours */}
            {selectedZone.peak_hours && selectedZone.peak_hours.length > 0 && (
              <div>
                <div style={{ fontWeight: 600, fontSize: "9px", color: "rgb(var(--color-on-surface-variant))", marginBottom: "2px" }}>Jam Rawan Tertinggi:</div>
                <div style={{ fontFamily: "monospace", fontSize: "10px", color: "#d97706", fontWeight: 600 }}>
                  {selectedZone.peak_hours.sort((a:number, b:number) => a - b).map((h: number) => `${String(h).padStart(2, '0')}:00`).join(', ')}
                </div>
              </div>
            )}
          </div>
        </Popup>
      )}
    </>
  );
}
