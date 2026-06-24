"""CL-2: 验证 Cleaner 纯通道模式（Phase D 扁平化）

_handle_cleaner_reply 现为存根，直接 delegate 到 _handle_reply。
不再有首次评估/对话模式切换/route_to 跳转。
"""
from unittest.mock import MagicMock, patch
import json as _json
import pandas as pd

from hagoku.config import HaGoKuConfig
from hagoku.manager.orchestrator import Orchestrator


def _setup_cleaner_context():
    return {
        "column_semantics": [
            {"column_name": "A", "display_name": "列A", "suggested_role": "target", "used_in_analysis": True},
        ],
        "query": "分析",
    }


def test_cleaner_reply_with_agent():
    """_handle_cleaner_reply 非空输入 → 调 _agent.run_step → 返回 scout_review。"""
    orch = Orchestrator(HaGoKuConfig())
    orch._df_raw = pd.DataFrame({"A": [1, 2]})
    orch._df_clean = orch._df_raw
    context = _setup_cleaner_context()

    from hagoku.agents.agent import DataAnalystAgent
    orch._agent = DataAnalystAgent.__new__(DataAnalystAgent)
    orch._agent.llm_config = orch.config.llm
    orch._agent.event_bus = orch.event_bus
    orch._agent.prompt = "test"
    orch._agent.run_step = MagicMock(return_value={
        "text": "评估完成",
        "submit_assessment": False,
        "assessment": None,
        "route_to": None,
    })

    result = orch._handle_cleaner_reply("评估", context)
    assert result["status"] == "scout_review"
    orch._agent.run_step.assert_called_once()


def test_cleaner_reply_returns_dict():
    """_handle_cleaner_reply 始终返回 dict。"""
    orch = Orchestrator(HaGoKuConfig())
    orch._df_raw = pd.DataFrame({"A": [1, 2]})
    orch._df_clean = orch._df_raw
    context = _setup_cleaner_context()

    from hagoku.agents.agent import DataAnalystAgent
    orch._agent = DataAnalystAgent.__new__(DataAnalystAgent)
    orch._agent.llm_config = orch.config.llm
    orch._agent.event_bus = orch.event_bus
    orch._agent.prompt = "test"
    orch._agent.run_step = MagicMock(return_value={
        "text": "收到",
        "submit_assessment": False,
        "assessment": None,
        "route_to": None,
    })

    result = orch._handle_cleaner_reply("换个方案", context)
    assert isinstance(result, dict)
    assert result["status"] == "scout_review"


def test_cleaner_route_to_no_longer_switches():
    """LLM route_to 已删除 — _handle_cleaner_reply 返回 dict 而非 switch tuple"""
    orch = Orchestrator(HaGoKuConfig())
    orch._df_raw = pd.DataFrame({"A": [1, 2]})
    orch._df_clean = orch._df_raw
    context = _setup_cleaner_context()

    from hagoku.agents.agent import DataAnalystAgent
    orch._agent = DataAnalystAgent.__new__(DataAnalystAgent)
    orch._agent.llm_config = orch.config.llm
    orch._agent.event_bus = orch.event_bus
    orch._agent.prompt = "test"
    orch._agent.run_step = MagicMock(return_value={
        "text": "好的",
        "submit_assessment": False,
        "assessment": None,
        "route_to": {"stage": "analyst", "reason": "清洗完成"},
    })

    result = orch._handle_cleaner_reply("可以了", context)
    assert isinstance(result, dict)
    assert result["status"] == "scout_review"


def test_cleaner_confirmation_text_no_longer_triggers_switch():
    """Phase C: 用户说"确认"但无 route_to → 留在 cleaner（不再硬编码切 analyst）。"""
    orch = Orchestrator(HaGoKuConfig())
    orch._df_raw = pd.DataFrame({"A": [1, 2]})
    orch._df_clean = orch._df_raw
    context = _setup_cleaner_context()

    from hagoku.agents.agent import DataAnalystAgent
    orch._agent = DataAnalystAgent.__new__(DataAnalystAgent)
    orch._agent.llm_config = orch.config.llm
    orch._agent.event_bus = orch.event_bus
    orch._agent.prompt = "test"
    orch._agent.run_step = MagicMock(return_value={
        "text": "ok",
        "submit_assessment": False,
        "assessment": None,
        "route_to": None,
    })

    result = orch._handle_cleaner_reply("确认", context)
    # Phase C/D: 留在当前，不再自动切 analyst
    assert isinstance(result, dict)
    assert result["status"] == "scout_review"
