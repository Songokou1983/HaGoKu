from __future__ import annotations
# Auto-split from analysis.py
import logging
import numpy as np
import pandas as pd
from typing import Any
from scipy import stats as _scipy_stats

from .config import _insufficient_data, _config

logger = logging.getLogger(__name__)

def check_test_assumptions(
    df: pd.DataFrame,
    test_type: str,
    **kwargs: Any,
) -> dict[str, Any]:
    """
    检验前假设检查：根据检验类型自动验证前提条件

    Args:
        df: 数据
        test_type: "ttest" / "anova" / "regression" / "correlation" / "chi_square"
        **kwargs: 检验相关参数（target, group_col, features 等）

    Returns:
        假设检查结果
    """
    from scipy import stats

    result: dict[str, Any] = {
        "test_type": test_type,
        "assumptions": {},
        "warnings": [],
        "recommendation": None,
    }

    if test_type == "ttest":
        group_col = kwargs.get("group_col")
        target = kwargs.get("target")
        if group_col and target and group_col in df.columns and target in df.columns:
            groups = df.groupby(group_col)[target]
            group_data = [g.dropna().values for _, g in groups]
            if len(group_data) >= 2:
                g1, g2 = group_data[0], group_data[1]

                # 正态性
                if len(g1) >= 3:
                    _, p1 = stats.shapiro(g1[:_config.shapiro_sample_limit])
                    result["assumptions"]["normality_group1"] = {
                        "p_value": round(float(p1), 4),
                        "met": p1 > _config.p_value_threshold,
                    }
                if len(g2) >= 3:
                    _, p2 = stats.shapiro(g2[:_config.shapiro_sample_limit])
                    result["assumptions"]["normality_group2"] = {
                        "p_value": round(float(p2), 4),
                        "met": p2 > _config.p_value_threshold,
                    }

                # 方差齐性
                if len(g1) >= 2 and len(g2) >= 2:
                    _, p_levene = stats.levene(g1, g2)
                    result["assumptions"]["equal_variance"] = {
                        "p_value": round(float(p_levene), 4),
                        "met": p_levene > _config.p_value_threshold,
                    }

                # 样本量
                min_n = min(len(g1), len(g2))
                result["assumptions"]["sample_size"] = {
                    "n1": len(g1), "n2": len(g2),
                    "met": min_n >= 30,
                }

                # 推荐替代
                norm_violated = any(
                    not v.get("met", True)
                    for k, v in result["assumptions"].items()
                    if k.startswith("normality") and not v.get("met", True)
                )
                var_violated = not result["assumptions"].get("equal_variance", {}).get("met", True)

                if norm_violated:
                    result["recommendation"] = "正态性不满足，建议使用 Mann-Whitney U 检验（非参数替代）"
                    result["warnings"].append("正态性假设不满足")
                elif var_violated:
                    result["recommendation"] = "方差齐性不满足，建议使用 Welch's t 检验"
                    result["warnings"].append("方差齐性假设不满足")

    elif test_type == "anova":
        group_col = kwargs.get("group_col")
        target = kwargs.get("target")
        if group_col and target and group_col in df.columns and target in df.columns:
            groups = [g.dropna().values for _, g in df.groupby(group_col)[target]]

            # 正态性（每组）
            normality_ok = True
            for i, g in enumerate(groups):
                if len(g) >= 3:
                    _, p = stats.shapiro(g[:_config.shapiro_sample_limit])
                    result["assumptions"][f"normality_group{i}"] = {
                        "p_value": round(float(p), 4),
                        "met": p > _config.p_value_threshold,
                    }
                    if p <= 0.05:
                        normality_ok = False

            # 方差齐性
            if len(groups) >= 2 and all(len(g) >= 2 for g in groups):
                _, p_levene = stats.levene(*groups)
                result["assumptions"]["equal_variance"] = {
                    "p_value": round(float(p_levene), 4),
                    "met": p_levene > _config.p_value_threshold,
                }

            # 样本量
            result["assumptions"]["sample_size"] = {
                "per_group": [len(g) for g in groups],
                "met": all(len(g) >= 5 for g in groups),
            }

            if not normality_ok:
                result["recommendation"] = "正态性不满足，建议使用 Kruskal-Wallis H 检验（非参数替代）"
                result["warnings"].append("正态性假设不满足")

    elif test_type == "regression":
        target = kwargs.get("target")
        features = kwargs.get("features", [])
        if target and target in df.columns:
            y = df[target].dropna()

            # 正态性（因变量）
            if len(y) >= 3:
                _, p = stats.shapiro(y[:_config.shapiro_sample_limit])
                result["assumptions"]["normality_target"] = {
                    "p_value": round(float(p), 4),
                    "met": p > _config.p_value_threshold,
                }

            # 线性暗示（如果有 features）
            if features:
                for feat in features[:5]:  # 最多检查 5 个
                    if feat in df.columns:
                        valid = df[[target, feat]].dropna()
                        if len(valid) >= 10:
                            corr, _ = stats.pearsonr(valid[target], valid[feat])
                            result["assumptions"][f"linearity_{feat}"] = {
                                "pearson_r": round(float(corr), 4),
                                "linear_hint": abs(corr) > 0.1,
                            }

            # 多重共线性（VIF）
            if len(features) > 1:
                try:
                    from statsmodels.stats.outliers_influence import variance_inflation_factor
                    X = df[features].dropna()
                    if len(X) > len(features):
                        vif_values = {}
                        for i, col in enumerate(features):
                            vif_values[col] = round(float(variance_inflation_factor(X.values, i)), 4)
                        max_vif = max(vif_values.values())
                        result["assumptions"]["multicollinearity"] = {
                            "vif": vif_values,
                            "max_vif": max_vif,
                            "met": max_vif < 10,
                        }
                        if max_vif >= 10:
                            result["warnings"].append(f"VIF={max_vif:.1f} >= 10，存在严重共线性")
                except Exception as e:
                    logger.debug("VIF calculation skipped: %s", e)

            # 样本量（每变量至少 10-15 个观测）
            n_per_var = len(df) / max(len(features), 1)
            result["assumptions"]["sample_size_per_predictor"] = {
                "ratio": round(float(n_per_var), 1),
                "met": n_per_var >= 10,
            }

    elif test_type == "correlation":
        col1 = kwargs.get("col1")
        col2 = kwargs.get("col2")
        method = kwargs.get("method", "pearson")
        if col1 and col2 and col1 in df.columns and col2 in df.columns:
            valid = df[[col1, col2]].dropna()

            if method == "pearson":
                # 正态性（两个变量）
                if len(valid) >= 3:
                    _, p1 = stats.shapiro(valid[col1].values[:_config.shapiro_sample_limit])
                    _, p2 = stats.shapiro(valid[col2].values[:_config.shapiro_sample_limit])
                    result["assumptions"]["normality"] = {
                        "p_value_col1": round(float(p1), 4),
                        "p_value_col2": round(float(p2), 4),
                        "met": p1 > _config.p_value_threshold and p2 > _config.p_value_threshold,
                    }
                    if p1 <= 0.05 or p2 <= 0.05:
                        result["recommendation"] = "变量非正态，建议使用 Spearman 等级相关"
                        result["warnings"].append("Pearson 相关的正态性假设不满足")

            # 线性（散点图暗示）
            if len(valid) >= 10:
                corr_p, _ = stats.pearsonr(valid[col1], valid[col2])
                corr_s, _ = stats.spearmanr(valid[col1], valid[col2])
                # Pearson 和 Spearman 差异大 → 非线性
                diff = abs(corr_p - corr_s)
                result["assumptions"]["linearity"] = {
                    "pearson_r": round(float(corr_p), 4),
                    "spearman_r": round(float(corr_s), 4),
                    "difference": round(float(diff), 4),
                    "met": diff < 0.2,
                }
                if diff >= 0.2:
                    result["warnings"].append("Pearson-Spearman 差异较大，可能存在非线性关系")

    elif test_type == "chi_square":
        col1 = kwargs.get("col1")
        col2 = kwargs.get("col2")
        if col1 and col2 and col1 in df.columns and col2 in df.columns:
            contingency = pd.crosstab(df[col1], df[col2])

            # 期望频数（每格 ≥ 5）
            from scipy import stats as sp_stats
            _, _, _, expected = sp_stats.chi2_contingency(contingency)
            low_expected = np.sum(expected < 5)
            total_cells = expected.size
            result["assumptions"]["expected_frequencies"] = {
                "cells_below_5": int(low_expected),
                "total_cells": int(total_cells),
                "rate": round(float(low_expected / total_cells), 4),
                "met": low_expected / total_cells < 0.2,
            }

            if low_expected / total_cells >= 0.2:
                result["recommendation"] = "期望频数过低（>20% 格子 < 5），建议使用 Fisher 精确检验"
                result["warnings"].append("卡方检验期望频数假设不满足")

    # 汇总
    all_met = all(
        v.get("met", True)
        for v in result["assumptions"].values()
        if isinstance(v, dict) and "met" in v
    )
    result["all_assumptions_met"] = all_met

    return result



def _check_ttest_assumptions(
    g1: pd.Series | np.ndarray,
    g2: pd.Series | np.ndarray,
) -> dict[str, Any]:
    """检查 t 检验假设"""
    from scipy import stats

    g1, g2 = np.asarray(g1, dtype=float), np.asarray(g2, dtype=float)
    assumptions: dict[str, Any] = {}

    # 正态性 (Shapiro-Wilk，样本量 ≤ 5000)
    if len(g1) <= 5000:
        _, p_norm1 = stats.shapiro(g1[:_config.shapiro_sample_limit] if len(g1) > 5000 else g1)
        assumptions["normality_group1"] = {"p_value": float(p_norm1), "met": p_norm1 > _config.p_value_threshold}
    if len(g2) <= 5000:
        _, p_norm2 = stats.shapiro(g2[:_config.shapiro_sample_limit] if len(g2) > 5000 else g2)
        assumptions["normality_group2"] = {"p_value": float(p_norm2), "met": p_norm2 > _config.p_value_threshold}

    # 方差齐性 (Levene's test)
    _, p_levene = stats.levene(g1, g2)
    assumptions["equal_variance"] = {"p_value": float(p_levene), "met": p_levene > _config.p_value_threshold}

    return assumptions



def _cohens_d(
    g1: pd.Series | np.ndarray,
    g2: pd.Series | np.ndarray,
    *,
    paired: bool = False,
) -> float:
    """计算 Cohen's d"""
    g1, g2 = np.asarray(g1, dtype=float), np.asarray(g2, dtype=float)
    if paired:
        diff = g1 - g2
        return float(np.mean(diff) / np.std(diff, ddof=1)) if np.std(diff, ddof=1) > 0 else 0
    else:
        pooled_std = np.sqrt((np.var(g1, ddof=1) + np.var(g2, ddof=1)) / 2)
        return float((np.mean(g1) - np.mean(g2)) / pooled_std) if pooled_std > 0 else 0



def _mean_diff_ci(
    g1: pd.Series | np.ndarray,
    g2: pd.Series | np.ndarray,
    *,
    paired: bool = False,
    confidence: float = 0.95,
) -> str:
    """均值差的置信区间"""
    from scipy import stats

    g1, g2 = np.asarray(g1, dtype=float), np.asarray(g2, dtype=float)
    diff = np.mean(g1) - np.mean(g2)

    if paired:
        diffs = g1 - g2
        se = np.std(diffs, ddof=1) / np.sqrt(len(diffs))
        df = len(diffs) - 1
    else:
        se = np.sqrt(np.var(g1, ddof=1) / len(g1) + np.var(g2, ddof=1) / len(g2))
        df = len(g1) + len(g2) - 2

    t_crit = stats.t.ppf((1 + confidence) / 2, df)
    lower = diff - t_crit * se
    upper = diff + t_crit * se
    return f"[{lower:.4f}, {upper:.4f}]"



