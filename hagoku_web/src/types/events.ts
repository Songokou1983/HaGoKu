/** Event types mirrored from hagoku.observability.events.EventType */
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
  | "tool_exchange"
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

// ── CO-23: 扩展事件载荷类型 ──────────────────────────────────────

/** state_snapshot: 重连时后端返回的完整状态 */
export interface StateSnapshotData {
  stage?: string;
  field_review?: unknown;
  cleaning_review?: unknown;
  analyst_message?: string;
  pending_ask_user?: AskUserPayload;
  agent_states?: Record<string, string>;
}

/** tool_exchange 事件载荷 */
export interface ToolExchangePayload {
  stage: string;
  revision: number;
  timestamp: string;
  assistant_pre_text?: string | null;
  tool_calls: ToolCallItem[];
}

export interface ToolCallItem {
  id: string;
  name: string;
  arguments_summary?: string;
  result_summary?: string;
  error?: string | null;
  duration_ms?: number;
}

/** ask_user 载荷（user_input_requested 中的纯 ask，无 review 表） */
export interface AskUserPayload {
  question: string;
  expected_format: "yes_no" | "choice" | "free_text";
  options?: string[];
}

/** agent_stream_delta 事件载荷 */
export interface StreamDeltaPayload {
  stream_id: string;
  delta: string;
  agent: string;
}

/** agent_stream_end 事件载荷 */
export interface StreamEndPayload {
  stream_id: string;
  agent: string;
}