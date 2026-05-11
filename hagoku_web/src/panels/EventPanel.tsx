import { useState, useEffect } from "react";
import { useAgentStatusSync } from "../hooks/useAgentStatusSync";
import { useBatchEvents } from "../hooks/useBatchEvents";
import { useWorkspaceStore } from "../stores/workspace";
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
  const connectionStatus = useWorkspaceStore((s) => s.connectionStatus);

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
    <div className="h-full flex flex-col bg-app-bg text-app-text max-md:min-h-[200px]">
      <PanelHeader
        title="Event Log"
        badge={
          <span className="text-app-text-muted font-normal">({entries.length})</span>
        }
      />
      <div className="flex-1 overflow-auto font-mono text-ui-sm relative">
        <EventTable entries={entries} />
        {connectionStatus === "disconnected" && (
          <div className="absolute inset-0 bg-app-bg/90 flex flex-col items-center justify-center gap-2 z-10">
            <span className="text-2xl">📡</span>
            <span className="text-ui-base text-app-error">Connection lost</span>
            <span className="text-ui-xs text-app-text-muted">Reconnecting…</span>
          </div>
        )}
      </div>
    </div>
  );
}