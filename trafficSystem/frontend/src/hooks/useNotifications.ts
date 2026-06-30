import { useState, useCallback } from "react";
import type { WSMessage } from "../types";

export interface Notification {
  id: string;
  message: string;
  severity: "low" | "medium" | "high";
  timestamp: Date;
  confidence_score?: number;
  source_count?: number;
}

const VIOLATION_LABELS: Record<string, string> = {
  illegal_parking: "Parkir Liar",
  busway_violation: "Pelanggaran Jalur Busway",
  congestion: "Kemacetan Terdeteksi",
  wrong_way: "Lawan Arah",
  hazard_lights: "Lampu Hazard",
};

export function useNotifications() {
  const [notifications, setNotifications] = useState<Notification[]>([]);

  const addFromWSMessage = useCallback((msg: WSMessage) => {
    if (msg.type !== "incident" || !msg.payload) return;
    const v = msg.payload;

    const notif: Notification = {
      id: v.id,
      message: `${VIOLATION_LABELS[v.type] || v.type} terdeteksi di ${v.camera_id}`,
      severity: v.severity,
      timestamp: new Date(),
      confidence_score: v.confidence_score,
      source_count: v.source_count,
    };

    setNotifications((prev) => {
      const filtered = prev.filter((item) => item.id !== notif.id);
      return [notif, ...filtered].slice(0, 5);
    });
  }, []);

  const dismissNotification = useCallback((id: string) => {
    setNotifications((prev) => prev.filter((item) => item.id !== id));
  }, []);

  return { notifications, addFromWSMessage, dismissNotification };
}
