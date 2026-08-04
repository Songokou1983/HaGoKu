import type {
  AgentKey,
} from "./types";

// ── Agent key resolution ──────────────────────────────────────

export function resolveAgentKey(raw: string): AgentKey | null {
  const s = raw.toLowerCase();
  if (s.includes("scout"))    return "scout";
  if (s.includes("clean"))    return "cleaner";
  if (s.includes("analys"))   return "analyst";
  if (s.includes("report"))   return "reporter";
  return null;
}

// ── Helpers ────────────────────────────────────────────────────

export function significanceShort(s: string): string {
  if (s === "significant") return "显著";
  if (s === "not_significant") return "未显著";
  return s.trim() || "—";
}
