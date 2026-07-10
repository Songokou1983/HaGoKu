"""Query 解析器 — 将用户的自然语言转换为结构化分析意图

全部通过 LLM 结构化输出完成，零硬编码规则。
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class QueryIntent:
    """结构化的用户查询意图"""

    intent_type: str = "exploration"
    target: str | None = None
    group_by: list[str] = field(default_factory=list)
    time_range: str | None = None
    time_from: datetime | None = None
    time_to: datetime | None = None
    filters: dict[str, Any] = field(default_factory=dict)
    mentioned_columns: list[str] = field(default_factory=list)
    confidence: str = "medium"
    thinking: str = ""
    analysis_focus: list[str] = field(default_factory=list)


# ── 快捷函数（LLM 驱动，零硬编码）────────────────────────────


def parse_query(query: str, context_hints: dict[str, Any] | None = None) -> QueryIntent:
    """LLM 驱动：解析用户查询为结构化意图。

    零硬编码规则——所有意图识别、目标提取、时间解析交由 LLM 完成。
    LLM 不可达时 raise RuntimeError（铁律 2 路径 A / 铁律 7），不兜底。
    """
    if not query or not query.strip():
        return QueryIntent(intent_type="exploration", confidence="high")

    try:
        intent_data = _llm_parse_intent(query.strip(), context_hints)
        return _build_intent(intent_data)
    except Exception as e:
        raise RuntimeError(f"query_parser: LLM 意图解析失败：{e}") from e


# ==== CHANNEL ZONE: 禁止正则/if-else 语义分支 ====
def _llm_parse_intent(query: str, context_hints: dict[str, Any] | None) -> dict[str, Any]:
    """调用 LLM 做意图识别，返回结构化 dict。"""
    from hagoku.config import HaGoKuConfig
    from hagoku.llm.client import create_raw_client  # pragma: no cover

    config = HaGoKuConfig.load().llm
    client = create_raw_client(config)

    system_prompt = """你是数据分析意图识别专家。根据用户问题，输出一个 JSON 对象：

{
  "intent_type": "exploration | comparison | causation | correlation | trend | diagnostic | roi_analysis | ltv_analysis | cac_analysis | funnel_conversion | attribution | investment_decision | cohort_analysis | growth_rate",
  "confidence": "high | medium | low",
  "target": "用户关注的目标变量（中文名），没有则为 null",
  "group_by": ["用户想按什么维度分组，中文名称列表"],
  "time_range": "用户提到的时间范围原文，没有则为 null",
  "mentioned_columns": ["用户直接或间接提到的数据列名，中文"],
  "analysis_focus": ["根据意图推荐的分析方法，从以下选: regression, hypothesis_test, correlation, trend, effect_size, causal"],
  "filters": {},
  "thinking": "一句话简述你的判断依据"
}

规则：
- intent_type 必须从上面枚举中选一个，不明确的用 "exploration"
- analysis_focus 由你根据意图直接推荐合适的分析方法列表
- target / group_by / mentioned_columns 用中文写出用户的业务语言
- time_range 保留用户在问题中的原文表述（如 "最近3个月"）
- confidence: 表达清晰且关键词匹配度高 → high；可推断但需要确认 → medium；完全不清楚 → low"""

    # 构建上下文信息
    hints_text = ""
    if context_hints:
        cols = context_hints.get("column_semantics", [])
        if cols:
            col_names = [c.get("column_name", "") for c in cols if isinstance(c, dict)]
            if col_names:
                hints_text = f"\n\n已知数据列名: {', '.join(col_names)}"

    from hagoku.channel import build_messages

    try:
        response = client.chat.completions.create(
            model=config.model,
            # EXEMPT: 辅助 LLM — 意图解析，非主对话通道
            messages=build_messages(
                query=query,
                user_input=f"用户问题：{query}{hints_text}",
                system_extra=system_prompt,
            ),
            temperature=0.0,
            max_tokens=512,
            response_format={"type": "json_object"},
        )
    except Exception:
        response = client.chat.completions.create(
            model=config.model,
            messages=build_messages(
                query=query,
                user_input=f"用户问题：{query}{hints_text}",
                system_extra=system_prompt,
            ),
            temperature=0.0,
            max_tokens=[redacted],
        )

    raw = response.choices[0].message.content or ""
    # 剥离 MiniMax 等模型的 <think>...</think> CoT 块
    raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # 尝试提取 JSON
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if match:
            return json.loads(match.group())
        raise ValueError(f"LLM 返回无法解析: {raw[:200]}")


def _build_intent(data: dict[str, Any]) -> QueryIntent:
    """从 LLM 返回的 dict 构建 QueryIntent。"""
    return QueryIntent(
        intent_type=data.get("intent_type", "exploration"),
        confidence=data.get("confidence", "medium"),
        target=data.get("target"),
        group_by=list(data.get("group_by") or []),
        time_range=data.get("time_range"),
        mentioned_columns=list(data.get("mentioned_columns") or []),
        analysis_focus=list(data.get("analysis_focus") or []),
        filters=data.get("filters") or {},
        thinking=data.get("thinking", ""),
    )
