"""清洗增强工具 — CO-T19～T21

注册：
  CO-T19 detect_outliers         → cleaning.detect_outliers_iqr / zscore
  CO-T20 detect_missing_pattern  → cleaning.detect_missing_mechanism
  CO-T21 suggest_cleaning        → cleaning.suggest_cleaning_strategy
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from hagoku.tools.registry import Tool, agent_tools


# ═══════════════════════════════════════════════════════════════════
# CO-T19: detect_outliers
# ═══════════════════════════════════════════════════════════════════

def _handle_detect_outliers(args: dict, _ctx: dict, df: pd.DataFrame | None) -> dict:
    method = str(args.get("method", "iqr")).strip()
    columns = list(args.get("columns", []) or []) or None

    if df is None:
        return {"error": "需要 DataFrame"}

    try:
        if method == "zscore":
            from hagoku.tools.cleaning import detect_outliers_zscore
            threshold = args.get("threshold")
            return detect_outliers_zscore(
                df, columns=columns,
                threshold=float(threshold) if threshold is not None else None,
            )
        else:
            # 默认 IQR
            from hagoku.tools.cleaning import detect_outliers_iqr
            factor = args.get("factor")
            return detect_outliers_iqr(
                df, columns=columns,
                factor=float(factor) if factor is not None else None,
            )
    except Exception as e:
        return {"error": str(e)}


agent_tools.register(Tool(
    name="detect_outliers",
    description=(
        "检测数据中的异常值。method 可选: iqr（四分位距法）/ zscore（Z分数法）。"
        "可选 columns（指定要检测的列，默认所有数值列）。"
        "IQR 法可选 factor（默认 1.5）；Z-score 法可选 threshold（默认 3）。"
        "返回每列的异常值数量和比例。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "method": {
                "type": "string",
                "enum": ["iqr", "zscore"],
                "description": "检测方法: iqr（默认）/ zscore",
            },
            "columns": {"type": "array", "items": {"type": "string"}, "description": "要检测的列名（默认所有数值列）"},
            "factor": {"type": "number", "description": "IQR 倍数（默认 1.5）"},
            "threshold": {"type": "number", "description": "Z-score 阈值（默认 3）"},
        },
    },
    handler=_handle_detect_outliers,
    phase_tag=["评估清洗"],
))


# ═══════════════════════════════════════════════════════════════════
# CO-T20: detect_missing_pattern
# ═══════════════════════════════════════════════════════════════════

def _handle_detect_missing_pattern(args: dict, _ctx: dict, df: pd.DataFrame | None) -> dict:
    column = str(args.get("column", ""))
    if not column:
        # 无指定列时，返回所有有缺失列的机制
        if df is None:
            return {"error": "需要 DataFrame"}
        from hagoku.tools.cleaning import detect_missing_mechanism
        results: dict[str, str] = {}
        for col in df.columns:
            if df[col].isnull().any():
                try:
                    results[col] = detect_missing_mechanism(df, col)
                except Exception:
                    results[col] = "unknown"
        return {"missing_mechanisms": results}

    if df is None:
        return {"error": "需要 DataFrame"}
    if column not in df.columns:
        return {"error": f"列 {column} 不存在"}

    from hagoku.tools.cleaning import detect_missing_mechanism

    try:
        mechanism = detect_missing_mechanism(df, column)
        return {"column": column, "mechanism": mechanism}
    except Exception as e:
        return {"error": str(e)}


agent_tools.register(Tool(
    name="detect_missing_pattern",
    description=(
        "检测数据缺失机制：判断是 MCAR（完全随机缺失）、MAR（随机缺失）还是 MNAR（非随机缺失）。"
        "需传 column（目标列名）。不传 column 时返回所有有缺失列的机制概览。"
        "机制判断影响清洗策略选择：MCAR 可用简单填充，MAR 建议多重插补，MNAR 建议标记而非删除。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "column": {"type": "string", "description": "目标列名（不传则返回所有列的概览）"},
        },
    },
    handler=_handle_detect_missing_pattern,
    phase_tag=["评估清洗"],
))


# ═══════════════════════════════════════════════════════════════════
# CO-T21: suggest_cleaning
# ═══════════════════════════════════════════════════════════════════

def _handle_suggest_cleaning(args: dict, _ctx: dict, df: pd.DataFrame | None) -> dict:
    column = str(args.get("column", ""))
    if not column:
        return {"error": "column 必填"}
    if df is None:
        return {"error": "需要 DataFrame"}
    if column not in df.columns:
        return {"error": f"列 {column} 不存在"}

    from hagoku.tools.cleaning import suggest_cleaning_strategy

    null_rate = args.get("null_rate")
    missing_mechanism = args.get("missing_mechanism")

    try:
        strategy, reason = suggest_cleaning_strategy(
            df, column,
            null_rate=float(null_rate) if null_rate is not None else None,
            missing_mechanism=str(missing_mechanism) if missing_mechanism else None,
        )
        return {
            "column": column,
            "strategy": strategy.value if hasattr(strategy, "value") else str(strategy),
            "reason": reason,
        }
    except Exception as e:
        return {"error": str(e)}


agent_tools.register(Tool(
    name="suggest_cleaning",
    description=(
        "根据缺失率和缺失机制，建议最合适的清洗策略。"
        "需传 column（目标列名）。可选 null_rate（缺失率，不传则自动计算）和 "
        "missing_mechanism（来自 detect_missing_pattern 的结果，不传则自动检测）。"
        "返回建议策略 (drop_rows / fill_median / multiple_imputation / flag_and_keep 等) 和理由。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "column": {"type": "string", "description": "目标列名"},
            "null_rate": {"type": "number", "description": "缺失率（不传则自动计算）"},
            "missing_mechanism": {"type": "string", "description": "缺失机制: mcar / mar / mnar（不传则自动检测）"},
        },
        "required": ["column"],
    },
    handler=_handle_suggest_cleaning,
    phase_tag=["评估清洗"],
))
