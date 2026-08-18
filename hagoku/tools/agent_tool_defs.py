"""统一注册 agent 工具定义。"""

from __future__ import annotations

import json as _json
from typing import Any

import pandas as pd

from .registry import agent_tools
from .registry import Tool


# ═══════════════════════════════════════════════════════════════════
# 辅助函数
# ═══════════════════════════════════════════════════════════════════

def _df_safe(df: pd.DataFrame | None) -> pd.DataFrame:
    import pandas as _pd
    return df if df is not None else _pd.DataFrame()


def _safe_float(v: Any) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _safe_int(v: Any) -> int | None:
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


# ═══════════════════════════════════════════════════════════════════
# 查询工具（所有 Agent 可用）
# ═══════════════════════════════════════════════════════════════════

def _handle_get_column_names(args: dict, ctx: dict, _df: pd.DataFrame | None) -> dict:
    df = _df_safe(_df)
    return {"columns": list(df.columns), "count": len(df.columns)}


agent_tools.register(Tool(
    name="get_column_names",
    description="获取数据集全部列名及数量。",
    parameters={"type": "object", "properties": {}, "required": []},
    handler=_handle_get_column_names,
    phase_tag=['理解字段', '评估清洗', '跑统计'],
))


def _handle_get_column_stats(args: dict, ctx: dict, _df: pd.DataFrame | None) -> dict:
    df = _df_safe(_df)
    col = str(args.get("column", ""))
    if col not in df.columns:
        return {"error": f"列 {col} 不存在", "available": list(df.columns)}
    s = df[col]
    result: dict[str, Any] = {"column": col, "dtype": str(s.dtype), "count": int(s.count())}
    try:
        if pd.api.types.is_numeric_dtype(s):
            result.update({
                "min": _safe_float(s.min()), "q25": _safe_float(s.quantile(0.25)),
                "median": _safe_float(s.median()), "q75": _safe_float(s.quantile(0.75)),
                "max": _safe_float(s.max()), "mean": _safe_float(s.mean()),
                "std": _safe_float(s.std()),
            })
        else:
            val_counts = s.value_counts().head(5).to_dict()
            result["top_values"] = {str(k): int(v) for k, v in val_counts.items()}
    except Exception:
        pass
    result["null_count"] = int(s.isna().sum())
    result["null_pct"] = round(s.isna().mean() * 100, 2)
    return result


agent_tools.register(Tool(
    name="get_column_stats",
    description="对单列做完整统计。",
    parameters={
        "type": "object",
        "properties": {"column": {"type": "string", "description": "列名"}},
        "required": ["column"],
    },
    handler=_handle_get_column_stats,
    phase_tag=['评估清洗', '跑统计'],
))


def _handle_get_group_stats(args: dict, ctx: dict, _df: pd.DataFrame | None) -> dict:
    df = _df_safe(_df)
    col = str(args.get("column", ""))
    by = str(args.get("by", ""))
    if col not in df.columns:
        return {"error": f"列 {col} 不存在"}
    if by not in df.columns:
        return {"error": f"分组列 {by} 不存在"}
    try:
        grouped = df.groupby(by)[col].agg(["count", "mean", "std", "min", "max"]).reset_index()
        return {"column": col, "by": by, "groups": grouped.to_dict(orient="records")}
    except Exception as e:
        return {"error": str(e)}


agent_tools.register(Tool(
    name="get_group_stats",
    description="对列按分组做聚合统计。",
    parameters={
        "type": "object",
        "properties": {
            "column": {"type": "string", "description": "要统计的列"},
            "by": {"type": "string", "description": "分组依据列"},
        },
        "required": ["column", "by"],
    },
    handler=_handle_get_group_stats,
    phase_tag=['评估清洗', '跑统计'],
))


# ═══════════════════════════════════════════════════════════════════
# Scout 字段理解工具
# ═══════════════════════════════════════════════════════════════════

def _handle_set_columns(args: dict, ctx: dict, _df: pd.DataFrame | None) -> dict:
    """更新字段的中文名和含义，同步写入 column_semantics。支持单列或批量。"""
    batch = args.get("columns")
    if batch and isinstance(batch, list):
        results = []
        for item in batch:
            if isinstance(item, dict):
                results.append(_update_one_field(item, ctx))
        return {"updated_batch": results}

    r = _update_one_field(args, ctx)
    return r


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
            "columns": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "column_name": {"type": "string"},
                        "display_name": {"type": "string"},
                        "description": {"type": "string"},
                        "suggested_role": {"type": "string", "enum": ["target", "feature", "identifier", "ignore"]},
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

    for s in sections:
        normalized = []
        for c in (s.charts or []):
            if isinstance(c, dict):
                if c.get("html_snippet") and not c.get("type"):
                    c["type"] = "inline_html"
                normalized.append(c)
            elif isinstance(c, str):
                normalized.append(c)
        s.charts = normalized

    generated = ctx.get("_generated_charts") or []
    chart_by_id = {c.get("chart_id", c.get("title", "")): c for c in generated}
    for s in sections:
        if s.charts and any(isinstance(c, str) for c in s.charts):
            s.charts = [chart_by_id[c] for c in s.charts if isinstance(c, str) and c in chart_by_id]
        else:
            s.charts = []

    ctx["_generated_charts"] = []

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

    if output_path:
        print_path = output_path.replace(".html", "_print.html")
        gen.generate_html(report, output_path=print_path, template_name="print")

    if run_dir and output_path:
        try:
            proj_dir = Path(run_dir).parent.parent
            reports_dir = proj_dir / "reports"
            reports_dir.mkdir(parents=True, exist_ok=True)
            latest_link = reports_dir / "latest.html"
            if latest_link.exists() or latest_link.is_symlink():
                latest_link.unlink()
            latest_link.symlink_to(os.path.relpath(output_path, reports_dir))
        except Exception:
            import logging
            logging.getLogger("hagoku.tools").debug("符号链接创建失败（非关键）", exc_info=True)

    chart_bindings = []
    for s in sections:
        for c in (s.charts or []):
            cid = c.get("chart_id") or c.get("title", "?")
            chart_bindings.append({"section": s.title, "chart": cid})

    ctx["_report_html_path"] = output_path
    return {
        "html_path": output_path,
        "sections_count": len(sections),
        "charts_injected": len(chart_bindings),
        "chart_bindings": chart_bindings,
        "page_width": page_width,
        "custom_css_applied": bool(custom_css),
    }


agent_tools.register(Tool(
    name="generate_report",
    description="生成 HTML 分析报告。",
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
                            "description": "create_plot 返回的 chart_id 列表",
                        },
                    },
                    "required": ["title", "content"],
                },
            },
            "headline": {"type": "string"},
            "findings": {"type": "array", "items": {"type": "object"}},
            "template": {"type": "string"},
            "page_width": {"type": "string", "enum": ["normal", "wide"]},
            "custom_css": {"type": "string"},
        },
        "required": ["sections"],
    },
    handler=_handle_generate_report,
    phase_tag=['写报告'],
))


import hagoku.tools.memory_tools  # noqa: F401
import hagoku.tools.stat_tools    # noqa: F401
import hagoku.tools.cleaning_tools  # noqa: F401
import hagoku.tools.viz_tools     # noqa: F401

try:
    import hagoku.tools._doctor_tools  # noqa: F401
except ImportError:
    pass


# ═══════════════════════════════════════════════════════════════════
# Quant 3.0 — 数据接入 + 回测
# ═══════════════════════════════════════════════════════════════════

from .market_data import fetch_market_data as _fetch_market_data_impl
from .backtest import run_backtest as _run_backtest_impl


def _handle_fetch_market_data(args: dict, ctx: dict, _df):
    return _fetch_market_data_impl(
        market=args.get("market", ""),
        symbol=args.get("symbol", ""),
        period=args.get("period", ""),
        interval=args.get("interval", "d1"),
        ctx=ctx,
    )


def _handle_run_backtest(args: dict, ctx: dict, _df):
    return _run_backtest_impl(
        strategy_spec=args.get("strategy_spec", {}),
        _df=_df_safe(_df),
        ctx=ctx,
    )


agent_tools.register(Tool(
    name="fetch_market_data",
    description=(
        "从 akshare（A 股）或 ccxt（加密货币）拉取历史 OHLCV 行情数据。"
        "输入市场类型、代码、起止区间、周期；返回标准化 DataFrame 并写入「量化数据集」库。"
        "何时用：用户要分析 A 股或加密货币，但没有现成 CSV。"
        "注意：网络失败会抛错；akshare 接口升级可能破坏历史调用。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "market": {"type": "string", "enum": ["a_stock", "crypto"]},
            "symbol": {"type": "string"},
            "period": {"type": "string"},
            "interval": {"type": "string", "enum": ["d1", "h1"]},
        },
        "required": ["market", "symbol", "period", "interval"],
    },
    handler=_handle_fetch_market_data,
    phase_tag=['理解字段', '跑统计'],
))


agent_tools.register(Tool(
    name="run_backtest",
    description=(
        "按 strategy_spec 在当前项目数据上模拟交易，输出权益曲线 / 交易明细 / 机械统计。"
        "输入策略名 + 入场/出场 pandas 表达式 + 可选止损止盈。"
        "返回纯机械量，Sharpe / MaxDD 等金融指标由你（LLM）从机械量推导。"
        "何时用：用户定义了交易策略，想看历史回测效果。"
        "注意：表达式必须是合法 pandas 表达式，引用当前数据列名。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "strategy_spec": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "entry": {"type": "string"},
                    "exit": {"type": "string"},
                    "stop_loss": {"type": "number"},
                    "take_profit": {"type": "number"},
                },
                "required": ["name", "entry", "exit"],
            },
        },
        "required": ["strategy_spec"],
    },
    handler=_handle_run_backtest,
    phase_tag=['跑统计', '撰写报告'],
))