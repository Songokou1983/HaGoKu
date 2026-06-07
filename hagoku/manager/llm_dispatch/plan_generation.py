"""计划生成 + 意图解析。CH-5 从 orchestrator.py 拆分。"""
from __future__ import annotations

from typing import Any

from ...observability.events import EventType

def _parse_user_query(self, query: str) -> Any:
    """解析用户查询为结构化意图。

    parse_query 在 LLM 不可达时直接 raise（铁律 7），不兜底。
    异常自然向上传播到调用方。
    """
    from ...manager.query_parser import parse_query
    return parse_query(query)

def _describe_intent(self, parsed_intent: Any) -> str:
    """将解析后的意图译成接在「让我来」后的自然短句。

    首选 LLM thinking 字段（Planning 阶段 LLM 产出），无 thinking 时回退为
    纯数据描述（不含硬编码 intent_type→短语映射），零语义归因。
    """
    # 优先使用 LLM 在意图解析时给出的 thinking
    thinking = getattr(parsed_intent, "thinking", "") or ""
    if thinking.strip():
        return thinking.strip()

    # LLM 未提供 thinking 时的纯数据兜底（零硬编码语义映射）
    parts: list[str] = []
    if getattr(parsed_intent, "target", None):
        parts.append(f"关注「{parsed_intent.target}」")
    if getattr(parsed_intent, "time_range", None):
        parts.append(f"时间范围「{parsed_intent.time_range}」")
    if getattr(parsed_intent, "group_by", None):
        parts.append(f"按「{'/'.join(parsed_intent.group_by)}」分组")

    if parts:
        return f"分析{'，'.join(parts)}"
    return "探索一下这份数据有什么规律"

def _build_analysis_purpose(self, context: dict[str, Any]) -> dict[str, Any]:
    """从 context 提取本次分析涉及的核心字段信息，供下游 Agent 聚焦。

    包含 target（目标变量）、features（特征变量）、roles（变量角色映射），
    以及一份人类可读的总结字符串。
    """
    target = context.get("target")
    features = context.get("features") or []
    variable_roles = context.get("variable_roles") or {}

    summary_parts: list[str] = []
    if target:
        summary_parts.append(f"目标变量（因变量）：{target}")
    if features:
        summary_parts.append(f"特征变量（自变量）：{', '.join(str(f) for f in features)}")
    if variable_roles:
        role_lines = [f"  {k}: {v}" for k, v in sorted(variable_roles.items())]
        summary_parts.append(f"变量角色：\n{chr(10).join(role_lines)}")

    return {
        "target": target,
        "features": features,
        "variable_roles": variable_roles,
        "summary": "\n".join(summary_parts) or "（未指定分析字段角色）",
    }

def _get_upstream_summary(self, agent_name: str) -> str | None:
    """占位方法（Step 3 删 handover 通道后保留兼容）。

    调用点（line 853）期望拿到上游 Agent 摘要注入下游 prompt。
    Step 4 决定：handover 通道彻底删除后，本方法返回 None 即可。
    下游 Agent 拿不到额外摘要，但其 ctx 仍包含上游的完整数据（self._analyst_messages 等）。
    """
    return None

# ── Kanban 状态机（Step 4：从 Scribe 内联到 Orchestrator） ──
