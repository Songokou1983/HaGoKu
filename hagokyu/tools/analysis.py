"""HaGoKu 统计分析核心 — 精、准、狠"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from ..config import AnalysisConfig
from ..log import get_logger

logger = get_logger("analysis")

# 模块级配置（默认值，可由 Orchestrator 通过 set_analysis_config 覆盖）
_config = AnalysisConfig()


def set_analysis_config(config: AnalysisConfig) -> None:
    """设置模块级分析配置（由 Orchestrator 在启动时调用）"""
    global _config
    _config = config


def _insufficient_data(msg: str) -> dict[str, Any]:
    """返回数据不足的标准错误结果"""
    return {"error": "insufficient_data", "message": msg}


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
    min_n = len(features) + 3
    if len(df) < min_n:
        return _insufficient_data(
            f"回归分析需要至少 {min_n} 行数据 ({len(features)} 个自变量 + 3, 实际: {len(df)})"
        )
    if target not in df.columns:
        return _insufficient_data(f"因变量 '{target}' 不在数据中")
    missing_features = [f for f in features if f not in df.columns]
    if missing_features:
        return _insufficient_data(f"自变量 {missing_features} 不在数据中")
    # 常数因变量
    if df[target].std() == 0:
        return _insufficient_data("因变量为常数列（零方差），无法做回归")
    # 常数自变量
    const_features = [f for f in features if df[f].std() == 0]
    if const_features:
        return _insufficient_data(f"自变量 {const_features} 为常数列（零方差），无法做回归")

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
        denom = 1 - result["r_squared"]
        if denom > 1e-10:
            result["effect_size"] = float(result["r_squared"] / denom)
            result["effect_type"] = "f_squared"
        else:
            # R² ≈ 1.0 (完美拟合)，f² 无意义但说明模型极强
            result["effect_size"] = float("inf")
            result["effect_type"] = "f_squared"
            result["warning"] = "R² ≈ 1.0，可能存在过拟合或完全拟合"

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


# ── 增强功能：交叉验证 / 多比较校正 / 假设检验前置检查 / 交互分析 ──


def cross_validate(
    df: pd.DataFrame,
    target: str,
    features: list[str],
    *,
    method: str = "ols",
    k_folds: int = 5,
    scoring: str = "r_squared",
) -> dict[str, Any]:
    """
    k-fold 交叉验证，评估模型泛化能力

    Args:
        df: 数据
        target: 因变量列名
        features: 自变量列名列表
        method: "ols" / "robust" / "logistic"
        k_folds: 折数（默认 5）
        scoring: "r_squared" / "rmse" / "mae"

    Returns:
        交叉验证结果
    """
    import statsmodels.api as sm
    from sklearn.model_selection import KFold

    n = len(df)
    min_n = len(features) + 3
    if n < min_n:
        return _insufficient_data(
            f"交叉验证需要至少 {min_n} 行数据 (实际: {n})"
        )
    if target not in df.columns:
        return _insufficient_data(f"因变量 '{target}' 不在数据中")
    missing_features = [f for f in features if f not in df.columns]
    if missing_features:
        return _insufficient_data(f"自变量 {missing_features} 不在数据中")

    # 调整折数：小样本时减少折数
    actual_k = min(k_folds, n // min_n)
    if actual_k < 2:
        return _insufficient_data(
            f"交叉验证至少需要 2 折 (样本 {n} / 最小折样本 {min_n})"
        )

    y = df[target].values
    X = df[features].values
    X = sm.add_constant(X)

    kf = KFold(n_splits=actual_k, shuffle=True, random_state=_config.random_state)

    train_scores: list[float] = []
    test_scores: list[float] = []

    for train_idx, test_idx in kf.split(X):
        X_train, X_test = X[train_idx], X[test_idx]
        y_train, y_test = y[train_idx], y[test_idx]

        try:
            if method == "ols":
                model = sm.OLS(y_train, X_train).fit()
            elif method == "robust":
                model = sm.RLM(y_train, X_train).fit()
            elif method == "logistic":
                model = sm.Logit(y_train, X_train).fit(disp=0)
            else:
                raise ValueError(f"不支持的回归方法: {method}")

            # 训练集评分
            if scoring == "r_squared" and method != "logistic":
                train_r2 = _calc_r_squared(y_train, model.predict(X_train))
                test_r2 = _calc_r_squared(y_test, model.predict(X_test))
                train_scores.append(train_r2)
                test_scores.append(test_r2)
            elif scoring == "rmse":
                train_rmse = float(np.sqrt(np.mean((y_train - model.predict(X_train)) ** 2)))
                test_rmse = float(np.sqrt(np.mean((y_test - model.predict(X_test)) ** 2)))
                train_scores.append(train_rmse)
                test_scores.append(test_rmse)
            elif scoring == "mae":
                train_mae = float(np.mean(np.abs(y_train - model.predict(X_train))))
                test_mae = float(np.mean(np.abs(y_test - model.predict(X_test))))
                train_scores.append(train_mae)
                test_scores.append(test_mae)
            else:
                # 默认 R²
                if method != "logistic":
                    train_scores.append(_calc_r_squared(y_train, model.predict(X_train)))
                    test_scores.append(_calc_r_squared(y_test, model.predict(X_test)))
        except Exception as e:
            logger.warning("Cross-validation fold failed: %s", e)
            continue

    if not train_scores:
        return {"error": "cv_failed", "message": "所有折的模型拟合均失败"}

    train_mean = float(np.mean(train_scores))
    test_mean = float(np.mean(test_scores))
    train_std = float(np.std(train_scores))
    test_std = float(np.std(test_scores))

    # 过拟合检测
    if scoring == "r_squared":
        gap = train_mean - test_mean
        overfitting = gap > _config.overfitting_gap_threshold
    elif scoring in ("rmse", "mae"):
        gap = test_mean - train_mean
        overfitting = gap / max(train_mean, 1e-10) > _config.overfitting_gap_threshold
    else:
        gap = abs(train_mean - test_mean)
        overfitting = False

    return {
        "test": "cross_validation",
        "method": method,
        "k_folds": actual_k,
        "scoring": scoring,
        "train_scores": [round(s, 4) for s in train_scores],
        "test_scores": [round(s, 4) for s in test_scores],
        "train_mean": round(train_mean, 4),
        "train_std": round(train_std, 4),
        "test_mean": round(test_mean, 4),
        "test_std": round(test_std, 4),
        "generalization_gap": round(float(gap), 4),
        "overfitting_detected": overfitting,
        "n_observations": n,
    }


def _calc_r_squared(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    """计算 R²"""
    ss_res = np.sum((y_true - y_pred) ** 2)
    ss_tot = np.sum((y_true - np.mean(y_true)) ** 2)
    return float(1 - ss_res / ss_tot) if ss_tot > 0 else 0.0


def multiple_comparison_correction(
    p_values: list[float],
    *,
    method: str = "bh",
    alpha: float = 0.05,
) -> dict[str, Any]:
    """
    多重比较校正（控制族错误率或发现错误率）

    Args:
        p_values: 原始 p 值列表
        method: "bonferroni" / "bh"（Benjamini-Hochberg）/ "holm"
        alpha: 显著性水平（默认 0.05）

    Returns:
        校正结果
    """

    n = len(p_values)
    if n == 0:
        return {"error": "no_p_values", "message": "p 值列表为空"}

    if n == 1:
        # 单个检验无需校正
        return {
            "test": "multiple_comparison_correction",
            "method": "none_needed",
            "n_tests": 1,
            "original_p": p_values,
            "adjusted_p": p_values,
            "significant": [p < alpha for p in p_values],
            "note": "单次检验无需多重比较校正",
        }

    original = np.array(p_values)

    if method == "bonferroni":
        adjusted = np.minimum(original * n, 1.0)
        method_name = "Bonferroni"

    elif method == "bh":
        # Benjamini-Hochberg procedure
        order = np.argsort(original)
        ranks = np.empty_like(order, dtype=float)
        ranks[order] = np.arange(1, n + 1)
        adjusted = original * n / ranks
        # 确保单调性：从最大 p 值回推
        for i in range(n - 2, -1, -1):
            idx = order[i]
            idx_next = order[i + 1]
            adjusted[idx] = min(adjusted[idx], adjusted[idx_next])
        adjusted = np.minimum(adjusted, 1.0)
        method_name = "Benjamini-Hochberg"

    elif method == "holm":
        # Holm-Bonferroni (step-down)
        order = np.argsort(original)
        adjusted = np.empty(n, dtype=float)
        for i, rank_idx in enumerate(order):
            # Holm: p_i * (n - i)
            multiplier = n - i
            adjusted[rank_idx] = min(original[rank_idx] * multiplier, 1.0)
        # 确保单调性
        for i in range(n - 2, -1, -1):
            idx = order[i]
            idx_next = order[i + 1]
            adjusted[idx] = max(adjusted[idx], adjusted[idx_next])
        adjusted = np.minimum(adjusted, 1.0)
        method_name = "Holm-Bonferroni"

    else:
        raise ValueError(f"不支持的校正方法: {method}，可选: bonferroni, bh, holm")

    significant = adjusted < alpha
    n_significant = int(np.sum(significant))

    return {
        "test": "multiple_comparison_correction",
        "method": method,
        "method_name": method_name,
        "n_tests": n,
        "alpha": alpha,
        "original_p": [round(float(p), 6) for p in original],
        "adjusted_p": [round(float(p), 6) for p in adjusted],
        "significant": [bool(s) for s in significant],
        "n_significant": n_significant,
        "n_original_significant": int(np.sum(original < alpha)),
        "correction_note": (
            f"{method_name} 校正: {int(np.sum(original < alpha))} → {n_significant} 个显著"
        ),
    }


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


def interaction_analysis(
    df: pd.DataFrame,
    target: str,
    feature1: str,
    feature2: str,
    *,
    add_main_effects: bool = True,
) -> dict[str, Any]:
    """
    交互效应分析：检验两个变量是否存在交互作用

    Args:
        df: 数据
        target: 因变量
        feature1: 第一个自变量
        feature2: 第二个自变量
        add_main_effects: 是否包含主效应

    Returns:
        交互分析结果
    """
    import statsmodels.api as sm

    if target not in df.columns:
        return _insufficient_data(f"因变量 '{target}' 不在数据中")
    for feat in (feature1, feature2):
        if feat not in df.columns:
            return _insufficient_data(f"自变量 '{feat}' 不在数据中")

    valid = df[[target, feature1, feature2]].dropna()
    if len(valid) < 10:
        return _insufficient_data(
            f"交互分析需要至少 10 行有效数据 (实际: {len(valid)})"
        )

    # 标准化连续变量（使交互项系数更可解释）
    y = valid[target].values

    # 构建特征矩阵
    features_list = []
    feature_names = []

    if add_main_effects:
        features_list.append(valid[feature1].values)
        feature_names.append(feature1)
        features_list.append(valid[feature2].values)
        feature_names.append(feature2)

    # 交互项
    interaction_term = valid[feature1].values * valid[feature2].values
    features_list.append(interaction_term)
    feature_names.append(f"{feature1}×{feature2}")

    X = np.column_stack(features_list)
    X = sm.add_constant(X)

    try:
        model = sm.OLS(y, X).fit()
    except Exception as e:
        return _insufficient_data(f"交互模型拟合失败: {e}")

    # 提取交互项的系数和 p 值（最后一项）
    interaction_idx = len(feature_names)  # +1 因为 const
    interaction_coef = float(model.params[interaction_idx])
    interaction_p = float(model.pvalues[interaction_idx])
    interaction_ci = model.conf_int()[interaction_idx].tolist()

    # 比较有交互项和无交互项的模型
    if add_main_effects:
        X_main = np.column_stack([
            valid[feature1].values,
            valid[feature2].values,
        ])
        X_main = sm.add_constant(X_main)
        model_main = sm.OLS(y, X_main).fit()

        r2_diff = float(model.rsquared - model_main.rsquared)
        # F 检验比较两个模型
        try:
            f_test = model.compare_f_test(model_main)
            f_stat = float(f_test[0])
            f_p = float(f_test[1])
        except Exception as e:
            logger.debug("F-test comparison skipped: %s", e)
            f_stat = None
            f_p = None
    else:
        r2_diff = None
        f_stat = None
        f_p = None

    sig = "significant" if interaction_p < 0.05 else "not_significant"

    # 效应量：交互项的偏 η²
    if model.f_pvalue is not None:
        # 近似：用交互项的 t 值计算
        t_val = float(model.tvalues[interaction_idx])
        partial_eta_sq = t_val ** 2 / (t_val ** 2 + model.df_resid)
    else:
        partial_eta_sq = None

    return {
        "test": "interaction_analysis",
        "feature1": feature1,
        "feature2": feature2,
        "interaction_term": f"{feature1}×{feature2}",
        "coefficient": round(interaction_coef, 6),
        "p_value": round(interaction_p, 6),
        "significance": sig,
        "confidence_interval": [round(float(v), 6) for v in interaction_ci],
        "effect_size": round(float(partial_eta_sq), 4) if partial_eta_sq is not None else None,
        "effect_type": "partial_eta_squared",
        "r_squared_with_interaction": round(float(model.rsquared), 4),
        "r_squared_improvement": round(r2_diff, 4) if r2_diff is not None else None,
        "f_test_statistic": round(f_stat, 4) if f_stat is not None else None,
        "f_test_p_value": round(f_p, 6) if f_p is not None else None,
        "n_observations": len(valid),
        "interpretation": (
            f"{'存在' if sig == 'significant' else '不存在'}显著交互效应: "
            f"{feature1} 对 {target} 的影响{'受' if sig == 'significant' else '不受'} "
            f"{feature2} 的调节"
        ),
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
        _, p_norm1 = stats.shapiro(g1[:_config.shapiro_sample_limit] if len(g1) > 5000 else g1)
        assumptions["normality_group1"] = {"p_value": float(p_norm1), "met": p_norm1 > _config.p_value_threshold}
    if len(g2) <= 5000:
        _, p_norm2 = stats.shapiro(g2[:_config.shapiro_sample_limit] if len(g2) > 5000 else g2)
        assumptions["normality_group2"] = {"p_value": float(p_norm2), "met": p_norm2 > _config.p_value_threshold}

    # 方差齐性 (Levene's test)
    _, p_levene = stats.levene(g1, g2)
    assumptions["equal_variance"] = {"p_value": float(p_levene), "met": p_levene > _config.p_value_threshold}

    return assumptions


def _regression_diagnostics(
    model: Any,
    df: pd.DataFrame,
    target: str,
    features: list[str],
) -> dict[str, Any]:
    """回归诊断"""
    import statsmodels.api as sm
    from scipy import stats

    diagnostics: dict[str, Any] = {}

    # 残差
    residuals = model.resid

    # 正态性
    _, p_norm = stats.shapiro(residuals[:_config.shapiro_sample_limit] if len(residuals) > 5000 else residuals)
    diagnostics["residual_normality"] = {
        "test": "shapiro_wilk",
        "p_value": float(p_norm),
        "met": p_norm > _config.p_value_threshold,
    }

    # 异方差 (Breusch-Pagan)
    try:
        bp_test = sm.stats.het_breuschpagan(residuals, model.model.exog)
        diagnostics["heteroscedasticity"] = {
            "test": "breusch_pagan",
            "statistic": float(bp_test[0]),
            "p_value": float(bp_test[1]),
            "met": bp_test[1] > _config.p_value_threshold,
        }
    except Exception as e:
        logger.debug("Breusch-Pagan test skipped: %s", e)
    if len(features) > 1:
        try:
            from statsmodels.stats.outliers_influence import variance_inflation_factor

            X = df[features].dropna()
            vif_data = {}
            for i, col in enumerate(features):
                vif_data[col] = float(variance_inflation_factor(X.values, i))
            diagnostics["vif"] = vif_data
        except Exception as e:
            logger.debug("VIF calculation skipped: %s", e)

    # Durbin-Watson (自相关)
    from statsmodels.stats.stattools import durbin_watson

    dw = durbin_watson(residuals)
    diagnostics["durbin_watson"] = {
        "statistic": float(dw),
        "interpretation": "no_autocorrelation" if 1.5 < dw < 2.5 else "potential_autocorrelation",
    }

    return diagnostics
