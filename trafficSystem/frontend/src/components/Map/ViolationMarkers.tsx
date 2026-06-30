import { Marker } from "react-map-gl/mapbox";
import type { Incident } from "../../types";

/**
 * Static warning markers placed at Jakarta locations with evidence snapshots.
 * Clicking a marker opens the existing IncidentDetailModal.
 */
interface WarningPoint {
  id: string;
  camera_id: string;
  label: string;
  location: string;
  type: Incident["type"];
  severity: "low" | "medium" | "high";
  lng: number;
  lat: number;
  snapshot: string;
  description: string;
  plate_number?: string;
}

const STATIC_WARNINGS: WarningPoint[] = [
  {
    id: "20001001",
    camera_id: "cam-sudirman-01",
    label: "Kemacetan Padat",
    location: "Jl. Sudirman — Semanggi",
    type: "congestion",
    severity: "high",
    lng: 106.8131,
    lat: -6.2246,
    snapshot: "/snapshots/kemacetan.png",
    description: "Deteksi tanda Kemacetan Padat di lokasi Jl. Sudirman — Semanggi. Tingkat akurasi sistem mencapai 92% dengan total sinyal masuk sebanyak 4.",
  },
  {
    id: "20001002",
    camera_id: "cam-gatot-02",
    label: "Kemacetan Pagi",
    location: "Jl. Gatot Subroto",
    type: "congestion",
    severity: "high",
    lng: 106.8275,
    lat: -6.2350,
    snapshot: "/snapshots/kemacetan_2.png",
    description: "Deteksi tanda Kemacetan Pagi di lokasi Jl. Gatot Subroto. Tingkat akurasi sistem mencapai 89% dengan total sinyal masuk sebanyak 3.",
  },
  {
    id: "20001003",
    camera_id: "cam-rasuna-03",
    label: "Kemacetan Sore",
    location: "Jl. HR Rasuna Said",
    type: "congestion",
    severity: "medium",
    lng: 106.8370,
    lat: -6.2180,
    snapshot: "/snapshots/kemacetan_3.png",
    description: "Deteksi tanda Kemacetan Sore di lokasi Jl. HR Rasuna Said. Tingkat akurasi sistem mencapai 87% dengan total sinyal masuk sebanyak 3.",
  },
  {
    id: "20001004",
    camera_id: "cam-casablanca-04",
    label: "Arus Padat",
    location: "Jl. Casablanca",
    type: "congestion",
    severity: "medium",
    lng: 106.8430,
    lat: -6.2290,
    snapshot: "/snapshots/kemacetan_4.png",
    description: "Deteksi tanda Arus Padat di lokasi Jl. Casablanca. Tingkat akurasi sistem mencapai 85% dengan total sinyal masuk sebanyak 2.",
  },
  {
    id: "20001005",
    camera_id: "cam-haryono-05",
    label: "Kemacetan Total",
    location: "Jl. MT Haryono",
    type: "congestion",
    severity: "high",
    lng: 106.8510,
    lat: -6.2420,
    snapshot: "/snapshots/kemacetan_5.png",
    description: "Deteksi tanda Kemacetan Total di lokasi Jl. MT Haryono. Tingkat akurasi sistem mencapai 94% dengan total sinyal masuk sebanyak 6.",
  },
  {
    id: "10000000",
    camera_id: "cam-006",
    label: "Parkir Liar",
    location: "Tanah Abang",
    type: "illegal_parking",
    severity: "high",
    lng: 106.8230,
    lat: -6.1950,
    snapshot: "/snapshots/parkir_liar.png",
    description: "Deteksi tanda Parkir Liar di lokasi Tanah Abang. Tingkat akurasi sistem mencapai 94% dengan total sinyal masuk sebanyak 5.",
    plate_number: "B 9442 GOX",
  },
  {
    id: "10000001",
    camera_id: "cam-007",
    label: "Parkir Liar",
    location: "Jl. Wahid Hasyim",
    type: "illegal_parking",
    severity: "medium",
    lng: 106.8180,
    lat: -6.1870,
    snapshot: "/snapshots/parkir_liar_2.png",
    description: "Deteksi tanda Parkir Liar di lokasi Jl. Wahid Hasyim. Tingkat akurasi sistem mencapai 88% dengan total sinyal masuk sebanyak 3.",
    plate_number: "B 1234 KJP",
  },
  {
    id: "10000002",
    camera_id: "cam-008",
    label: "Lawan Arah",
    location: "Jl. Kebon Sirih",
    type: "wrong_way",
    severity: "high",
    lng: 106.8320,
    lat: -6.1860,
    snapshot: "/snapshots/lawan_arah.png",
    description: "Deteksi tanda Lawan Arah di lokasi Jl. Kebon Sirih. Tingkat akurasi sistem mencapai 91% dengan total sinyal masuk sebanyak 4.",
  },
  {
    id: "10000003",
    camera_id: "cam-009",
    label: "Busway Violation",
    location: "Jl. Bendungan Hilir",
    type: "busway_violation",
    severity: "high",
    lng: 106.8100,
    lat: -6.2100,
    snapshot: "/snapshots/busway_violation_2.png",
    description: "Deteksi tanda Pelanggaran Jalur Busway di lokasi Jl. Bendungan Hilir. Tingkat akurasi sistem mencapai 96% dengan total sinyal masuk sebanyak 7.",
    plate_number: "B 7721 TJQ",
  },
];

/** Convert static warning to Incident object for the modal */
function toIncident(w: WarningPoint): Incident {
  const confMap: Record<string, number> = {
    "20001001": 0.92, "20001002": 0.89, "20001003": 0.87,
    "20001004": 0.85, "20001005": 0.94, "10000000": 0.94,
    "10000001": 0.88, "10000002": 0.91, "10000003": 0.96,
  };
  const sourceMap: Record<string, number> = {
    "20001001": 4, "20001002": 3, "20001003": 3,
    "20001004": 2, "20001005": 6, "10000000": 5,
    "10000001": 3, "10000002": 4, "10000003": 7,
  };
  return {
    id: w.id,
    camera_id: w.camera_id,
    type: w.type,
    lat: w.lat,
    lng: w.lng,
    severity: w.severity,
    confidence_score: confMap[w.id] ?? 0.90,
    source_count: sourceMap[w.id] ?? 3,
    status: "confirmed",
    timestamp: new Date().toISOString(),
    snapshot_url: w.snapshot,
    description: w.description,
    plate_number: w.plate_number,
  };
}

const SEVERITY_COLORS: Record<string, string> = {
  high: "#d32f2f",
  medium: "#f57c00",
  low: "#fbc02d",
};

const TYPE_ICONS: Record<string, string> = {
  congestion: "traffic",
  illegal_parking: "local_parking",
  wrong_way: "wrong_location",
  busway_violation: "directions_bus",
  hazard_lights: "warning",
  red_light_violation: "traffic",
  illegal_u_turn: "u_turn_right",
  unsafe_lane_change: "swap_horiz",
  shoulder_violation: "alt_route",
};

interface Props {
  violations: Incident[];
  onViolationClick?: (violation: Incident) => void;
}

export function ViolationMarkers({ violations, onViolationClick }: Props) {
  const staticWarnings = STATIC_WARNINGS.filter((warning) => {
    return !violations.some((violation) => {
      const sameSnapshot = violation.snapshot_url === warning.snapshot;
      const sameLocation =
        Math.abs(violation.lat - warning.lat) < 0.00001 &&
        Math.abs(violation.lng - warning.lng) < 0.00001;
      return violation.type === warning.type && (sameSnapshot || sameLocation);
    });
  });

  return (
    <>
      {/* Dynamic violations from backend */}
      {violations.map((v) => (
        <Marker
          key={v.id}
          longitude={v.lng}
          latitude={v.lat}
          anchor="center"
          onClick={(e: any) => {
            e.originalEvent.stopPropagation();
            onViolationClick?.(v);
          }}
        >
          <div
            className="cursor-pointer"
            style={{
              width: 28,
              height: 28,
              borderRadius: 8,
              background: SEVERITY_COLORS[v.severity] || "#d32f2f",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              border: "2px solid white",
              boxShadow: `0 0 0 1px ${SEVERITY_COLORS[v.severity] || "#d32f2f"}30, 0 2px 8px rgba(0,0,0,0.3)`,
              animation: "warningPulse 2s infinite",
            }}
            title={`${v.type} — ${v.severity}`}
          >
            <span
              className="material-symbols-outlined"
              style={{ color: "white", fontSize: 16 }}
            >
              {TYPE_ICONS[v.type] || "warning"}
            </span>
          </div>
        </Marker>
      ))}

      {/* Static warning markers — clicking opens IncidentDetailModal */}
      {staticWarnings.map((w) => (
        <Marker
          key={w.id}
          longitude={w.lng}
          latitude={w.lat}
          anchor="bottom"
          onClick={(e: any) => {
            e.originalEvent.stopPropagation();
            onViolationClick?.(toIncident(w));
          }}
        >
          <div
            className="cursor-pointer"
            style={{
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              filter: "drop-shadow(0 1px 3px rgba(0,0,0,0.35))",
            }}
          >
            {/* Icon circle */}
            <div
              style={{
                width: 32,
                height: 32,
                borderRadius: 8,
                background: SEVERITY_COLORS[w.severity],
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                border: "2px solid white",
                boxShadow: `0 0 0 1px ${SEVERITY_COLORS[w.severity]}40`,
                animation: "warningPulse 2.5s infinite",
              }}
            >
              <span
                className="material-symbols-outlined"
                style={{ color: "white", fontSize: 18 }}
              >
                {TYPE_ICONS[w.type] || "warning"}
              </span>
            </div>
            {/* Label pill */}
            <div
              style={{
                marginTop: 3,
                background: SEVERITY_COLORS[w.severity],
                color: "white",
                fontSize: 8,
                fontWeight: 600,
                padding: "1px 6px",
                borderRadius: 3,
                whiteSpace: "nowrap",
                letterSpacing: "0.02em",
              }}
            >
              {w.label}
            </div>
            {/* Pointer triangle */}
            <div
              style={{
                width: 0,
                height: 0,
                borderLeft: "5px solid transparent",
                borderRight: "5px solid transparent",
                borderTop: `5px solid ${SEVERITY_COLORS[w.severity]}`,
              }}
            />
          </div>
        </Marker>
      ))}

      <style>{`
        @keyframes warningPulse {
          0%   { box-shadow: 0 0 0 0 rgba(211,47,47,0.5); }
          50%  { box-shadow: 0 0 0 6px rgba(211,47,47,0); }
          100% { box-shadow: 0 0 0 0 rgba(211,47,47,0); }
        }
      `}</style>
    </>
  );
}
