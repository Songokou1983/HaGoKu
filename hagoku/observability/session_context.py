"""Session 上下文管理 — 每个 Agent 独立会话，跨 Agent 结论交接"""
from __future__ import annotations

from typing import Any


class SessionContext:
    """管理一个分析 session 的对话记忆和结论传递。

    使用方式：
        ctx = SessionContext()
        ctx.start_agent("scout")
        ctx.add_message("scout", {"role": "system", "content": "..."})
        ctx.add_message("scout", {"role": "assistant", "content": "..."})
        ctx.finish_agent("scout", conclusions={"target": "Inc1", "features": ["Code", "Period"]})

        # 下游 Agent 读取
        upstream = ctx.get_upstream_context("cleaner")
        # → "上游 Scout 结论：目标变量 Inc1，特征 Code, Period..."
    """

    def __init__(self) -> None:
        self._sessions: dict[str, list[dict[str, str]]] = {}
        self._conclusions: dict[str, dict[str, Any]] = {}
        self._agent_order: list[str] = []

    def start_agent(self, agent: str) -> None:
        """开始一个 Agent 的会话"""
        self._sessions[agent] = []
        self._agent_order.append(agent)

    def add_message(self, agent: str, msg: dict[str, str]) -> None:
        """追加一条消息到当前 Agent 会话"""
        if agent not in self._sessions:
            self._sessions[agent] = []
        self._sessions[agent].append(msg)

    def get_messages(self, agent: str) -> list[dict[str, str]]:
        """获取当前 Agent 的完整会话消息"""
        return self._sessions.get(agent, [])

    def finish_agent(self, agent: str, conclusions: dict[str, Any]) -> None:
        """Agent 完成，记录结论"""
        self._conclusions[agent] = conclusions

    def get_upstream_context(self, agent: str) -> str:
        """为下游 Agent 生成上游结论文本"""
        idx = self._agent_order.index(agent) if agent in self._agent_order else -1
        parts = []
        for prev in self._agent_order[:idx]:
            c = self._conclusions.get(prev, {})
            if not c:
                continue
            text = f"【{prev} 阶段结论】\n"
            if "target" in c:
                text += f"  目标变量: {c['target']}\n"
            if "features" in c:
                text += f"  特征变量: {', '.join(c['features'])}\n"
            if "participating" in c:
                text += f"  参与字段: {', '.join(c['participating'])}\n"
            if "excluded" in c:
                text += f"  排除字段: {', '.join(c['excluded'])}\n"
            if "summary" in c:
                text += f"  摘要: {c['summary']}\n"
            parts.append(text.strip())
        return "\n\n".join(parts)

    def to_context_dict(self) -> dict[str, Any]:
        """序列化到 context dict 中持久化"""
        return {
            "_session_sessions": self._sessions,
            "_session_conclusions": self._conclusions,
            "_session_order": self._agent_order,
        }

    @classmethod
    def from_context_dict(cls, d: dict[str, Any]) -> SessionContext:
        """从 context dict 恢复"""
        ctx = cls()
        ctx._sessions = d.get("_session_sessions", {})
        ctx._conclusions = d.get("_session_conclusions", {})
        ctx._agent_order = d.get("_session_order", [])
        return ctx
