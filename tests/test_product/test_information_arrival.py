"""信息抵达正向契约 — 落实 PROJECT.md「刹车 4」与「通道完备性十律」中的律 1、2、3、6。

本文件断言「代码看起来合规、但信息没到 LLM」这种 B 类语义漏水永远会被测试捕获。
三条契约：
  - 律 1（意图穿透）：每个 Agent 的每一次 LLM 调用，prompt 必须包含 `query`。
  - 律 2（原话抵达）：用户输入的 raw_text 必须出现在下一次 LLM 调用的 messages 中。
  - 律 3（多轮历史）：同一暂停点的第 N 轮 LLM 调用，messages 含前 N-1 轮历史（占位，待 P3 实施）。

变更暂停/用户输入路径时须跑：
  pytest tests/test_product/test_information_arrival.py -q
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest


# ─────────────────────────────────────────────────────────────────────────────
# 通用 spy：录制所有 chat.completions.create 调用，便于断言 messages 内容
# ─────────────────────────────────────────────────────────────────────────────

class LLMSpy:
    """录制 LLM 调用的 messages、tools、model；可断言任意 substring 是否抵达。

    用法：
        spy = LLMSpy(response_factory=lambda messages: <mock response>)
        _apply_scout_reply_with_llm(ctx, "raw text", cols, spy.client, "model")
        assert spy.contains_in_any_message("raw text")
    """

    def __init__(self, *, response_factory=None) -> None:
        self.calls: list[dict[str, Any]] = []
        self._response_factory = response_factory or self._default_response

    @staticmethod
    def _default_response(messages: list[dict[str, Any]]) -> Any:  # noqa: ARG004
        # 默认返回「未理解」响应：无 tool_calls、content 为空
        resp = MagicMock()
        resp.choices = [MagicMock()]
        resp.choices[0].message = MagicMock()
        resp.choices[0].message.tool_calls = None
        resp.choices[0].message.content = ""
        return resp

    @property
    def client(self) -> Any:
        spy = self

        class _Client:
            class chat:  # noqa: N801
                class completions:  # noqa: N801
                    @staticmethod
                    def create(*, model: str, messages: list[dict[str, Any]], **kwargs: Any) -> Any:
                        spy.calls.append({"model": model, "messages": messages, "kwargs": kwargs})
                        return spy._response_factory(messages)

        return _Client()

    # ── 断言辅助 ──────────────────────────────────────────────
    def all_messages_text(self) -> str:
        """所有调用的所有消息内容拼起来的大字符串，便于子串查找。"""
        parts: list[str] = []
        for call in self.calls:
            for msg in call.get("messages") or []:
                content = msg.get("content", "")
                if isinstance(content, str):
                    parts.append(content)
        return "\n".join(parts)

    def contains_in_any_message(self, needle: str) -> bool:
        return needle in self.all_messages_text()

    def call_count(self) -> int:
        return len(self.calls)


# ─────────────────────────────────────────────────────────────────────────────
# 律 1 + 律 2：Scout 字段纠错通道 `_apply_scout_reply_with_llm`
# ─────────────────────────────────────────────────────────────────────────────

def test_律2_scout字段纠错_用户原话抵达LLM():
    """用户原话 raw 必须出现在 _apply_scout_reply_with_llm 发给 LLM 的 messages 中。"""
    from hagoku.manager.orchestrator import _apply_scout_reply_with_llm

    ctx: dict[str, Any] = {
        "query": "分析每个店铺的收入增长趋势",
        "column_semantics": [{"column_name": "Inc1", "needs_user_input": True}],
        "column_descriptions": {},
        "column_display_names": {},
    }
    spy = LLMSpy()
    raw_user = "Inc1 代表店铺收入，不是其它意思"

    _apply_scout_reply_with_llm(ctx, raw_user, ["Inc1"], spy.client, "test-model")

    assert spy.call_count() == 1, "Scout 字段纠错通道必须恰好调用 LLM 一次"
    assert spy.contains_in_any_message(raw_user), (
        "律 2 违反：用户原话「{raw}」未抵达 LLM。\n"
        "实际 messages 内容:\n{actual}"
    ).format(raw=raw_user, actual=spy.all_messages_text()[:500])


def test_律1_scout字段纠错_分析意图抵达LLM():
    """context.query（分析意图）必须出现在 _apply_scout_reply_with_llm 的 LLM messages 中。"""
    from hagoku.manager.orchestrator import _apply_scout_reply_with_llm

    intent = "分析每个店铺的收入增长趋势"
    ctx: dict[str, Any] = {
        "query": intent,
        "column_semantics": [{"column_name": "Inc1", "needs_user_input": True}],
        "column_descriptions": {},
        "column_display_names": {},
    }
    spy = LLMSpy()
    _apply_scout_reply_with_llm(ctx, "Inc1 是销售额", ["Inc1"], spy.client, "test-model")

    assert spy.contains_in_any_message(intent), (
        "律 1 违反：分析意图「{intent}」未抵达 Scout 字段纠错的 LLM prompt。\n"
        "实际 messages 内容:\n{actual}"
    ).format(intent=intent, actual=spy.all_messages_text()[:500])


def test_律1_scout字段纠错_空意图时不强制抵达():
    """若 context.query 为空，律 1 不约束（无意图可送）；不应抛错也不该假装注入。"""
    from hagoku.manager.orchestrator import _apply_scout_reply_with_llm

    ctx: dict[str, Any] = {
        "query": "",
        "column_semantics": [{"column_name": "Inc1", "needs_user_input": True}],
        "column_descriptions": {},
        "column_display_names": {},
    }
    spy = LLMSpy()
    _apply_scout_reply_with_llm(ctx, "Inc1 是销售额", ["Inc1"], spy.client, "test-model")
    # 只要 LLM 仍被调用、用户原话抵达即可
    assert spy.call_count() == 1
    assert spy.contains_in_any_message("Inc1 是销售额")


# ─────────────────────────────────────────────────────────────────────────────
# 律 2：用户意图判定通道 `_detect_user_intent_via_llm`
# ─────────────────────────────────────────────────────────────────────────────

def test_律2_用户意图判定_用户原话抵达LLM():
    """_detect_user_intent_via_llm 必须把用户原话送进 LLM messages。"""
    from hagoku.manager.orchestrator import _detect_user_intent_via_llm

    raw_user = "等等，先回去改下 Inc1 的角色"

    def _resp(messages: list[dict[str, Any]]) -> Any:  # noqa: ARG001
        resp = MagicMock()
        resp.choices = [MagicMock()]
        resp.choices[0].message = MagicMock()
        resp.choices[0].message.content = '{"intent": "modify"}'
        return resp

    spy = LLMSpy(response_factory=_resp)
    is_confirm = _detect_user_intent_via_llm(
        raw_user, spy.client, "test-model", stage="scout"
    )

    assert is_confirm is False  # LLM 返回 modify
    assert spy.contains_in_any_message(raw_user), (
        "律 2 违反：用户原话未抵达意图判定 LLM。\n"
        "实际 messages:\n{actual}"
    ).format(actual=spy.all_messages_text()[:500])


# ─────────────────────────────────────────────────────────────────────────────
# 律 1：Scout 首次字段推断 `_infer_all_semantics`（端到端 mock）
# ─────────────────────────────────────────────────────────────────────────────

def test_律1_scout首次推断_分析意图抵达LLM():
    """ScoutAgent._infer_all_semantics 调用 LLM 时，user_query 必须出现在 messages 中。"""
    import pandas as pd
    from hagoku.agents.scout.agent import ScoutAgent
    from hagoku.config import HaGoKuConfig

    df = pd.DataFrame({"Inc1": [100, 200, 300], "Period": [1, 2, 3]})
    intent = "分析每个店铺收入的增长趋势"

    cfg = HaGoKuConfig()
    agent = ScoutAgent(cfg.llm, event_bus=MagicMock())

    spy = LLMSpy(
        response_factory=lambda messages: _make_tool_call_response(
            '{"columns": [{"name": "Inc1", "inferred_type": "numeric"}, '
            '{"name": "Period", "inferred_type": "ordinal"}]}'
        )
    )

    # patch raw client 工厂（在 _infer_all_semantics 内 from ...llm.client import create_raw_client）
    import hagoku.llm.client as llm_client_mod

    original = llm_client_mod.create_raw_client
    llm_client_mod.create_raw_client = lambda _cfg: spy.client  # type: ignore[assignment]
    try:
        agent._infer_all_semantics(df, intent, memory_project=None)
    finally:
        llm_client_mod.create_raw_client = original  # type: ignore[assignment]

    assert spy.call_count() >= 1
    assert spy.contains_in_any_message(intent), (
        "律 1 违反：Scout 首次字段推断 LLM prompt 中找不到分析意图「{intent}」。\n"
        "messages 摘要（前 800 字）:\n{actual}"
    ).format(intent=intent, actual=spy.all_messages_text()[:800])


def _make_tool_call_response(arguments_json: str) -> Any:
    """构造 OpenAI 风格的 tool_call 响应。"""
    resp = MagicMock()
    resp.choices = [MagicMock()]
    msg = MagicMock()
    msg.content = ""
    tc = MagicMock()
    tc.function = MagicMock()
    tc.function.arguments = arguments_json
    msg.tool_calls = [tc]
    resp.choices[0].message = msg
    return resp


# ─────────────────────────────────────────────────────────────────────────────
# 律 3：多轮历史抵达（占位 — 待 P3 message-history 改造完成后激活）
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.xfail(
    reason="律 3 待 P3 实施：当前 _apply_scout_reply_with_llm 每轮独立调用，未带前一轮 LLM 输出。",
    strict=False,
)
def test_律3_scout多轮纠错_前一轮LLM输出抵达本轮():
    """同一暂停点第 2 轮 LLM 调用，messages 应含第 1 轮的 assistant turn。

    当前实现：每轮都是 system+user 两条消息，无历史累积。
    P3 改造后：第 2 轮 messages = [system, user_1, assistant_1, user_2]。
    """
    from hagoku.manager.orchestrator import _apply_scout_reply_with_llm

    ctx: dict[str, Any] = {
        "query": "分析每个店铺的收入增长趋势",
        "column_semantics": [{"column_name": "Inc1", "needs_user_input": True}],
        "column_descriptions": {},
        "column_display_names": {},
    }

    # 第 1 轮：LLM 调用 tool 把 Inc1 标为「收入」
    spy = LLMSpy(
        response_factory=lambda messages: _make_tool_call_response(
            '{"column_name": "Inc1", "display_name": "收入"}'
        )
    )
    _apply_scout_reply_with_llm(ctx, "Inc1 是收入", ["Inc1"], spy.client, "test-model")

    # 第 2 轮：用户纠正，LLM 应能看到自己上一轮说过「收入」
    _apply_scout_reply_with_llm(ctx, "不对，Inc1 应该是销售额", ["Inc1"], spy.client, "test-model")

    # 律 3 期望：第 2 轮 LLM 看到第 1 轮 assistant 的产出
    assert spy.calls[1]["messages"][-2]["role"] == "assistant", (
        "律 3 违反：第 2 轮 LLM messages 缺少第 1 轮 assistant 历史。\n"
        f"第 2 轮 messages 角色序列: {[m['role'] for m in spy.calls[1]['messages']]}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# 律 6：信息抵达正向契约的元测试 —— 确认 spy 工具本身正常工作
# ─────────────────────────────────────────────────────────────────────────────

def test_meta_LLMSpy录制功能正常():
    """元测试：LLMSpy 能正确录制 messages 并支持子串断言。"""
    spy = LLMSpy()
    spy.client.chat.completions.create(
        model="m", messages=[{"role": "user", "content": "hello world"}]
    )
    assert spy.call_count() == 1
    assert spy.contains_in_any_message("hello world")
    assert not spy.contains_in_any_message("not there")
