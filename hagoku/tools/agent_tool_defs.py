"""HaGoKu 工具定义 — 在注册表中注册所有 Agent 可用的工具。

导入此模块即完成注册。新增工具只需在此文件添加。
"""

from __future__ import annotations

import json as _json
from typing import Any

import numpy as np
import pandas as pd

from hagoku.tools.registry import Tool, agent_tools


# ═══════════════════════════════════════════════════════════════════
# 通用数据探查工具（所有 Agent 可用）
# ═══════════════════════════════════════════════════════════════════

def _handle_get_column_stats(args: dict, _ctx: dict, df: pd.DataFrame | None) -> dict:
    col = str(args.get("column", "") or args.get("column_name", ""))
    if df is None or col not in df.columns:
        return {"error": f"列 {col} 不存在"}
    s = df[col].dropna()
    result: dict[str, Any] = {"column": col, "dtype": str(df[col].dtype), "count": len(s)}
    if pd.api.types.is_numeric_dtype(s):
        result.update({
            "min": float(s.min()), "q25": float(s.quantile(0.25)),
            "median": float(s.median()), "q75": float(s.quantile(0.75)),
            "max": float(s.max()), "mean": round(float(s.mean()), 4),
            "std": round(float(s.std()), 4),
        })
    result["null_count"] = int(df[col].isna().sum())
    result["null_pct"] = round(result["null_count"] / max(len(df), 1), 4)
    return result


def _handle_get_sample_rows(args: dict, _ctx: dict, df: pd.DataFrame | None) -> dict:
    col = str(args.get("column", "") or args.get("column_name", ""))
    n = int(args.get("n", 10))
    if df is None or col not in df.columns:
        return {"error": f"列 {col} 不存在"}
    vals = df[col].dropna().unique()[:n].tolist()
    return {"column": col, "sample": [str(v) for v in vals], "unique_count": len(vals), "total": len(df[col].dropna())}


def _handle_list_columns(_args: dict, _ctx: dict, df: pd.DataFrame | None) -> dict:
    if df is None:
        return {"columns": []}
    return {
        "columns": [
            {"name": c, "dtype": str(df[c].dtype)}
            for c in df.columns
        ]
    }


def _handle_group_stats(args: dict, _ctx: dict, df: pd.DataFrame | None) -> dict:
    col = str(args.get("column", "") or args.get("column_name", ""))
    by = str(args.get("by", "") or args.get("group_by", ""))
    if df is None or col not in df.columns or by not in df.columns:
        return {"error": f"列 {col} 或分组列 {by} 不存在"}
    grouped = df.groupby(by)[col].agg(["count", "mean", "median", "min", "max"])
    return {str(k): v.to_dict() for k, v in grouped.iterrows()}


agent_tools.register(Tool(
    name="get_column_stats",
    description="获取某列的统计信息：min/q25/median/q75/max/mean/std/null_count",
    parameters={
        "type": "object",
        "properties": {"column": {"type": "string", "description": "列名"}},
        "required": ["column"],
    },
    handler=_handle_get_column_stats,
))

agent_tools.register(Tool(
    name="get_sample_rows",
    description="获取某列的抽样值，用于理解字段内容",
    parameters={
        "type": "object",
        "properties": {
            "column": {"type": "string", "description": "列名"},
            "n": {"type": "integer", "description": "抽取行数，默认 10"},
        },
        "required": ["column"],
    },
    handler=_handle_get_sample_rows,
))

agent_tools.register(Tool(
    name="list_columns",
    description="列出数据集中所有列名和类型",
    parameters={"type": "object", "properties": {}, "required": []},
    handler=_handle_list_columns,
))

agent_tools.register(Tool(
    name="group_stats",
    description="按某列分组，查看另一列的统计量。用于判断极端值是业务规律还是数据错误",
    parameters={
        "type": "object",
        "properties": {
            "column": {"type": "string", "description": "要统计的列"},
            "by": {"type": "string", "description": "分组依据列"},
        },
        "required": ["column", "by"],
    },
    handler=_handle_group_stats,
    agents=["cleaner", "analyst"],  # 仅 Cleaner/Analyst
))


# ═══════════════════════════════════════════════════════════════════
# 统一表格工具（所有 Agent 可用）
# ═══════════════════════════════════════════════════════════════════

def _handle_update_field_table(args: dict, ctx: dict, _df: pd.DataFrame | None) -> dict:
    """统一表格更新。代码只做 merge 写入，不判断。"""
    updates = args.get("columns", args.get("updates", {}))
    if isinstance(updates, list):
        updates = {str(c.get("column", "")): c for c in updates if c.get("column")}
    if not isinstance(updates, dict) or not updates:
        return {"error": "columns 为空"}

    semantics = ctx.get("column_semantics", [])
    sem_by_name = {str(s.get("column_name", "")): s for s in semantics}
    applied = []

    for col, info in updates.items():
        if not isinstance(info, dict):
            continue
        s = sem_by_name.get(col)
        if s is None:
            s = {"column_name": col}
            semantics.append(s)
            sem_by_name[col] = s
        for field in ("display_name", "description", "role", "cleaning", "cleaning_reason", "suggested_role"):
            if field in info:
                s[field] = info[field]
        if "in_analysis" in info:
            s["in_analysis"] = info["in_analysis"]
            s["used_in_analysis"] = info["in_analysis"]
        applied.append(col)

    ctx["column_semantics"] = semantics
    # 律 5：同步 column_display_names，避免平行存储导致的展示不一致
    display_names = ctx.setdefault("column_display_names", {})
    for col in applied:
        sem = sem_by_name.get(col, {})
        if sem.get("display_name"):
            display_names[col] = sem["display_name"]
    return {"updated": applied}


agent_tools.register(Tool(
    name="update_field_table",
    description="更新字段表格。一次调用可修改多列的 display_name/description/role/in_analysis/cleaning/cleaning_reason。只需传要改的字段。",
    parameters={
        "type": "object",
        "properties": {
            "columns": {"type": "object", "description": "key=列名, value=要更新的字段"},
        },
        "required": ["columns"],
    },
    handler=_handle_update_field_table,
    agents=["scout", "cleaner", "analyst"],
))

# ═══════════════════════════════════════════════════════════════════
# Scout 字段理解工具
# ═══════════════════════════════════════════════════════════════════

def _handle_update_field_understanding(args: dict, ctx: dict, _df: pd.DataFrame | None) -> dict:
    """更新字段的中文名和含义。这个 handler 只返回结果，实际写入由 orchestrator 完成。"""
    return {
        "updated": args.get("column_name", ""),
        "display_name": args.get("display_name", ""),
        "description": args.get("description", ""),
    }


def _handle_update_field_role(args: dict, ctx: dict, _df: pd.DataFrame | None) -> dict:
    return {
        "target": args.get("target", ""),
        "features": args.get("features", []),
        "ignored": args.get("ignored", []),
    }


def _handle_restrict_analysis_to(args: dict, ctx: dict, _df: pd.DataFrame | None) -> dict:
    return {
        "included_fields": args.get("included_fields", []),
    }


def _handle_update_analysis_scope(args: dict, ctx: dict, _df: pd.DataFrame | None) -> dict:
    """更新分析范围——纳入或排除字段。"""
    add_columns = args.get("add_columns", []) or []
    remove_columns = args.get("remove_columns", []) or []
    reason = args.get("reason", "")

    semantics = ctx.get("column_semantics", [])
    updated_add: list[str] = []
    updated_remove: list[str] = []

    for sem in semantics:
        col = str(sem.get("column_name", ""))
        if col in add_columns:
            sem["used_in_analysis"] = True
            updated_add.append(col)
        if col in remove_columns:
            sem["used_in_analysis"] = False
            updated_remove.append(col)

    ctx["_pending_scope_update"] = True

    return {
        "added": updated_add,
        "removed": updated_remove,
        "reason": reason,
    }


agent_tools.register(Tool(
    name="update_field_understanding",
    description="更新字段的中文名（display_name）或业务含义（description）。列名和业务名均可",
    parameters={
        "type": "object",
        "properties": {
            "column_name": {"type": "string", "description": "列名或已确认的业务名"},
            "display_name": {"type": "string", "description": "简短中文名称"},
            "description": {"type": "string", "description": "业务含义说明"},
            "suggested_role": {"type": "string", "enum": ["target", "feature", "identifier", "ignore"]},
            "used_in_analysis": {"type": "boolean"},
            "evidence": {"type": "string", "description": "参与分析的理由，与 used_in_analysis 保持一致"},
        },
        "required": ["column_name"],
    },
    handler=_handle_update_field_understanding,
    agents=["scout"],
))

agent_tools.register(Tool(
    name="update_field_role",
    description="设置分析的 target/features/ignored 字段",
    parameters={
        "type": "object",
        "properties": {
            "target": {"type": "string", "description": "目标变量"},
            "features": {"type": "array", "items": {"type": "string"}},
            "ignored": {"type": "array", "items": {"type": "string"}},
        },
        "required": [],
    },
    handler=_handle_update_field_role,
    agents=["scout"],
))

def _handle_update_assessment(args: dict, ctx: dict, _df: pd.DataFrame | None) -> dict:
    """更新评估表格中某一行。context 中的 _cleaner_assessment 会被修改。"""
    assessment = ctx.get("_cleaner_assessment", {})
    cols = assessment.get("columns", [])
    target_col = str(args.get("column", ""))
    updated = False
    for c in cols:
        if c.get("column") == target_col:
            if "action" in args:
                c["action"] = args["action"]
                updated = True
            if "reason" in args:
                c["reason"] = args["reason"]
                updated = True
            break
    if updated:
        assessment["columns"] = cols
        ctx["_cleaner_assessment"] = assessment
    return {"updated": updated, "column": target_col}


agent_tools.register(Tool(
    name="update_assessment",
    description="修改清洗评估表格中某一行的建议或原因。仅在用户明确要求修改某列时调用。",
    parameters={
        "type": "object",
        "properties": {
            "column": {"type": "string", "description": "列名"},
            "action": {"type": "string", "enum": ["clean", "skip"]},
            "reason": {"type": "string", "description": "新的原因说明"},
        },
        "required": ["column"],
    },
    handler=_handle_update_assessment,
    agents=["cleaner"],
))

agent_tools.register(Tool(
    name="submit_assessment",
    description="提交清洗评估结果。action 只有 clean 或 skip，reason 是大白话原因说明",
    parameters={
        "type": "object",
        "properties": {
            "summary": {"type": "string", "description": "整体评估"},
            "columns": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "column": {"type": "string"},
                        "display_name": {"type": "string"},
                        "action": {"type": "string", "enum": ["clean", "skip"]},
                        "reason": {"type": "string"},
                        "operations": {"type": "array", "items": {"type": "object", "properties": {"strategy": {"type": "string"}}}},
                    },
                    "required": ["column", "action", "reason"],
                },
            },
        },
        "required": ["summary", "columns"],
    },
    handler=lambda args, ctx, df: args,
    agents=["cleaner"],
))

agent_tools.register(Tool(
    name="restrict_analysis_to",
    description="限定参与分析的字段，其余自动排除",
    parameters={
        "type": "object",
        "properties": {
            "included_fields": {"type": "array", "items": {"type": "string"}, "description": "要保留的字段，列名或业务名均可"},
            "rationale": {"type": "string", "description": "简要说明"},
        },
        "required": ["included_fields"],
    },
    handler=_handle_restrict_analysis_to,
    agents=["scout"],
))


# ═══════════════════════════════════════════════════════════════════
# Analyst 对话式分析工具
# ═══════════════════════════════════════════════════════════════════

def _handle_propose_method(args: dict, ctx: dict, _df: pd.DataFrame | None) -> dict:
    return {
        "method_name": args.get("method_name", ""),
        "reasoning": args.get("reasoning", ""),
        "prerequisites": args.get("prerequisites", ""),
    }

agent_tools.register(Tool(
    name="propose_method",
    description="向用户建议一种分析方法，说明理由和前提。调用后会暂停等待用户回复。用户可接受、否定或调整。",
    parameters={
        "type": "object",
        "properties": {
            "method_name": {"type": "string", "description": "方法名（如「趋势分解」「线性回归」「分组t检验」）"},
            "reasoning": {"type": "string", "description": "为什么建议这个方法"},
            "prerequisites": {"type": "string", "description": "前提条件（如「需要至少 30 个样本」）"},
        },
        "required": ["method_name", "reasoning"],
    },
    handler=_handle_propose_method,
    agents=["analyst"],
))


def _handle_ask_user(args: dict, ctx: dict, _df: pd.DataFrame | None) -> dict:
    return {
        "question": args.get("question", ""),
        "options": args.get("options", []),
    }

agent_tools.register(Tool(
    name="ask_user",
    description="向用户提问，需要用户方向性决策时使用。调用后会暂停等待用户回复。普通分析陈述用纯文本输出。如果你提供 options，前端渲染为可点击按钮。",
    parameters={
        "type": "object",
        "properties": {
            "question": {"type": "string", "description": "问题文本"},
            "options": {"type": "array", "items": {"type": "string"}, "description": "可选回复项"},
        },
        "required": ["question"],
    },
    handler=_handle_ask_user,
    agents=["analyst"],
))


def _handle_submit_analysis(args: dict, ctx: dict, _df: pd.DataFrame | None) -> dict:
    return {
        "findings": args.get("findings", []),
        "method_used": args.get("method_used", []),
        "summary": args.get("summary", ""),
    }

agent_tools.register(Tool(
    name="submit_analysis",
    description="提交分析发现，结束分析阶段。调用前确保已覆盖用户关心的方向。confidence 取 high/medium/low 三选一。",
    parameters={
        "type": "object",
        "properties": {
            "findings": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "detail": {"type": "string"},
                        "evidence_columns": {"type": "array", "items": {"type": "string"}},
                        "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
                    },
                    "required": ["title", "detail", "evidence_columns", "confidence"],
                },
            },
            "method_used": {"type": "array", "items": {"type": "string"}},
            "summary": {"type": "string"},
        },
        "required": ["findings", "method_used", "summary"],
    },
    handler=_handle_submit_analysis,
    agents=["analyst"],
))

import numpy as _np
from scipy import stats as _scipy_stats

def _handle_run_statistical_test(args: dict, ctx: dict, _df: pd.DataFrame | None) -> dict:
    test_type = str(args.get("test_type", "")).strip()
    columns = list(args.get("columns") or [])
    if not test_type or not columns or _df is None:
        return {"error": "test_type 和 columns 必填，且需要 DataFrame"}

    try:
        if test_type == "ttest" and len(columns) >= 2:
            a = _df[columns[0]].dropna().astype(float)
            b = _df[columns[1]].dropna().astype(float)
            stat, p = _scipy_stats.ttest_ind(a, b)
            return {"test": "ttest", "statistic": float(stat), "p_value": float(p)}
        elif test_type == "anova":
            groups = [_df[c].dropna().astype(float) for c in columns if c in _df.columns]
            if len(groups) >= 2:
                stat, p = _scipy_stats.f_oneway(*groups)
                return {"test": "anova", "statistic": float(stat), "p_value": float(p)}
        elif test_type == "pearson_r" and len(columns) >= 2:
            a = _df[columns[0]].dropna().astype(float)
            b = _df[columns[1]].dropna().astype(float)
            mask = a.notna() & b.notna()
            r, p = _scipy_stats.pearsonr(a[mask], b[mask])
            return {"test": "pearson_r", "statistic": float(r), "p_value": float(p)}
        elif test_type == "spearman_r" and len(columns) >= 2:
            a = _df[columns[0]].dropna().astype(float)
            b = _df[columns[1]].dropna().astype(float)
            mask = a.notna() & b.notna()
            r, p = _scipy_stats.spearmanr(a[mask], b[mask])
            return {"test": "spearman_r", "statistic": float(r), "p_value": float(p)}
        elif test_type == "chi2" and len(columns) >= 2:
            import pandas as _pd
            a = _df[columns[0]].dropna()
            b = _df[columns[1]].dropna()
            ct = _pd.crosstab(a, b)
            stat, p, dof, _ = _scipy_stats.chi2_contingency(ct)
            return {"test": "chi2", "statistic": float(stat), "p_value": float(p), "dof": int(dof)}
        elif test_type == "linear_regression" and len(columns) >= 2:
            import statsmodels.api as _sm
            import pandas as _pd
            X = _sm.add_constant(_df[columns[1:]].dropna().astype(float))
            y = _df[columns[0]].loc[X.index].dropna().astype(float)
            X = X.loc[y.index]
            model = _sm.OLS(y, X).fit()
            return {
                "test": "linear_regression",
                "r_squared": float(model.rsquared),
                "params": {str(k): float(v) for k, v in model.params.items()},
                "p_values": {str(k): float(v) for k, v in model.pvalues.items()},
            }
        elif test_type == "trend_decomposition" and columns:
            s = _df[columns[0]].dropna().astype(float)
            w = min(7, max(1, len(s) // 4))
            trend = s.rolling(window=w, center=True).mean()
            return {
                "test": "trend_decomposition",
                "column": columns[0],
                "trend_mean": float(trend.mean()) if not trend.isna().all() else None,
                "detrended_std": float((s - trend).std()) if not trend.isna().all() else None,
            }
        return {"error": f"不支持或参数不足: {test_type}"}
    except Exception as e:
        return {"error": str(e)}

agent_tools.register(Tool(
    name="run_statistical_test",
    description="执行统计检验。可用类型：ttest, anova, chi2, pearson_r, spearman_r, linear_regression, trend_decomposition",
    parameters={
        "type": "object",
        "properties": {
            "test_type": {"type": "string", "enum": ["ttest", "anova", "chi2", "pearson_r", "spearman_r", "linear_regression", "trend_decomposition"]},
            "columns": {"type": "array", "items": {"type": "string"}, "description": "列名（第一个通常是目标变量）"},
            "params": {"type": "object", "description": "额外参数"},
        },
        "required": ["test_type", "columns"],
    },
    handler=_handle_run_statistical_test,
    agents=["analyst"],
))


agent_tools.register(Tool(
    name="update_analysis_scope",
    description=(
        "调整分析范围——纳入或排除字段。调用前先检查字段数据质量（调 get_column_stats）。"
        "若空值率 < 20% 且无类型异常，可直接纳入。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "add_columns": {
                "type": "array",
                "items": {"type": "string"},
                "description": "纳入分析的列名列表",
            },
            "remove_columns": {
                "type": "array",
                "items": {"type": "string"},
                "description": "移出分析的列名列表",
            },
            "reason": {
                "type": "string",
                "description": "调整原因",
            },
        },
        "required": [],
    },
    handler=_handle_update_analysis_scope,
    agents=["analyst"],
))
