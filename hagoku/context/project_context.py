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
class ContextEntry:
    """一条上下文记录。追加式，不可删除。"""

    type: Literal["goal", "agent_response", "user_feedback", "stage_transition"]
    stage: str                     # scout / cleaner / analyst / reporter
    revision: int                  # 阶段内轮数，从 0 开始
    timestamp: str                 # ISO-8601
    content: str                   # 人类可读摘要
    raw_user_text: str | None = None    # 律 2：用户原话（type=user_feedback 时必填）
    snapshot: dict[str, Any] | None = None  # type=agent_response 时附带


@dataclass
class ProjectContext:
    """一次分析 run 的完整上下文记忆。"""

    run_id: str
    analysis_goal: str
    entries: list[ContextEntry] = field(default_factory=list)
    _event_bus: Any = field(init=False, default=None)
    _context_ref: dict[str, Any] | None = field(init=False, default=None)

    # ── 追加接口 ──

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def add_entry(self, entry: ContextEntry) -> None:
        """追加一条记录。不可删除，不可修改已有记录。"""
        self.entries.append(entry)

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

        return {
            "fields": fields,
            "target": context.get("target"),
            "features": context.get("features") or [],
            "pending": pending,
        }

    # ── 上下文拼装 ──

    def build_prompt(self, agent: str, context: dict[str, Any]) -> dict[str, str]:
        """为指定 Agent 拼装上下文注入块。

        Returns:
            {"system_prefix": str, "upstream_summary": str, "messages_history": list[dict]}
        """
        # 1. system_prefix：分析目标 + 当前字段状态 + 角色 + 命令上下文
        snapshot = self._derive_snapshot(context)
        target = snapshot.get("target") or "（未设置）"
        features = snapshot.get("features") or []
        pending = snapshot.get("pending") or []
        cmd_text = (context.get("_pending_command_text") or "").strip()

        lines = [
            f"分析目标: {self.analysis_goal}",
            "",
            "当前字段状态:",
        ]
        for f in snapshot.get("fields", []):
            status = "参与" if f["participating"] is True else ("不参与" if f["participating"] is False else "待定")
            lines.append(f"  {f['name']}({f['display']}): {status}  role={f['role']}")

        lines.extend([
            "",
            f"目标变量: {target}",
            f"特征变量: {', '.join(features) if features else '（未设置）'}",
        ])
        if pending:
            lines.append(f"待确认字段: {', '.join(pending)}")
        if cmd_text:
            lines.extend(["", f"用户指令: {cmd_text}"])

        system_prefix = "\n".join(lines)

        # ── upstream_summary：上游阶段结构化快照 ──
        upstream_entries = [e for e in self.entries if e.stage != agent]
        upstream_parts: list[str] = []
        for e in upstream_entries:
            if e.type == "agent_response" and e.snapshot:
                t = e.snapshot.get("target", "")
                f = e.snapshot.get("features", [])
                p = e.snapshot.get("pending", [])
                summary = f"{e.stage} 阶段完成: target={t}, features={f}"
                if p:
                    summary += f", 待确认={p}"
                upstream_parts.append(summary)
        upstream_summary = "【上游阶段摘要】\n" + "\n".join(upstream_parts) if upstream_parts else ""

        # ── messages_history：标准 messages list（律 3）──
        # stage_transition 不进入 messages_history
        current_stage_entries = [e for e in self.entries if e.stage == agent]
        messages_history: list[dict[str, str]] = []
        for e in current_stage_entries:
            if e.type == "user_feedback":
                messages_history.append({"role": "user", "content": e.raw_user_text or e.content})
            elif e.type == "agent_response":
                messages_history.append({"role": "assistant", "content": e.content})

        return {
            "system_prefix": system_prefix,
            "upstream_summary": upstream_summary,
            "messages_history": messages_history,
        }

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
            if self._context_ref is None:
                logging.warning("ProjectContext._context_ref is None, using empty dict")
                ctx = {}
            else:
                ctx = self._context_ref
            snapshot = self._derive_snapshot(ctx) if ctx else None
            revision = ctx.get("interaction_revision", 0) if ctx else 0
            self.add_agent_response(
                stage=agent,
                revision=revision,
                content=data.get("result_summary", data.get("message", f"{agent} 完成")),
                snapshot=snapshot,
            )

        elif etype == EventType.USER_INPUT_RECEIVED:
            if self._context_ref is None:
                logging.warning("ProjectContext._context_ref is None, using empty dict")
                ctx = {}
            else:
                ctx = self._context_ref
            revision = ctx.get("interaction_revision", 0) if ctx else 0
            raw = data.get("reply", "")
            self.add_user_feedback(
                stage=agent,
                revision=revision,
                raw_text=raw,
                content=raw[:200] if raw else "",
            )
