"""A-2: 验证 _handle_analyst_reply 纯通道模式（Phase D 扁平化）"""
from unittest.mock import MagicMock
import pandas as pd

from hagoku.config import HaGoKuConfig
from hagoku.manager.orchestrator import Orchestrator
from hagoku.context.session import Session
from hagoku.observability.events import EventType


def test_handle_analyst_reply_delegates_to_agent_run_step():
    """_handle_analyst_reply 非空输入 → 调 _agent.run_step，返回 scout_review。"""
    orch = Orchestrator(HaGoKuConfig())
    orch._df_clean = pd.DataFrame({"A": [1, 2]})

    from hagoku.agents.agent import DataAnalystAgent
    orch._agent = DataAnalystAgent.__new__(DataAnalystAgent)
    orch._agent.llm_config = orch.config.llm
    orch._agent.event_bus = orch.event_bus
    orch._agent.prompt = "test"

    session = Session(analysis_goal="测试分析")
    context = {"query": "test", "column_semantics": [], "_session": session}

    step_result = {
        "text": "收到，请说",
        "submit_findings": False,
        "findings": None,
    }
    orch._agent.run_step = MagicMock(return_value=step_result)

    result = orch._handle_analyst_reply("确认", context)

    orch._agent.run_step.assert_called_once()
    assert result["status"] == "scout_review"
    assert result["message"] == "收到，请说"

    user_msgs = [m for m in session.messages if m.get("role") == "user"]
    assert len(user_msgs) == 0, f"handler 不应写入 user_feedback（由 respond 统一），实际: {user_msgs}"


def test_handle_analyst_reply_with_mock_agent():
    """_handle_analyst_reply 带 mock agent：验证纯通道返回 dict。"""
    orch = Orchestrator(HaGoKuConfig())
    orch._df_clean = pd.DataFrame({"A": [1, 2]})

    from hagoku.agents.agent import DataAnalystAgent
    orch._agent = DataAnalystAgent.__new__(DataAnalystAgent)
    orch._agent.llm_config = orch.config.llm
    orch._agent.event_bus = orch.event_bus
    orch._agent.prompt = "test"

    session = Session(analysis_goal="测试")
    context = {"query": "test", "column_semantics": [], "_session": session}

    step_result = {
        "text": "收到，请说",
        "submit_findings": False,
        "findings": None,
    }
    orch._agent.run_step = MagicMock(return_value=step_result)

    result = orch._handle_analyst_reply("换个方法试试", context)

    assert result["status"] == "scout_review"
    assert result["message"] == "收到，请说"


def test_handle_analyst_reply_empty_input():
    """空输入 → 不调 run_step，返回 scout_review + 空 message。"""
    orch = Orchestrator(HaGoKuConfig())
    orch._df_clean = pd.DataFrame({"A": [1, 2]})

    session = Session(analysis_goal="测试")
    context = {"query": "test", "column_semantics": [], "_session": session}

    result = orch._handle_analyst_reply("", context)

    assert result["status"] == "scout_review"
    assert result["message"] == ""

    user_msgs = [m for m in session.messages if m.get("role") == "user"]
    assert len(user_msgs) == 0, f"空输入不应追加 user 消息，实际: {user_msgs}"


def test_reset_run_state_clears_first_pass_flag():
    """_reset_run_state 清理运行时字段（_stage 已删除）。"""
    orch = Orchestrator(HaGoKuConfig())
    orch._df_raw = pd.DataFrame({"a": [1]})
    orch._df_clean = pd.DataFrame({"b": [2]})
    orch._error = ValueError("test")
    orch._reset_run_state()
    assert orch._df_raw is None
    assert orch._df_clean is None
    assert orch._error is None
