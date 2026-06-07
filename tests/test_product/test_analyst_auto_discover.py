"""A-2: 端到端验证 Analyst 阶段进入时触发首波自动分析"""
from unittest.mock import MagicMock, patch
import pandas as pd

from hagoku.config import HaGoKuConfig
from hagoku.manager.orchestrator import Orchestrator
from hagoku.observability.events import EventType


def test_handle_analyst_reply_triggers_first_pass_on_first_entry():
    """首次进入 Analyst 阶段 → _handle_analyst_reply 触发首波 + 设置 _analyst_first_pass_done=True。"""
    orch = Orchestrator(HaGoKuConfig())
    orch._df_clean = pd.DataFrame({"A": [1, 2]})

    context = {"query": "test", "column_semantics": []}

    # 确认初始状态
    assert not orch._analyst_first_pass_done

    # Mock _run_analyst_first_pass 为 no-op（不调真 LLM）
    with patch(
        "hagoku.manager.llm_dispatch.reply_handlers._run_analyst_first_pass",
        return_value=None,
    ):
        result = orch._handle_analyst_reply("确认", context)

    # 断言 _analyst_first_pass_done 变为 True
    assert orch._analyst_first_pass_done, "首次进入应设置 _analyst_first_pass_done=True"

    # 断言返回 status 为 analyst_review
    assert result["status"] == "analyst_review"

    # 断言首次进入时用户尾话被保留为阶段 2 第一条消息
    assert len(orch._analyst_messages) >= 1
    first_user_msg = orch._analyst_messages[0]
    assert first_user_msg["role"] == "user"
    assert first_user_msg["content"] == "确认"


def test_handle_analyst_reply_skips_first_pass_on_second_entry():
    """第二次进入 Analyst 阶段 → 不再触发首波，直接进入阶段 2 对话。"""
    orch = Orchestrator(HaGoKuConfig())
    orch._df_clean = pd.DataFrame({"A": [1, 2]})
    orch._analyst_first_pass_done = True  # 模拟首波已完成

    # 设置 agent 和 messages
    from hagoku.agents.analyst import AnalystAgent
    orch._analyst_agent = AnalystAgent.__new__(AnalystAgent)
    orch._analyst_agent.llm_config = orch.config.llm
    orch._analyst_agent.event_bus = orch.event_bus
    orch._analyst_agent.prompt = "test"
    orch._analyst_messages = [{"role": "user", "content": "首轮对话"}]

    context = {"query": "test", "column_semantics": []}

    # Mock run_step 返回正常对话
    step_result = {
        "messages": [
            {"role": "user", "content": "首轮对话"},
            {"role": "assistant", "content": "收到，请说"},
        ],
        "text": "收到，请说",
        "submit_analysis": False,
        "findings": None,
    }
    orch._analyst_agent.run_step = MagicMock(return_value=step_result)

    # 确认 _run_analyst_first_pass 未被调用
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

    context = {"query": "test", "column_semantics": []}

    with patch(
        "hagoku.manager.llm_dispatch.reply_handlers._run_analyst_first_pass",
        return_value=None,
    ):
        result = orch._handle_analyst_reply("", context)

    assert orch._analyst_first_pass_done
    # 空输入不应追加 user 消息
    user_msgs = [m for m in orch._analyst_messages if m.get("role") == "user"]
    assert len(user_msgs) == 0, f"空输入不应追加 user 消息，实际: {user_msgs}"
    assert result["status"] == "analyst_review"


def test_reset_run_state_clears_first_pass_flag():
    """_reset_run_state 应重置 _analyst_first_pass_done。"""
    orch = Orchestrator(HaGoKuConfig())
    orch._analyst_first_pass_done = True
    orch._reset_run_state()
    assert not orch._analyst_first_pass_done, "_reset_run_state 应重置 _analyst_first_pass_done"
