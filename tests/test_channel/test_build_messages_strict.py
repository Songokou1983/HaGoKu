"""build_messages() 严格 schema 测试（Phase B CO-B1）。

覆盖 §2.3 行为契约的 8 种场景，含 tool 协议支持（方案 B）。
"""

import pytest
from pydantic import ValidationError

from hagoku.channel import (
    BuildMessagesInput,
    ChatTurn,
    ToolCall,
    _ChatTurnValidator,
    build_messages,
)


class TestBuildMessagesBasics:
    """基本场景：query + user_input 最小调用。"""

    def test_minimal_valid_call(self):
        msgs = build_messages(query="分析数据", user_input="请继续")
        assert len(msgs) == 2
        assert msgs[0] == {"role": "user", "content": "分析数据"}
        assert msgs[1] == {"role": "user", "content": "请继续"}

    def test_with_system_extra(self):
        msgs = build_messages(
            query="分析数据",
            user_input="请继续",
            system_extra="你是一个数据分析师",
        )
        assert len(msgs) == 3
        assert msgs[0] == {"role": "system", "content": "你是一个数据分析师"}
        assert msgs[1] == {"role": "user", "content": "分析数据"}
        assert msgs[2] == {"role": "user", "content": "请继续"}

    def test_system_extra_empty_string_omitted(self):
        """system_extra 为空时不注入 system 消息。"""
        msgs = build_messages(query="q", user_input="u", system_extra="")
        assert len(msgs) == 2
        assert msgs[0]["role"] == "user"

    def test_with_valid_user_assistant_history(self):
        msgs = build_messages(
            query="分析数据",
            user_input="请继续",
            history=[
                {"role": "user", "content": "看看收入"},
                {"role": "assistant", "content": "好的，收入分析如下..."},
            ],
        )
        assert len(msgs) == 4


class TestBuildMessagesInputValidation:
    """BuildMessagesInput schema 严格性测试。"""

    def test_extra_field_rejected(self):
        """未知顶层字段被拒绝（extra='forbid'）。"""
        with pytest.raises(ValidationError, match="extra"):
            BuildMessagesInput(query="q", user_input="u", extra_arg="x")

    def test_history_invalid_role_rejected(self):
        """history 中非法 role 被拒绝。"""
        with pytest.raises(ValidationError):
            BuildMessagesInput(
                query="q",
                user_input="u",
                history=[{"role": "junk", "content": "x"}],
            )

    def test_history_user_missing_content_rejected(self):
        """role=user 但缺 content → 拒绝。"""
        with pytest.raises(ValidationError):
            BuildMessagesInput(
                query="q",
                user_input="u",
                history=[{"role": "user"}],
            )

    def test_history_assistant_with_tool_calls_accepted(self):
        """role=assistant 可只有 tool_calls（方案 B 核心）。"""
        inp = BuildMessagesInput(
            query="q",
            user_input="u",
            history=[
                {
                    "role": "assistant",
                    "tool_calls": [
                        {
                            "id": "t1",
                            "type": "function",
                            "function": {"name": "x", "arguments": "{}"},
                        }
                    ],
                }
            ],
        )
        assert len(inp.history) == 1

    def test_history_tool_missing_tool_call_id_rejected(self):
        """role=tool 缺 tool_call_id → 拒绝。"""
        with pytest.raises(ValidationError):
            BuildMessagesInput(
                query="q",
                user_input="u",
                history=[{"role": "tool", "content": "result"}],
            )

    def test_history_user_with_tool_calls_rejected(self):
        """role=user 不允许 tool_calls。"""
        with pytest.raises(ValidationError):
            BuildMessagesInput(
                query="q",
                user_input="u",
                history=[
                    {
                        "role": "user",
                        "content": "x",
                        "tool_calls": [
                            {
                                "id": "t1",
                                "type": "function",
                                "function": {"name": "x", "arguments": "{}"},
                            }
                        ],
                    }
                ],
            )

    def test_history_assistant_empty_content_and_no_tool_calls_rejected(self):
        """role=assistant 必须有 content 或 tool_calls。"""
        with pytest.raises(ValidationError):
            BuildMessagesInput(
                query="q",
                user_input="u",
                history=[{"role": "assistant"}],
            )


class TestChatTurnValidator:
    """_ChatTurnValidator 边界场景。"""

    def test_tool_valid_turn_accepted(self):
        """合法的 tool turn。"""
        v = _ChatTurnValidator(
            role="tool", content="result", tool_call_id="t1"
        )
        assert v.role == "tool"

    def test_tool_with_tool_calls_rejected(self):
        """role=tool 不允许 tool_calls。"""
        with pytest.raises(ValidationError):
            _ChatTurnValidator(
                role="tool",
                content="result",
                tool_call_id="t1",
                tool_calls=[{"id": "x", "type": "function", "function": {"name": "x", "arguments": "{}"}}],
            )

    def test_assistant_with_tool_call_id_rejected(self):
        """role=assistant 不允许 tool_call_id。"""
        with pytest.raises(ValidationError):
            _ChatTurnValidator(
                role="assistant",
                content="hello",
                tool_call_id="t1",
            )


class TestBuildMessagesToolProtocol:
    """方案 B：build_messages 输出的 tool 协议完整性。"""

    def test_tool_exchange_roundtrip_preserved(self):
        """assistant(tool_calls) + tool(result) 在 messages 中完整保留。"""
        msgs = build_messages(
            query="分析数据",
            user_input="请解释",
            history=[
                {
                    "role": "assistant",
                    "tool_calls": [
                        {
                            "id": "call_1",
                            "type": "function",
                            "function": {"name": "get_stats", "arguments": '{"col":"Revenue"}'},
                        }
                    ],
                },
                {"role": "tool", "content": "mean=100.5", "tool_call_id": "call_1"},
                {
                    "role": "assistant",
                    "content": "收入均值为 100.5",
                },
            ],
        )
        assert len(msgs) == 5  # system empty → skipped, query, 2 history, user_input
        # history[0] = assistant with tool_calls
        assert msgs[1]["role"] == "assistant"
        assert "tool_calls" in msgs[1]
        assert len(msgs[1]["tool_calls"]) == 1
        assert msgs[1]["tool_calls"][0]["id"] == "call_1"
        # history[1] = tool result
        assert msgs[2]["role"] == "tool"
        assert msgs[2]["content"] == "mean=100.5"
        assert msgs[2]["tool_call_id"] == "call_1"
        # history[2] = assistant text
        assert msgs[3]["role"] == "assistant"
        assert msgs[3]["content"] == "收入均值为 100.5"
