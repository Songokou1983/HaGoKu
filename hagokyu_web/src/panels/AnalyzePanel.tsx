import { useState, useCallback, useEffect } from "react";
import { useWebSocket } from "../hooks/useWebSocket";
import { useAgentStatusSync } from "../hooks/useAgentStatusSync";
import { useBatchEvents } from "../hooks/useBatchEvents";
import { PanelHeader } from "../components/PanelHeader";
import { LogView, type LogLine } from "../components/LogView";
import { InputBar } from "../components/InputBar";
import type { WSMessage } from "../types/events";

const MAX_LOG_LINES = 500;

const agentLabelMap = new Map<string, string>([
  ["scout", "🔍"],
  ["cleaner", "🧹"],
  ["analyst", "📊"],
  ["reporter", "📝"],
  ["manager", "🧠"],
  ["system", "⚙️"],
]);

function agentEmoji(name: string): string {
  const key = name.replace(/_/g, " ").toLowerCase();
  for (const [k, v] of agentLabelMap) {
    if (key.includes(k)) return v;
  }
  return "📌";
}

let _msgIdCounter = 0;

export default function AnalyzePanel() {
  const { send } = useWebSocket();
  const [logs, setLogs] = useState<LogLine[]>([]);

  // Shared agent-status sync (no duplicated logic)
  useAgentStatusSync();

  // Batched event stream for high-frequency rendering
  const batch = useBatchEvents();

  // Process each batch
  useEffect(() => {
    if (batch.length === 0) return;
    setLogs((prev) => {
      let next = prev;
      for (const msg of batch) {
        if (msg.type === "event" && msg.data) {
          const d = msg.data;
          const emoji = agentEmoji(d.agent);
          next = [
            ...next.slice(-(MAX_LOG_LINES - 1)),
            {
              id: d.event_id,
              text: `${emoji} [${d.event_type}] ${d.agent.replace(/_/g, " ")}`,
              type: "event" as const,
              timestamp: d.timestamp,
            },
          ];
        }
        if (msg.type === "ack") {
          next = [
            ...next.slice(-(MAX_LOG_LINES - 1)),
            {
              id: `ack-${++_msgIdCounter}`,
              text: `⏳ ${msg.message ?? "Processing..."}`,
              type: "system" as const,
              timestamp: new Date().toISOString(),
            },
          ];
        }
      }
      return next;
    });
  }, [batch]);

  const handleSend = useCallback(
    (text: string) => {
      setLogs((prev) => [
        ...prev.slice(-(MAX_LOG_LINES - 1)),
        {
          id: `user-${++_msgIdCounter}`,
          text,
          type: "user" as const,
          timestamp: new Date().toISOString(),
        },
      ]);
      send("analyze", { query: text });
    },
    [send],
  );

  return (
    <div className="h-full flex flex-col bg-[#1e1e1e] text-[#d4d4d4]">
      <PanelHeader title="Analyze" />
      <LogView lines={logs} />
      <InputBar onSend={handleSend} />
    </div>
  );
}