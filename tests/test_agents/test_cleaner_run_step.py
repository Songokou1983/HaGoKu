"""CL-1: 验证 Cleaner run_step（Phase B 升级版）"""
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


def test_run_step_injects_prompt_md_into_system():
    """Phase B: agent_system_extra（含 prompt.md）注入到 system 前缀。"""
    config = LLMConfig()
    bus = EventBus()
    agent = CleanerAgent(config, bus)
    assert agent.prompt, "prompt.md 应非空"

    pc = ProjectContext(run_id="test", analysis_goal="测试清洗")
    df = pd.DataFrame({"A": [1, 2], "B": [3, 4]})
    context = {"_project_context": pc, "query": "测试"}

    mock_resp = _make_mock_llm_response("评估完成")
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = mock_resp

    with patch("hagoku.llm.client.create_raw_client", return_value=mock_client):
        with patch("hagoku.tools.registry.agent_tools") as mock_agt:
            mock_agt.to_openai.return_value = []
            mock_agt.dispatch.return_value = {}
            agent.run_step(context, df, "评估")

    call_kwargs = mock_client.chat.completions.create.call_args.kwargs
    sent_messages = call_kwargs["messages"]
    # 第一条应为 system（包含 prompt.md 内容）
    assert sent_messages[0]["role"] == "system"
    # prompt.md 内容在 system 消息里
    assert "清洗" in sent_messages[0]["content"] or agent.prompt[:10] in sent_messages[0]["content"]


def test_run_step_returns_submit_assessment():
    """LLM 调 submit_assessment → run_step 返回 submit_assessment=True。"""
    config = LLMConfig()
    bus = EventBus()
    agent = CleanerAgent(config, bus)
    agent.prompt = "test"

    pc = ProjectContext(run_id="test", analysis_goal="测试")
    df = pd.DataFrame({"A": [1]})
    context = {"_project_context": pc}

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
            result = agent.run_step(context, df, "评估")

    assert result["submit_assessment"] is True
    assert result["assessment"] == {"summary": "ok", "columns": []}
    # Phase B: messages 不再返回
    assert "messages" not in result


def test_run_step_injects_project_context():
    """context 含 _project_context 时 system 消息含 analysis_goal。"""
    config = LLMConfig()
    bus = EventBus()
    agent = CleanerAgent(config, bus)

    pc = ProjectContext(run_id="test", analysis_goal="清洗评估")
    pc.add_agent_response(stage="scout", revision=0, content="ok",
                          snapshot={"target": "X", "features": [], "pending": []})

    df = pd.DataFrame({"X": [1, 2]})
    context = {"_project_context": pc, "query": "清洗评估"}

    mock_resp = _make_mock_llm_response("ok")
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = mock_resp

    with patch("hagoku.llm.client.create_raw_client", return_value=mock_client):
        with patch("hagoku.tools.registry.agent_tools") as mock_agt:
            mock_agt.to_openai.return_value = []
            mock_agt.dispatch.return_value = {}
            agent.run_step(context, df, "评估")

    call_kwargs = mock_client.chat.completions.create.call_args.kwargs
    sent = call_kwargs["messages"]
    all_text = " ".join(m.get("content", "") for m in sent)
    assert "清洗评估" in all_text or "分析目标" in all_text
