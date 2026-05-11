import { useState, useCallback, useEffect } from "react";
import { useWebSocket } from "../hooks/useWebSocket";
import { useAgentStatusSync } from "../hooks/useAgentStatusSync";
import { useBatchEvents } from "../hooks/useBatchEvents";
import { PanelHeader } from "../components/PanelHeader";
import { LogView, type LogLine } from "../components/LogView";
import { InputBar } from "../components/InputBar";
import { FileText } from "lucide-react";

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
  const [dataPath, setDataPath] = useState("");

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
      if (!dataPath.trim()) {
        setLogs((prev) => [
          ...prev.slice(-(MAX_LOG_LINES - 1)),
          {
            id: `user-${++_msgIdCounter}`,
            text: "⚠️ 请先输入数据文件路径",
            type: "system" as const,
            timestamp: new Date().toISOString(),
          },
        ]);
        return;
      }
      setLogs((prev) => [
        ...prev.slice(-(MAX_LOG_LINES - 1)),
        {
          id: `user-${++_msgIdCounter}`,
          text: `[${dataPath}] ${text}`,
          type: "user" as const,
          timestamp: new Date().toISOString(),
        },
      ]);
      send("analyze", { data_path: dataPath, query: text, project_name: "default", phase: "full" });
    },
    [send, dataPath],
  );

  return (
    <div className="h-full flex flex-col bg-[#1e1e1e] text-[#d4d4d4]">
      <PanelHeader title="Analyze" />
      <div className="px-3 py-2 border-b border-[#333] flex items-center gap-2">
        <FileText size={14} className="text-[#569cd6] shrink-0" />
        <input
          type="text"
          className="flex-1 bg-transparent border-none outline-none text-[13px] text-[#d4d4d4] placeholder-[#555]"
          placeholder="数据文件路径 (e.g. /path/to/data.csv)"
          value={dataPath}
          onChange={(e) => setDataPath(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey && dataPath.trim()) {
              // Focus the textarea and let user type query
            }
          }}
        />
      </div>
      <LogView lines={logs} />
      <InputBar onSend={handleSend} />
    </div>
  );
}