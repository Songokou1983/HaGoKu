"""Refinement 解析器 — 解析用户的反馈/调整指令

HaGoKu Studio 的定位：调仪表盘，不是换引擎

✅ 允许的调整（结构性）：
- filter：缩小数据范围（"只看付费渠道"）
- switch_target：换分析指标（"换成ROI"）
- simplify：简化报告（"太长了"）
- more_detail：详细报告（"详细点"）
- explain：解释已有结论

❌ 不允许的调整（会退化）：
- new_direction：新分析方向 → 引导重新 run
- regenerate：重新跑一遍 → 引导重新 run
- speculate：推测性回答、原因猜测等 → 明确拒绝
- explore：开放性探索 → 引导重新 run

核心原则：保持 HaGoKu Studio 的分析约束，不因交互而退化。
全部语义理解通过 LLM function calling 完成，零硬编码正则。
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class RefinementIntent:
    """用户的调整意图"""

    # 调整类型
    # ✅ allowed: filter / switch_target / simplify / more_detail / explain / exit
    # ❌ blocked: new_direction / regenerate / speculate / explore
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


# ── 阻断类型的引导文案（唯一硬编码：这些文案是稳定 UI 文案，不含语义判断）


_BLOCKED_GUIDANCE: dict[str, str] = {
    "new_direction": (
        "💡 这是新的分析方向，我会保存当前报告。\n"
        "   如需新方向分析，请输入「退出」后重新 run"
    ),
    "regenerate": (
        "💡 重新生成请输入「退出」后重新 run，\n"
        "   或直接运行：hagoku run <数据文件> -q <新问题>"
    ),
    "speculate": (
        "💡 HaGoKu Studio 只呈现数据告诉你的事实，不推测原因。\n"
        "   如需分析原因，请重新 run 并明确问题"
    ),
    "explore": (
        "💡 如需新的分析方向，请退出后重新 run。"
    ),
}


class RefinementParser:
    """解析用户的 refinement 指令（LLM 驱动，零硬编码正则）。

    对标 ScoutAgent._infer_all_semantics() 的设计：用户自然语言 → LLM function calling → 结构化输出。
    """

    def parse(self, feedback: str, context: dict[str, Any] | None = None) -> RefinementIntent:
        """解析用户反馈。

        Args:
            feedback: 用户的反馈文本
            context: 分析上下文，包含已有结论、列名信息等

        Returns:
            RefinementIntent 结构化意图
        """
        if not feedback or not feedback.strip():
            return RefinementIntent(raw_input=feedback, confidence="high")

        f = feedback.strip()

        # LLM 语义理解（唯一通道：全部走 function calling）
        try:
            return self._parse_via_llm(f, context)
        except Exception as e:
            raise RuntimeError(f"refinement: LLM 反馈解析失败：{e}") from e

    def _parse_via_llm(self, feedback: str, context: dict[str, Any] | None) -> RefinementIntent:
        """通过 LLM function calling 解析用户意图。"""
        from hagoku.agents.types import build_submit_refinement_schema
        from hagoku.config import HaGoKuConfig
        from hagoku.llm.client import create_raw_client

        config = HaGoKuConfig.load().llm
        client = create_raw_client(config)

        schema = build_submit_refinement_schema()
        submit_tool = {
            "type": "function",
            "function": {
                "name": "submit_refinement",
                "description": "提交对用户调整指令的理解结果。根据用户自然语言输出结构化意图。",
                "parameters": schema,
            },
        }

        # 构建上下文信息（已有分析的列名、指标名、结论等，帮助 LLM 理解用户指的什么）
        ctx_text = ""
        if context:
            target = context.get("target", "")
            features = context.get("features", [])
            columns = context.get("column_semantics", [])
            if columns:
                col_names = [c.get("column_name", "") for c in columns if isinstance(c, dict)]
                if col_names:
                    ctx_text += f"当前可用列: {', '.join(col_names)}\n"
            if target:
                ctx_text += f"当前目标变量: {target}\n"
            if features:
                ctx_text += f"当前特征变量: {', '.join(features)}\n"

        system_prompt = (
            "你是数据分析助手，负责理解用户在当前分析基础上的调整意图。\n\n"
            "用户可能在要求：\n"
            "  ✅ 允许的调整（在当前分析基础上微调）：\n"
            "    - filter: 筛选数据（如「只看一线城市」「排除付费渠道」）\n"
            "    - switch_target: 切换分析指标（如「换成 ROI 看看」）\n"
            "    - simplify/more_detail: 调整报告详略（如「太长了」「详细展开」）\n"
            "    - explain: 解释已有结论（如「为什么 ROI 下降了」）\n"
            "    - exit: 用户想要退出/结束当前分析（如「退出」「结束」「算了」「保存并退出」）\n\n"
            "  ❌ 不允许的调整（需重新 run）：\n"
            "    - new_direction: 提出新的分析方向，超出当前调整范围\n"
            "    - regenerate: 要求重新生成\n"
            "    - speculate: 要求推测原因（超出数据能告诉你的事实）\n"
            "    - explore: 要求开放性探索\n\n"
            "你需要调用 submit_refinement 工具来提交你的理解。\n"
            "如果用户要求的是新分析方向或超出当前调整范围的操作，"
            "refine_type 设为对应的 blocked 类型并提供 guidance。"
        )

        try:
            response = client.chat.completions.create(
                model=config.model_quick or config.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"{ctx_text}用户输入：{feedback}"},
                ],
                temperature=0.0,
                max_tokens=512,
                tools=[submit_tool],
                tool_choice={"type": "function", "function": {"name": "submit_refinement"}},
            )
        except Exception:
            # 如果 tool_choice 要求严格但模型不支持，回退到自由调用
            response = client.chat.completions.create(
                model=config.model_quick or config.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"{ctx_text}用户输入：{feedback}"},
                ],
                temperature=0.0,
                max_tokens=512,
                tools=[submit_tool],
            )

        # 解析 tool call 结果
        msg = response.choices[0].message
        if msg.tool_calls:
            args = json.loads(msg.tool_calls[0].function.arguments)
        elif msg.content:
            # 某些模型可能不通过 tool call 返回，尝试从 content 解析
            try:
                args = json.loads(msg.content)
            except json.JSONDecodeError:
                return self._build_unknown_intent(feedback)
        else:
            return self._build_unknown_intent(feedback)

        refine_type = args.get("refine_type", "unknown")

        # blocked 类型：使用预定义的引导文案（稳定 UI）
        if refine_type in _BLOCKED_GUIDANCE:
            return RefinementIntent(
                raw_input=feedback,
                refine_type="blocked",
                confidence="medium",
                guidance=_BLOCKED_GUIDANCE[refine_type],
            )

        # 正常允许的类型
        return RefinementIntent(
            raw_input=feedback,
            refine_type=refine_type,
            filter_column=args.get("filter_column"),
            filter_value=args.get("filter_value"),
            filter_exclude=bool(args.get("filter_exclude", False)),
            new_target=args.get("new_target"),
            verbosity=args.get("verbosity"),
            explain_target=args.get("explain_target"),
            can_explain_from_data=bool(args.get("can_explain_from_data", False)),
            guidance=args.get("guidance"),
            confidence="medium",
        )

    def _build_unknown_intent(self, feedback: str) -> RefinementIntent:
        """LLM 不可达或不理解时的最小兜底。"""
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
                "   如需结束当前分析，请直接说明（如「退出」「结束」）"
            ),
        )


# ── 快捷函数 ────────────────────────────────────────────────


def parse_refinement(feedback: str, context: dict[str, Any] | None = None) -> RefinementIntent:
    """快捷函数：解析用户 refinement 指令"""
    return RefinementParser().parse(feedback, context)