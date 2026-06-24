"""B-1: 验证 Scout route_to 链路修复 — channels-through agent.run_step"""
from unittest.mock import MagicMock
import json as _json

from hagoku.config import HaGoKuConfig
from hagoku.agents.agent import DataAnalystAgent
from hagoku.manager.orchestrator import Orchestrator


def _setup_scout_context():
    return {
        "column_semantics": [
            {"column_name": "Inc1", "display_name": "收入", "suggested_role": "target", "used_in_analysis": True},
            {"column_name": "Inc2", "display_name": "费用", "suggested_role": "feature", "used_in_analysis": True},
        ],
        "column_descriptions": {"Inc1": "店铺收入", "Inc2": "店铺费用"},
        "column_display_names": {"Inc1": "收入", "Inc2": "费用"},
        "query": "分析收入趋势",
    }


def _setup_scout_agent(orch, route_to=None):
    orch._agent = DataAnalystAgent.__new__(DataAnalystAgent)
    orch._agent.llm_config = orch.config.llm
    orch._agent.event_bus = orch.event_bus
    orch._agent.prompt = ""
    orch._agent.run_step = MagicMock(return_value={"route_to": route_to} if route_to else {})


def test_scout_route_to_cleaner():
    orch = Orchestrator(HaGoKuConfig())
    context = _setup_scout_context()
    _setup_scout_agent(orch, {"stage": "cleaner", "reason": "done"})
    result = orch._handle_scout_reply("可以了，进入清洗", context)
    assert isinstance(result, dict)
    assert result["status"] == "scout_review"


def test_scout_route_to_reporter():
    orch = Orchestrator(HaGoKuConfig())
    context = _setup_scout_context()
    _setup_scout_agent(orch, {"stage": "reporter", "reason": "直接报告"})
    result = orch._handle_scout_reply("直接生成报告，跳过分析", context)
    assert isinstance(result, dict)
    assert result["status"] == "scout_review"


def test_scout_route_to_scout_stays():
    orch = Orchestrator(HaGoKuConfig())
    context = _setup_scout_context()
    _setup_scout_agent(orch, {"stage": "scout", "reason": "stay"})
    result = orch._handle_scout_reply("继续字段理解", context)
    assert not isinstance(result, tuple)
    assert result["status"] == "scout_review"


def test_scout_no_route_to_stays():
    orch = Orchestrator(HaGoKuConfig())
    context = _setup_scout_context()
    _setup_scout_agent(orch)  # no route_to
    result = orch._handle_scout_reply("好，继续", context)
    assert isinstance(result, dict)
    assert result["status"] == "scout_review"


def test_scout_route_to_priority():
    orch = Orchestrator(HaGoKuConfig())
    context = _setup_scout_context()
    _setup_scout_agent(orch, {"stage": "reporter", "reason": "跳"})
    result = orch._handle_scout_reply("字段没问题，去报告", context)
    assert isinstance(result, dict)
    assert result["status"] == "scout_review"


def test_scout_confirmation_stays_in_scout():
    orch = Orchestrator(HaGoKuConfig())
    context = _setup_scout_context()
    _setup_scout_agent(orch)  # no route_to
    result = orch._handle_scout_reply("确认", context)
    assert isinstance(result, dict)
    assert result["status"] == "scout_review"
