import { useState, useEffect } from "react";
import { Source, Layer } from "react-map-gl/mapbox";
import axios from "axios";

interface HeatmapFilters {
  days: number;
  hourFrom: number;
  hourTo: number;
  dayOfWeek?: number;
  violationType?: string;
}

interface Props {
  filters: HeatmapFilters;
  visible: boolean;
}

export function ViolationHeatmapLayer({ filters, visible }: Props) {
  const [geojson, setGeojson] = useState<GeoJSON.FeatureCollection | null>(null);

  useEffect(() => {
    if (!visible) return;
    const params = new URLSearchParams({
      days: String(filters.days),
      hour_from: String(filters.hourFrom),
      hour_to: String(filters.hourTo),
    });
    if (filters.dayOfWeek !== undefined) params.set("day_of_week", String(filters.dayOfWeek));
    if (filters.violationType) params.set("violation_type", filters.violationType);

    axios
      .get(`${import.meta.env.VITE_API_BASE_URL}/api/analytics/heatmap?${params}`)
      .then((r) => setGeojson(r.data));
  }, [filters, visible]);

  if (!visible || !geojson) return null;

  return (
    <Source id="violation-heatmap" type="geojson" data={geojson}>
      <Layer
        id="violation-heatmap-layer"
        type="heatmap"
        paint={{
          "heatmap-weight": ["get", "weight"],
          "heatmap-intensity": ["interpolate", ["linear"], ["zoom"], 8, 1, 14, 5],
          "heatmap-color": [
            "interpolate", ["linear"], ["heatmap-density"],
            0, "rgba(0, 220, 255, 0)",
            0.1, "rgba(0, 200, 255, 0.5)",
            0.3, "rgb(0, 255, 100)",
            0.5, "rgb(255, 200, 0)",
            0.8, "rgb(255, 100, 0)",
            1, "rgb(255, 0, 0)",
          ],
          "heatmap-radius": ["interpolate", ["linear"], ["zoom"], 8, 15, 14, 40],
          "heatmap-opacity": 0.85,
        }}
      />
    </Source>
  );
}
