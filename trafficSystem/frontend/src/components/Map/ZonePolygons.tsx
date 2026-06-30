import { Source, Layer } from "react-map-gl/mapbox";
import type { Zone } from "../../types";

// Warna per tipe zona
const ZONE_COLORS: Record<Zone["type"], string> = {
  illegal_parking: "#fdd003",
  busway_corridor: "#69adcd",
  event_impact: "#30318b",
};

interface Props {
  zones: Zone[];
}

export function ZonePolygons({ zones }: Props) {
  return (
    <>
      {zones.map((zone) => {
        const geojson: any = {
          type: "Feature",
          properties: { name: zone.name },
          geometry: {
            type: "Polygon",
            coordinates: [zone.coordinates],
          },
        };

        return (
          <Source key={zone.id} id={zone.id} type="geojson" data={geojson}>
            {/* Fill transparan */}
            <Layer
              id={`${zone.id}-fill`}
              type="fill"
              paint={{
                "fill-color": ZONE_COLORS[zone.type],
                "fill-opacity": 0.15,
              }}
            />
            {/* Border zona */}
            <Layer
              id={`${zone.id}-border`}
              type="line"
              paint={{
                "line-color": ZONE_COLORS[zone.type],
                "line-width": 2,
                "line-dasharray": [2, 1],
              }}
            />
          </Source>
        );
      })}
    </>
  );
}
