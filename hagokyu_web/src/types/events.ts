/** Event types mirrored from hagokyu.observability.events.EventType */
export type EventType =
  | "plan_created"
  | "task_assigned"
  | "quality_check"
  | "mode_switched"
  | "plan_adjusted"
  | "agent_started"
  | "agent_thinking"
  | "agent_completed"
  | "agent_failed"
  | "tool_called"
  | "tool_result"
  | "tool_error"
  | "data_passed"
  | "data_artifact_created"
  | "user_input_requested"
  | "user_input_received"
  | "run_started"
  | "run_completed"
  | "run_failed";

/** Known agent identifiers */
export type AgentId = "scout" | "cleaner" | "analyst" | "reporter";

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
export type AgentStatus = "idle" | "running" | "done" | "error" | "waiting_input";

/** Connection states for the shared WebSocket */
export type ConnectionStatus =
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