// ── Agent pipeline types ───────────────────────────────────────
import type React from "react";

export type AgentKey = "scout" | "cleaner" | "analyst" | "reporter";
export type AgentRunState = "idle" | "running" | "done" | "error" | "skipped";

// ── Session ────────────────────────────────────────────────────
export type SessionPhase = "setup" | "running" | "done";

// ── Conversation ───────────────────────────────────────────────

export interface ConvoMessage {
  id: string;
  role: "system" | "user" | "agent";
  text: string;
  timestamp: string;
  html?: string;
  collapsible?: boolean;
  streaming?: boolean;
  streamId?: string;
}

export interface ProjectFile {
  name: string;
  path: string;
  size: number;
  mtime: number;
}

// ── WebSocket Event Handler Deps ──────────────────────────────
// 从 useWsEventHandler 提取，供 handler 函数共享。

export interface WsEventDeps {
  batch: any[];
  setMessages: (msgs: ConvoMessage[]) => void;
  appendDelta: (streamId: string, delta: string) => void;
  addUserMsg: (text: string) => void;
  clearMessages: () => void;
  endStream: () => void;
  setAgentElapsed: React.Dispatch<React.SetStateAction<Record<AgentKey, number>>>;
  agentStartTimes: React.MutableRefObject<Record<string, number>>;
  setWaitingAgent: React.Dispatch<React.SetStateAction<AgentKey | null>>;
  setPhase: React.Dispatch<React.SetStateAction<any>>;
  setGateOpen: React.Dispatch<React.SetStateAction<boolean>>;
  setGuardrailsBlocked: React.Dispatch<React.SetStateAction<boolean>>;
  setBlockedRunId: React.Dispatch<React.SetStateAction<string | null>>;
  setResultReportUrl: React.Dispatch<React.SetStateAction<string | null>>;
  replySnapshotRef: React.MutableRefObject<{ agent: AgentKey; gate: boolean } | null>;
  replyInputRef: React.MutableRefObject<HTMLTextAreaElement | null>;
  waitinAgent: AgentKey | null;
  gateOpen: boolean;
  currentProject: string | null;
  onThinking?: (text: string | null) => void;
  setReplyPending?: React.Dispatch<React.SetStateAction<boolean>>;
  setCurrentProject?: (p: string) => void;
  setCurrentDataPath?: (p: string) => void;
  log?: (msg: string) => void;
}
