"""HaGoKu Studio 结构化输出解析器 — 从 LLM 自由文本中提取统计结论"""

from __future__ import annotations

import re
from typing import Any, Optional


def parse_pvalue(text: str) -> Optional[float]:
    """
    从 LLM 输出文本中提取 p 值。

    匹配模式:
      - "p = 0.042", "p < 0.001", "p ≈ 0.03"
      - "(p=0.042)", "P=0.042", "(p = .042)"
      - "p-value = 0.042"

    返回 float 或 None。
    """
    # 匹配 p[=\s<>≈]*[\d.]+
    pattern = r"""(?ix)
        (?:p|p[\s-]*value)\s*[=<>≈]\s*
        (\d+\.?\d*)
    """
    match = re.search(pattern, text)
    if match:
        return float(match.group(1))
    return None


def parse_effect_size(text: str) -> Optional[float]:
    """
    从 LLM 输出文本中提取效应量。

    匹配模式:
      - "Cohen's d = 0.52", "d = 0.52"
      - "效应量 = 0.52", "effect size = 0.52"
      - "η² = 0.14", "eta-squared = 0.14"

    返回 float 或 None。
    """
    pattern = r"""(?ix)
        (?:cohen'?s?\s*d|效应量|effect\s*size|η²|eta[\s-]*squared)\s*[=：:]\s*
        (\d+\.?\d*)
    """
    match = re.search(pattern, text)
    if match:
        return float(match.group(1))
    return None


def parse_conclusion_count(text: str) -> Optional[int]:
    """
    从 LLM 输出中统计明确结论的数量。

    识别模式：
      - 编号列表："1. ... 2. ..."
      - Markdown 标题 + 结论性动词："### 结论"
      - 统计性陈述："研究发现"、"结果表明"、"conclusion"

    返回结论数（int）或 None。
    """
    count = 0
    # 编号列表
    numbered = re.findall(r"(?:^|\n)\s*\d+\.\s+", text)
    count += len(numbered)
    # 结论性动词
    conclusion_keywords = [
        r"研究.?发现", r"结果.?表明", r"数据.?显示",
        r"结论", r"conclusion", r"we find", r"results show",
    ]
    for kw in conclusion_keywords:
        count += len(re.findall(kw, text, re.IGNORECASE))
    return count if count > 0 else None


def parse_confidence_interval(text: str) -> Optional[tuple[float, float]]:
    """
    从 LLM 输出中提取置信区间。

    匹配模式: "[0.12, 0.89]", "(0.12, 0.89)", "0.12–0.89"

    返回 (lower, upper) 或 None。
    """
    # 方括号/圆括号
    bracket_pattern = r"[\[\(]\s*(\d+\.?\d*)\s*[,，]\s*(\d+\.?\d*)\s*[\]\)]"
    match = re.search(bracket_pattern, text)
    if match:
        return float(match.group(1)), float(match.group(2))
    # 短横线连接
    dash_pattern = r"(\d+\.?\d*)\s*[–—\-]\s*(\d+\.?\d*)"
    match = re.search(dash_pattern, text)
    if match:
        a, b = float(match.group(1)), float(match.group(2))
        # 启发式：如果差值大于 10 则非 CI，跳过
        if abs(b - a) <= 10:
            return a, b
    return None


def parse_test_statistic(text: str) -> Optional[dict[str, Any]]:
    """
    从 LLM 输出中提取检验统计量（t / F / χ² / z）。

    匹配模式:
      - "t = 2.34", "t(23) = 2.34", "t-statistic = 2.34"
      - "F = 5.67", "F(2, 45) = 5.67"
      - "χ² = 12.34", "chi-square = 12.34", "chi2 = 12.34"
      - "z = 1.96", "z-score = 1.96"

    返回 {"type": "t"|"F"|"chi2"|"z", "value": float, "df": int|None} 或 None。
    """
    # t 检验
    t_pattern = r"""(?ix)
        t(?:[\s-]*stat(?:istic)?)?\s*(?:\(\s*(\d+)\s*\))?\s*[=：:]\s*
        (-?\d+\.?\d*)
    """
    m = re.search(t_pattern, text)
    if m:
        return {"type": "t", "value": float(m.group(2)), "df": int(m.group(1)) if m.group(1) else None}

    # F 检验
    f_pattern = r"""(?ix)
        F(?:[\s-]*stat(?:istic)?)?\s*(?:\(\s*(\d+)\s*,\s*(\d+)\s*\))?\s*[=：:]\s*
        (\d+\.?\d*)
    """
    m = re.search(f_pattern, text)
    if m:
        return {"type": "F", "value": float(m.group(3)), "df": None}

    # χ² 检验
    chi_pattern = r"""(?ix)
        (?:χ\s*2|chi[\s-]*square|chi\s*2)\s*(?:\(\s*(\d+)\s*\))?\s*[=：:]\s*
        (\d+\.?\d*)
    """
    m = re.search(chi_pattern, text)
    if m:
        return {"type": "chi2", "value": float(m.group(2)), "df": int(m.group(1)) if m.group(1) else None}

    # z 检验
    z_pattern = r"""(?ix)
        z(?:[\s-]*score)?\s*[=：:]\s*
        (-?\d+\.?\d*)
    """
    m = re.search(z_pattern, text)
    if m:
        return {"type": "z", "value": float(m.group(1)), "df": None}

    return None


def parse_r_squared(text: str) -> Optional[float]:
    """
    从 LLM 输出中提取 R² / 调整 R² 值。

    匹配模式:
      - "R² = 0.72", "R-squared = 0.72", "R2 = 0.72"
      - "adjusted R² = 0.68", "Adj. R² = 0.68"

    返回 float 或 None。
    """
    pattern = r"""(?ix)
        (?:adj(?:usted)?\.?\s*)?R\s*(?:²|2|[\s-]*squared)\s*[=：:]\s*
        (\d+\.?\d*)
    """
    m = re.search(pattern, text)
    if m:
        return float(m.group(1))
    return None


def parse_sample_size(text: str) -> Optional[int]:
    """
    从 LLM 输出中提取样本量。

    匹配模式:
      - "n = 120", "N = 120"
      - "样本量 = 120", "sample size = 120"
      - "共 120 个观测", "120 observations"

    返回 int 或 None。
    """
    patterns = [
        r"""(?ix)(?:n|样本量|sample\s*size)\s*[=：:]\s*(\d+)""",
        r"""(?ix)(\d+)\s*(?:个观测|observations|条记录|个样本)""",
    ]
    for pat in patterns:
        m = re.search(pat, text)
        if m:
            return int(m.group(1))
    return None


def validate_analysis_output(text: str) -> dict[str, bool]:
    """
    综合验证 Analyst 输出的结构完整性。

    检查项：
      - has_pvalue: 是否包含 p 值
      - has_effect_size: 是否包含效应量
      - has_conclusion: 是否包含明确结论
      - has_confidence: 是否包含置信区间

    返回检查结果的 dict。
    """
    return {
        "has_pvalue": parse_pvalue(text) is not None,
        "has_effect_size": parse_effect_size(text) is not None,
        "has_conclusion": parse_conclusion_count(text) is not None,
        "has_confidence": parse_confidence_interval(text) is not None,
        "has_test_statistic": parse_test_statistic(text) is not None,
        "has_r_squared": parse_r_squared(text) is not None,
        "has_sample_size": parse_sample_size(text) is not None,
    }


# ── 合理性校验层 ────────────────────────────────────────────────


def is_valid_pvalue(p: float | None) -> bool:
    """p 值必须在 [0, 1] 范围内。超出此范围说明 LLM 幻觉或解析错误。"""
    if p is None:
        return False
    return 0.0 <= p <= 1.0


def is_valid_effect_size(d: float | None) -> bool:
    """效应量必须 ≥ 0（Cohen's d 取绝对值，η² 天然非负）。
    允许一个宽松上界 (10.0) 来捕获异常大的幻觉值。"""
    if d is None:
        return False
    return 0.0 <= d <= 10.0


def is_valid_ci(lower: float | None, upper: float | None) -> bool:
    """置信区间：lower < upper，且区间宽度不超过 1000（防幻觉）。"""
    if lower is None or upper is None:
        return False
    width = upper - lower
    return lower < upper and abs(width) <= 1000.0


def check_p_ci_consistency(p: float | None, ci: tuple[float, float] | None) -> dict[str, any]:
    """
    检查 p 值与置信区间的一致性。

    如果 p < 0.05（显著），则 95% CI 不应跨越零（均值差场景）。
    如果 p ≥ 0.05（不显著），则 CI 应包含零。

    返回 {"consistent": bool, "detail": str}
    """
    if p is None or ci is None:
        return {"consistent": True, "detail": "无法判断（缺少 p 或 CI）"}
    lower, upper = ci
    crosses_zero = (lower <= 0 <= upper)
    is_significant = p < 0.05

    if is_significant and crosses_zero:
        return {
            "consistent": False,
            "detail": f"p={p:.4f}<0.05（显著）但 CI=[{lower:.3f}, {upper:.3f}] 跨越零，存在矛盾",
        }
    if (not is_significant) and (not crosses_zero):
        return {
            "consistent": False,
            "detail": f"p={p:.4f}≥0.05（不显著）但 CI=[{lower:.3f}, {upper:.3f}] 不跨越零，存在矛盾",
        }
    return {"consistent": True, "detail": "p 值与 CI 一致"}


def is_valid_r_squared(r2: float | None) -> bool:
    """R² 必须在 [0, 1] 范围内。"""
    if r2 is None:
        return False
    return 0.0 <= r2 <= 1.0


def is_valid_sample_size(n: int | None) -> bool:
    """样本量必须为正整数且不超过合理上界 (10^9)。"""
    if n is None:
        return False
    return 1 <= n <= 1_000_000_000


def is_valid_test_statistic(stat: dict[str, Any] | None) -> bool:
    """检验统计量值必须为有限数。"""
    if stat is None:
        return False
    v = stat.get("value")
    if v is None:
        return False
    try:
        fv = float(v)
    except (TypeError, ValueError):
        return False
    import math
    return math.isfinite(fv)


def detect_hallucination_indicators(text: str) -> list[str]:
    """
    检测 LLM 输出中可能的幻觉指标。

    检查项：
      - 无法识别的统计测试名称
      - 数值超出合理范围（p > 1, 样本量为负等）
      - 自相矛盾的陈述（同时声称"显著"和"不显著"）
      - R² 超出 [0,1] 范围
      - 检验统计量值非有限

    返回发现的可疑项列表。
    """
    warnings: list[str] = []

    # 1. 检查 p 值是否超出 [0,1]
    p = parse_pvalue(text)
    if p is not None and not is_valid_pvalue(p):
        warnings.append(f"p 值 {p} 不在 [0,1] 范围，可能存在幻觉")

    # 2. 检查效应量是否异常
    d = parse_effect_size(text)
    if d is not None and not is_valid_effect_size(d):
        warnings.append(f"效应量 {d} 异常，可能存在幻觉")

    # 3. 检查 CI 是否合法
    ci = parse_confidence_interval(text)
    if ci is not None and not is_valid_ci(*ci):
        warnings.append(f"置信区间 [{ci[0]}, {ci[1]}] 不合法")

    # 4. 检查自相矛盾陈述
    has_significant = bool(re.search(r"(?:显著|significant|p\s*[<≤]\s*0\.0[0-5])", text, re.IGNORECASE))
    has_not_significant = bool(re.search(r"(?:不显著|not\s*significant|无显著|no\s*significant|p\s*[>≥]\s*0\.0[0-5])", text, re.IGNORECASE))
    if has_significant and has_not_significant:
        # 在相同上下文中同时声称显著和不显著（可能在讨论不同变量，所以只是警告级别）
        warnings.append('文本中同时包含「显著」和「不显著」陈述，请确认是否有矛盾')

    # 5. 检查 p 值与 CI 一致性
    if p is not None and ci is not None:
        consistency = check_p_ci_consistency(p, ci)
        if not consistency["consistent"]:
            warnings.append(consistency["detail"])

    # 6. 检查 R² 是否合法
    r2 = parse_r_squared(text)
    if r2 is not None and not is_valid_r_squared(r2):
        warnings.append(f"R² = {r2} 不在 [0,1] 范围，可能存在幻觉")

    # 7. 检查检验统计量是否合法
    stat = parse_test_statistic(text)
    if stat is not None and not is_valid_test_statistic(stat):
        warnings.append(f"检验统计量 {stat.get('type')}={stat.get('value')} 非合法数值")

    # 8. 检查样本量是否合理
    n = parse_sample_size(text)
    if n is not None and not is_valid_sample_size(n):
        warnings.append(f"样本量 n={n} 不在合理范围，可能存在幻觉")

    return warnings


def deep_validate(text: str) -> dict[str, any]:
    """
    深度校验 LLM 分析输出，合并结构完整性和合理性检查。

    返回：
      - structure: 结构完整性 dict
      - p_value_valid: p 值是否在合理范围
      - effect_size_valid: 效应量是否合理
      - ci_valid: 置信区间是否合法
      - p_ci_consistent: p 值与 CI 是否一致
      - hallucination_warnings: 幻觉可疑项列表
      - overall_healthy: 整体是否健康（无结构缺失且无幻觉）
    """
    structure = validate_analysis_output(text)
    p = parse_pvalue(text)
    d = parse_effect_size(text)
    ci = parse_confidence_interval(text)
    r2 = parse_r_squared(text)
    stat = parse_test_statistic(text)
    n = parse_sample_size(text)

    p_ok = is_valid_pvalue(p) if p is not None else None  # None = 无 p 值，不算错
    d_ok = is_valid_effect_size(d) if d is not None else None
    ci_ok = is_valid_ci(*ci) if ci is not None else None
    r2_ok = is_valid_r_squared(r2) if r2 is not None else None
    stat_ok = is_valid_test_statistic(stat) if stat is not None else None
    n_ok = is_valid_sample_size(n) if n is not None else None
    consistency = check_p_ci_consistency(p, ci) if p is not None and ci is not None else {"consistent": True, "detail": "无足够数据比较"}

    warnings = detect_hallucination_indicators(text)

    overall = bool(
        structure.get("has_conclusion", False)
        and len(warnings) == 0
    )

    return {
        "structure": structure,
        "p_value_raw": p,
        "p_value_valid": p_ok,
        "effect_size_raw": d,
        "effect_size_valid": d_ok,
        "ci_raw": ci,
        "ci_valid": ci_ok,
        "p_ci_consistent": consistency["consistent"],
        "p_ci_detail": consistency["detail"],
        "r_squared_raw": r2,
        "r_squared_valid": r2_ok,
        "test_statistic_raw": stat,
        "test_statistic_valid": stat_ok,
        "sample_size_raw": n,
        "sample_size_valid": n_ok,
        "hallucination_warnings": warnings,
        "overall_healthy": overall,
    }
