"""A-3: 验证 Analyst route_to 链路修复"""
from unittest.mock import MagicMock, patch
import json as _json
import pandas as pd

from hagoku.config import HaGoKuConfig
from hagoku.manager.orchestrator import Orchestrator


def _setup_analyst_agent_for_test(orch):
    """设置 mock AnalystAgent 用于 route_to 测试。"""
    from hagoku.agents.agent import DataAnalystAgent
    orch._df_clean = pd.DataFrame({"A": [1, 2], "B": [3, 4]})
    orch._agent = DataAnalystAgent.__new__(DataAnalystAgent)
    orch._agent.llm_config = orch.config.llm
    orch._agent.event_bus = orch.event_bus
    orch._agent.prompt = "test prompt"
    orch._analyst_messages = [{"role": "user", "content": "够了，去写报告吧"}]
    orch._analyst_first_pass_done = True


def test_route_to_reporter_no_longer_switches():
    """LLM route_to 已删除 — _handle_analyst_reply 返回 dict 而非 switch tuple"""
    orch = Orchestrator(HaGoKuConfig())
    _setup_analyst_agent_for_test(orch)

    step_result = {
        "messages": orch._analyst_messages + [{"role": "assistant", "content": "好的"}],
        "text": "好的，切换至报告阶段",
        "submit_findings": False,
        "findings": None,
        "route_to": {"stage": "reporter", "reason": "用户要求进入报告阶段"},
    }
    orch._agent.run_step = MagicMock(return_value=step_result)

    result = orch._handle_analyst_reply("够了，去写报告吧", {"query": "test"})

    assert isinstance(result, dict), f"应返回 dict，实际: {type(result)}"
    assert result["status"] == "analyst_review"


def test_route_to_scout_no_longer_switches():
    """LLM route_to 已删除 — _handle_analyst_reply 返回 dict"""
    orch = Orchestrator(HaGoKuConfig())
    _setup_analyst_agent_for_test(orch)

    step_result = {
        "messages": orch._analyst_messages,
        "text": "方向不对，回 Scout 重看字段",
        "submit_findings": False,
        "findings": None,
        "route_to": {"stage": "scout", "reason": "字段理解可能有问题"},
    }
    orch._agent.run_step = MagicMock(return_value=step_result)

    result = orch._handle_analyst_reply("方向不对，回去重看字段", {"query": "test"})

    assert isinstance(result, dict)
    assert result["status"] == "analyst_review"


def test_route_to_cleaner_no_longer_switches():
    """LLM route_to 已删除 — _handle_analyst_reply 返回 dict"""
    orch = Orchestrator(HaGoKuConfig())
    _setup_analyst_agent_for_test(orch)

    step_result = {
        "messages": orch._analyst_messages,
        "text": "清洗方案不对",
        "submit_findings": False,
        "findings": None,
        "route_to": {"stage": "cleaner", "reason": "清洗方案需要调整"},
    }
    orch._agent.run_step = MagicMock(return_value=step_result)

    result = orch._handle_analyst_reply("Cleaner 的清洗方案不对", {"query": "test"})

    assert isinstance(result, dict)
    assert result["status"] == "analyst_review"


def test_route_to_without_stage_stays():
    """LLM 调 route_to() 不传 stage → 留在当前阶段，不切换。"""
    orch = Orchestrator(HaGoKuConfig())
    _setup_analyst_agent_for_test(orch)

    step_result = {
        "messages": orch._analyst_messages + [{"role": "assistant", "content": "再等等"}],
        "text": "好的，再等等",
        "submit_findings": False,
        "findings": None,
        "route_to": {"reason": "用户说再等等"},
    }
    orch._agent.run_step = MagicMock(return_value=step_result)

    result = orch._handle_analyst_reply("再等等，我再看看", {"query": "test"})

    # 不应是 tuple（不应切换）
    assert not isinstance(result, tuple), f"不传 stage 不应切换，实际: {result}"
    assert result["status"] == "analyst_review"


def test_route_to_analyst_stays():
    """LLM 调 route_to(stage="analyst") → 留在当前阶段（不切换到自己）"""
    orch = Orchestrator(HaGoKuConfig())
    _setup_analyst_agent_for_test(orch)

    step_result = {
        "messages": orch._analyst_messages,
        "text": "继续分析",
        "submit_findings": False,
        "findings": None,
        "route_to": {"stage": "analyst", "reason": "继续"},
    }
    orch._agent.run_step = MagicMock(return_value=step_result)

    result = orch._handle_analyst_reply("继续分析", {"query": "test"})

    assert not isinstance(result, tuple), f"stage=analyst 不应切换，实际: {result}"
    assert result["status"] == "analyst_review"


def test_route_to_and_other_tools_no_longer_switches():
    """LLM route_to 已删除 — run_step 同轮既有 route_to 又有其他工具，handler 只返回 dict。"""
    orch = Orchestrator(HaGoKuConfig())
    _setup_analyst_agent_for_test(orch)

    # run_step 返回 route_to + 文本（正常执行了其他工具的结果）
    step_result = {
        "messages": orch._analyst_messages + [{"role": "assistant", "content": "检验完成，可以收尾了"}],
        "text": "检验完成，可以收尾了",
        "submit_findings": False,
        "findings": None,
        "route_to": {"stage": "reporter", "reason": "用户要求收尾"},
    }
    orch._agent.run_step = MagicMock(return_value=step_result)

    result = orch._handle_analyst_reply("够了，去写报告", {"query": "test"})

    assert isinstance(result, dict)
    assert result["status"] == "analyst_review"


def test_no_route_to_no_switch():
    """LLM 不调 route_to → 正常对话，不切换。"""
    orch = Orchestrator(HaGoKuConfig())
    _setup_analyst_agent_for_test(orch)

    step_result = {
        "messages": orch._analyst_messages + [{"role": "assistant", "content": "已执行 t 检验"}],
        "text": "已执行 t 检验，p=0.03",
        "submit_findings": False,
        "findings": None,
        "route_to": None,
    }
    orch._agent.run_step = MagicMock(return_value=step_result)

    result = orch._handle_analyst_reply("换 t 检验试试", {"query": "test"})

    assert not isinstance(result, tuple), f"无 route_to 不应切换，实际: {result}"
    assert result["status"] == "analyst_review"
    assert "t 检验" in result["message"]
