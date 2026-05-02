"""Refinement 解析器 — 解析用户的反馈/调整指令

HaGoKu 的定位：调仪表盘，不是换引擎

✅ 允许的调整（结构性）：
- filter：缩小数据范围（"只看付费渠道"）
- switch_target：换分析指标（"换成ROI"）
- simplify：简化报告（"太长了"）
- more_detail：详细报告（"详细点"）
- explain：解释已有结论

❌ 不允许的调整（会退化）：
- add：新分析方向 → 引导重新 run
- regenerate：重新跑一遍 → 引导重新 run
- 推测性回答、原因猜测等 → 明确拒绝

核心原则：保持 HaGoKu 的分析约束，不因交互而退化
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
    # ✅ allowed: filter / switch_target / simplify / more_detail / explain
    # ❌ blocked: add / regenerate / unknown_speculative
    refine_type: str = "unknown"

    # 如果是 filter（缩小范围）
    filter_column: str | None = None
    filter_value: str | None = None  # e.g. "付费渠道"
    filter_exclude: bool = False  # True=排除, False=只看

    # 如果是 switch_target（换指标）
    new_target: str | None = None  # e.g. "ROI"

    # 如果是 simplify（简化/详细）
    verbosity: str | None = None  # "simpler" / "more_detailed"

    # 如果是 explain（要求解释）
    explain_target: str | None = None  # 要解释哪个结论

    # 如果是 explain，且能从已有结论中解释
    can_explain_from_data: bool = False

    # 原始用户输入
    raw_input: str = ""

    # 置信度
    confidence: str = "medium"

    # 无法理解或不允许时的引导
    guidance: str | None = None  # 引导用户如何做


# ── 关键词映射（白名单）────────────────────────────────────


# 只允许这 5 种调整类型
ALLOWED_PATTERNS: list[tuple[str, str]] = [
    # (refine_type, 正则模式)
    ("filter", r"只看|只看|只看"),
    ("exclude", r"排除|去掉|不要|不含|不包括|除了"),
    ("switch_target", r"换成|改为|改用|换.*指标|改.*指标|换.*目标|换成.*的"),
    ("simplify", r"太长了|太啰嗦|简单点|简洁点|精简|简短|只要|只留|简洁"),
    ("more_detail", r"详细点|展开|多说点|更详细|更完整|展开说"),
    ("explain", r"为什么|怎么得出的|怎么知道的|依据是什么|解释一下|怎么算的"),
]

# 维度关键词（用于提取 filter/exclude 的具体值）
DIMENSION_KEYWORDS = [
    "渠道", "地区", "产品", "城市", "省份", "性别", "年龄段",
    "用户", "客群", "来源", "平台", "设备",
    "付费", "免费", "新用户", "老用户",
    "PC", "App", "H5", "web", "小程序",
]

# 指标关键词（用于提取 switch_target）
TARGET_KEYWORDS = [
    "ROI", "roas", "ROAS", "CTR", "ctr", "CVR", "cvr",
    "转化率", "点击率", "点击", "曝光",
    "销量", "销售额", "GMV", "gmv", "收入", "利润", "成本", "客单价",
    "留存率", "流失率", " churn", "激活率", "注册率",
    "活跃", "新增", "访问", "PV", "UV",
]

# ── 不允许的模式（拦截）────────────────────────────────────


# 这些模式 → 引导用户重新 run，不在当前 loop 处理
BLOCKED_PATTERNS: list[tuple[str, str]] = [
    # 新分析方向
    ("new_direction", r"分析.*趋势|看看.*变化|再看下.*|再看看|再跑.*|再算.*|再查.*|再加.*|补充.*|加上.*|算一下.*|分析下.*|跑下.*|再看一下"),
    # 重新生成
    ("regenerate", r"重新生成|再来一遍|重新跑|重新分析|从头开始|再来一次"),
    # 推测原因
    ("speculate", r"原因是什么|可能是因为|应该是.*导致|估计.*原因|猜测|推测|可能.*导致|大概是.*原因"),
    # 开放性探索
    ("explore", r"还有什么|还有什么发现|还应该看什么|还应该分析什么|有没有.*遗漏|还有没有.*问题"),
]


class RefinementParser:
    """解析用户的 refinement 指令（严格白名单）"""

    def parse(self, feedback: str, context: dict[str, Any] | None = None) -> RefinementIntent:
        """
        解析用户反馈

        Args:
            feedback: 用户的反馈文本
            context: 分析上下文，包含已有结论等

        Returns:
            RefinementIntent 结构化意图
        """
        if not feedback or not feedback.strip():
            return RefinementIntent(raw_input=feedback, confidence="high")

        f = feedback.strip()
        intent = RefinementIntent(raw_input=f)

        # 1. 先检查退出指令
        if self._is_exit(f):
            intent.refine_type = "exit"
            intent.confidence = "high"
            return intent

        # 2. 检查是否是不允许的模式
        for block_type, pattern in BLOCKED_PATTERNS:
            if re.search(pattern, f):
                return self._build_blocked_intent(block_type, f)

        # 3. 检查是否是允许的模式
        for refine_type, patterns in ALLOWED_PATTERNS:
            if re.search(patterns, f):
                intent.refine_type = refine_type
                intent.confidence = "high"
                self._extract_details(f, intent, refine_type)
                return intent

        # 4. 无法识别 → 帮助用户找到正确方式
        return self._build_unknown_intent(f)

    def _build_blocked_intent(self, block_type: str, feedback: str) -> RefinementIntent:
        """构建被拦截的意图"""
        guidance_map = {
            "new_direction": (
                "💡 这是新的分析方向，我会保存当前报告。\n"
                "   如需新方向分析，请输入「退出」后重新 run"
            ),
            "regenerate": (
                "💡 重新生成请输入「退出」后重新 run，\n"
                "   或直接运行：hagokyu run <数据文件> -q <新问题>"
            ),
            "speculate": (
                "💡 HaGoKu 只呈现数据告诉你的事实，不推测原因。\n"
                "   如需分析原因，请重新 run 并明确问题"
            ),
            "explore": (
                "💡 如需新的分析方向，请退出后重新 run。"
            ),
        }
        return RefinementIntent(
            raw_input=feedback,
            refine_type="blocked",
            confidence="high",
            guidance=guidance_map.get(block_type, "💡 请输入「退出」后重新 run"),
        )

    def _build_unknown_intent(self, feedback: str) -> RefinementIntent:
        """无法识别时的引导"""
        return RefinementIntent(
            raw_input=feedback,
            refine_type="unknown",
            confidence="low",
            guidance=(
                "💡 我支持以下调整：\n"
                "   • 「只看XX」— 缩小数据范围\n"
                "   • 「换成XX指标」— 换分析指标\n"
                "   • 「简单点/详细点」— 调整报告详略\n"
                "   • 「为什么」— 解释已有结论\n"
                "   输入「退出」可结束并保存当前报告"
            ),
        )

    def _extract_details(self, feedback: str, intent: RefinementIntent, refine_type: str) -> None:
        """提取具体参数"""
        if refine_type in ("filter", "exclude"):
            intent.filter_exclude = (refine_type == "exclude")
            self._extract_filter_details(feedback, intent)

        elif refine_type == "switch_target":
            self._extract_target_details(feedback, intent)

        elif refine_type == "simplify":
            intent.verbosity = "simpler"

        elif refine_type == "more_detail":
            intent.verbosity = "more_detailed"

        elif refine_type == "explain":
            self._extract_explain_details(feedback, intent)

    def _extract_filter_details(self, feedback: str, intent: RefinementIntent) -> None:
        """提取 filter/exclude 的具体值"""
        # 找维度
        for dim in DIMENSION_KEYWORDS:
            if dim in feedback:
                intent.filter_column = dim
                # 尝试提取值
                match = re.search(rf"{dim}[是为是]\s*(\S+)", feedback)
                if match:
                    intent.filter_value = match.group(1)
                else:
                    # 尝试从反馈中提取值（去掉维度和连接词）
                    rest = feedback.replace(dim, "").strip()
                    for conn in ["是为是", "是", "为", "等于", "的"]:
                        rest = rest.replace(conn, "").strip()
                    if rest and len(rest) < 20:
                        intent.filter_value = rest
                break

        # 如果没找到维度，尝试从上下文猜
        if not intent.filter_column:
            for dim in DIMENSION_KEYWORDS:
                if dim in feedback:
                    intent.filter_column = dim
                    break

    def _extract_target_details(self, feedback: str, intent: RefinementIntent) -> None:
        """提取 switch_target 的新指标"""
        for kw in TARGET_KEYWORDS:
            if kw in feedback:
                intent.new_target = kw
                break

        if not intent.new_target:
            # 尝试提取任意数字/英文字符作为指标
            match = re.search(r"(?:换成|改为|改用)\s*(\S+)", feedback)
            if match:
                intent.new_target = match.group(1)

    def _extract_explain_details(self, feedback: str, intent: RefinementIntent) -> None:
        """提取 explain 的具体目标"""
        # 提取"为什么XXX"中的XXX
        match = re.search(r"为什么\s*(.+?)(?:\s|$|？|\?)", feedback)
        if match:
            intent.explain_target = match.group(1).strip()
        intent.can_explain_from_data = True

    def _is_exit(self, feedback: str) -> bool:
        """判断是否是退出指令"""
        exit_words = ["退出", "exit", "quit", "done", "stop", "q", "算了", "保存", "结束", "再见"]
        return feedback in exit_words or feedback.lower() in exit_words


# ── 快捷函数 ────────────────────────────────────────────────


def parse_refinement(feedback: str, context: dict[str, Any] | None = None) -> RefinementIntent:
    """快捷函数：解析用户 refinement 指令"""
    return RefinementParser().parse(feedback, context)
