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
    phase_tag=['评估清洗', '跑统计'],  # 仅 Cleaner/Analyst
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
    phase_tag=['理解字段', '评估清洗', '跑统计'],
))

# ═══════════════════════════════════════════════════════════════════
# Scout 字段理解工具
# ═══════════════════════════════════════════════════════════════════

def _handle_update_field_understanding(args: dict, ctx: dict, _df: pd.DataFrame | None) -> dict:
    """更新字段的中文名和含义，同步写入 column_semantics。支持单列或批量。"""
    # 批量模式: {"columns": [{"column_name": ..., "display_name": ..., ...}, ...]}
    batch = args.get("columns")
    if batch and isinstance(batch, list):
        results = []
        for item in batch:
            if isinstance(item, dict):
                results.append(_update_one_field(item, ctx))
        return {"updated_batch": results}

    # 单列模式（向后兼容）
    return _update_one_field(args, ctx)


def _update_one_field(args: dict, ctx: dict) -> dict:
    col = str(args.get("column_name", ""))
    dn = str(args.get("display_name", ""))
    desc = str(args.get("description", ""))
    role = str(args.get("suggested_role", ""))
    used = args.get("used_in_analysis")
    evidence = str(args.get("evidence", ""))

    semantics = ctx.get("column_semantics", [])
    updated = False
    for sem in semantics:
        sn = str(sem.get("column_name", ""))
        if sn == col or sem.get("display_name") == col or sem.get("chinese_name") == col:
            if dn:
                sem["display_name"] = dn
                sem["chinese_name"] = dn
            if desc:
                sem["description"] = desc
            if role:
                sem["suggested_role"] = role
            if used is not None:
                sem["used_in_analysis"] = bool(used)
            if evidence:
                sem["evidence"] = evidence
            updated = True

    if not updated:
        semantics.append({
            "column_name": col,
            "display_name": dn or col,
            "chinese_name": dn or col,
            "description": desc,
        })

    return {
        "updated": col,
        "display_name": dn,
        "description": desc,
        "synced_to_table": updated,
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

    # F-067 修复：检测 add/remove 交集。同一列同时出现在两侧说明 LLM
    # 给出了矛盾指令 —— 拒绝写入而非静默选一边（铁律 2 路径 A）。
    add_set = set(add_columns)
    remove_set = set(remove_columns)
    conflict = add_set & remove_set
    if conflict:
        raise ValueError(
            f"update_analysis_scope: 列 {sorted(conflict)} 同时出现在 "
            f"add_columns 和 remove_columns 中。请 LLM 明确该列是纳入还是排除。"
        )

    semantics = ctx.get("column_semantics", [])
    updated_add: list[str] = []
    updated_remove: list[str] = []

    for sem in semantics:
        col = str(sem.get("column_name", ""))
        if col in add_set:
            sem["used_in_analysis"] = True
            updated_add.append(col)
        if col in remove_set:
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
    description="更新字段的中文名或业务含义。单列用 column_name，批量用 columns 数组。",
    parameters={
        "type": "object",
        "properties": {
            "column_name": {"type": "string", "description": "列名或已确认的业务名（单列模式）"},
            "display_name": {"type": "string", "description": "简短中文名称"},
            "description": {"type": "string", "description": "业务含义说明"},
            "suggested_role": {"type": "string", "enum": ["target", "feature", "identifier", "ignore"]},
            "used_in_analysis": {"type": "boolean"},
            "evidence": {"type": "string", "description": "参与分析的理由"},
            "columns": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "column_name": {"type": "string"},
                        "display_name": {"type": "string"},
                        "description": {"type": "string"},
                        "suggested_role": {"type": "string", "enum": ["target", "feature", "identifier", "ignore"]},
                        "used_in_analysis": {"type": "boolean"},
                        "evidence": {"type": "string"},
                    },
                    "required": ["column_name"],
                },
                "description": "批量更新多列（推荐）",
            },
        },
        "required": [],
    },
    handler=_handle_update_field_understanding,
    phase_tag=['理解字段'],
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
    phase_tag=['理解字段'],
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
    phase_tag=['评估清洗'],
))

agent_tools.register(Tool(
    name="submit_assessment",
    description=(
        "【Cleaner 阶段专用】提交清洗评估结果，结束清洗评估阶段。\n"
        "调用此工具 = 告诉系统『我已完成所有列的清洗评估，可以进入分析阶段了』。\n"
        "每列必须有明确的 action（clean/skip）和 reason。调用后系统会记录评估结果。"
    ),
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
    phase_tag=['评估清洗'],
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
    phase_tag=['理解字段'],
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
    phase_tag=['跑统计'],
))


def _handle_ask_user(args: dict, ctx: dict, _df: pd.DataFrame | None) -> dict:
    """处理 LLM 的 ask_user 调用——触发暂停信号写入 context。

    orchestrator/reply_handlers 检测到 context["_pending_ask_user"] 后：
      1. emit USER_INPUT_REQUESTED 事件（payload 含 question/options/expected_format）
      2. 设置 _stage 仍为当前阶段（不切换）
      3. respond() 返回，等待 WS 收到用户回复后再走一轮
    """
    pending = {
        "question": args.get("question", ""),
        "options": args.get("options", []),
        "expected_format": args.get("expected_format", "free_text"),
        "asked_by_stage": ctx.get("_current_stage", "unknown"),
    }
    ctx["_pending_ask_user"] = pending
    return pending

agent_tools.register(Tool(
    name="ask_user",
    description=(
        "向用户提问并暂停等待回复。调用后 pipeline 进入暂停状态，等用户在 UI 回复。\n"
        "\n"
        "各阶段典型用法：\n"
        "  scout: 展示完字段理解表后 → ask_user(question='是否进入清洗评估？', expected_format='yes_no')\n"
        "  cleaner: 展示完清洗评估表后 → ask_user(question='清洗方案是否认可？', expected_format='yes_no')\n"
        "  analyst: 用户给出方向性选择时（如「用哪个模型」）→ ask_user(expected_format='choice', options=[...])\n"
        "\n"
        "用户选「是」/「确认」后，你必须紧接着调用 route_to 切换阶段。\n"
        "选「否」/「等等」则留在当前阶段继续对话。\n"
        "\n"
        "不适用：你只是想说一段话——直接输出文本，不要用此工具。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "question": {"type": "string", "description": "问题文本"},
            "options": {
                "type": "array", "items": {"type": "string"},
                "description": "可选回复项（让用户从中选）；若开放问题不传"
            },
            "expected_format": {
                "type": "string",
                "enum": ["choice", "free_text", "yes_no"],
                "description": "期望回复格式——UI 据此渲染单选/输入框/确认按钮"
            },
        },
        "required": ["question", "expected_format"],
    },
    handler=_handle_ask_user,
    phase_tag=['理解字段', '评估清洗', '跑统计', '写报告'],
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
    phase_tag=['跑统计'],
))


def _handle_submit_first_pass(args: dict, ctx: dict, _df: pd.DataFrame | None) -> dict:
    """首波自动分析完成，提交原始 findings 给 Orchestrator 重写为书面概括。"""
    return {
        "findings": args.get("findings", []),
        "method_used": args.get("method_used", []),
        "summary": args.get("summary", ""),
    }

agent_tools.register(Tool(
    name="submit_first_pass",
    description=(
        "【Analyst 阶段 1 专用】首波自动分析完成时调用。\n"
        "调用此工具 = 告诉系统『我的初始分析做完了，可以把发现展示给用户了』。\n"
        "系统会自动将你的发现重写为书面概括并展示，然后打开自由对话窗口。\n"
        "仅在 Analyst 阶段首次进入时使用；后续对话轮次使用 submit_analysis 提交最终结论。"
    ),
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
    handler=_handle_submit_first_pass,
    phase_tag=['跑统计'],
))




agent_tools.register(Tool(
    name="update_analysis_scope",
    description=(
        "调整分析范围——纳入或排除字段。调用前先检查字段数据质量（调 get_column_stats），"
        "根据实际数据自行判断是否满足分析要求。"
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
    phase_tag=['跑统计'],
))


# ═══════════════════════════════════════════════════════════════════
# Cleaner 对话式清洗工具
# ═══════════════════════════════════════════════════════════════════

def _handle_propose_cleaning_rule(args: dict, ctx: dict, _df: pd.DataFrame | None) -> dict:
    return {
        "column": args.get("column", ""),
        "rule": args.get("rule", ""),
        "reason": args.get("reason", ""),
    }

agent_tools.register(Tool(
    name="propose_cleaning_rule",
    description="提议一条清洗规则。包含目标列、规则内容和理由。用户确认后才会应用。",
    parameters={
        "type": "object",
        "properties": {
            "column": {"type": "string", "description": "目标列名"},
            "rule": {"type": "string", "description": "清洗规则内容（如「将空值填充为0」「剔除 Z>3 的离群值」）"},
            "reason": {"type": "string", "description": "提议这条规则的理由"},
        },
        "required": ["column", "rule", "reason"],
    },
    handler=_handle_propose_cleaning_rule,
    phase_tag=['评估清洗'],
))


def _handle_compare_before_after(args: dict, ctx: dict, df: pd.DataFrame | None) -> dict:
    """跑 before/after 对比，展示清洗规则对数据的影响。"""
    column = str(args.get("column", ""))
    rule = str(args.get("rule", ""))
    if df is None or column not in df.columns:
        return {"error": f"列 {column} 不存在"}
    before = {
        "count": int(len(df)),
        "nulls": int(df[column].isna().sum()),
    }
    if pd.api.types.is_numeric_dtype(df[column]):
        before.update({
            "mean": round(float(df[column].mean()), 4),
            "std": round(float(df[column].std()), 4),
            "min": float(df[column].min()),
            "max": float(df[column].max()),
        })
    return {
        "column": column,
        "rule": rule,
        "before": before,
        "note": "before/after 对比需由调用方在应用规则后计算 after 值。此工具仅返回当前状态（before）。",
    }

agent_tools.register(Tool(
    name="compare_before_after",
    description="对比清洗规则应用前后的数据变化。传入列名和规则描述，返回当前（before）统计值。",
    parameters={
        "type": "object",
        "properties": {
            "column": {"type": "string", "description": "目标列名"},
            "rule": {"type": "string", "description": "要对比的清洗规则"},
        },
        "required": ["column", "rule"],
    },
    handler=_handle_compare_before_after,
    phase_tag=['评估清洗'],
))


# ═══════════════════════════════════════════════════════════════════
# 流程路由工具（所有 Agent 可用）
# ═══════════════════════════════════════════════════════════════════

def _handle_route_to(args: dict, ctx: dict, _df: pd.DataFrame | None) -> dict:
    """LLM 表达流程意图。留在当前阶段或切换到下一阶段。"""
    stage = args.get("stage")
    reason = args.get("reason", "")
    return {"stage": stage, "reason": reason}


agent_tools.register(Tool(
    name="route_to",
    description=(
        "切换分析阶段。你必须在当前阶段的工作全部完成后才调用此工具。\n"
        "\n"
        "标准流程（必须按顺序）：\n"
        "  scout（字段理解完成） → route_to(stage='cleaner', reason='字段已确认')\n"
        "  cleaner（清洗评估完成） → route_to(stage='analyst', reason='清洗方案已确认')\n"
        "  analyst（统计分析完成） → route_to(stage='reporter', reason='结论已确定')\n"
        "\n"
        "规则：\n"
        "- 用户说「确认」「可以」「继续」「没问题」「进入下一步」→ 你必须调 route_to 切换阶段，不要停留在当前阶段输出文本\n"
        "- 用户说「等等」「不对」「修改」「再看看」→ 不调 route_to，留在当前阶段继续对话\n"
        "- 每个阶段只能向前，不能回退（除非用户明确要求回到某阶段）\n"
        "- 这是控制 pipeline 流向的唯一方式——代码不做任何关键词判断"
    ),
    parameters={
        "type": "object",
        "properties": {
            "stage": {"type": "string", "enum": ["scout", "cleaner", "analyst", "reporter"]},
            "reason": {"type": "string", "description": "切换原因——告诉用户和后续 AI 为什么走这条路"},
        },
        "required": ["reason"],
    },
    handler=_handle_route_to,
    phase_tag=['理解字段', '评估清洗', '跑统计', '写报告'],
))

import hagoku.tools.memory_tools  # noqa: F401,E402 — Phase E ✅: memory 工具已注册
import hagoku.tools.stat_tools    # noqa: F401  — CO-T05～T11: 统计/诊断/功效
# biz_tools 已移除 — ROI/ROAS/LTV 等公式不是工具，LLM 训练数据自带
import hagoku.tools.cleaning_tools  # noqa: F401  — CO-T19～T21: 清洗增强
import hagoku.tools.viz_tools     # noqa: F401  — CO-T22: 可视化
