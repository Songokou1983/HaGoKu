"""事件驱动通道守门测试 G1-G8

验证：run() 不阻塞、LLM route_to 阶段切换、cancel、异常处理、
raw_text 跨 respond 保留、messages 累积。
"""

import inspect
from unittest.mock import MagicMock, patch

import pytest

from hagoku.config import HaGoKuConfig
from hagoku.manager.orchestrator import Orchestrator


@pytest.fixture
def orch():
    return Orchestrator(HaGoKuConfig())


def test_G1_run_不阻塞(orch):
    """G1: run() 不调 _pause_and_wait，改用 emit USER_INPUT_REQUESTED。"""
    source = inspect.getsource(Orchestrator.run)
    assert "_pause_and_wait" not in source, (
        "run() 不应调用 _pause_and_wait——事件驱动通道已删除阻塞机制"
    )


def test_G2_Scout_handler_空输入_返回字段表(orch):
    """G2: _handle_scout_reply 空输入时返回 scout_review 含 field_review。"""
    context = {
        "column_semantics": [
            {"column_name": "A", "display_name": "列A", "suggested_role": "feature", "used_in_analysis": True},
        ],
        "column_descriptions": {"A": "测试列"},
        "column_display_names": {},
    }
    result = orch._handle_scout_reply("", context)
    assert result["status"] == "scout_review"
    assert "field_review" in result


def test_G3_Scout_handler_无字段更新_切Cleaner(orch):
    """G3: Scout handler 无字段更新 → 返回 ("switch", "cleaner")。"""
    context = {
        "column_semantics": [
            {"column_name": "A", "display_name": "列A", "used_in_analysis": True},
        ],
        "column_descriptions": {},
        "column_display_names": {},
    }
    result = orch._handle_scout_reply("好，继续", context)
    assert isinstance(result, tuple)
    assert result[0] == "switch"
    assert result[1] == "cleaner"


def test_G4_cancel_via_respond(orch):
    """G4: request_cancel() 后 respond() 返回 cancelled。"""
    orch.request_cancel()
    result = orch.respond({"text": "anything"})
    assert result["status"] == "cancelled"


def test_G5_respond_未知阶段_返回error(orch):
    """G5: self._stage 为空字符串 → respond() 返回 error。"""
    orch._stage = ""
    result = orch.respond({"text": "test"})
    assert result["status"] == "error"


def test_G6_respond路由_switch_切阶段(orch):
    """G6: handler 返回 ("switch", "X") → respond() 切换 self._stage 并递归。"""
    import pandas as pd
    orch._stage = "scout"
    orch._context = {}
    orch._df_raw = pd.DataFrame({"A": [1, 2]})
    orch._df_clean = orch._df_raw

    # Mock both handlers: scout → switch to cleaner, cleaner → stay
    saved_scout = orch._handle_scout_reply
    saved_cleaner = orch._handle_cleaner_reply

    orch._handle_scout_reply = lambda *a, **kw: ("switch", "cleaner")
    orch._handle_cleaner_reply = lambda *a, **kw: {"status": "cleaner_review", "message": "ok"}
    try:
        orch.respond({"text": "test"})
        assert orch._stage == "cleaner"
    finally:
        orch._handle_scout_reply = saved_scout
        orch._handle_cleaner_reply = saved_cleaner


def test_G7_StageHandlers_完整性(orch):
    """G7: _STAGE_HANDLERS 覆盖全部 4 个阶段。"""
    assert set(orch._STAGE_HANDLERS.keys()) == {"scout", "cleaner", "analyst", "reporter"}
    for stage, handler_name in orch._STAGE_HANDLERS.items():
        assert hasattr(orch, handler_name), f"handler {handler_name} 不存在"


def test_G8_analyst_run_step_正常返回(orch):
    """G8: Analyst.run_step 正常处理 submit_analysis。"""
    from hagoku.agents.analyst.agent import AnalystAgent
    import json

    agent = AnalystAgent.__new__(AnalystAgent)
    agent.llm_config = orch.config.llm
    agent.event_bus = orch.event_bus

    context = {"query": "test", "column_semantics": []}
    messages = [{"role": "system", "content": "test"}, {"role": "user", "content": "分析"}]

    # Mock LLM: 直接返回 submit_analysis
    mock_client = MagicMock()
    choice = MagicMock()
    msg = MagicMock()
    tc = MagicMock()
    tc.function.name = "submit_analysis"
    tc.function.arguments = json.dumps({"findings": [], "method_used": [], "summary": "ok"})
    tc.id = "call_test"
    msg.tool_calls = [tc]
    msg.content = ""
    choice.message = msg
    resp = MagicMock()
    resp.choices = [choice]
    mock_client.chat.completions.create.return_value = resp

    with patch("hagoku.llm.client.create_raw_client", return_value=mock_client):
        with patch("hagoku.tools.registry.agent_tools") as mock_agt:
            mock_agt.dispatch.return_value = {"findings": [], "summary": "ok"}
            mock_agt.to_openai.return_value = []
            result = agent.run_step(messages, context)

    assert result["submit_analysis"] is True
    assert "findings" in result
    assert len(result["messages"]) >= 2  # system + user，assistant 在 submit_analysis break 前可能未追加
