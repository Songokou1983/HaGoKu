# hagoku/context/project_context.py
"""ProjectContext — 一次分析 run 的统一上下文记忆。

作为 EventBus 的被动消费者（与 Scribe 平级），自动记录所有 Agent 交互。
不做任何流程控制——只记录和查询。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal


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

    # ── 追加接口 ──

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
            timestamp=datetime.now(timezone.utc).isoformat(),
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
            timestamp=datetime.now(timezone.utc).isoformat(),
            content=content,
            snapshot=snapshot,
        ))

    def add_stage_transition(self, stage: str, content: str = "") -> None:
        """记录阶段切换。"""
        self.entries.append(ContextEntry(
            type="stage_transition",
            stage=stage,
            revision=0,
            timestamp=datetime.now(timezone.utc).isoformat(),
            content=content or f"进入 {stage} 阶段",
        ))

    # ── 快照生成（律 5：从 column_semantics 实时派生，不平行存储）──

    def _derive_snapshot(self, context: dict[str, Any]) -> dict[str, Any]:
        """从 context 的权威数据结构派生当前状态快照。"""
        semantics = context.get("column_semantics") or []
        fields = []
        pending = []
        for s in semantics:
            col = str(s.get("column_name", ""))
            if not col:
                continue
            fields.append({
                "name": col,
                "display": str(s.get("display_name", "") or ""),
                "role": str(s.get("suggested_role", "") or ""),
                "participating": bool(s.get("used_in_analysis")) if s.get("used_in_analysis") is not None else None,
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
            {"system_prefix": str, "history_context": str}
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

        # 2. history_context：当前阶段的对话历史 + 上游阶段快照摘要
        current_stage_entries = [e for e in self.entries if e.stage == agent]
        upstream_entries = [e for e in self.entries if e.stage != agent]

        history_parts: list[str] = []

        # 上游阶段：仅保留 agent_response 的 snapshot 摘要
        if upstream_entries:
            history_parts.append("【上游阶段摘要】")
            for e in upstream_entries:
                if e.type == "agent_response" and e.snapshot:
                    t = e.snapshot.get("target", "")
                    f = e.snapshot.get("features", [])
                    p = e.snapshot.get("pending", [])
                    summary = f"{e.stage} 阶段完成: target={t}, features={f}"
                    if p:
                        summary += f", 待确认={p}"
                    history_parts.append(summary)
                elif e.type == "stage_transition":
                    history_parts.append(f"→ {e.content}")
            history_parts.append("")

        # 当前阶段：完整对话历史
        if current_stage_entries:
            history_parts.append(f"【{agent} 阶段对话】")
            for e in current_stage_entries:
                if e.type == "user_feedback":
                    history_parts.append(f"用户: {e.raw_user_text or e.content}")
                elif e.type == "agent_response":
                    history_parts.append(f"Agent: {e.content}")
                elif e.type == "stage_transition":
                    history_parts.append(f"── {e.content} ──")
            history_parts.append("")

        history_context = "\n".join(history_parts)

        return {
            "system_prefix": system_prefix,
            "history_context": history_context,
        }

    # ── EventBus 集成 ──

    def subscribe(self, event_bus: Any, context_ref: dict[str, Any] | None = None) -> None:
        """注册为 EventBus 消费者。context_ref 是 orchestrator 的 context dict 引用。"""
        self._event_bus = event_bus
        self._context_ref = context_ref
        event_bus.subscribe(self._on_event)

    def _on_event(self, event: Any) -> None:
        """EventBus 回调：监听关键事件并自动记录。"""
        from hagoku.observability.events import EventType

        etype = event.event_type
        agent = event.agent
        data = event.data or {}

        if etype == EventType.AGENT_STARTED:
            self.add_stage_transition(
                stage=agent,
                content=data.get("goal", f"{agent} 开始"),
            )

        elif etype == EventType.AGENT_COMPLETED:
            ctx = getattr(self, "_context_ref", {}) or {}
            snapshot = self._derive_snapshot(ctx) if ctx else None
            revision = ctx.get("interaction_revision", 0) if ctx else 0
            self.add_agent_response(
                stage=agent,
                revision=revision,
                content=data.get("result_summary", data.get("message", f"{agent} 完成")),
                snapshot=snapshot,
            )

        elif etype == EventType.USER_INPUT_RECEIVED:
            ctx = getattr(self, "_context_ref", {}) or {}
            revision = ctx.get("interaction_revision", 0) if ctx else 0
            raw = data.get("reply", "")
            self.add_user_feedback(
                stage=agent,
                revision=revision,
                raw_text=raw,
                content=raw[:200] if raw else "",
            )
