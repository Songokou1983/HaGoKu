"""Session — 一次分析就是一场会话。

会话 = messages 数组 [{role, content}]
没有 entry 类型、没有 build_prompt 翻译层、没有 _maybe_save 选择性持久化。

消息直接以 OpenAI 格式存储：role + content + 可选的 tool_calls/tool_call_id。
存盘就是 JSON，加载就是 messages。
"""

from __future__ import annotations

import json as _json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class ToolCallRecord:
    """单次工具调用 + 结果的记录。"""
    tool_call_id: str
    name: str
    arguments: str
    result: str
    error: str | None = None


@dataclass
class Session:
    """一次分析会话。"""

    analysis_goal: str
    messages: list[dict[str, Any]] = field(default_factory=list)
    _save_path: str | None = field(default=None, repr=False)

    # ── 消息操作 ──

    def add(self, role: str, content: str = "", **extra: Any) -> None:
        """追加一条消息。"""
        msg: dict[str, Any] = {"role": role}
        if content:
            msg["content"] = content
        msg.update(extra)
        self.messages.append(msg)
        self._maybe_save()

    def add_tool_call(
        self,
        assistant_text: str,
        tool_calls: list[dict[str, Any]],
        tool_results: list[dict[str, Any]],
    ) -> None:
        """追加一轮 tool exchange：assistant(tool_calls) + tool results。"""
        assist: dict[str, Any] = {"role": "assistant", "tool_calls": tool_calls}
        if assistant_text:
            assist["content"] = assistant_text
        self.messages.append(assist)
        for tr in tool_results:
            self.messages.append({
                "role": "tool",
                "content": tr.get("content", ""),
                "tool_call_id": tr.get("tool_call_id", ""),
            })
        self._maybe_save()

    # ── LLM 调用 ──

    def to_llm_messages(
        self,
        system_extra: str = "",
        user_input: str = "",
    ) -> list[dict[str, Any]]:
        """构建发给 LLM 的完整 messages。"""
        from hagoku.channel import build_messages

        return build_messages(
            query=self.analysis_goal,
            user_input=user_input,
            history=list(self.messages),
            system_extra=system_extra,
        )

    # ── 持久化 ──

    def _maybe_save(self) -> None:
        if self._save_path:
            self.save(self._save_path)

    def save(self, path: str) -> None:
        """保存到 JSON 文件（原子写入，崩溃不损坏）。"""
        import os as _os
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(p.suffix + ".tmp")
        tmp.write_text(
            _json.dumps({
                "analysis_goal": self.analysis_goal,
                "messages": self.messages,
            }, ensure_ascii=False, default=str),
            encoding="utf-8",
        )
        _os.replace(tmp, p)

    @classmethod
    def load(cls, path: str, analysis_goal: str = "") -> "Session":
        """从 JSON 文件加载。"""
        p = Path(path)
        if not p.exists():
            return cls(analysis_goal=analysis_goal)
        data = _json.loads(p.read_text(encoding="utf-8"))
        session = cls(
            analysis_goal=data.get("analysis_goal", analysis_goal),
            messages=data.get("messages", []),
        )
        session._save_path = str(p)
        return session
