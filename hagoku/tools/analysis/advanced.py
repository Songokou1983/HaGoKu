from __future__ import annotations
# Auto-split from analysis.py
import logging
import numpy as np
from typing import Any
from scipy import stats as _scipy_stats
from .config import _insufficient_data, _config

logger = logging.getLogger(__name__)

from sklearn.model_selection import KFold
from sklearn.linear_model import LinearRegression

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



