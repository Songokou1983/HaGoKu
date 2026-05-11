import { FileText } from "lucide-react";
import { useState, useEffect } from "react";
import { useAgentStatusSync } from "../hooks/useAgentStatusSync";
import { useBatchEvents } from "../hooks/useBatchEvents";
import { PanelHeader } from "../components/PanelHeader";
import { EmptyState } from "../components/EmptyState";

const MAX_REPORTS = 100;

export default function ReportPanel() {
  const [content, setContent] = useState<string[]>([]);

  useAgentStatusSync();

  const batch = useBatchEvents();

  useEffect(() => {
    if (batch.length === 0) return;
    setContent((prev) => {
      let next = prev;
      for (const msg of batch) {
        if (msg.type === "event" && msg.data) {
          const d = msg.data;
          if (
            d.agent === "reporter" &&
            d.event_type === "agent_completed"
          ) {
            next = [
              ...next.slice(-(MAX_REPORTS - 1)),
              `[${new Date(d.timestamp).toLocaleTimeString()}] Report ready: ${JSON.stringify(d.data).slice(0, 200)}`,
            ];
          }
        }
      }
      return next;
    });
  }, [batch]);

  return (
    <div className="h-full flex flex-col bg-[#1e1e1e] text-[#cccccc]">
      <PanelHeader title="Reports" />
      <div className="flex-1 overflow-auto p-3">
        {content.length === 0 ? (
          <EmptyState icon={<FileText size={32} />} message="No reports yet" />
        ) : (
          content.map((c, i) => (
            <div
              key={i}
              className="mb-2 p-2 bg-[#252525] border border-[#333] rounded text-[13px] font-mono text-[#6a9955] whitespace-pre-wrap break-words"
            >
              {c}
            </div>
          ))
        )}
      </div>
    </div>
  );
}