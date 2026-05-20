"""HaGoKu Studio 模型诊断 — 让回归模型经得起审查"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


def diagnose_regression(
    model: Any,
    df: pd.DataFrame,
    target: str,
    features: list[str],
) -> dict[str, Any]:
    """
    全面回归诊断

    包含：
    - 残差正态性 (Shapiro-Wilk)
    - 异方差 (Breusch-Pagan)
    - 多重共线性 (VIF)
    - 自相关 (Durbin-Watson)
    - 残差模式 (非线性暗示)
    - 影响点 (Cook's distance)

    Args:
        model: statsmodels 回归模型
        df: 原始数据
        target: 因变量
        features: 自变量列表

    Returns:
        诊断结果字典
    """
    import statsmodels.api as sm
    from scipy import stats

    diagnostics: dict[str, Any] = {}
    residuals = model.resid
    fitted = model.fittedvalues
    n = len(residuals)

    # ── 残差正态性 ───────────────────────────────────────
    sample = residuals[:5000] if n > 5000 else residuals
    stat_sw, p_sw = stats.shapiro(sample)
    diagnostics["residual_normality"] = {
        "test": "shapiro_wilk",
        "statistic": float(stat_sw),
        "p_value": float(p_sw),
        "met": p_sw > 0.05,
        "verdict": "残差近似正态" if p_sw > 0.05 else "残差非正态，考虑稳健标准误或转换",
    }

    # ── 异方差 ───────────────────────────────────────────
    try:
        bp = sm.stats.het_breuschpagan(residuals, model.model.exog)
        diagnostics["heteroscedasticity"] = {
            "test": "breusch_pagan",
            "statistic": float(bp[0]),
            "p_value": float(bp[1]),
            "met": bp[1] > 0.05,
            "verdict": "无异方差" if bp[1] > 0.05 else "存在异方差，考虑稳健标准误(HC)或加权最小二乘",
        }
    except Exception as e:
        diagnostics["heteroscedasticity"] = {"error": str(e)}

    # ── VIF ──────────────────────────────────────────────
    if len(features) > 1:
        try:
            from statsmodels.stats.outliers_influence import variance_inflation_factor

            X = df[features].dropna()
            vif_data = {}
            for i, col in enumerate(features):
                vif_data[col] = round(float(variance_inflation_factor(X.values, i)), 4)

            max_vif = max(vif_data.values())
            diagnostics["multicollinearity"] = {
                "vif": vif_data,
                "max_vif": max_vif,
                "met": max_vif < 10,
                "verdict": "无严重共线性" if max_vif < 10 else f"VIF={max_vif:.1f} > 10，存在严重共线性",
            }
        except Exception as e:
            diagnostics["multicollinearity"] = {"error": str(e)}
    else:
        diagnostics["multicollinearity"] = {"met": True, "verdict": "单变量，无需检验共线性"}

    # ── Durbin-Watson ────────────────────────────────────
    from statsmodels.stats.stattools import durbin_watson

    dw = durbin_watson(residuals)
    if 1.5 < dw < 2.5:
        dw_verdict = "无自相关"
    elif dw < 1.5:
        dw_verdict = "正自相关，考虑 Newey-West 标准误"
    else:
        dw_verdict = "负自相关"

    diagnostics["autocorrelation"] = {
        "test": "durbin_watson",
        "statistic": float(dw),
        "met": 1.5 < dw < 2.5,
        "verdict": dw_verdict,
    }

    # ── 残差模式 (非线性暗示) ─────────────────────────────
    residual_pattern = _detect_residual_pattern(fitted, residuals)
    diagnostics["residual_pattern"] = residual_pattern

    # ── 影响点 (Cook's distance) ──────────────────────────
    try:
        influence = model.get_influence()
        cooks_d = influence.cooks_distance[0]
        threshold = 4 / n
        influential = np.sum(cooks_d > threshold)

        diagnostics["influential_points"] = {
            "test": "cooks_distance",
            "threshold": round(float(threshold), 6),
            "count": int(influential),
            "rate": round(float(influential / n), 4),
            "met": influential / n < 0.05,
            "verdict": "无严重影响点" if influential / n < 0.05 else f"{influential} 个影响点超过阈值，检查是否有录入错误",
        }
    except Exception as e:
        diagnostics["influential_points"] = {"error": str(e)}

    # ── 综合评估 ─────────────────────────────────────────
    all_met = all(
        v.get("met", True)
        for v in diagnostics.values()
        if isinstance(v, dict) and "met" in v
    )
    diagnostics["overall"] = {
        "passed": all_met,
        "verdict": "模型诊断通过" if all_met else "模型存在诊断问题，结果需谨慎解读",
    }

    return diagnostics


def _detect_residual_pattern(
    fitted: np.ndarray | pd.Series,
    residuals: np.ndarray | pd.Series,
) -> dict[str, Any]:
    """
    检测残差模式（暗示非线性）

    通过拟合残差与拟合值的关系来判断
    """
    fitted = np.asarray(fitted, dtype=float)
    residuals = np.asarray(residuals, dtype=float)

    # 排序拟合值
    order = np.argsort(fitted)
    fitted_sorted = fitted[order]
    residuals_sorted = residuals[order]

    # 计算残差的局部平均趋势（简单移动平均）
    window = max(10, len(fitted) // 20)
    if len(fitted) < window * 2:
        return {"pattern": "insufficient_data", "met": True}

    # 简单方法：把拟合值分 bin，看残差均值趋势
    n_bins = min(10, len(fitted) // 5)
    if n_bins < 3:
        return {"pattern": "insufficient_data", "met": True}

    bins = np.array_split(np.arange(len(fitted_sorted)), n_bins)
    bin_means = [residuals_sorted[b].mean() for b in bins]

    # 趋势检测：如果 bin 均值单调或呈 U 形
    bin_diffs = np.diff(bin_means)
    n_positive = np.sum(bin_diffs > 0)
    n_negative = np.sum(bin_diffs < 0)

    pattern = "random"
    if n_positive == len(bin_diffs) or n_negative == len(bin_diffs):
        pattern = "trend"  # 单调趋势
    elif _is_u_shaped(bin_means):
        pattern = "u_shape"
    elif _is_u_shaped(list(reversed(bin_means))):
        pattern = "inverted_u"

    return {
        "pattern": pattern,
        "met": pattern == "random",
        "verdict": {
            "random": "残差分布随机，线性假设合理",
            "trend": "残差呈趋势，可能遗漏变量",
            "u_shape": "残差呈 U 形，考虑非线性变换",
            "inverted_u": "残差呈倒 U 形，考虑非线性变换",
        }.get(pattern, "无法判断"),
    }


def _is_u_shaped(values: list[float]) -> bool:
    """简单 U 形检测：前半段递减，后半段递增"""
    if len(values) < 4:
        return False
    mid = len(values) // 2
    first_half = values[:mid]
    second_half = values[mid:]

    first_decreasing = all(first_half[i] >= first_half[i + 1] for i in range(len(first_half) - 1))
    second_increasing = all(second_half[i] <= second_half[i + 1] for i in range(len(second_half) - 1))

    return first_decreasing and second_increasing


def generate_diagnostic_plots(
    model: Any,
    output_dir: str | None = None,
) -> dict[str, Any]:
    """
    生成诊断图数据（不直接画图，返回数据供 visualization 模块使用）

    Args:
        model: statsmodels 回归模型
        output_dir: 输出目录（可选）

    Returns:
        图表数据字典
    """
    residuals = model.resid
    fitted = model.fittedvalues

    plots: dict[str, Any] = {}

    # 残差 vs 拟合值
    plots["residual_vs_fitted"] = {
        "type": "scatter",
        "x": {"label": "Fitted values", "data": fitted.tolist()[:1000]},
        "y": {"label": "Residuals", "data": residuals.tolist()[:1000]},
        "title": "Residuals vs Fitted",
        "hline": 0,
    }

    # Q-Q 图数据
    from scipy import stats

    (osm, osr), (slope, intercept, r) = stats.probplot(residuals, dist="norm")
    plots["qq_plot"] = {
        "type": "qq",
        "theoretical": osm.tolist()[:1000],
        "sample": osr.tolist()[:1000],
        "fit_line": {
            "slope": float(slope),
            "intercept": float(intercept),
        },
        "title": "Normal Q-Q Plot",
    }

    # Scale-Location 图
    std_residuals = residuals / residuals.std()
    sqrt_abs_std = np.sqrt(np.abs(std_residuals))
    plots["scale_location"] = {
        "type": "scatter",
        "x": {"label": "Fitted values", "data": fitted.tolist()[:1000]},
        "y": {"label": "√|Standardized residuals|", "data": sqrt_abs_std.tolist()[:1000]},
        "title": "Scale-Location",
    }

    # Cook's distance
    try:
        influence = model.get_influence()
        cooks_d = influence.cooks_distance[0]
        plots["cooks_distance"] = {
            "type": "bar",
            "x": {"label": "Observation", "data": list(range(len(cooks_d)))[:100]},
            "y": {"label": "Cook's distance", "data": cooks_d.tolist()[:100]},
            "title": "Cook's Distance",
            "hline": 4 / len(cooks_d),
        }
    except Exception:
        pass

    return plots
