import { useCallback, useEffect, useRef, useState } from "react";

import type { ClientMessage, ServerMessage } from "../api/contract";

const RECONNECT_MS = [1000, 2000, 5000];

/** Ignore every event of a socket we're done with; one still connecting closes once it opens. */
function closeQuietly(socket: WebSocket) {
  socket.onmessage = null;
  socket.onclose = null;
  socket.onerror = null;
  if (socket.readyState === WebSocket.CONNECTING) {
    // Closing now would log "closed before the connection is established" on every StrictMode remount.
    socket.onopen = () => socket.close();
  } else {
    socket.onopen = null;
    socket.close();
  }
}

/** The /live socket: JSON text both ways, reconnecting after 1 s, 2 s, then every 5 s. Null url: closed. */
export function useLiveSocket(url: string | null, onMessage: (message: ServerMessage) => void) {
  const [open, setOpen] = useState(false);
  const socket = useRef<WebSocket | null>(null);
  const latest = useRef(onMessage);
  useEffect(() => {
    latest.current = onMessage;
  });

  useEffect(() => {
    if (!url) return;
    let disposed = false;
    let attempt = 0;
    let retry = 0;

    const connect = () => {
      const ws = new WebSocket(url);
      socket.current = ws;
      ws.onopen = () => {
        attempt = 0;
        setOpen(true);
      };
      ws.onmessage = (event: MessageEvent) => {
        if (typeof event.data !== "string") return;
        let message: ServerMessage;
        try {
          message = JSON.parse(event.data);
        } catch {
          console.warn("Name Tags live: a message that isn't JSON", event.data);
          return;
        }
        if (typeof message?.type === "string") latest.current(message);
      };
      ws.onclose = () => {
        if (socket.current === ws) socket.current = null;
        setOpen(false);
        if (disposed) return;
        retry = window.setTimeout(connect, RECONNECT_MS[Math.min(attempt, RECONNECT_MS.length - 1)]);
        attempt += 1;
      };
    };

    connect();
    return () => {
      disposed = true;
      window.clearTimeout(retry);
      const ws = socket.current;
      socket.current = null;
      if (ws) closeQuietly(ws);
      setOpen(false);
    };
  }, [url]);

  /** False (and dropped) unless the socket is open. */
  const send = useCallback((message: ClientMessage): boolean => {
    const ws = socket.current;
    if (!ws || ws.readyState !== WebSocket.OPEN) return false;
    ws.send(JSON.stringify(message));
    return true;
  }, []);

  return { open, send };
}
