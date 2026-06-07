"""Cleaner 阶段暂停载荷 + 辅助函数。CH-5 从 orchestrator.py 拆分。"""
from __future__ import annotations

from typing import Any

def _normalize_cleaning_operation(op: Any) -> dict[str, Any]:
    """CleaningOp / dict 统一为 dict，供 prompt 与 cleaning_review 载荷使用。"""
    if op is None:
        return {}
    if isinstance(op, dict):
        return op
    if hasattr(op, "to_dict") and callable(getattr(op, "to_dict")):
        try:
            return dict(op.to_dict())  # type: ignore[arg-type]
        except Exception:
            pass
    col = getattr(op, "column", "") or ""
    strat = getattr(op, "strategy", "")
    if hasattr(strat, "value"):
        strat = strat.value
    reason = getattr(op, "reason", "") or ""
    ra = int(getattr(op, "rows_affected", 0) or 0)
    return {"column": str(col), "strategy": str(strat), "reason": str(reason), "rows_affected": ra}

def _cleaning_quality_display(
    report: Any,
    *,
    impact_rate: float,
    t_orig: int,
    t_after: int,
    fallback_label: str,
) -> str:
    """CleaningReport 无标准 data_quality 字段；避免把用户晾在 unknown 上。"""
    raw = (fallback_label or "").strip()
    if raw and raw.lower() != "unknown":
        return raw
    if t_orig <= 0:
        return "—"
    if t_after < t_orig:
        return "有删行"
    if impact_rate > 0.12:
        return "高影响（删行计）"
    if impact_rate > 0.04:
        return "中影响（删行计）"
    br = str(getattr(report, "bias_risk", "") or "").lower()
    if br in ("high", "medium"):
        return f"偏差风险 {br}"
    return "—"

def cleaning_review_pause_payload(
    cleaning_report: Any,
    *,
    data_quality: str,
    impact_rate: float,  # 与编排层传入一致；当前以报告内 impact_rate 为准
) -> dict[str, Any]:
    """Cleaner 暂停：结构化清洗结果表；`message` 留空，避免编排层写死「Agent 台词」。"""
    if cleaning_report is None:
        return {
            "message": "",
            "cleaning_review": {
                "data_quality": "—",
                "impact_rate": float(impact_rate or 0.0),
                "total_rows_original": 0,
                "total_rows_after": 0,
                "rows_removed": 0,
                "bias_risk": "unknown",
                "n_ops": 0,
                "warnings": [],
                "rows": [],
            },
        }
    ops_raw: list[Any] = list(getattr(cleaning_report, "operations", None) or [])
    rows: list[dict[str, Any]] = []
    for op in ops_raw[:120]:
        d = _normalize_cleaning_operation(op)
        col = str(d.get("column", "") or "")
        strat = str(d.get("strategy", "") or "")
        reason = str(d.get("reason", "") or "")
        if len(reason) > 400:
            reason = reason[:397] + "…"
        rows.append({
            "column": col,
            "strategy": strat,
            "reason": reason,
            "rows_affected": int(d.get("rows_affected", 0) or 0),
        })
    t_orig = int(getattr(cleaning_report, "total_rows_original", 0) or 0)
    t_after = int(getattr(cleaning_report, "total_rows_after", 0) or 0)
    bias = str(getattr(cleaning_report, "bias_risk", "unknown") or "unknown")
    warnings = getattr(cleaning_report, "warnings", None) or []
    if not isinstance(warnings, list):
        warnings = []
    warn_strs = [str(w) for w in warnings[:8] if str(w).strip()]
    rep_impact = float(getattr(cleaning_report, "impact_rate", 0) or float(impact_rate or 0.0))
    rows_removed = max(0, t_orig - t_after)
    dq = _cleaning_quality_display(
        cleaning_report,
        impact_rate=rep_impact,
        t_orig=t_orig,
        t_after=t_after,
        fallback_label=str(data_quality or ""),
    )
    return {
        "message": "",
        "cleaning_review": {
            "data_quality": dq,
            "impact_rate": rep_impact,
            "total_rows_original": t_orig,
            "total_rows_after": t_after,
            "rows_removed": rows_removed,
            "bias_risk": bias,
            "n_ops": len(ops_raw),
            "warnings": warn_strs,
            "rows": rows,
        },
    }

# ── 编排器 ────────────────────────────────────────────────────
