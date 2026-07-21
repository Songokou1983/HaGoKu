"""HaGoKu 工具定义 — 在注册表中注册所有 Agent 可用的工具。

导入此模块即完成注册。新增工具只需在此文件添加。
"""

from __future__ import annotations

import json as _json
from typing import Any

from hagoku.tools.registry import Tool, agent_tools


# ═══════════════════════════════════════════════════════════════════
# 通用数据探查工具（所有 Agent 可用）
# ═══════════════════════════════════════════════════════════════════

def _handle_get_column_stats(args: dict, _ctx: dict, df: pd.DataFrame | None) -> dict:
    import pandas as pd
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




# ═══════════════════════════════════════════════════════════════════
# Scout 字段理解工具
# ═══════════════════════════════════════════════════════════════════

def _handle_set_columns(args: dict, ctx: dict, _df: pd.DataFrame | None) -> dict:
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
        entry = {
            "column_name": col,
            "display_name": dn or col,
            "chinese_name": dn or col,
            "description": desc,
        }
        if role:
            entry["suggested_role"] = role
        if used is not None:
            entry["used_in_analysis"] = bool(used)
        if evidence:
            entry["evidence"] = evidence
        semantics.append(entry)

    return {
        "updated": col,
        "display_name": dn,
        "description": desc,
        "synced_to_table": updated,
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
    name="set_columns",
    description='写入你对字段的理解。批量推荐 columns 数组一次性写入全部列。',
    parameters={
        "type": "object",
        "properties": {
            "column_name": {"type": "string", "description": "列名或已确认的业务名（单列模式）"},
            "display_name": {"type": "string", "description": "简短中文名称"},
            "description": {"type": "string", "description": "业务含义说明"},
            "suggested_role": {"type": "string", "enum": ["target", "feature", "identifier", "ignore"]},
            "used_in_analysis": {"type": "boolean", "description": "是否参与后续统计分析"},
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
                        "used_in_analysis": {"type": "boolean", "description": "是否参与后续统计分析"},
                        "evidence": {"type": "string"},
                    },
                    "required": ["column_name"],
                },
                "description": "批量更新多列（推荐）",
            },
        },
        "required": [],
    },
    handler=_handle_set_columns,
    phase_tag=['理解字段'],
))





agent_tools.register(Tool(
    name="submit_assessment",
    description="提交清洗评估结果。",
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



# ═══════════════════════════════════════════════════════════════════
# Analyst 对话式分析工具
# ═══════════════════════════════════════════════════════════════════




def _handle_ask_user(args: dict, ctx: dict, _df: pd.DataFrame | None) -> dict:
    """处理 LLM 的 ask_user 调用——触发暂停信号写入 context。"""
    pending = {
        "question": args.get("question", ""),
        "options": args.get("options", []),
        "expected_format": args.get("expected_format", "free_text"),
    }
    ctx["_pending_ask_user"] = pending
    return pending

agent_tools.register(Tool(
    name="ask_user",
    description="向用户提问并暂停等待回复。",
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


def _handle_submit_findings(args: dict, ctx: dict, _df: pd.DataFrame | None) -> dict:
    return {
        "findings": args.get("findings", []),
        "method_used": args.get("method_used", []),
        "summary": args.get("summary", ""),
    }

agent_tools.register(Tool(
    name="submit_findings",
    description="提交分析发现。可以是首波探索性发现或最终结论。",
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
    handler=_handle_submit_findings,
    phase_tag=['跑统计'],
))


# ═══════════════════════════════════════════════════════════════════
# 报告生成工具
# ═══════════════════════════════════════════════════════════════════

def _handle_generate_report(args: dict, ctx: dict, _df: pd.DataFrame | None) -> dict:
    from hagoku.tools.reporting import ReportData, ReportGenerator, ReportSection
    from pathlib import Path
    import os

    sections_data = args.get("sections") or []
    sections = []
    for s in sections_data:
        content = s.get("content", "")
        # 将 LLM 输出的 markdown 转为 HTML
        if content:
            try:
                import markdown as _md
                content = _md.markdown(content, extensions=["tables", "fenced_code", "nl2br"])
            except Exception:
                pass
        sections.append(ReportSection(
            title=s.get("title", ""),
            content=content,
            findings=s.get("findings") or [],
            charts=s.get("charts") or [],
            headline=s.get("headline"),
        ))

    # ── 标准化图表格式：LLM 可能只传 html_snippet 缺 type，统一补全 ──
    for s in sections:
        normalized = []
        for c in (s.charts or []):
            if isinstance(c, dict):
                if c.get("html_snippet") and not c.get("type"):
                    c["type"] = "inline_html"
                normalized.append(c)
        s.charts = normalized

    # ── 图表注入：按 chart_id 显式绑定，未绑定的不注入 ──
    generated = ctx.get("_generated_charts") or []
    has_explicit = any(s.charts and any(isinstance(c, str) for c in s.charts) for s in sections)
    if has_explicit and generated:
        chart_by_id = {c["chart_id"]: c for c in generated if "chart_id" in c}
        for s in sections:
            if s.charts:
                resolved = []
                for ref in s.charts:
                    if isinstance(ref, str) and ref in chart_by_id:
                        resolved.append(chart_by_id[ref])
                    elif isinstance(ref, dict):
                        resolved.append(ref)
                s.charts = resolved
        ctx["_generated_charts"] = []  # 已消费，防重复
    elif generated and not has_explicit:
        # 无显式绑定 → 全部自动分配到没有 charts 的 section
        empty_sections = [s for s in sections if not s.charts]
        if empty_sections:
            for i, chart in enumerate(generated):
                empty_sections[i % len(empty_sections)].charts.append(chart)

    # ── page_width: wide=无限制, normal=960px（默认）──
    page_width = args.get("page_width", "normal") or "normal"
    custom_css = args.get("custom_css") or ""

    report = ReportData(
        project_name=ctx.get("_project_name", ""),
        query=ctx.get("query", ""),
        sections=sections,
        headline=args.get("headline", ""),
        findings_summary=args.get("findings", []),
        data_summary={
            "n_rows": ctx.get("n_rows", 0),
            "n_cols": ctx.get("n_cols", 0),
        },
    )

    run_dir = ctx.get("_run_dir") or ""
    if run_dir:
        from datetime import datetime
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = str(Path(run_dir) / "output" / f"report_{ts}.html")
    else:
        output_path = ""
    gen = ReportGenerator()
    gen.generate_html(report, output_path=output_path, template_name=args.get("template", "default"))

    # ── 注入 page_width 和 custom_css ──
    if (page_width == "wide" or custom_css) and output_path:
        html = output_path and __import__("pathlib").Path(output_path).read_text(encoding="utf-8")
        if html:
            extra = ""
            if page_width == "wide":
                extra += "<style>body{max-width:none!important;padding:1rem 2rem!important}</style>"
            if custom_css:
                extra += f"<style>{custom_css}</style>"
            html = html.replace("</head>", f"{extra}\n</head>")
            __import__("pathlib").Path(output_path).write_text(html, encoding="utf-8")

    # 同步生成打印版
    if output_path:
        print_path = output_path.replace(".html", "_print.html")
        gen.generate_html(report, output_path=print_path, template_name="print")

    # ── 更新项目报告链接 ──
    if run_dir and output_path:
        try:
            proj_dir = Path(run_dir).parent.parent  # runs/{id} → {project}
            reports_dir = proj_dir / "reports"
            reports_dir.mkdir(parents=True, exist_ok=True)
            latest_link = reports_dir / "latest.html"
            if latest_link.exists() or latest_link.is_symlink():
                latest_link.unlink()
            latest_link.symlink_to(os.path.relpath(output_path, reports_dir))
        except Exception:
            import logging
            logging.getLogger("hagoku.tools").debug("符号链接创建失败（非关键）", exc_info=True)

    return {"html_path": output_path, "sections_count": len(sections)}


agent_tools.register(Tool(
    name="generate_report",
    description="生成 HTML 分析报告。图表可用 create_plot 的 chart_id 显式绑定（section.charts: [\"chart_1\", \"chart_2\"]）。page_width: wide 时内容撑满页面。",
    parameters={
        "type": "object",
        "properties": {
            "sections": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "content": {"type": "string"},
                        "headline": {"type": "string"},
                        "findings": {"type": "array", "items": {"type": "object"}},
                        "charts": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "create_plot 返回的 chart_id 列表，不传则自动分配",
                        },
                    },
                    "required": ["title", "content"],
                },
            },
            "headline": {"type": "string"},
            "findings": {"type": "array", "items": {"type": "object"}},
            "template": {"type": "string"},
            "page_width": {"type": "string", "enum": ["normal", "wide"], "description": "normal=960px 版心, wide=撑满页面"},
            "custom_css": {"type": "string", "description": "自定义 CSS 样式（高级用户微调）"},
        },
        "required": ["sections"],
    },
    handler=_handle_generate_report,
    phase_tag=['写报告'],
))


# ═══════════════════════════════════════════════════════════════════
# Cleaner 对话式清洗工具
# ═══════════════════════════════════════════════════════════════════






import hagoku.tools.memory_tools  # noqa: F401  — 项目记忆 + Agent 成长经验
import hagoku.tools.stat_tools    # noqa: F401  — CO-T05～T11: 统计/诊断/功效
# biz_tools 已移除 — ROI/ROAS/LTV 等公式不是工具，LLM 训练数据自带
import hagoku.tools.cleaning_tools  # noqa: F401  — CO-T19～T21: 清洗增强
import hagoku.tools.viz_tools     # noqa: F401  — CO-T22: 可视化

# Doctor 创建的临时工具桩（文件不存在时跳过）
try:
    import hagoku.tools._doctor_tools  # noqa: F401
except ImportError:
    pass
