import { Marker } from "react-map-gl/mapbox";
import type { Camera } from "../../types";

interface Props {
  cameras: Camera[];
  onCameraClick: (camera: Camera) => void;
}

export function CameraMarkers({ cameras, onCameraClick }: Props) {
  return (
    <>
      {cameras.map((camera) => (
        <Marker
          key={camera.id}
          longitude={camera.lng}
          latitude={camera.lat}
          anchor="center"
          onClick={(e: any) => {
            e.originalEvent.stopPropagation();
            onCameraClick(camera);
          }}
        >
          <div
            title={camera.name}
            className={`map-marker shadow-lg ${camera.id.startsWith("esp32") ? "esp32" : ""}`}
          >
            <span className="material-symbols-outlined text-[16px]">
              {camera.id.startsWith("esp32") ? "linked_camera" : "videocam"}
            </span>
          </div>
        </Marker>
      ))}
    </>
  );
}
