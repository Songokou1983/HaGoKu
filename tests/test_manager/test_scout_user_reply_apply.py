"""Scout 字段暂停：用户自由文本应写入 context，而非仅追加 query。"""

from hagoku.manager.orchestrator import (
    apply_scout_user_field_reply_to_context,
    _scout_reply_is_pure_confirm,
)


def _ctx():
    return {
        "column_semantics": [
            {"column_name": "Code", "needs_user_input": True},
            {"column_name": "Period", "needs_user_input": False},
        ],
        "column_descriptions": {"Code": "多为编码（例：A1）", "Period": "多为周期"},
    }


def test_means_english_updates_description_and_clears_flag():
    ctx = _ctx()
    applied = apply_scout_user_field_reply_to_context(ctx, "code means store number")
    assert applied == ["Code←store number"]
    assert ctx["column_descriptions"]["Code"] == "store number"
    assert ctx["column_semantics"][0]["needs_user_input"] is False


def test_equals_form():
    ctx = _ctx()
    applied = apply_scout_user_field_reply_to_context(ctx, "Code=门店编号")
    assert applied == ["Code←门店编号"]
    assert ctx["column_descriptions"]["Code"] == "门店编号"


def test_chinese_prefix():
    ctx = _ctx()
    applied = apply_scout_user_field_reply_to_context(ctx, "Code就是门店编码")
    assert applied and applied[0].startswith("Code←")
    assert "门店编码" in ctx["column_descriptions"]["Code"]


def test_pure_confirm_no_mutation():
    ctx = _ctx()
    before = dict(ctx["column_descriptions"])
    assert apply_scout_user_field_reply_to_context(ctx, "确认") == []
    assert ctx["column_descriptions"] == before
    assert _scout_reply_is_pure_confirm("确认")
    assert _scout_reply_is_pure_confirm("确认无误")
    assert _scout_reply_is_pure_confirm("") is False


def test_empty_no_mutation():
    ctx = _ctx()
    before = dict(ctx["column_descriptions"])
    assert apply_scout_user_field_reply_to_context(ctx, "") == []
    assert ctx["column_descriptions"] == before


# ── 尾部 display_name 意图信号 ────────────────────────────────

def test_trailing_display_intent_prefixed_is():
    """「Code为店铺编号，你要更新到中文名称里」→ 应写入 display_names 而非 descs。"""
    ctx = _ctx()
    ctx.setdefault("column_display_names", {})
    applied = apply_scout_user_field_reply_to_context(
        ctx, "Code为店铺编号，你要更新到中文名称里"
    )
    assert applied == ["Code:[display]←店铺编号"]
    assert ctx["column_display_names"].get("Code") == "店铺编号"
    # descs 不应被写入（含义理解不变）
    assert ctx["column_descriptions"]["Code"] == "多为编码（例：A1）"


def test_trailing_display_intent_equals():
    """「Code=门店编号，请改到中文名称」→ 应写入 display_names。"""
    ctx = _ctx()
    ctx.setdefault("column_display_names", {})
    applied = apply_scout_user_field_reply_to_context(
        ctx, "Code=门店编号，请改到中文名称"
    )
    assert applied == ["Code:[display]←门店编号"]
    assert ctx["column_display_names"].get("Code") == "门店编号"


def test_trailing_display_intent_short_verb():
    """「Code是店铺，放到中文名里」→ display_names。"""
    ctx = _ctx()
    ctx.setdefault("column_display_names", {})
    applied = apply_scout_user_field_reply_to_context(
        ctx, "Code是店铺，放到中文名里"
    )
    assert "display" in applied[0]
    assert ctx["column_display_names"].get("Code") == "店铺"


def test_trailing_display_intent_clean_meaning():
    """「Code为订单编号，用作中文名」→ 剥离后 meaning 不含「用作中文名」。"""
    ctx = _ctx()
    ctx.setdefault("column_display_names", {})
    applied = apply_scout_user_field_reply_to_context(
        ctx, "Code为订单编号，用作中文名"
    )
    assert ctx["column_display_names"].get("Code") == "订单编号"


def test_no_trailing_intent_stays_desc():
    """无尾部意图信号时，仍写入 descs。"""
    ctx = _ctx()
    applied = apply_scout_user_field_reply_to_context(ctx, "Code就是门店编号")
    assert applied and applied[0].startswith("Code←")
    assert ctx["column_descriptions"]["Code"] == "门店编号"
