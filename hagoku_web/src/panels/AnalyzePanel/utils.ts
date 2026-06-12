/** 简易唯一 ID */
export function uid(): string {
  return Math.random().toString(36).slice(2, 10);
}

/** 文件大小格式化 */
export function fmtSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

/** 由后端 `user_input_received` 结构化字段拼一条事实行（随状态变化，非固定话术库） */
export function formatScoutUserInputFactLine(inner: Record<string, unknown>): string {
  const failure = inner.understanding_failure as { raw_text?: string } | null | undefined;
  if (failure && typeof failure === "object") {
    const hint =
      typeof inner.parse_hint === "string" && inner.parse_hint.trim()
        ? inner.parse_hint.trim()
        : "未能理解你的说明。请改用原始列名（如 Period、Inc1）或更短的中文名重说。";
    return hint;
  }
  const llmReply = typeof inner.llm_reply === "string" ? inner.llm_reply.trim() : "";
  if (llmReply && !llmReply.startsWith("[调用]")) {
    return llmReply;
  }
  return "";
}

/** 将后端 applied_field_updates 转为用户可读摘要 */
export function formatScoutAppliedUpdates(applied: string[]): string {
  const parts: string[] = [];
  for (const a of applied) {
    if (a.startsWith("[signal]") || a.startsWith("[route_to]") || a.startsWith("[ask_user]")) {
      continue;
    }
    const display = a.match(/^([^:]+):\[display\]←(.+)$/);
    if (display) {
      parts.push(`${display[1]} 中文名 → ${display[2]}`);
      continue;
    }
    const meaning = a.match(/^([^:]+)←(.+)$/);
    if (meaning) {
      parts.push(`${meaning[1]} 含义已更新`);
      continue;
    }
    const uia = a.match(/^([^:]+):\[used_in_analysis\]←(true|false)$/);
    if (uia) {
      parts.push(`${uia[1]} 参与分析 → ${uia[2] === "true" ? "是" : "否"}`);
    }
  }
  return parts.join("；");
}
