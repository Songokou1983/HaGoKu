"""A-2: 验证首波自动分析 + 书面概括化（Phase B 升级版）"""
from unittest.mock import MagicMock, patch, ANY
import json as _json

from hagoku.config import HaGoKuConfig
from hagoku.manager.orchestrator import Orchestrator
from hagoku.observability.events import EventType
from hagoku.context.project_context import ProjectContext, ToolCallRecord


def _make_mock_step_result(text="", findings=None, submit_analysis=False):
    """Phase B: run_step 不再返回 messages。"""
    return {
        "text": text,
        "submit_analysis": submit_analysis,
        "findings": findings,
    }


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

    mock_client.chat.completions.create.assert_called_once()
    call_kwargs = mock_client.chat.completions.create.call_args.kwargs
    system_content = call_kwargs["messages"][0]["content"]
    assert "[发现]" in system_content, f"system prompt 应含 [发现] 标记，实际: {system_content[:200]}"
    assert "[统计依据]" in system_content
    assert "[局限或解读]" in system_content
    assert result, "重写结果不应为空"


def test_run_analyst_first_pass_with_submit_first_pass():
    """Phase B: submit_first_pass 检测从 ProjectContext entries 读取 tool_exchange。"""
    orch = Orchestrator(HaGoKuConfig())

    from hagoku.agents.agent import DataAnalystAgent
    orch._agent = DataAnalystAgent.__new__(DataAnalystAgent)
    orch._agent.llm_config = orch.config.llm
    orch._agent.event_bus = orch.event_bus
    orch._agent.prompt = "test prompt"
    orch._df_clean = None

    # 构造 context 含 ProjectContext（submit_first_pass 结果记录为 tool_exchange）
    pc = ProjectContext(run_id="test", analysis_goal="分析测试")
    findings_dict = {"findings": [{"title": "t1", "detail": "d1", "evidence_columns": ["c1"], "confidence": "high"}], "method_used": ["ttest"], "summary": "ok"}
    pc.add_tool_exchange("analyst", 0, [
        ToolCallRecord(
            tool_call_id="call_1",
            name="submit_first_pass",
            arguments='{"findings": [{"title": "t1"}]}',
            result=_json.dumps(findings_dict),
        )
    ])
    context = {"_project_context": pc, "query": "test"}

    step_result = _make_mock_step_result(text="首波分析完成")
    orch._agent.run_step = MagicMock(return_value=step_result)

    rewrite_output = "[发现] 测试发现\n[统计依据] p=0.05\n[局限或解读] 样本小"
    with patch(
        "hagoku.manager.llm_dispatch.reply_handlers._rewrite_as_written_summary",
        return_value=rewrite_output,
    ):
        emits = []
        with patch.object(orch.event_bus, "emit", wraps=lambda et, ag, data=None: emits.append((et, ag, data))):
            from hagoku.manager.llm_dispatch.reply_handlers import _run_analyst_first_pass
            _run_analyst_first_pass(orch, context)

    user_events = [e for e in emits if e[0] == EventType.USER_INPUT_REQUESTED]
    assert len(user_events) >= 1, f"应 emit USER_INPUT_REQUESTED，实际 emits: {emits}"
    event = user_events[0]
    assert event[1] == "analyst"
    message = event[2].get("message", "")
    assert "[发现]" in message


def test_run_analyst_first_pass_converges_when_no_tool_calls():
    """首波无 findings 时必须失败在场（铁律 7）。"""
    import pytest
    orch = Orchestrator(HaGoKuConfig())

    from hagoku.agents.agent import DataAnalystAgent
    orch._agent = DataAnalystAgent.__new__(DataAnalystAgent)
    orch._agent.llm_config = orch.config.llm
    orch._agent.event_bus = orch.event_bus
    orch._agent.prompt = "test"
    orch._df_clean = None

    context = {"query": "test"}

    step_result = _make_mock_step_result(text="分析完成，没有发现异常")
    orch._agent.run_step = MagicMock(return_value=step_result)

    from hagoku.manager.llm_dispatch.reply_handlers import _run_analyst_first_pass
    with pytest.raises(RuntimeError, match="首波自动分析未产生有效统计发现"):
        _run_analyst_first_pass(orch, context)


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
