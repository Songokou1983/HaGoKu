"""Agent 交互基类 — 双方法接口 begin()/respond()

每个 Agent 继承 InteractionMixin，实现 _run_until_pause()。
begin()/respond() 内部管理 phase 状态机，支持暂停等用户确认。
"""

from __future__ import annotations

from typing import Any

from .types import InteractionResult


class InteractionMixin:
    """
    交互混入类。

    提供 begin()/respond() 双方法接口，内部管理 phase 状态机。
    子类实现 _run_until_pause()，返回 (phase, pending_items) 或 None（完成）。

    看板集成：
    - begin() 时自动 claim_task（通过 scribe）
    - 需要确认时自动 block_task
    - respond() 时自动 unblock_task
    """

    _phase: str = "begin"
    _pending_data: dict[str, Any] = {}

    def begin(self, **kwargs) -> InteractionResult:
        """开始或继续，返回暂停点或最终结果"""
        raise NotImplementedError

    def respond(self, user_input: str | dict, **kwargs) -> InteractionResult:
        """处理用户输入，继续流程"""
        raise NotImplementedError

    def _pause(
        self,
        phase: str,
        message: str,
        needs_confirmation: bool = False,
        confirmation_prompt: str = "",
        pending_items: list[dict[str, Any]] | None = None,
        data: dict[str, Any] | None = None,
    ) -> InteractionResult:
        """Agent 主动暂停，等用户响应"""
        return InteractionResult(
            phase=phase,
            message=message,
            data=data or {},
            actions=[],
            final=False,
            needs_confirmation=needs_confirmation,
            confirmation_prompt=confirmation_prompt,
            pending_items=pending_items or [],
        )

    def _done(self, phase: str, message: str, data: dict[str, Any] | None = None) -> InteractionResult:
        """Agent 完成"""
        return InteractionResult(
            phase=phase,
            message=message,
            data=data or {},
            actions=[],
            final=True,
            needs_confirmation=False,
            confirmation_prompt="",
            pending_items=[],
        )
