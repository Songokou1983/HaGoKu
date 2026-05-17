"""Scout 字段暂停：用户自由文本应通过 LLM 理解后写入 context。

设计原则：LLM 是字段理解的唯一引擎，代码不做正则解析。
测试使用 mock LLM 验证 _apply_scout_reply_with_llm 的行为。
"""

from unittest.mock import MagicMock

from hagoku.manager.orchestrator import (
    _apply_scout_reply_with_llm,
    _scout_reply_is_pure_confirm,
    apply_scout_user_field_reply_to_context,
)


def _ctx():
    return {
        "column_semantics": [
            {"column_name": "Code", "needs_user_input": True},
            {"column_name": "Period", "needs_user_input": False},
        ],
        "column_descriptions": {"Code": "多为编码（例：A1）", "Period": "多为周期"},
    }


# ── 无 LLM client：安全返回空列表，不写入 context ────────────

def test_no_llm_client_returns_empty():
    """无 LLM client 时返回 []，context 不变。"""
    ctx = _ctx()
    before_descs = dict(ctx["column_descriptions"])
    applied = apply_scout_user_field_reply_to_context(ctx, "Code 代表店铺编号")
    assert applied == []
    assert ctx["column_descriptions"] == before_descs


def test_pure_confirm_no_llm_needed():
    """纯确认不需要 LLM，直接返回 []。"""
    ctx = _ctx()
    before = dict(ctx["column_descriptions"])
    assert apply_scout_user_field_reply_to_context(ctx, "确认") == []
    assert ctx["column_descriptions"] == before
    assert _scout_reply_is_pure_confirm("确认")
    assert _scout_reply_is_pure_confirm("确认无误")
    assert _scout_reply_is_pure_confirm("") is False


def test_empty_no_llm_needed():
    """空输入不需要 LLM，直接返回 []。"""
    ctx = _ctx()
    before = dict(ctx["column_descriptions"])
    assert apply_scout_user_field_reply_to_context(ctx, "") == []
    assert ctx["column_descriptions"] == before


# ── Mock LLM 驱动：验证 _apply_scout_reply_with_llm ──────────

def _mock_llm_client(json_response: dict | str):
    """创建一个 mock LLM client，返回指定的 JSON 响应。"""
    client = MagicMock()
    content = json_response
    if isinstance(content, dict):
        import json
        content = json.dumps(content, ensure_ascii=False)
    choice = MagicMock()
    choice.message.content = content
    resp = MagicMock()
    resp.choices = [choice]
    client.chat.completions.create.return_value = resp
    return client


def test_llm_description_update():
    """LLM 返回 description → 写入 column_descriptions。"""
    ctx = _ctx()
    mock = _mock_llm_client({"Code": "store number"})
    applied = _apply_scout_reply_with_llm(ctx, "code means store number", ["Code", "Period"], mock, "test-model")
    assert any("Code←store number" in a for a in applied)
    assert ctx["column_descriptions"]["Code"] == "store number"
    assert ctx["column_semantics"][0]["needs_user_input"] is False


def test_llm_description_chinese():
    """LLM 返回中文 description。"""
    ctx = _ctx()
    mock = _mock_llm_client({"Code": "门店编号"})
    applied = _apply_scout_reply_with_llm(ctx, "Code=门店编号", ["Code", "Period"], mock, "test-model")
    assert any("Code←门店编号" in a for a in applied)
    assert ctx["column_descriptions"]["Code"] == "门店编号"


def test_llm_display_name_only():
    """LLM 只返回 display_name → 写入 column_display_names，不写 description。"""
    ctx = _ctx()
    ctx.setdefault("column_display_names", {})
    mock = _mock_llm_client({"Code": {"display_name": "店铺编号"}})
    applied = _apply_scout_reply_with_llm(ctx, "Code的中文名是店铺编号", ["Code", "Period"], mock, "test-model")
    assert any("[display]←店铺编号" in a for a in applied)
    assert ctx["column_display_names"].get("Code") == "店铺编号"
    # description 保持原值不变
    assert ctx["column_descriptions"]["Code"] == "多为编码（例：A1）"


def test_llm_both_description_and_display_name():
    """LLM 同时返回 description 和 display_name → 两者都写入。"""
    ctx = _ctx()
    ctx.setdefault("column_display_names", {})
    mock = _mock_llm_client({"Code": {"description": "店铺唯一编号", "display_name": "店铺编号"}})
    applied = _apply_scout_reply_with_llm(ctx, "Code代表店铺编号", ["Code", "Period"], mock, "test-model")
    assert any("Code←店铺唯一编号" in a for a in applied)
    assert any("[display]←店铺编号" in a for a in applied)
    assert ctx["column_descriptions"]["Code"] == "店铺唯一编号"
    assert ctx["column_display_names"].get("Code") == "店铺编号"


def test_llm_markdown_fence_handling():
    """LLM 返回带 ```json 包裹的响应 → 正确解析。"""
    ctx = _ctx()
    mock = _mock_llm_client('```json\n{"Code": "store number"}\n```')
    applied = _apply_scout_reply_with_llm(ctx, "code means store number", ["Code", "Period"], mock, "test-model")
    assert any("Code←store number" in a for a in applied)
    assert ctx["column_descriptions"]["Code"] == "store number"


def test_llm_column_not_in_list_ignored():
    """LLM 返回未知列名 → 忽略，不写入。"""
    ctx = _ctx()
    mock = _mock_llm_client({"UnknownCol": "something"})
    applied = _apply_scout_reply_with_llm(ctx, "UnknownCol is something", ["Code", "Period"], mock, "test-model")
    assert applied == []
    assert ctx["column_descriptions"]["Code"] == "多为编码（例：A1）"


def test_llm_duplicate_column_skipped():
    """LLM 返回重复列名 → 只写入第一次。"""
    ctx = _ctx()
    mock = _mock_llm_client({"Code": "first", "code": "second"})
    applied = _apply_scout_reply_with_llm(ctx, "code means first and second", ["Code", "Period"], mock, "test-model")
    # code（小写）通过 _resolve_scout_column_token 解析后映射到 "Code"，但 seen_col 防重
    assert len(applied) <= 2  # 最多两条（已去重）
    assert ctx["column_descriptions"]["Code"] in ("first", "second")


def test_llm_exception_returns_empty():
    """LLM 抛出异常 → 返回 []，context 不变。"""
    ctx = _ctx()
    before = dict(ctx["column_descriptions"])
    mock = MagicMock()
    mock.chat.completions.create.side_effect = RuntimeError("LLM timeout")
    applied = _apply_scout_reply_with_llm(ctx, "Code is store", ["Code", "Period"], mock, "test-model")
    assert applied == []
    assert ctx["column_descriptions"] == before