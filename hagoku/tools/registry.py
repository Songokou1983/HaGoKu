"""HaGoKu 全局工具注册表 — 所有 Agent 共享的工具系统

每个工具定义：
  - name: 工具名
  - description: 给 LLM 看的描述
  - parameters: OpenAI function calling 格式的 JSON Schema
  - handler: Python 回调，接收 (args: dict, context: dict, df: DataFrame | None) → result

用法：
  from hagoku.tools.registry import agent_tools
  tools = agent_tools.to_openai("cleaner")  # → OpenAI tools array
  result = agent_tools.dispatch("get_column_stats", {"column": "Inc1"}, context, df)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable

_log = logging.getLogger("hagoku.tools")


@dataclass
class Tool:
    name: str
    description: str
    parameters: dict[str, Any]
    handler: Callable[..., Any]
    phase_tag: list[str] = field(default_factory=lambda: ["理解字段", "评估清洗", "跑统计", "写报告"])
    # Phase D: phase_tag 标注工具的典型使用场景，供 LLM 选工具时参考


class AgentTools:
    """全局工具注册表，单例。"""

    _tools: dict[str, Tool] = {}

    @classmethod
    def register(cls, tool: Tool) -> None:
        if tool.name in cls._tools:
            _log.warning("工具 %s 已注册，将被覆盖", tool.name)
        cls._tools[tool.name] = tool

    @classmethod
    def get(cls, name: str) -> Tool | None:
        return cls._tools.get(name)

    @classmethod
    def list_for_agent(cls, agent: str) -> list[Tool]:
        """Phase D: 不再按 agent 过滤——返回全部工具。agent 参数保留兼容旧调用。"""
        return list(cls._tools.values())

    @classmethod
    def to_openai(cls, agent: str = "") -> list[dict[str, Any]]:
        """返回全部工具（不再按 agent 过滤）。
        
        phase_tag 标注工具的典型使用场景，帮助 LLM 选工具。
        """
        result: list[dict[str, Any]] = []
        for t in cls._tools.values():
            desc = t.description
            result.append({
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": desc,
                    "parameters": t.parameters,
                },
            })
        return result

    @classmethod
    def dispatch(
        cls,
        name: str,
        args: dict[str, Any],
        context: dict[str, Any],
        df: pd.DataFrame | None = None,
    ) -> Any:
        """执行工具调用。返回工具执行结果。"""
        tool = cls._tools.get(name)
        if tool is None:
            return {"error": f"未知工具: {name}"}
        try:
            return tool.handler(args, context, df)
        except Exception as e:
            _log.warning("工具 %s 执行失败: %s", name, e)
            return {"error": str(e)}


# ── 单例 ──
agent_tools = AgentTools()
