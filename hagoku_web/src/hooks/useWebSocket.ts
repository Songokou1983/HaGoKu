import { useCallback, useSyncExternalStore } from "react";
import { useWorkspaceStore } from "../stores/workspace";
import type { WSMessage, ConnectionStatus } from "../types/events";

type Listener = (msg: WSMessage) => void;

const BASE_URL =
  import.meta.env.VITE_WS_URL ?? `ws://${window.location.hostname}:8000/ws`;

/** Global singleton WebSocket + listener registry */
let _ws: WebSocket | null = null;
let _status: ConnectionStatus = "connecting";
let _reconnectAttempt = 0;
let _reconnectTimer: ReturnType<typeof setTimeout> | null = null;
let _pingTimer: ReturnType<typeof setInterval> | null = null;
let _lastPong = 0;
const _listeners = new Set<Listener>();
const _statusSubs = new Set<() => void>();

/** Exponential backoff: 2^n seconds, max 30s, with ±20% jitter */
function backoffMs(attempt: number): number {
  const base = Math.min(2000 * 2 ** attempt, 30_000);
  const jitter = base * 0.2 * (Math.random() - 0.5);
  return Math.round(base + jitter);
}

function setStatus(s: ConnectionStatus) {
  if (_status === s) return;
  _status = s;
  _statusSubs.forEach((cb) => cb());
  // Sync to Zustand store (safe to call outside React)
  useWorkspaceStore.getState().setConnectionStatus(s);
}

function clearTimers() {
  if (_reconnectTimer) {
    clearTimeout(_reconnectTimer);
    _reconnectTimer = null;
  }
  if (_pingTimer) {
    clearInterval(_pingTimer);
    _pingTimer = null;
  }
}

function startPing() {
  if (_pingTimer) clearInterval(_pingTimer);
  _lastPong = Date.now();
  _pingTimer = setInterval(() => {
    if (_ws?.readyState === WebSocket.OPEN) {
      _ws.send(JSON.stringify({ cmd: "ping" }));
      // If no pong within 10s, treat as dead connection
      if (Date.now() - _lastPong > 10_000) {
        _ws.close();
      }
    }
  }, 30_000);
}

function broadcast(msg: WSMessage) {
  _listeners.forEach((fn) => fn(msg));
}

function connect() {
  clearTimers();
  if (_ws) {
    _ws.onclose = null; // suppress auto-reconnect from old instance
    _ws.close();
    _ws = null;
  }

  setStatus(_reconnectAttempt === 0 ? "connecting" : "reconnecting");
  const ws = new WebSocket(BASE_URL);
  _ws = ws;

  ws.onopen = () => {
    _reconnectAttempt = 0;
    _lastPong = Date.now();
    setStatus("connected");
    startPing();
  };

  ws.onmessage = (ev) => {
    try {
      const msg = JSON.parse(ev.data as string) as WSMessage;
      if (msg.type === "pong") {
        _lastPong = Date.now();
        return;
      }
      broadcast(msg);
    } catch {
      /* ignore malformed messages */
    }
  };

  ws.onclose = () => {
    _ws = null;
    clearTimers();
    setStatus("disconnected");
    // Schedule reconnect with exponential backoff
    const delay = backoffMs(_reconnectAttempt);
    _reconnectAttempt++;
    _reconnectTimer = setTimeout(connect, delay);
  };

  ws.onerror = () => {
    // onclose will fire after onerror; we just let onclose handle reconnect
    ws.close();
  };
}

/** Ensure singleton is connected — call once at app root before any useWebSocket usage. */
export function initWebSocket() {
  if (!_ws) connect();
}

export function useWebSocket() {
  const status = useSyncExternalStore(
    useCallback((cb: () => void) => {
      _statusSubs.add(cb);
      return () => {
        _statusSubs.delete(cb);
      };
    }, []),
    () => _status,
  );

  const onMessage = useCallback((fn: Listener) => {
    _listeners.add(fn);
    return () => {
      _listeners.delete(fn);
    };
  }, []);

  const send = useCallback((cmd: string, payload?: unknown) => {
    if (_ws?.readyState === WebSocket.OPEN) {
      _ws.send(JSON.stringify({ cmd, payload }));
    }
  }, []);

  return { status, send, onMessage };
}