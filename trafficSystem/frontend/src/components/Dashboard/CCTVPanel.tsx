import { useCallback, useEffect, useRef, useState } from "react";
import { getCctvCameras, resolveCctvStream, getWebSocketUrl } from "../../services/api";

interface CctvCamera {
  name: string;
  url: string;
  type: string;
}

interface Detection {
  track_id: number;
  class_name: string;
  confidence: number;
  bbox: number[];
  is_stopped: boolean;
  stationary_seconds: number;
  violation: string | null;
}

interface TrafficInfo {
  vehicle_count: number;
  stopped_count: number;
  stopped_ratio: number;
  level: string;
  average_speed?: number;
  dominant_direction?: string;
}

interface LiveEvent {
  event_id: string;
  timestamp: string;
  violation_type: string;
  track_id: number;
  vehicle_type: string;
  plate_number: string;
  confidence: number;
}

type ConnectionStatus = "idle" | "connecting" | "connected" | "error" | "disconnected";

const LOCATION_LABELS: Record<string, string> = {
  "Bendungan Hilir": "Bendungan Hilir",
  GBK: "Gelora Bung Karno",
  "GBK Jl": "GBK Asia Afrika",
  "Tanjung Duren": "Tanjung Duren",
  Tomang: "Tomang",
  "Jati Pulo": "Jati Pulo",
  Kemanggisan: "Kemanggisan",
  Menteng: "Menteng",
  "Pasar Manggis": "Pasar Manggis",
  Senayan: "Senayan",
  "Kuningan Barat": "Kuningan Barat",
  Cikoko: "Cikoko",
  "Cengkareng Barat": "Cengkareng Barat",
  "Manggarai Pintu Air": "Manggarai Pintu Air",
};

export function CCTVPanel() {
  const [cameras, setCameras] = useState<CctvCamera[]>([]);
  const [loading, setLoading] = useState(true);
  const [groups, setGroups] = useState<Record<string, CctvCamera[]>>({});

  const [selectedCamera, setSelectedCamera] = useState<CctvCamera | null>(null);
  const [connectionStatus, setConnectionStatus] = useState<ConnectionStatus>("idle");
  const [isFullscreen, setIsFullscreen] = useState(false);

  const displayCanvasRef = useRef<HTMLCanvasElement>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<number | null>(null);

  const [serverFps, setServerFps] = useState(0);
  const [frameCount, setFrameCount] = useState(0);
  const [sessionDuration, setSessionDuration] = useState(0);
  const [detections, setDetections] = useState<Detection[]>([]);
  const [traffic, setTraffic] = useState<TrafficInfo>({
    vehicle_count: 0, stopped_count: 0, stopped_ratio: 0, level: "LOW",
  });
  const [liveEvents, setLiveEvents] = useState<LiveEvent[]>([]);
  const [selectedLocation, setSelectedLocation] = useState<string>("");
  const [cameraSearch, setCameraSearch] = useState("");

  useEffect(() => {
    getCctvCameras()
      .then((list) => {
        setCameras(list);
        const g: Record<string, CctvCamera[]> = {};
        for (const cam of list) {
          const nameParts = cam.name.split(/\s+\d+$/);
          const groupKey = nameParts[0];
          if (!g[groupKey]) g[groupKey] = [];
          g[groupKey].push(cam);
        }
        setGroups(g);
      })
      .catch(console.error)
      .finally(() => setLoading(false));
  }, []);

  const renderBinaryFrame = useCallback((arrayBuffer: ArrayBuffer) => {
    const canvas = displayCanvasRef.current;
    if (!canvas) return;
    const blob = new Blob([arrayBuffer], { type: "image/jpeg" });
    createImageBitmap(blob)
      .then((imageBitmap) => {
        const ctx = canvas.getContext("2d");
        if (ctx) {
          if (canvas.width !== imageBitmap.width || canvas.height !== imageBitmap.height) {
            canvas.width = imageBitmap.width;
            canvas.height = imageBitmap.height;
          }
          ctx.drawImage(imageBitmap, 0, 0);
        }
        imageBitmap.close();
      })
      .catch(() => {});
  }, []);

  const disconnectCamera = useCallback(() => {
    if (reconnectTimeoutRef.current) clearTimeout(reconnectTimeoutRef.current);
    if (wsRef.current) {
      try { wsRef.current.send(JSON.stringify({ type: "stop" })); } catch {}
      wsRef.current.close();
      wsRef.current = null;
    }
    setConnectionStatus("idle");
    setSelectedCamera(null);
    setDetections([]);
    setFrameCount(0);
    setServerFps(0);
    setSessionDuration(0);
    setLiveEvents([]);
  }, []);

  const resolveAndConnect = useCallback(async (cam: CctvCamera) => {
    setSelectedCamera(cam);
    setConnectionStatus("connecting");
    setDetections([]);
    setTraffic({ vehicle_count: 0, stopped_count: 0, stopped_ratio: 0, level: "LOW" });
    setLiveEvents([]);

    try {
      const { resolved_url } = await resolveCctvStream(cam.url);
      const wsUrl = getWebSocketUrl();
      const ws = new WebSocket(wsUrl);
      ws.binaryType = "arraybuffer";
      wsRef.current = ws;

      ws.onopen = () => {
        ws.send(JSON.stringify({
          type: "config",
          mode: "stream",
          stream_url: resolved_url,
          jpeg_quality: 80,
          resize_width: 960,
          source_label: cam.name.replace(/\s+/g, "_").toLowerCase(),
        }));
      };

      ws.onmessage = (event) => {
        if (event.data instanceof ArrayBuffer) {
          renderBinaryFrame(event.data);
          return;
        }
        try {
          const data = JSON.parse(event.data);
          if (data.type === "connected") {
            setConnectionStatus("connected");
          } else if (data.type === "stream_started") {
          } else if (data.type === "frame_result") {
            setServerFps(data.fps);
            setFrameCount(data.frame_count);
            setSessionDuration(data.session_duration);
            setDetections(data.detections);
            setTraffic(data.traffic);
            if (data.new_events?.length > 0) {
              setLiveEvents((prev) => [...data.new_events, ...prev].slice(0, 50));
            }
          } else if (data.type === "error") {
            console.warn("[CCTV] Error:", data.message);
          }
        } catch {}
      };

      ws.onerror = () => {
        setConnectionStatus("error");
      };

      ws.onclose = () => {
        setConnectionStatus("disconnected");
        wsRef.current = null;
        if (selectedCamera) {
          reconnectTimeoutRef.current = window.setTimeout(() => {
            resolveAndConnect(cam);
          }, 3000);
        }
      };
    } catch {
      setConnectionStatus("error");
    }
  }, [renderBinaryFrame, selectedCamera]);

  useEffect(() => {
    return () => {
      if (reconnectTimeoutRef.current) clearTimeout(reconnectTimeoutRef.current);
      if (wsRef.current) {
        try { wsRef.current.send(JSON.stringify({ type: "stop" })); } catch {}
        wsRef.current.close();
      }
    };
  }, []);

  const isStreaming = connectionStatus === "connected" || connectionStatus === "connecting";

  const trafficLevelColor = (level: string) => {
    switch (level) {
      case "SEVERE": return "text-red-600";
      case "HIGH": return "text-orange-600";
      case "MEDIUM": return "text-yellow-600";
      default: return "text-emerald-600";
    }
  };

  const groupKeys = Object.keys(groups).sort();
  const normalizedCameraSearch = cameraSearch.trim().toLowerCase();
  const filteredGroups = Object.fromEntries(
    Object.entries(groups).map(([groupKey, groupCameras]) => [
      groupKey,
      normalizedCameraSearch
        ? groupCameras.filter((cam) => {
            const haystack = [cam.name, cam.type, cam.url, groupKey].join(" ").toLowerCase();
            return haystack.includes(normalizedCameraSearch);
          })
        : groupCameras,
    ])
  );
  const filteredGroupKeys = (selectedLocation
    ? groupKeys.filter((k) => k === selectedLocation)
    : groupKeys).filter((k) => filteredGroups[k]?.length > 0);
  const filteredCameraCount = filteredGroupKeys.reduce((count, groupKey) => count + (filteredGroups[groupKey]?.length || 0), 0);

  return (
    <div className={`flex-1 flex flex-col h-full overflow-hidden ${isFullscreen ? "fixed inset-0 z-[70] bg-white" : ""}`}>
      {!isFullscreen && (
        <div className="px-4 py-3 border-b border-outline-variant flex items-center justify-between flex-shrink-0">
          <div className="flex items-center gap-2">
            <span className="material-symbols-outlined text-primary text-[20px]">settings_remote</span>
            <h2 className="text-[14px] font-bold uppercase tracking-tight text-on-surface">CCTV Traffic Monitoring</h2>
          </div>
          <div className="flex items-center gap-3">
            {selectedCamera && (
              <span className={`flex items-center gap-1.5 text-[10px] font-semibold ${
                connectionStatus === "connected" ? "text-emerald-600" : "text-red-600"
              }`}>
                <span className={`w-1.5 h-1.5 rounded-full ${
                  connectionStatus === "connected" ? "bg-emerald-500 animate-pulse" : "bg-red-500"
                }`} />
                {connectionStatus === "connected" ? "Connected" : connectionStatus === "connecting" ? "Connecting..." : "Offline"}
              </span>
            )}
          </div>
        </div>
      )}

      {selectedCamera && isStreaming ? (
        <div className="flex-1 flex flex-col overflow-hidden">
          <div className={`px-4 py-2 flex items-center justify-between ${isFullscreen ? "hidden" : ""}`}>
            <div className="flex items-center gap-2">
              <span className="material-symbols-outlined text-[16px] text-primary">videocam</span>
              <span className="text-[12px] font-semibold text-on-surface">{selectedCamera.name}</span>
              <span className="text-[9px] text-on-surface-variant font-mono bg-surface-container px-1.5 py-0.5 rounded">{connectionStatus}</span>
            </div>
            <div className="flex items-center gap-2">
              <button onClick={() => setIsFullscreen(!isFullscreen)}
                className="p-1.5 bg-white border border-outline-variant rounded-lg text-on-surface-variant hover:text-on-surface transition-colors">
                <span className="material-symbols-outlined text-[16px]">{isFullscreen ? "fullscreen_exit" : "fullscreen"}</span>
              </button>
              <button onClick={disconnectCamera}
                className="px-3 py-1.5 bg-red-50 text-red-600 border border-red-200 rounded-lg text-[10px] font-bold transition-colors hover:bg-red-100">
                Disconnect
              </button>
            </div>
          </div>

          <div className={`flex-1 flex ${isFullscreen ? "" : "lg:flex-row"} flex-col overflow-hidden`}>
            <div className={`relative bg-slate-950 flex items-center justify-center min-h-[240px] ${isFullscreen ? "flex-1" : "lg:flex-1"}`}>
              {connectionStatus === "connecting" ? (
                <div className="flex items-center gap-2">
                  <span className="material-symbols-outlined text-[20px] text-emerald-400 animate-spin">sync</span>
                  <span className="text-[12px] text-white font-medium">Connecting to camera stream...</span>
                </div>
              ) : (
                <canvas ref={displayCanvasRef} className="w-full h-full object-contain" />
              )}
              {connectionStatus === "connected" && (
                <>
                  <div className="absolute top-2 left-2 flex items-center gap-2 bg-black/60 backdrop-blur-sm px-2.5 py-1.5 rounded-lg">
                    <div className="w-2 h-2 bg-red-500 rounded-full animate-pulse" />
                    <span className="text-[10px] font-bold text-white">LIVE</span>
                    <span className="text-[9px] text-slate-300 font-mono">
                      {Math.floor(sessionDuration / 60)}:{String(Math.floor(sessionDuration % 60)).padStart(2, "0")}
                    </span>
                  </div>
                  <div className="absolute top-2 right-2 flex items-center gap-2 bg-black/60 backdrop-blur-sm px-2.5 py-1.5 rounded-lg">
                    <span className="flex items-center gap-1 text-[10px] text-white font-mono">
                      <span className="material-symbols-outlined text-[12px] text-emerald-400">speed</span>
                      {serverFps} FPS
                    </span>
                    <span className="text-[9px] text-slate-400">#{frameCount}</span>
                  </div>
                </>
              )}
            </div>

            <div className={`flex flex-col gap-3 overflow-y-auto ${isFullscreen ? "w-80 flex-shrink-0 border-l border-outline-variant p-4" : "p-4 lg:w-80 lg:border-l lg:border-outline-variant"}`}>
              <div>
                <h3 className="text-[10px] font-bold uppercase text-on-surface mb-2 flex items-center gap-1.5">
                  <span className="material-symbols-outlined text-[14px] text-primary">monitoring</span>
                  Traffic Stats
                </h3>
                <div className="grid grid-cols-2 gap-2">
                  {[
                    { label: "Vehicles", value: traffic.vehicle_count, color: "text-on-surface" },
                    { label: "Stopped", value: traffic.stopped_count, color: "text-yellow-600" },
                    { label: "Level", value: traffic.level, color: trafficLevelColor(traffic.level) },
                    { label: "Detections", value: detections.length, color: "text-on-surface" },
                  ].map((stat) => (
                    <div key={stat.label} className="bg-white border border-outline-variant rounded-xl p-3 text-center">
                      <div className={`text-[16px] font-bold font-mono ${stat.color}`}>{stat.value}</div>
                      <div className="text-[8px] text-on-surface-variant font-semibold uppercase mt-0.5">{stat.label}</div>
                    </div>
                  ))}
                </div>
              </div>

              <div className="flex-1 min-h-0">
                <h3 className="text-[10px] font-bold uppercase text-on-surface mb-2 flex items-center gap-1.5">
                  <span className="material-symbols-outlined text-[14px] text-primary">radar</span>
                  Active Detections
                  <span className="ml-auto text-[9px] font-mono text-on-surface-variant">{detections.length}</span>
                </h3>
                <div className="flex flex-col gap-1 max-h-32 overflow-y-auto">
                  {detections.length === 0 ? (
                    <p className="text-[10px] text-on-surface-variant text-center py-4">No detections yet</p>
                  ) : (
                    detections.map((d) => (
                      <div key={d.track_id}
                        className={`flex items-center justify-between p-2 rounded-lg text-[10px] ${
                          d.violation ? "bg-red-50 border border-red-200" : "bg-surface-container-low border border-outline-variant"
                        }`}>
                        <div className="flex items-center gap-2">
                          <span className="font-mono text-on-surface-variant">#{d.track_id}</span>
                          <span className="font-semibold capitalize">{d.class_name}</span>
                          {d.is_stopped && <span className="text-yellow-600 font-bold">STOP {d.stationary_seconds}s</span>}
                        </div>
                        {d.violation && <span className="text-red-600 font-bold uppercase">{d.violation.replace(/_/g, " ")}</span>}
                      </div>
                    ))
                  )}
                </div>
              </div>

              <div>
                <h3 className="text-[10px] font-bold uppercase text-on-surface mb-2 flex items-center gap-1.5">
                  <span className="material-symbols-outlined text-[14px] text-error">warning</span>
                  Violation Events
                  {liveEvents.length > 0 && (
                    <span className="ml-auto bg-red-50 text-red-600 text-[9px] font-bold px-2 py-0.5 rounded-full">{liveEvents.length}</span>
                  )}
                </h3>
                <div className="flex flex-col gap-1.5 max-h-48 overflow-y-auto">
                  {liveEvents.length === 0 ? (
                    <p className="text-[10px] text-on-surface-variant text-center py-4">No violations detected</p>
                  ) : (
                    liveEvents.map((evt) => (
                      <div key={evt.event_id} className="bg-red-50 border border-red-200 rounded-xl p-2.5">
                        <div className="flex items-center justify-between mb-0.5">
                          <span className="text-[10px] font-bold text-red-600 uppercase">{evt.violation_type.replace(/_/g, " ")}</span>
                          <span className="text-[9px] text-on-surface-variant">{new Date(evt.timestamp).toLocaleTimeString()}</span>
                        </div>
                        <div className="flex items-center gap-2 text-[9px] text-on-surface-variant">
                          <span className="capitalize">{evt.vehicle_type}</span>
                          <span className="font-mono">#{evt.track_id}</span>
                          <span className="font-semibold text-on-surface">{evt.plate_number}</span>
                        </div>
                      </div>
                    ))
                  )}
                </div>
              </div>
            </div>
          </div>
        </div>
      ) : (
        <div className="flex-1 overflow-y-auto p-4">
          <div className="mb-4 space-y-2">
            <div className="relative">
              <span className="material-symbols-outlined absolute left-3 top-1/2 -translate-y-1/2 text-[17px] text-on-surface-variant">search</span>
              <input
                type="search"
                value={cameraSearch}
                onChange={(e) => setCameraSearch(e.target.value)}
                placeholder="Cari kamera CCTV"
                className="w-full rounded-xl border border-outline-variant bg-white py-2.5 pl-9 pr-9 text-[12px] font-semibold text-on-surface outline-none transition-colors placeholder:font-normal placeholder:text-on-surface-variant focus:border-primary focus:ring-2 focus:ring-primary/10"
              />
              {cameraSearch && (
                <button
                  onClick={() => setCameraSearch("")}
                  className="absolute right-2 top-1/2 -translate-y-1/2 rounded-lg p-1 text-on-surface-variant hover:bg-surface-container-high hover:text-on-surface"
                  aria-label="Clear CCTV camera search"
                >
                  <span className="material-symbols-outlined text-[16px]">close</span>
                </button>
              )}
            </div>
            <div className="flex items-center gap-2">
              <span className="material-symbols-outlined text-[16px] text-on-surface-variant">layers</span>
              <span className="text-[10px] text-on-surface-variant font-medium">Location:</span>
              <select
                value={selectedLocation}
                onChange={(e) => setSelectedLocation(e.target.value)}
                className="bg-white border border-outline-variant text-on-surface rounded-lg px-2.5 py-1.5 text-[11px] outline-none focus:border-primary transition-colors"
              >
                <option value="">All Locations</option>
                {groupKeys.map((k) => (
                  <option key={k} value={k}>{LOCATION_LABELS[k] || k}</option>
                ))}
              </select>
              <span className="text-[10px] text-on-surface-variant ml-auto">{filteredCameraCount}/{cameras.length} cameras</span>
            </div>
          </div>

          {loading ? (
            <div className="py-16 flex items-center justify-center">
              <span className="material-symbols-outlined text-[24px] text-primary animate-spin">sync</span>
            </div>
          ) : (
            <div className="space-y-6">
              {filteredGroupKeys.map((groupKey) => (
                <div key={groupKey}>
                  <div className="flex items-center gap-2 mb-3">
                    <span className="material-symbols-outlined text-[14px] text-primary">location_on</span>
                    <h3 className="text-[12px] font-bold text-on-surface">{LOCATION_LABELS[groupKey] || groupKey}</h3>
                    <span className="text-[9px] text-on-surface-variant font-mono">{filteredGroups[groupKey].length} cameras</span>
                  </div>
                  <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-2">
                    {filteredGroups[groupKey].map((cam) => (
                      <button
                        key={cam.name}
                        onClick={() => resolveAndConnect(cam)}
                        disabled={connectionStatus !== "idle"}
                        className={`p-3 bg-white border rounded-xl text-left hover:border-primary/40 transition-all group ${
                          selectedCamera?.name === cam.name
                            ? "border-primary/50 bg-primary/5"
                            : "border-outline-variant"
                        } disabled:opacity-50 disabled:cursor-wait`}
                      >
                        <div className="flex items-center gap-2 mb-2">
                          <div className={`w-2 h-2 rounded-full ${
                            selectedCamera?.name === cam.name && connectionStatus === "connected"
                              ? "bg-emerald-500 animate-pulse"
                              : "bg-on-surface-variant/30"
                          }`} />
                          <span className="text-[11px] font-semibold text-on-surface truncate group-hover:text-primary transition-colors">
                            {cam.name}
                          </span>
                        </div>
                        <div className="flex items-center gap-1.5">
                          <span className="material-symbols-outlined text-[12px] text-on-surface-variant">videocam</span>
                          <span className="text-[9px] text-on-surface-variant font-mono truncate">{cam.type}</span>
                        </div>
                      </button>
                    ))}
                  </div>
                </div>
              ))}
              {filteredCameraCount === 0 && (
                <div className="rounded-xl border border-dashed border-outline-variant bg-white/70 p-4 text-[12px] text-on-surface-variant">
                  Tidak ada kamera CCTV yang cocok.
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
