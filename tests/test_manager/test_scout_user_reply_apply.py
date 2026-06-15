"""Scout 字段暂停：用户自由文本应通过 LLM 理解后写入 context。

设计原则：LLM 是字段理解的唯一引擎，代码不做正则解析。
LLM 通过 function calling（tool_calls）主动更新字段信息。
测试使用 mock LLM 验证 _apply_scout_reply_with_llm 的行为。
"""

import json as _json
from unittest.mock import MagicMock

from hagoku.manager.llm_dispatch.scout_reply import (
    _apply_scout_reply_with_llm,
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


def _mock_llm_client(*tool_calls: dict):
    """
    创建一个 mock LLM client，通过 tool_calls 机制返回字段更新。

    每个 tool_call 为 dict：
      {
        "name": "update_field_understanding",
        "arguments": {"column_name": "Code", "display_name": "店铺编号", "description": "代表店铺编号"}
      }

    若 tool_calls 为空 list，mock 将返回无 tool_calls 的消息（用于测试 fallback JSON / 无操作场景）。
    """
    client = MagicMock()
    choice = MagicMock()
    msg = MagicMock()

    if tool_calls:
        # 构建 OpenAI tool_calls 对象列表
        tc_list = []
        for tc in tool_calls:
            tc_obj = MagicMock()
            tc_obj.function.name = tc["name"]
            tc_obj.function.arguments = _json.dumps(tc["arguments"], ensure_ascii=False)
            tc_list.append(tc_obj)
        msg.tool_calls = tc_list
        msg.content = ""
    else:
        msg.tool_calls = None
        msg.content = ""

    choice.message = msg
    resp = MagicMock()
    resp.choices = [choice]
    client.chat.completions.create.return_value = resp
    return client


# ── 无 LLM client：安全返回空列表，不写入 context ────────────

def test_no_llm_client_raises():
    """无 LLM client 时 raise RuntimeError（铁律 2 路径 A / 铁律 7），不静默兜底。"""
    ctx = _ctx()
    before_descs = dict(ctx["column_descriptions"])
    import pytest
    with pytest.raises(RuntimeError, match="LLM client 未初始化"):
        apply_scout_user_field_reply_to_context(ctx, "Code 代表店铺编号")
    assert ctx["column_descriptions"] == before_descs


def test_pure_confirm_no_llm_needed():
    """纯确认由 _handle_scout_reply 上层截获，不进入 apply_scout_user_field_reply_to_context。
    直接调用此函数且无 LLM client 时 raise RuntimeError（铁律 2 路径 A）。"""
    ctx = _ctx()
    before = dict(ctx["column_descriptions"])
    import pytest
    with pytest.raises(RuntimeError, match="LLM client 未初始化"):
        apply_scout_user_field_reply_to_context(ctx, "确认")
    assert ctx["column_descriptions"] == before


def test_empty_no_llm_needed():
    """空输入不需要 LLM，直接返回 []。"""
    ctx = _ctx()
    before = dict(ctx["column_descriptions"])
    assert apply_scout_user_field_reply_to_context(ctx, "") == []
    assert ctx["column_descriptions"] == before


# ── Mock LLM 驱动（tool_calls 主路径）：验证 _apply_scout_reply_with_llm ──────────

def test_llm_tool_call_description_update():
    """LLM 通过 tool_calls 返回 description → 写入 column_descriptions。"""
    ctx = _ctx()
    mock = _mock_llm_client({
        "name": "update_field_understanding",
        "arguments": {"column_name": "Code", "description": "store number"},
    })
    applied = _apply_scout_reply_with_llm(ctx, "code means store number", ["Code", "Period"], mock, "test-model")
    assert any("Code←store number" in a for a in applied)
    assert ctx["column_descriptions"]["Code"] == "store number"
    assert ctx["column_semantics"][0]["needs_user_input"] is False


def test_llm_tool_call_description_chinese():
    """LLM 通过 tool_calls 返回中文 description。"""
    ctx = _ctx()
    mock = _mock_llm_client({
        "name": "update_field_understanding",
        "arguments": {"column_name": "Code", "description": "门店编号"},
    })
    applied = _apply_scout_reply_with_llm(ctx, "Code=门店编号", ["Code", "Period"], mock, "test-model")
    assert any("Code←门店编号" in a for a in applied)
    assert ctx["column_descriptions"]["Code"] == "门店编号"


def test_llm_tool_call_display_name_only():
    """LLM 通过 tool_calls 只返回 display_name → 写入 column_display_names，不写 description。"""
    ctx = _ctx()
    ctx.setdefault("column_display_names", {})
    mock = _mock_llm_client({
        "name": "update_field_understanding",
        "arguments": {"column_name": "Code", "display_name": "店铺编号"},
    })
    applied = _apply_scout_reply_with_llm(ctx, "Code的中文名是店铺编号", ["Code", "Period"], mock, "test-model")
    assert any("[display]←店铺编号" in a for a in applied)
    assert ctx["column_display_names"].get("Code") == "店铺编号"
    # description 保持原值不变
    assert ctx["column_descriptions"]["Code"] == "多为编码（例：A1）"


def test_llm_tool_call_both_description_and_display_name():
    """LLM 通过 tool_calls 同时返回 description 和 display_name → 两者都写入。"""
    ctx = _ctx()
    ctx.setdefault("column_display_names", {})
    mock = _mock_llm_client({
        "name": "update_field_understanding",
        "arguments": {"column_name": "Code", "description": "店铺唯一编号", "display_name": "店铺编号"},
    })
    applied = _apply_scout_reply_with_llm(ctx, "Code代表店铺编号", ["Code", "Period"], mock, "test-model")
    assert any("Code←店铺唯一编号" in a for a in applied)
    assert any("[display]←店铺编号" in a for a in applied)
    assert ctx["column_descriptions"]["Code"] == "店铺唯一编号"
    assert ctx["column_display_names"].get("Code") == "店铺编号"


def test_llm_tool_call_column_not_in_list_ignored():
    """LLM tool_calls 返回未知列名 → 忽略，不写入。"""
    ctx = _ctx()
    mock = _mock_llm_client({
        "name": "update_field_understanding",
        "arguments": {"column_name": "UnknownCol", "description": "something"},
    })
    applied = _apply_scout_reply_with_llm(ctx, "UnknownCol is something", ["Code", "Period"], mock, "test-model")
    assert applied == []
    assert ctx["column_descriptions"]["Code"] == "多为编码（例：A1）"


def test_llm_tool_call_duplicate_column_skipped():
    """LLM tool_calls 返回重复列名 → 只写入第一次。"""
    ctx = _ctx()
    mock = _mock_llm_client(
        {
            "name": "update_field_understanding",
            "arguments": {"column_name": "Code", "description": "first"},
        },
        {
            "name": "update_field_understanding",
            "arguments": {"column_name": "code", "description": "second"},
        },
    )
    applied = _apply_scout_reply_with_llm(ctx, "code means first and second", ["Code", "Period"], mock, "test-model")
    # code（小写）通过 _resolve_scout_column_token 解析后映射到 "Code"，但 seen_col 防重
    assert len(applied) <= 3
    assert ctx["column_descriptions"]["Code"] in ("first", "second")


def test_llm_tool_call_multiple_fields():
    """LLM 通过 tool_calls 一次更新多个字段。"""
    ctx = _ctx()
    ctx["column_semantics"][1]["needs_user_input"] = True
    ctx.setdefault("column_display_names", {})
    mock = _mock_llm_client(
        {
            "name": "update_field_understanding",
            "arguments": {"column_name": "Code", "display_name": "店铺编号", "description": "代表店铺编号"},
        },
        {
            "name": "update_field_understanding",
            "arguments": {"column_name": "Period", "display_name": "周次"},
        },
    )
    applied = _apply_scout_reply_with_llm(ctx, "Code代表店铺编号，Period中文名是周次", ["Code", "Period"], mock, "test-model")
    assert any("Code←代表店铺编号" in a for a in applied)
    assert any("[display]←店铺编号" in a for a in applied)
    assert any("[display]←周次" in a for a in applied)
    assert ctx["column_descriptions"]["Code"] == "代表店铺编号"
    assert ctx["column_display_names"]["Code"] == "店铺编号"
    assert ctx["column_display_names"]["Period"] == "周次"
    assert ctx["column_semantics"][0]["needs_user_input"] is False
    assert ctx["column_semantics"][1]["needs_user_input"] is False


def test_llm_tool_call_no_tool_calls_no_action():
    """LLM 无 tool_calls 且 content 为空 → 返回 []，context 不变（如纯确认不会走到这里但覆盖路径）。"""
    ctx = _ctx()
    before = dict(ctx["column_descriptions"])
    mock = _mock_llm_client()  # 无 tool_calls
    applied = _apply_scout_reply_with_llm(ctx, "今天天气不错", ["Code", "Period"], mock, "test-model")
    assert applied == []
    assert ctx["column_descriptions"] == before


def test_llm_exception_raises():
    """LLM 抛出异常 → raise RuntimeError（铁律 2 路径 A / 铁律 7），不静默兜底。"""
    ctx = _ctx()
    before = dict(ctx["column_descriptions"])
    mock = MagicMock()
    mock.chat.completions.create.side_effect = RuntimeError("LLM timeout")
    import pytest
    with pytest.raises(RuntimeError, match="Scout 字段理解 LLM 调用失败"):
        _apply_scout_reply_with_llm(ctx, "Code is store", ["Code", "Period"], mock, "test-model")
    assert ctx["column_descriptions"] == before
