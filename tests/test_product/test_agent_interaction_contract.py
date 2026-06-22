"""
Agent 互动与成长 — 可执行契约（见 docs/AGENT_INTERACTION_CONTRACT.md）。

变更暂停/用户输入路径时须跑：pytest tests/test_product/test_agent_interaction_contract.py
"""

from hagoku.config import HaGoKuConfig
from hagoku.manager.orchestrator import Orchestrator


def test_c3_scout_user_natural_language_llm_driven():
    """C3：自然语言纠错须经 LLM 理解后写入 column_descriptions（Phase B: tool_calls 路径）。"""
    from unittest.mock import MagicMock
    from tests.helpers.scout_reply_legacy import _apply_scout_reply_with_llm

    ctx = {
        "column_semantics": [{"column_name": "Code", "needs_user_input": True}],
        "column_descriptions": {"Code": "old"},
    }
    mock_llm = MagicMock()
    choice = MagicMock()
    # Phase B: 使用 tool_calls 而非 JSON text fallback
    tc = MagicMock()
    tc.function.name = "update_field_understanding"
    tc.function.arguments = '{"column_name": "Code", "description": "store number"}'
    tc.id = "call_1"
    choice.message.configure_mock(content="", tool_calls=[tc])
    resp = MagicMock()
    resp.choices = [choice]
    mock_llm.chat.completions.create.return_value = resp
    applied = _apply_scout_reply_with_llm(ctx, "code means store number", ["Code"], mock_llm, "test-model")
    assert applied
    assert ctx["column_descriptions"]["Code"] == "store number"


# ─── Phase 1：Scout 多轮对齐子状态机 ───────────────────────────────────────────




# ─── 2.8.3：跨阶段闸门 ─────────────────────────────────────────────────────────

def test_scout_user_input_received_payload_has_machine_fields():
    """user_input_received（Scout）载荷含可核验字段，供前端事实行。

    pure_confirm 字段已移除——确认判断由 LLM 通道完成，不在此载荷中。
    """
    from hagoku.manager.orchestrator import scout_user_input_received_state

    ctx = {
        "column_semantics": [
            {"column_name": "a", "needs_user_input": True},
            {"column_name": "b", "needs_user_input": False},
        ],
    }
    p = scout_user_input_received_state(ctx, "a=foo", ["a←foo"], 2)
    assert p["parse_applied_count"] == 1
    assert p["parse_failed"] is False
    assert p["columns_still_needing_input"] == []
    p2 = scout_user_input_received_state(ctx, "确认", [], 3)
    assert p2["parse_applied_count"] == 0
    assert p2["parse_failed"] is True  # 有输入但无应用更新

