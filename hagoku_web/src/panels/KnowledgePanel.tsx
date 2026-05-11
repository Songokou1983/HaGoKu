import { BookOpen } from "lucide-react";
import { useState, useEffect } from "react";
import { useAgentStatusSync } from "../hooks/useAgentStatusSync";
import { useBatchEvents } from "../hooks/useBatchEvents";
import { PanelHeader } from "../components/PanelHeader";
import { EmptyState } from "../components/EmptyState";

interface KnowledgeEntry {
  key: string;
  title: string;
  tags: string[];
}

export default function KnowledgePanel() {
  const [entries, setEntries] = useState<KnowledgeEntry[]>([]);

  useAgentStatusSync();

  const batch = useBatchEvents();

  useEffect(() => {
    if (batch.length === 0) return;
    // Merge knowledge-load events
    for (const msg of batch) {
      if (msg.type === "event" && msg.data) {
        const d = msg.data;
        if (d.agent === "analyst" && d.event_type === "tool_called") {
          const tool = (d.data as Record<string, unknown>)?.tool as
            | string
            | undefined;
          if (tool?.startsWith("load_knowledge")) {
            const name = ((d.data as Record<string, unknown>)?.name as string) ?? "unknown";
            setEntries((prev) => {
              if (prev.some((e) => e.key === name)) return prev;
              return [
                ...prev,
                {
                  key: name,
                  title: name,
                  tags: [],
                },
              ];
            });
          }
        }
      }
    }
  }, [batch]);

  return (
    <div className="h-full flex flex-col bg-[#1e1e1e] text-[#cccccc] max-md:min-h-[200px]">
      <PanelHeader title="Knowledge" />
      <div className="flex-1 overflow-auto p-3">
        {entries.length === 0 ? (
          <EmptyState
            icon={<BookOpen size={32} />}
            message="Knowledge base empty"
          />
        ) : (
          <div className="space-y-2">
            {entries.map((e) => (
              <div
                key={e.key}
                className="p-2 bg-[#252525] border border-[#333] rounded flex items-center gap-2"
              >
                <BookOpen size={14} className="text-[#569cd6] shrink-0" />
                <span className="text-[13px] text-[#d4d4d4]">{e.title}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}