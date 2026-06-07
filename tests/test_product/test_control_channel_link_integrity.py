"""C-1: 律 4 / 律 8 升级 — 链路验证而非仅 schema

验证每个 Agent 的控制类工具调用 → 业务效果链路完整。
覆盖：状态变更工具（ctx 真改变）+ 流程控制工具（_handle_X_reply 返回正确切换信号）。
盲点用 xfail(strict=True) 标记，禁止 skip。
"""
from unittest.mock import MagicMock, patch
import json as _json
import pandas as pd
import pytest

from hagoku.config import HaGoKuConfig
from hagoku.manager.orchestrator import Orchestrator


# ═══════════════════════════════════════════════════════════════════
# Scout 链路矩阵
# ═══════════════════════════════════════════════════════════════════

class TestScoutControlChannelLinks:
    """Scout 控制通道链路验证"""

    @pytest.fixture
    def orch(self):
        return Orchestrator(HaGoKuConfig())

    def _scout_context(self):
        return {
            "column_semantics": [
                {"column_name": "Inc1", "display_name": "收入", "suggested_role": "target", "used_in_analysis": True},
                {"column_name": "Inc2", "display_name": "费用", "suggested_role": "feature", "used_in_analysis": True},
            ],
            "column_descriptions": {"Inc1": "店铺收入", "Inc2": "店铺费用"},
            "column_display_names": {"Inc1": "收入", "Inc2": "费用"},
            "query": "分析收入趋势",
        }

    def test_route_to_cleaner_triggers_switch(self, orch):
        """LLM route_to(stage="cleaner") → _handle_scout_reply 返回 ("switch", "cleaner")"""
        context = self._scout_context()
        mock_resp = self._make_route_to_response("cleaner", "done")
        orch._llm_quick_raw = self._make_client(mock_resp)
        result = orch._handle_scout_reply("可以进入清洗了", context)
        assert isinstance(result, tuple)
        assert result[0] == "switch"
        assert result[1] == "cleaner"

    def test_route_to_reporter_triggers_switch(self, orch):
        """LLM route_to(stage="reporter") → switch to reporter"""
        context = self._scout_context()
        mock_resp = self._make_route_to_response("reporter", "直接报告")
        orch._llm_quick_raw = self._make_client(mock_resp)
        result = orch._handle_scout_reply("直接去报告", context)
        assert isinstance(result, tuple)
        assert result[0] == "switch"
        assert result[1] == "reporter"

    def test_route_to_scout_stays(self, orch):
        """LLM route_to(stage="scout") → 留在 scout"""
        context = self._scout_context()
        mock_resp = self._make_route_to_response("scout", "stay")
        orch._llm_quick_raw = self._make_client(mock_resp)
        result = orch._handle_scout_reply("继续字段理解", context)
        assert not isinstance(result, tuple), f"stage=scout 不应切换"

    @staticmethod
    def _make_route_to_response(stage, reason):
        choice = MagicMock()
        msg = MagicMock()
        tc = MagicMock()
        tc.function.name = "route_to"
        tc.function.arguments = _json.dumps({"stage": stage, "reason": reason})
        msg.tool_calls = [tc]
        msg.content = f"route to {stage}"
        choice.message = msg
        resp = MagicMock()
        resp.choices = [choice]
        return resp

    @staticmethod
    def _make_client(mock_resp):
        c = MagicMock()
        c.chat.completions.create.return_value = mock_resp
        return c


# ═══════════════════════════════════════════════════════════════════
# Analyst 链路矩阵
# ═══════════════════════════════════════════════════════════════════

class TestAnalystControlChannelLinks:
    """Analyst 控制通道链路验证"""

    @pytest.fixture
    def orch(self):
        orch = Orchestrator(HaGoKuConfig())
        orch._df_clean = pd.DataFrame({"A": [1, 2], "B": [3, 4]})
        from hagoku.agents.analyst import AnalystAgent
        orch._analyst_agent = AnalystAgent.__new__(AnalystAgent)
        orch._analyst_agent.llm_config = orch.config.llm
        orch._analyst_agent.event_bus = orch.event_bus
        orch._analyst_agent.prompt = "test"
        orch._analyst_messages = [{"role": "user", "content": "test"}]
        orch._analyst_first_pass_done = True
        return orch

    def test_route_to_reporter_triggers_switch(self, orch):
        """Analyst route_to(reporter) → switch"""
        step_result = {
            "messages": orch._analyst_messages,
            "text": "ok",
            "submit_analysis": False,
            "findings": None,
            "route_to": {"stage": "reporter", "reason": "done"},
        }
        orch._analyst_agent.run_step = MagicMock(return_value=step_result)
        result = orch._handle_analyst_reply("够了", {"query": "test"})
        assert isinstance(result, tuple)
        assert result[0] == "switch"
        assert result[1] == "reporter"

    def test_submit_analysis_triggers_switch(self, orch):
        """Analyst submit_analysis → switch to reporter"""
        step_result = {
            "messages": orch._analyst_messages,
            "text": "done",
            "submit_analysis": True,
            "findings": {"findings": [], "method_used": [], "summary": "ok"},
            "route_to": None,
        }
        orch._analyst_agent.run_step = MagicMock(return_value=step_result)
        result = orch._handle_analyst_reply("提交", {"query": "test"})
        assert isinstance(result, tuple)
        assert result[0] == "switch"
        assert result[1] == "reporter"

    def test_no_control_tool_stays(self, orch):
        """无控制工具调用 → 留在 analyst"""
        step_result = {
            "messages": orch._analyst_messages + [{"role": "assistant", "content": "ok"}],
            "text": "ok",
            "submit_analysis": False,
            "findings": None,
            "route_to": None,
        }
        orch._analyst_agent.run_step = MagicMock(return_value=step_result)
        result = orch._handle_analyst_reply("继续", {"query": "test"})
        assert not isinstance(result, tuple)
        assert result["status"] == "analyst_review"


# ═══════════════════════════════════════════════════════════════════
# Cleaner 盲点声明（B-2 Option B：schema-only）
# ═══════════════════════════════════════════════════════════════════

class TestCleanerControlChannelBlindSpot:
    """Cleaner 控制通道盲点 — route_to schema-only"""

    @pytest.mark.xfail(
        strict=True,
        reason="Cleaner 无 LLM 工具调用入口（仅一次评估），route_to 为 schema-only"
    )
    def test_cleaner_route_to_link_present(self):
        """验证 Cleaner 的 route_to 链路已触达——若此测试 PASS 说明盲点已修复。

        当前预期 FAIL：Cleaner 阶段 _handle_cleaner_reply 不消费 route_to。
        当 Cleaner 有了 LLM 交互循环并消费 route_to 时，此测试将 PASS（XPASS），
        提醒开发者移除 xfail 并补充链路测试。
        """
        from hagoku.manager.llm_dispatch.reply_handlers import _handle_cleaner_reply
        import inspect
        src = inspect.getsource(_handle_cleaner_reply)
        assert "route_to" in src, (
            "Cleaner 当前不消费 route_to——盲点存在。\n"
            "当 Cleaner 有 LLM 交互循环后此测试将 PASS，届时移除 xfail。"
        )

    @pytest.mark.xfail(
        strict=True,
        reason="Cleaner 无 LLM 工具调用入口，submit_assessment 是唯一退出路径"
    )
    def test_cleaner_plan_via_llm_handles_route_to(self):
        """验证 Cleaner._plan_via_llm 处理 route_to——若 PASS 说明盲点缩小。

        当前预期 FAIL：_plan_via_llm 不处理 route_to（仅处理 submit_assessment）。
        """
        from hagoku.agents.cleaner.agent import CleanerAgent
        import inspect
        src = inspect.getsource(CleanerAgent._plan_via_llm)
        assert "route_to" in src, (
            "Cleaner._plan_via_llm 当前不处理 route_to——盲点存在。\n"
            "当 _plan_via_llm 处理 route_to 后此测试将 PASS，届时移除 xfail。"
        )


# ═══════════════════════════════════════════════════════════════════
# Reporter 盲点声明（B-3 Option B：schema-only）
# ═══════════════════════════════════════════════════════════════════

class TestReporterControlChannelBlindSpot:
    """Reporter 控制通道盲点 — route_to schema-only"""

    @pytest.mark.xfail(
        strict=True,
        reason="Reporter 无用户交互循环（_handle_reporter_reply 直接返回 done），route_to schema-only"
    )
    def test_reporter_route_to_link_present(self):
        """验证 Reporter 的 route_to 链路已触达——若 PASS 说明盲点已修复。

        当前预期 FAIL：Reporter 阶段 _handle_reporter_reply 不消费 route_to。
        """
        from hagoku.manager.llm_dispatch.reply_handlers import _handle_reporter_reply
        import inspect
        src = inspect.getsource(_handle_reporter_reply)
        assert "route_to" in src, (
            "Reporter 当前不消费 route_to——盲点存在。\n"
            "当 Reporter 有用户交互后此测试将 PASS，届时移除 xfail。"
        )
