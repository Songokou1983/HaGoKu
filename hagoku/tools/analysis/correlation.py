from __future__ import annotations
# Auto-split from analysis.py
import numpy as np
from typing import Any
from scipy import stats as _scipy_stats
from .config import _insufficient_data


def correlation(
    df: pd.DataFrame,
    col1: str,
    col2: str,
    *,
    method: str = "pearson",
) -> dict[str, Any]:
    """
    相关分析

    Args:
        df: 数据
        col1: 第一个变量
        col2: 第二个变量
        method: "pearson" / "spearman" / "kendall"

    Returns:
        相关分析结果
    """
    if col1 not in df.columns or col2 not in df.columns:
        return _insufficient_data(f"列 '{col1}' 或 '{col2}' 不在数据中")

    valid = df[[col1, col2]].dropna()
    if len(valid) < 3:
        return _insufficient_data(f"相关分析需要至少 3 对有效观测 (实际: {len(valid)})")

    # 常数列无法计算相关
    if valid[col1].std() == 0 or valid[col2].std() == 0:
        return _insufficient_data("常数列（零方差）无法计算相关系数")

    from scipy import stats

    x, y = df[col1].dropna(), df[col2].dropna()
    # 对齐有效索引（已上方 dropna，此处用 valid）
    x, y = valid[col1], valid[col2]

    if method == "pearson":
        stat, p = stats.pearsonr(x, y)
    elif method == "spearman":
        stat, p = stats.spearmanr(x, y)
    elif method == "kendall":
        stat, p = stats.kendalltau(x, y)
    else:
        raise ValueError(f"不支持的方法: {method}，可选: pearson, spearman, kendall")

    return {
        "test": "correlation",
        "method": method,
        "statistic": float(stat),
        "p_value": float(p),
        "effect_size": float(abs(stat)),
        "effect_type": f"{method}_r",
        "n_observations": len(valid),
    }



