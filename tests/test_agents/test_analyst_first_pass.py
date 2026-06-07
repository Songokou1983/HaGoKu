"""A-2: 验证首波自动分析 + 书面概括化"""
from unittest.mock import MagicMock, patch, ANY
import json as _json

from hagoku.config import HaGoKuConfig
from hagoku.manager.orchestrator import Orchestrator
from hagoku.observability.events import EventType


def _make_mock_step_result(text="", findings=None, submit_analysis=False):
    """构造 run_step 返回值。"""
    return {
        "messages": [{"role": "assistant", "content": text}],
        "text": text,
        "submit_analysis": submit_analysis,
        "findings": findings,
    }


def _capture_event_bus_emits(orch):
    """Patch EventBus.emit to capture all calls."""
    emits = []
    original_emit = orch.event_bus.emit

    def _capture(event_type, agent, data=None):
        emits.append((event_type, agent, data))
        original_emit(event_type, agent, data)

    return patch.object(orch.event_bus, "emit", side_effect=_capture), emits


def test_rewrite_as_written_summary_calls_llm_with_three_element_prompt():
    """断言 _rewrite_as_written_summary 调 LLM 时 system prompt 含三要素约束。"""
    orch = Orchestrator(HaGoKuConfig())
    findings = {
        "findings": [{"title": "渠道差异显著", "detail": "渠道A ROI高于渠道B", "evidence_columns": ["channel"], "confidence": "high"}],
        "method_used": ["ttest"],
        "summary": "渠道A显著优于渠道B",
    }

    mock_client = MagicMock()
    mock_msg = MagicMock()
    mock_msg.content = "[发现] 渠道差异显著\n[统计依据] p=0.001\n[局限或解读] 样本量偏小"
    mock_choice = MagicMock()
    mock_choice.message = mock_msg
    mock_resp = MagicMock()
    mock_resp.choices = [mock_choice]
    mock_client.chat.completions.create.return_value = mock_resp

    with patch("hagoku.llm.client.create_raw_client", return_value=mock_client):
        from hagoku.manager.llm_dispatch.reply_handlers import _rewrite_as_written_summary
        result = _rewrite_as_written_summary(orch, findings)

    # 断言 LLM 被调用
    mock_client.chat.completions.create.assert_called_once()
    call_kwargs = mock_client.chat.completions.create.call_args.kwargs

    # 断言 system prompt 含三要素约束
    system_content = call_kwargs["messages"][0]["content"]
    assert "[发现]" in system_content, f"system prompt 应含 [发现] 标记，实际: {system_content[:200]}"
    assert "[统计依据]" in system_content, f"system prompt 应含 [统计依据] 标记"
    assert "[局限或解读]" in system_content, f"system prompt 应含 [局限或解读] 标记"

    # 断言结果非空
    assert result, "重写结果不应为空"


def test_run_analyst_first_pass_with_submit_first_pass():
    """Mock LLM 调 submit_first_pass → 断言 _run_analyst_first_pass 触发书面概括化 + emit USER_INPUT_REQUESTED。"""
    orch = Orchestrator(HaGoKuConfig())

    # 设置必要的状态
    from hagoku.agents.analyst import AnalystAgent
    orch._analyst_agent = AnalystAgent.__new__(AnalystAgent)
    orch._analyst_agent.llm_config = orch.config.llm
    orch._analyst_agent.event_bus = orch.event_bus
    orch._analyst_agent.prompt = "test prompt"
    orch._analyst_messages = []
    orch._df_clean = None

    # Mock run_step 返回 submit_first_pass 工具调用结果
    # 模拟：assistant 消息含 tool_calls(submit_first_pass) + 后续 tool 消息含 findings
    step_result = {
        "messages": [
            {
                "role": "assistant",
                "content": "首波分析完成",
                "tool_calls": [
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {"name": "submit_first_pass", "arguments": '{"findings": [{"title": "t1", "detail": "d1", "evidence_columns": ["c1"], "confidence": "high"}], "method_used": ["ttest"], "summary": "ok"}'},
                    }
                ],
            },
            {
                "role": "tool",
                "tool_call_id": "call_1",
                "content": '{"findings": [{"title": "t1", "detail": "d1", "evidence_columns": ["c1"], "confidence": "high"}], "method_used": ["ttest"], "summary": "ok"}',
            },
        ],
        "text": "首波分析完成",
        "submit_analysis": False,
        "findings": None,
    }
    orch._analyst_agent.run_step = MagicMock(return_value=step_result)

    # Mock _rewrite_as_written_summary
    rewrite_output = "[发现] 测试发现\n[统计依据] p=0.05\n[局限或解读] 样本小"
    with patch(
        "hagoku.manager.llm_dispatch.reply_handlers._rewrite_as_written_summary",
        return_value=rewrite_output,
    ):
        # Capture event bus emits
        emits = []
        with patch.object(orch.event_bus, "emit", wraps=lambda et, ag, data=None: emits.append((et, ag, data))):
            from hagoku.manager.llm_dispatch.reply_handlers import _run_analyst_first_pass
            _run_analyst_first_pass(orch, {"query": "test"})

    # 断言 USER_INPUT_REQUESTED 已 emit
    user_events = [e for e in emits if e[0] == EventType.USER_INPUT_REQUESTED]
    assert len(user_events) >= 1, f"应 emit USER_INPUT_REQUESTED，实际 emits: {emits}"

    event = user_events[0]
    assert event[1] == "analyst", f"agent 应为 analyst，实际: {event[1]}"
    message = event[2].get("message", "")
    assert "[发现]" in message, f"message 应含 [发现] 标记，实际: {message[:200]}"
    assert "[统计依据]" in message, f"message 应含 [统计依据] 标记"
    assert "[局限或解读]" in message, f"message 应含 [局限或解读] 标记"


def test_run_analyst_first_pass_converges_when_no_tool_calls():
    """LLM 不再调工具时应收敛（无 submit_first_pass 时）。"""
    orch = Orchestrator(HaGoKuConfig())

    from hagoku.agents.analyst import AnalystAgent
    orch._analyst_agent = AnalystAgent.__new__(AnalystAgent)
    orch._analyst_agent.llm_config = orch.config.llm
    orch._analyst_agent.event_bus = orch.event_bus
    orch._analyst_agent.prompt = "test"
    orch._analyst_messages = []
    orch._df_clean = None

    # run_step 返回纯文本，无 tool_calls
    step_result = {
        "messages": [{"role": "assistant", "content": "分析完成，没有发现异常"}],
        "text": "分析完成，没有发现异常",
        "submit_analysis": False,
        "findings": None,
    }
    orch._analyst_agent.run_step = MagicMock(return_value=step_result)

    emits = []
    with patch.object(orch.event_bus, "emit", wraps=lambda et, ag, data=None: emits.append((et, ag, data))):
        from hagoku.manager.llm_dispatch.reply_handlers import _run_analyst_first_pass
        _run_analyst_first_pass(orch, {"query": "test"})

    # 应 emit USER_INPUT_REQUESTED（即使无 findings）
    user_events = [e for e in emits if e[0] == EventType.USER_INPUT_REQUESTED]
    assert len(user_events) >= 1, "即使无 findings 也应收敛并 emit"


def test_rewrite_as_written_summary_no_fabrication():
    """验证 _rewrite_as_written_summary 的 system prompt 禁止编造数字。"""
    orch = Orchestrator(HaGoKuConfig())
    findings = {"findings": [], "method_used": [], "summary": "无发现"}

    mock_client = MagicMock()
    mock_msg = MagicMock()
    mock_msg.content = "无显著发现"
    mock_choice = MagicMock()
    mock_choice.message = mock_msg
    mock_resp = MagicMock()
    mock_resp.choices = [mock_choice]
    mock_client.chat.completions.create.return_value = mock_resp

    with patch("hagoku.llm.client.create_raw_client", return_value=mock_client):
        from hagoku.manager.llm_dispatch.reply_handlers import _rewrite_as_written_summary
        _rewrite_as_written_summary(orch, findings)

    call_kwargs = mock_client.chat.completions.create.call_args.kwargs
    system_content = call_kwargs["messages"][0]["content"]
    assert "不许编造" in system_content, "system prompt 必须禁止编造数字"
