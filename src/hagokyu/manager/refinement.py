"""Refinement 解析器 — 解析用户的反馈/调整指令

用户看到分析结果后，可能会说：
- "只看付费渠道" → 缩小范围
- "换成ROI对比" → 换目标变量
- "报告太长了" → 简化输出
- "为什么这个渠道效果最好" → 要求解释
- "加上环比数据" → 增加分析维度
- "重新生成" → 重新跑一遍

核心原则：模糊反馈也要尽量理解，不理解就问用户
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


# ── Refinement 类型 ───────────────────────────────────────────


@dataclass
class RefinementIntent:
    """用户的调整意图"""

    # 调整类型
    refine_type: str = "unknown"  # filter/switch_target/simplify/explain/add/regenerate/unknown

    # 如果是 filter（缩小范围）
    filter_column: str | None = None
    filter_value: str | None = None  # e.g. "付费渠道"
    filter_exclude: bool = False  # True=排除, False=只看

    # 如果是 switch_target（换指标）
    new_target: str | None = None  # e.g. "ROI"

    # 如果是 simplify（简化/详细）
    verbosity: str | None = None  # "simpler" / "more_detailed"

    # 如果是 add（增加分析）
    add_dimension: str | None = None  # e.g. "环比", "同比"

    # 如果是 explain（要求解释）
    explain_target: str | None = None  # 要解释哪个结论

    # 如果是 regenerate（重新生成）
    new_template: str | None = None

    # 原始用户输入
    raw_input: str = ""

    # 置信度
    confidence: str = "medium"

    # 如果无法理解，需要向用户确认什么
    clarification_needed: str | None = None


# ── 反馈关键词映射 ──────────────────────────────────────────


REFINE_PATTERNS: list[tuple[str, str]] = [
    # (refine_type, 正则模式)
    ("filter", r"只看|只看"),
    ("exclude", r"排除|去掉|不要|不含|不包括"),
    ("switch_target", r"换成|改为|改用|换.*指标|改.*指标|换.*目标"),
    ("simplify", r"太长了|太啰嗦|简单点|简洁|精简|简短|只要|只留"),
    ("more_detail", r"详细点|展开|多说点|更详细|更完整"),
    ("explain", r"为什么|怎么得出的|怎么知道的|依据是什么|解释一下"),
    ("add", r"加上|加个|算一下|再加上|加入|补充"),
    ("regenerate", r"重新生成|再来一遍|重跑|重新分析"),
]

# 维度关键词
DIMENSION_KEYWORDS = [
    "渠道", "地区", "产品", "城市", "省份", "性别", "年龄段",
    "用户", "客群", "来源", "平台", "设备",
    "付费", "免费", "新用户", "老用户",
]


class RefinementParser:
    """解析用户的 refinement 指令"""

    def parse(self, feedback: str, context: dict[str, Any] | None = None) -> RefinementIntent:
        """
        解析用户反馈

        Args:
            feedback: 用户的反馈文本
            context: 分析上下文，可能包含已知的列名等信息

        Returns:
            RefinementIntent 结构化意图
        """
        if not feedback or not feedback.strip():
            return RefinementIntent(raw_input=feedback, confidence="high")

        f = feedback.strip()
        intent = RefinementIntent(raw_input=f)

        # 1. 检查是否是退出指令
        if self._is_exit(f):
            intent.refine_type = "exit"
            intent.confidence = "high"
            return intent

        # 2. 遍历模式匹配
        for refine_type, patterns in REFINE_PATTERNS:
            if re.search(patterns, f):
                intent.refine_type = refine_type
                intent.confidence = "high"
                break

        # 3. 根据类型提取详细信息
        if intent.refine_type == "filter":
            self._extract_filter(f, intent)
        elif intent.refine_type == "exclude":
            self._extract_filter(f, intent, exclude=True)
        elif intent.refine_type == "switch_target":
            self._extract_target(f, intent)
        elif intent.refine_type == "simplify":
            intent.verbosity = "simpler"
        elif intent.refine_type == "more_detail":
            intent.verbosity = "more_detailed"
        elif intent.refine_type == "explain":
            self._extract_explain_target(f, intent, context)
        elif intent.refine_type == "add":
            self._extract_add_dimension(f, intent)
        elif intent.refine_type == "unknown":
            self._fallback_to_query_parser(f, intent)

        return intent

    def _extract_filter(self, feedback: str, intent: RefinementIntent, exclude: bool = False) -> None:
        """提取 filter/exclude 意图"""
        intent.filter_exclude = exclude

        for dim in DIMENSION_KEYWORDS:
            if dim in feedback:
                intent.filter_column = dim
                # 提取维度值
                match = re.search(rf"{dim}[是为是]\s*(\S+)", feedback)
                if match:
                    intent.filter_value = match.group(1)
                else:
                    intent.clarification_needed = f"你说的是「{dim}」的哪个值？"
                break

        if not intent.filter_column:
            # 尝试从反馈中提取任意维度词
            for dim in DIMENSION_KEYWORDS:
                if dim in feedback:
                    intent.filter_column = dim
                    break

    def _extract_target(self, feedback: str, intent: RefinementIntent) -> None:
        """提取 switch_target 意图"""
        for kw in ["ROI", "ROAS", "CTR", "CVR", "转化率", "点击率",
                   "销量", "销售额", "利润", "收入", "客单价", "GMV"]:
            if kw in feedback:
                intent.new_target = kw
                break

        if not intent.new_target:
            intent.clarification_needed = "你想换成什么指标？（比如：ROI、转化率、销量）"

    def _extract_explain_target(self, feedback: str, intent: RefinementIntent, context: dict | None) -> None:
        """提取 explain 意图"""
        if context:
            results = context.get("recent_results", [])
            if results:
                first = results[0]
                intent.explain_target = first.get("question", "") if isinstance(first, dict) else str(first)

    def _extract_add_dimension(self, feedback: str, intent: RefinementIntent) -> None:
        """提取 add 意图"""
        for kw in ["环比", "同比", "趋势", "对比", "分布"]:
            if kw in feedback:
                intent.add_dimension = kw
                break

        if not intent.add_dimension:
            intent.clarification_needed = "你想加什么分析？（比如：环比、同比、趋势）"

    def _fallback_to_query_parser(self, feedback: str, intent: RefinementIntent) -> None:
        """无法识别时，尝试用 query_parser 理解"""
        try:
            from .query_parser import parse_query
            parsed = parse_query(feedback)
            if parsed and parsed.intent_type != "exploration":
                intent.refine_type = "refine_query"
                intent.new_target = parsed.target
                intent.confidence = "medium"
            else:
                intent.confidence = "low"
                intent.clarification_needed = (
                    "我不太理解，你可以说：\n"
                    "  • 「只看XX」— 缩小范围\n"
                    "  • 「换成XX指标」— 换指标\n"
                    "  • 「简单点/详细点」— 调整报告\n"
                    "  • 「为什么」— 解释结论\n"
                    "  • 「退出」— 结束"
                )
        except Exception:
            intent.confidence = "low"
            intent.clarification_needed = (
                "我不太理解，你可以说：\n"
                "  • 「只看XX」— 缩小范围\n"
                "  • 「换成XX指标」— 换指标\n"
                "  • 「简单点/详细点」— 调整报告\n"
                "  • 「退出」— 结束"
            )

    def _is_exit(self, feedback: str) -> bool:
        """判断是否是退出指令"""
        exit_words = ["退出", "够了", "结束", "exit", "quit", "done", "stop", "q", "再见"]
        return feedback in exit_words or feedback.lower() in exit_words


# ── 快捷函数 ────────────────────────────────────────────────


def parse_refinement(feedback: str, context: dict[str, Any] | None = None) -> RefinementIntent:
    """快捷函数：解析用户 refinement 指令"""
    return RefinementParser().parse(feedback, context)
