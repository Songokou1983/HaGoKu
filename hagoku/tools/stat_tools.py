"""统计诊断与功效工具 — CO-T05～T11

注册：
  CO-T05 check_test_assumptions    → analysis.diagnostics.check_test_assumptions
  CO-T06 assess_statistical_power  → power_analysis (统一入口)
  CO-T07 required_sample_size      → power_analysis (统一入口)
  CO-T09 correct_multiple_comparisons → analysis.advanced.multiple_comparison_correction
  CO-T10 diagnose_regression       → diagnostics.diagnose_regression
  CO-T11 run_statistical_test      → 重构委托 analysis/* 模块
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from hagoku.tools.registry import Tool, agent_tools


# ═══════════════════════════════════════════════════════════════════
# CO-T05: check_test_assumptions
# ═══════════════════════════════════════════════════════════════════

def _handle_check_test_assumptions(args: dict, _ctx: dict, df: pd.DataFrame | None) -> dict:
    test_type = str(args.get("test_type", "")).strip()
    if not test_type or df is None:
        return {"error": "test_type 必填，且需要 DataFrame"}

    from hagoku.tools.analysis.diagnostics import check_test_assumptions

    kwargs: dict[str, Any] = {}
    for k in ("group_col", "target", "features", "col1", "col2", "method"):
        if k in args and args[k] is not None:
            kwargs[k] = args[k]
    try:
        return check_test_assumptions(df, test_type, **kwargs)
    except Exception as e:
        return {"error": str(e)}


agent_tools.register(Tool(
    name="check_test_assumptions",
    description=(
        "检验前假设检查：根据 test_type 验证正态性、方差齐性、样本量等前提条件。"
        "返回各项假设的检查结果 (met: true/false)、warnings 和替代建议。"
        "test_type 可选: ttest / anova / regression / correlation / chi_square。"
        "ttest 需传 group_col + target；anova 需传 group_col + target；"
        "regression 需传 target + features；correlation 需传 col1 + col2 + method；"
        "chi_square 需传 col1 + col2。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "test_type": {
                "type": "string",
                "enum": ["ttest", "anova", "regression", "correlation", "chi_square"],
                "description": "检验类型",
            },
            "group_col": {"type": "string", "description": "分组列名（ttest/anova）"},
            "target": {"type": "string", "description": "目标变量列名"},
            "features": {"type": "array", "items": {"type": "string"}, "description": "自变量列表（regression）"},
            "col1": {"type": "string", "description": "变量1（correlation/chi_square）"},
            "col2": {"type": "string", "description": "变量2（correlation/chi_square）"},
            "method": {"type": "string", "description": "相关方法: pearson / spearman"},
        },
        "required": ["test_type"],
    },
    handler=_handle_check_test_assumptions,
    phase_tag=["跑统计"],
))


# ═══════════════════════════════════════════════════════════════════
# CO-T06: assess_statistical_power — 统一功效入口
# ═══════════════════════════════════════════════════════════════════

def _handle_assess_statistical_power(args: dict, _ctx: dict, _df: pd.DataFrame | None) -> dict:
    mode = str(args.get("mode", "") or args.get("test_type", "")).strip()
    n = args.get("n")
    effect_size = float(args.get("effect_size", 0.5))
    alpha = float(args.get("alpha", 0.05))

    from hagoku.tools.power_analysis import power_ttest, power_anova, power_correlation, power_regression

    try:
        if mode == "ttest":
            n1 = int(args.get("n1", n or 0))
            n2 = int(args.get("n2", n1))
            paired = bool(args.get("paired", False))
            return power_ttest(n1, n2, effect_size, alpha, paired=paired)
        elif mode == "anova":
            n_per_group = int(args.get("n_per_group", n or 0))
            n_groups = int(args.get("n_groups", 2))
            return power_anova(n_per_group, n_groups, effect_size, alpha)
        elif mode == "correlation":
            n_val = int(args.get("n", n or 0))
            method = str(args.get("method", "pearson"))
            return power_correlation(n_val, effect_size, alpha, method=method)
        elif mode == "regression":
            n_val = int(args.get("n", n or 0))
            n_predictors = int(args.get("n_predictors", 1))
            return power_regression(n_val, n_predictors, effect_size, alpha)
        else:
            return {"error": f"未知 mode: {mode}，可选: ttest / anova / correlation / regression"}
    except Exception as e:
        return {"error": str(e)}




# ═══════════════════════════════════════════════════════════════════
# CO-T07: required_sample_size — 统一样本量入口
# ═══════════════════════════════════════════════════════════════════

def _handle_required_sample_size(args: dict, _ctx: dict, _df: pd.DataFrame | None) -> dict:
    mode = str(args.get("mode", "") or args.get("test_type", "")).strip()
    effect_size = float(args.get("effect_size", 0.5))
    power = float(args.get("power", 0.8))
    alpha = float(args.get("alpha", 0.05))

    from hagoku.tools.power_analysis import required_n_ttest, required_n_anova, required_n_correlation, required_n_regression

    try:
        if mode == "ttest":
            paired = bool(args.get("paired", False))
            ratio = float(args.get("ratio", 1.0))
            return required_n_ttest(effect_size, power, alpha, paired=paired, ratio=ratio)
        elif mode == "anova":
            n_groups = int(args.get("n_groups", 2))
            return required_n_anova(effect_size, n_groups, power, alpha)
        elif mode == "correlation":
            return required_n_correlation(effect_size, power, alpha)
        elif mode == "regression":
            n_predictors = int(args.get("n_predictors", 1))
            return required_n_regression(n_predictors, effect_size, power, alpha)
        else:
            return {"error": f"未知 mode: {mode}，可选: ttest / anova / correlation / regression"}
    except Exception as e:
        return {"error": str(e)}





# ═══════════════════════════════════════════════════════════════════
# CO-T09: correct_multiple_comparisons
# ═══════════════════════════════════════════════════════════════════

def _handle_correct_multiple_comparisons(args: dict, _ctx: dict, _df: pd.DataFrame | None) -> dict:
    from hagoku.tools.analysis.advanced import multiple_comparison_correction

    p_values = list(args.get("p_values", []) or [])
    method = str(args.get("method", "bh"))
    alpha = float(args.get("alpha", 0.05))

    if not p_values:
        return {"error": "p_values 不能为空"}

    try:
        return multiple_comparison_correction(
            p_values=[float(p) for p in p_values],
            method=method,
            alpha=alpha,
        )
    except Exception as e:
        return {"error": str(e)}


agent_tools.register(Tool(
    name="correct_multiple_comparisons",
    description=(
        "多重比较校正：控制多次检验的假阳性累积。"
        "method 可选: bonferroni（最保守）/ bh（Benjamini-Hochberg，探索推荐）/ holm。"
        "传入原始 p 值列表，返回校正后 p 值和显著性判断。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "p_values": {"type": "array", "items": {"type": "number"}, "description": "原始 p 值列表"},
            "method": {
                "type": "string",
                "enum": ["bonferroni", "bh", "holm"],
                "description": "校正方法: bonferroni/bh(推荐)/holm",
            },
            "alpha": {"type": "number", "description": "显著性水平，默认 0.05"},
        },
        "required": ["p_values"],
    },
    handler=_handle_correct_multiple_comparisons,
    phase_tag=["跑统计"],
))


# ═══════════════════════════════════════════════════════════════════
# CO-T10: diagnose_regression
# ═══════════════════════════════════════════════════════════════════

def _handle_diagnose_regression(args: dict, _ctx: dict, df: pd.DataFrame | None) -> dict:
    """诊断回归模型 — 需要先跑 run_statistical_test (linear_regression) 拿到模型引用。

    由于 diagnose_regression 需要 statsmodels 模型对象，而工具调用上下文通常只有 DataFrame，
    这里通过 ctx 中的 _last_model 传递模型对象（由 run_statistical_test 保存）。
    如果没有模型对象，则返回错误提示。
    """
    model = _ctx.get("_last_regression_model")
    target = str(args.get("target", ""))
    features = list(args.get("features", []) or [])

    if model is None:
        return {
            "error": (
                "诊断需要先执行 run_statistical_test(test_type='linear_regression', ...)，"
                "系统会自动保存模型用于诊断。请先跑回归分析再调此工具。"
            ),
        }

    if df is None or not target or not features:
        return {"error": "target 和 features 必填，且需要 DataFrame"}

    from hagoku.tools.diagnostics import diagnose_regression

    try:
        result = diagnose_regression(model, df, target, features)
        return result
    except Exception as e:
        return {"error": str(e)}




# ═══════════════════════════════════════════════════════════════════
# CO-T11: run_statistical_test — 重构委托 analysis/* 模块
# ═══════════════════════════════════════════════════════════════════

def _handle_run_statistical_test(args: dict, ctx: dict, df: pd.DataFrame | None) -> dict:
    """执行统计检验 — 委托 hagoku.tools.analysis.* 模块。

    返回统一结构：{test, statistic, p_value, effect_size, effect_type, confidence_interval}
    """
    test_type = str(args.get("test_type", "")).strip()
    columns: list[str] = list(args.get("columns") or [])
    params: dict = args.get("params", {}) or {}

    if not test_type or not columns or df is None:
        return {"error": "test_type 和 columns 必填，且需要 DataFrame"}

    # 验证列存在
    missing = [c for c in columns if c not in df.columns]
    if missing:
        return {"error": f"列不存在: {missing}"}

    try:
        if test_type == "ttest" and len(columns) >= 2:
            from hagoku.tools.analysis.comparison import ttest as _ttest
            paired = bool(params.get("paired", False))
            g1 = df[columns[0]].dropna().astype(float)
            g2 = df[columns[1]].dropna().astype(float)
            return _ttest(g1, g2, paired=paired)

        elif test_type == "anova":
            from hagoku.tools.analysis.comparison import anova as _anova
            dv = columns[0]
            between = params.get("group_col") or (columns[1] if len(columns) >= 2 else None)
            if between is None:
                # 兼容旧行为：每个 column 作为独立组
                from scipy import stats as _scipy_stats
                groups = [df[c].dropna().astype(float) for c in columns if c in df.columns]
                if len(groups) < 2:
                    return {"error": "ANOVA 需要至少 2 组数据"}
                stat, p = _scipy_stats.f_oneway(*groups)
                return {
                    "test": "anova",
                    "statistic": float(stat),
                    "p_value": float(p),
                    "effect_size": None,
                    "effect_type": None,
                    "note": "未提供 group_col，使用列名作为独立组（旧行为）。建议传 params.group_col 以获取效应量和置信区间。",
                }
            return _anova(df, dv=dv, between=between)

        elif test_type == "pearson_r" and len(columns) >= 2:
            from hagoku.tools.analysis.correlation import correlation as _corr
            return _corr(df, col1=columns[0], col2=columns[1], method="pearson")

        elif test_type == "spearman_r" and len(columns) >= 2:
            from hagoku.tools.analysis.correlation import correlation as _corr
            return _corr(df, col1=columns[0], col2=columns[1], method="spearman")

        elif test_type == "chi2" and len(columns) >= 2:
            from hagoku.tools.analysis.comparison import chi_square as _chi2
            return _chi2(df, col1=columns[0], col2=columns[1])

        elif test_type == "linear_regression":
            from hagoku.tools.analysis.regression import regression as _reg
            target = columns[0]
            features = columns[1:] if len(columns) > 1 else []
            if not features:
                return {"error": "线性回归需要至少 2 列 (target + 至少1个feature)"}
            result = _reg(df, target=target, features=features)
            # 保存模型引用供 diagnose_regression 使用
            if "error" not in result and result.get("r_squared") is not None:
                try:
                    import statsmodels.api as _sm
                    y = df[target]
                    X = df[features]
                    X = _sm.add_constant(X)
                    model = _sm.OLS(y, X).fit()
                    ctx["_last_regression_model"] = model
                except Exception:
                    import logging
                    logging.getLogger("hagoku.tools").warning("OLS 回归失败", exc_info=True)
            # 统一返回字段
            if "effect_size" not in result:
                result["effect_size"] = None
            if "effect_type" not in result:
                result["effect_type"] = None
            if "confidence_interval" not in result:
                result["confidence_interval"] = result.get("confidence_intervals")
            return result

        elif test_type == "trend_decomposition" and columns:
            s = df[columns[0]].dropna().astype(float)
            w = min(7, max(1, len(s) // 4))
            trend = s.rolling(window=w, center=True).mean()
            return {
                "test": "trend_decomposition",
                "column": columns[0],
                "statistic": float(trend.mean()) if not trend.isna().all() else None,
                "p_value": None,
                "effect_size": None,
                "effect_type": None,
                "trend_mean": float(trend.mean()) if not trend.isna().all() else None,
                "detrended_std": float((s - trend).std()) if not trend.isna().all() else None,
            }

        return {"error": f"不支持的检验类型或参数不足: {test_type}"}
    except Exception as e:
        return {"error": str(e)}


agent_tools.register(Tool(
    name="run_statistical_test",
    description=(
        "执行统计检验，委托专业分析模块。返回统一结构含 p_value / effect_size / effect_type / confidence_interval。"
        "可用 test_type: ttest / anova / chi2 / pearson_r / spearman_r / linear_regression / trend_decomposition。"
        "ttest: columns = [组1列, 组2列]，可选 params.paired=true 做配对检验。"
        "anova: columns = [因变量列, 分组列]，推荐在 params.group_col 里指定分组列以获取效应量和 CI。"
        "pearson_r / spearman_r: columns = [变量1, 变量2]。"
        "chi2: columns = [变量1, 变量2]（两分类变量）。"
        "linear_regression: columns = [因变量, 自变量1, 自变量2, ...]。"
        "trend_decomposition: columns = [数值列]，用滚动平均做趋势分解。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "test_type": {
                "type": "string",
                "enum": ["ttest", "anova", "chi2", "pearson_r", "spearman_r", "linear_regression", "trend_decomposition"],
                "description": "检验类型",
            },
            "columns": {"type": "array", "items": {"type": "string"}, "description": "列名列表（第1个通常是目标变量或组1）"},
            "params": {"type": "object", "description": "额外参数: paired(ttest), group_col(anova)"},
        },
        "required": ["test_type", "columns"],
    },
    handler=_handle_run_statistical_test,
    phase_tag=["跑统计"],
))

# ── CO-T13: assess_statistical_power ────────────────────────────────
agent_tools.register(Tool(
    name="assess_statistical_power",
    description="评估已完成检验的统计功效。用于解读不显著结果时应先调用此工具。",
    parameters={
        "type": "object",
        "properties": {
            "test_type": {"type": "string", "description": "检验类型"},
            "n": {"type": "integer", "description": "样本量"},
            "effect_size": {"type": "number", "description": "效应量（如 Cohen's d）"},
            "alpha": {"type": "number", "description": "显著性水平，默认 0.05"},
        },
        "required": ["test_type", "n"],
    },
    handler=_handle_assess_statistical_power,
    phase_tag=["跑统计"],
))

# ── CO-T14: required_sample_size ────────────────────────────────────
agent_tools.register(Tool(
    name="required_sample_size",
    description="估算达到目标功效所需的样本量。设计实验或判断已有数据是否足够时使用。",
    parameters={
        "type": "object",
        "properties": {
            "test_type": {"type": "string", "description": "检验类型"},
            "effect_size": {"type": "number", "description": "期望检测的最小效应量"},
            "power": {"type": "number", "description": "目标功效，默认 0.8"},
            "alpha": {"type": "number", "description": "显著性水平，默认 0.05"},
        },
        "required": ["test_type", "effect_size"],
    },
    handler=_handle_required_sample_size,
    phase_tag=["跑统计"],
))

# ── CO-T15: diagnose_regression ─────────────────────────────────────
agent_tools.register(Tool(
    name="diagnose_regression",
    description="诊断线性回归模型：残差分析、多重共线性(VIF)、影响点。需先执行 run_statistical_test(test_type='linear_regression')。",
    parameters={
        "type": "object",
        "properties": {
            "target": {"type": "string", "description": "因变量列名"},
            "features": {"type": "array", "items": {"type": "string"}, "description": "自变量列名列表"},
        },
        "required": ["target", "features"],
    },
    handler=_handle_diagnose_regression,
    phase_tag=["跑统计"],
))
