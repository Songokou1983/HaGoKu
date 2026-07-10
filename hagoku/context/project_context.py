# hagoku/context/project_context.py
"""[DEPRECATED] 生产代码已迁移到 Session (context/session.py)。

本文件是兼容层——ProjectContext 继承 Session，保留旧方法名作为别名。
新代码请直接使用 Session。
"""
from __future__ import annotations

from typing import Any

from hagoku.context.session import Session, ToolCallRecord  # noqa: F401


class ProjectContext(Session):
    """[DEPRECATED] 兼容层。"""

    def __init__(self, *, run_id: str = "", analysis_goal: str = "", **kwargs: Any) -> None:
        super().__init__(analysis_goal=analysis_goal, **kwargs)

    @property
    def entries(self) -> list[Any]:
        """兼容旧代码的 .entries 访问——从 messages 构造简单对象。"""
        result = []
        for m in self.messages:
            role = m.get("role", "")
            content = m.get("content", "")
            tc_data = m.get("tool_calls")
            entry = type("_Entry", (), {
                "type": "user_feedback" if role == "user" else
                        "agent_response" if role == "assistant" and not tc_data else
                        "tool_exchange" if tc_data else "stage_transition",
                "stage": "scout",
                "revision": 0,
                "timestamp": "",
                "content": content,
                "raw_user_text": content if role == "user" else None,
                "snapshot": {"assistant_pre_text": content} if tc_data else None,
                "tool_calls": [
                    ToolCallRecord(
                        tool_call_id=tc.get("id", ""),
                        name=tc.get("function", {}).get("name", ""),
                        arguments=tc.get("function", {}).get("arguments", ""),
                        result="",
                    ) for tc in (tc_data or [])
                ] if tc_data else None,
            })()
            result.append(entry)
        return result

    # ── 旧方法别名 ──

    def to_messages_for_llm(self, agent: str = "", context: dict | None = None,
                            user_input: str = "", *,
                            agent_system_extra: str = "") -> list[dict[str, Any]]:
        return super().to_llm_messages(system_extra=agent_system_extra, user_input=user_input)

    def add_user_feedback(self, stage: str = "", revision: int = 0,
                          raw_text: str = "", content: str = "") -> None:
        super().add("user", raw_text or content)

    def add_stage_transition(self, stage: str = "", content: str = "") -> None:
        self.add("system", f"[进入 {stage} 阶段] {content}".strip())

    def add_agent_response(self, stage: str = "", revision: int = 0,
                           content: str = "", snapshot: Any = None) -> None:
        super().add("assistant", content)

    def add_tool_exchange(self, stage: str = "", revision: int = 0,
                          tool_calls: list | None = None,
                          assistant_content: str = "") -> None:
        if tool_calls:
            oai_calls = [{
                "id": tc.tool_call_id,
                "type": "function",
                "function": {"name": tc.name, "arguments": tc.arguments},
            } for tc in tool_calls]
            results = [{
                "content": tc.error or tc.result,
                "tool_call_id": tc.tool_call_id,
            } for tc in tool_calls]
            super().add_tool_call(assistant_content, oai_calls, results)

    def build_prompt(self, agent: str = "", context: dict | None = None) -> dict[str, Any]:
        return {"messages_history": list(self.messages)}

    def subscribe(self, event_bus: Any = None, context_ref: Any = None) -> None:
        if event_bus:
            event_bus.subscribe(self._on_event)

    def _on_event(self, event: Any) -> None:
        """兼容旧测试的 EventBus 回调。"""
        etype_val = getattr(event, "event_type", None)
        etype = etype_val.value if hasattr(etype_val, "value") else str(etype_val)
        data = getattr(event, "data", None) or {}
        if etype == "user_input_received":
            raw = data.get("reply", "")
            self.add_user_feedback(raw_text=raw)

    def set_context_ref(self, *args: Any, **kwargs: Any) -> None:
        pass

    def save_jsonl(self, path: str) -> None:
        self.save(path)

    @classmethod
    def load_jsonl(cls, path: str, run_id: str = "", analysis_goal: str = "") -> "ProjectContext":
        obj = cls(run_id=run_id, analysis_goal=analysis_goal)
        loaded = Session.load(path, analysis_goal=analysis_goal)
        obj.messages = loaded.messages
        obj.analysis_goal = loaded.analysis_goal
        return obj
