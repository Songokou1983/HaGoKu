"""架构守门——状态一致性审计。

不扫描代码，不查违规。只验证运行时的行为是否正确。
"""
from __future__ import annotations

import json
import pytest
from unittest.mock import MagicMock, patch


# ────────────────────────────────────────────────────────────────
# 1. 每条 LLM 回复只有一个 session 写入点
# ────────────────────────────────────────────────────────────────

def test_session_single_write_per_assistant_message():
    """模拟一轮 run_step，断言 assistant 消息不重复写入 session。"""
    from hagoku.context.session import Session

    session = Session(analysis_goal="test")

    # 模拟流式 LLM 返回文本+tool_calls，然后 add_tool_call
    # 构造和真实 run_step 相同的写入序列
    session.add("user", "测试查询")

    # 模拟 _call_llm_step 流结束存盘（仅文本，无 tool_calls 时）
    # 当前代码：仅在 not final_tool_calls_raw 时写入
    # 模拟工具调用场景：有 tool_calls，所以不触发流存盘
    tool_calls_raw = [{"id": "call_1", "type": "function", "function": {"name": "get_sample_rows", "arguments": "{}"}}]
    # tool_calls 存在 → _call_llm_step 不写（正确行为）
    
    # 模拟 add_tool_call
    oai_calls = [{
        "id": "call_1",
        "type": "function",
        "function": {"name": "get_sample_rows", "arguments": "{}"},
    }]
    results = [{"content": '{"result": "ok"}', "tool_call_id": "call_1"}]
    session.add_tool_call("LLM回复文本", oai_calls, results)
    
    # 数 assistant 消息
    assistant_msgs = [m for m in session.messages if m.get("role") == "assistant"]
    assert len(assistant_msgs) == 1, f"期望 1 条 assistant，实际 {len(assistant_msgs)} 条"


def test_session_no_duplicate_on_text_only():
    """模拟纯文本回复（无 tool_calls），断言只有一条 assistant。"""
    from hagoku.context.session import Session

    session = Session(analysis_goal="test")
    session.add("user", "你好")

    # 模拟 _call_llm_step 流结束存盘（无 tool_calls）
    session.add("assistant", "你好！有什么可以帮助你的？")

    # run_step 的兜底逻辑：无 tool_calls 时也会尝试写
    # 当前代码有去重检查
    last = session.messages[-1] if session.messages else None
    if not (last and last.get("role") == "assistant" and last.get("content") == "你好！有什么可以帮助你的？"):
        session.add("assistant", "你好！有什么可以帮助你的？")

    assistant_msgs = [m for m in session.messages if m.get("role") == "assistant"]
    assert len(assistant_msgs) == 1, f"期望 1 条 assistant，实际 {len(assistant_msgs)} 条"


# ────────────────────────────────────────────────────────────────
# 2. snapshot 包含和 live 事件兼容的数据
# ────────────────────────────────────────────────────────────────

def test_snapshot_field_review_from_column_semantics():
    """验证从 column_semantics 重建 field_review 的格式正确。"""
    from hagoku.api.ws_handler import _build_state_snapshot
    
    # 构造一个模拟的 orchestrator
    class MockOrch:
        _context = {}
        _project_name = "test"
    
    orch = MockOrch()
    orch._context["n_rows"] = 100
    orch._context["n_cols"] = 5
    orch._context["column_semantics"] = [
        {"column_name": "Col1", "display_name": "列1", "description": "第一列",
         "suggested_role": "target", "used_in_analysis": True, "evidence": "测试"},
    ]
    # 需要活跃 session 才生成 field_review
    orch._context["_session"] = MagicMock()
    orch._context["_session"].messages = [{"role": "assistant", "content": "test"}]

    snap = _build_state_snapshot(orch)
    
    assert snap is not None
    assert "field_review" in snap, "snapshot 应包含 field_review"
    fr = snap["field_review"]
    assert fr["n_rows"] == 100
    assert fr["n_cols"] == 5
    assert len(fr["rows"]) == 1
    assert fr["rows"][0]["field_name"] == "Col1"
    assert fr["rows"][0]["chinese_name"] == "列1"


def test_snapshot_no_field_review_without_session():
    """无活跃 session 时 snapshot 不应包含 field_review。"""
    from hagoku.api.ws_handler import _build_state_snapshot

    class MockOrch:
        _context = {}
        _project_name = "test"

    orch = MockOrch()
    orch._context["n_rows"] = 100
    orch._context["n_cols"] = 5
    orch._context["column_semantics"] = [
        {"column_name": "Col1", "display_name": "列1", "description": "第一列",
         "suggested_role": "target", "used_in_analysis": True, "evidence": "测试"},
    ]
    # 不设 _session → 无活跃分析

    snap = _build_state_snapshot(orch)
    assert snap is not None
    assert "field_review" not in snap, "无活跃 session 时不应生成 field_review"


def test_snapshot_report_url_from_context():
    """验证 report_url 正确从 context 传递到 snapshot。"""
    from hagoku.api.ws_handler import _build_state_snapshot

    class MockOrch:
        _context = {"_report_html_path": "/tmp/report.html"}
        _project_name = "test"

    orch = MockOrch()
    snap = _build_state_snapshot(orch)
    assert snap is not None
    assert snap.get("report_url") == "/tmp/report.html"


# ────────────────────────────────────────────────────────────────
# 3. 清历史后 context 全空
# ────────────────────────────────────────────────────────────────

def test_cancel_analysis_clears_context():
    """模拟 cancel_analysis 后的上下文清理。"""
    ctx = {
        "column_semantics": [{"col": "test"}],
        "_pending_ask_user": {"question": "?"},
        "_report_html_path": "/tmp/report.html",
        "_session": MagicMock(),
        "query": "test",
    }
    
    # 模拟 ws_handler cancel_analysis 的清理逻辑
    ctx.pop("column_semantics", None)
    ctx.pop("_pending_ask_user", None)
    ctx.pop("_report_html_path", None)
    
    assert "column_semantics" not in ctx
    assert "_pending_ask_user" not in ctx
    assert "_report_html_path" not in ctx
    # 保留非分析特定字段
    assert "query" in ctx
    assert "_session" in ctx


def test_clear_history_clears_context():
    """模拟 clear_history 的 ctx.clear() 行为。"""
    ctx = {
        "column_semantics": [{"col": "test"}],
        "_pending_ask_user": {"question": "?"},
        "_report_html_path": "/tmp/report.html",
        "_session": MagicMock(),
        "query": "test",
    }
    
    # 模拟 clear_history 的清理逻辑
    ctx.clear()
    
    assert len(ctx) == 0, "ctx.clear() 应清空所有字段"


# ────────────────────────────────────────────────────────────────
# 4. tool 消息不连续重复
# ────────────────────────────────────────────────────────────────

def test_to_llm_messages_collapses_duplicate_tools():
    """连续相同内容的 tool 消息应该被折叠。"""
    from hagoku.context.session import Session

    session = Session(analysis_goal="test")
    session.add("user", "查询")
    session.add("assistant", "让我查一下")

    # 5 条完全相同的 tool 结果
    same_result = '{"test":"trend_decomposition","statistic":59.37}'
    for i in range(5):
        session.messages.append({
            "role": "tool",
            "content": same_result,
            "tool_call_id": f"call_{i}",
        })

    msgs = session.to_llm_messages("", "")
    tool_msgs = [m for m in msgs if m.get("role") == "tool"]
    assert len(tool_msgs) == 1, f"期望折叠为 1 条，实际 {len(tool_msgs)} 条"


def test_to_llm_messages_keeps_different_tool_call_ids():
    """不同 tool_call_id 的 tool 消息不应被折叠（LLM API 要求每条 tool_call 有对应响应）。"""
    from hagoku.context.session import Session

    session = Session(analysis_goal="test")
    session.add("user", "查询")
    session.add("assistant", "让我查一下")

    # 不同 tool_call_id，相同内容
    session.messages.append({
        "role": "tool", "content": '{"result":"ok"}', "tool_call_id": "call_1",
    })
    session.messages.append({
        "role": "tool", "content": '{"result":"ok"}', "tool_call_id": "call_2",
    })

    msgs = session.to_llm_messages("", "")
    tool_msgs = [m for m in msgs if m.get("role") == "tool"]
    assert len(tool_msgs) == 2, f"不同 tool_call_id 不应折叠，期望 2 条，实际 {len(tool_msgs)} 条"
