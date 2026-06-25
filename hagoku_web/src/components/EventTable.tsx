import { EmptyState } from "./EmptyState";
import { WifiOff } from "lucide-react";
import type { EventType } from "../types/events";

export interface EventEntry {
  id: string;
  timestamp: string;
  agent: string;
  event: EventType;
  detail: string;
  /** `run_completed` 且强制护栏拦截 */
  guardrailsBlocked?: boolean;
}

interface EventTableProps {
  entries: EventEntry[];
}

const AGENT_COLORS: Record<string, string> = {
  scout:    "text-app-accent",
  cleaner:  "text-app-warning",
  analyst:  "text-event-purple",
  reporter: "text-app-success",
  manager:  "text-app-text-muted",
  scribe:   "text-app-text-muted",
};

const eventColorClass: Record<string, string> = {
  run_started:          "text-event-run",
  agent_started:        "text-event-run",
  run_completed:        "text-event-done",
  agent_completed:      "text-event-done",
  agent_failed:         "text-event-fail",
  run_failed:           "text-event-fail",
  agent_thinking:        "text-event-warn",
  tool_called:          "text-event-warn",
  user_input_requested:  "text-event-purple",
};

function EventRow({ entry }: { entry: EventEntry }) {
  const agentColor = AGENT_COLORS[entry.agent?.toLowerCase() ?? ""] ?? "text-app-agent";
  const gr = entry.guardrailsBlocked === true;
  const eventCls = gr
    ? "text-app-warning font-medium"
    : (eventColorClass[entry.event] ?? "text-app-text-muted");
  const eventLabel = gr ? "run_completed（护栏未过）" : entry.event;
  return (
    <tr className={`border-b border-app-border hover:bg-app-bg-secondary transition-colors duration-150 ${gr ? "bg-app-warning/5" : ""}`}>
      <td className="px-3 py-0.5 text-app-text-muted whitespace-nowrap">
        {new Date(entry.timestamp).toLocaleTimeString('zh-CN')}
      </td>
      <td className={`px-3 py-0.5 whitespace-nowrap ${eventCls}`}>
        {eventLabel}
      </td>
      <td className="px-3 py-0.5 text-app-text-muted max-w-[300px] truncate max-md:hidden">
        {entry.detail}
      </td>
    </tr>
  );
}

export function EventTable({ entries }: EventTableProps) {
  if (entries.length === 0) {
    return (
      <EmptyState
        icon={<WifiOff size={32} className="text-app-text-muted" />}
        message="等待事件…"
      />
    );
  }

  return (
    <table className="w-full border-collapse">
      <thead className="sticky top-0 bg-app-bg-secondary text-app-text-muted text-ui-xs uppercase select-none z-10">
        <tr>
          <th className="px-3 py-1 text-left font-medium">时间</th>
          <th className="px-3 py-1 text-left font-medium">事件</th>
          <th className="px-3 py-1 text-left font-medium">详情</th>
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