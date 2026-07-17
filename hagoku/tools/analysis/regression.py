from __future__ import annotations
# Auto-split from analysis.py
import logging
import numpy as np
from typing import Any
from scipy import stats as _scipy_stats
from .config import _insufficient_data, _config

logger = logging.getLogger(__name__)

import statsmodels.api as _sm
import pandas as _pd

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

