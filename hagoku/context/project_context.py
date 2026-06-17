# hagoku/context/project_context.py
"""ProjectContext — 一次分析 run 的统一上下文记忆。

作为 EventBus 的被动消费者（与 Scribe 平级），自动记录所有 Agent 交互。
不做任何流程控制——只记录和查询。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal

from hagoku.observability.events import EventType


@dataclass
class ToolCallRecord:
    """单次工具调用 + 结果的记录。"""
    tool_call_id: str
    name: str
    arguments: str          # JSON 字符串
    result: str             # 工具执行返回值（已 stringify）
    error: str | None = None  # 工具执行失败时填错误信息（铁律 7 失败在场——不吞）


@dataclass
class ContextEntry:
    """一条上下文记录。追加式，不可删除。"""

    type: Literal["goal", "agent_response", "user_feedback", "stage_transition", "tool_exchange"]
    stage: str                     # scout / cleaner / analyst / reporter
    revision: int                  # 阶段内轮数，从 0 开始
    timestamp: str                 # ISO-8601
    content: str                   # 人类可读摘要
    raw_user_text: str | None = None    # 律 2：用户原话（type=user_feedback 时必填）
    snapshot: dict[str, Any] | None = None  # type=agent_response / tool_exchange 时附带
    tool_calls: list[ToolCallRecord] | None = None  # 仅 type="tool_exchange" 时填


@dataclass
class ProjectContext:
    """一次分析 run 的完整上下文记忆。"""

    run_id: str
    analysis_goal: str
    entries: list[ContextEntry] = field(default_factory=list)
    _event_bus: Any = field(init=False, default=None)
    _context_ref: dict[str, Any] | None = field(init=False, default=None)
    _save_path: str | None = field(init=False, default=None)

    # ── 追加接口 ──

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _maybe_save(self) -> None:
        """如果设置了 _save_path，追加写入最后一条 entry 到 JSONL。"""
        if self._save_path and self.entries:
            import json as _json
            from pathlib import Path
            e = self.entries[-1]
            p = Path(self._save_path)
            p.parent.mkdir(parents=True, exist_ok=True)
            with open(p, "a") as f:
                f.write(_json.dumps({
                    "type": e.type,
                    "stage": e.stage,
                    "revision": e.revision,
                    "timestamp": e.timestamp,
                    "content": e.content,
                    "raw_user_text": e.raw_user_text,
                    "snapshot": e.snapshot,
                    "tool_calls": [
                        {
                            "tool_call_id": tc.tool_call_id,
                            "name": tc.name,
                            "arguments": tc.arguments,
                            "result": tc.result,
                            "error": tc.error,
                        }
                        for tc in (e.tool_calls or [])
                    ] if e.tool_calls else None,
                }, ensure_ascii=False) + "\n")

    def add_entry(self, entry: ContextEntry) -> None:
        """追加一条记录。不可删除，不可修改已有记录。"""
        self.entries.append(entry)
        self._maybe_save()

    def add_user_feedback(
        self,
        stage: str,
        revision: int,
        raw_text: str,
        content: str = "",
    ) -> None:
        """记录用户反馈（律 2：保留原话）。"""
        self.entries.append(ContextEntry(
            type="user_feedback",
            stage=stage,
            revision=revision,
            timestamp=self._now(),
            content=content or raw_text[:200],
            raw_user_text=raw_text,
        ))

    def add_agent_response(
        self,
        stage: str,
        revision: int,
        content: str,
        snapshot: dict[str, Any] | None = None,
    ) -> None:
        """记录 Agent 响应，可附带字段状态快照。"""
        self.entries.append(ContextEntry(
            type="agent_response",
            stage=stage,
            revision=revision,
            timestamp=self._now(),
            content=content,
            snapshot=snapshot,
        ))

    def add_stage_transition(self, stage: str, content: str = "") -> None:
        """记录阶段切换。"""
        self.entries.append(ContextEntry(
            type="stage_transition",
            stage=stage,
            revision=0,
            timestamp=self._now(),
            content=content or f"进入 {stage} 阶段",
        ))

    def add_tool_exchange(
        self,
        stage: str,
        revision: int,
        tool_calls: list[ToolCallRecord],
        assistant_content: str = "",
    ) -> None:
        """记录一轮 assistant tool_calls + tool results。

        序列化进 messages_history 时展开为 OpenAI 协议标准的两类 turn：
          [{"role":"assistant", "content":..., "tool_calls":[...]},
           {"role":"tool", "content":result, "tool_call_id":id}, ...]
        """
        summary_lines = []
        if assistant_content:
            summary_lines.append(assistant_content)
        for tc in tool_calls:
            line = f"→ 调用 {tc.name}({tc.arguments})"
            if tc.error:
                line += f"  ❌ 错误: {tc.error}"
            else:
                line += f"  ✓ {tc.result[:120]}"
            summary_lines.append(line)
        content_summary = "\n".join(summary_lines)

        entry = ContextEntry(
            type="tool_exchange",
            stage=stage,
            revision=revision,
            timestamp=self._now(),
            content=content_summary,
            tool_calls=tool_calls,
            snapshot={"assistant_pre_text": assistant_content} if assistant_content else None,
        )
        self.add_entry(entry)

        # emit TOOL_EXCHANGE 事件给前端
        if self._event_bus:
            self._event_bus.emit(EventType.TOOL_EXCHANGE, stage, {
                "stage": stage,
                "revision": revision,
                "timestamp": entry.timestamp,
                "assistant_pre_text": assistant_content or None,
                "tool_calls": [
                    {
                        "id": tc.tool_call_id,
                        "name": tc.name,
                        "arguments_summary": tc.arguments[:200],
                        "result_summary": tc.error or tc.result[:200],
                        "error": tc.error,
                        "duration_ms": 0,
                    }
                    for tc in tool_calls
                ],
            })

    # ── 快照生成（律 5：从 column_semantics 实时派生，不平行存储）──

    def _derive_snapshot(self, context: dict[str, Any]) -> dict[str, Any]:
        """从 context 的权威数据结构派生当前状态快照。"""
        semantics = context.get("column_semantics") or []
        fields = []
        pending = []
        for s in semantics:
            col = s.get("column_name", "")
            if not col:
                continue
            used = s.get("used_in_analysis")
            fields.append({
                "name": col,
                "display": s.get("display_name", "") or "",
                "role": s.get("suggested_role", "") or "",
                "participating": used if used is None else bool(used),
            })
            if s.get("needs_user_input"):
                pending.append(col)

        snapshot = {
            "fields": fields,
            "target": context.get("target"),
            "features": context.get("features") or [],
            "pending": pending,
        }
        if context.get("findings"):
            snapshot["findings"] = context["findings"]
        return snapshot

    # ── 上下文拼装 ──

    def build_prompt(self, agent: str, context: dict[str, Any]) -> dict[str, Any]:
        """为指定 Agent 拼装 messages_history。

        上下文保真律：动态数据（分析目标、字段状态、用户纠正）走对话历史，
        不走系统消息。LLM 自己会读对话——不需要代码替它提取"重点"。

        Returns:
            {"messages_history": list[dict]}
        """
        # 上下文保真律：不按 stage 过滤——跨阶段的 tool exchange 也必须原样保留
        # stage_transition 不进入 messages_history
        messages_history: list[dict[str, str]] = []
        for e in self.entries:
            if e.type == "user_feedback":
                text = (e.raw_user_text or e.content or "").strip()
                if text:
                    messages_history.append({"role": "user", "content": text})
            elif e.type == "agent_response":
                messages_history.append({"role": "assistant", "content": e.content})
            elif e.type == "tool_exchange":
                oai_tool_calls = [
                    {
                        "id": tc.tool_call_id,
                        "type": "function",
                        "function": {"name": tc.name, "arguments": tc.arguments},
                    }
                    for tc in (e.tool_calls or [])
                ]
                assist_turn: dict = {"role": "assistant", "tool_calls": oai_tool_calls}
                pre_text = (e.snapshot or {}).get("assistant_pre_text", "")
                if pre_text:
                    assist_turn["content"] = pre_text
                messages_history.append(assist_turn)
                for tc in (e.tool_calls or []):
                    messages_history.append({
                        "role": "tool",
                        "content": tc.error or tc.result,
                        "tool_call_id": tc.tool_call_id,
                    })

        return {
            "messages_history": messages_history,
        }

    # ── LLM messages 统一入口 ──

    def to_messages_for_llm(
        self,
        agent: str,
        context: dict[str, Any],
        user_input: str,
        *,
        agent_system_extra: str = "",
    ) -> list[dict[str, Any]]:
        """打通 ProjectContext → build_messages 的链路。

        任何 agent 调 LLM 时，调这一个方法即可，禁止手动拼装。

        agent_system_extra 用于注入 agent 自身的 prompt.md / phase_id / cleaning_rules 等
        ——这些是 agent 域指令，与 ProjectContext 的 system_prefix（分析目标+字段状态）分开。
        """
        from hagoku.channel import build_messages

        parts = self.build_prompt(agent, context)
        # 上下文保真律：动态数据（分析目标、字段状态、用户纠正）走对话历史。
        # 系统消息只放 agent 指令（prompt.md）。LLM 自己会读对话——不需要代码替它提取"重点"。
        return build_messages(
            query=self.analysis_goal,
            user_input=user_input,
            history=parts["messages_history"],
            system_extra=agent_system_extra,
        )

    # ── EventBus 集成 ──

    def set_context_ref(self, context_ref: dict[str, Any] | None) -> None:
        """供 orchestrator 在 context dict 就绪后补充设置。"""
        self._context_ref = context_ref

    def subscribe(self, event_bus: Any, context_ref: dict[str, Any] | None = None) -> None:
        """注册为 EventBus 消费者。context_ref 是 orchestrator 的 context dict 引用。"""
        self._event_bus = event_bus
        self._context_ref = context_ref
        event_bus.subscribe(self._on_event)

    def _on_event(self, event: Any) -> None:
        """EventBus 回调：监听关键事件并自动记录。"""
        etype = event.event_type
        agent = event.agent
        data = event.data or {}

        if etype == EventType.AGENT_STARTED:
            self.add_stage_transition(
                stage=agent,
                content=data.get("goal", f"{agent} 开始"),
            )

        elif etype == EventType.AGENT_COMPLETED:
            # 真实 LLM 文本已由 run_step/run_scout_phase 显式写入。
            # 此处不重复写入，避免 status string 覆盖真实输出。
            pass

        elif etype == EventType.USER_INPUT_RECEIVED:
            if self._context_ref is None:
                raise RuntimeError("ProjectContext._context_ref 未设置，信息通道断裂")
            ctx = self._context_ref
            revision = ctx.get("interaction_revision", 0) if ctx else 0
            raw = data.get("reply", "")
            self.add_user_feedback(
                stage=agent,
                revision=revision,
                raw_text=raw,
                content=raw[:200] if raw else "",
            )

    # ── 持久化（阶段 3：crash 恢复）──────────────────────────

    def save_jsonl(self, path: str) -> None:
        """追加式写入 JSONL。每行一个 entry 的 JSON 序列化。"""
        import json as _json
        from pathlib import Path

        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w") as f:
            for e in self.entries:
                f.write(_json.dumps({
                    "type": e.type,
                    "stage": e.stage,
                    "revision": e.revision,
                    "timestamp": e.timestamp,
                    "content": e.content,
                    "raw_user_text": e.raw_user_text,
                    "snapshot": e.snapshot,
                    "tool_calls": [
                        {
                            "tool_call_id": tc.tool_call_id,
                            "name": tc.name,
                            "arguments": tc.arguments,
                            "result": tc.result,
                            "error": tc.error,
                        }
                        for tc in (e.tool_calls or [])
                    ] if e.tool_calls else None,
                }, ensure_ascii=False) + "\n")

    @classmethod
    def load_jsonl(cls, path: str, run_id: str, analysis_goal: str) -> "ProjectContext":
        """从 JSONL 文件恢复 ProjectContext。"""
        import json as _json
        from pathlib import Path

        ctx = cls(run_id=run_id, analysis_goal=analysis_goal)
        p = Path(path)
        if not p.exists():
            return ctx
        with open(p) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                d = _json.loads(line)
                tool_calls_raw = d.get("tool_calls")
                tool_calls = None
                if tool_calls_raw:
                    tool_calls = [
                        ToolCallRecord(
                            tool_call_id=tc["tool_call_id"],
                            name=tc["name"],
                            arguments=tc["arguments"],
                            result=tc["result"],
                            error=tc.get("error"),
                        )
                        for tc in tool_calls_raw
                    ]
                ctx.entries.append(ContextEntry(
                    type=d["type"],
                    stage=d["stage"],
                    revision=d["revision"],
                    timestamp=d["timestamp"],
                    content=d["content"],
                    raw_user_text=d.get("raw_user_text"),
                    snapshot=d.get("snapshot"),
                    tool_calls=tool_calls,
                ))
        return ctx
