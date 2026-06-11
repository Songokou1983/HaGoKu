"""tool_exchange entry 测试 — Phase B CO-B2。

覆盖 §3.4 全部场景：add_tool_exchange / build_prompt 展开 / persistence / to_messages_for_llm。
"""

import json
import tempfile
from pathlib import Path

import pytest

from hagoku.context.project_context import (
    ContextEntry,
    ProjectContext,
    ToolCallRecord,
)


@pytest.fixture
def ctx():
    return ProjectContext(run_id="r1", analysis_goal="分析ROI")


class TestToolExchangeEntry:
    """tool_exchange entry 类型的基础行为。"""

    def test_add_tool_exchange_creates_entry(self, ctx):
        tc = ToolCallRecord(
            tool_call_id="call_1",
            name="get_stats",
            arguments='{"col":"Revenue"}',
            result="mean=100.5",
        )
        ctx.add_tool_exchange("analyst", 0, [tc])

        assert len(ctx.entries) == 1
        e = ctx.entries[0]
        assert e.type == "tool_exchange"
        assert e.stage == "analyst"
        assert e.tool_calls is not None
        assert len(e.tool_calls) == 1
        assert e.tool_calls[0].tool_call_id == "call_1"
        assert e.tool_calls[0].name == "get_stats"

    def test_add_tool_exchange_multiple_tools(self, ctx):
        """多个工具调用在一轮 tool_exchange 中。"""
        tcs = [
            ToolCallRecord("c1", "schema_lint", '{"cols":["A"]}', "通过", None),
            ToolCallRecord("c2", "zero_var_check", '{"col":"B"}', "", "B 列零方差"),
        ]
        ctx.add_tool_exchange("cleaner", 1, tcs, assistant_content="检查数据质量...")
        assert len(ctx.entries) == 1
        e = ctx.entries[0]
        assert e.tool_calls is not None
        assert len(e.tool_calls) == 2

    def test_add_tool_exchange_with_assistant_pre_text(self, ctx):
        tc = ToolCallRecord("c1", "get_stats", '{"col":"X"}', "ok")
        ctx.add_tool_exchange("analyst", 0, [tc], assistant_content="让我看看数据...")
        e = ctx.entries[0]
        assert e.snapshot is not None
        assert e.snapshot["assistant_pre_text"] == "让我看看数据..."


class TestToolExchangeInBuildPrompt:
    """tool_exchange 在 build_prompt() 的 messages_history 中展开为 OpenAI 协议。"""

    def test_single_tool_exchange_expands_to_assistant_plus_tool_turns(self, ctx):
        tc = ToolCallRecord("call_1", "get_stats", '{"col":"Revenue"}', "mean=100.5")
        ctx.add_tool_exchange("analyst", 0, [tc])

        result = ctx.build_prompt("analyst", {"column_semantics": []})
        history = result["messages_history"]
        # 1 assistant(tool_calls) + 1 tool(result) = 2 turns
        assert len(history) == 2
        assert history[0]["role"] == "assistant"
        assert "tool_calls" in history[0]
        assert history[0]["tool_calls"][0]["id"] == "call_1"
        assert history[1]["role"] == "tool"
        assert history[1]["content"] == "mean=100.5"
        assert history[1]["tool_call_id"] == "call_1"

    def test_tool_exchange_with_error_shows_error_in_tool_turn(self, ctx):
        """铁律 7：工具执行失败也记录，不吞。"""
        tc = ToolCallRecord("c1", "bad_tool", "{}", "", "工具崩溃")
        ctx.add_tool_exchange("cleaner", 0, [tc])

        result = ctx.build_prompt("cleaner", {"column_semantics": []})
        history = result["messages_history"]
        assert history[1]["role"] == "tool"
        assert history[1]["content"] == "工具崩溃"

    def test_tool_exchange_with_pre_text_has_content(self, ctx):
        tc = ToolCallRecord("c1", "get_stats", "{}", "ok")
        ctx.add_tool_exchange("analyst", 0, [tc], assistant_content="分析中...")
        result = ctx.build_prompt("analyst", {"column_semantics": []})
        history = result["messages_history"]
        assert history[0]["content"] == "分析中..."
        assert "tool_calls" in history[0]


class TestToMessagesForLlm:
    """to_messages_for_llm() 端到端链路。"""

    def test_minimal_to_messages_for_llm(self, ctx):
        """空 context、空 history 的最简调用。"""
        msgs = ctx.to_messages_for_llm("scout", {"column_semantics": []}, "请分析")
        assert len(msgs) >= 2  # system_prefix (含 analysis_goal) + user_input
        assert msgs[0]["role"] == "system"
        assert "分析ROI" in msgs[0]["content"]

    def test_to_messages_for_llm_with_user_feedback(self, ctx):
        """含用户反馈时，messages 包含历史。"""
        ctx.add_user_feedback("scout", 0, "Code是店铺编号")
        ctx.add_agent_response("scout", 0, "已更新 Code 为店铺编号")
        msgs = ctx.to_messages_for_llm("scout", {"column_semantics": []}, "再看看 Period")
        # system + query + user_feedback + agent_response + user_input = 5
        assert len(msgs) == 5
        # history[0] = user feedback
        assert msgs[2]["role"] == "user"
        assert msgs[2]["content"] == "Code是店铺编号"

    def test_to_messages_for_llm_with_tool_exchange(self, ctx):
        """带 tool_exchange 历史时，展开为标准协议。"""
        tc = ToolCallRecord("c1", "get_stats", '{"col":"Revenue"}', "mean=100.5")
        ctx.add_tool_exchange("analyst", 0, [tc])
        msgs = ctx.to_messages_for_llm("analyst", {"column_semantics": []}, "继续")
        # system + query + assistant(tool_calls) + tool(result) + user_input = 5
        assert len(msgs) == 5
        assert msgs[2]["role"] == "assistant"
        assert "tool_calls" in msgs[2]
        assert msgs[3]["role"] == "tool"
        assert msgs[3]["tool_call_id"] == "c1"


class TestToolExchangePersistence:
    """持久化：save_jsonl / load_jsonl 兼容 tool_exchange。"""

    def test_roundtrip_tool_exchange(self, ctx):
        """写入 → 读出 → 完全相同。"""
        tc = ToolCallRecord("c1", "get_stats", '{"col":"X"}', "mean=5.0", None)
        ctx.add_tool_exchange("analyst", 0, [tc])

        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "test.jsonl"
            ctx.save_jsonl(str(path))
            restored = ProjectContext.load_jsonl(str(path), "r1", "分析ROI")

        assert len(restored.entries) == 1
        re = restored.entries[0]
        assert re.type == "tool_exchange"
        assert re.tool_calls is not None
        assert len(re.tool_calls) == 1
        rtc = re.tool_calls[0]
        assert rtc.tool_call_id == "c1"
        assert rtc.name == "get_stats"
        assert rtc.arguments == '{"col":"X"}'
        assert rtc.result == "mean=5.0"
        assert rtc.error is None

    def test_roundtrip_tool_exchange_with_error(self, ctx):
        """含错误的 tool_exchange 也能完整恢复。"""
        tc = ToolCallRecord("c1", "bad", "{}", "", "崩溃了")
        ctx.add_tool_exchange("cleaner", 0, [tc])

        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "test.jsonl"
            ctx.save_jsonl(str(path))
            restored = ProjectContext.load_jsonl(str(path), "r1", "分析ROI")

        assert restored.entries[0].tool_calls[0].error == "崩溃了"

    def test_roundtrip_mixed_entries(self, ctx):
        """混合 entry 类型（含 tool_exchange）完整恢复。"""
        ctx.add_user_feedback("scout", 0, "Code是店铺编号")
        ctx.add_agent_response("scout", 0, "好的")
        tc = ToolCallRecord("c1", "get_stats", "{}", "ok")
        ctx.add_tool_exchange("analyst", 0, [tc])

        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "test.jsonl"
            ctx.save_jsonl(str(path))
            restored = ProjectContext.load_jsonl(str(path), "r1", "分析ROI")

        assert len(restored.entries) == 3
        assert restored.entries[0].type == "user_feedback"
        assert restored.entries[1].type == "agent_response"
        assert restored.entries[2].type == "tool_exchange"
        assert restored.entries[2].tool_calls is not None
