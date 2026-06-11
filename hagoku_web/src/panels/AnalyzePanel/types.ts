// ── Agent pipeline types ───────────────────────────────────────
export type AgentKey = "scout" | "cleaner" | "analyst" | "reporter";
export type AgentRunState = "idle" | "running" | "done" | "error" | "skipped";

// ── Session ────────────────────────────────────────────────────
export type SessionPhase = "setup" | "running" | "done";

/** Scout 字段核对：后端 `field_review`（列：字段名称 / 中文名称 / 含义理解 / 分析角色） */
export interface FieldReviewPayload {
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
    /** LLM 对参与分析的判断原因 */
    evidence?: string;
    /** 建议分析角色：target / feature / identifier（由 Scout 语义推断） */
    suggested_role: string;
    needs_attention?: boolean;
    /** 用户是否明确指定该字段参与本次分析（true/false/null） */
    used_in_analysis?: boolean | null;
  }>;
}

/** Cleaner 评估：后端 `cleaning_assessment` — LLM 的自由文本评估 */
export interface CleaningAssessment {
  summary: string;
  columns: Array<{
    column: string;
    display_name?: string;
    action: "skip" | "clean";
    reason: string;
    operations?: Array<{ strategy: string }>;
  }>;
}

/** Cleaner 核对：后端 `cleaning_review` 结构化载荷（非 Agent 台词） */
export interface CleaningReviewPayload {
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

/** Analyst 结果核对：后端 `analyst_review` 结构化载荷（非 Agent 台词） */
export interface AnalystReviewPayload {
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

// ── Conversation ───────────────────────────────────────────────

export interface ConvoMessage {
  id: string;
  role: "system" | "user" | "agent" | "workflow";
  text: string;
  timestamp: string;
  html?: string;
  fieldReview?: FieldReviewPayload;
  cleaningReview?: CleaningReviewPayload;
  analystReview?: AnalystReviewPayload;
  /** CO-13: tool_exchange payload for ToolExchangeTurn rendering */
  toolExchange?: {
    stage: string;
    tool_calls: Array<{
      id: string;
      name: string;
      arguments_summary?: string;
      result_summary?: string;
      error?: string | null;
      duration_ms?: number;
    }>;
    assistant_pre_text?: string | null;
  };
  /** CO-14: ask_user payload for AskUserPrompt rendering */
  askUser?: {
    question: string;
    expected_format: string;
    options?: string[];
  };
  /** CO-19: whether this message is still being streamed */
  streaming?: boolean;
  /** CO-19: stream_id for delta merging */
  streamId?: string;
}

export interface ProjectFile {
  name: string;
  path: string;
  size: number;
  mtime: number;
}
