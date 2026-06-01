import { useState, useCallback, useEffect, useLayoutEffect, useRef } from "react";
import { guardrailsRunCompletedInfo } from "../utils/wsGuardrails";
import { useWebSocket } from "../hooks/useWebSocket";
import { useAgentStatusSync } from "../hooks/useAgentStatusSync";
import { useBatchEvents } from "../hooks/useBatchEvents";
import { useWorkspaceStore } from "../stores/workspace";
import { PanelHeader } from "../components/PanelHeader";
import {
  Loader2, WifiOff, Search, Sparkles, BarChart2, FileText,
  ArrowRight, FolderOpen, Upload, ChevronDown, CheckCircle2, X,
  PlayCircle, RotateCcw, Clock, ShieldAlert, MessageSquarePlus, Trash2,
} from "lucide-react";

// ── Agent pipeline definition ─────────────────────────────────
const PIPELINE_AGENTS = [
  { key: "scout",    label: "Scout",    icon: Search,    desc: "理解数据" },
  { key: "cleaner",  label: "Cleaner",  icon: Sparkles,  desc: "清洗数据" },
  { key: "analyst",  label: "Analyst",  icon: BarChart2, desc: "统计分析" },
  { key: "reporter", label: "Reporter", icon: FileText,  desc: "生成报告" },
] as const;

type AgentKey = typeof PIPELINE_AGENTS[number]["key"];
type AgentRunState = "idle" | "running" | "done" | "error" | "skipped";

// Map raw WS event agent names → pipeline keys
function resolveAgentKey(raw: string): AgentKey | null {
  const s = raw.toLowerCase();
  if (s.includes("scout"))    return "scout";
  if (s.includes("clean"))    return "cleaner";
  if (s.includes("analys"))   return "analyst";
  if (s.includes("report"))   return "reporter";
  return null;
}

function parsePauseInteractionRevision(data: Record<string, unknown>): number | null {
  const v = data.interaction_revision;
  return typeof v === "number" && Number.isFinite(v) ? v : null;
}

// ── Types ────────────────────────────────────────────────────
type SessionPhase = "setup" | "running" | "done";

/** Scout 字段核对：后端 `field_review`（列：字段名称 / 中文名称 / 含义理解 / 分析角色） */
interface FieldReviewPayload {
  n_rows: number | string;
  n_cols: number;
  /** 分析字段摘要：目标变量/特征/标识列的划分概览 */
  analysis_fields_summary?: string;
  rows: Array<{
    field_name: string;
    /** 中文名称：column_display_names 显式命名；无则占位「—」 */
    chinese_name: string;
    /** AI 对字段的含义理解（column_descriptions 或语义兜底） */
    meaning: string;
    /** 建议分析角色：target / feature / identifier（由 Scout 语义推断） */
    suggested_role: string;
    needs_attention?: boolean;
    /** 用户是否明确指定该字段参与本次分析（true/false/null） */
    used_in_analysis?: boolean | null;
  }>;
}

function parseFieldReview(raw: unknown): FieldReviewPayload | null {
  if (!raw || typeof raw !== "object") return null;
  const o = raw as Record<string, unknown>;
  const rowsRaw = o.rows;
  if (!Array.isArray(rowsRaw) || rowsRaw.length === 0) return null;
  const rows: FieldReviewPayload["rows"] = [];
  for (const item of rowsRaw) {
    if (!item || typeof item !== "object") continue;
    const r = item as Record<string, unknown>;
    rows.push({
      field_name: String(r.field_name ?? ""),
      chinese_name: String(r.chinese_name ?? "—"),
      meaning: String(r.meaning ?? ""),
      suggested_role: String(r.suggested_role ?? "—"),
      needs_attention: Boolean(r.needs_attention),
        used_in_analysis: "used_in_analysis" in r ? (r.used_in_analysis === null ? null : Boolean(r.used_in_analysis)) : undefined,
    });
  }
  if (rows.length === 0) return null;
  const nCols = typeof o.n_cols === "number" && Number.isFinite(o.n_cols) ? o.n_cols : rows.length;
  const nRowsRaw = o.n_rows;
  const nRows: number | string =
    typeof nRowsRaw === "number" && Number.isFinite(nRowsRaw)
      ? nRowsRaw
      : typeof nRowsRaw === "string"
        ? nRowsRaw
        : "?";
  const summaryRaw = o.analysis_fields_summary;
  const analysis_fields_summary: string | undefined =
    typeof summaryRaw === "string" && summaryRaw.trim() ? summaryRaw.trim() : undefined;
  return {
    n_rows: nRows,
    n_cols: nCols,
    rows,
    ...(analysis_fields_summary !== undefined ? { analysis_fields_summary } : {}),
  };
}

/** Cleaner 评估：后端 `cleaning_assessment` — LLM 的自由文本评估 */
interface CleaningAssessment {
  summary: string;
  columns: Array<{
    column: string;
    display_name?: string;
    action: "skip" | "clean";
    reason: string;
    operations?: Array<{ strategy: string }>;
  }>;
}
function parseCleaningAssessment(raw: unknown): CleaningAssessment | null {
  if (!raw || typeof raw !== "object") return null;
  const d = raw as Record<string, unknown>;
  if (!Array.isArray(d.columns)) return null;
  return { summary: String(d.summary || ""), columns: (d.columns as any[]).map((c: any) => ({ ...c, reason: c.reason || c.reason || "" })) };
}

/** Cleaner 核对：后端 `cleaning_review` 结构化载荷（非 Agent 台词） */
interface CleaningReviewPayload {
  data_quality: string;
  impact_rate: number;
  total_rows_original: number;
  total_rows_after: number;
  rows_removed: number;
  bias_risk: string;
  n_ops: number;
  warnings: string[];
  rows: Array<{
    column: string;
    strategy: string;
    reason: string;
    rows_affected: number;
  }>;
}

function parseCleaningReview(raw: unknown): CleaningReviewPayload | null {
  if (!raw || typeof raw !== "object") return null;
  const o = raw as Record<string, unknown>;
  const rowsRaw = o.rows;
  if (!Array.isArray(rowsRaw)) return null;
  const rows: CleaningReviewPayload["rows"] = [];
  for (const item of rowsRaw) {
    if (!item || typeof item !== "object") continue;
    const r = item as Record<string, unknown>;
    rows.push({
      column: String(r.column ?? ""),
      strategy: String(r.strategy ?? ""),
      reason: String(r.reason ?? ""),
      rows_affected: typeof r.rows_affected === "number" && Number.isFinite(r.rows_affected) ? r.rows_affected : 0,
    });
  }
  const wRaw = o.warnings;
  const warnings: string[] = Array.isArray(wRaw)
    ? wRaw.filter((x): x is string => typeof x === "string" && x.trim().length > 0).map((x) => x.trim())
    : [];
  const ir = o.impact_rate;
  const impact = typeof ir === "number" && Number.isFinite(ir) ? ir : 0;
  const nOps = typeof o.n_ops === "number" && Number.isFinite(o.n_ops) ? o.n_ops : rows.length;
  const tOrig = typeof o.total_rows_original === "number" && Number.isFinite(o.total_rows_original)
    ? o.total_rows_original
    : 0;
  const tAfter = typeof o.total_rows_after === "number" && Number.isFinite(o.total_rows_after)
    ? o.total_rows_after
    : 0;
  const rrRaw = o.rows_removed;
  const rowsRemoved =
    typeof rrRaw === "number" && Number.isFinite(rrRaw) ? rrRaw : Math.max(0, tOrig - tAfter);
  return {
    data_quality: String(o.data_quality ?? "—"),
    impact_rate: impact,
    total_rows_original: tOrig,
    total_rows_after: tAfter,
    rows_removed: rowsRemoved,
    bias_risk: String(o.bias_risk ?? "unknown"),
    n_ops: nOps,
    warnings,
    rows,
  };
}

/** Analyst 结果核对：后端 `analyst_review` 结构化载荷（非 Agent 台词）；含 p 值/效应量/置信区间与「精、准、狠」一致 */
interface AnalystReviewPayload {
  n_findings: number;
  n_significant: number;
  rows: Array<{
    result_id: string;
    analysis_type: string;
    question: string;
    significance: string;
    p_value: string;
    effect_summary: string;
    confidence_interval: string;
    conclusion_plain: string;
  }>;
}

function parseAnalystReview(raw: unknown): AnalystReviewPayload | null {
  if (!raw || typeof raw !== "object") return null;
  const o = raw as Record<string, unknown>;
  if (!Array.isArray(o.rows)) return null;
  const rowsRaw = o.rows;
  const rows: AnalystReviewPayload["rows"] = [];
  for (const item of rowsRaw) {
    if (!item || typeof item !== "object") continue;
    const r = item as Record<string, unknown>;
    rows.push({
      result_id: String(r.result_id ?? ""),
      analysis_type: String(r.analysis_type ?? ""),
      question: String(r.question ?? ""),
      significance: String(r.significance ?? ""),
      p_value: typeof r.p_value === "string" ? r.p_value : String(r.p_value ?? "—"),
      effect_summary: typeof r.effect_summary === "string"
        ? r.effect_summary
        : String(r.effect_summary ?? "—"),
      confidence_interval: typeof r.confidence_interval === "string"
        ? r.confidence_interval
        : String(r.confidence_interval ?? "—"),
      conclusion_plain: String(r.conclusion_plain ?? ""),
    });
  }
  const nf = o.n_findings;
  const nFindings = typeof nf === "number" && Number.isFinite(nf) ? nf : rows.length;
  const ns = o.n_significant;
  const nSig =
    typeof ns === "number" && Number.isFinite(ns)
      ? ns
      : rows.filter((x) => x.significance === "significant").length;
  return { n_findings: nFindings, n_significant: nSig, rows };
}

function significanceShort(s: string): string {
  if (s === "significant") return "显著";
  if (s === "not_significant") return "未显著";
  return s.trim() || "—";
}

function AnalystReviewTable({ data }: { data: AnalystReviewPayload }) {
  return (
    <div
      className="w-full max-w-full border border-app-border rounded-lg bg-app-bg-secondary overflow-x-auto
        motion-safe:transition-shadow motion-safe:duration-300 shadow-sm hover:shadow-md"
    >
      <div className="px-3 py-2 border-b border-app-border text-ui-xs leading-snug space-y-0.5">
        <div className="font-medium text-app-text">Analyst</div>
        <div className="text-app-text-muted">
          共 {data.n_findings} 条结果 · 其中统计显著 {data.n_significant} 条 · 请核对下表（p 值、效应量、置信区间）；可补充说明，或点「确认继续」进入下一步
        </div>
      </div>
      <table className="w-full text-ui-sm border-collapse min-w-[720px]">
        <caption className="sr-only">统计分析结果摘要</caption>
        <colgroup>
          <col className="w-[7%]" />
          <col className="w-[9%]" />
          <col className="w-[20%]" />
          <col className="w-[9%]" />
          <col className="w-[11%]" />
          <col className="w-[14%]" />
          <col className="w-[8%]" />
          <col className="w-[22%]" />
        </colgroup>
        <thead>
          <tr className="bg-app-bg border-b border-app-border">
            <th scope="col" className="px-2 py-2 font-medium text-center border-r border-app-border align-middle">
              ID
            </th>
            <th scope="col" className="px-2 py-2 font-medium text-center border-r border-app-border align-middle">
              类型
            </th>
            <th scope="col" className="px-2 py-2 font-medium text-center border-r border-app-border align-middle">
              研究问题
            </th>
            <th scope="col" className="px-2 py-2 font-medium text-center border-r border-app-border align-middle">
              p 值
            </th>
            <th scope="col" className="px-2 py-2 font-medium text-center border-r border-app-border align-middle">
              效应量
            </th>
            <th scope="col" className="px-2 py-2 font-medium text-center border-r border-app-border align-middle">
              置信区间
            </th>
            <th scope="col" className="px-2 py-2 font-medium text-center border-r border-app-border align-middle">
              显著性
            </th>
            <th scope="col" className="px-2 py-2 font-medium text-center align-middle">
              简要结论
            </th>
          </tr>
        </thead>
        <tbody>
          {data.rows.length === 0 ? (
            <tr>
              <td colSpan={8} className="px-2 py-2 text-left text-app-text-muted text-ui-xs">
                （无结构化结果行）
              </td>
            </tr>
          ) : (
            data.rows.map((r, i) => (
              <tr key={`${r.result_id}-${i}`} className="border-b border-app-border last:border-b-0">
                <td className="px-2 py-1.5 text-left align-top border-r border-app-border font-mono text-ui-xs break-all">
                  {r.result_id || "—"}
                </td>
                <td className="px-2 py-1.5 text-left align-top border-r border-app-border font-mono text-ui-xs break-all">
                  {r.analysis_type || "—"}
                </td>
                <td className="px-2 py-1.5 text-left align-top border-r border-app-border break-words">
                  {r.question || "—"}
                </td>
                <td className="px-2 py-1.5 text-left align-top border-r border-app-border font-mono text-ui-xs tabular-nums">
                  {r.p_value || "—"}
                </td>
                <td className="px-2 py-1.5 text-left align-top border-r border-app-border font-mono text-ui-xs break-words">
                  {r.effect_summary || "—"}
                </td>
                <td className="px-2 py-1.5 text-left align-top border-r border-app-border font-mono text-ui-xs break-words">
                  {r.confidence_interval || "—"}
                </td>
                <td className="px-2 py-1.5 text-left align-top border-r border-app-border">
                  {significanceShort(r.significance)}
                </td>
                <td className="px-2 py-1.5 text-left align-top break-words">{r.conclusion_plain || "—"}</td>
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  );
}

function CleaningReviewTable({ data }: { data: CleaningReviewPayload }) {
  const pct = `${(100 * data.impact_rate).toFixed(1)}%`;
  const rowLine =
    data.rows_removed > 0
      ? `${data.total_rows_original} → ${data.total_rows_after} 行（已删 ${data.rows_removed}）`
      : `${data.total_rows_original} 行（行数未变）`;
  const qual = data.data_quality && data.data_quality !== "—" ? `${data.data_quality} · ` : "";
  return (
    <div
      className="w-full max-w-full border border-app-border rounded-lg bg-app-bg-secondary overflow-x-auto
        motion-safe:transition-shadow motion-safe:duration-300 shadow-sm hover:shadow-md"
    >
      <div className="px-3 py-2 border-b border-app-border text-ui-xs leading-snug space-y-1">
        <div className="font-medium text-app-text">Cleaner</div>
        <div className="text-app-text-muted">
          {rowLine} · {qual}偏差 {data.bias_risk} · {data.n_ops} 条 · 删行影响率{" "}
          <abbr
            title="该比例来自报告中的删行/整行替换；Winsorize 等只改单元值、不删行时常为 0%。「影响行」列为各列被改写取值的行数。"
            className="cursor-help underline decoration-dotted decoration-app-text-muted/50 underline-offset-2"
          >
            {pct}
          </abbr>
        </div>
        {data.warnings.length > 0 && (
          <ul className="list-disc pl-4 text-app-warning">
            {data.warnings.map((w) => (
              <li key={w}>{w}</li>
            ))}
          </ul>
        )}
      </div>
      <table className="w-full text-ui-sm border-collapse table-fixed">
        <caption className="sr-only">清洗操作摘要</caption>
        <colgroup>
          <col className="w-[16%]" />
          <col className="w-[18%]" />
          <col className="w-[10%]" />
          <col className="w-[56%]" />
        </colgroup>
        <thead>
          <tr className="bg-app-bg border-b border-app-border">
            <th scope="col" className="px-2 py-2 font-medium text-center border-r border-app-border align-middle">
              列
            </th>
            <th scope="col" className="px-2 py-2 font-medium text-center border-r border-app-border align-middle">
              策略
            </th>
            <th
              scope="col"
              title="该列被改写取值的行数（与删行影响率含义不同）"
              className="px-2 py-2 font-medium text-center border-r border-app-border align-middle cursor-help"
            >
              影响行
            </th>
            <th scope="col" className="px-2 py-2 font-medium text-center align-middle">
              说明
            </th>
          </tr>
        </thead>
        <tbody>
          {data.rows.length === 0 ? (
            <tr>
              <td colSpan={4} className="px-2 py-2 text-left text-app-text-muted text-ui-xs">
                （无单独逐条操作记录）
              </td>
            </tr>
          ) : (
            data.rows.map((r, i) => (
              <tr key={`${r.column}-${i}`} className="border-b border-app-border last:border-b-0">
                <td className="px-2 py-1.5 text-left align-top border-r border-app-border font-mono text-ui-xs break-all">
                  {r.column}
                </td>
                <td className="px-2 py-1.5 text-left align-top border-r border-app-border font-mono text-ui-xs break-all">
                  {r.strategy}
                </td>
                <td className="px-2 py-1.5 text-left align-top border-r border-app-border tabular-nums">
                  {r.rows_affected}
                </td>
                <td className="px-2 py-1.5 text-left align-top break-words">{r.reason}</td>
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  );
}

function FieldReviewTable({ data }: { data: FieldReviewPayload }) {
  const summaryLine = data.analysis_fields_summary
    ? data.analysis_fields_summary
    : `共 ${String(data.n_rows)} 行 × ${data.n_cols} 列 · 四列：字段名称 / 中文名称 / 含义理解 / 参与分析`;
  return (
    <div
      className="w-full max-w-full border border-app-border rounded-lg bg-app-bg-secondary overflow-x-auto
        motion-safe:transition-shadow motion-safe:duration-300 shadow-sm hover:shadow-md"
    >
      <div className="px-3 py-2 border-b border-app-border text-ui-xs text-app-text-muted leading-snug">
        {summaryLine}
      </div>
      <table className="w-full text-ui-sm border-collapse table-fixed">
        <caption className="sr-only">字段理解核对：字段名称、中文名称、含义理解、参与分析</caption>
        <colgroup>
          <col className="w-[15%]" />
          <col className="w-[15%]" />
          <col className="w-[45%]" />
          <col className="w-[25%]" />
        </colgroup>
        <thead>
          <tr className="bg-app-bg border-b border-app-border">
            <th scope="col" className="px-2 py-2 font-medium text-center border-r border-app-border align-middle">
              字段名称
            </th>
            <th scope="col" className="px-2 py-2 font-medium text-center border-r border-app-border align-middle">
              中文名称
            </th>
            <th scope="col" className="px-2 py-2 font-medium text-center border-r border-app-border align-middle">
              含义理解
            </th>
            <th scope="col" className="px-2 py-2 font-medium text-center align-middle">
              参与分析
            </th>
          </tr>
        </thead>
        <tbody>
          {data.rows.map((r, i) => {
            return (
              <tr
                key={`${r.field_name}-${i}`}
                className="border-b border-app-border last:border-b-0"
              >
                <td className="px-2 py-1.5 text-left align-top border-r border-app-border font-mono text-ui-xs break-all">
                  {r.field_name}
                </td>
                <td className="px-2 py-1.5 text-left align-top border-r border-app-border break-words">
                  {r.needs_attention ? (
                    <span className="text-app-warning">{r.chinese_name}</span>
                  ) : (
                    r.chinese_name
                  )}
                </td>
                <td className="px-2 py-1.5 text-left align-top border-r border-app-border break-words">{r.meaning}</td>
                <td className="px-2 py-1.5 text-center align-top break-words text-ui-sm">
                  {r.used_in_analysis === true ? "✔" : ""}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

interface ConvoMessage {
  id: string;
  role: "system" | "user" | "agent" | "workflow";
  text: string;
  timestamp: string;
  html?: string;
  fieldReview?: FieldReviewPayload;
  cleaningReview?: CleaningReviewPayload;
  analystReview?: AnalystReviewPayload;
}

interface ProjectFile {
  name: string;
  path: string;
  size: number;
  mtime: number;
}

function fmtSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

let _idCtr = 0;
function uid() { return `m-${++_idCtr}-${Date.now()}`; }

/** 由后端 `user_input_received` 结构化字段拼一条事实行（随状态变化，非固定话术库） */
function formatScoutUserInputFactLine(inner: Record<string, unknown>): string {
  const llmReply = typeof inner.llm_reply === "string" ? inner.llm_reply : "";
  return llmReply;
}

function formatStageProceedFactLine(label: "清洗" | "统计", inner: Record<string, unknown>): string {
  const ok = Boolean(inner.proceed_accepted);
  const rev = inner.interaction_revision;
  const revStr = typeof rev === "number" && Number.isFinite(rev) ? String(rev) : "?";
  const r = typeof inner.reply === "string" ? inner.reply : "";
  return `${label}确认 · revision ${revStr}: proceed=${ok} · 回复长度 ${r.length}`;
}

// ── Pipeline status bar ───────────────────────────────────────
function PipelineBar({ states, elapsed }: {
  states: Record<AgentKey, AgentRunState>;
  elapsed: Record<AgentKey, number>;
}) {
  return (
    <div className="flex items-stretch gap-0 border border-app-border rounded overflow-hidden shrink-0">
      {PIPELINE_AGENTS.map((agent, i) => {
        const state = states[agent.key];
        const Icon = agent.icon;
        const secs = elapsed[agent.key];
        const colorClass =
          state === "running" ? "bg-app-accent/15 border-app-accent text-app-accent" :
          state === "done"    ? "bg-app-success/10 text-app-success" :
          state === "error"   ? "bg-app-error/10 text-app-error" :
          state === "skipped" ? "bg-app-warning/10 text-app-warning" :
          "text-app-text-muted";
        return (
          <div
            key={agent.key}
            className={`flex-1 flex flex-col items-center justify-center gap-0.5 py-2 px-1
              ${colorClass}
              ${i > 0 ? "border-l border-app-border" : ""}
              transition-colors duration-300`}
          >
            <div className="flex items-center gap-1">
              {state === "running"
                ? <Loader2 size={13} className="animate-spin" />
                : state === "done"
                ? <CheckCircle2 size={13} />
                : state === "error"
                ? <X size={13} />
                : state === "skipped"
                ? <ShieldAlert size={13} />
                : <Clock size={13} className="opacity-40" />}
              <Icon size={12} />
            </div>
            <span className="text-ui-xs font-medium">{agent.label}</span>
            <span className="text-ui-xs opacity-60">{agent.desc}</span>
            {secs > 0 && (
              <span className="text-ui-xs opacity-50">{secs}s</span>
            )}
          </div>
        );
      })}
    </div>
  );
}

// ── Conversation feed ─────────────────────────────────────────
function ConvoFeed({
  messages,
  scrollFieldTableId,
  scrollFieldTableNonce,
}: {
  messages: ConvoMessage[];
  scrollFieldTableId: string | null;
  scrollFieldTableNonce: number;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  useLayoutEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages.length]);

  useLayoutEffect(() => {
    if (!scrollFieldTableId || scrollFieldTableNonce === 0) return;
    const root = containerRef.current;
    if (!root) return;
    const el = root.querySelector(`[data-workflow-id="${scrollFieldTableId}"]`);
    el?.scrollIntoView({ behavior: "smooth", block: "nearest", inline: "nearest" });
  }, [scrollFieldTableId, scrollFieldTableNonce]);

  return (
    <div ref={containerRef} className="flex-1 overflow-y-auto px-4 py-3 space-y-2">
      {messages.map((m) => {
        if (m.role === "workflow" && m.fieldReview) {
          return (
            <div key={m.id} data-workflow-id={m.id} className="flex justify-start w-full">
              <div className="w-full max-w-full">
                <FieldReviewTable data={m.fieldReview} />
              </div>
            </div>
          );
        }
        if (m.role === "workflow" && m.cleaningReview) {
          return (
            <div key={m.id} className="flex justify-start w-full">
              <div className="w-full max-w-full">
                <CleaningReviewTable data={m.cleaningReview} />
              </div>
            </div>
          );
        }
        if (m.role === "workflow" && m.analystReview) {
          return (
            <div key={m.id} className="flex justify-start w-full">
              <div className="w-full max-w-full">
                <AnalystReviewTable data={m.analystReview} />
              </div>
            </div>
          );
        }
        return (
          <div
            key={m.id}
            className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}
          >
            <div
              className={`max-w-[85%] px-3 py-2 rounded-lg text-ui-sm leading-relaxed
                ${m.role === "user"
                  ? "bg-app-accent text-white rounded-br-sm"
                  : m.role === "agent"
                  ? "bg-app-bg-secondary border border-app-border text-app-text rounded-bl-sm whitespace-pre-wrap"
                  : "bg-transparent text-app-text-muted text-ui-xs italic whitespace-pre-wrap"
                }`}
            >
              {m.html ? <span dangerouslySetInnerHTML={{ __html: m.html }} /> : m.text}
            </div>
          </div>
        );
      })}
      <div ref={bottomRef} />
    </div>
  );
}

// ── Main component ────────────────────────────────────────────
function ClearHistoryButton({ currentProject }: { currentProject: string | null }) {
  const [showConfirm, setShowConfirm] = useState(false);
  const [clearing, setClearing] = useState(false);

  if (!currentProject) return null;

  const handleClear = async () => {
    setClearing(true);
    try {
      await fetch(`/api/projects/${currentProject}/clear-history`, { method: "POST" });
      handleReset();
    } finally {
      setClearing(false);
      setShowConfirm(false);
    }
  };

  return (
    <>
      <button
        type="button"
        onClick={() => setShowConfirm(true)}
        className="flex items-center gap-1 px-2 py-0.5 border border-app-border rounded text-ui-xs normal-case tracking-normal font-medium text-app-text
          hover:border-app-error hover:text-app-error transition-colors cursor-pointer"
      >
        <Trash2 size={12} />
        清除历史
      </button>
      {showConfirm && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-app-bg border border-app-border rounded-lg p-6 max-w-sm mx-4 shadow-xl">
            <p className="text-ui-sm text-app-text mb-4">
              将清除该项目所有历史分析记录（运行记录、看板、记忆）。数据文件保留。此操作不可撤销，确认清除？
            </p>
            <div className="flex justify-end gap-3">
              <button onClick={() => setShowConfirm(false)} disabled={clearing}
                className="px-4 py-1.5 border border-app-border rounded text-ui-sm text-app-text hover:bg-app-bg-secondary cursor-pointer disabled:opacity-50">
                否
              </button>
              <button onClick={handleClear} disabled={clearing}
                className="px-4 py-1.5 bg-app-error text-white rounded text-ui-sm hover:bg-red-700 cursor-pointer disabled:opacity-50">
                {clearing ? "清除中…" : "是，确认清除"}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}

export default function AnalyzePanel() {
  const { send } = useWebSocket();
  const status = useWorkspaceStore((s) => s.status);
  const connectionStatus = useWorkspaceStore((s) => s.connectionStatus);
  const currentProject = useWorkspaceStore((s) => s.currentProject);
  const setCurrentProject = useWorkspaceStore((s) => s.setCurrentProject);
  const projects = useWorkspaceStore((s) => s.projects);
  const setActiveView = useWorkspaceStore((s) => s.setActiveView);
  const resetRunUiState = useWorkspaceStore((s) => s.resetRunUiState);

  // Session state machine
  const [phase, setPhase] = useState<SessionPhase>("setup");
  const [messages, setMessages] = useState<ConvoMessage[]>([]);
  const [agentStates, setAgentStates] = useState<Record<AgentKey, AgentRunState>>({
    scout: "idle", cleaner: "idle", analyst: "idle", reporter: "idle",
  });
  const [agentElapsed, setAgentElapsed] = useState<Record<AgentKey, number>>({
    scout: 0, cleaner: 0, analyst: 0, reporter: 0,
  });
  const agentStartTimes = useRef<Record<string, number>>({});
  // Track which agent is waiting for user reply
  const [waitingAgent, setWaitingAgent] = useState<AgentKey | null>(null);
  const [replyText, setReplyText] = useState("");
  const [queryText, setQueryText] = useState("");
  const [resultReportUrl, setResultReportUrl] = useState<string | null>(null);
  const [guardrailsBlocked, setGuardrailsBlocked] = useState(false);
  const [blockedRunId, setBlockedRunId] = useState<string | null>(null);
  const replyInputRef = useRef<HTMLTextAreaElement>(null);
  /** 当前暂停点是否对应「字段表」工作流（用于行点选、空回车确认） */
  const [activeFieldReviewId, setActiveFieldReviewId] = useState<string | null>(null);
  /** 多轮对齐：当前 field_review 卡片的 interaction_revision（递增时更新同一卡片） */
  const [activeFieldReviewRevision, setActiveFieldReviewRevision] = useState<number>(-1);
  const [activeCleaningReviewId, setActiveCleaningReviewId] = useState<string | null>(null);
  const [activeCleaningReviewRevision, setActiveCleaningReviewRevision] = useState<number>(-1);
  const [activeAnalystReviewId, setActiveAnalystReviewId] = useState<string | null>(null);
  const [activeAnalystReviewRevision, setActiveAnalystReviewRevision] = useState<number>(-1);
  /** 跨阶段闸门：gate_to_cleaning 暂停点（展示「确认进入清洗」/「还有补充」按钮） */
  const [gateOpen, setGateOpen] = useState(false);
  /** 强确认类按钮默认收起，用户点「我已核对」后再展示，避免与输入区误触混淆 */
  /** 字段表刷新时递增，驱动对话区把该卡片滚入视口（原地更新时 length 不变，仅靠 length 不会滚） */
  const [fieldReviewScrollNonce, setFieldReviewScrollNonce] = useState(0);
  /** 最近一次 respond：WS 报错「无暂停」等时恢复等待态 */
  const replySnapshotRef = useRef<{ agent: AgentKey; gate: boolean } | null>(null);

  // File / project state
  const [dataPath, setDataPath] = useState("");
  const [projectFiles, setProjectFiles] = useState<ProjectFile[]>([]);
  const [filesLoading, setFilesLoading] = useState(false);
  const [showFileDropdown, setShowFileDropdown] = useState(false);
  const [showProjectDropdown, setShowProjectDropdown] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const dropdownRef = useRef<HTMLDivElement>(null);
  const projectDropdownRef = useRef<HTMLDivElement>(null);

  // Close dropdowns on outside click
  useEffect(() => {
    function handle(e: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node))
        setShowFileDropdown(false);
      if (projectDropdownRef.current && !projectDropdownRef.current.contains(e.target as Node))
        setShowProjectDropdown(false);
    }
    document.addEventListener("mousedown", handle);
    return () => document.removeEventListener("mousedown", handle);
  }, []);

  const loadFiles = useCallback((proj: string) => {
    setFilesLoading(true);
    fetch(`/api/projects/${proj}/files`)
      .then((r) => r.json())
      .then((d: { files: ProjectFile[] }) => setProjectFiles(d.files ?? []))
      .catch(() => setProjectFiles([]))
      .finally(() => setFilesLoading(false));
  }, []);

  useEffect(() => {
    if (!currentProject) { setDataPath(""); setProjectFiles([]); return; }
    loadFiles(currentProject);
    fetch(`/api/projects/${currentProject}/detail`)
      .then((r) => r.json())
      .then((d: { data_path?: string; last_query?: string }) => {
        if (d.data_path) setDataPath(d.data_path);
        if (d.last_query) setQueryText(d.last_query);
      })
      .catch(() => {});
  }, [currentProject, loadFiles]);

  useAgentStatusSync();
  const batch = useBatchEvents();

  // Process WS events
  useEffect(() => {
    if (batch.length === 0) return;
    for (const msg of batch) {
      if (msg.type === "ack" && msg.cmd === "respond") {
        replySnapshotRef.current = null;
        continue;
      }
      if (msg.type === "error") {
        const detail = typeof msg.message === "string" ? msg.message.trim() : "";
        const iso = new Date().toISOString();
        setMessages((prev) => [
          ...prev,
          {
            id: uid(),
            role: "system",
            text: detail || "服务器返回错误",
            timestamp: iso,
          },
        ]);
        const snap = replySnapshotRef.current;
        const recoverable = /No agent is waiting|No active orchestrator/i.test(detail);
        if (recoverable && snap) {
          setWaitingAgent(snap.agent);
          setGateOpen(snap.gate);
          replySnapshotRef.current = null;
        }
        continue;
      }
      if (msg.type === "event" && msg.data) {
        const d = msg.data;
        const agentKey = resolveAgentKey(d.agent);

        // Agent lifecycle → update pipeline（不在此插入固定「台词」）
        if (d.event_type === "agent_started" && agentKey) {
          agentStartTimes.current[agentKey] = Date.now();
          setAgentStates((prev) => ({ ...prev, [agentKey]: "running" }));
        }
        if (d.event_type === "agent_completed" && agentKey) {
          const elapsed = Math.round((Date.now() - (agentStartTimes.current[agentKey] ?? Date.now())) / 1000);
          setAgentStates((prev) => ({ ...prev, [agentKey]: "done" }));
          setAgentElapsed((prev) => ({ ...prev, [agentKey]: elapsed }));
        }
        if (d.event_type === "agent_failed" && agentKey) {
          setAgentStates((prev) => ({ ...prev, [agentKey]: "error" }));
          const detail = (d.data as Record<string, unknown>)?.error;
          if (typeof detail === "string" && detail.trim()) {
            setMessages((prev) => [
              ...prev,
              { id: uid(), role: "system", text: detail.trim(), timestamp: d.timestamp },
            ]);
          }
        }

        // 进度提示：后端在长时间步骤会发 agent_thinking；此前对话区空白易被误认为「无回复」
        if (d.event_type === "agent_thinking") {
          const raw = (d.data as Record<string, unknown> | undefined)?.thought;
          if (typeof raw === "string") {
            const t = raw.trim();
            if (t) {
              const short = t.length > 220 ? `${t.slice(0, 217)}…` : t;
              setMessages((prev) => [
                ...prev,
                { id: uid(), role: "system", text: short, timestamp: d.timestamp },
              ]);
            }
          }
        }

        // Reporter skipped (guardrails blocked) → set skipped state
        if (d.agent === "reporter" && d.event_type === "agent_completed") {
          const data = d.data as Record<string, unknown>;
          const elapsed = Math.round((Date.now() - (agentStartTimes.current["reporter"] ?? Date.now())) / 1000);
          if (data?.skipped === true) {
            setAgentStates((prev) => ({ ...prev, reporter: "skipped" }));
            setAgentElapsed((prev) => ({ ...prev, reporter: elapsed }));
            setWaitingAgent(null);
            setPhase("done");
          } else {
            setAgentStates((prev) => ({ ...prev, reporter: "done" }));
            setAgentElapsed((prev) => ({ ...prev, reporter: elapsed }));
            const proj = data?.project_name as string ?? currentProject ?? "default";
            setResultReportUrl(`/api/reports/${proj}`);
            setWaitingAgent(null);
            setPhase("done");
          }
        }

        // 暂停点：结构化 field_review 用工作流卡片展示；message 由编排层填入简短 Agent 气泡（可与卡片并存）
        if (d.event_type === "user_input_requested") {
          setGateOpen(false);  // 每次暂停默认关，有 gate 才开
          const dataObj = (d.data ?? {}) as Record<string, unknown>;
          const gatePayload = dataObj.gate as { phase?: string; prompt?: string } | undefined;
          const fr = parseFieldReview(dataObj.field_review);
          const ca = parseCleaningAssessment(dataObj.cleaning_assessment);
          const cr = parseCleaningReview(dataObj.cleaning_review);
          const ar = parseAnalystReview(dataObj.analyst_review);
          const incRev = parsePauseInteractionRevision(dataObj);
          const incomingRevision = incRev !== null ? incRev : Infinity;
          if (fr) {
            // 多轮对齐：同 revision 或递增 revision → 更新同一张卡片（不堆叠）；revision 未变时
            // 常见于闸门「还有补充」回到字段表（后端已递增 revision；此处兜底同号原地更新）。
            const patchInPlace =
              activeFieldReviewId !== null
              && (
                incomingRevision === activeFieldReviewRevision
                || incomingRevision > activeFieldReviewRevision
              );
            if (patchInPlace) {
              setMessages((prev) =>
                prev.map((m) =>
                  m.id === activeFieldReviewId ? { ...m, fieldReview: fr, timestamp: d.timestamp } : m,
                ),
              );
            } else {
              // 新卡片
              const wfId = uid();
              setActiveFieldReviewId(wfId);
              setMessages((prev) => [
                ...prev,
                {
                  id: wfId,
                  role: "workflow",
                  text: "",
                  timestamp: d.timestamp,
                  fieldReview: fr,
                },
              ]);
            }
            setActiveFieldReviewRevision(incomingRevision);
            setFieldReviewScrollNonce((n) => n + 1);
          } else if (!gatePayload && !cr && !ar) {
            // 非结构化暂停（且无清洗/分析卡）时才清 field_review 追踪；避免 Cleaner 暂停误清
            setActiveFieldReviewId(null);
            setActiveFieldReviewRevision(-1);
            setFieldReviewScrollNonce(0);
          }
          if (cr) {
            const patchCleaning =
              activeCleaningReviewId !== null
              && incRev !== null
              && (
                incRev === activeCleaningReviewRevision
                || incRev > activeCleaningReviewRevision
              );
            if (patchCleaning) {
              setMessages((prev) =>
                prev.map((m) =>
                  m.id === activeCleaningReviewId
                    ? { ...m, cleaningReview: cr, timestamp: d.timestamp }
                    : m,
                ),
              );
            } else {
              const cid = uid();
              setActiveCleaningReviewId(cid);
              setMessages((prev) => [
                ...prev,
                {
                  id: cid,
                  role: "workflow",
                  text: "",
                  timestamp: d.timestamp,
                  cleaningReview: cr,
                },
              ]);
            }
            if (incRev !== null) setActiveCleaningReviewRevision(incRev);
          } else {
            setActiveCleaningReviewId(null);
            setActiveCleaningReviewRevision(-1);
          }
          if (ca) {
            // 清洗评估：结构化展示 LLM 的大白话评估
            const cid = uid();
            const colLines = ca.columns.map((c) =>
              `<tr><td style="padding:4px 8px;border:1px solid #2a3040">${c.column}</td><td style="padding:4px 8px;border:1px solid #2a3040;color:#4ade80">${c.action === "clean" ? "清洗" : "不清洗"}</td><td style="padding:4px 8px;border:1px solid #2a3040">${c.reason}</td></tr>`
            ).join("");
            const tableHtml = `<div style="margin-top:8px"><table style="width:100%;border-collapse:collapse;font-size:14px"><thead><tr style="background:#1e2430"><th style="padding:6px 8px;border:1px solid #2a3040;text-align:left">字段</th><th style="padding:6px 8px;border:1px solid #2a3040;text-align:center;width:80px">建议</th><th style="padding:6px 8px;border:1px solid #2a3040;text-align:left">原因</th></tr></thead><tbody>${colLines}</tbody></table></div>`;
            setMessages((prev) => [
              ...prev,
              {
                id: cid,
                role: "agent",
                text: ca.summary,
                html: `<p><strong>${ca.summary}</strong></p>${tableHtml}`,
                timestamp: d.timestamp,
              } as ConvoMessage,
            ]);
          }
          if (ar) {
            const patchAnalyst =
              activeAnalystReviewId !== null
              && incRev !== null
              && (
                incRev === activeAnalystReviewRevision
                || incRev > activeAnalystReviewRevision
              );
            if (patchAnalyst) {
              setMessages((prev) =>
                prev.map((m) =>
                  m.id === activeAnalystReviewId
                    ? { ...m, analystReview: ar, timestamp: d.timestamp }
                    : m,
                ),
              );
            } else {
              const aid = uid();
              setActiveAnalystReviewId(aid);
              setMessages((prev) => [
                ...prev,
                {
                  id: aid,
                  role: "workflow",
                  text: "",
                  timestamp: d.timestamp,
                  analystReview: ar,
                },
              ]);
            }
            if (incRev !== null) setActiveAnalystReviewRevision(incRev);
          } else {
            setActiveAnalystReviewId(null);
            setActiveAnalystReviewRevision(-1);
          }
          // 跨阶段闸门：gate_to_cleaning（Scout 对齐后、进入清洗前）
          if (gatePayload) {
            setGateOpen(true);
            const prompt =
              typeof gatePayload.prompt === "string" ? gatePayload.prompt.trim() : "";
            if (prompt) {
              const gateId = uid();
              setMessages((prev) => [
                ...prev,
                {
                  id: gateId,
                  role: "workflow",
                  text: prompt,
                  timestamp: d.timestamp,
                },
              ]);
            }
          }
          const raw = dataObj.message;
          const agentMsg = typeof raw === "string" ? raw.trim() : "";
          if (agentMsg) {
            setMessages((prev) => [
              ...prev,
              { id: uid(), role: "agent", text: agentMsg, timestamp: d.timestamp },
            ]);
          }
          const pausedAgent = resolveAgentKey(d.agent) ?? "scout";
          setWaitingAgent(pausedAgent);
          setPhase("running");
          setTimeout(() => replyInputRef.current?.focus(), 100);
        }

        if (d.event_type === "user_input_received") {
          const inner = (d.data ?? {}) as Record<string, unknown>;
          if (agentKey === "scout") {
            const hasNewFields =
              "parse_applied_count" in inner
              || "columns_still_needing_input" in inner
              || "pure_confirm" in inner;
            let line = "";
            if (hasNewFields) {
              line = formatScoutUserInputFactLine(inner);
            } else {
              const applied = inner.applied_field_updates;
              const lines = Array.isArray(applied)
                ? applied.filter((x): x is string => typeof x === "string" && x !== null && (x as string).trim() !== "")
                : [];
              if (lines.length > 0) {
                line = `字段理解写入: ${lines.join("；")}`;
              }
            }
            if (line) {
              setMessages((prev) => [
                ...prev,
                { id: uid(), role: "system", text: line, timestamp: d.timestamp },
              ]);
            }
          } else if (agentKey === "cleaner" && typeof inner.proceed_accepted === "boolean") {
            setMessages((prev) => [
              ...prev,
              {
                id: uid(),
                role: "system",
                text: formatStageProceedFactLine("清洗", inner),
                timestamp: d.timestamp,
              },
            ]);
          } else if (agentKey === "analyst" && typeof inner.proceed_accepted === "boolean") {
            setMessages((prev) => [
              ...prev,
              {
                id: uid(),
                role: "system",
                text: formatStageProceedFactLine("统计", inner),
                timestamp: d.timestamp,
              },
            ]);
          }
        }

        // Run completed with guardrails blocked（说明走底部 CTA，不插固定对话文案）
        if (d.event_type === "run_completed") {
          const runPayload = (d.data ?? {}) as Record<string, unknown>;
          if (runPayload.cancelled === true) {
            setWaitingAgent(null);
            setActiveFieldReviewId(null);
            setActiveFieldReviewRevision(-1);
            setFieldReviewScrollNonce(0);
            setActiveCleaningReviewId(null);
            setActiveCleaningReviewRevision(-1);
            setActiveAnalystReviewId(null);
            setActiveAnalystReviewRevision(-1);
            setGateOpen(false);
            setPhase("setup");
            setAgentStates({ scout: "idle", cleaner: "idle", analyst: "idle", reporter: "idle" });
            setAgentElapsed({ scout: 0, cleaner: 0, analyst: 0, reporter: 0 });
            setResultReportUrl(null);
            setGuardrailsBlocked(false);
            setBlockedRunId(null);
            continue;
          }
          const gr = guardrailsRunCompletedInfo({
            event_type: d.event_type,
            agent: d.agent,
            data: d.data as Record<string, unknown> | undefined,
          });
          if (gr.guardrailsBlocked) {
            setGuardrailsBlocked(true);
            if (gr.runId) setBlockedRunId(gr.runId);
            setWaitingAgent(null);
            setActiveFieldReviewId(null);
            setActiveFieldReviewRevision(-1);
            setFieldReviewScrollNonce(0);
            setActiveCleaningReviewId(null);
            setActiveCleaningReviewRevision(-1);
            setActiveAnalystReviewId(null);
            setActiveAnalystReviewRevision(-1);
            setGateOpen(false);
            setPhase("done");
          }
        }
      }
    }
  }, [batch]);

  const submitUserReply = useCallback(
    (raw: string) => {
      if (!waitingAgent) return;
      const outgoing = raw.trim();
      if (!outgoing) return;
      const displayBubble = outgoing;
      replySnapshotRef.current = { agent: waitingAgent, gate: gateOpen };
      const sent = send("respond", { text: outgoing });
      if (!sent) {
        replySnapshotRef.current = null;
        setMessages((prev) => [
          ...prev,
          {
            id: uid(),
            role: "system",
            text: "当前未连接到服务器，回复未发出。请确认右上角连接状态后重试。",
            timestamp: new Date().toISOString(),
          },
        ]);
        return;
      }
      const ts = new Date().toISOString();
      setMessages((prev) => [
        ...prev,
        {
          id: uid(),
          role: "user",
          text: displayBubble,
          timestamp: ts,
        },
      ]);
      setReplyText("");
    setQueryText("");
      setWaitingAgent(null);
      setGateOpen(false);
      // 多轮对齐：不清 activeFieldReviewId / activeCleaningReviewId / activeAnalystReviewId；
      // 下一轮 user_input_requested 依赖同一 id 原地更新工作流卡片。
    },
    [send, waitingAgent, gateOpen],
  );

  const handleReply = useCallback(() => {
    submitUserReply(replyText);
  }, [submitUserReply, replyText]);

  /** 与 PROJECT.md「人机互动」一致：不在此步插入固定 Agent 话术；由编排层在暂停点生成说明。 */
  const handleStartSession = useCallback(() => {
    if (!currentProject || !dataPath) return;
    setMessages([]);
    setAgentStates({ scout: "idle", cleaner: "idle", analyst: "idle", reporter: "idle" });
    setAgentElapsed({ scout: 0, cleaner: 0, analyst: 0, reporter: 0 });
    setGuardrailsBlocked(false);
    setBlockedRunId(null);
    setResultReportUrl(null);
    setWaitingAgent(null);
    setReplyText("");
    setActiveFieldReviewId(null);
    setActiveFieldReviewRevision(-1);
    setFieldReviewScrollNonce(0);
    setActiveCleaningReviewId(null);
    setActiveCleaningReviewRevision(-1);
    setActiveAnalystReviewId(null);
    setActiveAnalystReviewRevision(-1);
    setGateOpen(false);
    setPhase("running");
    send("analyze", {
      data_path: dataPath,
      query: queryText.trim() || "",
      project_name: currentProject ?? "default",
      phase: "full",
    });
  }, [send, dataPath, currentProject, queryText]);

  const handleReset = useCallback(() => {
    send("cancel_analysis", {});
    resetRunUiState();
    setPhase("setup");
    setMessages([]);
    setWaitingAgent(null);
    setReplyText("");
    setActiveFieldReviewId(null);
    setActiveFieldReviewRevision(-1);
    setFieldReviewScrollNonce(0);
    setActiveCleaningReviewId(null);
    setActiveCleaningReviewRevision(-1);
    setActiveAnalystReviewId(null);
    setActiveAnalystReviewRevision(-1);
    setGateOpen(false);
    setResultReportUrl(null);
    setGuardrailsBlocked(false);
    setBlockedRunId(null);
    setAgentStates({ scout: "idle", cleaner: "idle", analyst: "idle", reporter: "idle" });
    setAgentElapsed({ scout: 0, cleaner: 0, analyst: 0, reporter: 0 });
  }, [send, resetRunUiState]);

  const handleUpload = useCallback(async (file: File) => {
    if (!currentProject) return;
    setUploading(true);
    setUploadError(null);
    const form = new FormData();
    form.append("file", file);
    try {
      const res = await fetch(`/api/projects/${currentProject}/upload`, { method: "POST", body: form });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: "上传失败" }));
        throw new Error(err.detail ?? "上传失败");
      }
      const data = await res.json() as { path: string };
      setDataPath(data.path);
      loadFiles(currentProject);
    } catch (e) {
      setUploadError(e instanceof Error ? e.message : "上传失败");
    } finally {
      setUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  }, [currentProject, loadFiles]);

  const selectedFileName = dataPath ? dataPath.split("/").pop() ?? dataPath : null;
  const [fileExists, setFileExists] = useState(false);
  useEffect(() => {
    if (!currentProject || !dataPath) { setFileExists(false); return; }
    fetch(`/api/projects/${currentProject}/files`)
      .then(r => r.json())
      .then((d: { files?: Array<{path: string}> }) => {
        setFileExists((d.files || []).some((f: {path: string}) => f.path === dataPath));
      })
      .catch(() => setFileExists(false));
  }, [currentProject, dataPath]);
  const canStart = !!currentProject && !!dataPath && fileExists && connectionStatus === "connected";
  const scoutFieldReviewOpen =
    Boolean(activeFieldReviewId) && waitingAgent === "scout";
  const cleanerCleaningReviewOpen =
    Boolean(activeCleaningReviewId) && waitingAgent === "cleaner";
  const analystReviewOpen =
    Boolean(activeAnalystReviewId) && waitingAgent === "analyst";
  const canSendReply =
    !!waitingAgent && replyText.trim().length > 0;
  return (
    <div className="h-full flex flex-col bg-app-bg text-app-text relative">
      <PanelHeader title="分析">
        {(
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={handleReset}
              className="flex items-center gap-1 px-2 py-0.5 border border-app-border rounded text-ui-xs normal-case tracking-normal font-medium text-app-text
                hover:border-app-accent hover:text-app-accent transition-colors cursor-pointer"
            >
              <RotateCcw size={12} />
              重置分析
            </button>
            <ClearHistoryButton currentProject={currentProject} />
          </div>
        )}
      </PanelHeader>

      {/* ── Connection overlay ── */}
      {connectionStatus === "disconnected" && (
        <div className="absolute inset-0 bg-app-bg/90 flex flex-col items-center justify-center gap-2 z-20">
          <WifiOff size={28} className="text-app-text-muted" />
          <span className="text-ui-base text-app-error">连接断开</span>
          <span className="text-ui-xs text-app-text-muted">正在重新连接…</span>
        </div>
      )}
      {(connectionStatus === "connecting" || connectionStatus === "reconnecting") && (
        <div className="absolute inset-0 z-20 flex flex-col items-center justify-center gap-2 bg-app-bg/80 backdrop-blur-sm">
          <Loader2 size={20} className="animate-spin text-app-accent" />
          <span className="text-ui-sm text-app-text-muted">正在连接服务器…</span>
        </div>
      )}

      {/* ── Setup: project + file selectors ── */}
      <div className="px-3 py-2 border-b border-app-border bg-app-bg-secondary shrink-0 space-y-2">
        {/* Project selector */}
        <div className="flex items-center gap-2">
          <span className="text-ui-xs text-app-text-muted w-12 shrink-0">项目</span>
          <div className="relative flex-1" ref={projectDropdownRef}>
            <button
              onClick={() => setShowProjectDropdown((v) => !v)}
              disabled={phase === "running"}
              className={`w-full flex items-center gap-2 px-2 py-1.5 bg-app-bg border rounded
                         text-ui-sm transition-colors
                         ${phase !== "running"
                           ? "border-app-border hover:border-app-accent cursor-pointer text-app-text"
                           : "border-app-border opacity-50 cursor-not-allowed text-app-text-muted"}`}
            >
              <FolderOpen size={13} className="text-app-accent shrink-0" />
              <span className="flex-1 text-left truncate font-mono">{currentProject ?? "— 选择项目 —"}</span>
              <ChevronDown size={12} className="text-app-text-muted shrink-0" />
            </button>
            {showProjectDropdown && (
              <div className="absolute left-0 right-0 top-full mt-1 z-30 bg-app-bg-secondary border border-app-border rounded shadow-lg max-h-48 overflow-y-auto">
                {projects.length === 0
                  ? <div className="px-3 py-2 text-ui-xs text-app-text-muted">暂无项目</div>
                  : projects.map((p) => (
                    <button key={p} onClick={() => { setCurrentProject(p); setShowProjectDropdown(false); }}
                      className={`w-full text-left px-3 py-1.5 text-ui-sm font-mono hover:bg-app-bg cursor-pointer
                        ${p === currentProject ? "text-app-accent" : "text-app-text"}`}>
                      {p === currentProject && <CheckCircle2 size={11} className="inline mr-1.5 text-app-accent" />}
                      {p}
                    </button>
                  ))}
                <div className="border-t border-app-border">
                  <button onClick={() => { setShowProjectDropdown(false); setActiveView("projects"); }}
                    className="w-full text-left px-3 py-1.5 text-ui-xs text-app-accent hover:bg-app-bg cursor-pointer">
                    + 新建项目 →
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>

        {/* File selector */}
        <div className="flex items-center gap-2">
          <span className="text-ui-xs text-app-text-muted w-12 shrink-0">数据</span>
          <div className="relative flex-1" ref={dropdownRef}>
            <button
              disabled={!currentProject || phase === "running"}
              onClick={() => setShowFileDropdown((v) => !v)}
              className={`w-full flex items-center gap-2 px-2 py-1.5 bg-app-bg border rounded text-ui-sm transition-colors
                ${currentProject && phase !== "running"
                  ? "border-app-border hover:border-app-accent cursor-pointer text-app-text"
                  : "border-app-border opacity-40 cursor-not-allowed text-app-text-muted"}`}
            >
              <FileText size={13} className={selectedFileName ? "text-app-accent shrink-0" : "text-app-text-muted shrink-0"} />
              <span className="flex-1 text-left truncate font-mono text-ui-xs">{selectedFileName ?? "— 选择文件 —"}</span>
              {filesLoading
                ? <Loader2 size={12} className="animate-spin text-app-text-muted shrink-0" />
                : <ChevronDown size={12} className="text-app-text-muted shrink-0" />}
            </button>
            {showFileDropdown && currentProject && (
              <div className="absolute left-0 right-0 top-full mt-1 z-30 bg-app-bg-secondary border border-app-border rounded shadow-lg max-h-56 overflow-y-auto">
                {projectFiles.length === 0
                  ? <div className="px-3 py-3 text-ui-xs text-app-text-muted text-center">暂无数据文件，请上传</div>
                  : projectFiles.map((f) => (
                    <button key={f.path} onClick={() => { setDataPath(f.path); setShowFileDropdown(false); }}
                      className={`w-full text-left px-3 py-2 hover:bg-app-bg cursor-pointer border-b border-app-border/50 last:border-0
                        ${f.path === dataPath ? "text-app-accent" : "text-app-text"}`}>
                      <div className="flex items-center gap-2">
                        {f.path === dataPath && <CheckCircle2 size={11} className="text-app-accent shrink-0" />}
                        <span className="text-ui-xs font-mono truncate flex-1">{f.name}</span>
                        <span className="text-ui-xs text-app-text-muted shrink-0">{fmtSize(f.size)}</span>
                      </div>
                    </button>
                  ))}
              </div>
            )}
          </div>
          {/* Upload button */}
          <div className="relative shrink-0">
            <input ref={fileInputRef} type="file"
              accept=".csv,.tsv,.json,.jsonl,.xlsx,.xls,.parquet,.txt"
              className="absolute inset-0 opacity-0 cursor-pointer w-full h-full"
              disabled={!currentProject || uploading || phase === "running"}
              onChange={(e) => { const f = e.target.files?.[0]; if (f) void handleUpload(f); }}
            />
            <button disabled={!currentProject || uploading || phase === "running"}
              className={`flex items-center gap-1 px-2 py-1.5 border rounded text-ui-xs transition-colors
                ${currentProject && !uploading && phase !== "running"
                  ? "border-app-accent text-app-accent hover:bg-app-accent hover:text-white cursor-pointer"
                  : "border-app-border text-app-text-muted opacity-40 cursor-not-allowed"}`}>
              {uploading ? <Loader2 size={12} className="animate-spin" /> : <Upload size={12} />}
              {uploading ? "上传中…" : "上传"}
            </button>
          </div>
        </div>
        {uploadError && (
          <div className="flex items-center gap-1 text-ui-xs text-app-error">
            <X size={11} />{uploadError}
            <button onClick={() => setUploadError(null)} className="ml-auto text-app-text-muted hover:text-app-text cursor-pointer">忽略</button>
          </div>
        )}
      </div>

      {/* ── Setup idle: start button ── */}
      {phase === "setup" && (
        <div className="flex-1 flex flex-col items-center justify-center gap-4 px-6">
          {!currentProject || !dataPath ? (
            <div className="text-center space-y-2">
              <div className="text-app-text-muted text-ui-sm">
                {!currentProject ? "请先选择一个项目" : "请选择或上传数据文件"}
              </div>
              <div className="text-app-text-muted text-ui-xs">准备好后点击"开始分析"</div>
            </div>
          ) : (
            <>
              <div className="text-center space-y-2">
                <div className="text-ui-sm text-app-text-muted">项目和数据文件已就绪</div>
                <div className="text-ui-xs text-app-text-muted opacity-60">
                  需要暂停确认时会在对话区提示，并在下方出现输入框
                </div>
              </div>
              <div className="w-full max-w-md">
                <textarea
                  value={queryText}
                  onChange={(e) => setQueryText(e.target.value)}
                  placeholder="你想分析什么？例如：这批广告投放的 ROI 如何？哪个渠道转化最高？"
                  rows={3}
                  className="w-full px-3 py-2 bg-app-bg border border-app-border rounded-md text-ui-sm text-app-text placeholder:text-app-text-muted focus:outline-none focus:border-app-accent resize-none transition-colors"
                />
              </div>
            </>
          )}
          <button
            onClick={handleStartSession}
            disabled={!canStart}
            className={`flex items-center gap-2 px-6 py-3 rounded-lg text-ui-base font-medium transition-all duration-200
              ${canStart
                ? "bg-app-accent hover:bg-app-accent-hover text-white cursor-pointer shadow-lg hover:shadow-app-accent/30 hover:-translate-y-0.5"
                : "bg-app-bg-secondary border border-app-border text-app-text-muted cursor-not-allowed"}`}
          >
            <PlayCircle size={18} />
            开始分析
          </button>
        </div>
      )}

      {/* ── Query / running / done: conversation view ── */}
      {phase !== "setup" && (
        <>
          {/* Pipeline bar */}
          <div className="px-3 py-2 border-b border-app-border shrink-0">
            <PipelineBar states={agentStates} elapsed={agentElapsed} />
          </div>

          {/* Running progress bar */}
          {status === "running" && (
            <div className="h-0.5 bg-app-accent animate-pulse shrink-0" />
          )}

          {/* Conversation feed */}
          <ConvoFeed
            messages={messages}
            scrollFieldTableId={activeFieldReviewId}
            scrollFieldTableNonce={fieldReviewScrollNonce}
          />

          {/* Agent reply input — shown when any agent is waiting */}
          {waitingAgent && (
            <div className="px-3 pb-2 shrink-0 border-t border-app-border/60 pt-2 motion-safe:transition-colors">
              {(cleanerCleaningReviewOpen) && (
                <div className="flex flex-wrap items-center gap-2 mb-2">
                  <button
                    type="button"
                    onClick={() => submitUserReply("确认继续")}
                    className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md text-ui-xs font-medium
                      bg-app-accent text-white hover:bg-app-accent-hover cursor-pointer motion-safe:transition-colors"
                  >
                    <CheckCircle2 size={14} />
                    确认继续
                  </button>
                </div>
              )}
              {analystReviewOpen && (
                <div className="flex flex-wrap items-center gap-2 mb-2">
                  <button
                    type="button"
                    onClick={() => submitUserReply("确认继续")}
                    className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md text-ui-xs font-medium
                      bg-app-accent text-white hover:bg-app-accent-hover cursor-pointer motion-safe:transition-colors"
                  >
                    <CheckCircle2 size={14} />
                    确认继续
                  </button>
                  <button
                    type="button"
                    onClick={() =>
                      submitUserReply("已核对上表中的 p 值、效应量与置信区间，同意进入报告阶段")}
                    className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md text-ui-xs font-medium border
                      border-app-border text-app-text hover:border-app-accent hover:text-app-accent cursor-pointer
                      motion-safe:transition-colors"
                  >
                    <FileText size={14} />
                    同意进入报告
                  </button>
                </div>
              )}
              {scoutFieldReviewOpen && !gateOpen && (
                <div className="flex flex-wrap items-center gap-2 mb-2">
                  <button
                    type="button"
                    onClick={() => submitUserReply("可以进入下一阶段了")}
                    className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md text-ui-xs font-medium
                      bg-app-accent text-white hover:bg-app-accent-hover cursor-pointer motion-safe:transition-colors"
                  >
                    <CheckCircle2 size={14} />
                    进入下一阶段
                  </button>
                </div>
              )}
              {waitingAgent === "cleaner" && (
                <div className="flex flex-wrap items-center gap-2 mb-2">
                  <button
                    type="button"
                    onClick={() => submitUserReply("确认继续")}
                    className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md text-ui-xs font-medium
                      bg-app-accent text-white hover:bg-app-accent-hover cursor-pointer motion-safe:transition-colors"
                  >
                    <CheckCircle2 size={14} />
                    确认
                  </button>
                </div>
              )}
              <div className="flex gap-2 items-end">
                <textarea
                  ref={replyInputRef}
                  value={replyText}
                  onChange={(e) => setReplyText(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key !== "Enter" || e.shiftKey) return;
                    // 中文输入法用 Enter 确认候选时勿 preventDefault，否则无法上屏
                    const ne = e.nativeEvent as unknown as { isComposing?: boolean; keyCode?: number };
                    if (e.nativeEvent.isComposing || ne.keyCode === 229) {
                      return;
                    }
                    e.preventDefault();
                    if (canSendReply) submitUserReply(replyText);
                  }}
                  placeholder={
                    waitingAgent === "cleaner" && !cleanerCleaningReviewOpen
                      ? "不同意建议？输入你的想法后 Enter 发送；进入下一阶段请点上方按钮"
                      : scoutFieldReviewOpen
                      ? "字段理解不对时输入说明，Enter 发送；进入下一阶段请点上方按钮"
                      : cleanerCleaningReviewOpen
                        ? "补充说明后 Enter 发送；确认结果请点上方按钮"
                        : analystReviewOpen
                          ? "补充关注点后 Enter 发送；确认结果请点上方按钮"
                          : gateOpen && waitingAgent === "scout"
                            ? "补充说明后 Enter 发送；确认请点上方按钮"
                            : "输入回复后 Enter 发送 · Shift+Enter 换行"
                  }
                  rows={2}
                  className={`flex-1 bg-app-bg-secondary border rounded px-3 py-2
                             text-ui-sm text-app-text placeholder-app-text-muted resize-none
                             focus:outline-none transition-colors
                             ${scoutFieldReviewOpen
                               ? "border-app-accent ring-1 ring-app-accent/30"
                               : cleanerCleaningReviewOpen
                                 ? "border-app-success/50 ring-1 ring-app-success/20"
                                 : analystReviewOpen
                                   ? "border-app-accent/60 ring-1 ring-app-accent/25"
                                   : "border-app-accent/50 focus:border-app-accent"}`}
                />
                <button
                  type="button"
                  onClick={handleReply}
                  disabled={!canSendReply}
                  className={`px-4 py-2 rounded text-ui-sm font-medium transition-colors shrink-0 flex items-center gap-1.5
                    ${canSendReply
                      ? "bg-app-accent hover:bg-app-accent-hover text-white cursor-pointer"
                      : "bg-app-bg-secondary border border-app-border text-app-text-muted cursor-not-allowed"}`}
                >
                  <ArrowRight size={14} />
                  发送
                </button>
              </div>
              <div className="mt-1 text-ui-xs text-app-text-muted">
                {scoutFieldReviewOpen
                  ? "用自然语言说明字段理解即可 · Scout 会带入后续 · Enter 发送 · Shift+Enter 换行"
                  : cleanerCleaningReviewOpen
                    ? "补充说明后 Enter 发送 · Shift+Enter 换行"
                    : analystReviewOpen
                      ? "补充关注点后 Enter 发送 · Shift+Enter 换行"
                      : gateOpen && waitingAgent === "scout"
                        ? "补充说明后 Enter 发送 · Shift+Enter 换行"
                    : "Enter 发送 · Shift+Enter 换行"}
              </div>
            </div>
          )}

          {/* Done: report link + reset */}
          {phase === "done" && resultReportUrl && !guardrailsBlocked && (
            <div className="mx-3 mb-3 p-3 bg-app-bg-secondary border border-app-success rounded flex items-center justify-between gap-3 shrink-0">
              <div>
                <div className="text-ui-xs text-app-success font-semibold mb-0.5">分析完成</div>
                <div className="text-ui-sm text-app-text">报告已生成</div>
              </div>
              <div className="flex items-center gap-2 shrink-0">
                <a href={resultReportUrl} target="_blank" rel="noopener noreferrer"
                  className="px-3 py-1.5 bg-app-accent hover:bg-app-accent-hover text-white text-ui-xs rounded cursor-pointer transition-colors whitespace-nowrap flex items-center gap-1">
                  查看报告 <ArrowRight size={12} />
                </a>
                <button onClick={handleReset}
                  className="px-3 py-1.5 border border-app-border text-app-text-muted hover:text-app-text text-ui-xs rounded cursor-pointer transition-colors flex items-center gap-1">
                  <RotateCcw size={12} /> 再次分析
                </button>
              </div>
            </div>
          )}

          {/* Done: guardrails blocked — different UI */}
          {phase === "done" && guardrailsBlocked && (
            <div className="mx-3 mb-3 p-3 bg-app-bg-secondary border border-app-warning rounded flex items-center justify-between gap-3 shrink-0">
              <div>
                <div className="text-ui-xs text-app-warning font-semibold mb-0.5 flex items-center gap-1">
                  <ShieldAlert size={12} />
                  报告未生成
                </div>
                <div className="text-ui-sm text-app-text">统计护栏未通过，请查看说明</div>
              </div>
              <div className="flex items-center gap-2 shrink-0">
                {blockedRunId && currentProject && (
                  <a
                    href={`/api/reports/${currentProject}/${blockedRunId}/GUARDRAILS_BLOCKED.md`}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="px-3 py-1.5 bg-app-warning hover:bg-app-warning-hover text-white text-ui-xs rounded cursor-pointer transition-colors whitespace-nowrap flex items-center gap-1"
                  >
                    <ShieldAlert size={12} />
                    查看护栏说明
                  </a>
                )}
                <button onClick={handleReset}
                  className="px-3 py-1.5 border border-app-border text-app-text-muted hover:text-app-text text-ui-xs rounded cursor-pointer transition-colors flex items-center gap-1">
                  <RotateCcw size={12} /> 再次分析
                </button>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
