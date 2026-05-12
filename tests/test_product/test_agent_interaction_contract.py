"""
Agent 互动与成长 — 可执行契约（见 docs/AGENT_INTERACTION_CONTRACT.md）。

变更暂停/用户输入路径时须跑：pytest tests/test_product/test_agent_interaction_contract.py
"""

from hagoku.config import HaGoKuConfig
from hagoku.manager.orchestrator import (
    Orchestrator,
    analyst_review_pause_payload,
    apply_scout_user_field_reply_to_context,
    cleaning_review_pause_payload,
    scout_field_review_pause_payload,
)


def test_c1_fallback_cleaner_banned_phrases_absent():
    """C1：Cleaner LLM 回退句不得再出现旧版「冒充对话」客服长模板。"""
    orch = Orchestrator(HaGoKuConfig())
    msg = orch._fallback_pause_message(
        "cleaner",
        {
            "operations": [{"column": "x", "strategy": "winsorize", "reason": "test"}],
            "data_quality": "good",
            "impact_rate": 0.0,
        },
    )
    banned = (
        "特别想保留",
        "特别想排除",
        "数据质量检测完成",
        "可以继续执行清洗吗",
    )
    for b in banned:
        assert b not in msg, f"forbidden substring {b!r} in fallback: {msg!r}"


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


def test_c2_analyst_review_structured_empty_message():
    """Analyst 暂停须 analyst_review + 空 message（与 Scout/Cleaner 一致）。"""
    findings = [
        {
            "result_id": "a1",
            "analysis_type": "regression",
            "question": "Q?",
            "significance": "significant",
            "conclusion_plain": "ok",
        },
    ]
    p = analyst_review_pause_payload(findings)
    assert p.get("message") == ""
    ar = p.get("analyst_review")
    assert ar is not None
    assert ar["n_findings"] == 1
    assert ar["n_significant"] == 1
    assert len(ar["rows"]) == 1


def test_c3_scout_user_natural_language_updates_context():
    """C3：自然语言纠错须写入 column_descriptions。"""
    ctx = {
        "column_semantics": [{"column_name": "Code", "needs_user_input": True}],
        "column_descriptions": {"Code": "old"},
    }
    applied = apply_scout_user_field_reply_to_context(ctx, "code means store number")
    assert applied
    assert ctx["column_descriptions"]["Code"] == "store number"
