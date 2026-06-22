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

