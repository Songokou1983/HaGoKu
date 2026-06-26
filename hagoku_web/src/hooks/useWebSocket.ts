import { useCallback, useSyncExternalStore } from "react";
import { useWorkspaceStore } from "../stores/workspace";
import type { WSMessage, ConnectionStatus } from "../types/events";

type Listener = (msg: WSMessage) => void;

function defaultWsUrl(): string {
  const raw = import.meta.env.VITE_WS_URL;
  if (typeof raw === "string" && raw.trim()) return raw.trim();
  const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
  // 开发：与页面同源走 Vite `server.proxy['/ws']` → 后端 8000，避免直连 8000 被环境拦住时 send 静默失败
  if (import.meta.env.DEV) return `${proto}//${window.location.host}/ws`;
  // 生产默认仍对齐 README（API 在 hostname:8000）；同源反代部署请用 VITE_WS_URL 指到 /ws
  return `${proto}//${window.location.hostname}:8000/ws`;
}

const BASE_URL = defaultWsUrl();

/** Global singleton WebSocket + listener registry */
let _ws: WebSocket | null = null;
let _status: ConnectionStatus = "idle";
let _reconnectAttempt = 0;
let _reconnectTimer: ReturnType<typeof setTimeout> | null = null;
let _pingTimer: ReturnType<typeof setInterval> | null = null;
let _lastPong = 0;
const _pongCheckTimers: ReturnType<typeof setTimeout>[] = [];
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
  for (const t of _pongCheckTimers) {
    clearTimeout(t);
  }
  _pongCheckTimers.length = 0;
}

function startPing() {
  if (_pingTimer) clearInterval(_pingTimer);
  _lastPong = Date.now();
  _pingTimer = setInterval(() => {
    if (_ws?.readyState === WebSocket.OPEN) {
      const pingSentAt = Date.now();
      _ws.send(JSON.stringify({ cmd: "ping" }));
      // 延迟 10 秒后再检查：只有 pong 在此次 ping 发送之后仍未到达，才判定超时断开
      const pongCheck = setTimeout(() => {
        if (_lastPong < pingSentAt && _ws?.readyState === WebSocket.OPEN) {
          _ws.close();
        }
      }, 10_000);
      _pongCheckTimers.push(pongCheck);
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
      // project_list → 更新全局项目列表
      if (msg.type === "project_list") {
        const data = (msg as any).data;
        if (Array.isArray(data)) {
          useWorkspaceStore.getState().setProjects(data);
        }
      }
      // state_snapshot → 更新全局快照（AnalyzePanel 监听恢复）
      if (msg.type === "state_snapshot") {
        const snap = (msg as any).data;
        if (snap) {
          useWorkspaceStore.getState().setSnapshot({
            messages: Array.isArray(snap.messages) ? snap.messages : [],
            reportUrl: snap.report_url || null,
            pendingAskUser: snap.pending_ask_user || null,
            projectName: snap.project_name || "",
            dataPath: snap.data_path || "",
          });
        }
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

  const send = useCallback((cmd: string, payload?: unknown): boolean => {
    if (_ws?.readyState === WebSocket.OPEN) {
      _ws.send(JSON.stringify({ cmd, payload }));
      console.log("[hagoku:ws] send %s ok", cmd);
      return true;
    }
    console.log("[hagoku:ws] send %s FAIL readyState=%s", cmd, _ws?.readyState);
    return false;
  }, []);

  return { status, send, onMessage };
}