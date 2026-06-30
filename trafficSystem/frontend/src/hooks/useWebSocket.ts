import { useEffect, useRef } from "react";
import type { WSMessage } from "../types";

export function useWebSocket(onMessage: (msg: WSMessage) => void) {
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeout = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const onMessageRef = useRef(onMessage);

  // Keep onMessageRef up to date with the latest onMessage callback
  useEffect(() => {
    onMessageRef.current = onMessage;
  }, [onMessage]);

  useEffect(() => {
    const connect = () => {
      const wsUrl = import.meta.env.VITE_WS_URL || `${window.location.protocol === "https:" ? "wss:" : "ws:"}//${window.location.host}/ws`;
      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      ws.onmessage = (event) => {
        try {
          const data: WSMessage = JSON.parse(event.data);
          if (data.type !== "ping") {
            onMessageRef.current(data);
          }
        } catch (e) {
          console.error("WS parse error:", e);
        }
      };

      ws.onclose = () => {
        reconnectTimeout.current = setTimeout(connect, 3000);
      };
    };

    connect();

    return () => {
      if (wsRef.current) {
        wsRef.current.close();
      }
      clearTimeout(reconnectTimeout.current);
    };
  }, []);
}
