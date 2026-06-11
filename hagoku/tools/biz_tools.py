"""业务指标工具 — CO-T12～T18

注册：
  CO-T12 calc_roi                → business.calc_roi
  CO-T13 calc_roas               → business.calc_roas
  CO-T14 calc_ltv                → business.calc_ltv
  CO-T15 calc_cac                → business.calc_cac
  CO-T16 calc_ltv_cac_ratio      → business.calc_ltv_cac_ratio
  CO-T17 funnel_analysis         → business.funnel_analysis
  CO-T18 attribution_analysis    → business.attribution_analysis
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from hagoku.tools.registry import Tool, agent_tools


# ═══════════════════════════════════════════════════════════════════
# CO-T12: calc_roi
# ═══════════════════════════════════════════════════════════════════

def _handle_calc_roi(args: dict, _ctx: dict, df: pd.DataFrame | None) -> dict:
    from hagoku.tools.business import calc_roi as _calc_roi

    revenue_col = args.get("revenue_col")
    cost_col = args.get("cost_col")
    revenue_val = args.get("revenue")
    cost_val = args.get("cost")

    # 优先列名模式
    if revenue_col and cost_col and isinstance(revenue_col, str) and isinstance(cost_col, str):
        if df is None:
            return {"error": "传入列名时需要 DataFrame"}
        if revenue_col not in df.columns:
            return {"error": f"列 {revenue_col} 不存在"}
        if cost_col not in df.columns:
            return {"error": f"列 {cost_col} 不存在"}
        try:
            return _calc_roi(df[revenue_col], df[cost_col])
        except Exception as e:
            return {"error": str(e)}

    # 数值模式
    if revenue_val is not None and cost_val is not None:
        try:
            return _calc_roi(float(revenue_val), float(cost_val))
        except Exception as e:
            return {"error": str(e)}

    return {"error": "需传 revenue_col + cost_col（列名）或 revenue + cost（数值）"}


agent_tools.register(Tool(
    name="calc_roi",
    description=(
        "计算投资回报率 (ROI)。公式: (收益 - 成本) / 成本 × 100%。"
        "可传 revenue_col + cost_col（DataFrame 列名）或 revenue + cost（数值）。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "revenue_col": {"type": "string", "description": "收益列名"},
            "cost_col": {"type": "string", "description": "成本列名"},
            "revenue": {"type": "number", "description": "收益数值（单次计算）"},
            "cost": {"type": "number", "description": "成本数值（单次计算）"},
        },
    },
    handler=_handle_calc_roi,
    phase_tag=["跑统计"],
))


# ═══════════════════════════════════════════════════════════════════
# CO-T13: calc_roas
# ═══════════════════════════════════════════════════════════════════

def _handle_calc_roas(args: dict, _ctx: dict, df: pd.DataFrame | None) -> dict:
    from hagoku.tools.business import calc_roas as _calc_roas

    revenue_col = args.get("revenue_col")
    ad_spend_col = args.get("ad_spend_col")
    revenue_val = args.get("revenue")
    ad_spend_val = args.get("ad_spend")

    # 优先列名模式
    if revenue_col and ad_spend_col and isinstance(revenue_col, str) and isinstance(ad_spend_col, str):
        if df is None:
            return {"error": "传入列名时需要 DataFrame"}
        if revenue_col not in df.columns:
            return {"error": f"列 {revenue_col} 不存在"}
        if ad_spend_col not in df.columns:
            return {"error": f"列 {ad_spend_col} 不存在"}
        try:
            return _calc_roas(df[revenue_col], df[ad_spend_col])
        except Exception as e:
            return {"error": str(e)}

    # 数值模式
    if revenue_val is not None and ad_spend_val is not None:
        try:
            return _calc_roas(float(revenue_val), float(ad_spend_val))
        except Exception as e:
            return {"error": str(e)}

    return {"error": "需传 revenue_col + ad_spend_col（列名）或 revenue + ad_spend（数值）"}


agent_tools.register(Tool(
    name="calc_roas",
    description=(
        "计算广告支出回报率 (ROAS)。公式: 广告收益 / 广告支出。"
        "可传 revenue_col + ad_spend_col（列名）或 revenue + ad_spend（数值）。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "revenue_col": {"type": "string", "description": "广告收益列名"},
            "ad_spend_col": {"type": "string", "description": "广告支出列名"},
            "revenue": {"type": "number", "description": "收益数值"},
            "ad_spend": {"type": "number", "description": "广告支出数值"},
        },
    },
    handler=_handle_calc_roas,
    phase_tag=["跑统计"],
))


# ═══════════════════════════════════════════════════════════════════
# CO-T14: calc_ltv
# ═══════════════════════════════════════════════════════════════════

def _handle_calc_ltv(args: dict, _ctx: dict, df: pd.DataFrame | None) -> dict:
    from hagoku.tools.business import calc_ltv as _calc_ltv

    customer_col = str(args.get("customer_col", ""))
    revenue_col = str(args.get("revenue_col", ""))
    periods = args.get("periods")
    discount_rate = float(args.get("discount_rate", 0.0))

    if not customer_col or not revenue_col:
        return {"error": "customer_col 和 revenue_col 必填"}

    if df is None:
        return {"error": "需要 DataFrame"}

    if customer_col not in df.columns:
        return {"error": f"列 {customer_col} 不存在"}
    if revenue_col not in df.columns:
        return {"error": f"列 {revenue_col} 不存在"}

    try:
        return _calc_ltv(
            df, customer_col=customer_col, revenue_col=revenue_col,
            periods=int(periods) if periods is not None else None,
            discount_rate=discount_rate,
        )
    except Exception as e:
        return {"error": str(e)}


agent_tools.register(Tool(
    name="calc_ltv",
    description=(
        "计算用户生命周期价值 (LTV / CLV)。公式: Σ(每期收益)。"
        "需传 customer_col（客户ID列）+ revenue_col（收益列）。"
        "可选 periods（计算期数）和 discount_rate（折现率）。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "customer_col": {"type": "string", "description": "客户ID列名"},
            "revenue_col": {"type": "string", "description": "收益列名"},
            "periods": {"type": "integer", "description": "计算期数（默认从数据推断）"},
            "discount_rate": {"type": "number", "description": "年化折现率，默认 0"},
        },
        "required": ["customer_col", "revenue_col"],
    },
    handler=_handle_calc_ltv,
    phase_tag=["跑统计"],
))


# ═══════════════════════════════════════════════════════════════════
# CO-T15: calc_cac
# ═══════════════════════════════════════════════════════════════════

def _handle_calc_cac(args: dict, _ctx: dict, df: pd.DataFrame | None) -> dict:
    from hagoku.tools.business import calc_cac as _calc_cac

    customer_col = str(args.get("customer_col", ""))
    cost_col = str(args.get("cost_col", ""))
    acquisition_date_col = args.get("acquisition_date_col")

    if not customer_col or not cost_col:
        return {"error": "customer_col 和 cost_col 必填"}

    if df is None:
        return {"error": "需要 DataFrame"}

    if customer_col not in df.columns:
        return {"error": f"列 {customer_col} 不存在"}
    if cost_col not in df.columns:
        return {"error": f"列 {cost_col} 不存在"}

    try:
        return _calc_cac(
            df, customer_col=customer_col, cost_col=cost_col,
            acquisition_date_col=str(acquisition_date_col) if acquisition_date_col else None,
        )
    except Exception as e:
        return {"error": str(e)}


agent_tools.register(Tool(
    name="calc_cac",
    description=(
        "计算客户获取成本 (CAC)。公式: 总获取成本 / 新客户数。"
        "需传 customer_col（客户ID列）+ cost_col（获取成本列）。"
        "可选 acquisition_date_col（获取日期列）用于分期 CAC 趋势分析。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "customer_col": {"type": "string", "description": "客户ID列名"},
            "cost_col": {"type": "string", "description": "获取成本列名"},
            "acquisition_date_col": {"type": "string", "description": "获取日期列名（可选）"},
        },
        "required": ["customer_col", "cost_col"],
    },
    handler=_handle_calc_cac,
    phase_tag=["跑统计"],
))


# ═══════════════════════════════════════════════════════════════════
# CO-T16: calc_ltv_cac_ratio
# ═══════════════════════════════════════════════════════════════════

def _handle_calc_ltv_cac_ratio(args: dict, _ctx: dict, _df: pd.DataFrame | None) -> dict:
    from hagoku.tools.business import calc_ltv_cac_ratio as _calc

    ltv = float(args.get("ltv", 0))
    cac = float(args.get("cac", 0))

    if ltv <= 0 or cac <= 0:
        return {"error": "LTV 和 CAC 必须为正数"}

    try:
        return _calc(ltv, cac)
    except Exception as e:
        return {"error": str(e)}


agent_tools.register(Tool(
    name="calc_ltv_cac_ratio",
    description=(
        "计算 LTV/CAC 比率。公式: 用户生命周期价值 / 客户获取成本。"
        "需传 ltv + cac（来自 calc_ltv 和 calc_cac 的结果）。"
        "行业经验：LTV/CAC > 3x 为健康标准。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "ltv": {"type": "number", "description": "用户生命周期价值"},
            "cac": {"type": "number", "description": "客户获取成本"},
        },
        "required": ["ltv", "cac"],
    },
    handler=_handle_calc_ltv_cac_ratio,
    phase_tag=["跑统计"],
))


# ═══════════════════════════════════════════════════════════════════
# CO-T17: funnel_analysis
# ═══════════════════════════════════════════════════════════════════

def _handle_funnel_analysis(args: dict, _ctx: dict, df: pd.DataFrame | None) -> dict:
    from hagoku.tools.business import funnel_analysis as _funnel

    stage_col = str(args.get("stage_col", ""))
    stage_order = list(args.get("stage_order", []) or []) or None
    count_col = args.get("count_col")
    value_col = args.get("value_col")

    if not stage_col:
        return {"error": "stage_col 必填"}
    if df is None:
        return {"error": "需要 DataFrame"}
    if stage_col not in df.columns:
        return {"error": f"列 {stage_col} 不存在"}

    try:
        return _funnel(
            df, stage_col=stage_col, stage_order=stage_order,
            count_col=str(count_col) if count_col else None,
            value_col=str(value_col) if value_col else None,
        )
    except Exception as e:
        return {"error": str(e)}


agent_tools.register(Tool(
    name="funnel_analysis",
    description=(
        "漏斗分析：计算各阶段转化率、步骤流失和总体转化率。"
        "需传 stage_col（漏斗阶段列名）。可选 stage_order（阶段顺序列表）、"
        "count_col（每阶段计数列）、value_col（每阶段金额列）。"
        "返回每个阶段的 count、step_conversion_rate、cumulative_conversion_rate 和 biggest_drop。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "stage_col": {"type": "string", "description": "漏斗阶段列名"},
            "stage_order": {"type": "array", "items": {"type": "string"}, "description": "阶段顺序（按漏斗从上到下），默认按频数降序"},
            "count_col": {"type": "string", "description": "每阶段计数列（默认统计行数）"},
            "value_col": {"type": "string", "description": "每阶段金额列（可选）"},
        },
        "required": ["stage_col"],
    },
    handler=_handle_funnel_analysis,
    phase_tag=["跑统计"],
))


# ═══════════════════════════════════════════════════════════════════
# CO-T18: attribution_analysis
# ═══════════════════════════════════════════════════════════════════

def _handle_attribution_analysis(args: dict, _ctx: dict, df: pd.DataFrame | None) -> dict:
    from hagoku.tools.business import attribution_analysis as _attr

    conversions_col = str(args.get("conversions_col", ""))
    channel_col = str(args.get("channel_col", ""))
    revenue_col = args.get("revenue_col")
    customer_col = args.get("customer_col")
    method = str(args.get("method", "last_touch"))

    if not conversions_col or not channel_col:
        return {"error": "conversions_col 和 channel_col 必填"}
    if df is None:
        return {"error": "需要 DataFrame"}
    if conversions_col not in df.columns:
        return {"error": f"列 {conversions_col} 不存在"}
    if channel_col not in df.columns:
        return {"error": f"列 {channel_col} 不存在"}

    try:
        return _attr(
            df,
            conversions_col=conversions_col,
            channel_col=channel_col,
            revenue_col=str(revenue_col) if revenue_col else None,
            customer_col=str(customer_col) if customer_col else None,
            method=method,
        )
    except Exception as e:
        return {"error": str(e)}


agent_tools.register(Tool(
    name="attribution_analysis",
    description=(
        "渠道归因分析：将转化归功于各渠道。method 可选: last_touch（最后触达）/ first_touch（首次触达）/ linear（线性分配）。"
        "需传 conversions_col（转化列）+ channel_col（渠道列）。"
        "可选 revenue_col（收益列，用于收益归因）、customer_col（客户ID列，用于旅程归因）。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "conversions_col": {"type": "string", "description": "转化列名"},
            "channel_col": {"type": "string", "description": "渠道列名"},
            "revenue_col": {"type": "string", "description": "收益列名（可选）"},
            "customer_col": {"type": "string", "description": "客户ID列名（可选，用于旅程归因）"},
            "method": {
                "type": "string",
                "enum": ["last_touch", "first_touch", "linear"],
                "description": "归因方法: last_touch / first_touch / linear",
            },
        },
        "required": ["conversions_col", "channel_col"],
    },
    handler=_handle_attribution_analysis,
    phase_tag=["跑统计"],
))
