/**
 * WebSocket 事件里与统计护栏拦截相关的解析（供面板与单测共用，避免回归）。
 * 载荷形状与后端 `Event.to_dict()` / `hagoku.observability.events.Event` 一致。
 *
 * 逻辑契约（勿改动而不更新 Python 镜像）：
 * `tests/test_web/test_ws_guardrails_parity.py`
 */

export interface WsEventLike {
  event_type: string;
  agent?: string;
  data?: Record<string, unknown>;
}

/** 从绝对 output_path 解析 run_id（兼容缺省 WS payload.run_id 的旧数据）。 */
export function runIdFromOutputPath(outputPath: string | undefined): string | null {
  if (!outputPath) return null;
  const normalized = outputPath.replace(/\\/g, "/");
  const marker = "/runs/";
  const idx = normalized.lastIndexOf(marker);
  if (idx === -1) return null;
  const rest = normalized.slice(idx + marker.length);
  const seg = rest.split("/")[0];
  return seg || null;
}

export interface GuardrailsRunCompletedInfo {
  guardrailsBlocked: boolean;
  runId: string | null;
}

/** 解析 `run_completed` 是否护栏拦截及可用 run_id。 */
export function guardrailsRunCompletedInfo(e: WsEventLike): GuardrailsRunCompletedInfo {
  const inner = e.data ?? {};
  if (e.event_type !== "run_completed" || inner.guardrails_blocked !== true) {
    return { guardrailsBlocked: false, runId: null };
  }
  const explicit = typeof inner.run_id === "string" ? inner.run_id : null;
  const out =
    typeof inner.output_path === "string" ? inner.output_path : undefined;
  const runId = explicit ?? runIdFromOutputPath(out);
  return { guardrailsBlocked: true, runId };
}

/** 运行日志里护栏拦截行的详情文案。 */
export function guardrailsRunCompletedLogDetail(): string {
  return "未生成正式 HTML；说明见 GUARDRAILS_BLOCKED.md";
}

/** Reporter `agent_completed` 且 `skipped`（编排层跳过正式报告）。 */
export function isReporterSkippedCompletion(e: WsEventLike): boolean {
  const agent = (e.agent ?? "").toLowerCase();
  if (!agent.includes("report")) return false;
  if (e.event_type !== "agent_completed") return false;
  return e.data?.skipped === true;
}
