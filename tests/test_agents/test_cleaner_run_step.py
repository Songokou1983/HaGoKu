"""CL-1: 验证 Cleaner run_step + _compose_system_messages"""
from unittest.mock import MagicMock, patch
import json as _json
import pandas as pd

from hagoku.agents.cleaner.agent import CleanerAgent
from hagoku.config import LLMConfig
from hagoku.observability.event_bus import EventBus
from hagoku.context.project_context import ProjectContext


def _make_mock_llm_response(content="", tool_calls=None):
    choice = MagicMock()
    msg = MagicMock()
    msg.content = content
    if tool_calls:
        msg.tool_calls = tool_calls
    choice.message = msg
    resp = MagicMock()
    resp.choices = [choice]
    return resp


def test_run_step_injects_system_prompt():
    """断言 Cleaner run_step 注入 system prompt。"""
    config = LLMConfig()
    bus = EventBus()
    agent = CleanerAgent(config, bus)
    assert agent.prompt, "prompt.md 应非空"

    df = pd.DataFrame({"A": [1, 2], "B": [3, 4]})
    context = {}
    messages = [{"role": "user", "content": "评估"}]

    mock_resp = _make_mock_llm_response("评估完成")
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = mock_resp

    with patch("hagoku.llm.client.create_raw_client", return_value=mock_client):
        with patch("hagoku.tools.registry.agent_tools") as mock_agt:
            mock_agt.to_openai.return_value = []
            result = agent.run_step(messages, context, df)

    call_kwargs = mock_client.chat.completions.create.call_args.kwargs
    sent_messages = call_kwargs["messages"]
    assert sent_messages[0]["role"] == "system"

    # 返回的 messages 不含 system
    returned = result["messages"]
    roles = {m.get("role") for m in returned}
    assert "system" not in roles


def test_run_step_returns_submit_assessment():
    """LLM 调 submit_assessment → run_step 返回 submit_assessment=True。"""
    config = LLMConfig()
    bus = EventBus()
    agent = CleanerAgent(config, bus)
    agent.prompt = "test"

    df = pd.DataFrame({"A": [1]})
    context = {}
    messages = [{"role": "user", "content": "评估"}]

    tc = MagicMock()
    tc.function.name = "submit_assessment"
    tc.function.arguments = _json.dumps({"summary": "ok", "columns": []})
    tc.id = "call_1"
    mock_resp = _make_mock_llm_response("done", [tc])
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = mock_resp

    with patch("hagoku.llm.client.create_raw_client", return_value=mock_client):
        with patch("hagoku.tools.registry.agent_tools") as mock_agt:
            mock_agt.dispatch.return_value = {"summary": "ok", "columns": []}
            mock_agt.to_openai.return_value = []
            result = agent.run_step(messages, context, df)

    assert result["submit_assessment"] is True
    assert result["assessment"] == {"summary": "ok", "columns": []}


def test_run_step_injects_project_context():
    """context 含 _project_context 时注入 upstream_summary。"""
    config = LLMConfig()
    bus = EventBus()
    agent = CleanerAgent(config, bus)

    pc = ProjectContext(run_id="test", analysis_goal="清洗评估")
    pc.add_agent_response(stage="scout", revision=0, content="ok",
                          snapshot={"target": "X", "features": [], "pending": []})

    df = pd.DataFrame({"X": [1, 2]})
    context = {"_project_context": pc}
    messages = [{"role": "user", "content": "评估"}]

    mock_resp = _make_mock_llm_response("ok")
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = mock_resp

    with patch("hagoku.llm.client.create_raw_client", return_value=mock_client):
        with patch("hagoku.tools.registry.agent_tools") as mock_agt:
            mock_agt.to_openai.return_value = []
            agent.run_step(messages, context, df)

    call_kwargs = mock_client.chat.completions.create.call_args.kwargs
    sent = call_kwargs["messages"]
    all_text = " ".join(m.get("content", "") for m in sent)
    assert "清洗评估" in all_text or "分析目标" in all_text
