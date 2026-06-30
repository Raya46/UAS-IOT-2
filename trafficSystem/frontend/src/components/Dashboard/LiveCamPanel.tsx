import { useCallback, useEffect, useRef, useState } from "react";
import { getDashcamSources } from "../../services/api";

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
  contextual_reasoning?: {
    is_violation: boolean;
    behavior: string;
    confidence: number;
    reason: string;
    exemption: string;
    reasoning_source?: string;
  };
}

interface EnhancementInfo {
  applied: boolean;
  modes: string[];
  brightness: number;
  contrast: number;
  sharpness: number;
}

interface DashcamSource {
  id: string;
  name: string;
  route: string;
  videoFile: string;
  videoUrl?: string;
  color: string;
  status: "active" | "standby" | "unavailable";
  description: string;
}

interface DashcamSourceResponse {
  id: string;
  name: string;
  route: string;
  description: string;
  color: string;
  video_file: string;
  video_url?: string;
  status: "active" | "standby" | "unavailable";
}

type SourceMode = "browser" | "stream";
type ConnectionStatus = "idle" | "connecting" | "connected" | "error" | "disconnected";

const QUALITY_PRESETS = [
  { label: "Low", captureWidth: 480, jpegQuality: 60, serverResize: 640, serverJpeg: 65 },
  { label: "Medium", captureWidth: 640, jpegQuality: 75, serverResize: 800, serverJpeg: 75 },
  { label: "High", captureWidth: 960, jpegQuality: 85, serverResize: 960, serverJpeg: 85 },
  { label: "Ultra", captureWidth: 1280, jpegQuality: 92, serverResize: 1280, serverJpeg: 90 },
];

const WS_BASE = import.meta.env.VITE_WS_URL || "ws://localhost:8000/ws";

const toDashcamSource = (source: DashcamSourceResponse): DashcamSource => ({
  id: source.id,
  name: source.name,
  route: source.route,
  videoFile: source.video_file,
  videoUrl: source.video_url,
  color: source.color,
  status: source.status,
  description: source.description,
});

interface ViolationLog {
  source: string; // dashcam name or CCTV label
  type: string;   // violation type
  detail: string; // description
  plate?: string; // plate number if available
  vehicleType?: string;
  evidenceImage?: string;
  evidenceSize?: [number, number];
  plateCrop?: string;
  plateBbox?: [number, number, number, number];
  plateConfidence?: number;
  plateNote?: string;
  videoTimeSeconds?: number;
  videoFile?: string;
}

interface LiveCamPanelProps {
  onViolationDetected?: (v: ViolationLog) => void;
}

export function LiveCamPanel({ onViolationDetected }: LiveCamPanelProps) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const captureCanvasRef = useRef<HTMLCanvasElement>(null);
  const displayCanvasRef = useRef<HTMLCanvasElement>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const captureIntervalRef = useRef<number | null>(null);
  const reconnectTimeoutRef = useRef<number | null>(null);
  const waitingForResponseRef = useRef(false);

  const [sourceMode, setSourceMode] = useState<SourceMode>("browser");
  const [streamUrl, setStreamUrl] = useState("http://192.168.1.100:81/stream");
  const [sourceLabel, setSourceLabel] = useState("livecam");
  const [cameraActive, setCameraActive] = useState(false);
  const [connectionStatus, setConnectionStatus] = useState<ConnectionStatus>("idle");
  const [sessionId, setSessionId] = useState("");
  const [facingMode, setFacingMode] = useState<"environment" | "user">("environment");
  const [cameraError, setCameraError] = useState("");
  const [showSettings, setShowSettings] = useState(false);
  const [qualityPreset, setQualityPreset] = useState(2);
  const [targetFps, setTargetFps] = useState(12);
  const [serverFps, setServerFps] = useState(0);
  const [frameCount, setFrameCount] = useState(0);
  const [sessionDuration, setSessionDuration] = useState(0);
  const [detections, setDetections] = useState<Detection[]>([]);
  const [traffic, setTraffic] = useState<TrafficInfo>({ vehicle_count: 0, stopped_count: 0, stopped_ratio: 0, level: "LOW" });
  const [liveEvents, setLiveEvents] = useState<LiveEvent[]>([]);
  const [enhancement, setEnhancement] = useState<EnhancementInfo | null>(null);

  const [selectedDashcam, setSelectedDashcam] = useState<DashcamSource | null>(null);
  const selectedDashcamRef = useRef<DashcamSource | null>(null);
  const [dashcamSources, setDashcamSources] = useState<DashcamSource[]>([]);
  const [dashcamSourcesLoading, setDashcamSourcesLoading] = useState(true);
  const [dashcamSourcesError, setDashcamSourcesError] = useState("");
  const dashcamOverlayRef = useRef<HTMLCanvasElement>(null);
  const dashcamWsRef = useRef<WebSocket | null>(null);
  const [dashcamStatus, setDashcamStatus] = useState<string>("idle");
  const [dashcamDetections, setDashcamDetections] = useState<any[]>([]);
  const [dashcamPedestrians, setDashcamPedestrians] = useState<any[]>([]);
  const [dashcamBicycles, setDashcamBicycles] = useState<any[]>([]);
  const [dashcamTrafficSigns, setDashcamTrafficSigns] = useState<any[]>([]);
  const [dashcamTrafficLights, setDashcamTrafficLights] = useState<any[]>([]);
  const [dashcamTrafficLightColor, setDashcamTrafficLightColor] = useState<string>("unknown");

  // Track logged violations to avoid duplicates (key = source+type+trackId)
  const loggedViolationsRef = useRef<Set<string>>(new Set());

  // Ref to always access latest onViolationDetected without stale closures
  const onViolationRef = useRef(onViolationDetected);
  onViolationRef.current = onViolationDetected;

  const preset = QUALITY_PRESETS[qualityPreset];
  const activeDashcams = dashcamSources.filter((cam) => cam.status === "active");

  useEffect(() => {
    selectedDashcamRef.current = selectedDashcam;
  }, [selectedDashcam]);

  useEffect(() => {
    const loadDashcamSources = async () => {
      setDashcamSourcesLoading(true);
      setDashcamSourcesError("");
      try {
        const sources = await getDashcamSources();
        setDashcamSources(sources.map(toDashcamSource));
      } catch (error) {
        setDashcamSources([]);
        setDashcamSourcesError(
          error instanceof Error ? error.message : "Cannot load dashcam sources",
        );
      } finally {
        setDashcamSourcesLoading(false);
      }
    };

    void loadDashcamSources();
  }, []);

  const renderBinaryFrame = useCallback((arrayBuffer: ArrayBuffer) => {
    const canvas = displayCanvasRef.current;
    if (!canvas) return;
    const blob = new Blob([arrayBuffer], { type: "image/jpeg" });
    const url = URL.createObjectURL(blob);
    const img = new window.Image();
    img.onload = () => {
      canvas.width = img.width;
      canvas.height = img.height;
      const ctx = canvas.getContext("2d");
      if (ctx) ctx.drawImage(img, 0, 0);
      URL.revokeObjectURL(url);
    };
    img.onerror = () => URL.revokeObjectURL(url);
    img.src = url;
  }, []);

  const connectWebSocket = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return;
    setConnectionStatus("connecting");
    const ws = new WebSocket(`${WS_BASE}/livecam`);
    ws.binaryType = "arraybuffer";
    wsRef.current = ws;

    ws.onopen = () => {};

    ws.onmessage = (event) => {
      if (event.data instanceof ArrayBuffer) {
        renderBinaryFrame(event.data);
        waitingForResponseRef.current = false;
        return;
      }
      try {
        const data = JSON.parse(event.data);
        if (data.type === "connected") {
          setConnectionStatus("connected");
          setSessionId(data.session_id);
          ws.send(JSON.stringify({
            type: "config", mode: sourceMode,
            stream_url: sourceMode === "stream" ? streamUrl : undefined,
            jpeg_quality: preset.serverJpeg, resize_width: preset.serverResize,
            source_label: sourceLabel || "livecam",
          }));
          return;
        }
        if (data.type === "stream_started") return;
        if (data.type === "dropped") { waitingForResponseRef.current = false; return; }
        if (data.type === "error") { waitingForResponseRef.current = false; return; }
        if (data.type === "frame_result") {
          setServerFps(data.fps);
          setFrameCount(data.frame_count);
          setSessionDuration(data.session_duration);
          setDetections(data.detections);
          setTraffic(data.traffic);
          setEnhancement(data.image_enhancement || null);
          if (data.new_events?.length > 0) {
            setLiveEvents((prev) => [...data.new_events, ...prev].slice(0, 50));
          }

          // --- CCTV Violation logging ---
          if (onViolationRef.current && data.new_events?.length > 0) {
            const logged = loggedViolationsRef.current;
            for (const evt of data.new_events) {
              const key = `cctv-${evt.event_id}`;
              if (!logged.has(key)) {
                logged.add(key);
                onViolationRef.current({
                  source: `CCTV: ${sourceLabel}`,
                  type: evt.violation_type || "violation",
                  detail: `${evt.violation_type?.replace(/_/g, " ")} pada ${evt.vehicle_type} (ID: ${evt.track_id})`,
                  plate: evt.plate_number || undefined,
                });
              }
            }
          }

          // CCTV: violations from individual detections
          if (onViolationRef.current && data.detections) {
            const logged = loggedViolationsRef.current;
            for (const d of data.detections) {
              if (d.violation) {
                const key = `cctv-det-${sourceLabel}-${d.track_id}-${d.violation}`;
                if (!logged.has(key)) {
                  logged.add(key);
                  onViolationRef.current({
                    source: `CCTV: ${sourceLabel}`,
                    type: d.violation,
                    detail: `${d.violation.replace(/_/g, " ")} terdeteksi pada ${d.class_name} (ID: ${d.track_id})`,
                  });
                }
              }
            }
          }
        }
      } catch {}
    };

    ws.onerror = () => setConnectionStatus("error");
    ws.onclose = () => {
      setConnectionStatus("disconnected");
      wsRef.current = null;
      waitingForResponseRef.current = false;
      if (cameraActive) {
        reconnectTimeoutRef.current = window.setTimeout(() => connectWebSocket(), 2000);
      }
    };
  }, [cameraActive, sourceMode, streamUrl, preset, sourceLabel]);

  const startCapture = useCallback(() => {
    if (captureIntervalRef.current) clearInterval(captureIntervalRef.current);
    const intervalMs = Math.round(1000 / targetFps);
    captureIntervalRef.current = window.setInterval(() => {
      const video = videoRef.current;
      const canvas = captureCanvasRef.current;
      const ws = wsRef.current;
      if (!video || !canvas || !ws || ws.readyState !== WebSocket.OPEN) return;
      if (video.readyState < 2) return;
      if (waitingForResponseRef.current) return;
      const maxWidth = preset.captureWidth;
      const scale = video.videoWidth > maxWidth ? maxWidth / video.videoWidth : 1;
      canvas.width = Math.round(video.videoWidth * scale);
      canvas.height = Math.round(video.videoHeight * scale);
      const ctx = canvas.getContext("2d");
      if (!ctx) return;
      ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
      canvas.toBlob((blob) => {
        if (blob && ws.readyState === WebSocket.OPEN && ws.bufferedAmount < 1024 * 512) {
          waitingForResponseRef.current = true;
          ws.send(blob);
        }
      }, "image/jpeg", preset.jpegQuality / 100);
    }, intervalMs);
  }, [targetFps, preset]);

  const startCamera = useCallback(async () => {
    setCameraError("");
    try {
      if (sourceMode === "browser") {
        const stream = await navigator.mediaDevices.getUserMedia({
          video: { facingMode, width: { ideal: 1920 }, height: { ideal: 1080 } },
          audio: false,
        });
        streamRef.current = stream;
        if (videoRef.current) {
          videoRef.current.srcObject = stream;
          await videoRef.current.play();
        }
      }
      setCameraActive(true);
      connectWebSocket();
      if (sourceMode === "browser" && videoRef.current) {
        videoRef.current.onloadedmetadata = () => startCapture();
        if (videoRef.current.readyState >= 2) startCapture();
      }
    } catch (err: any) {
      if (err.name === "NotAllowedError") setCameraError("Camera access denied.");
      else if (err.name === "NotFoundError") setCameraError("No camera found.");
      else if (err.name === "NotReadableError") setCameraError("Camera is being used by another application.");
      else setCameraError(`Camera error: ${err.message || err.name}`);
    }
  }, [facingMode, connectWebSocket, sourceMode, startCapture]);

  const stopCamera = useCallback(() => {
    if (captureIntervalRef.current) { clearInterval(captureIntervalRef.current); captureIntervalRef.current = null; }
    if (reconnectTimeoutRef.current) { clearTimeout(reconnectTimeoutRef.current); reconnectTimeoutRef.current = null; }
    if (streamRef.current) { streamRef.current.getTracks().forEach((t) => t.stop()); streamRef.current = null; }
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      try { wsRef.current.send(JSON.stringify({ type: "stop" })); } catch {}
    }
    if (wsRef.current) { wsRef.current.close(); wsRef.current = null; }
    if (videoRef.current) videoRef.current.srcObject = null;
    setCameraActive(false);
    setConnectionStatus("idle");
    setSessionId("");
    setDetections([]);
    setFrameCount(0);
    setServerFps(0);
    setSessionDuration(0);
    setEnhancement(null);
    waitingForResponseRef.current = false;
  }, []);

  const switchCamera = useCallback(() => {
    const newMode = facingMode === "environment" ? "user" : "environment";
    setFacingMode(newMode);
    if (cameraActive) { stopCamera(); setTimeout(() => startCamera(), 500); }
  }, [facingMode, cameraActive, stopCamera, startCamera]);

  useEffect(() => {
    if (cameraActive && sourceMode === "browser" && videoRef.current?.readyState && videoRef.current.readyState >= 2) {
      startCapture();
    }
  }, [targetFps, qualityPreset, startCapture, cameraActive, sourceMode]);

  useEffect(() => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: "config", jpeg_quality: preset.serverJpeg, resize_width: preset.serverResize }));
    }
  }, [qualityPreset, preset]);

  const formatDuration = (seconds: number) => {
    const m = Math.floor(seconds / 60);
    const s = Math.floor(seconds % 60);
    return `${m}:${s.toString().padStart(2, "0")}`;
  };

  const trafficLevelColor = (level: string) => {
    switch (level) {
      case "SEVERE": return "text-red-400";
      case "HIGH": return "text-orange-400";
      case "MEDIUM": return "text-yellow-400";
      default: return "text-emerald-400";
    }
  };

  const isStreaming = cameraActive && (connectionStatus === "connected" || connectionStatus === "connecting");


  const disconnectDashcam = useCallback(() => {

    if (dashcamWsRef.current) {
      try { dashcamWsRef.current.send(JSON.stringify({ type: "stop" })); } catch {}
      dashcamWsRef.current.close();
      dashcamWsRef.current = null;
    }
    setDashcamStatus("idle");
  }, []);

  useEffect(() => {
    return () => { stopCamera(); disconnectDashcam(); };
  }, [stopCamera, disconnectDashcam]);


  const connectDashcamWS = useCallback((videoFile: string) => {
    if (dashcamWsRef.current?.readyState === WebSocket.OPEN) {
      dashcamWsRef.current.close();
    }
    setDashcamStatus("connecting");
    setDashcamDetections([]);
    setDashcamPedestrians([]);
    setDashcamBicycles([]);
    setDashcamTrafficSigns([]);
    setDashcamTrafficLights([]);

    const wsBase = import.meta.env.VITE_WS_URL || "ws://localhost:8000/ws";
    const ws = new WebSocket(`${wsBase}/dashcam`);
    ws.binaryType = "arraybuffer";
    dashcamWsRef.current = ws;

    ws.onopen = () => {
      ws.send(JSON.stringify({ video_file: videoFile }));
    };

    ws.onmessage = (event) => {
      // Render binary frames from server (YOLO-annotated JPEG)
      if (event.data instanceof ArrayBuffer) {
        const canvas = dashcamOverlayRef.current;
        if (!canvas) return;
        const blob = new Blob([event.data], { type: "image/jpeg" });
        createImageBitmap(blob)
          .then((bitmap) => {
            if (canvas.width !== bitmap.width || canvas.height !== bitmap.height) {
              canvas.width = bitmap.width;
              canvas.height = bitmap.height;
            }
            const ctx = canvas.getContext("2d");
            if (ctx) ctx.drawImage(bitmap, 0, 0);
            bitmap.close();
          })
          .catch(() => {});
        return;
      }
      try {
        const data = JSON.parse(event.data);
        if (data.type === "connected") {
          setDashcamStatus("connected");
        } else if (data.type === "resolved") {
          setDashcamStatus("streaming");
        } else if (data.type === "frame_result") {
          setDashcamDetections(data.vehicles || []);
          setDashcamPedestrians(data.pedestrians || []);
          setDashcamBicycles(data.bicycles || []);
          setDashcamTrafficSigns(data.traffic_signs || []);
          setDashcamTrafficLights(data.traffic_lights || []);
          setDashcamTrafficLightColor(data.traffic_light_color || "unknown");
          setServerFps(data.fps || 0);
          setFrameCount(data.frame_count || 0);
          setSessionDuration(data.session_duration || 0);
          if (data.traffic) {
            setTraffic(data.traffic);
          }

          // --- Process violation events from backend ---
          if (onViolationRef.current && data.violations?.length > 0) {
            const logged = loggedViolationsRef.current;
            const selectedCam = selectedDashcamRef.current;
            const camName = selectedCam?.name || "Dashcam";
            for (const vio of data.violations) {
              const key = `dashcam-vio-${vio.event_id}`;
              if (!logged.has(key)) {
                logged.add(key);
                onViolationRef.current({
                  source: `Dashcam: ${camName}`,
                  type: vio.violation_type,
                  detail: vio.description,
                  plate: vio.plate_number || undefined,
                  vehicleType: vio.vehicle_type || undefined,
                  evidenceImage: vio.evidence_image || undefined,
                  evidenceSize: vio.evidence_size || undefined,
                  plateCrop: vio.plate_crop || undefined,
                  plateBbox: vio.plate_bbox || undefined,
                  plateConfidence: vio.plate_confidence ?? undefined,
                  plateNote: vio.plate_note || undefined,
                  videoTimeSeconds: vio.video_time_seconds ?? undefined,
                  videoFile: selectedCam?.videoFile,
                });
              }
            }
          }
        } else if (data.type === "error") {
          setDashcamStatus("error");
        }
      } catch {}
    };

    ws.onerror = () => {
      setDashcamStatus("error");
    };

    ws.onclose = () => {
      dashcamWsRef.current = null;
      if (selectedDashcamRef.current) {
        setDashcamStatus("disconnected");
      }
    };
  }, []);


  const handleDashcamClick = (cam: DashcamSource) => {
    if (selectedDashcam?.id === cam.id) {
      disconnectDashcam();
      setSelectedDashcam(null);
    } else {
      disconnectDashcam();
      setSelectedDashcam(cam);
      connectDashcamWS(cam.videoFile);
    }
  };

  return (
    <div className="flex-1 flex flex-col h-full overflow-hidden">
      <div className="p-4 border-b border-outline-variant flex items-center justify-between flex-shrink-0">
        <div className="flex items-center gap-2">
          <span className="material-symbols-outlined text-primary text-[20px]">videocam</span>
          <h2 className="text-[14px] font-bold uppercase tracking-tight text-on-surface">Live Cam Detection</h2>
        </div>
        <div className="flex items-center gap-2">
          {sessionId && (
            <span className="text-[9px] font-mono text-on-surface-variant bg-surface-container px-1.5 py-0.5 rounded">{sessionId}</span>
          )}
          {connectionStatus === "connected" && (
            <span className="flex items-center gap-1 text-[10px] font-bold text-emerald-600 bg-emerald-50 px-2 py-0.5 rounded-full border border-emerald-200">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />LIVE
            </span>
          )}
          {connectionStatus === "connecting" && (
            <span className="flex items-center gap-1 text-[10px] font-bold text-yellow-600 bg-yellow-50 px-2 py-0.5 rounded-full">
              <span className="material-symbols-outlined text-[12px] animate-spin">sync</span>Connecting
            </span>
          )}
          {connectionStatus === "error" && (
            <span className="flex items-center gap-1 text-[10px] font-bold text-red-600 bg-red-50 px-2 py-0.5 rounded-full">
              Error
            </span>
          )}
        </div>
      </div>

      <div className="flex-1 overflow-y-auto">
        {!cameraActive && (
          <div className="p-4 space-y-4 border-b border-outline-variant bg-surface-container-low/30">
            <div className="flex gap-2">
              <button onClick={() => setSourceMode("browser")}
                className={`flex-1 py-2 text-[11px] font-bold rounded-lg border transition-all ${sourceMode === "browser" ? "bg-primary text-white border-primary" : "bg-white text-on-surface-variant border-outline-variant"}`}>
                Device Camera
              </button>
              <button onClick={() => setSourceMode("stream")}
                className={`flex-1 py-2 text-[11px] font-bold rounded-lg border transition-all ${sourceMode === "stream" ? "bg-primary text-white border-primary" : "bg-white text-on-surface-variant border-outline-variant"}`}>
                IP Cam / Stream
              </button>
            </div>
            {sourceMode === "stream" && (
              <div className="space-y-2">
                <input type="url" value={streamUrl} onChange={(e) => setStreamUrl(e.target.value)}
                  placeholder="rtsp://... or http://.../stream"
                  className="w-full px-3 py-2 bg-white border border-outline-variant rounded-lg text-[12px] placeholder:text-on-surface-variant focus:outline-none focus:border-primary" />
                <input type="text" value={sourceLabel} onChange={(e) => setSourceLabel(e.target.value)}
                  placeholder="Source label (e.g. esp32-front)"
                  className="w-full px-3 py-2 bg-white border border-outline-variant rounded-lg text-[12px] placeholder:text-on-surface-variant focus:outline-none focus:border-primary" />
              </div>
            )}
            <div>
              <label className="text-[10px] font-semibold text-on-surface-variant mb-2 block">Quality</label>
              <div className="grid grid-cols-4 gap-1">
                {QUALITY_PRESETS.map((p, i) => (
                  <button key={p.label} onClick={() => setQualityPreset(i)}
                    className={`py-1.5 text-[10px] font-bold rounded-lg border transition-all ${qualityPreset === i ? "bg-primary text-white border-primary" : "bg-white text-on-surface-variant border-outline-variant"}`}>
                    {p.label}
                    <span className="block text-[8px] font-mono mt-0.5 opacity-60">{p.captureWidth}px</span>
                  </button>
                ))}
              </div>
            </div>
            <div className="flex items-center gap-3">
              <span className="text-[10px] text-on-surface-variant w-20">FPS: {targetFps}</span>
              <input type="range" min={3} max={24} value={targetFps}
                onChange={(e) => setTargetFps(Number(e.target.value))}
                className="flex-1 accent-primary" />
            </div>
          </div>
        )}

        <div className="p-4">
          <div className="bg-slate-950 rounded-xl overflow-hidden border border-outline-variant mb-3 relative" style={{ minHeight: 280 }}>
            <video ref={videoRef} playsInline muted autoPlay style={{ display: "none" }} />
            <canvas ref={captureCanvasRef} style={{ display: "none" }} />
            {isStreaming ? (
              <canvas ref={displayCanvasRef} className="w-full" />
            ) : selectedDashcam ? (
              <div className="relative w-full" style={{ minHeight: 280 }}>
                <canvas
                  ref={dashcamOverlayRef}
                  className="absolute inset-0 w-full h-full"
                  style={{ minHeight: 280 }}
                />
                {(dashcamStatus === "connecting" || dashcamStatus === "connected") && !frameCount && (
                  <div className="absolute inset-0 flex items-center justify-center bg-black/60">
                    <div className="flex flex-col items-center gap-2">
                      <span className="material-symbols-outlined text-white animate-spin text-[32px]">sync</span>
                      <span className="text-white text-[12px] font-semibold">
                        Loading YOLO model...
                      </span>
                    </div>
                  </div>
                )}
                {dashcamStatus === "error" && (
                  <div className="absolute inset-0 flex items-center justify-center bg-black/60">
                    <div className="flex flex-col items-center gap-2">
                      <span className="material-symbols-outlined text-red-400 text-[32px]">error</span>
                      <span className="text-white text-[12px] font-semibold">Stream Error</span>
                    </div>
                  </div>
                )}
                {dashcamStatus === "streaming" && frameCount > 0 && (
                  <div className="absolute top-3 left-3 flex items-center gap-2 bg-black/60 backdrop-blur-sm px-2.5 py-1.5 rounded-lg">
                    <span className="w-2 h-2 rounded-full bg-green-500 animate-pulse" />
                    <span className="text-[10px] font-bold text-white">YOLO</span>
                    <span className="text-[9px] text-slate-300 font-mono">{serverFps} FPS</span>
                    <span className="text-[9px] text-slate-400 font-mono">#{frameCount}</span>
                  </div>
                )}
                <button
                  onClick={() => { disconnectDashcam(); setSelectedDashcam(null); }}
                  className="absolute top-3 right-3 p-1.5 bg-black/50 rounded-lg text-white hover:bg-black/70 transition-colors z-10"
                >
                  <span className="material-symbols-outlined text-[16px]">close</span>
                </button>
              </div>
            ) : (
              <div className="flex flex-col items-center justify-center py-16 text-center">
                {cameraError ? (
                  <>
                    <span className="material-symbols-outlined text-[40px] text-error mb-2">error</span>
                    <p className="text-error text-[12px] max-w-xs">{cameraError}</p>
                    <button onClick={() => { setCameraError(""); startCamera(); }}
                      className="mt-3 px-4 py-1.5 bg-surface-container-high rounded-lg text-[11px] font-bold">Try Again</button>
                  </>
                ) : (
                  <>
                    <span className="material-symbols-outlined text-[40px] text-on-surface-variant mb-2">videocam</span>
                    <p className="text-on-surface-variant text-[12px]">Configure and start the stream above</p>
                  </>
                )}
              </div>
            )}
            {isStreaming && connectionStatus === "connected" && (
              <div className="absolute top-3 left-3 flex items-center gap-2 bg-black/60 backdrop-blur-sm px-2.5 py-1.5 rounded-lg">
                <div className="w-2 h-2 bg-red-500 rounded-full animate-pulse" />
                <span className="text-[10px] font-bold text-white">LIVE</span>
                <span className="text-[9px] text-slate-300 font-mono">{formatDuration(sessionDuration)}</span>
                <span className="text-[9px] text-emerald-300 font-mono ml-2">{serverFps} FPS</span>
                <span className="text-[9px] text-slate-400 font-mono ml-2">#{frameCount}</span>
              </div>
            )}
          </div>

          {(isStreaming || (selectedDashcam && dashcamStatus === "streaming" && frameCount > 0)) && (
            <div className="bg-white border border-outline-variant rounded-xl p-3 mb-3 grid grid-cols-3 gap-2 text-center text-[11px]">
              <div><span className="font-bold font-mono text-lg">{traffic.vehicle_count}</span><div className="text-[9px] text-on-surface-variant">Vehicles</div></div>
              <div><span className="font-bold font-mono text-lg text-yellow-600">{traffic.stopped_count || dashcamPedestrians.length}</span><div className="text-[9px] text-on-surface-variant">{selectedDashcam ? "Pedestrians" : "Stopped"}</div></div>
              <div><span className={`font-bold text-lg ${trafficLevelColor(traffic.level)}`}>{traffic.level}</span><div className="text-[9px] text-on-surface-variant">Traffic</div></div>
            </div>
          )}

          {isStreaming && enhancement && !selectedDashcam && (
            <div className="mb-4 border border-outline-variant bg-surface-container-low p-3">
              <div className="mb-2 flex items-center justify-between gap-2">
                <div className="flex items-center gap-2">
                  <span className="material-symbols-outlined text-[17px] text-primary">auto_fix_high</span>
                  <span className="text-[11px] font-bold uppercase text-on-surface">Adaptive Vision</span>
                </div>
                <span className={`text-[9px] font-bold uppercase ${enhancement.applied ? "text-emerald-600" : "text-on-surface-variant"}`}>
                  {enhancement.applied ? "Enhanced" : "Normal"}
                </span>
              </div>
              <div className="grid grid-cols-3 gap-2 text-center">
                <div><div className="font-mono text-[12px] font-bold">{enhancement.brightness}</div><div className="text-[8px] text-on-surface-variant">Brightness</div></div>
                <div><div className="font-mono text-[12px] font-bold">{enhancement.contrast}</div><div className="text-[8px] text-on-surface-variant">Contrast</div></div>
                <div><div className="font-mono text-[12px] font-bold">{enhancement.sharpness}</div><div className="text-[8px] text-on-surface-variant">Sharpness</div></div>
              </div>
              {enhancement.modes.length > 0 && (
                <div className="mt-2 flex flex-wrap gap-1">
                  {enhancement.modes.map((mode) => (
                    <span key={mode} className="border border-primary/20 bg-primary/5 px-1.5 py-0.5 text-[8px] font-semibold text-primary">
                      {mode.replace(/_/g, " ")}
                    </span>
                  ))}
                </div>
              )}
            </div>
          )}

          <div className="flex gap-2 mb-4">
            {!selectedDashcam && (
              <button onClick={cameraActive ? stopCamera : startCamera}
                disabled={sourceMode === "stream" && !streamUrl.trim()}
                className={`flex-1 flex items-center justify-center gap-2 py-2.5 text-[12px] font-bold rounded-xl transition-all disabled:opacity-40 ${
                  cameraActive ? "bg-red-500 text-white" : "bg-primary text-white"
                }`}>
                <span className="material-symbols-outlined text-[16px]">{cameraActive ? "videocam_off" : "videocam"}</span>
                {cameraActive ? "Stop" : sourceMode === "stream" ? "Connect Stream" : "Start Camera"}
              </button>
            )}
            {selectedDashcam && (
              <button onClick={() => { disconnectDashcam(); setSelectedDashcam(null); }}
                className="flex-1 flex items-center justify-center gap-2 py-2.5 text-[12px] font-bold rounded-xl transition-all bg-surface-container-high text-on-surface">
                <span className="material-symbols-outlined text-[16px]">arrow_back</span>
                Back to Dashcams
              </button>
            )}
            {sourceMode === "browser" && cameraActive && (
              <button onClick={switchCamera}
                className="px-4 py-2.5 bg-surface-container-high rounded-xl text-[12px] font-bold">
                <span className="material-symbols-outlined text-[16px]">flip_camera_android</span>
              </button>
            )}
            {cameraActive && (
              <button onClick={() => setShowSettings(!showSettings)}
                className="px-3 py-2.5 bg-surface-container-high rounded-xl text-[11px] font-bold whitespace-nowrap">
                {preset.label}
              </button>
            )}
          </div>

          {cameraActive && showSettings && (
            <div className="mb-4 p-3 bg-surface-container-low rounded-xl border border-outline-variant">
              <div className="grid grid-cols-4 gap-1 mb-2">
                {QUALITY_PRESETS.map((p, i) => (
                  <button key={p.label} onClick={() => setQualityPreset(i)}
                    className={`py-1.5 text-[10px] font-bold rounded-lg border transition-all ${qualityPreset === i ? "bg-primary text-white border-primary" : "bg-white text-on-surface-variant border-outline-variant"}`}>
                    {p.label}
                  </button>
                ))}
              </div>
              <div className="flex items-center gap-2">
                <span className="text-[10px] text-on-surface-variant">FPS: {targetFps}</span>
                <input type="range" min={3} max={24} value={targetFps}
                  onChange={(e) => setTargetFps(Number(e.target.value))} className="flex-1 accent-primary" />
              </div>
            </div>
          )}

          {detections.length > 0 && !selectedDashcam && (
            <div className="mb-4">
              <h3 className="text-[11px] font-bold uppercase text-on-surface mb-2">Detections</h3>
              <div className="flex flex-col gap-1 max-h-32 overflow-y-auto">
                {detections.map((d) => (
                  <div key={d.track_id}
                    className={`flex items-center justify-between p-2 rounded-lg text-[10px] ${d.violation ? "bg-red-50 border border-red-200" : "bg-surface-container-low border border-outline-variant"}`}>
                    <div className="flex items-center gap-2">
                      <span className="font-mono text-on-surface-variant">#{d.track_id}</span>
                      <span className="font-semibold capitalize">{d.class_name}</span>
                      {d.is_stopped && <span className="text-yellow-600 font-bold">STOP {d.stationary_seconds}s</span>}
                    </div>
                    <div className="flex items-center gap-2">
                      {d.violation && <span className="text-red-600 font-bold uppercase">{d.violation.replace(/_/g, " ")}</span>}
                      <span className="text-on-surface-variant">{Math.round(d.confidence * 100)}%</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {selectedDashcam && dashcamStatus === "streaming" && frameCount > 0 && (
            <div className="mb-4 space-y-3">
              {/* Detection Summary */}
              <div className="grid grid-cols-2 gap-2">
                <div className="bg-surface-container-low rounded-xl p-2.5 text-[10px]">
                  <div className="flex items-center gap-1.5 mb-1">
                    <span className="w-2 h-2 rounded-full" style={{ backgroundColor: "#22c55e" }} />
                    <span className="font-bold text-on-surface">Vehicles</span>
                  </div>
                  <span className="font-mono text-lg font-bold">{dashcamDetections.length}</span>
                </div>
                <div className="bg-surface-container-low rounded-xl p-2.5 text-[10px]">
                  <div className="flex items-center gap-1.5 mb-1">
                    <span className="w-2 h-2 rounded-full" style={{ backgroundColor: "#06b6d4" }} />
                    <span className="font-bold text-on-surface">Pedestrians</span>
                  </div>
                  <span className="font-mono text-lg font-bold">{dashcamPedestrians.length}</span>
                </div>
                <div className="bg-surface-container-low rounded-xl p-2.5 text-[10px]">
                  <div className="flex items-center gap-1.5 mb-1">
                    <span className="w-2 h-2 rounded-full" style={{ backgroundColor: "#f97316" }} />
                    <span className="font-bold text-on-surface">Bicycles</span>
                  </div>
                  <span className="font-mono text-lg font-bold">{dashcamBicycles.length}</span>
                </div>
                <div className="bg-surface-container-low rounded-xl p-2.5 text-[10px]">
                  <div className="flex items-center gap-1.5 mb-1">
                    <span className={`w-2 h-2 rounded-full ${dashcamTrafficLightColor === "red" ? "bg-red-500" : dashcamTrafficLightColor === "green" ? "bg-green-500" : "bg-yellow-500"}`} />
                    <span className="font-bold text-on-surface">Traffic Light</span>
                  </div>
                  <span className="font-mono text-lg font-bold capitalize">{dashcamTrafficLightColor} ({dashcamTrafficLights.length})</span>
                </div>
              </div>

              {/* Traffic Signs */}
              {dashcamTrafficSigns.length > 0 && (
                <div>
                  <h4 className="text-[9px] font-bold uppercase text-on-surface-variant mb-1 tracking-wider">Traffic Signs</h4>
                  <div className="flex flex-wrap gap-1">
                    {dashcamTrafficSigns.map((s: any, i: number) => (
                      <span key={i} className="px-2 py-0.5 bg-purple-50 border border-purple-200 rounded text-[9px] font-semibold text-purple-700">
                        {s.class_name} {Math.round(s.confidence * 100)}%
                      </span>
                    ))}
                  </div>
                </div>
              )}

               {/* Vehicle List */}
              {dashcamDetections.length > 0 && (
                <div>
                  <h4 className="text-[9px] font-bold uppercase text-on-surface-variant mb-1 tracking-wider">Vehicles</h4>
                  <div className="flex flex-col gap-0.5 max-h-24 overflow-y-auto">
                    {dashcamDetections.slice(0, 15).map((d: any, i: number) => (
                      <div key={i} className="flex items-center justify-between p-1.5 rounded bg-surface-container-low text-[9px]">
                        <div className="flex items-center gap-1.5">
                          <span className="w-1.5 h-1.5 rounded-full" style={{ backgroundColor: "#3b82f6" }} />
                          <span className="font-semibold capitalize">{d.class_name}</span>
                          {d.track_id && <span className="font-mono text-[8px] opacity-75">#{d.track_id}</span>}
                          {d.plate_number && <span className="bg-slate-800 text-white font-mono text-[8px] px-1 py-0.5 rounded border border-slate-700 ml-1">{d.plate_number}</span>}
                          {d.lane && <span className="text-on-surface-variant">[{d.lane}]</span>}
                        </div>
                        <span className="text-on-surface-variant">{Math.round(d.confidence * 100)}%</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}

          {!cameraActive && !selectedDashcam && (
            <div className="mb-4">
              <div className="flex items-center gap-2 mb-3">
                <span className="material-symbols-outlined text-[16px] text-primary">dashboard</span>
                <h3 className="text-[11px] font-bold uppercase text-on-surface">Live Dashcam</h3>
              </div>

              {dashcamSourcesLoading ? (
                <div className="rounded-xl border border-outline-variant bg-surface-container-low p-3 text-[11px] font-semibold text-on-surface-variant">
                  Loading dashcam videos...
                </div>
              ) : dashcamSourcesError ? (
                <div className="rounded-xl border border-red-200 bg-red-50 p-3 text-[11px] font-semibold text-red-700">
                  Failed to load dashcam videos: {dashcamSourcesError}
                </div>
              ) : activeDashcams.length === 0 ? (
                <div className="rounded-xl border border-outline-variant bg-surface-container-low p-3 text-[11px] font-semibold text-on-surface-variant">
                  No dashcam videos found.
                </div>
              ) : (
                <div className="grid grid-cols-2 gap-2">
                  {activeDashcams.map((cam) => (
                    <button
                      key={cam.id}
                      onClick={() => handleDashcamClick(cam)}
                      className="text-left bg-white rounded-xl border border-outline-variant overflow-hidden hover:shadow-md hover:border-primary transition-all group"
                    >
                      <div className="aspect-video bg-slate-900 relative overflow-hidden flex items-center justify-center">
                        <span className="material-symbols-outlined text-[40px] text-slate-600 group-hover:text-primary transition-colors">directions_bus</span>
                        <div className="absolute inset-0 bg-gradient-to-t from-black/50 to-transparent" />
                        <div className="absolute top-2 left-2 flex items-center gap-1.5">
                          <span className="flex items-center gap-1 px-2 py-0.5 bg-emerald-500/80 backdrop-blur-sm rounded text-[8px] font-bold text-white">
                            <span className="w-1.5 h-1.5 bg-white rounded-full animate-pulse" />AI
                          </span>
                        </div>
                        <div className="absolute bottom-2 left-2 right-2">
                          <div className="flex items-center gap-1.5">
                            <div className="w-2 h-2 rounded-full" style={{ backgroundColor: cam.color }} />
                            <span className="text-[11px] font-bold text-white drop-shadow-lg">{cam.name}</span>
                          </div>

                        </div>
                      </div>
                      <div className="p-2">
                        <p className="text-[9px] text-on-surface-variant truncate">{cam.description}</p>
                        <p className="text-[8px] font-semibold text-on-surface mt-0.5">{cam.route}</p>
                      </div>
                    </button>
                  ))}
                </div>
              )}
            </div>
          )}

          {liveEvents.length > 0 && !selectedDashcam && (
            <div>
              <h3 className="text-[11px] font-bold uppercase text-on-surface mb-2 flex items-center gap-1.5">
                <span className="material-symbols-outlined text-[16px] text-error">warning</span>
                Violation Events
                <span className="ml-auto bg-red-50 text-red-600 text-[9px] font-bold px-2 py-0.5 rounded-full">{liveEvents.length}</span>
              </h3>
              <div className="flex flex-col gap-1.5 max-h-48 overflow-y-auto">
                {liveEvents.map((evt) => (
                  <div key={evt.event_id} className="bg-red-50 border border-red-200 rounded-xl p-2.5 text-[11px]">
                    <div className="flex justify-between items-center mb-0.5">
                      <span className="font-bold text-red-600 uppercase text-[10px]">{evt.violation_type?.replace(/_/g, " ")}</span>
                      <span className="text-[9px] text-on-surface-variant">{new Date(evt.timestamp).toLocaleTimeString()}</span>
                    </div>
                    <div className="flex items-center gap-2 text-[10px] text-on-surface-variant">
                      <span className="capitalize">{evt.vehicle_type}</span>
                      <span className="font-semibold text-on-surface">{evt.plate_number || "N/A"}</span>
                    </div>
                    {evt.contextual_reasoning && (
                      <div className="mt-2 border-t border-red-200 pt-2 text-[9px] text-on-surface-variant">
                        <div className="mb-1 flex items-center justify-between gap-2">
                          <span className="font-bold uppercase text-on-surface">Contextual AI</span>
                          <span className="font-mono uppercase text-primary">
                            {evt.contextual_reasoning.reasoning_source || "local"} {Math.round(evt.contextual_reasoning.confidence * 100)}%
                          </span>
                        </div>
                        <p>{evt.contextual_reasoning.reason}</p>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
