import type { Notification } from "../../hooks/useNotifications";

interface StyleConfig {
  bg: string;
  border: string;
  dot: string;
  text: string;
  label: string;
  progressBg: string;
}

const SEVERITY_STYLES: Record<string, StyleConfig> = {
  low:    { bg: "#fffbeb", border: "#f59e0b", dot: "#f59e0b", text: "#78350f", label: "#b45309", progressBg: "#fef08a" },
  medium: { bg: "#fff7ed", border: "#f97316", dot: "#f97316", text: "#7c2d12", label: "#ea580c", progressBg: "#ffedd5" },
  high:   { bg: "#fef2f2", border: "#ef4444", dot: "#ef4444", text: "#7f1d1d", label: "#dc2626", progressBg: "#fee2e2" },
};

interface Props {
  notifications: Notification[];
  onDismiss: (id: string) => void;
}

export function NotificationPanel({ notifications, onDismiss }: Props) {
  if (notifications.length === 0) return null;

  return (
    <div
      style={{
        position: "absolute",
        top: 80,
        right: 16,
        zIndex: 500,
        display: "flex",
        flexDirection: "column",
        gap: 8,
        maxWidth: 320,
        pointerEvents: "none",
      }}
    >
      {notifications.map((notification) => {
        const style = SEVERITY_STYLES[notification.severity] || SEVERITY_STYLES.medium;
        return (
          <div
            key={notification.id}
            style={{
              background: style.bg,
              border: `1px solid ${style.border}`,
              borderRadius: 12,
              padding: "12px 14px",
              paddingRight: 32, // Give space for close button
              animation: "slideIn 0.2s ease",
              position: "relative",
              pointerEvents: "none",
              boxShadow: "0 10px 15px -3px rgba(0,0,0,0.05), 0 4px 6px -4px rgba(0,0,0,0.05)"
            }}
          >
            {/* Close Button */}
            <button
              onClick={() => onDismiss(notification.id)}
              style={{
                position: "absolute",
                top: 8,
                right: 8,
                background: "transparent",
                border: "none",
                color: "#64748b",
                cursor: "pointer",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                padding: 2,
                pointerEvents: "auto",
              }}
              className="material-symbols-outlined hover:text-slate-900"
            >
              <span style={{ fontSize: 14 }}>close</span>
            </button>

            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <span
                style={{
                  width: 8,
                  height: 8,
                  borderRadius: "50%",
                  background: style.dot,
                  flexShrink: 0,
                  animation: "pulse 1.5s infinite",
                }}
              />
              <span style={{ color: style.text, fontSize: 12, fontWeight: 700 }}>
                {notification.message}
              </span>
            </div>

            {/* Confidence Bar & Signal Count */}
            <div style={{ marginTop: 6, marginLeft: 16 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                <span style={{ color: "#64748b", fontSize: 10, fontWeight: 500 }}>Confidence</span>
                <div style={{
                  flex: 1, height: 4, background: "#e2e8f0", borderRadius: 2, overflow: "hidden"
                }}>
                  <div style={{
                    width: `${(notification.confidence_score ?? 0.5) * 100}%`,
                    height: "100%",
                    background: (notification.confidence_score ?? 0.5) > 0.7 ? "#ef4444"
                      : (notification.confidence_score ?? 0.5) > 0.4 ? "#f97316" : "#64748b",
                    transition: "width 0.3s ease",
                  }} />
                </div>
                <span style={{ color: "#475569", fontSize: 10, minWidth: 32, textAlign: "right", fontWeight: 600 }}>
                  {Math.round((notification.confidence_score ?? 0.5) * 100)}%
                </span>
              </div>
              {(notification.source_count ?? 1) > 1 && (
                <div style={{ color: "#64748b", fontSize: 9, marginTop: 2, fontWeight: 500, display: "flex", alignItems: "center", gap: 3 }}>
                  <span className="material-symbols-outlined" style={{ fontSize: 11 }}>hub</span>
                  {notification.source_count} sinyal digabungkan
                </div>
              )}
            </div>

            <div style={{ color: "#94a3b8", fontSize: 9, marginTop: 4, marginLeft: 16, fontWeight: 500 }}>
              {notification.timestamp.toLocaleTimeString("id-ID")}
            </div>
          </div>
        );
      })}
      <style>{`
        @keyframes slideIn {
          from { transform: translateX(100%); opacity: 0; }
          to   { transform: translateX(0);    opacity: 1; }
        }
        @keyframes pulse {
          0% { transform: scale(1); opacity: 1; }
          50% { transform: scale(1.3); opacity: 0.5; }
          100% { transform: scale(1); opacity: 1; }
        }
      `}</style>
    </div>
  );
}
