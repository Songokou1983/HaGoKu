import { useState, useEffect, useCallback } from "react";
import { WifiOff, Loader2 } from "lucide-react";
import { useAgentStatusSync } from "../hooks/useAgentStatusSync";
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
  const loading = connectionStatus === "connecting" || connectionStatus === "reconnecting";

  // 加载系统日志
  const loadSysLog = useCallback(() => {
    fetch("/api/log?limit=50")
      .then(r => r.json())
      .then(d => setSysLog(d.lines || []))
      .catch(() => {});
  }, []);

  useEffect(() => { loadSysLog(); }, [loadSysLog]);

  useAgentStatusSync();

  const batch = useBatchEvents();

  useEffect(() => {
    if (batch.length === 0) return;
    // eslint-disable-next-line react-hooks/set-state-in-effect -- batch events from external WS, functional update is correct
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
    <div className="h-full flex flex-col bg-app-bg text-app-text max-md:min-h-[200px]">
      <PanelHeader
        title="运行日志"
        badge={
          <span className="text-app-text-muted font-normal">({entries.length})</span>
        }
      />
      {entries.length === 0 && !loading && (connectionStatus === "connected" || connectionStatus === "idle") && (
        <div className="px-3 py-2 border-b border-app-border shrink-0">
          <p className="text-ui-xs text-app-text-muted">
            {connectionStatus === "idle"
              ? "正在连接服务器…"
              : "分析运行时，工作进展和事件会实时显示在这里。等待分析启动。"}
          </p>
        </div>
      )}
      <div className="flex-1 overflow-auto font-mono text-ui-sm relative">
        <EventTable entries={entries} />
        <div className="border-t border-app-border mt-1">
          <div className="flex items-center justify-between px-3 py-1 bg-app-bg-secondary">
            <span className="text-ui-xs text-app-text-muted">系统日志 ({sysLog.length})</span>
            <button onClick={loadSysLog} className="text-ui-xs text-app-accent hover:underline cursor-pointer">刷新</button>
          </div>
          <div className="max-h-60 overflow-auto text-xs text-app-text-muted leading-relaxed">
            {sysLog.map((line, i) => (
              <div key={i} className="px-3 py-0.5 hover:bg-app-bg-secondary border-b border-app-border/30 whitespace-pre font-mono"
                style={{fontSize: '0.68rem'}}>
                {line}
              </div>
            ))}
          </div>
        </div>
        {(connectionStatus === "connecting" || connectionStatus === "reconnecting") && (
          <div className="absolute inset-0 z-10 flex flex-col items-center justify-center gap-2 bg-app-bg/80 backdrop-blur-sm">
            <Loader2 size={20} className="animate-spin text-app-accent" />
            <span className="text-ui-xs text-app-text-muted">正在连接服务器…</span>
          </div>
        )}
        {connectionStatus === "disconnected" && (
          <div className="absolute inset-0 bg-app-bg/90 flex flex-col items-center justify-center gap-2 z-10">
            <WifiOff size={28} className="text-app-text-muted" />
            <span className="text-ui-base text-app-error">连接断开</span>
            <span className="text-ui-xs text-app-text-muted">正在重新连接…</span>
          </div>
        )}
      </div>
    </div>
  );
}