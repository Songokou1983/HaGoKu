"""A-2: 端到端验证 Analyst 阶段进入时触发首波自动分析（Phase B 升级版）"""
from unittest.mock import MagicMock, patch
import pandas as pd

from hagoku.config import HaGoKuConfig
from hagoku.manager.orchestrator import Orchestrator
from hagoku.context.project_context import ProjectContext
from hagoku.observability.events import EventType


def test_handle_analyst_reply_triggers_first_pass_on_first_entry():
    """首次进入 Analyst 阶段 → _handle_analyst_reply 触发首波 + 设置 _analyst_first_pass_done=True。"""
    orch = Orchestrator(HaGoKuConfig())
    orch._df_clean = pd.DataFrame({"A": [1, 2]})

    pc = ProjectContext(run_id="test", analysis_goal="测试分析")
    context = {"query": "test", "column_semantics": [], "_project_context": pc}

    assert not orch._analyst_first_pass_done

    with patch(
        "hagoku.manager.llm_dispatch.reply_handlers._run_analyst_first_pass",
        return_value=None,
    ):
        result = orch._handle_analyst_reply("确认", context)

    assert orch._analyst_first_pass_done, "首次进入应设置 _analyst_first_pass_done=True"
    assert result["status"] == "analyst_review"

    # Phase B: 用户尾话写入 ProjectContext
    user_entries = [e for e in pc.entries if e.type == "user_feedback" and e.stage == "analyst"]
    assert len(user_entries) >= 1, f"用户尾话应写入 ProjectContext，实际 entries: {pc.entries}"
    assert user_entries[0].raw_user_text == "确认"


def test_handle_analyst_reply_skips_first_pass_on_second_entry():
    """第二次进入 Analyst 阶段 → 不再触发首波，直接进入阶段 2 对话。"""
    orch = Orchestrator(HaGoKuConfig())
    orch._df_clean = pd.DataFrame({"A": [1, 2]})
    orch._analyst_first_pass_done = True

    from hagoku.agents.agent import DataAnalystAgent
    orch._agent = DataAnalystAgent.__new__(DataAnalystAgent)
    orch._agent.llm_config = orch.config.llm
    orch._agent.event_bus = orch.event_bus
    orch._agent.prompt = "test"

    pc = ProjectContext(run_id="test", analysis_goal="测试")
    pc.add_user_feedback("analyst", 0, "首轮对话")
    context = {"query": "test", "column_semantics": [], "_project_context": pc}

    step_result = {
        "text": "收到，请说",
        "submit_analysis": False,
        "findings": None,
    }
    orch._agent.run_step = MagicMock(return_value=step_result)

    with patch(
        "hagoku.manager.llm_dispatch.reply_handlers._run_analyst_first_pass",
    ) as mock_first_pass:
        result = orch._handle_analyst_reply("换个方法试试", context)

    mock_first_pass.assert_not_called()
    assert result["status"] == "analyst_review"
    assert result["message"] == "收到，请说"


def test_handle_analyst_reply_empty_input_first_pass():
    """Cleaner→Analyst 切换时空输入 → 首波跑但不追加空用户消息。"""
    orch = Orchestrator(HaGoKuConfig())
    orch._df_clean = pd.DataFrame({"A": [1, 2]})

    pc = ProjectContext(run_id="test", analysis_goal="测试")
    context = {"query": "test", "column_semantics": [], "_project_context": pc}

    with patch(
        "hagoku.manager.llm_dispatch.reply_handlers._run_analyst_first_pass",
        return_value=None,
    ):
        result = orch._handle_analyst_reply("", context)

    assert orch._analyst_first_pass_done
    # 空输入不应追加 user 消息
    user_msgs = [e for e in pc.entries if e.type == "user_feedback" and e.stage == "analyst"]
    assert len(user_msgs) == 0, f"空输入不应追加 user 消息，实际: {user_msgs}"
    assert result["status"] == "analyst_review"


def test_reset_run_state_clears_first_pass_flag():
    """_reset_run_state 应重置 _analyst_first_pass_done。"""
    orch = Orchestrator(HaGoKuConfig())
    orch._analyst_first_pass_done = True
    orch._reset_run_state()
    assert not orch._analyst_first_pass_done, "_reset_run_state 应重置 _analyst_first_pass_done"
