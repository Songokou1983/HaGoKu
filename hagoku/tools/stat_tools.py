"""统计工具 — run_statistical_test
"""
from __future__ import annotations
from typing import Any
from hagoku.tools.registry import Tool, agent_tools


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
