import { useRef, useEffect, useState, useCallback } from "react";
import type { PatrolVehicle } from "../Map/PatrolMarkers";

interface Props {
  patrol: PatrolVehicle | null;
  onClose: () => void;
  onViolationDetected?: (violation: {
    source: string;
    type: string;
    detail: string;
    plate?: string;
    vehicleType?: string;
    evidenceImage?: string;
    evidenceSize?: [number, number];
    plateCrop?: string;
    plateBbox?: [number, number, number, number];
    plateConfidence?: number;
    plateNote?: string;
    videoTimeSeconds?: number;
    videoFile?: string;
  }) => void;
}

const WS_BASE = import.meta.env.VITE_WS_URL || "ws://localhost:8000/ws";

export function PatrolVideoModal({ patrol, onClose, onViolationDetected }: Props) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const overlayCanvasRef = useRef<HTMLCanvasElement>(null);
  const wsRef = useRef<WebSocket | null>(null);

  const [aiEnabled, setAiEnabled] = useState(false);
  const [aiStatus, setAiStatus] = useState<"off" | "connecting" | "active">("off");
  const [aiFps, setAiFps] = useState(0);
  const [hasAiFrame, setHasAiFrame] = useState(false);
  const [violations, setViolations] = useState<{description: string; type: string; time: number}[]>([]);
  const loggedViolationIdsRef = useRef<Set<string>>(new Set());
  const onViolationDetectedRef = useRef(onViolationDetected);

  useEffect(() => {
    onViolationDetectedRef.current = onViolationDetected;
  }, [onViolationDetected]);

  // FIX #2: Reset AI state whenever patrol changes
  useEffect(() => {
    stopAi();
    setAiEnabled(false);
    setAiStatus("off");
    setHasAiFrame(false);
    setAiFps(0);
    setViolations([]);
    loggedViolationIdsRef.current.clear();

    if (patrol && videoRef.current) {
      videoRef.current.currentTime = 0;
      videoRef.current.play().catch(() => {});
    }
  }, [patrol?.id]);

  // Close on Escape
  useEffect(() => {
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, [onClose]);

  // Cleanup on unmount
  useEffect(() => {
    return () => { stopAi(); };
  }, []);

  const renderAiFrame = useCallback((data: ArrayBuffer) => {
    const canvas = overlayCanvasRef.current;
    if (!canvas) return;
    const blob = new Blob([data], { type: "image/jpeg" });
    createImageBitmap(blob)
      .then((bitmap) => {
        if (canvas.width !== bitmap.width || canvas.height !== bitmap.height) {
          canvas.width = bitmap.width;
          canvas.height = bitmap.height;
        }
        const ctx = canvas.getContext("2d");
        if (ctx) {
          ctx.clearRect(0, 0, canvas.width, canvas.height);
          ctx.drawImage(bitmap, 0, 0);
        }
        bitmap.close();
        setHasAiFrame(true);
      })
      .catch(() => {});
  }, []);

  const startAi = useCallback(() => {
    if (!patrol) return;
    setAiStatus("connecting");
    setHasAiFrame(false);

    const ws = new WebSocket(`${WS_BASE}/dashcam`);
    ws.binaryType = "arraybuffer";
    wsRef.current = ws;

    ws.onopen = () => {
      ws.send(JSON.stringify({ video_file: patrol.videoFile }));
    };

    ws.onmessage = (event) => {
      if (event.data instanceof ArrayBuffer) {
        renderAiFrame(event.data);
        return;
      }
      try {
        const data = JSON.parse(event.data);
        if (data.type === "connected" || data.type === "resolved") {
          setAiStatus("active");
        } else if (data.type === "frame_result") {
          setAiFps(data.fps || 0);
          // Capture violations
          if (data.violations && data.violations.length > 0) {
            const newVios = data.violations.map((v: any) => ({
              description: v.description || v.violation_type,
              type: v.violation_type,
              time: Date.now(),
            }));
            setViolations(prev => [...newVios, ...prev].slice(0, 20));
            for (const vio of data.violations) {
              const eventId = vio.event_id || `${patrol.videoFile}-${vio.violation_type}-${vio.video_time_seconds ?? Date.now()}`;
              if (loggedViolationIdsRef.current.has(eventId)) continue;
              loggedViolationIdsRef.current.add(eventId);
              onViolationDetectedRef.current?.({
                source: `Dashcam: ${patrol.label}`,
                type: vio.violation_type,
                detail: vio.description || vio.violation_type,
                plate: vio.plate_number || undefined,
                vehicleType: vio.vehicle_type || undefined,
                evidenceImage: vio.evidence_image || undefined,
                evidenceSize: vio.evidence_size || undefined,
                plateCrop: vio.plate_crop || undefined,
                plateBbox: vio.plate_bbox || undefined,
                plateConfidence: vio.plate_confidence ?? undefined,
                plateNote: vio.plate_note || undefined,
                videoTimeSeconds: vio.video_time_seconds ?? undefined,
                videoFile: patrol.videoFile,
              });
            }
          }
        }
      } catch {}
    };

    ws.onerror = () => setAiStatus("off");
    ws.onclose = () => {
      setAiStatus("off");
      wsRef.current = null;
    };
  }, [patrol, renderAiFrame]);

  useEffect(() => {
    if (!patrol) return;
    setAiEnabled(true);
    const timer = window.setTimeout(() => startAi(), 250);
    return () => window.clearTimeout(timer);
  }, [patrol?.id, startAi]);

  const stopAi = useCallback(() => {
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
    setAiStatus("off");
    setAiFps(0);
    setHasAiFrame(false);
    const canvas = overlayCanvasRef.current;
    if (canvas) {
      const ctx = canvas.getContext("2d");
      if (ctx) ctx.clearRect(0, 0, canvas.width, canvas.height);
    }
  }, []);

  const toggleAi = useCallback(() => {
    if (aiEnabled) {
      stopAi();
      setAiEnabled(false);
    } else {
      setAiEnabled(true);
      startAi();
    }
  }, [aiEnabled, startAi, stopAi]);

  if (!patrol) return null;

  const statusLabel =
    aiStatus === "active" && hasAiFrame
      ? `${aiFps.toFixed(1)} FPS`
      : aiStatus === "connecting" || (aiStatus === "active" && !hasAiFrame)
      ? "Memproses..."
      : "";

  return (
    <div
      style={{
        position: "fixed",
        inset: 0,
        zIndex: 9999,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        background: "rgba(0,0,0,0.8)",
        backdropFilter: "blur(6px)",
      }}
      onClick={onClose}
    >
      <div
        style={{
          background: "#111827",
          borderRadius: 12,
          overflow: "hidden",
          maxWidth: 960,
          width: "94vw",
          maxHeight: "90vh",
          display: "flex",
          flexDirection: "column" as const,
          boxShadow: "0 20px 60px rgba(0,0,0,0.5)",
          border: "1px solid rgba(255,255,255,0.08)",
        }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div
          style={{
            padding: "12px 16px",
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            borderBottom: "1px solid rgba(255,255,255,0.06)",
            flexShrink: 0,
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <div
              style={{
                width: 32,
                height: 32,
                borderRadius: 8,
                background: patrol.color,
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
              }}
            >
              <span
                className="material-symbols-outlined"
                style={{ color: "white", fontSize: 18 }}
              >
                directions_car
              </span>
            </div>
            <div>
              <h3 style={{ color: "white", fontSize: 14, fontWeight: 600, margin: 0 }}>
                {patrol.label}
              </h3>
              <p style={{ color: "rgba(255,255,255,0.45)", fontSize: 11, margin: 0 }}>
                {patrol.description}
              </p>
            </div>
          </div>

          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            {/* AI Toggle */}
            <button
              onClick={toggleAi}
              style={{
                display: "flex",
                alignItems: "center",
                gap: 5,
                padding: "5px 12px",
                borderRadius: 6,
                border: `1px solid ${aiEnabled ? patrol.color : "rgba(255,255,255,0.12)"}`,
                background: aiEnabled ? `${patrol.color}18` : "rgba(255,255,255,0.04)",
                color: aiEnabled ? patrol.color : "rgba(255,255,255,0.55)",
                cursor: "pointer",
                fontSize: 11,
                fontWeight: 600,
                transition: "all 0.2s",
              }}
            >
              <span
                className="material-symbols-outlined"
                style={{ fontSize: 16 }}
              >
                {aiEnabled ? "visibility" : "visibility_off"}
              </span>
              AI Detection
              {statusLabel && (
                <span style={{ opacity: 0.7, fontSize: 10, marginLeft: 2 }}>
                  {statusLabel}
                </span>
              )}
            </button>

            {/* Close */}
            <button
              onClick={onClose}
              style={{
                background: "rgba(255,255,255,0.06)",
                border: "1px solid rgba(255,255,255,0.08)",
                borderRadius: 6,
                width: 32,
                height: 32,
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                cursor: "pointer",
                color: "rgba(255,255,255,0.5)",
                transition: "all 0.2s",
              }}
              onMouseEnter={(e) => {
                e.currentTarget.style.background = "rgba(255,255,255,0.12)";
                e.currentTarget.style.color = "white";
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.background = "rgba(255,255,255,0.06)";
                e.currentTarget.style.color = "rgba(255,255,255,0.5)";
              }}
            >
              <span className="material-symbols-outlined" style={{ fontSize: 18 }}>close</span>
            </button>
          </div>
        </div>

        {/* Video + AI Overlay — FIX #1: video always visible until AI frame arrives */}
        <div
          style={{
            position: "relative",
            background: "black",
            flexShrink: 1,
            minHeight: 0,
            overflow: "hidden",
            lineHeight: 0,
          }}
        >
          <video
            ref={videoRef}
            src={patrol.videoSrc}
            controls={!aiEnabled || !hasAiFrame}
            autoPlay
            loop
            muted
            playsInline
            style={{
              width: "100%",
              display: aiEnabled && hasAiFrame ? "none" : "block",
              objectFit: "contain",
            }}
          />

          {aiEnabled && hasAiFrame && (
            <canvas
              ref={overlayCanvasRef}
              style={{
                width: "100%",
                display: "block",
                objectFit: "contain",
              }}
            />
          )}

          {/* Hidden canvas for receiving frames before display */}
          {aiEnabled && !hasAiFrame && (
            <canvas
              ref={overlayCanvasRef}
              style={{ display: "none" }}
            />
          )}

          {/* Status overlay */}
          <div
            style={{
              position: "absolute",
              top: 8,
              left: 8,
              display: "flex",
              gap: 6,
            }}
          >
            <div
              style={{
                background: "rgba(0,0,0,0.6)",
                color: "white",
                fontSize: 10,
                fontWeight: 600,
                padding: "3px 8px",
                borderRadius: 4,
                display: "flex",
                alignItems: "center",
                gap: 4,
                backdropFilter: "blur(4px)",
              }}
            >
              <span
                style={{
                  width: 5,
                  height: 5,
                  borderRadius: "50%",
                  background: "#4caf50",
                  display: "inline-block",
                }}
              />
              DASHCAM
            </div>

            {aiEnabled && (
              <div
                style={{
                  background: "rgba(0,0,0,0.6)",
                  color: hasAiFrame ? patrol.color : "rgba(255,255,255,0.6)",
                  fontSize: 10,
                  fontWeight: 600,
                  padding: "3px 8px",
                  borderRadius: 4,
                  backdropFilter: "blur(4px)",
                }}
              >
                {hasAiFrame ? `AI ${aiFps.toFixed(1)} FPS` : "AI Loading..."}
              </div>
            )}
          </div>
        </div>

        {/* Footer — Violation Log */}
        <div
          style={{
            borderTop: "1px solid rgba(255,255,255,0.06)",
            flexShrink: 0,
            maxHeight: aiEnabled && violations.length > 0 ? 120 : 36,
            overflow: "hidden",
            transition: "max-height 0.3s ease",
          }}
        >
          <div
            style={{
              padding: "6px 16px",
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
            }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
              <span
                className="material-symbols-outlined"
                style={{
                  fontSize: 14,
                  color: violations.length > 0 ? "#ef5350" : "rgba(255,255,255,0.3)",
                }}
              >
                {violations.length > 0 ? "warning" : "shield"}
              </span>
              <span
                style={{
                  color: violations.length > 0 ? "#ef5350" : "rgba(255,255,255,0.35)",
                  fontSize: 10,
                  fontWeight: 600,
                }}
              >
                {violations.length > 0
                  ? `${violations.length} VIOLATION${violations.length > 1 ? "S" : ""}`
                  : aiEnabled
                  ? "Monitoring..."
                  : "Klik AI Detection untuk aktivasi"}
              </span>
            </div>
            <span
              style={{
                color: aiEnabled ? patrol.color : "rgba(255,255,255,0.25)",
                fontSize: 10,
                fontWeight: 500,
              }}
            >
              {aiEnabled ? "YOLO Detection Active" : ""}
            </span>
          </div>

          {/* Violation list */}
          {violations.length > 0 && (
            <div
              style={{
                maxHeight: 80,
                overflowY: "auto",
                padding: "0 16px 6px",
              }}
            >
              {violations.slice(0, 10).map((v, i) => (
                <div
                  key={`${v.time}-${i}`}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: 6,
                    padding: "3px 0",
                    borderBottom: "1px solid rgba(255,255,255,0.04)",
                    fontSize: 10,
                  }}
                >
                  <span
                    style={{
                      width: 4,
                      height: 4,
                      borderRadius: "50%",
                      background:
                        v.type === "red_light_violation"
                          ? "#f44336"
                          : v.type === "shoulder_violation"
                          ? "#ff9800"
                          : v.type === "illegal_maneuver"
                          ? "#e91e63"
                          : "#ffc107",
                      flexShrink: 0,
                    }}
                  />
                  <span style={{ color: "rgba(255,255,255,0.5)", flexShrink: 0 }}>
                    {new Date(v.time).toLocaleTimeString("id-ID", {
                      hour: "2-digit",
                      minute: "2-digit",
                      second: "2-digit",
                    })}
                  </span>
                  <span style={{ color: "rgba(255,255,255,0.8)" }}>{v.description}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
