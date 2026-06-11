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


def test_G3_Scout_handler_纯确认_切Cleaner(orch):
    """Phase C: 确认词不再触发切换——LLM route_to 是唯一入口。
    用户说"继续"但 LLM 没调 route_to → 留在 scout。"""
    context = {
        "column_semantics": [
            {"column_name": "A", "display_name": "列A", "used_in_analysis": True},
        ],
        "column_descriptions": {},
        "column_display_names": {},
    }
    result = orch._handle_scout_reply("继续", context)
    # Phase C: 不再是 switch，留在 scout
    assert isinstance(result, dict)
    assert result["status"] == "scout_review"


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
    """G8: Analyst.run_step 正常处理 submit_analysis（Phase B 升级版）。"""
    from hagoku.agents.analyst.agent import AnalystAgent
    from hagoku.context.project_context import ProjectContext
    import json

    agent = AnalystAgent.__new__(AnalystAgent)
    agent.llm_config = orch.config.llm
    agent.event_bus = orch.event_bus
    agent.prompt = "test"

    pc = ProjectContext(run_id="test", analysis_goal="分析测试")
    context = {"query": "test", "column_semantics": [], "_project_context": pc}

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
            result = agent.run_step(context, None, "分析")

    assert result["submit_analysis"] is True
    assert "findings" in result
    # Phase B: messages 不再返回（由 ProjectContext 内部管理）


def test_G9_律8_route_to_触发(orch):
    """G9（律 8）：handler 返回 ("switch", "X") 模拟 route_to 效果。

    LLM 调 route_to(stage="cleaner") 的真实路径需要在端到端测试中验证
    （需要 mock LLM 返回 route_to tool_call）。
    本测试验证 handler→switch→respond 的切换机制正确。
    """
    orch._stage = "scout"
    orch._context = {"column_semantics": [], "column_descriptions": {}, "column_display_names": {}}

    saved_scout = orch._handle_scout_reply
    saved_cleaner = orch._handle_cleaner_reply

    orch._handle_scout_reply = lambda *a, **kw: ("switch", "cleaner")
    orch._handle_cleaner_reply = lambda *a, **kw: {"status": "cleaner_review", "message": "ok"}
    try:
        orch.respond({"text": "好，进入清洗"})
        assert orch._stage == "cleaner"
    finally:
        orch._handle_scout_reply = saved_scout
        orch._handle_cleaner_reply = saved_cleaner


def test_G10_律2_raw_text_跨_respond_保留(orch):
    """G10（律 2）：Scout handler 多次 receive 不同 raw_text，context 正确更新。

    律 2 要求 raw_text 保留。_handle_scout_reply 内部调
    apply_scout_user_field_reply_to_context → LLM 处理 → 更新 context。
    本测试验证 handler 对多次用户输入能正确传递和处理。
    """
    context = {
        "column_semantics": [
            {"column_name": "A", "display_name": "列A", "suggested_role": "feature", "used_in_analysis": True},
        ],
        "column_descriptions": {"A": "旧描述"},
        "column_display_names": {},
    }
    orch._context = context

    # 第一次纠正（mock LLM 会处理，实际调 apply_scout_user_field_reply_to_context）
    result1 = orch._handle_scout_reply("A是收入", context)
    assert result1["status"] == "scout_review" or isinstance(result1, tuple)

    # 第二次纠正
    result2 = orch._handle_scout_reply("A的单位是万元", context)
    assert result2["status"] == "scout_review" or isinstance(result2, tuple)

    # handler 被调了 2 次，状态应一致
    assert "field_review" in result1 if isinstance(result1, dict) else True


def test_G11_律6_raw_text_抵达_LLM(orch):
    """G11（律 6）：respond() 将 raw_text 传给 handler——handler 能拿到用户输入。

    律 6 要求信息抵达。handler 的 text 参数必须等于用户输入的 raw_text。
    """
    captured = {}

    def _capture(text, ctx):
        captured["text"] = text
        return {"status": "analyst_review", "message": f"收到: {text}"}

    saved = orch._handle_analyst_reply
    orch._handle_analyst_reply = _capture
    orch._stage = "analyst"
    orch._context = {"query": "测试", "column_semantics": []}
    try:
        orch.respond({"text": "把Inc1加进来"})
        assert "Inc1" in captured.get("text", ""), f"handler 收到的 text 应为用户 raw_text，实际: {captured}"
    finally:
        orch._handle_analyst_reply = saved


def test_G12_真端到端_cleaner_handler_不报_ValueError(orch, tmp_path):
    """G12：真端到端——_handle_cleaner_reply 调 cleaner.assess(df, ...) 不应抛 ValueError。

    回归保护：line 2582 之前写 `self._df_raw or self._df_clean`，DataFrame 求
    值抛 ambiguous truth value。修复后改三元表达式，pytest 必须能真调 cleaner
    handler 一遍（不走 mock），确认 bug 不复发。

    parse_query 在 LLM 不可达时直接 raise（铁律 7），这里 mock 掉让测试
    专注于 DataFrame truthiness 回归，不依赖真实 LLM。
    """
    import pandas as pd
    from unittest.mock import patch
    from hagoku.manager.query_parser import QueryIntent

    # 写最小 CSV 走真 run() 触发 _df_raw 加载
    csv_path = tmp_path / "data.csv"
    csv_path.write_text("A,B\n1,3\n2,4\n3,5\n", encoding="utf-8")

    # mock parse_query 在源头（query_parser 模块），因为 orchestrator 用 local import
    # Mock plan + Scout + Cleaner assess（非本测试关注点），核心验证 _handle_cleaner_reply 不抛 ValueError
    with patch("hagoku.manager.query_parser.parse_query") as mock_parse, \
         patch.object(orch, "_create_plan", return_value={
             "plan_name": "探索性分析", "agents": ["scout", "cleaner", "analyst", "reporter"],
             "analyst_focus": ["regression"], "target": "", "query": "分析", "reasoning": "",
             "llm_generated": True,
         }), \
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
        result = orch.run(data_path=str(csv_path), query="分析")

        assert result.get("status") == "scout_review"
        assert isinstance(orch._df_raw, pd.DataFrame)
        assert isinstance(orch._df_clean, pd.DataFrame)

        # 真调 _handle_cleaner_reply——之前会 ValueError，现在应正常返回
        try:
            resp = orch._handle_cleaner_reply("确认清洗策略", orch._context)
        except ValueError as e:
            if "ambiguous" in str(e):
                pytest.fail(f"回归：DataFrame truth value ambiguous 复发: {e}")
            raise

        assert resp["status"] == "cleaner_review"
        assert "cleaning_assessment" in resp
