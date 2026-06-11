"""A-1: 验证 run_step 注入 system prompt + ProjectContext（Phase B 升级版）"""
from unittest.mock import MagicMock, patch
import pandas as pd

from hagoku.agents.analyst.agent import AnalystAgent
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


def test_run_step_injects_system_prompt_as_first_message():
    """Phase B: agent_system_extra（含 prompt.md）注入到 system 前缀。"""
    config = LLMConfig()
    bus = EventBus()
    agent = AnalystAgent(config, bus)
    assert agent.prompt, "prompt.md 应非空"

    pc = ProjectContext(run_id="test", analysis_goal="分析测试")
    df = pd.DataFrame({"A": [1, 2]})
    context = {"_project_context": pc}

    mock_resp = _make_mock_llm_response("分析结果")
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = mock_resp

    with patch("hagoku.llm.client.create_raw_client", return_value=mock_client):
        with patch("hagoku.tools.registry.agent_tools") as mock_agt:
            mock_agt.to_openai.return_value = []
            mock_agt.dispatch.return_value = {}
            agent.run_step(context, df, "分析")

    call_kwargs = mock_client.chat.completions.create.call_args.kwargs
    sent_messages = call_kwargs["messages"]
    assert sent_messages[0]["role"] == "system"
    assert "分析测试" in sent_messages[0]["content"] or agent.prompt[:10] in sent_messages[0]["content"]


def test_run_step_injects_project_context():
    """context 含 _project_context 时 system 含 analysis_goal。"""
    config = LLMConfig()
    bus = EventBus()
    agent = AnalystAgent(config, bus)

    pc = ProjectContext(run_id="test", analysis_goal="分析ROI")
    pc.add_agent_response(stage="scout", revision=0, content="ok",
                          snapshot={"target": "X", "features": [], "pending": []})

    df = pd.DataFrame({"X": [1, 2]})
    context = {"_project_context": pc, "query": "分析ROI"}

    mock_resp = _make_mock_llm_response("ok")
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = mock_resp

    with patch("hagoku.llm.client.create_raw_client", return_value=mock_client):
        with patch("hagoku.tools.registry.agent_tools") as mock_agt:
            mock_agt.to_openai.return_value = []
            mock_agt.dispatch.return_value = {}
            agent.run_step(context, df, "分析")

    call_kwargs = mock_client.chat.completions.create.call_args.kwargs
    sent = call_kwargs["messages"]
    all_text = " ".join(m.get("content", "") for m in sent)
    assert "分析ROI" in all_text


def test_run_step_no_project_context_raises():
    """Phase B: _project_context 缺失应 raise RuntimeError。"""
    import pytest
    config = LLMConfig()
    bus = EventBus()
    agent = AnalystAgent(config, bus)
    agent.prompt = "test"
    df = pd.DataFrame({"A": [1]})
    context = {}  # 无 _project_context

    with pytest.raises(RuntimeError, match="_project_context"):
        agent.run_step(context, df, "分析")


def test_run_step_returns_no_messages():
    """Phase B: run_step 返回不再含 messages 键。"""
    config = LLMConfig()
    bus = EventBus()
    agent = AnalystAgent(config, bus)
    agent.prompt = "test"

    pc = ProjectContext(run_id="test", analysis_goal="测试")
    df = pd.DataFrame({"A": [1]})
    context = {"_project_context": pc}

    mock_resp = _make_mock_llm_response("分析完成")
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = mock_resp

    with patch("hagoku.llm.client.create_raw_client", return_value=mock_client):
        with patch("hagoku.tools.registry.agent_tools") as mock_agt:
            mock_agt.to_openai.return_value = []
            mock_agt.dispatch.return_value = {}
            result = agent.run_step(context, df, "分析")

    assert "messages" not in result
    assert "text" in result
