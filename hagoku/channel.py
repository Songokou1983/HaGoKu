"""通道函数 — 所有 Agent 调用 LLM 时的统一 messages 构造入口。

铁律 11（通道优先律）+ 通道守门（Phase 0）：
禁止任何代码直接构造 messages = [...]。必须通过此模块的函数。
只追加，不筛选、不删减、不重排。

Phase B (CO-B1) 升级：
- ChatTurn TypedDict 支持 OpenAI tool 标准协议（assistant.tool_calls + tool.tool_call_id）
- _ChatTurnValidator 按 role 验证字段组合
- BuildMessagesInput 顶层未知字段拒绝
- system_extra 默认空串（消除 "传 None vs 空" 的歧义）
"""

from __future__ import annotations

from typing import Literal, TypedDict

from pydantic import BaseModel, Field, model_validator

# ── TypedDict 定义（设计稿 §2.2）──────────────────────────────

class ToolCallFunction(TypedDict):
    """OpenAI tool_call 的 function 子字段。"""
    name: str
    arguments: str  # JSON 字符串


class ToolCall(TypedDict):
    """OpenAI tool_call 标准格式。"""
    id: str
    type: Literal["function"]
    function: ToolCallFunction


class ChatTurn(TypedDict, total=False):
    """LLM 消息单元的严格类型。

    role 必填；content / tool_calls / tool_call_id 按 role 选择性必填：
    - role="system" / "user"        → content 必填
    - role="assistant"              → content 与 tool_calls 至少一个非空
    - role="tool"                   → content + tool_call_id 必填
    """
    role: Literal["system", "user", "assistant", "tool"]
    content: str
    tool_calls: list[ToolCall]          # 仅 role=assistant 时允许
    tool_call_id: str                   # 仅 role=tool 时必填


# ── Pydantic 校验器（设计稿 §2.2）────────────────────────────

class _ChatTurnValidator(BaseModel):
    """逐条 turn 的语义校验（role 与字段的对应规则）。"""
    model_config = {"extra": "forbid"}

    role: Literal["system", "user", "assistant", "tool"]
    content: str | None = None
    tool_calls: list[dict] | None = None
    tool_call_id: str | None = None

    @model_validator(mode="after")
    def _check_role_field_rules(self):
        if self.role in ("system", "user"):
            if self.content is None or not self.content.strip():
                raise ValueError(f"role={self.role} 的 turn content 必须非空")
            if self.tool_calls or self.tool_call_id:
                raise ValueError(f"role={self.role} 不允许 tool_calls/tool_call_id")
        elif self.role == "assistant":
            if not self.content and not self.tool_calls:
                raise ValueError("role=assistant 的 turn 必须有 content 或 tool_calls")
            if self.tool_call_id:
                raise ValueError("role=assistant 不允许 tool_call_id")
        elif self.role == "tool":
            if not self.content:
                raise ValueError("role=tool 的 turn content 必须非空")
            if not self.tool_call_id:
                raise ValueError("role=tool 的 turn 必须有 tool_call_id")
            if self.tool_calls:
                raise ValueError("role=tool 不允许 tool_calls")
        return self


class BuildMessagesInput(BaseModel):
    """build_messages() 的严格输入 schema（未知顶层字段被拒绝）。"""
    model_config = {"extra": "forbid", "frozen": True}

    query: str = Field(..., description="第一条 user 消息，永不删除")
    user_input: str = Field(..., description="最后一条 user 消息")
    history: list[ChatTurn] = Field(default_factory=list, description="中间历史，逐条按 role 规则验证")
    system_extra: str = Field(default="", description="可选 system 前缀")

    @model_validator(mode="after")
    def _validate_history(self):
        for i, turn in enumerate(self.history):
            try:
                _ChatTurnValidator(**turn)
            except Exception as e:
                raise ValueError(f"history[{i}] 不符合 ChatTurn 规则: {e}") from e
        return self


# ── 核心函数 ────────────────────────────────────────────────

def build_messages(
    *,
    query: str,
    user_input: str,
    history: list[ChatTurn] | None = None,
    system_extra: str = "",
) -> list[ChatTurn]:
    """构建发给 LLM 的 messages — 唯一合法入口。

    与升级前的区别：
    1. history 支持 OpenAI 标准 tool 协议（assistant.tool_calls + tool.tool_call_id）
    2. 内部用 BuildMessagesInput + _ChatTurnValidator 做严格校验
    3. role/字段组合不合法 → ValidationError（带详细错误位置）
    4. system_extra 默认空串而非 None（消除"传 None vs 空"的歧义）
    """
    validated = BuildMessagesInput(
        query=query,
        user_input=user_input,
        history=list(history or []),
        system_extra=system_extra,
    )
    msgs: list[ChatTurn] = []
    if validated.system_extra:
        msgs.append({"role": "system", "content": validated.system_extra})
    msgs.append({"role": "user", "content": validated.query})
    msgs.extend(validated.history)
    msgs.append({"role": "user", "content": validated.user_input})
    return msgs
