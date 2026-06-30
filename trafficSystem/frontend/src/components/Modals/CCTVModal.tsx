import { useState, useEffect, useRef, useCallback } from "react";
import ReactPlayer from "react-player";
const Player = (ReactPlayer as any).default || ReactPlayer;
import type { Camera } from "../../types";
import { getTrafficCounts, getTrafficMetrics } from "../../services/api";

interface Props {
  camera: Camera;
  onClose: () => void;
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

const WS_BASE = import.meta.env.VITE_WS_URL || `ws://localhost:8000/ws`;
const API_BASE = import.meta.env.VITE_API_BASE_URL || `http://localhost:8000`;

export function CCTVModal({ camera, onClose }: Props) {
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [aiMode, setAiMode] = useState(false);
  const [connectionStatus, setConnectionStatus] = useState<ConnectionStatus>("idle");
  const [serverFps, setServerFps] = useState(0);
  const [frameCount, setFrameCount] = useState(0);
  const [sessionDuration, setSessionDuration] = useState(0);
  const [detections, setDetections] = useState<Detection[]>([]);
  const [traffic, setTraffic] = useState({ vehicle_count: 0, stopped_count: 0, stopped_ratio: 0, level: "LOW" });
  const [liveEvents, setLiveEvents] = useState<LiveEvent[]>([]);

  const displayCanvasRef = useRef<HTMLCanvasElement>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectRef = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const containerRef = useRef<HTMLDivElement>(null);
  const esp32CaptureRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const renderBinaryFrame = useCallback((arrayBuffer: ArrayBuffer) => {
    const canvas = displayCanvasRef.current;
    if (!canvas) return;
    const blob = new Blob([arrayBuffer], { type: "image/jpeg" });
    createImageBitmap(blob)
      .then((bitmap) => {
        const ctx = canvas.getContext("2d");
        if (ctx) {
          if (canvas.width !== bitmap.width || canvas.height !== bitmap.height) {
            canvas.width = bitmap.width;
            canvas.height = bitmap.height;
          }
          ctx.drawImage(bitmap, 0, 0);
        }
        bitmap.close();
      })
      .catch(() => {});
  }, []);


  const disconnect = useCallback(() => {
    if (esp32CaptureRef.current) {
      clearInterval(esp32CaptureRef.current);
      esp32CaptureRef.current = null;
    }
    if (reconnectRef.current) clearTimeout(reconnectRef.current);
    if (wsRef.current) {
      try { wsRef.current.send(JSON.stringify({ type: "stop" })); } catch { /* ws may be closed */ }
      wsRef.current.close();
      wsRef.current = null;
    }
    setConnectionStatus("idle");
    setDetections([]);
    setFrameCount(0);
    setServerFps(0);
    setSessionDuration(0);
  }, []);

  const connectRef = useRef<(() => void) | null>(null);

  const connect = useCallback(() => {
    if (!camera.stream_url) {
      setConnectionStatus("error");
      return;
    }
    setConnectionStatus("connecting");
    setDetections([]);
    setTraffic({ vehicle_count: 0, stopped_count: 0, stopped_ratio: 0, level: "LOW" });
    setLiveEvents([]);

    const ws = new WebSocket(`${WS_BASE}/livecam`);
    ws.binaryType = "arraybuffer";
    wsRef.current = ws;

    const camName = camera.name.replace(/\s+/g, "_").toLowerCase();

    ws.onopen = () => {
      ws.send(JSON.stringify({
        type: "config",
        mode: "stream",
        stream_url: camera.stream_url,
        jpeg_quality: 80,
        resize_width: 960,
        source_label: camName,
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
        } else if (data.type === "frame_result") {
          setServerFps(data.fps);
          setFrameCount(data.frame_count);
          setSessionDuration(data.session_duration);
          setDetections(data.detections);
          setTraffic(data.traffic);
          if (data.new_events?.length > 0) {
            setLiveEvents((prev) => [...data.new_events, ...prev].slice(0, 50));
          }
        }
      } catch { /* ws message parse */ }
    };

    ws.onerror = () => {
      setConnectionStatus("error");
    };

    ws.onclose = () => {
      setConnectionStatus("disconnected");
      wsRef.current = null;
      // ESP32 cameras: don't auto-reconnect (only 1 client supported)
      if (connectRef.current && !camera.id.startsWith("esp32")) {
        reconnectRef.current = setTimeout(connectRef.current, 3000);
      }
    };
  }, [camera, renderBinaryFrame]);

  useEffect(() => {
    connectRef.current = connect;
  }, [connect]);

  // Determine if this camera uses an embeddable CCTV player (Balitower)
  const isEmbedCam = camera.stream_url?.includes("balitower.co.id");
  const isEsp32Cam = camera.id.startsWith("esp32");

  useEffect(() => {
    // For embed/ESP32 cameras: only connect WebSocket when user explicitly enables AI mode
    // For other cameras: connect automatically
    if (camera.stream_url && (!(isEmbedCam || isEsp32Cam) || aiMode)) {
      connect();
    }
    return () => {
      disconnect();
    };
  }, [camera.stream_url, aiMode]);

  const trafficLevelColor = (level: string) => {
    switch (level) {
      case "SEVERE": return "text-red-600";
      case "HIGH": return "text-orange-600";
      case "MEDIUM": return "text-yellow-600";
      default: return "text-emerald-600";
    }
  };

  const hasWsFeed = connectionStatus === "connected" || connectionStatus === "connecting";

  const embedIframeRef = useRef<HTMLIFrameElement>(null);

  const [embedTraffic, setEmbedTraffic] = useState<any>(null);
  const [embedMetrics, setEmbedMetrics] = useState<any>(null);

  useEffect(() => {
    if (!isEmbedCam) return;
    const fetch = () => {
      getTrafficCounts().then(setEmbedTraffic).catch(() => {});
      getTrafficMetrics().then(setEmbedMetrics).catch(() => {});
    };
    fetch();
    const interval = setInterval(fetch, 5000);
    return () => clearInterval(interval);
  }, [isEmbedCam]);

  return (
    <div
      className={`fixed inset-0 z-[60] ${isFullscreen ? "" : "flex items-center justify-center p-6 md:p-10 bg-black/40 backdrop-blur-sm overflow-y-auto"}`}
      onClick={isFullscreen ? undefined : onClose}
    >
      <div
        ref={containerRef}
        className={`${isFullscreen ? "fixed inset-0 z-[70] bg-white flex flex-col" : "w-full max-w-4xl glass-modal rounded-2xl overflow-hidden flex flex-col shadow-2xl animate-in fade-in zoom-in-95 duration-200 my-auto max-h-[95vh]"}`}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="px-lg py-md border-b border-outline-variant flex items-center justify-between bg-white/50 flex-shrink-0">
          <div className="flex items-center gap-md">
            <div className="w-10 h-10 bg-primary-fixed-dim/10 rounded-lg flex items-center justify-center border border-primary-fixed-dim/20">
              <span className="material-symbols-outlined text-primary-fixed-dim text-[20px]">videocam</span>
            </div>
            <div>
              <div className="flex items-center gap-2">
                <span className="text-[10px] font-bold text-on-surface-variant uppercase tracking-widest">CCTV Node</span>
                <span className="text-[11px] font-bold text-primary-fixed-dim font-semibold font-mono">{camera.id}</span>
                {hasWsFeed && (
                  <span className={`flex items-center gap-1 text-[10px] font-semibold ${connectionStatus === "connected" ? "text-emerald-600" : "text-amber-600"}`}>
                    <span className={`w-1.5 h-1.5 rounded-full ${connectionStatus === "connected" ? "bg-emerald-500 animate-pulse" : "bg-amber-500"}`} />
                    {connectionStatus === "connected" ? "AI" : "Connecting..."}
                  </span>
                )}
              </div>
              <h2 className="text-[14px] font-bold text-on-surface uppercase tracking-tight">{camera.name}</h2>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <span className="flex items-center gap-1.5 px-3 py-1 bg-emerald-500/10 rounded-full border border-emerald-500/20">
              <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
              <span className="text-[10px] text-emerald-600 uppercase tracking-widest font-bold">LIVE</span>
            </span>
            <button
              onClick={() => setIsFullscreen(!isFullscreen)}
              className="p-2 bg-white border border-outline-variant rounded-lg text-on-surface-variant hover:text-on-surface hover:bg-surface-container transition-colors"
            >
              <span className="material-symbols-outlined text-[18px]">
                {isFullscreen ? "fullscreen_exit" : "fullscreen"}
              </span>
            </button>
            {!isFullscreen && (
              <button
                onClick={onClose}
                className="p-2 bg-white border border-outline-variant rounded-lg text-on-surface-variant hover:text-on-surface hover:bg-surface-container transition-colors"
              >
                <span className="material-symbols-outlined text-[18px]">close</span>
              </button>
            )}
          </div>
        </div>

        {/* Content */}
        <div className={`flex flex-col ${isFullscreen ? "flex-1" : ""} lg:flex-row overflow-hidden`}>
          {/* Video Area */}
          <div className={`relative ${isFullscreen ? "flex-1" : "lg:flex-1"} bg-slate-950 flex items-center justify-center min-h-[300px]`}>
            {isEsp32Cam && camera.stream_url ? (
              aiMode && hasWsFeed ? (
                <canvas ref={displayCanvasRef} className="w-full h-full object-contain" />
              ) : aiMode ? (
                <div className="flex flex-col items-center gap-3">
                  <span className="material-symbols-outlined text-[24px] text-emerald-400 animate-spin">sync</span>
                  <span className="text-[13px] font-semibold text-white">Connecting to AI stream...</span>
                </div>
              ) : (
                <img
                  src={`${API_BASE}/esp32-stream`}
                  className="w-full h-full object-contain"
                  alt={camera.name}
                />
              )
            ) : hasWsFeed && aiMode ? (
              <canvas ref={displayCanvasRef} className="w-full h-full object-contain" />
            ) : camera.stream_url ? (
              camera.stream_url.includes("embed.html") || camera.stream_url.includes("cctv.balitower.co.id") || camera.stream_url.endsWith(".html") ? (
                <iframe
                  ref={embedIframeRef}
                  src={camera.stream_url.replace("http://cctv.balitower.co.id", "https://cctv.balitower.co.id")}
                  className="w-full h-full border-0 bg-slate-950"
                  allowFullScreen
                  scrolling="no"
                  frameBorder="0"
                  allow="autoplay; encrypted-media"
                />
              ) : hasWsFeed ? (
                <canvas ref={displayCanvasRef} className="w-full h-full object-contain" />
              ) : (
                <Player
                  url={camera.stream_url}
                  playing
                  loop
                  muted
                  width="100%"
                  height="100%"
                />
              )
            ) : (
              <div className="text-[12px] text-on-surface-variant font-medium uppercase tracking-wider flex flex-col items-center gap-2">
                <span className="material-symbols-outlined text-[36px] text-outline">videocam_off</span>
                <span>Feed tidak tersedia</span>
              </div>
            )}

            {connectionStatus === "connecting" && aiMode && (
              <div className="absolute inset-0 bg-black/60 flex items-center justify-center">
                <div className="flex items-center gap-3">
                  <span className="material-symbols-outlined text-[24px] text-emerald-400 animate-spin">sync</span>
                  <span className="text-[13px] font-semibold text-white">Connecting to AI stream...</span>
                </div>
              </div>
            )}

            {/* AI Mode Toggle for embed/ESP32 cameras */}
            {(isEmbedCam || isEsp32Cam) && (
              <div className="absolute bottom-3 left-3">
                <button
                  onClick={() => {
                    if (aiMode) {
                      disconnect();
                      setAiMode(false);
                    } else {
                      setAiMode(true);
                    }
                  }}
                  className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-[11px] font-bold backdrop-blur-sm transition-all ${
                    aiMode
                      ? "bg-emerald-500/90 text-white hover:bg-emerald-600/90"
                      : "bg-black/60 text-white/80 hover:bg-black/80 hover:text-white"
                  }`}
                >
                  <span className="material-symbols-outlined text-[14px]">{aiMode ? "smart_toy" : "auto_awesome"}</span>
                  {aiMode ? "AI Active" : "Enable AI Detection"}
                </button>
              </div>
            )}

            {/* Stream overlay info */}
            {connectionStatus === "connected" && (
              <>
                <div className="absolute top-3 left-3 flex items-center gap-2 bg-black/60 backdrop-blur-sm px-3 py-1.5 rounded-lg">
                  <span className="w-2 h-2 bg-red-500 rounded-full animate-pulse" />
                  <span className="text-[11px] font-bold text-white">LIVE</span>
                  <span className="text-[10px] text-slate-300 font-mono">
                    {Math.floor(sessionDuration / 60)}:{String(Math.floor(sessionDuration % 60)).padStart(2, "0")}
                  </span>
                </div>
                <div className="absolute top-3 right-3 flex items-center gap-3 bg-black/60 backdrop-blur-sm px-3 py-1.5 rounded-lg">
                  <span className="flex items-center gap-1 text-[11px] text-white font-mono">
                    <span className="material-symbols-outlined text-[14px] text-emerald-400">speed</span>
                    {serverFps} FPS
                  </span>
                  <span className="text-[10px] text-slate-400">#{frameCount}</span>
                </div>
              </>
            )}
          </div>

          {/* Side Panel */}
          {(hasWsFeed || isEmbedCam || isEsp32Cam) && (
            <div className={`${isFullscreen ? "w-80 flex-shrink-0 border-l border-outline-variant" : ""} bg-white/80 flex flex-col gap-4 overflow-y-auto ${isFullscreen ? "" : "p-4 lg:w-80 lg:border-l lg:border-outline-variant"}`}>
              {(isEmbedCam || isEsp32Cam) ? (
                <>
                  {/* Camera Info */}
                  <div className={isFullscreen ? "p-4" : ""}>
                    <h3 className="text-[11px] font-bold uppercase text-on-surface mb-3 flex items-center gap-1.5">
                      <span className="material-symbols-outlined text-[16px] text-primary">videocam</span>
                      Camera Info
                    </h3>
                    <div className="bg-white border border-outline-variant rounded-xl p-3 flex flex-col gap-2 text-[11px]">
                      <div className="flex justify-between"><span className="text-on-surface-variant">ID</span><span className="font-mono font-semibold">{camera.id}</span></div>
                      <div className="flex justify-between"><span className="text-on-surface-variant">Area</span><span className="font-semibold">{camera.name}</span></div>
                      <div className="flex justify-between"><span className="text-on-surface-variant">Latitude</span><span className="font-mono">{camera.lat.toFixed(4)}</span></div>
                      <div className="flex justify-between"><span className="text-on-surface-variant">Longitude</span><span className="font-mono">{camera.lng.toFixed(4)}</span></div>
                      <div className="flex justify-between"><span className="text-on-surface-variant">Type</span><span className="bg-primary/10 text-primary text-[10px] font-bold px-2 py-0.5 rounded-full">LIVESTREAM</span></div>
                    </div>
                  </div>

                  {/* Traffic Stats from API */}
                  <div className={isFullscreen ? "px-4" : ""}>
                    <h3 className="text-[11px] font-bold uppercase text-on-surface mb-3 flex items-center gap-1.5">
                      <span className="material-symbols-outlined text-[16px] text-primary">monitoring</span>
                      Traffic Stats
                    </h3>
                    <div className="grid grid-cols-2 gap-2">
                      {[
                        { label: "Density", value: embedMetrics?.density_level || "—", color: "text-on-surface" },
                        { label: "Speed", value: embedMetrics?.average_speed ? `${Math.round(embedMetrics.average_speed)} px/s` : "—", color: "text-cyan-600" },
                        { label: "Vehicles", value: embedMetrics?.vehicle_count ?? "—", color: "text-violet-600" },
                        { label: "Crossings", value: embedTraffic ? Object.values(embedTraffic).reduce((s: number, l: any) => s + (l.forward?.total || 0) + (l.backward?.total || 0), 0) : "—", color: "text-emerald-600" },
                      ].map((stat) => (
                        <div key={stat.label} className="bg-white border border-outline-variant rounded-xl p-3 text-center">
                          <div className={`text-[18px] font-bold font-mono ${stat.color}`}>{stat.value}</div>
                          <div className="text-[9px] text-on-surface-variant font-semibold uppercase mt-1">{stat.label}</div>
                        </div>
                      ))}
                    </div>
                  </div>

                  {/* Actions */}
                  <div className={`${isFullscreen ? "px-4 pb-4" : ""} flex flex-col gap-2`}>
                    <a href={camera.stream_url} target="_blank" rel="noopener noreferrer" className="flex items-center justify-center gap-2 py-2 bg-primary text-white text-[12px] font-bold rounded-xl hover:brightness-105 transition-all">
                      <span className="material-symbols-outlined text-[16px]">open_in_new</span>
                      Buka di Browser
                    </a>
                    <button onClick={onClose} className="py-2 bg-white border border-outline-variant text-on-surface-variant hover:text-on-surface text-[12px] font-semibold rounded-xl transition-colors">
                      Tutup
                    </button>
                  </div>
                </>
              ) : (
                <>
                  {/* Traffic Stats */}
                  <div className={isFullscreen ? "p-4" : ""}>
                    <h3 className="text-[11px] font-bold uppercase text-on-surface mb-3 flex items-center gap-1.5">
                      <span className="material-symbols-outlined text-[16px] text-primary">monitoring</span>
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
                          <div className={`text-[18px] font-bold font-mono ${stat.color}`}>{stat.value}</div>
                          <div className="text-[9px] text-on-surface-variant font-semibold uppercase mt-1">{stat.label}</div>
                        </div>
                      ))}
                    </div>
                  </div>

                  {/* Detections */}
                  <div className={isFullscreen ? "px-4" : ""}>
                    <h3 className="text-[11px] font-bold uppercase text-on-surface mb-3 flex items-center gap-1.5">
                      <span className="material-symbols-outlined text-[16px] text-primary">radar</span>
                      Active Detections
                      <span className="ml-auto text-[10px] font-mono text-on-surface-variant">{detections.length}</span>
                    </h3>
                    <div className="flex flex-col gap-1.5 max-h-40 overflow-y-auto">
                      {detections.length === 0 ? (
                        <p className="text-[11px] text-on-surface-variant text-center py-4">No detections yet</p>
                      ) : (
                        detections.map((d) => (
                          <div
                            key={d.track_id}
                            className={`flex items-center justify-between p-2 rounded-lg text-[11px] ${
                              d.violation ? "bg-red-50 border border-red-200" : "bg-slate-50 border border-slate-200"
                            }`}
                          >
                            <div className="flex items-center gap-2">
                              <span className="font-mono text-on-surface-variant text-[10px]">#{d.track_id}</span>
                              <span className="font-semibold text-on-surface capitalize">{d.class_name}</span>
                              {d.is_stopped && <span className="text-yellow-600 text-[10px] font-bold">STOP {d.stationary_seconds}s</span>}
                            </div>
                            {d.violation && <span className="text-red-600 font-bold text-[10px] uppercase">{d.violation.replace(/_/g, " ")}</span>}
                          </div>
                        ))
                      )}
                    </div>
                  </div>

                  {/* Violation Events */}
                  <div className={isFullscreen ? "px-4 pb-4" : ""}>
                    <h3 className="text-[11px] font-bold uppercase text-on-surface mb-3 flex items-center gap-1.5">
                      <span className="material-symbols-outlined text-[16px] text-error">warning</span>
                      Violation Events
                      {liveEvents.length > 0 && (
                        <span className="ml-auto bg-red-50 text-red-600 text-[10px] font-bold px-2 py-0.5 rounded-full border border-red-200">
                          {liveEvents.length}
                        </span>
                      )}
                    </h3>
                    <div className="flex flex-col gap-1.5 max-h-48 overflow-y-auto">
                      {liveEvents.length === 0 ? (
                        <p className="text-[11px] text-on-surface-variant text-center py-4">No violations detected</p>
                      ) : (
                        liveEvents.map((evt) => (
                          <div key={evt.event_id} className="bg-red-50 border border-red-200 rounded-xl p-3">
                            <div className="flex items-center justify-between mb-1">
                              <span className="text-[11px] font-bold text-red-600 uppercase">{evt.violation_type.replace(/_/g, " ")}</span>
                              <span className="text-[10px] text-on-surface-variant">{new Date(evt.timestamp).toLocaleTimeString()}</span>
                            </div>
                            <div className="flex items-center gap-3 text-[10px] text-on-surface-variant">
                              <span className="capitalize">{evt.vehicle_type}</span>
                              <span className="font-mono">#{evt.track_id}</span>
                              <span className="font-semibold text-on-surface">{evt.plate_number}</span>
                            </div>
                          </div>
                        ))
                      )}
                    </div>
                  </div>
                </>
              )}
            </div>
          )}

          {/* Telemetry + Actions for non-WS & non-embed mode */}
          {!hasWsFeed && !isEmbedCam && !isEsp32Cam && (
            <div className="flex justify-between items-center p-4 border-t border-outline-variant/50 bg-white/50">
              <div className="flex gap-4 text-[11px] text-on-surface-variant font-medium">
                <span className="flex items-center gap-1">
                  <span className="material-symbols-outlined text-[14px]">location_on</span>
                  Lat: {camera.lat.toFixed(4)}
                </span>
                <span>Lng: {camera.lng.toFixed(4)}</span>
              </div>
              <button
                onClick={onClose}
                className="py-2 px-6 bg-white border border-outline-variant text-on-surface-variant hover:text-on-surface hover:bg-surface-container font-semibold rounded-lg transition-colors text-[12px]"
              >
                Tutup
              </button>
            </div>
          )}
        </div>

        {/* Close button for fullscreen */}
        {isFullscreen && (
          <div className="fixed top-4 right-4 z-[80] flex items-center gap-2">
            <button
              onClick={() => setIsFullscreen(false)}
              className="p-2 bg-white/90 backdrop-blur-md border border-outline-variant rounded-lg shadow-lg text-on-surface-variant hover:text-on-surface transition-colors"
            >
              <span className="material-symbols-outlined text-[18px]">fullscreen_exit</span>
            </button>
            <button
              onClick={onClose}
              className="p-2 bg-white/90 backdrop-blur-md border border-outline-variant rounded-lg shadow-lg text-on-surface-variant hover:text-on-surface transition-colors"
            >
              <span className="material-symbols-outlined text-[18px]">close</span>
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
