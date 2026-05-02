"""HaGoKu 商业分析 — 财务指标和业务洞察

商业分析回答：ROI多少、用户值多少钱、何时回本、增长多少

核心原则：
- 所有指标都有明确计算公式，不模糊
- 尽量用相对指标（比率/百分比）而非绝对值，方便跨期对比
- 输出包含业务含义解读，不只是数字
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


def _insufficient_data(msg: str) -> dict[str, Any]:
    """返回数据不足的标准错误结果"""
    return {"error": "insufficient_data", "message": msg}


def _warn(msg: str) -> dict[str, Any]:
    """返回警告信息"""
    return {"warning": msg}


# ── 效果指标 ───────────────────────────────────────────────


def calc_roi(
    revenue: float | pd.Series,
    cost: float | pd.Series,
) -> dict[str, Any]:
    """
    计算投资回报率 (ROI)

    ROI = (收益 - 成本) / 成本 × 100%

    Args:
        revenue: 收益（总额或 Series）
        cost: 成本（总额或 Series）

    Returns:
        ROI 分析结果
    """
    try:
        if isinstance(revenue, pd.Series) and isinstance(cost, pd.Series):
            # Series 情况
            net = revenue - cost
            roi_series = ((net / cost) * 100).replace([np.inf, -np.inf], np.nan)
            avg_roi = float(roi_series.dropna().mean())
            return {
                "metric": "ROI",
                "formula": "(收益 - 成本) / 成本 × 100%",
                "avg_roi": avg_roi,
                "net_profit": float(net.sum()),
                "total_revenue": float(revenue.sum()),
                "total_cost": float(cost.sum()),
                "roi_series": roi_series.dropna().to_dict(),
                "interpretation": _interpret_roi(avg_roi),
            }
        else:
            r = float(revenue)
            c = float(cost)
            if c == 0:
                return _insufficient_data("成本为 0，无法计算 ROI")
            roi = (r - c) / c * 100
            return {
                "metric": "ROI",
                "formula": "(收益 - 成本) / 成本 × 100%",
                "roi": roi,
                "net_profit": r - c,
                "revenue": r,
                "cost": c,
                "interpretation": _interpret_roi(roi),
            }
    except Exception as e:
        return _insufficient_data(f"ROI 计算失败: {e}")


def calc_roas(
    revenue: float | pd.Series,
    ad_spend: float | pd.Series,
) -> dict[str, Any]:
    """
    计算广告支出回报率 (ROAS)

    ROAS = 广告带来的收益 / 广告支出

    Args:
        revenue: 广告带来的收益
        ad_spend: 广告支出

    Returns:
        ROAS 分析结果
    """
    try:
        if isinstance(revenue, pd.Series) and isinstance(ad_spend, pd.Series):
            # 对齐索引后计算
            aligned = pd.DataFrame({"revenue": revenue, "ad_spend": ad_spend}).dropna()
            if len(aligned) == 0:
                return _insufficient_data("没有足够的有效数据计算 ROAS")
            roas_series = (aligned["revenue"] / aligned["ad_spend"].replace(0, np.nan)).replace([np.inf, -np.inf], np.nan)
            avg_roas = float(roas_series.dropna().mean())
            return {
                "metric": "ROAS",
                "formula": "广告收益 / 广告支出",
                "avg_roas": avg_roas,
                "total_revenue": float(revenue.sum()),
                "total_ad_spend": float(ad_spend.sum()),
                "roas_series": roas_series.dropna().to_dict(),
                "interpretation": _interpret_roas(avg_roas),
            }
        else:
            r = float(revenue)
            a = float(ad_spend)
            if a == 0:
                return _insufficient_data("广告支出为 0，无法计算 ROAS")
            roas = r / a
            return {
                "metric": "ROAS",
                "formula": "广告收益 / 广告支出",
                "roas": roas,
                "revenue": r,
                "ad_spend": a,
                "interpretation": _interpret_roas(roas),
            }
    except Exception as e:
        return _insufficient_data(f"ROAS 计算失败: {e}")


def calc_ltv(
    df: pd.DataFrame,
    customer_col: str,
    revenue_col: str,
    periods: int | None = None,
    discount_rate: float = 0.0,
) -> dict[str, Any]:
    """
    计算用户生命周期价值 (LTV/CLV)

    LTV = Σ (每期收益 × 留存概率) / (1 + 折扣率)^期数

    Args:
        df: 数据
        customer_col: 客户 ID 列
        revenue_col: 收益列
        periods: 计算期数（默认从数据推断）
        discount_rate: 年化折扣率（用于 DCF 模型，默认 0 = 简单求和）

    Returns:
        LTV 分析结果
    """
    try:
        if customer_col not in df.columns or revenue_col not in df.columns:
            return _insufficient_data(f"列不存在: {customer_col} 或 {revenue_col}")

        total_revenue = df[revenue_col].sum()
        n_customers = df[customer_col].nunique()
        if n_customers == 0:
            return _insufficient_data("没有有效客户数据")

        # 每客户收益
        per_customer = df.groupby(customer_col)[revenue_col].sum()
        avg_ltv = float(per_customer.mean())
        median_ltv = float(per_customer.median())

        # 留存分析
        if periods is None:
            periods = df[customer_col].value_counts().max()

        # 每期收益（跨客户汇总）
        period_revenue = df.groupby(df.index)[revenue_col].sum()
        n_alive = per_customer.count()  # 活跃客户数

        # 简单 LTV（无留存率）
        simple_ltv = avg_ltv

        # 折扣 LTV（折现）
        if discount_rate > 0:
            discount_factor = 1 / (1 + discount_rate) ** np.arange(periods)
            discounted_ltv = avg_ltv * np.sum(discount_factor[:len(period_revenue)])
        else:
            discounted_ltv = simple_ltv

        # 分位数
        p25 = float(per_customer.quantile(0.25))
        p75 = float(per_customer.quantile(0.75))

        # 解读
        if avg_ltv > 0:
            top_pct = (per_customer > avg_ltv * 2).sum() / len(per_customer) * 100
            high_value_rate = float(top_pct)
        else:
            high_value_rate = 0.0

        return {
            "metric": "LTV",
            "formula": "用户生命周期内总收益",
            "avg_ltv": avg_ltv,
            "median_ltv": median_ltv,
            "discounted_ltv": discounted_ltv,
            "simple_ltv": simple_ltv,
            "total_revenue": float(total_revenue),
            "n_customers": int(n_customers),
            "periods": periods,
            "discount_rate": discount_rate,
            "p25": p25,
            "p75": p75,
            "high_value_rate": high_value_rate,
            "distribution": {
                "mean": avg_ltv,
                "median": median_ltv,
                "q25": p25,
                "q75": p75,
            },
            "interpretation": (
                f"平均用户 LTV={avg_ltv:.2f}，中位数={median_ltv:.2f}。"
                f"前 25% 高价值用户贡献了约 {high_value_rate:.1f}% 的用户。"
            ),
        }
    except Exception as e:
        return _insufficient_data(f"LTV 计算失败: {e}")


def calc_cac(
    df: pd.DataFrame,
    customer_col: str,
    cost_col: str,
    acquisition_date_col: str | None = None,
) -> dict[str, Any]:
    """
    计算客户获取成本 (CAC)

    CAC = 总获取成本 / 新客户数

    Args:
        df: 数据
        customer_col: 客户 ID 列
        cost_col: 获取成本列
        acquisition_date_col: 获取日期列（可选，用于分期 CAC）

    Returns:
        CAC 分析结果
    """
    try:
        if customer_col not in df.columns or cost_col not in df.columns:
            return _insufficient_data(f"列不存在")

        n_new_customers = df[customer_col].nunique()
        if n_new_customers == 0:
            return _insufficient_data("没有新客户数据")

        total_cost = df[cost_col].sum()
        cac = total_cost / n_new_customers

        if acquisition_date_col and acquisition_date_col in df.columns:
            # 分期 CAC
            df_sorted = df.copy()
            df_sorted[acquisition_date_col] = pd.to_datetime(df_sorted[acquisition_date_col], errors="coerce")
            df_sorted = df_sorted.dropna(subset=[acquisition_date_col])
            period_cac = df_sorted.groupby(pd.Grouper(key=acquisition_date_col, freq="ME")).apply(
                lambda g: float(g[cost_col].sum()) / g[customer_col].nunique() if g[customer_col].nunique() > 0 else np.nan
            ).dropna()
            trend = "上升" if period_cac.diff().mean() > 0 else "下降"
        else:
            period_cac = None
            trend = None

        return {
            "metric": "CAC",
            "formula": "总获取成本 / 新客户数",
            "cac": float(cac),
            "total_cost": float(total_cost),
            "n_new_customers": int(n_new_customers),
            "period_cac": period_cac.to_dict() if period_cac is not None else None,
            "trend": trend,
            "interpretation": (
                f"平均获取一个客户花费 {cac:.2f}。"
                f"（{total_cost:.2f} 成本，{n_new_customers} 个新客户）"
                + (f" CAC 呈{trend}趋势。" if trend else "")
            ),
        }
    except Exception as e:
        return _insufficient_data(f"CAC 计算失败: {e}")


def calc_ltv_cac_ratio(ltv: float, cac: float) -> dict[str, Any]:
    """
    计算 LTV/CAC 比率

    LTV/CAC > 3 是健康标准

    Args:
        ltv: 用户生命周期价值
        cac: 客户获取成本

    Returns:
        比率分析结果
    """
    if ltv <= 0 or cac <= 0:
        return _insufficient_data("LTV 和 CAC 必须为正数")
    ratio = ltv / cac
    if ratio < 1:
        health = "差：获取用户亏本"
    elif ratio < 3:
        health = "一般：需要优化获取效率"
    elif ratio < 5:
        health = "良好：业务可持续发展"
    else:
        health = "优秀：增长空间大"
    return {
        "metric": "LTV/CAC",
        "formula": "用户生命周期价值 / 客户获取成本",
        "ratio": ratio,
        "ltv": ltv,
        "cac": cac,
        "health": health,
        "interpretation": f"LTV/CAC = {ratio:.1f}x（{health}）。行业经验：LTV/CAC > 3x 为健康标准。",
    }


# ── 回本与投资指标 ─────────────────────────────────────────


def calc_payback_period(
    df: pd.DataFrame,
    customer_col: str,
    revenue_col: str,
    cost_col: str,
    period_col: str | None = None,
) -> dict[str, Any]:
    """
    计算回本周期（投资回收期）

    回本周期 = 累计收益 = 累计成本 的时间点

    Args:
        df: 数据
        customer_col: 客户 ID 列
        revenue_col: 收益列
        cost_col: 成本列
        period_col: 周期列（默认按自然顺序）

    Returns:
        回本周期分析结果
    """
    try:
        if not all(c in df.columns for c in [customer_col, revenue_col, cost_col]):
            return _insufficient_data("列不存在")

        # 按期汇总
        if period_col and period_col in df.columns:
            period_df = df.groupby(period_col).agg(
                revenue=(revenue_col, "sum"),
                cost=(cost_col, "sum"),
            ).reset_index()
            period_df = period_df.sort_values(period_col)
        else:
            df_indexed = df.copy()
            df_indexed["_period"] = range(len(df_indexed))
            period_df = df_indexed.groupby("_period").agg(
                revenue=(revenue_col, "sum"),
                cost=(cost_col, "sum"),
            ).reset_index()

        period_df["net"] = period_df["revenue"] - period_df["cost"]
        period_df["cumsum_net"] = period_df["net"].cumsum()

        # 找回本点
        payback_idx = None
        for i, val in enumerate(period_df["cumsum_net"]):
            if val >= 0:
                payback_idx = i
                break

        if payback_idx is None:
            return {
                "metric": "Payback Period",
                "payback_period": None,
                "total_revenue": float(period_df["revenue"].sum()),
                "total_cost": float(period_df["cost"].sum()),
                "net_profit": float(period_df["net"].sum()),
                "interpretation": "尚未回本：累计收益 < 累计成本",
            }

        # 插值估算精确回本期（如果恰好在期间内）
        if payback_idx > 0 and period_df["cumsum_net"].iloc[payback_idx - 1] < 0:
            prev_cumsum = period_df["cumsum_net"].iloc[payback_idx - 1]
            curr_cumsum = period_df["cumsum_net"].iloc[payback_idx]
            prev_net = period_df["net"].iloc[payback_idx]
            fraction = abs(prev_cumsum) / abs(prev_net) if prev_net != 0 else 0
            exact_period = payback_idx - 1 + fraction
        else:
            exact_period = float(payback_idx)

        return {
            "metric": "Payback Period",
            "formula": "累计收益 = 累计成本的时点",
            "payback_period": round(exact_period, 2),
            "payback_period_index": payback_idx,
            "total_revenue": float(period_df["revenue"].sum()),
            "total_cost": float(period_df["cost"].sum()),
            "net_profit": float(period_df["net"].sum()),
            "cumsum_series": period_df["cumsum_net"].to_dict(),
            "interpretation": f"约 {exact_period:.1f} 个周期后回本（第 {payback_idx + 1} 期前后）。",
        }
    except Exception as e:
        return _insufficient_data(f"回本周期计算失败: {e}")


def calc_npv(
    cash_flows: list[float] | pd.Series,
    discount_rate: float,
    periods: int | None = None,
) -> dict[str, Any]:
    """
    计算净现值 (NPV)

    NPV = Σ CFt / (1 + r)^t

    Args:
        cash_flows: 现金流序列（第一期为初始投资，负值）
        discount_rate: 折现率（年化）
        periods: 期数（默认从现金流序列长度推断）

    Returns:
        NPV 分析结果
    """
    try:
        if isinstance(cash_flows, pd.Series):
            cf_list = cash_flows.tolist()
        else:
            cf_list = list(cash_flows)

        if not cf_list:
            return _insufficient_data("现金流为空")

        if periods is None:
            periods = len(cf_list)

        npv = 0.0
        npv_details = []
        for t, cf in enumerate(cf_list):
            pv = cf / (1 + discount_rate) ** t
            npv += pv
            npv_details.append({"period": t, "cash_flow": cf, "pv": pv})

        return {
            "metric": "NPV",
            "formula": "Σ CFt / (1 + r)^t",
            "npv": npv,
            "discount_rate": discount_rate,
            "periods": periods,
            "cash_flows": cf_list,
            "npv_details": npv_details,
            "interpretation": (
                f"NPV = {npv:.2f}。"
                f"{'投资可行（NPV > 0）' if npv > 0 else '投资不可行（NPV < 0）'}。"
                f"以 {discount_rate:.1%} 折现率计算。"
            ),
        }
    except Exception as e:
        return _insufficient_data(f"NPV 计算失败: {e}")


def calc_irr(
    cash_flows: list[float] | pd.Series,
    max_iter: int = 1000,
    tol: float = 1e-6,
) -> dict[str, Any]:
    """
    计算内部收益率 (IRR)

    IRR = 使 NPV = 0 的折现率

    Args:
        cash_flows: 现金流序列
        max_iter: 最大迭代次数
        tol: 收敛容差

    Returns:
        IRR 分析结果
    """
    try:
        if isinstance(cash_flows, pd.Series):
            cf_list = cash_flows.tolist()
        else:
            cf_list = list(cash_flows)

        if not cf_list:
            return _insufficient_data("现金流为空")

        # 符号变化法寻找初始区间
        sign_changes = sum(
            1 for i in range(len(cf_list) - 1)
            if cf_list[i] * cf_list[i + 1] < 0
        )
        if sign_changes == 0:
            return _insufficient_data("现金流无符号变化，无法计算 IRR")

        # Newton-Raphson 迭代
        r = 0.1  # 初始猜测 10%
        for _ in range(max_iter):
            npv, d_npv = _npv_derivative(cf_list, r)
            if abs(d_npv) < 1e-12:
                break
            r_new = r - npv / d_npv
            if abs(r_new - r) < tol:
                r = r_new
                break
            r = r_new

        if r < -0.99:
            return _insufficient_data("IRR 计算收敛失败（可能是现金流结构异常）")

        return {
            "metric": "IRR",
            "formula": "使 NPV=0 的折现率",
            "irr": r,
            "irr_percent": f"{r * 100:.2f}%",
            "interpretation": (
                f"内部收益率为 {r*100:.2f}%。"
                f"{'投资回报高于预期（IRR > 基准收益率）' if r > 0.1 else '投资回报率较低'}"
            ),
        }
    except Exception as e:
        return _insufficient_data(f"IRR 计算失败: {e}")


def _npv_derivative(cf_list: list[float], r: float) -> tuple[float, float]:
    """计算 NPV 和 d(NPV)/dr"""
    npv = 0.0
    d_npv = 0.0
    for t, cf in enumerate(cf_list):
        factor = (1 + r) ** (-t)
        npv += cf * factor
        d_npv -= t * cf * factor / (1 + r)
    return npv, d_npv


def calc_break_even(
    fixed_cost: float,
    unit_price: float,
    unit_cost: float,
) -> dict[str, Any]:
    """
    计算盈亏平衡点

    盈亏平衡量 = 固定成本 / (单价 - 单位成本)
    盈亏平衡额 = 盈亏平衡量 × 单价

    Args:
        fixed_cost: 固定成本
        unit_price: 单位售价
        unit_cost: 单位可变成本

    Returns:
        盈亏平衡分析结果
    """
    try:
        if unit_price <= unit_cost:
            return _insufficient_data("单价必须大于单位可变成本（否则无法盈利）")

        contribution_margin = unit_price - unit_cost
        break_even_qty = fixed_cost / contribution_margin
        break_even_revenue = break_even_qty * unit_price
        contribution_margin_ratio = contribution_margin / unit_price

        return {
            "metric": "Break-Even",
            "formula": "固定成本 / (单价 - 单位成本)",
            "fixed_cost": fixed_cost,
            "unit_price": unit_price,
            "unit_cost": unit_cost,
            "contribution_margin": contribution_margin,
            "contribution_margin_ratio": contribution_margin_ratio,
            "break_even_quantity": round(break_even_qty, 2),
            "break_even_revenue": round(break_even_revenue, 2),
            "interpretation": (
                f"需要销售 {break_even_qty:.0f} 件（营收 {break_even_revenue:.2f}）才能回本。"
                f"每件贡献边际 {contribution_margin:.2f}，边际贡献率 {contribution_margin_ratio:.1%}。"
            ),
        }
    except Exception as e:
        return _insufficient_data(f"盈亏平衡计算失败: {e}")


# ── 增长指标 ───────────────────────────────────────────────


def calc_cagr(
    values: list[float] | pd.Series,
    periods: int | None = None,
) -> dict[str, Any]:
    """
    计算年复合增长率 (CAGR)

    CAGR = (终值/初值)^(1/年数) - 1

    Args:
        values: 数值序列（两个值以上）
        periods: 年数（默认从序列长度推断）

    Returns:
        CAGR 分析结果
    """
    try:
        if isinstance(values, pd.Series):
            vals = values.dropna().tolist()
        else:
            vals = list(values)

        if len(vals) < 2:
            return _insufficient_data("CAGR 需要至少两个数据点")

        start_value = float(vals[0])
        end_value = float(vals[-1])

        if start_value == 0 or start_value < 0 or end_value < 0:
            return _insufficient_data("CAGR 计算要求初始值为正数")

        if periods is None:
            periods = len(vals) - 1

        cagr = (end_value / start_value) ** (1 / periods) - 1
        abs_change = end_value - start_value
        pct_change = (end_value - start_value) / abs(start_value) * 100

        return {
            "metric": "CAGR",
            "formula": "(终值/初值)^(1/年数) - 1",
            "cagr": cagr,
            "cagr_percent": f"{cagr * 100:.2f}%",
            "start_value": start_value,
            "end_value": end_value,
            "abs_change": abs_change,
            "pct_change": pct_change,
            "periods": periods,
            "interpretation": (
                f"年复合增长率 {cagr*100:.2f}%。"
                f"（从 {start_value:.2f} 到 {end_value:.2f}，共 {periods} 期，"
                f"累计变化 {pct_change:+.1f}%）"
            ),
        }
    except Exception as e:
        return _insufficient_data(f"CAGR 计算失败: {e}")


def calc_growth_rate(
    current: float,
    previous: float,
) -> dict[str, Any]:
    """
    计算增长率（单期）

    Args:
        current: 本期值
        previous: 上期值

    Returns:
        增长率分析结果
    """
    try:
        if previous == 0:
            if current > 0:
                return {"metric": "Growth Rate", "growth": None, "interpretation": "上期为 0，无法计算增长率"}
            elif current < 0:
                return {"metric": "Growth Rate", "growth": None, "interpretation": "从负增长，两期均为负"}
            else:
                return {"metric": "Growth Rate", "growth": 0.0, "interpretation": "无变化"}
        growth = (current - previous) / abs(previous)
        abs_change = current - previous
        return {
            "metric": "Growth Rate",
            "formula": "(本期 - 上期) / |上期|",
            "growth": growth,
            "growth_percent": f"{growth * 100:+.2f}%",
            "current": current,
            "previous": previous,
            "abs_change": abs_change,
            "interpretation": (
                f"增长率 {growth*100:+.2f}%（{previous:.2f} → {current:.2f}，"
                f"{abs_change:+.2f}）"
            ),
        }
    except Exception as e:
        return _insufficient_data(f"增长率计算失败: {e}")


# ── 归因分析 ───────────────────────────────────────────────


def attribution_analysis(
    df: pd.DataFrame,
    conversions_col: str,
    channel_col: str,
    revenue_col: str | None = None,
    customer_col: str | None = None,
    method: str = "last_touch",
) -> dict[str, Any]:
    """
    渠道归因分析

    支持：首次触达(last_touch) / 最后触达(first_touch) / 线性归因(linear) / 位置归因(position)

    Args:
        df: 数据
        conversions_col: 转化列（1/0 或数值）
        channel_col: 渠道列
        revenue_col: 收益列（可选）
        customer_col: 客户 ID 列（用于旅程归因）
        method: 归因方法

    Returns:
        归因分析结果
    """
    try:
        if channel_col not in df.columns or conversions_col not in df.columns:
            return _insufficient_data(f"列不存在")

        if method == "last_touch":
            # 最后触达：转化归功于最后一次接触渠道
            conv_df = df[df[conversions_col] > 0]
            if len(conv_df) == 0:
                return _insufficient_data("没有转化数据")
            last_touch = conv_df.groupby(channel_col)[conversions_col].count()
            total = last_touch.sum()
            attributed = (last_touch / total * 100).round(2).to_dict()
            best_channel = last_touch.idxmax()

        elif method == "first_touch":
            # 首次触达：归功于第一次接触渠道
            conv_df = df[df[conversions_col] > 0]
            if customer_col and customer_col in df.columns:
                # 按客户找首次触达
                first_touch = df[df[conversions_col] > 0].sort_values(channel_col).groupby(customer_col)[channel_col].first()
                counts = first_touch.value_counts()
            else:
                counts = conv_df.groupby(channel_col)[conversions_col].count()
            total = counts.sum()
            attributed = (counts / total * 100).round(2).to_dict()
            best_channel = counts.idxmax()

        elif method == "linear":
            # 线性归因：平均分配给所有触达渠道
            if customer_col and customer_col in df.columns:
                n_touches = df.groupby(customer_col)[channel_col].count()
                credit = 1 / n_touches
                df_with_credit = df.copy()
                df_with_credit["credit"] = df_with_credit.index.map(
                    lambda idx: credit.get(df_with_credit.loc[idx, customer_col], 0)
                )
                conv_df = df_with_credit[df_with_credit[conversions_col] > 0]
                attr_series = conv_df.groupby(channel_col)["credit"].sum()
                total = attr_series.sum()
                attributed = (attr_series / total * 100).round(2).to_dict()
            else:
                attributed = {}
            best_channel = None

        elif method == "position":
            # 位置归因：首尾各 40%，中间平均分配 20%
            if customer_col and customer_col in df.columns:
                def position_credit(group):
                    n = len(group)
                    if n == 1:
                        return {group.name: 1.0}
                    first_c = 0.4 / n
                    last_c = 0.4 / n
                    mid_c = 0.2 / (n - 2) if n > 2 else 0
                    return {group.name: first_c if group.name == 0 else (last_c if group.name == n-1 else mid_c)}
            else:
                return _insufficient_data("位置归因需要 customer_col")
        else:
            return _insufficient_data(f"不支持的归因方法: {method}")

        # 收益归因（如果有）
        if revenue_col and revenue_col in df.columns and method in ("last_touch", "first_touch"):
            rev_by_channel = conv_df.groupby(channel_col)[revenue_col].sum()
            revenue_attr = rev_by_channel.to_dict()
        else:
            revenue_attr = None

        return {
            "metric": "Attribution",
            "method": method,
            "attribution": attributed,
            "best_channel": best_channel,
            "total_conversions": int(total),
            "n_channels": len(attributed),
            "revenue_by_channel": revenue_attr,
            "interpretation": (
                f"使用 {method} 归因，共 {total} 次转化，{len(attributed)} 个渠道。"
                + (f"最优渠道：{best_channel}。" if best_channel else "")
            ),
        }
    except Exception as e:
        return _insufficient_data(f"归因分析失败: {e}")


# ── 漏斗分析 ───────────────────────────────────────────────


def funnel_analysis(
    df: pd.DataFrame,
    stage_col: str,
    stage_order: list[str] | None = None,
    count_col: str | None = None,
    value_col: str | None = None,
) -> dict[str, Any]:
    """
    漏斗分析：各阶段转化率

    Args:
        df: 数据
        stage_col: 漏斗阶段列
        stage_order: 阶段顺序（按漏斗从上到下）
        count_col: 每阶段计数列（默认统计行数）
        value_col: 每阶段金额列（可选）

    Returns:
        漏斗分析结果
    """
    try:
        if stage_col not in df.columns:
            return _insufficient_data(f"列不存在: {stage_col}")

        # 确定顺序
        if stage_order is None:
            # 按频数降序排列（假设上面的漏斗量更大）
            stage_order = df[stage_col].value_counts().index.tolist()

        funnel = []
        prev_count = None
        prev_value = None

        for stage in stage_order:
            stage_df = df[df[stage_col] == stage]
            count = stage_df.shape[0] if count_col is None else float(stage_df[count_col].sum())
            value = float(stage_df[value_col].sum()) if value_col and value_col in stage_df.columns else None

            if prev_count is not None and prev_count > 0:
                stage_conv_rate = count / prev_count
                step_drop = prev_count - count
            else:
                stage_conv_rate = 1.0
                step_drop = 0

            funnel.append({
                "stage": stage,
                "count": int(count),
                "value": value,
                "from_previous_rate": round(stage_conv_rate, 4) if stage_conv_rate else 0,
                "step_drop": int(step_drop),
            })

            prev_count = count
            prev_value = value

        # 计算总体转化率
        if funnel and funnel[0]["count"] > 0:
            total_conv = funnel[-1]["count"] / funnel[0]["count"]
        else:
            total_conv = 0

        # 最大流失点
        max_drop_idx = max(range(len(funnel)), key=lambda i: funnel[i]["from_previous_rate"] < 1.0 and funnel[i]["from_previous_rate"] > 0)

        return {
            "metric": "Funnel",
            "funnel": funnel,
            "total_conversion": round(total_conv, 4),
            "total_conversion_percent": f"{total_conv*100:.2f}%",
            "biggest_drop_stage": funnel[max_drop_idx]["stage"] if funnel else None,
            "biggest_drop_rate": funnel[max_drop_idx]["from_previous_rate"] if funnel else None,
            "n_stages": len(funnel),
            "interpretation": (
                f"共 {len(funnel)} 个阶段，"
                f"总体转化率 {total_conv*100:.1f}%。"
                + (f"最大流失在「{funnel[max_drop_idx]['stage']}」"
                   f"（仅 {funnel[max_drop_idx]['from_previous_rate']*100:.1f}% 从上一步流入）。"
                   if funnel else "")
            ),
        }
    except Exception as e:
        return _insufficient_data(f"漏斗分析失败: {e}")


# ── 辅助函数 ───────────────────────────────────────────────


def _interpret_roi(roi: float) -> str:
    """ROI 解读"""
    if roi > 2:  # 200%
        return f"ROI = {roi:.1f}%，回报丰厚。投入 1 元，净赚 {roi/100:.2f} 元。"
    elif roi > 0:
        return f"ROI = {roi:.1f}%，有正回报。"
    elif roi == 0:
        return "ROI = 0%，刚好回本。"
    else:
        return f"ROI = {roi:.1f}%，亏损！投入 1 元，亏 {abs(roi)/100:.2f} 元。"


def _interpret_roas(roas: float) -> str:
    """ROAS 解读"""
    if roas >= 4:
        return f"ROAS = {roas:.1f}x，效果优秀。投入 1 元广告，带来 {roas:.1f} 元收益。"
    elif roas >= 2:
        return f"ROAS = {roas:.1f}x，效果良好。"
    elif roas >= 1:
        return f"ROAS = {roas:.1f}x，效果一般，勉强覆盖成本。"
    else:
        return f"ROAS = {roas:.1f}x，效果差，广告投放亏损！"
