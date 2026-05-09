"""HaGoKu 功效分析 — 告诉用户"你的数据能检测到多大的效应"

功效分析回答三个核心问题：
1. 分析前：我需要多少数据才能检测到预期效应？
2. 分析前：这个数据量能检测到多大的效应？
3. 分析后：结果不显著，是因为真的没效应，还是数据不够？

功效 (power) = 在效应真实存在时，正确拒绝原假设的概率
典型目标：power ≥ 0.80（80% 的把握检测到真实存在的效应）
"""

from __future__ import annotations

from typing import Any

import numpy as np


def _insufficient_data(msg: str) -> dict[str, Any]:
    """返回数据不足的标准错误结果"""
    return {"error": "insufficient_data", "message": msg}


def _require_power_deps() -> dict[str, Any]:
    """检查功效分析依赖，返回可用库或报错信息"""
    try:
        from scipy import stats
        return {"scipy": stats}
    except ImportError:
        return {"scipy": None}


# ── 效应量参考标准（Cohen's conventions）────────────────────


EFFECT_SIZE_REFERENCES: dict[str, dict[str, Any]] = {
    # t 检验 / 相关
    "cohen_d": {
        "small": 0.2,
        "medium": 0.5,
        "large": 0.8,
        "interpretation": {
            "small": "小效应：需要大样本才能可靠检测",
            "medium": "中等效应：常规样本量可检测",
            "large": "大效应：小样本也能检测到",
        },
    },
    # ANOVA / η²
    "eta_squared": {
        "small": 0.01,
        "medium": 0.06,
        "large": 0.14,
        "interpretation": {
            "small": "小效应：方差解释比例很低",
            "medium": "中等效应：解释了部分方差",
            "large": "大效应：解释了相当比例的方差",
        },
    },
    # 相关 / r
    "pearson_r": {
        "small": 0.1,
        "medium": 0.3,
        "large": 0.5,
        "interpretation": {
            "small": "弱相关：两变量关联很弱",
            "medium": "中等相关：存在可见关联",
            "large": "强相关：两变量高度关联",
        },
    },
    # Cohen's f² (回归)
    "f_squared": {
        "small": 0.02,
        "medium": 0.15,
        "large": 0.35,
        "interpretation": {
            "small": "小效应：自变量解释力有限",
            "medium": "中等效应：有实际意义",
            "large": "大效应：强预测力",
        },
    },
}


def interpret_effect_size(effect_size: float, effect_type: str) -> dict[str, Any]:
    """
    结构化解读效应量大小

    Args:
        effect_size: 效应量值
        effect_type: 效应量类型 (cohen_d / eta_squared / pearson_r / f_squared)

    Returns:
        包含大小标签、参考标准和解读
    """
    ref = EFFECT_SIZE_REFERENCES.get(effect_type, EFFECT_SIZE_REFERENCES["cohen_d"])
    es = abs(effect_size)

    if es < ref["small"]:
        magnitude = "negligible"
        label = "可忽略"
    elif es < ref["medium"]:
        magnitude = "small"
        label = "小"
    elif es < ref["large"]:
        magnitude = "medium"
        label = "中等"
    else:
        magnitude = "large"
        label = "大"

    return {
        "effect_size": effect_size,
        "effect_type": effect_type,
        "magnitude": magnitude,
        "label": label,
        "reference_standard": ref,
        "interpretation": ref["interpretation"].get(magnitude, ""),
        "user_message": (
            f"效应量为 {effect_size:.3f}，属于{magnitude}效应"
            f"（{ref['interpretation'].get(magnitude, '')}）"
        ),
    }


# ── t 检验功效分析 ─────────────────────────────────────────


def power_ttest(
    n1: int,
    n2: int | None = None,
    effect_size: float = 0.5,
    alpha: float = 0.05,
    *,
    paired: bool = False,
) -> dict[str, Any]:
    """
    计算 t 检验的功效

    Args:
        n1: 第一组样本量（或配对样本总数）
        n2: 第二组样本量（配对时为 None）
        effect_size: Cohen's d（默认 0.5 = 中等效应）
        alpha: 显著性水平（默认 0.05）
        paired: 是否配对 t 检验

    Returns:
        功效分析结果
    """
    deps = _require_power_deps()
    if deps["scipy"] is None:
        return _insufficient_data("功效分析需要 scipy: pip install scipy")

    stats = deps["scipy"]
    n1 = int(n1)
    if n1 < 2:
        return _insufficient_data(f"样本量 n1={n1} 不足（至少需要 2）")

    if paired:
        n2 = n1
    else:
        n2 = int(n2) if n2 else n1
        if n2 < 2:
            return _insufficient_data(f"样本量 n2={n2} 不足（至少需要 2）")

    try:
        # 计算自由度
        if paired:
            df = n1 - 1
        else:
            df = n1 + n2 - 2

        # t 临界值
        t_crit = stats.t.ppf(1 - alpha / 2, df)

        # 非中心参数
        if paired:
            # 配对: ncp = d * sqrt(n)
            ncp = effect_size * np.sqrt(n1)
        else:
            # 两独立: ncp = d * sqrt(n1*n2/(n1+n2))
            ncp = effect_size * np.sqrt(n1 * n2 / (n1 + n2))

        # 功效 = P(t > t_crit | ncp)
        power = 1 - stats.nct.cdf(t_crit, df, ncp) + stats.nct.cdf(-t_crit, df, ncp)

        return _build_ttest_power_result(
            n1=n1, n2=n2, effect_size=effect_size, alpha=alpha,
            power=float(power), df=df, paired=paired,
        )
    except Exception as e:
        return _insufficient_data(f"功效计算失败: {e}")


def required_n_ttest(
    effect_size: float,
    power: float = 0.8,
    alpha: float = 0.05,
    *,
    paired: bool = False,
    ratio: float = 1.0,
) -> dict[str, Any]:
    """
    计算达到目标功效所需的样本量

    Args:
        effect_size: 预期 Cohen's d
        power: 目标功效（默认 0.80）
        alpha: 显著性水平
        paired: 是否配对
        ratio: n2/n1 比例（独立样本时）

    Returns:
        所需样本量
    """
    deps = _require_power_deps()
    if deps["scipy"] is None:
        return _insufficient_data("功效分析需要 scipy")

    stats = deps["scipy"]
    if not (0 < power < 1):
        return _insufficient_data(f"power={power} 无效，需在 (0,1) 范围内")
    if effect_size <= 0:
        return _insufficient_data(f"effect_size={effect_size} 无效，需大于 0")

    try:
        if paired:
            # 配对: n = (z_alpha + z_beta)² / d²
            z_alpha = stats.norm.ppf(1 - alpha / 2)
            z_beta = stats.norm.ppf(power)
            n = int(np.ceil(((z_alpha + z_beta) / effect_size) ** 2))
            return {
                "test": "ttest_paired",
                "required_n": n,
                "per_group": n,
                "effect_size": effect_size,
                "power": power,
                "alpha": alpha,
                "user_message": (
                    f"配对设计检测 d={effect_size} 效应，"
                    f"power={power:.0%} 时需要 n={n} 对样本"
                ),
            }
        else:
            # 两独立样本
            z_alpha = stats.norm.ppf(1 - alpha / 2)
            z_beta = stats.norm.ppf(power)
            n1 = int(np.ceil(2 * ((z_alpha + z_beta) / effect_size) ** 2))
            n2 = int(np.ceil(ratio * n1))
            return {
                "test": "ttest_independent",
                "required_n1": n1,
                "required_n2": n2,
                "total": n1 + n2,
                "effect_size": effect_size,
                "power": power,
                "alpha": alpha,
                "user_message": (
                    f"独立样本检测 d={effect_size} 效应，"
                    f"power={power:.0%} 时需要 n1={n1}, n2={n2}（共 {n1+n2} 个样本）"
                ),
            }
    except Exception as e:
        return _insufficient_data(f"样本量计算失败: {e}")


def _build_ttest_power_result(
    n1: int, n2: int, effect_size: float, alpha: float,
    power: float, df: float, paired: bool,
) -> dict[str, Any]:
    """构建 t 检验功效分析结果"""
    power_level = "低" if power < 0.5 else ("中" if power < 0.8 else "充足")
    action = ""
    if power < 0.5:
        action = "数据严重不足，建议增加样本量"
    elif power < 0.8:
        action = "功效偏低，建议增加样本量以提高检测力"
    else:
        action = "功效充足，可以进行可靠的统计分析"

    es_interp = interpret_effect_size(effect_size, "cohen_d")

    return {
        "test": "ttest",
        "paired": paired,
        "n1": n1,
        "n2": n2,
        "effect_size": effect_size,
        "alpha": alpha,
        "power": float(power),
        "power_level": power_level,
        "df": int(df),
        "effect_interpretation": es_interp,
        "action": action,
        "user_message": (
            f"当前 n={n1 + (n2 - n1 if paired else n2)} 样本量，"
            f"对 d={effect_size}（{es_interp['label']}效应）的检测功效为 {power:.1%}（{power_level}）。"
            f"{action}"
        ),
    }


# ── ANOVA 功效分析 ──────────────────────────────────────────


def power_anova(
    n_per_group: int,
    n_groups: int,
    effect_size: float = 0.25,
    alpha: float = 0.05,
) -> dict[str, Any]:
    """
    计算单因素 ANOVA 的功效

    Args:
        n_per_group: 每组样本量
        n_groups: 组数
        effect_size: Cohen's f（默认 0.25 = 中等效应）
        alpha: 显著性水平

    Returns:
        功效分析结果
    """
    deps = _require_power_deps()
    if deps["scipy"] is None:
        return _insufficient_data("功效分析需要 scipy")

    stats = deps["scipy"]
    if n_per_group < 2:
        return _insufficient_data(f"每组样本量 n={n_per_group} 不足（至少需要 2）")
    if n_groups < 2:
        return _insufficient_data(f"组数 n_groups={n_groups} 不足（至少需要 2）")

    try:
        # 非中心 F 分布参数
        df_between = n_groups - 1
        df_within = n_groups * (n_per_group - 1)
        ncp = n_per_group * n_groups * effect_size ** 2

        # F 临界值
        f_crit = stats.f.ppf(1 - alpha, df_between, df_within)

        # 功效
        power = 1 - stats.ncf.cdf(f_crit, df_between, df_within, ncp)

        es_interp = interpret_effect_size(effect_size, "eta_squared")

        return {
            "test": "anova",
            "n_per_group": n_per_group,
            "n_groups": n_groups,
            "total_n": n_per_group * n_groups,
            "effect_size": effect_size,
            "effect_type": "cohen_f",
            "alpha": alpha,
            "power": float(power),
            "df_between": df_between,
            "df_within": df_within,
            "effect_interpretation": es_interp,
            "user_message": (
                f"{n_groups} 组，每组 n={n_per_group}，共 {n_per_group*n_groups} 个样本，"
                f"对 f={effect_size}（{es_interp['label']}效应）检测功效为 {power:.1%}"
            ),
        }
    except Exception as e:
        return _insufficient_data(f"功效计算失败: {e}")


def required_n_anova(
    effect_size: float,
    n_groups: int,
    power: float = 0.8,
    alpha: float = 0.05,
) -> dict[str, Any]:
    """
    计算 ANOVA 达到目标功效所需的每组样本量

    Args:
        effect_size: Cohen's f
        n_groups: 组数
        power: 目标功效
        alpha: 显著性水平

    Returns:
        所需样本量
    """
    deps = _require_power_deps()
    if deps["scipy"] is None:
        return _insufficient_data("功效分析需要 scipy")

    stats = deps["scipy"]
    if not (0 < power < 1):
        return _insufficient_data(f"power={power} 无效")
    if effect_size <= 0:
        return _insufficient_data("effect_size 需大于 0")

    try:
        from scipy.optimize import brentq

        def _power_func(n):
            if n < 2:
                return 0.0
            df1 = n_groups - 1
            df2 = n_groups * (n - 1)
            ncp = n * n_groups * effect_size ** 2
            f_crit = stats.f.ppf(1 - alpha, df1, df2)
            return 1 - stats.ncf.cdf(f_crit, df1, df2, ncp)

        n_per_group = int(np.ceil(brentq(lambda n: _power_func(n) - power, 2, 10000)))
        total = n_per_group * n_groups
        return {
            "test": "anova",
            "required_n_per_group": n_per_group,
            "required_n_groups": n_groups,
            "total": total,
            "effect_size": effect_size,
            "effect_type": "cohen_f",
            "power": power,
            "alpha": alpha,
            "user_message": (
                f"{n_groups} 组，检测 f={effect_size} 效应，"
                f"power={power:.0%} 时每组需要 n={n_per_group}，共 {total} 个样本"
            ),
        }
    except Exception:
        # 近似估计
        n_est = int(np.ceil(2 * (1 + 1 / n_groups) * ((1 / effect_size ** 2))))
        return {
            "test": "anova",
            "required_n_per_group": n_est,
            "total": n_est * n_groups,
            "effect_size": effect_size,
            "power": power,
            "alpha": alpha,
            "note": "近似估计",
            "user_message": (
                f"估算：{n_groups} 组检测 f={effect_size} 效应，"
                f"power={power:.0%} 时每组约需 n={n_est}，共约 {n_est*n_groups} 个样本"
            ),
        }


# ── 相关分析功效 ───────────────────────────────────────────


def power_correlation(
    n: int,
    effect_size: float = 0.3,
    alpha: float = 0.05,
    *,
    method: str = "pearson",
) -> dict[str, Any]:
    """
    计算相关系数检验的功效

    Args:
        n: 样本量
        effect_size: 相关系数 r（默认 0.3 = 中等相关）
        alpha: 显著性水平
        method: "pearson" / "spearman"

    Returns:
        功效分析结果
    """
    deps = _require_power_deps()
    if deps["scipy"] is None:
        return _insufficient_data("功效分析需要 scipy")

    stats = deps["scipy"]
    if n < 4:
        return _insufficient_data(f"相关分析需要 n≥4（当前 n={n}）")

    try:
        # Fisher z 变换后计算
        z_r = np.arctanh(effect_size)
        se = 1 / np.sqrt(n - 3)
        z_alpha = stats.norm.ppf(1 - alpha / 2)
        z_beta = (z_r / se) - z_alpha

        power = stats.norm.cdf(z_beta)
        power = float(np.clip(power, 0, 1))

        es_interp = interpret_effect_size(effect_size, "pearson_r")

        return {
            "test": f"correlation_{method}",
            "n": n,
            "effect_size": effect_size,
            "alpha": alpha,
            "power": power,
            "effect_interpretation": es_interp,
            "user_message": (
                f"n={n} 个样本，对 r={effect_size}（{es_interp['label']}相关）"
                f"的检测功效为 {power:.1%}"
            ),
        }
    except Exception as e:
        return _insufficient_data(f"功效计算失败: {e}")


def required_n_correlation(
    effect_size: float,
    power: float = 0.8,
    alpha: float = 0.05,
) -> dict[str, Any]:
    """计算相关分析达到目标功效所需的样本量"""
    deps = _require_power_deps()
    if deps["scipy"] is None:
        return _insufficient_data("功效分析需要 scipy")

    stats = deps["scipy"]
    if effect_size == 0:
        return _insufficient_data("effect_size 不能为 0")
    if not (0 < power < 1):
        return _insufficient_data(f"power={power} 无效")

    try:
        z_r = np.arctanh(effect_size)
        z_alpha = stats.norm.ppf(1 - alpha / 2)
        z_beta = stats.norm.ppf(power)
        n = int(np.ceil(((z_alpha + z_beta) / z_r) ** 2 + 3))
        return {
            "test": "correlation",
            "required_n": n,
            "effect_size": effect_size,
            "power": power,
            "alpha": alpha,
            "user_message": (
                f"检测 r={effect_size} 相关，power={power:.0%} 时需要 n={n} 个样本"
            ),
        }
    except Exception as e:
        return _insufficient_data(f"样本量计算失败: {e}")


# ── 回归分析功效 ───────────────────────────────────────────


def power_regression(
    n: int,
    n_predictors: int,
    effect_size: float = 0.15,
    alpha: float = 0.05,
) -> dict[str, Any]:
    """
    计算多元回归整体检验的功效

    Args:
        n: 样本量
        n_predictors: 自变量数量
        effect_size: Cohen's f²（默认 0.15 = 中等效应）
        alpha: 显著性水平

    Returns:
        功效分析结果
    """
    deps = _require_power_deps()
    if deps["scipy"] is None:
        return _insufficient_data("功效分析需要 scipy")

    stats = deps["scipy"]
    if n < n_predictors + 2:
        return _insufficient_data(
            f"回归需要 n > 自变量数+2（当前 n={n}，自变量={n_predictors}）"
        )

    try:
        # 转换为非中心 F 参数
        df1 = n_predictors
        df2 = n - n_predictors - 1
        ncp = n * effect_size

        f_crit = stats.f.ppf(1 - alpha, df1, df2)
        power = 1 - stats.ncf.cdf(f_crit, df1, df2, ncp)

        es_interp = interpret_effect_size(effect_size, "f_squared")

        return {
            "test": "regression",
            "n": n,
            "n_predictors": n_predictors,
            "effect_size": effect_size,
            "effect_type": "f_squared",
            "alpha": alpha,
            "power": float(power),
            "df1": df1,
            "df2": df2,
            "effect_interpretation": es_interp,
            "user_message": (
                f"n={n} 个样本，{n_predictors} 个自变量，"
                f"对 f²={effect_size}（{es_interp['label']}效应）检测功效为 {power:.1%}"
            ),
        }
    except Exception as e:
        return _insufficient_data(f"功效计算失败: {e}")


def required_n_regression(
    n_predictors: int,
    effect_size: float = 0.15,
    power: float = 0.8,
    alpha: float = 0.05,
) -> dict[str, Any]:
    """计算回归达到目标功效所需的样本量"""
    deps = _require_power_deps()
    if deps["scipy"] is None:
        return _insufficient_data("功效分析需要 scipy")

    stats = deps["scipy"]
    try:
        from scipy.optimize import brentq

        def _power_func(n):
            if n <= n_predictors + 2:
                return 0.0
            df1 = n_predictors
            df2 = int(n - n_predictors - 1)
            ncp = n * effect_size
            f_crit = stats.f.ppf(1 - alpha, df1, df2)
            return 1 - stats.ncf.cdf(f_crit, df1, df2, ncp)

        n = int(np.ceil(brentq(lambda n: _power_func(n) - power, n_predictors + 3, 100000)))
        return {
            "test": "regression",
            "required_n": n,
            "n_predictors": n_predictors,
            "effect_size": effect_size,
            "power": power,
            "alpha": alpha,
            "user_message": (
                f"{n_predictors} 个自变量，检测 f²={effect_size} 效应，"
                f"power={power:.0%} 时需要 n={n} 个样本"
            ),
        }
    except Exception:
        # 简化估算（用于小样本）
        n_est = int(np.ceil((8 + n_predictors) / effect_size))
        return {
            "test": "regression",
            "required_n": n_est,
            "n_predictors": n_predictors,
            "effect_size": effect_size,
            "power": power,
            "note": "近似估计",
            "user_message": (
                f"估算：{n_predictors} 个自变量，检测 f²={effect_size} 效应，"
                f"power={power:.0%} 时约需 n={n_est} 个样本"
            ),
        }


# ── 综合解读：分析结果 + 功效判断 ──────────────────────────


def interpret_nonsignificant_result(
    p_value: float,
    effect_size: float | None,
    effect_type: str,
    n: int,
    alpha: float = 0.05,
) -> dict[str, Any]:
    """
    当结果不显著时，判断是"真的没效应"还是"数据不够"

    这是功效分析最重要的应用场景：
    - p > 0.05 不显著 ≠ 没效应
    - 可能是因为功效不足，检测不到真实存在的效应

    Args:
        p_value: 检验 p 值
        effect_size: 观察到的效应量（如果有）
        effect_type: 效应量类型
        n: 样本量
        alpha: 显著性水平

    Returns:
        解读结论
    """
    deps = _require_power_deps()
    if deps["scipy"] is None:
        return {"error": "scipy not available"}

    is_significant = p_value < alpha

    if is_significant:
        return {
            "verdict": "significant",
            "conclusion": "结果显著，有足够证据支持效应存在",
            "user_message": (
                f"p={p_value:.4f} < {alpha}，结果统计显著。"
                f"结合效应量 {effect_size:.3f}，结论可靠。"
            ),
        }

    # 不显著 → 需要判断是"真没效应"还是"功效不足"
    if effect_size is None:
        return {
            "verdict": "inconclusive",
            "conclusion": "无法判断：效应量未知，无法评估功效",
            "user_message": "p 值不显著，但缺少效应量信息，无法判断是效应不存在还是数据不足",
        }

    # 根据效应量和样本量估算功效
    es_interp = interpret_effect_size(effect_size, effect_type)
    magnitude = es_interp["magnitude"]

    # 估算当前功效（简化版：基于 Cohen's d）
    if effect_type in ("cohen_d", "cohen_d_paired"):
        n1 = n2 = int(n / 2)
        power_result = power_ttest(n1, n2, abs(effect_size), alpha)
    elif effect_type == "eta_squared":
        # 估算 ANOVA 功效（假设 2 组）
        power_result = power_anova(n // 2, 2, abs(effect_size), alpha)
    elif effect_type in ("pearson_r", "spearman_r"):
        power_result = power_correlation(n, abs(effect_size), alpha)
    elif effect_type == "f_squared":
        power_result = power_regression(n, 1, abs(effect_size), alpha)
    else:
        power_result = power_ttest(n // 2, n // 2, abs(effect_size), alpha)

    estimated_power = power_result.get("power", 0.5) if "error" not in power_result else 0.5

    # 判断
    if magnitude in ("negligible", "small") and estimated_power < 0.5:
        verdict = "likely_no_effect"
        conclusion = "效应量很小，即使有效应也需要更大样本才能检测"
        suggestion = (
            f"观察到的效应量 d={effect_size:.3f}（{magnitude}），"
            f"即使效应真实存在，当前样本量（n={n}）也只有 {estimated_power:.0%} 的把握检测到它。"
            f"建议：增加样本量，或接受该效应可能实际意义有限。"
        )
    elif magnitude == "small" and estimated_power < 0.8:
        verdict = "possibly_underpowered"
        conclusion = "可能功效不足，无法确定效应是否存在"
        suggestion = (
            f"效应量 d={effect_size:.3f}（{magnitude}），"
            f"当前样本量检测功效约 {estimated_power:.0%}（低于 80%）。"
            f"建议增加样本后再分析，或谨慎解读为'效应可能存在但不确定'。"
        )
    elif magnitude in ("medium", "large") and estimated_power < 0.5:
        verdict = "likely_no_effect"
        conclusion = "效应量不小但结果不显著，可能是检验本身的问题"
        suggestion = (
            f"效应量 d={effect_size:.3f}（{magnitude}），"
            f"在合理的样本量下应该能检测到。p 值不显著可能由其他因素导致。"
        )
    else:
        verdict = "likely_no_effect"
        conclusion = "效应量小且功效合理，更可能是效应本身不存在"
        suggestion = (
            f"效应量 d={effect_size:.3f}（{magnitude}），"
            f"功效 {estimated_power:.0%}，结果不显著更可能是效应本身很小或不存在。"
        )

    return {
        "verdict": verdict,
        "p_value": p_value,
        "effect_size": effect_size,
        "effect_interpretation": es_interp,
        "n": n,
        "estimated_power": estimated_power,
        "conclusion": conclusion,
        "suggestion": suggestion,
        "user_message": suggestion,
    }


# ── 批量功效评估（用于 Scout 阶段）────────────────────────


def assess_power_for_data(
    n: int,
    effect_size_estimate: float = 0.5,
    test_type: str = "ttest",
    n_groups: int = 2,
    n_predictors: int = 1,
) -> dict[str, Any]:
    """
    给定数据量，快速评估能做哪些分析

    用于 Scout/Orchestrator 阶段，在分析前告诉用户数据够不够

    Args:
        n: 数据总量
        effect_size_estimate: 预估效应量（默认中等）
        test_type: "ttest" / "anova" / "correlation" / "regression"
        n_groups: ANOVA 的组数
        n_predictors: 回归的自变量数

    Returns:
        功效评估报告
    """
    deps = _require_power_deps()
    if deps["scipy"] is None:
        return {"error": "scipy not available"}

    if test_type == "ttest":
        n_per_group = n // 2
        result = power_ttest(n_per_group, n_per_group, effect_size_estimate)
    elif test_type == "anova":
        n_per_group = max(2, n // n_groups)
        result = power_anova(n_per_group, n_groups, effect_size_estimate)
    elif test_type == "correlation":
        result = power_correlation(n, effect_size_estimate)
    elif test_type == "regression":
        result = power_regression(n, n_predictors, effect_size_estimate)
    else:
        return {"error": f"未知检验类型: {test_type}"}

    return result
