// ── File size formatter ───────────────────────────────────────

export function fmtSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

// ── Unique ID generator ───────────────────────────────────────

let _idCtr = 0;
export function uid() { return `m-${++_idCtr}-${Date.now()}`; }

// ── Scout fact line formatter ──────────────────────────────────

/** 由后端 `user_input_received` 结构化字段拼一条事实行（随状态变化，非固定话术库） */
export function formatScoutUserInputFactLine(inner: Record<string, unknown>): string {
  const llmReply = typeof inner.llm_reply === "string" ? inner.llm_reply : "";
  return llmReply;
}

// ── Stage proceed fact line formatter ──────────────────────────

export function formatStageProceedFactLine(label: "清洗" | "统计", inner: Record<string, unknown>): string {
  const ok = Boolean(inner.proceed_accepted);
  const rev = inner.interaction_revision;
  const revStr = typeof rev === "number" && Number.isFinite(rev) ? String(rev) : "?";
  const r = typeof inner.reply === "string" ? inner.reply : "";
  return `${label}确认 · revision ${revStr}: proceed=${ok} · 回复长度 ${r.length}`;
}
