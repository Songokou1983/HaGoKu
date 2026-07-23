import { useState, useEffect, useCallback } from "react";
import { WifiOff } from "lucide-react";
import { useBatchEvents } from "../hooks/useBatchEvents";
import { useWorkspaceStore } from "../stores/workspace";
import { PanelHeader } from "../components/PanelHeader";
import { EventTable, type EventEntry } from "../components/EventTable";
import type { EventType } from "../types/events";
import { guardrailsRunCompletedInfo, guardrailsRunCompletedLogDetail } from "../utils/wsGuardrails";

const MAX_ENTRIES = 500;

function detailSnippet(data: Record<string, unknown>): string {
  const keys = Object.keys(data).filter(
    (k) => k !== "event_id" && k !== "event_type",
  );
  if (keys.length === 0) return "—";
  const first = data[keys[0]];
  const s =
    typeof first === "string" ? first : JSON.stringify(first).slice(0, 120);
  return s.length > 100 ? s.slice(0, 100) + "…" : s;
}

export default function EventPanel() {
  const [entries, setEntries] = useState<EventEntry[]>([]);
  const [sysLog, setSysLog] = useState<string[]>([]);
  const connectionStatus = useWorkspaceStore((s) => s.connectionStatus);
  const disconnected = connectionStatus === "disconnected";

  const loadSysLog = useCallback(() => {
    fetch("/api/log?limit=100")
      .then(r => r.json())
      .then(d => setSysLog(d.lines || []))
      .catch(() => {});
  }, []);

  useEffect(() => { loadSysLog(); const t = setInterval(loadSysLog, 5000); return () => clearInterval(t); }, [loadSysLog]);

  const batch = useBatchEvents();

  useEffect(() => {
    if (batch.length === 0) return;
    setEntries((prev) => {
      let next = prev;
      for (const msg of batch) {
        if (msg.type !== "event" || !msg.data) continue;
        const d = msg.data;
        const inner = (d.data ?? {}) as Record<string, unknown>;
        const gr = guardrailsRunCompletedInfo({
          event_type: d.event_type,
          agent: d.agent,
          data: inner,
        });
        let detail = detailSnippet(inner);
        if (gr.guardrailsBlocked) {
          detail = guardrailsRunCompletedLogDetail();
        }
        const entry: EventEntry = {
          id: d.event_id,
          timestamp: d.timestamp,
          agent: d.agent,
          event: d.event_type as EventType,
          detail,
          guardrailsBlocked: gr.guardrailsBlocked,
        };
        next = [entry, ...next.slice(0, MAX_ENTRIES - 1)];
      }
      return next;
    });
  }, [batch]);

  return (
    <div className="h-full flex flex-col bg-app-bg text-app-text">
      <PanelHeader
        title="事件与日志"
        badge={
          <span className="text-app-text-muted font-normal">
            ({entries.length} 事件 · {sysLog.length} 日志)
          </span>
        }
      />

      {/* ── 上半：运行事件 ── */}
      <div className="flex-1 flex flex-col min-h-0 border-b border-app-border">
        <div className="flex items-center justify-between px-3 py-1 bg-app-bg-secondary shrink-0">
          <span className="text-ui-xs font-medium text-app-text">
            📡 运行事件
          </span>
          <span className="text-ui-xs text-app-text-muted">
            {entries.length} 条
          </span>
        </div>
        <div className="flex-1 overflow-auto">
          {entries.length === 0 ? (
            <div className="flex items-center justify-center h-full text-app-text-muted text-ui-sm">
              {disconnected ? "连接断开，等待重连…" : "等待分析启动，事件将实时显示"}
            </div>
          ) : (
            <EventTable entries={entries} />
          )}
        </div>
      </div>

      {/* ── 下半：系统日志 ── */}
      <div className="flex-1 flex flex-col min-h-0">
        <div className="flex items-center justify-between px-3 py-1 bg-app-bg-secondary shrink-0">
          <span className="text-ui-xs font-medium text-app-text">
            📋 系统日志
          </span>
          <button
            onClick={loadSysLog}
            className="text-ui-xs text-app-accent hover:underline cursor-pointer"
          >
            刷新
          </button>
        </div>
        <div className="flex-1 overflow-auto font-mono">
          {sysLog.length === 0 ? (
            <div className="flex items-center justify-center h-full text-app-text-muted text-ui-sm">
              加载中…
            </div>
          ) : (
            sysLog.map((line, i) => (
              <div
                key={i}
                className="px-3 py-0.5 text-xs hover:bg-app-bg-secondary border-b border-app-border/20 whitespace-pre leading-relaxed"
                style={{ fontSize: "0.68rem" }}
              >
                {line}
              </div>
            ))
          )}
        </div>
      </div>

      {/* ── 断开遮罩 ── */}
      {disconnected && (
        <div className="absolute inset-0 bg-app-bg/90 flex flex-col items-center justify-center gap-2 z-10">
          <WifiOff size={28} className="text-app-text-muted" />
          <span className="text-ui-base text-app-error">连接断开</span>
          <span className="text-ui-xs text-app-text-muted">正在重新连接…</span>
        </div>
      )}
    </div>
  );
}
