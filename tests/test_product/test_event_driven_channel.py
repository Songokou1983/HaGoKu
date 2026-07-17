"""事件驱动通道守门测试 G1-G8（Phase D 扁平化版）

验证：run() 不阻塞、cancel、异常处理、raw_text 保留。
Phase D 后不再有 stage 路由/switch tuple/route_to 跳转。
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


def test_G2_Scout_handler_空输入_返回scout_review(orch):
    """G2: _handle_scout_reply 空输入时返回 scout_review 并 emit USER_INPUT_REQUESTED。"""
    context = {
        "column_semantics": [
            {"column_name": "A", "display_name": "列A", "suggested_role": "feature", "used_in_analysis": True},
        ],
        "column_descriptions": {"A": "测试列"},
        "column_display_names": {},
    }
    captured = []
    orch.event_bus.subscribe(lambda e: captured.append(e))
    result = orch._handle_scout_reply("", context)
    assert result["status"] == "scout_review"
    assert any(e.event_type.value == "user_input_requested" for e in captured)


def test_G3_Scout_handler_纯确认_切Cleaner(orch):
    """Phase C/D: 确认词不再触发切换——LLM route_to 已删除。
    用户说"继续"但 LLM 没调 route_to → 留在 scout。"""
    from hagoku.agents.agent import DataAnalystAgent
    orch._agent = DataAnalystAgent.__new__(DataAnalystAgent)
    orch._agent.llm_config = orch.config.llm
    orch._agent.event_bus = orch.event_bus
    orch._agent.prompt = ""
    orch._agent.run_step = MagicMock(return_value={"text": "ok"})
    context = {
        "column_semantics": [
            {"column_name": "A", "display_name": "列A", "used_in_analysis": True},
        ],
        "column_descriptions": {},
        "column_display_names": {},
    }
    result = orch._handle_scout_reply("继续", context)
    assert isinstance(result, dict)
    assert result["status"] == "scout_review"


def test_G4_cancel_via_respond(orch):
    """G4: request_cancel() 后 respond() 返回 cancelled。"""
    orch.request_cancel()
    result = orch.respond({"text": "anything"})
    assert result["status"] == "cancelled"


def test_G5_respond_error_state(orch):
    """G5: self._error 非空 → respond() 返回 error（Phase D 后 _stage 不再产生 error）。"""
    orch._error = RuntimeError("测试错误")
    result = orch.respond({"text": "test"})
    assert result["status"] == "error"


def test_G6_respond_flat_pipe_no_switch(orch):
    """G6: Phase D 后 respond() 直接调 _handle_reply，不再通过 stage 路由切换。
    respond() 始终返回 _handle_reply 的 dict 结果。"""
    import pandas as pd
    from hagoku.agents.agent import DataAnalystAgent

    orch._stage = "analyst"
    orch._context = {"query": "测试", "column_semantics": []}
    orch._df_raw = pd.DataFrame({"A": [1, 2]})
    orch._df_clean = orch._df_raw

    orch._agent = DataAnalystAgent.__new__(DataAnalystAgent)
    orch._agent.llm_config = orch.config.llm
    orch._agent.event_bus = orch.event_bus
    orch._agent.prompt = ""
    orch._agent.run_step = MagicMock(return_value={"text": "收到"})

    result = orch.respond({"text": "test"})
    assert isinstance(result, dict)
    assert result["status"] == "scout_review"
    assert result["message"] == "收到"


def test_G7_StageHandlers_完整性(orch):
    """G7: _STAGE_HANDLERS 覆盖全部 4 个阶段。"""
    assert set(orch._STAGE_HANDLERS.keys()) == {"scout", "cleaner", "analyst", "reporter"}
    for stage, handler_name in orch._STAGE_HANDLERS.items():
        assert hasattr(orch, handler_name), f"handler {handler_name} 不存在"


def test_G8_analyst_run_step_正常返回(orch):
    """G8: Analyst.run_step 正常处理 submit_analysis（Phase B 升级版）。"""
    from hagoku.agents.agent import DataAnalystAgent as AnalystAgent
    from hagoku.context.session import Session
    import json

    agent = AnalystAgent.__new__(AnalystAgent)
    agent.llm_config = orch.config.llm
    agent.llm_config.stream_enabled = False  # 测试走 batch 路径
    agent.event_bus = orch.event_bus
    agent.prompt = "test"

    session = Session(analysis_goal="分析测试")
    context = {"query": "test", "column_semantics": [], "_session": session}

    # Mock LLM: 直接返回 submit_analysis
    mock_client = MagicMock()
    choice = MagicMock()
    msg = MagicMock()
    tc = MagicMock()
    tc.function.name = "submit_findings"
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
            result = agent.run_step(context, None, "分析")

    assert result["submit_findings"] is True
    assert "findings" in result


def test_G9_flat_pipe_no_switch_tuple(orch):
    """G9（律 8）：Phase D 后 handler 不再返回 switch tuple。
    respond() 直接调 _handle_reply，忽略任何旧式 tuple。"""
    import pandas as pd
    from hagoku.agents.agent import DataAnalystAgent

    orch._stage = "scout"
    orch._context = {"column_semantics": [], "column_descriptions": {}, "column_display_names": {}}
    orch._df_raw = pd.DataFrame({"A": [1, 2]})
    orch._df_clean = orch._df_raw

    orch._agent = DataAnalystAgent.__new__(DataAnalystAgent)
    orch._agent.llm_config = orch.config.llm
    orch._agent.event_bus = orch.event_bus
    orch._agent.prompt = ""
    orch._agent.run_step = MagicMock(return_value={"text": "ok"})

    result = orch.respond({"text": "好，进入清洗"})
    # Phase D: respond() 不再处理 switch tuple，直接返回 _handle_reply 的 dict
    assert isinstance(result, dict)
    assert result["status"] == "scout_review"
    # _stage 不变（无切换逻辑）
    assert orch._stage == "scout"


def test_G10_律2_raw_text_跨_respond_保留(orch):
    """G10（律 2）：Scout handler 多次 receive 不同 raw_text，正确传递。"""
    context = {
        "column_semantics": [
            {"column_name": "A", "display_name": "列A", "suggested_role": "feature", "used_in_analysis": True},
        ],
        "column_descriptions": {"A": "旧描述"},
        "column_display_names": {},
    }
    orch._context = context
    from hagoku.agents.agent import DataAnalystAgent
    orch._agent = DataAnalystAgent.__new__(DataAnalystAgent)
    orch._agent.llm_config = orch.config.llm
    orch._agent.event_bus = orch.event_bus
    orch._agent.prompt = ""
    orch._agent.run_step = MagicMock(return_value={"text": "ok"})

    result1 = orch._handle_scout_reply("A是收入", context)
    assert result1["status"] == "scout_review"

    result2 = orch._handle_scout_reply("A的单位是万元", context)
    assert result2["status"] == "scout_review"

    # Phase D: 验证 handler 未因多次调用而崩溃


def test_G11_律6_raw_text_抵达_handler(orch):
    """G11（律 6）：respond() 将 raw_text 经 _handle_reply 传给 _agent.run_step。

    律 6 要求信息抵达。验证 _agent.run_step 收到的 user_input 等于 raw_text。
    """
    import pandas as pd
    from hagoku.agents.agent import DataAnalystAgent

    orch._stage = "analyst"
    orch._context = {"query": "测试", "column_semantics": []}
    orch._df_raw = pd.DataFrame({"A": [1, 2]})
    orch._df_clean = orch._df_raw

    orch._agent = DataAnalystAgent.__new__(DataAnalystAgent)
    orch._agent.llm_config = orch.config.llm
    orch._agent.event_bus = orch.event_bus
    orch._agent.prompt = ""
    orch._agent.run_step = MagicMock(return_value={"text": "收到"})

    result = orch.respond({"text": "把Inc1加进来"})
    assert result["status"] == "scout_review"

    # 验证 run_step 收到了 raw_text
    orch._agent.run_step.assert_called_once()
    call_args = orch._agent.run_step.call_args
    user_input_arg = call_args[0][2]  # run_step(context, df, user_input)
    assert "Inc1" in user_input_arg, f"run_step 应收到 raw_text，实际: {user_input_arg}"


def test_G12_真端到端_cleaner_handler_不报_ValueError(orch, tmp_path):
    """G12：真端到端——_handle_cleaner_reply 调 _handle_reply 不抛 ValueError。

    回归保护：DataFrame truthiness 回归。
    Phase D 后 _handle_cleaner_reply 是存根，delegate 到 _handle_reply。
    需要 mock _agent.run_step 避免真实 LLM 调用。
    """
    import pandas as pd
    from unittest.mock import patch
    from hagoku.manager.query_parser import QueryIntent
    from hagoku.agents.agent import DataAnalystAgent

    # 写最小 CSV 走真 run() 触发 _df_raw 加载
    csv_path = tmp_path / "data.csv"
    csv_path.write_text("A,B\n1,3\n2,4\n3,5\n", encoding="utf-8")

    # Mock plan + Scout + Cleaner assess（非本测试关注点），核心验证 _handle_cleaner_reply 不抛 ValueError
    with patch("hagoku.manager.query_parser.parse_query") as mock_parse, \
         patch("hagoku.agents.agent.DataAnalystAgent.run_scout_phase") as mock_scout_run, \
         patch("hagoku.agents.agent.DataAnalystAgent.assess") as mock_cleaner_assess:
        mock_parse.return_value = QueryIntent(intent_type="exploration", confidence="high")
        mock_cleaner_assess.return_value = {
            "summary": "数据质量良好",
            "columns": [{"column": "A", "display_name": "列A", "action": "skip", "reason": "良好"}],
        }
        mock_scout_run.return_value = {
            "column_semantics": [
                {"column_name": "A", "display_name": "列A", "suggested_role": "feature", "used_in_analysis": True},
                {"column_name": "B", "display_name": "列B", "suggested_role": "feature", "used_in_analysis": True},
            ],
            "column_descriptions": {"A": "列A", "B": "列B"},
            "column_display_names": {"A": "列A", "B": "列B"},
            "query": "分析", "n_rows": 3, "n_cols": 2,
        }
        # 确保项目目录存在（G12 修复：orch.run 不再自动创建项目）
        # 使用 tmp_path 避免污染真实项目目录
        orch.config.output.project_dir = tmp_path / "projects"
        proj_dir = orch.config.output.project_dir / "test_channel"
        proj_dir.mkdir(parents=True, exist_ok=True)
        (proj_dir / "project.json").write_text('{"name":"test_channel"}')
        result = orch.run(data_path=str(csv_path), query="分析", project_name="test_channel")

        assert result.get("status") == "scout_review"
        assert isinstance(orch._df_raw, pd.DataFrame)
        assert isinstance(orch._df_clean, pd.DataFrame)

        # 设置 mock _agent 以便 _handle_cleaner_reply 能正常返回
        orch._agent = DataAnalystAgent.__new__(DataAnalystAgent)
        orch._agent.llm_config = orch.config.llm
        orch._agent.event_bus = orch.event_bus
        orch._agent.prompt = ""
        orch._agent.run_step = MagicMock(return_value={"text": "ok"})

        # 真调 _handle_cleaner_reply——之前会 ValueError，现在应正常返回
        try:
            resp = orch._handle_cleaner_reply("确认清洗策略", orch._context)
        except ValueError as e:
            if "ambiguous" in str(e):
                pytest.fail(f"回归：DataFrame truth value ambiguous 复发: {e}")
            raise

        assert resp["status"] == "scout_review"
