import { EmptyState } from "./EmptyState";
import type { EventType } from "../types/events";

export interface EventEntry {
  id: string;
  timestamp: string;
  agent: string;
  event: EventType;
  detail: string;
}

interface EventTableProps {
  entries: EventEntry[];
}

const colorMap: Record<EventType, string> = {
  agent_started: "#569cd6",
  agent_thinking: "#569cd6",
  agent_completed: "#6a9955",
  agent_failed: "#f44747",
  tool_called: "#ce9178",
  tool_result: "#dcdcaa",
  tool_error: "#f44747",
  run_started: "#4ec9b0",
  run_completed: "#6a9955",
  run_failed: "#f44747",
  plan_created: "#c586c0",
  task_assigned: "#dcdcaa",
  quality_check: "#4ec9b0",
  mode_switched: "#ce9178",
  plan_adjusted: "#dcdcaa",
  data_passed: "#569cd6",
  data_artifact_created: "#c586c0",
  user_input_requested: "#4ec9b0",
  user_input_received: "#6a9955",
};

function eventColor(evt: EventType): string {
  return colorMap[evt] ?? "#888";
}

function EventRow({ entry }: { entry: EventEntry }) {
  return (
    <tr className="border-b border-[#2a2a2a] hover:bg-[#252525]">
      <td className="px-3 py-0.5 text-[#555] whitespace-nowrap">
        {new Date(entry.timestamp).toLocaleTimeString()}
      </td>
      <td className="px-3 py-0.5 text-[#9cdcfe] whitespace-nowrap">
        {entry.agent}
      </td>
      <td
        className="px-3 py-0.5 whitespace-nowrap"
        style={{ color: eventColor(entry.event) }}
      >
        {entry.event}
      </td>
      <td className="px-3 py-0.5 text-[#999] max-w-[300px] truncate">
        {entry.detail}
      </td>
    </tr>
  );
}

export function EventTable({ entries }: EventTableProps) {
  if (entries.length === 0) {
    return (
      <EmptyState
        icon={<span className="text-2xl">📡</span>}
        message="Waiting for events…"
      />
    );
  }

  return (
    <table className="w-full border-collapse">
      <thead className="sticky top-0 bg-[#252525] text-[#888] text-[11px] uppercase select-none z-10">
        <tr>
          <th className="px-3 py-1 text-left font-medium">Time</th>
          <th className="px-3 py-1 text-left font-medium">Agent</th>
          <th className="px-3 py-1 text-left font-medium">Event</th>
          <th className="px-3 py-1 text-left font-medium">Detail</th>
        </tr>
      </thead>
      <tbody>
        {entries.map((e) => (
          <EventRow key={e.id} entry={e} />
        ))}
      </tbody>
    </table>
  );
}