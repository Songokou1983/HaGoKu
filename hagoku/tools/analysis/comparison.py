from __future__ import annotations
# Auto-split from analysis.py
import numpy as np
import pandas as pd
from typing import Any
from scipy import stats as _scipy_stats
from .config import _insufficient_data
from .diagnostics import _check_ttest_assumptions, _cohens_d, _mean_diff_ci


def ttest(
    group1: pd.Series | np.ndarray,
    group2: pd.Series | np.ndarray,
    *,
    paired: bool = False,
    alternative: str = "two-sided",
) -> dict[str, Any]:
    """
    t 检验，自动报告效应量

    Args:
        group1: 第一组数据
        group2: 第二组数据
        paired: 是否配对
        alternative: "two-sided" / "greater" / "less"

    Returns:
        检验结果字典
    """
    g1 = np.asarray(group1, dtype=float)
    g2 = np.asarray(group2, dtype=float)
    g1 = g1[~np.isnan(g1)]
    g2 = g2[~np.isnan(g2)]

    min_n = 3 if not paired else 2
    if len(g1) < min_n or len(g2) < min_n:
        return _insufficient_data(
            f"t 检验需要每组至少 {min_n} 个有效观测值 "
            f"(实际: n1={len(g1)}, n2={len(g2)})"
        )
    if paired and len(g1) != len(g2):
        return _insufficient_data(
            f"配对 t 检验需要两组等长 (n1={len(g1)}, n2={len(g2)})"
        )

    # 常数列（零方差）无法做 t 检验
    if np.std(g1) == 0 or np.std(g2) == 0:
        return _insufficient_data(
            "t 检验要求每组方差 > 0（检测到常数列）"
        )

    try:
        import pingouin as pg

        result = pg.ttest(g1, g2, paired=paired, alternative=alternative)
        # pingouin 列名版本兼容: p-val / p_val, cohen-d / cohen_d, CI95% / CI95
        p_val_col = "p-val" if "p-val" in result.columns else "p_val"
        d_col = "cohen-d" if "cohen-d" in result.columns else "cohen_d"
        ci_col = "CI95%" if "CI95%" in result.columns else "CI95"
        return {
            "test": "ttest",
            "paired": paired,
            "statistic": float(result["T"].iloc[0]),
            "p_value": float(result[p_val_col].iloc[0]),
            "effect_size": float(result[d_col].iloc[0]),
            "effect_type": "cohen_d",
            "confidence_interval": str(result[ci_col].iloc[0]),
            "df": float(result["dof"].iloc[0]),
            "assumptions": _check_ttest_assumptions(g1, g2),
        }
    except ImportError:
        # 退回 scipy
        from scipy import stats

        if paired:
            stat, p = stats.ttest_rel(g1, g2, alternative=alternative)
        else:
            stat, p = stats.ttest_ind(g1, g2, alternative=alternative)

        # 手动计算 Cohen's d
        d = _cohens_d(g1, g2, paired=paired)
        ci = _mean_diff_ci(g1, g2, paired=paired)

        return {
            "test": "ttest",
            "paired": paired,
            "statistic": float(stat),
            "p_value": float(p),
            "effect_size": float(d),
            "effect_type": "cohen_d",
            "confidence_interval": ci,
            "df": len(g1) + len(g2) - 2 if not paired else len(g1) - 1,
            "assumptions": _check_ttest_assumptions(g1, g2),
        }



def anova(
    df: pd.DataFrame,
    dv: str,
    between: str | list[str],
) -> dict[str, Any]:
    """
    方差分析，自动报告效应量

    Args:
        df: 数据
        dv: 因变量列名
        between: 自变量列名（单因素 / 多因素）

    Returns:
        ANOVA 结果字典
    """
    if len(df) < 4:
        return _insufficient_data(f"ANOVA 需要至少 4 行数据 (实际: {len(df)})")

    if dv not in df.columns:
        return _insufficient_data(f"因变量 '{dv}' 不在数据中")

    if isinstance(between, str):
        if between not in df.columns:
            return _insufficient_data(f"分组变量 '{between}' 不在数据中")
        n_groups = df[between].nunique()
        if n_groups < 2:
            return _insufficient_data(f"ANOVA 需要至少 2 个分组 (实际: {n_groups})")
        # 检查每组至少 2 个观测值
        group_sizes = df.groupby(between)[dv].count()
        if (group_sizes < 2).any():
            return _insufficient_data(
                f"ANOVA 每组需要至少 2 个观测值 "
                f"(最小组: {group_sizes.min()})"
            )

    try:
        import pingouin as pg

        if isinstance(between, str):
            result = pg.anova(df, dv=dv, between=between)
            p_unc_col = "p-unc" if "p-unc" in result.columns else "p_unc"
            np2_col = "np2" if "np2" in result.columns else "n2p"
            return {
                "test": "one_way_anova",
                "f_statistic": float(result["F"].iloc[0]),
                "p_value": float(result[p_unc_col].iloc[0]),
                "effect_size": float(result[np2_col].iloc[0]),
                "effect_type": "eta_squared",
                "df_between": float(result["ddof1"].iloc[0]),
                "df_within": float(result["ddof2"].iloc[0]),
            }
        else:
            result = pg.anova(df, dv=dv, between=between)
            return {
                "test": "n_way_anova",
                "results": result.to_dict("records"),
            }
    except ImportError:
        from scipy import stats

        if isinstance(between, str):
            groups = [g[dv].values for _, g in df.groupby(between)]
            stat, p = stats.f_oneway(*groups)
            # 计算 η²
            ss_between = sum(len(g) * (g.mean() - df[dv].mean()) ** 2 for g in groups)
            ss_total = sum((df[dv] - df[dv].mean()) ** 2)
            eta_sq = ss_between / ss_total if ss_total > 0 else 0

            return {
                "test": "one_way_anova",
                "f_statistic": float(stat),
                "p_value": float(p),
                "effect_size": float(eta_sq),
                "effect_type": "eta_squared",
                "n_groups": len(groups),
            }
        raise ImportError("多因素 ANOVA 需要 pingouin: pip install pingouin")



def chi_square(
    df: pd.DataFrame,
    col1: str,
    col2: str,
) -> dict[str, Any]:
    """
    卡方检验（独立性检验），自动报告 Cramér's V

    Args:
        df: 数据
        col1: 第一个分类变量
        col2: 第二个分类变量

    Returns:
        卡方检验结果
    """
    if len(df) < 5:
        return _insufficient_data(f"卡方检验需要至少 5 行数据 (实际: {len(df)})")
    if col1 not in df.columns or col2 not in df.columns:
        return _insufficient_data(f"列 '{col1}' 或 '{col2}' 不在数据中")

    contingency = pd.crosstab(df[col1], df[col2])
    if contingency.size == 0:
        return _insufficient_data("列联表为空")

    from scipy import stats

    chi2, p, dof, expected = stats.chi2_contingency(contingency)
    n = len(df)
    min_dim = min(contingency.shape) - 1
    cramers_v = np.sqrt(chi2 / (n * min_dim)) if min_dim > 0 else 0

    return {
        "test": "chi_square",
        "statistic": float(chi2),
        "p_value": float(p),
        "df": int(dof),
        "effect_size": float(cramers_v),
        "effect_type": "cramers_v",
        "n_observations": n,
    }



def mann_whitney_u(
    group1: pd.Series | np.ndarray,
    group2: pd.Series | np.ndarray,
) -> dict[str, Any]:
    """
    Mann-Whitney U 检验（非参数 t 检验替代）

    Args:
        group1: 第一组数据
        group2: 第二组数据

    Returns:
        检验结果
    """
    g1 = np.asarray(group1, dtype=float)
    g2 = np.asarray(group2, dtype=float)
    g1 = g1[~np.isnan(g1)]
    g2 = g2[~np.isnan(g2)]

    if len(g1) < 2 or len(g2) < 2:
        return _insufficient_data(
            f"Mann-Whitney U 需要每组至少 2 个有效观测值 (n1={len(g1)}, n2={len(g2)})"
        )

    from scipy import stats

    stat, p = stats.mannwhitneyu(g1, g2, alternative="two-sided")

    # 效应量: rank-biserial correlation r = 1 - 2U / (n1*n2)
    n1, n2 = len(g1), len(g2)
    r = 1 - (2 * stat) / (n1 * n2)

    return {
        "test": "mann_whitney_u",
        "statistic": float(stat),
        "p_value": float(p),
        "effect_size": float(abs(r)),
        "effect_type": "rank_biserial_r",
        "n_group1": n1,
        "n_group2": n2,
    }



def kruskal_wallis(
    df: pd.DataFrame,
    dv: str,
    between: str,
) -> dict[str, Any]:
    """
    Kruskal-Wallis H 检验（非参数 ANOVA 替代）

    Args:
        df: 数据
        dv: 因变量列名
        between: 分组变量列名

    Returns:
        检验结果
    """
    if len(df) < 4:
        return _insufficient_data(f"Kruskal-Wallis 需要至少 4 行数据 (实际: {len(df)})")
    if between not in df.columns:
        return _insufficient_data(f"分组变量 '{between}' 不在数据中")
    n_groups = df[between].nunique()
    if n_groups < 2:
        return _insufficient_data(f"Kruskal-Wallis 需要至少 2 个分组 (实际: {n_groups})")

    from scipy import stats

    groups = [g[dv].values for _, g in df.groupby(between)]
    stat, p = stats.kruskal(*groups)

    # 效应量: η²_H = (H - k + 1) / (n - k)
    k = len(groups)
    n = len(df)
    eta_sq = (stat - k + 1) / (n - k) if n > k else 0

    return {
        "test": "kruskal_wallis",
        "statistic": float(stat),
        "p_value": float(p),
        "effect_size": float(eta_sq),
        "effect_type": "eta_squared_h",
        "n_groups": k,
        "n_observations": n,
    }



