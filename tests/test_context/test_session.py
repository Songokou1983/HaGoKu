"""Session 单元测试。"""
from hagoku.context.session import Session, ToolCallRecord


class TestSessionBasic:
    def test_create_session(self):
        s = Session(analysis_goal="分析收入趋势")
        assert s.analysis_goal == "分析收入趋势"
        assert s.messages == []

    def test_add_user_message(self):
        s = Session(analysis_goal="test")
        s.add("user", "Inc1是店铺收入")
        assert len(s.messages) == 1
        assert s.messages[0]["role"] == "user"
        assert s.messages[0]["content"] == "Inc1是店铺收入"

    def test_add_assistant_message(self):
        s = Session(analysis_goal="test")
        s.add("assistant", "已更新字段理解")
        assert len(s.messages) == 1
        assert s.messages[0]["role"] == "assistant"
        assert s.messages[0]["content"] == "已更新字段理解"

    def test_add_multiple_messages(self):
        s = Session(analysis_goal="test")
        s.add("user", "hello")
        s.add("assistant", "hi")
        s.add("user", "ok")
        assert len(s.messages) == 3


class TestSessionToolExchange:
    def test_add_tool_call_creates_assistant_and_tool_messages(self):
        s = Session(analysis_goal="test")
        s.add_tool_call(
            assistant_text="让我查一下",
            tool_calls=[{
                "id": "call_1",
                "type": "function",
                "function": {"name": "get_sample_rows", "arguments": '{"column":"BU"}'},
            }],
            tool_results=[{
                "content": '{"sample":["B01","B02"]}',
                "tool_call_id": "call_1",
            }],
        )
        assert len(s.messages) == 2
        assert s.messages[0]["role"] == "assistant"
        assert s.messages[0]["content"] == "让我查一下"
        assert s.messages[0]["tool_calls"][0]["function"]["name"] == "get_sample_rows"
        assert s.messages[1]["role"] == "tool"
        assert s.messages[1]["tool_call_id"] == "call_1"

    def test_add_tool_call_without_text(self):
        s = Session(analysis_goal="test")
        s.add_tool_call(
            assistant_text="",
            tool_calls=[{
                "id": "call_1",
                "type": "function",
                "function": {"name": "set_columns", "arguments": "{}"},
            }],
            tool_results=[{
                "content": "ok",
                "tool_call_id": "call_1",
            }],
        )
        # assistant_text="" → no content key
        assert "content" not in s.messages[0]

    def test_add_tool_call_multiple_tools(self):
        s = Session(analysis_goal="test")
        s.add_tool_call(
            assistant_text="查三个列",
            tool_calls=[
                {"id": "c1", "type": "function", "function": {"name": "a", "arguments": "{}"}},
                {"id": "c2", "type": "function", "function": {"name": "b", "arguments": "{}"}},
            ],
            tool_results=[
                {"content": "r1", "tool_call_id": "c1"},
                {"content": "r2", "tool_call_id": "c2"},
            ],
        )
        assert len(s.messages) == 3  # 1 assistant + 2 tool


class TestSessionLLMMessages:
    def test_to_llm_messages_basic(self):
        s = Session(analysis_goal="分析收入")
        s.add("user", "Inc1是什么")
        s.add("assistant", "Inc1是收入指标")
        msgs = s.to_llm_messages(system_extra="【理解字段】")
        assert msgs[0]["role"] == "system"
        assert msgs[0]["content"] == "【理解字段】"
        assert msgs[1]["role"] == "user"
        assert msgs[1]["content"] == "分析收入"
        assert msgs[2]["role"] == "user"
        assert msgs[2]["content"] == "Inc1是什么"
        assert msgs[3]["role"] == "assistant"
        assert msgs[3]["content"] == "Inc1是收入指标"

    def test_to_llm_messages_with_user_input(self):
        s = Session(analysis_goal="分析收入")
        s.add("user", "之前说过的话")
        msgs = s.to_llm_messages(system_extra="prompt", user_input="现在说的")
        # user_input is appended at the end
        assert msgs[-1]["role"] == "user"
        assert msgs[-1]["content"] == "现在说的"

    def test_to_llm_messages_preserves_tool_calls(self):
        s = Session(analysis_goal="test")
        s.add_tool_call(
            assistant_text="查询",
            tool_calls=[{
                "id": "c1", "type": "function",
                "function": {"name": "get_sample_rows", "arguments": "{}"},
            }],
            tool_results=[{"content": "ok", "tool_call_id": "c1"}],
        )
        msgs = s.to_llm_messages()
        # Should have: user(goal), assistant(tool_calls), tool
        assert msgs[1]["role"] == "assistant"
        assert "tool_calls" in msgs[1]
        assert msgs[2]["role"] == "tool"


class TestSessionPersistence:
    def test_save_and_load(self, tmp_path):
        path = str(tmp_path / "session.json")
        s = Session(analysis_goal="测试")
        s.add("user", "hello")
        s.save(path)

        s2 = Session.load(path)
        assert s2.analysis_goal == "测试"
        assert len(s2.messages) == 1
        assert s2.messages[0]["role"] == "user"
        assert s2.messages[0]["content"] == "hello"

    def test_load_nonexistent(self, tmp_path):
        path = str(tmp_path / "nonexistent.json")
        s = Session.load(path, analysis_goal="default")
        assert s.analysis_goal == "default"
        assert s.messages == []

    def test_auto_save_with_path(self, tmp_path):
        path = str(tmp_path / "auto.json")
        s = Session(analysis_goal="test")
        s._save_path = path
        s.add("user", "auto saved")
        # Load back
        s2 = Session.load(path)
        assert len(s2.messages) == 1
