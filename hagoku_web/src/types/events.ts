/** Event types mirrored from hagoku.observability.events.EventType */
export type EventType =
  | "quality_check"
  | "agent_started"
  | "agent_thinking"
  | "agent_completed"
  | "agent_failed"
  | "tool_called"
  | "tool_result"
  | "tool_error"
  | "user_input_requested"
  | "user_input_received"
  | "tool_exchange"
  | "agent_stream_delta"
  | "agent_stream_end"
  | "run_started"
  | "run_completed"
  | "run_failed";

/** Structured event payload sent from the backend */
export interface EventData {
  event_id: string;
  event_type: EventType;
  timestamp: string;
  agent: string;
  data: Record<string, unknown>;
  parent_id: string | null;
}

/** Agent lifecycle status used in the global store */
export type AgentStatus = "idle" | "running" | "done" | "error" | "waiting_input" | "skipped";

/** Connection states for the shared WebSocket */
export type ConnectionStatus =
  | "idle"
  | "connecting"
  | "connected"
  | "reconnecting"
  | "disconnected";

export interface WSMessage {
  type: "welcome" | "event" | "pong" | "ack" | "error";
  message?: string;
  data?: EventData;
  cmd?: string;
  version?: string;
}

export interface ToolCallItem {
  id: string;
  name: string;
  arguments_summary?: string;
  result_summary?: string;
  error?: string | null;
  duration_ms?: number;
}