// 前端事件日志 — 所有用户可感知动作都调此函数
// console + localStorage (环形200条) + WS __log (连上时)
const LOG_KEY = "hagoku_event_log";
const MAX = 200;

function _writeLocal(line: string) {
  try {
    const prev = JSON.parse(localStorage.getItem(LOG_KEY) || "[]");
    prev.push(line);
    if (prev.length > MAX) prev.splice(0, prev.length - MAX);
    localStorage.setItem(LOG_KEY, JSON.stringify(prev));
  } catch {}
}

function _sendWS(line: string) {
  try {
    const ws = (window as any).__hagoku_ws;
    if (ws?.readyState === 1) {
      ws.send(JSON.stringify({ cmd: "__log", payload: { text: line } }));
    }
  } catch {}
}

export function eventLog(category: string, detail: string) {
  const ts = new Date().toISOString();
  const line = `[frontend] [${ts}] [${category}] ${detail}`;
  try { console.log(line); } catch {}
  _writeLocal(line);
  _sendWS(line);
}

// 启动时同步离线日志到后端
export function flushOfflineLog() {
  try {
    const raw = localStorage.getItem(LOG_KEY);
    if (!raw) return;
    const lines: string[] = JSON.parse(raw);
    for (const line of lines.slice(-50)) {
      _sendWS(`[offline] ${line}`);
    }
  } catch {}
}
