import { useState, useEffect } from "react";
import { useAgentStatusSync } from "../hooks/useAgentStatusSync";
import { useBatchEvents } from "../hooks/useBatchEvents";
import { PanelHeader } from "../components/PanelHeader";
import { EventTable, type EventEntry } from "../components/EventTable";
import type { EventType } from "../types/events";

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

  useAgentStatusSync();

  const batch = useBatchEvents();

  useEffect(() => {
    if (batch.length === 0) return;
    setEntries((prev) => {
      let next = prev;
      for (const msg of batch) {
        if (msg.type !== "event" || !msg.data) continue;

        const d = msg.data;
        const entry: EventEntry = {
          id: d.event_id,
          timestamp: d.timestamp,
          agent: d.agent,
          event: d.event_type as EventType,
          detail: detailSnippet(d.data),
        };
        next = [entry, ...next.slice(0, MAX_ENTRIES - 1)];
      }
      return next;
    });
  }, [batch]);

  return (
    <div className="h-full flex flex-col bg-[#1e1e1e] text-[#cccccc]">
      <PanelHeader
        title="Event Log"
        badge={
          <span className="text-[#555] font-normal">({entries.length})</span>
        }
      />
      <div className="flex-1 overflow-auto font-mono text-[12px]">
        <EventTable entries={entries} />
      </div>
    </div>
  );
}