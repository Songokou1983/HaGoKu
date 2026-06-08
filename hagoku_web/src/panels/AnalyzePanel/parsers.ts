import type {
  AgentKey,
  FieldReviewPayload,
  CleaningAssessment,
  CleaningReviewPayload,
  AnalystReviewPayload,
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

// ── Pause interaction revision ─────────────────────────────────

export function parsePauseInteractionRevision(data: Record<string, unknown>): number | null {
  const v = data.interaction_revision;
  return typeof v === "number" && Number.isFinite(v) ? v : null;
}

// ── Field review parser ────────────────────────────────────────

export function parseFieldReview(raw: unknown): FieldReviewPayload | null {
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
      evidence: String(r.evidence ?? ''),
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

// ── Cleaning assessment parser ─────────────────────────────────

export function parseCleaningAssessment(raw: unknown): CleaningAssessment | null {
  if (!raw || typeof raw !== "object") return null;
  const d = raw as Record<string, unknown>;
  if (!Array.isArray(d.columns)) return null;
  return { summary: String(d.summary || ""), columns: (d.columns as any[]).map((c: any) => ({ ...c, reason: c.reason || c.reason || "" })) };
}

// ── Cleaning review parser ─────────────────────────────────────

export function parseCleaningReview(raw: unknown): CleaningReviewPayload | null {
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

// ── Analyst review parser ──────────────────────────────────────

export function parseAnalystReview(raw: unknown): AnalystReviewPayload | null {
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

// ── Helpers ────────────────────────────────────────────────────

export function significanceShort(s: string): string {
  if (s === "significant") return "显著";
  if (s === "not_significant") return "未显著";
  return s.trim() || "—";
}
