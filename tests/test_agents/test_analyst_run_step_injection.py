"""A-1: 验证 run_step 注入 system prompt + ProjectContext"""
from unittest.mock import MagicMock, patch
import json as _json
import pandas as pd

from hagoku.agents.analyst.agent import AnalystAgent
from hagoku.config import LLMConfig
from hagoku.observability.event_bus import EventBus
from hagoku.context.project_context import ProjectContext


def _make_mock_llm_response(content: str = "", tool_calls: list | None = None) -> MagicMock:
    """构造一个 mock LLM 响应。"""
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
    """断言传给 LLM 的 messages[0].role == 'system'，且含 prompt.md 关键词。"""
    config = LLMConfig()
    bus = EventBus()
    agent = AnalystAgent(config, bus)

    # 确保 prompt.md 已加载
    assert agent.prompt, "prompt.md 应非空"

    df = pd.DataFrame({"A": [1, 2], "B": [3, 4]})
    context: dict = {}
    messages: list[dict] = [{"role": "user", "content": "分析测试"}]

    mock_resp = _make_mock_llm_response(content="收到，开始分析")
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = mock_resp

    with patch("hagoku.llm.client.create_raw_client", return_value=mock_client):
        with patch("hagoku.tools.registry.agent_tools") as mock_agt:
            mock_agt.to_openai.return_value = []
            result = agent.run_step(messages, context, df)

    # 断言 LLM 被调用
    mock_client.chat.completions.create.assert_called_once()
    call_kwargs = mock_client.chat.completions.create.call_args.kwargs
    sent_messages = call_kwargs["messages"]

    # 断言第一条是 system 消息
    assert sent_messages[0]["role"] == "system", (
        f"第一条消息应为 system，实际为 {sent_messages[0]['role']}"
    )

    # 断言 system prompt 含 prompt.md 关键词
    system_content = sent_messages[0]["content"]
    assert "数理分析员" in system_content or "Analyst" in system_content, (
        f"system prompt 应含 prompt.md 内容，实际内容前 200 字符: {system_content[:200]}"
    )

    # 断言返回的 messages 不含 system 头（避免永久存储）
    returned_messages = result["messages"]
    for m in returned_messages:
        assert m.get("role") != "system", (
            f"返回的 messages 不应含 system 角色，发现: {m}"
        )


def test_run_step_injects_project_context():
    """断言当 context 含 _project_context 时，system messages 含 upstream_summary。"""
    config = LLMConfig()
    bus = EventBus()
    agent = AnalystAgent(config, bus)

    # 构造一个 ProjectContext，注入一条 Scout 阶段的 agent_response
    pc = ProjectContext(run_id="test-run", analysis_goal="哪个渠道 ROI 最高")
    pc.add_agent_response(
        stage="scout", revision=0,
        content="字段理解完成",
        snapshot={
            "fields": [{"name": "channel", "display": "渠道", "role": "feature", "participating": True}],
            "target": "roi",
            "features": ["channel"],
            "pending": [],
        },
    )

    df = pd.DataFrame({"channel": ["A", "B"], "roi": [0.5, 0.3]})
    context: dict = {"_project_context": pc}
    messages: list[dict] = [{"role": "user", "content": "分析"}]

    mock_resp = _make_mock_llm_response(content="开始分析")
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = mock_resp

    with patch("hagoku.llm.client.create_raw_client", return_value=mock_client):
        with patch("hagoku.tools.registry.agent_tools") as mock_agt:
            mock_agt.to_openai.return_value = []
            agent.run_step(messages, context, df)

    call_kwargs = mock_client.chat.completions.create.call_args.kwargs
    sent_messages = call_kwargs["messages"]

    # 断言至少有 2 条 system 消息（prompt.md + ProjectContext）
    system_msgs = [m for m in sent_messages if m["role"] == "system"]
    assert len(system_msgs) >= 2, (
        f"应有 >=2 条 system 消息（prompt.md + ProjectContext），实际 {len(system_msgs)} 条"
    )

    # 断言其中一条含 ProjectContext 内容（upstream_summary 或 system_prefix）
    all_system_text = " ".join(m["content"] for m in system_msgs)
    assert "哪个渠道 ROI 最高" in all_system_text or "分析目标" in all_system_text, (
        f"system 消息应含 ProjectContext 上下文，实际内容: {all_system_text[:300]}"
    )


def test_run_step_no_project_context_still_injects_prompt():
    """即使 context 无 _project_context，仍注入 prompt.md 作为 system 消息。"""
    config = LLMConfig()
    bus = EventBus()
    agent = AnalystAgent(config, bus)

    df = pd.DataFrame({"A": [1]})
    context: dict = {}  # 无 _project_context
    messages: list[dict] = [{"role": "user", "content": "分析"}]

    mock_resp = _make_mock_llm_response(content="收到")
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = mock_resp

    with patch("hagoku.llm.client.create_raw_client", return_value=mock_client):
        with patch("hagoku.tools.registry.agent_tools") as mock_agt:
            mock_agt.to_openai.return_value = []
            agent.run_step(messages, context, df)

    call_kwargs = mock_client.chat.completions.create.call_args.kwargs
    sent_messages = call_kwargs["messages"]

    # 断言至少有 1 条 system 消息
    system_msgs = [m for m in sent_messages if m["role"] == "system"]
    assert len(system_msgs) >= 1, "即使无 ProjectContext，也应有 prompt.md 作为 system 消息"


def test_run_step_returns_messages_without_system_prefix():
    """返回的 messages 不应含 system 角色，避免 `_analyst_messages` 永久存储 system prompt。"""
    config = LLMConfig()
    bus = EventBus()
    agent = AnalystAgent(config, bus)

    df = pd.DataFrame({"A": [1]})
    context: dict = {}
    messages: list[dict] = [{"role": "user", "content": "分析"}]

    mock_resp = _make_mock_llm_response(content="收到")
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = mock_resp

    with patch("hagoku.llm.client.create_raw_client", return_value=mock_client):
        with patch("hagoku.tools.registry.agent_tools") as mock_agt:
            mock_agt.to_openai.return_value = []
            result = agent.run_step(messages, context, df)

    returned = result["messages"]
    roles = {m.get("role") for m in returned}
    assert "system" not in roles, (
        f"返回的 messages 不应含 system 角色，实际 roles: {roles}"
    )
