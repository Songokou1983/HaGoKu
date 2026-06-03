"""验证 Analyst.run() 在当前代码状态下不会出现 AttributeError 或消息顺序错误"""
from unittest.mock import MagicMock, patch
import json as _json
import pandas as pd

from hagoku.agents.analyst.agent import AnalystAgent
from hagoku.config import LLMConfig
from hagoku.observability.event_bus import EventBus


def test_analyst_run_completes_with_submit_analysis():
    """验证 Analyst.run() 在 LLM 调 submit_analysis 后正常返回。"""
    config = LLMConfig()
    bus = EventBus()
    agent = AnalystAgent(config, bus)

    df = pd.DataFrame({"A": [1, 2], "B": [3, 4]})
    context = {"query": "测试", "column_semantics": []}

    # Mock LLM: 第一轮返回 submit_analysis
    mock_client = MagicMock()
    choice = MagicMock()
    msg = MagicMock()
    tc = MagicMock()
    tc.function.name = "submit_analysis"
    tc.function.arguments = _json.dumps({"findings": [], "method_used": [], "summary": "ok"})
    tc.id = "call_test123"
    msg.tool_calls = [tc]
    msg.content = ""
    choice.message = msg
    resp = MagicMock()
    resp.choices = [choice]
    mock_client.chat.completions.create.return_value = resp

    agent.llm_config = config

    with patch("hagoku.llm.client.create_raw_client", return_value=mock_client):
        with patch("hagoku.tools.registry.agent_tools") as mock_agt:
            mock_agt.dispatch.return_value = {"findings": [], "summary": "ok"}
            mock_agt.to_openai.return_value = []
            result = agent.run(df, context)

    assert isinstance(result, dict)
    assert "findings" in result
