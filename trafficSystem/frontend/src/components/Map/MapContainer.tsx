import Map, { NavigationControl, ScaleControl } from "react-map-gl/mapbox";
import "mapbox-gl/dist/mapbox-gl.css";

import { CameraMarkers } from "./CameraMarkers";
import { ViolationMarkers } from "./ViolationMarkers";
import { ViolationHeatmapLayer } from "./ViolationHeatmapLayer";
import { RiskZoneLayer } from "./RiskZoneLayer";
import { PlacementLayer } from "./PlacementLayer";
import { EventPredictionOverlay } from "./EventPredictionOverlay";
import { PatrolMarkers } from "./PatrolMarkers";
import type { PatrolVehicle } from "./PatrolMarkers";
import type { PatrolGeneratedViolation, PatrolRuntimePosition } from "./PatrolMarkers";
import type { Camera, Incident } from "../../types";

// Jakarta center
const INITIAL_VIEW = {
  longitude: 106.8456,
  latitude: -6.2088,
  zoom: 12,
};

const MAPBOX_STYLES = {
  light: "mapbox://styles/mapbox/navigation-day-v1",
  dark: "mapbox://styles/mapbox/dark-v11",
} as const;

interface Props {
  cameras: Camera[];
  setSelectedCamera: (camera: Camera | null) => void;
  activeIncidents: Incident[];
  onIncidentClick: (incident: Incident) => void;
  showHeatmap: boolean;
  heatmapFilters: any;
  showRiskZones: boolean;
  showPlacements: boolean;
  placementType: "camera_etle" | "officer";
  eventPredictions: any[];
  showCameras: boolean;
  showIncidents: boolean;
  showPatrol?: boolean;
  onPatrolClick?: (patrol: PatrolVehicle) => void;
  onPatrolPositionsUpdate?: (positions: Record<string, PatrolRuntimePosition>) => void;
  onRandomPatrolViolation?: (violation: PatrolGeneratedViolation) => void;
  theme: "light" | "dark";
}

export function MapContainer({
  cameras,
  setSelectedCamera,
  activeIncidents,
  onIncidentClick,
  showHeatmap,
  heatmapFilters,
  showRiskZones,
  showPlacements,
  placementType,
  eventPredictions,
  showCameras,
  showIncidents,
  showPatrol,
  onPatrolClick,
  onPatrolPositionsUpdate,
  onRandomPatrolViolation,
  theme,
}: Props) {
  return (
    <div
      className={theme === "dark" ? "mapbox-theme-dark" : "mapbox-theme-light"}
      style={{ width: "100%", height: "100%", position: "relative" }}
    >
      <Map
        mapboxAccessToken={import.meta.env.VITE_MAPBOX_TOKEN}
        initialViewState={INITIAL_VIEW}
        style={{ width: "100%", height: "100%" }}
        mapStyle={MAPBOX_STYLES[theme]}
      >
        <NavigationControl position="top-right" />
        <ScaleControl position="bottom-right" />

        {/* Layer 2: Marker kamera CCTV */}
        {showCameras && (
          <CameraMarkers
            cameras={cameras}
            onCameraClick={setSelectedCamera}
          />
        )}

        {/* Layer 3: Marker pelanggaran/insiden real-time */}
        {showIncidents && (
          <ViolationMarkers 
            violations={activeIncidents as any} 
            onViolationClick={onIncidentClick as any} 
          />
        )}

        {/* Heatmap Overlays */}
        <ViolationHeatmapLayer filters={heatmapFilters} visible={showHeatmap} />
        <RiskZoneLayer visible={showRiskZones} />

        {/* Placement Simulator Overlays */}
        <PlacementLayer type={placementType} visible={showPlacements} />

        {/* Event Impact Overlays */}
        <EventPredictionOverlay predictions={eventPredictions} />

        {/* Patrol Simulation */}
        {showPatrol && onPatrolClick && (
          <PatrolMarkers
            onPatrolClick={onPatrolClick}
            onPatrolPositionsUpdate={onPatrolPositionsUpdate}
            onRandomViolation={onRandomPatrolViolation}
          />
        )}
      </Map>
    </div>
  );
}
