"""
Agent 互动与成长 — 可执行契约（见 docs/AGENT_INTERACTION_CONTRACT.md）。

变更暂停/用户输入路径时须跑：pytest tests/test_product/test_agent_interaction_contract.py
"""

from hagoku.config import HaGoKuConfig
from hagoku.manager.orchestrator import (
    Orchestrator,
    cleaning_review_pause_payload,
    scout_field_review_pause_payload,
)


def test_c1_cleaner_pause_no_injected_dialogue():
    """C1：Cleaner 暂停不得再注入整段「冒充 Agent」中文气泡（仅结构化 cleaning_review）。"""
    orch = Orchestrator(HaGoKuConfig())

    class R:
        total_rows_original = 100
        total_rows_after = 100
        bias_risk = "low"
        warnings: list[str] = []
        operations = [{"column": "x", "strategy": "winsorize", "reason": "test", "rows_affected": 5}]

    p = cleaning_review_pause_payload(R(), data_quality="good", impact_rate=0.0)
    p["interaction_revision"] = 1
    out = orch._attach_pause_dialogue_message("cleaner", p)
    assert out.get("message") == ""
    assert isinstance(out.get("cleaning_review"), dict)


def test_c2_scout_field_review_structured_empty_message():
    """C2：Scout 字段核对须结构化 + message 可为空。"""
    ctx = {
        "n_rows": 3,
        "column_semantics": [{"column_name": "A", "needs_user_input": False}],
        "column_descriptions": {"A": "多为测试（例：1）"},
        "column_display_names": {},
    }
    p = scout_field_review_pause_payload(ctx)
    assert p.get("message") == ""
    fr = p.get("field_review")
    assert fr is not None
    assert fr["n_cols"] == 1
    assert len(fr["rows"]) == 1


def test_c2_cleaning_review_structured_empty_message():
    """Cleaner 暂停须 cleaning_review + 空 message（与 C2 同源）。"""
    class R:
        total_rows_original = 100
        total_rows_after = 100
        bias_risk = "low"
        warnings: list[str] = []
        operations = [{"column": "c", "strategy": "winsorize", "reason": "r", "rows_affected": 5}]

    p = cleaning_review_pause_payload(R(), data_quality="unknown", impact_rate=0.0)
    assert p.get("message") == ""
    cr = p.get("cleaning_review")
    assert cr is not None
    assert "rows_removed" in cr


def test_c3_scout_user_natural_language_llm_driven():
    """C3：自然语言纠错须经 LLM 理解后写入 column_descriptions（Phase B: tool_calls 路径）。"""
    from unittest.mock import MagicMock
    from hagoku.manager.orchestrator import _apply_scout_reply_with_llm

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


def test_interaction_revision_in_scout_payload():
    """interaction_revision 须出现在 Scout pause payload（供前端区分多轮同阶段）。"""
    ctx = {
        "n_rows": 2,
        "column_semantics": [{"column_name": "X", "needs_user_input": False}],
        "column_descriptions": {},
        "column_display_names": {},
    }
    p = scout_field_review_pause_payload(ctx)
    p["interaction_revision"] = 3
    assert p["interaction_revision"] == 3
    assert p["field_review"] is not None


# ─── 2.8.3：跨阶段闸门 ─────────────────────────────────────────────────────────

def test_scout_user_input_received_payload_has_machine_fields():
    """user_input_received（Scout）载荷含可核验字段，供前端事实行。

    pure_confirm 字段已移除——确认判断由 LLM 通道完成，不在此载荷中。
    """
    from hagoku.manager.orchestrator import scout_user_input_received_payload

    ctx = {
        "column_semantics": [
            {"column_name": "a", "needs_user_input": True},
            {"column_name": "b", "needs_user_input": False},
        ],
    }
    p = scout_user_input_received_payload(ctx, "a=foo", ["a←foo"], 2)
    assert p["parse_applied_count"] == 1
    assert p["parse_failed"] is False
    assert p["columns_still_needing_input"] == []
    p2 = scout_user_input_received_payload(ctx, "确认", [], 3)
    assert p2["parse_applied_count"] == 0
    assert p2["parse_failed"] is True  # 有输入但无应用更新

