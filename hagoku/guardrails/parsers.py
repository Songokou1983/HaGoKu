"""HaGoKu 结构化输出解析器 — 从 LLM 自由文本中提取统计结论"""

from __future__ import annotations

import re
from typing import Optional


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
    }
