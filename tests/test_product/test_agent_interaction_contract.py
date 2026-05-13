"""
Agent 互动与成长 — 可执行契约（见 docs/AGENT_INTERACTION_CONTRACT.md）。

变更暂停/用户输入路径时须跑：pytest tests/test_product/test_agent_interaction_contract.py
"""

from hagoku.config import HaGoKuConfig
from hagoku.manager.orchestrator import (
    Orchestrator,
    _is_gate_confirm,
    _is_scout_aligned,
    analyst_review_pause_payload,
    apply_scout_user_field_reply_to_context,
    cleaning_review_pause_payload,
    gate_cleaning_pause_payload,
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
            "p_value": 0.01,
            "effect_size": 0.35,
            "effect_type": "r",
            "confidence_interval": "[0,1]",
        },
    ]
    p = analyst_review_pause_payload(findings)
    assert p.get("message") == ""
    ar = p.get("analyst_review")
    assert ar is not None
    assert ar["n_findings"] == 1
    assert ar["n_significant"] == 1
    assert len(ar["rows"]) == 1
    row0 = ar["rows"][0]
    assert row0.get("p_value") == "0.01"
    assert row0.get("effect_summary") == "r=0.35"
    assert row0.get("confidence_interval") == "[0,1]"


def test_c3_scout_user_natural_language_updates_context():
    """C3：自然语言纠错须写入 column_descriptions。"""
    ctx = {
        "column_semantics": [{"column_name": "Code", "needs_user_input": True}],
        "column_descriptions": {"Code": "old"},
    }
    applied = apply_scout_user_field_reply_to_context(ctx, "code means store number")
    assert applied
    assert ctx["column_descriptions"]["Code"] == "store number"


# ─── Phase 1：Scout 多轮对齐子状态机 ───────────────────────────────────────────

def test_is_scout_aligned_pure_confirm():
    """纯确认（空字串 / ok / 好的 / 确认）→ 已对齐，不继续循环。"""
    ctx = {"column_semantics": [{"column_name": "X", "needs_user_input": True}]}
    assert _is_scout_aligned(ctx, "") is True
    assert _is_scout_aligned(ctx, "ok") is True
    assert _is_scout_aligned(ctx, "好的") is True
    assert _is_scout_aligned(ctx, "确认") is True


def test_is_scout_aligned_all_fields_resolved():
    """所有字段 needs_user_input=False → 已对齐。"""
    ctx = {
        "column_semantics": [
            {"column_name": "A", "needs_user_input": False},
            {"column_name": "B", "needs_user_input": False},
        ]
    }
    assert _is_scout_aligned(ctx, "Code=店铺编号") is True
    assert _is_scout_aligned(ctx, "") is True


def test_is_scout_aligned_not_aligned():
    """有字段仍 needs_user_input=True 且非纯确认 → 未对齐，继续循环。"""
    ctx = {"column_semantics": [{"column_name": "Code", "needs_user_input": True}]}
    assert _is_scout_aligned(ctx, "Code=店铺编号") is False
    assert _is_scout_aligned(ctx, "code means store number") is False


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

def test_gate_cleaning_pause_payload_structure():
    """gate_cleaning 暂停载荷含 gate.phase 与 gate.prompt。"""
    p = gate_cleaning_pause_payload()
    assert p["message"] == ""
    gate = p.get("gate")
    assert gate is not None
    assert gate["phase"] == "cleaning"
    assert "清洗" in gate["prompt"]


def test_is_gate_confirm_pure():
    """纯确认 / 空字串 → 闸门确认，进入下一阶段。"""
    assert _is_gate_confirm("") is True
    assert _is_gate_confirm("ok") is True
    assert _is_gate_confirm("好的") is True
    assert _is_gate_confirm("确认") is True
    assert _is_gate_confirm("确认进清洗") is True


def test_is_gate_confirm_supplement():
    """含「补充/还有/改」→ 闸门拒绝，回 FieldReviewLoop。"""
    assert _is_gate_confirm("还有补充") is False
    assert _is_gate_confirm("补充一下") is False
    assert _is_gate_confirm("还要改") is False
    assert _is_gate_confirm("不对") is False
    assert _is_gate_confirm("Code=店铺编号 补充一下") is False
