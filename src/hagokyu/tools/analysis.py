"""HaGoKu 统计分析核心 — 精、准、狠"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


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
    try:
        import pingouin as pg

        result = pg.ttest(group1, group2, paired=paired, alternative=alternative)
        return {
            "test": "ttest",
            "paired": paired,
            "statistic": float(result["T"].iloc[0]),
            "p_value": float(result["p-val"].iloc[0]),
            "effect_size": float(result["cohen-d"].iloc[0]),
            "effect_type": "cohen_d",
            "confidence_interval": str(result["CI95%"].iloc[0]),
            "df": float(result["dof"].iloc[0]),
            "assumptions": _check_ttest_assumptions(group1, group2),
        }
    except ImportError:
        # 退回 scipy
        from scipy import stats

        if paired:
            stat, p = stats.ttest_rel(group1, group2, alternative=alternative)
        else:
            stat, p = stats.ttest_ind(group1, group2, alternative=alternative)

        # 手动计算 Cohen's d
        d = _cohens_d(group1, group2, paired=paired)
        ci = _mean_diff_ci(group1, group2, paired=paired)

        return {
            "test": "ttest",
            "paired": paired,
            "statistic": float(stat),
            "p_value": float(p),
            "effect_size": float(d),
            "effect_type": "cohen_d",
            "confidence_interval": ci,
            "df": len(group1) + len(group2) - 2 if not paired else len(group1) - 1,
            "assumptions": _check_ttest_assumptions(group1, group2),
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
    try:
        import pingouin as pg

        if isinstance(between, str):
            result = pg.anova(df, dv=dv, between=between)
            return {
                "test": "one_way_anova",
                "f_statistic": float(result["F"].iloc[0]),
                "p_value": float(result["p-unc"].iloc[0]),
                "effect_size": float(result["np2"].iloc[0]),
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
    contingency = pd.crosstab(df[col1], df[col2])
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
    from scipy import stats

    x, y = df[col1].dropna(), df[col2].dropna()
    # 对齐有效索引
    valid = df[[col1, col2]].dropna()
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


def regression(
    df: pd.DataFrame,
    target: str,
    features: list[str],
    *,
    method: str = "ols",
    add_constant: bool = True,
) -> dict[str, Any]:
    """
    回归分析，自动诊断

    Args:
        df: 数据
        target: 因变量列名
        features: 自变量列名列表
        method: "ols" / "robust" / "logistic"
        add_constant: 是否添加常数项

    Returns:
        回归分析结果（含诊断）
    """
    import statsmodels.api as sm

    y = df[target]
    X = df[features]

    if add_constant:
        X = sm.add_constant(X)

    if method == "ols":
        model = sm.OLS(y, X).fit()
    elif method == "robust":
        model = sm.RLM(y, X).fit()
    elif method == "logistic":
        model = sm.Logit(y, X).fit(disp=0)
    else:
        raise ValueError(f"不支持的回归方法: {method}")

    # 基本结果
    result: dict[str, Any] = {
        "test": "regression",
        "method": method,
        "r_squared": float(model.rsquared) if hasattr(model, "rsquared") else None,
        "adj_r_squared": float(model.rsquared_adj) if hasattr(model, "rsquared_adj") else None,
        "f_statistic": float(model.fvalue) if hasattr(model, "fvalue") else None,
        "f_pvalue": float(model.f_pvalue) if hasattr(model, "f_pvalue") else None,
        "n_obs": int(model.nobs),
        "coefficients": {str(k): float(v) for k, v in model.params.items()},
        "p_values": {str(k): float(v) for k, v in model.pvalues.items()},
        "confidence_intervals": {
            str(k): [float(v[0]), float(v[1])]
            for k, v in model.conf_int().iterrows()
        },
    }

    # 效应量: f² = (R² - R²_0) / (1 - R²)
    if result["r_squared"] is not None:
        result["effect_size"] = float(result["r_squared"] / (1 - result["r_squared"]))
        result["effect_type"] = "f_squared"

    # 诊断（OLS 时）
    if method == "ols" and result["r_squared"] is not None:
        result["diagnostics"] = _regression_diagnostics(model, df, target, features)

    return result


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
    from scipy import stats

    stat, p = stats.mannwhitneyu(group1, group2, alternative="two-sided")

    # 效应量: rank-biserial correlation r = 1 - 2U / (n1*n2)
    n1, n2 = len(group1), len(group2)
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


# ── 辅助函数 ─────────────────────────────────────────────────


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
        _, p_norm1 = stats.shapiro(g1[:5000] if len(g1) > 5000 else g1)
        assumptions["normality_group1"] = {"p_value": float(p_norm1), "met": p_norm1 > 0.05}
    if len(g2) <= 5000:
        _, p_norm2 = stats.shapiro(g2[:5000] if len(g2) > 5000 else g2)
        assumptions["normality_group2"] = {"p_value": float(p_norm2), "met": p_norm2 > 0.05}

    # 方差齐性 (Levene's test)
    _, p_levene = stats.levene(g1, g2)
    assumptions["equal_variance"] = {"p_value": float(p_levene), "met": p_levene > 0.05}

    return assumptions


def _regression_diagnostics(
    model: Any,
    df: pd.DataFrame,
    target: str,
    features: list[str],
) -> dict[str, Any]:
    """回归诊断"""
    from scipy import stats
    import statsmodels.api as sm

    diagnostics: dict[str, Any] = {}

    # 残差
    residuals = model.resid

    # 正态性
    _, p_norm = stats.shapiro(residuals[:5000] if len(residuals) > 5000 else residuals)
    diagnostics["residual_normality"] = {
        "test": "shapiro_wilk",
        "p_value": float(p_norm),
        "met": p_norm > 0.05,
    }

    # 异方差 (Breusch-Pagan)
    try:
        bp_test = sm.stats.het_breuschpagan(residuals, model.model.exog)
        diagnostics["heteroscedasticity"] = {
            "test": "breusch_pagan",
            "statistic": float(bp_test[0]),
            "p_value": float(bp_test[1]),
            "met": bp_test[1] > 0.05,
        }
    except Exception:
        pass

    # 多重共线性 (VIF)
    if len(features) > 1:
        try:
            from statsmodels.stats.outliers_influence import variance_inflation_factor

            X = df[features].dropna()
            vif_data = {}
            for i, col in enumerate(features):
                vif_data[col] = float(variance_inflation_factor(X.values, i))
            diagnostics["vif"] = vif_data
        except Exception:
            pass

    # Durbin-Watson (自相关)
    from statsmodels.stats.stattools import durbin_watson

    dw = durbin_watson(residuals)
    diagnostics["durbin_watson"] = {
        "statistic": float(dw),
        "interpretation": "no_autocorrelation" if 1.5 < dw < 2.5 else "potential_autocorrelation",
    }

    return diagnostics
