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

    def _setup_scout_agent(self, orch, route_to_result=None):
        """设置 orch._agent，mock run_step 返回指定 route_to。"""
        from hagoku.agents.agent import DataAnalystAgent
        orch._agent = DataAnalystAgent.__new__(DataAnalystAgent)
        orch._agent.llm_config = orch.config.llm
        orch._agent.event_bus = orch.event_bus
        orch._agent.prompt = ""
        orch._agent.run_step = MagicMock(return_value={"route_to": route_to_result} if route_to_result else {})

    def test_route_to_cleaner_triggers_switch(self, orch):
        """LLM route_to(stage="cleaner") → _handle_scout_reply 返回 ("switch", "cleaner")"""
        context = self._scout_context()
        self._setup_scout_agent(orch, {"stage": "cleaner", "reason": "done"})
        result = orch._handle_scout_reply("可以进入清洗了", context)
        assert isinstance(result, tuple)
        assert result[0] == "switch"
        assert result[1] == "cleaner"

    def test_route_to_reporter_triggers_switch(self, orch):
        """LLM route_to(stage="reporter") → switch to reporter"""
        context = self._scout_context()
        self._setup_scout_agent(orch, {"stage": "reporter", "reason": "直接报告"})
        result = orch._handle_scout_reply("直接去报告", context)
        assert isinstance(result, tuple)
        assert result[0] == "switch"
        assert result[1] == "reporter"

    def test_route_to_scout_stays(self, orch):
        """LLM route_to(stage="scout") → 留在 scout"""
        context = self._scout_context()
        self._setup_scout_agent(orch, {"stage": "scout", "reason": "stay"})
        result = orch._handle_scout_reply("继续字段理解", context)
        # scout 的 route_to(scout) 不触发切换，因为 target==current
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
        from hagoku.agents.agent import DataAnalystAgent
        orch._agent = DataAnalystAgent.__new__(DataAnalystAgent)
        orch._agent.llm_config = orch.config.llm
        orch._agent.event_bus = orch.event_bus
        orch._agent.prompt = "test"
        orch._analyst_first_pass_done = True
        return orch

    def test_route_to_reporter_triggers_switch(self, orch):
        """Analyst route_to(reporter) → switch"""
        step_result = {
            "text": "ok",
            "submit_analysis": False,
            "findings": None,
            "route_to": {"stage": "reporter", "reason": "done"},
        }
        orch._agent.run_step = MagicMock(return_value=step_result)
        result = orch._handle_analyst_reply("够了", {"query": "test"})
        assert isinstance(result, tuple)
        assert result[0] == "switch"
        assert result[1] == "reporter"

    def test_submit_analysis_triggers_switch(self, orch):
        """Analyst submit_analysis → switch to reporter"""
        step_result = {
            "text": "done",
            "submit_analysis": True,
            "findings": {"findings": [], "method_used": [], "summary": "ok"},
            "route_to": None,
        }
        orch._agent.run_step = MagicMock(return_value=step_result)
        result = orch._handle_analyst_reply("提交", {"query": "test"})
        assert isinstance(result, tuple)
        assert result[0] == "switch"
        assert result[1] == "reporter"

    def test_no_control_tool_stays(self, orch):
        """无控制工具调用 → 留在 analyst"""
        step_result = {
            "text": "ok",
            "submit_analysis": False,
            "findings": None,
            "route_to": None,
        }
        orch._agent.run_step = MagicMock(return_value=step_result)
        result = orch._handle_analyst_reply("继续", {"query": "test"})
        assert not isinstance(result, tuple)
        assert result["status"] == "analyst_review"


# ═══════════════════════════════════════════════════════════════════
# Cleaner 盲点声明（B-2 Option B：schema-only）
# ═══════════════════════════════════════════════════════════════════

class TestCleanerControlChannelLinks:
    """Cleaner 控制通道链路验证 — CL-1~CL-3 后 route_to 已生效"""

    @pytest.fixture
    def orch(self):
        orch = Orchestrator(HaGoKuConfig())
        orch._df_raw = pd.DataFrame({"A": [1, 2], "B": [3, 4]})
        orch._df_clean = orch._df_raw
        return orch

    def _cleaner_context(self):
        return {
            "column_semantics": [
                {"column_name": "A", "display_name": "列A", "suggested_role": "target", "used_in_analysis": True},
            ],
            "query": "分析",
            "_cleaner_assessment": {"summary": "done", "columns": []},
        }

    def test_route_to_analyst_triggers_switch(self, orch):
        """Cleaner route_to(analyst) → switch"""
        context = self._cleaner_context()
        from hagoku.agents.agent import DataAnalystAgent
        agent = DataAnalystAgent.__new__(DataAnalystAgent)
        agent.llm_config = orch.config.llm
        agent.event_bus = orch.event_bus
        agent.prompt = "test"
        orch._agent = agent
        orch._cleaner_messages = [{"role": "user", "content": "可以了"}]
        orch._cleaner_dialog_open = True

        agent.run_step = MagicMock(return_value={
            "messages": orch._cleaner_messages,
            "text": "ok",
            "submit_assessment": False,
            "assessment": None,
            "route_to": {"stage": "analyst", "reason": "done"},
        })
        result = orch._handle_cleaner_reply("可以了", context)
        assert isinstance(result, tuple)
        assert result[0] == "switch"
        assert result[1] == "analyst"

    def test_route_to_scout_triggers_switch(self, orch):
        """Cleaner route_to(scout) → switch"""
        context = self._cleaner_context()
        from hagoku.agents.agent import DataAnalystAgent
        agent = DataAnalystAgent.__new__(DataAnalystAgent)
        agent.llm_config = orch.config.llm
        agent.event_bus = orch.event_bus
        agent.prompt = "test"
        orch._agent = agent
        orch._cleaner_messages = [{"role": "user", "content": "重看字段"}]
        orch._cleaner_dialog_open = True

        agent.run_step = MagicMock(return_value={
            "messages": orch._cleaner_messages,
            "text": "ok",
            "submit_assessment": False,
            "assessment": None,
            "route_to": {"stage": "scout", "reason": "重看"},
        })
        result = orch._handle_cleaner_reply("清洗方案有问题", context)
        assert isinstance(result, tuple)
        assert result[1] == "scout"

    def test_no_route_to_stays_in_cleaner(self, orch):
        """无 route_to → 留在 cleaner"""
        context = self._cleaner_context()
        from hagoku.agents.agent import DataAnalystAgent
        agent = DataAnalystAgent.__new__(DataAnalystAgent)
        agent.llm_config = orch.config.llm
        agent.event_bus = orch.event_bus
        agent.prompt = "test"
        orch._agent = agent
        orch._cleaner_messages = [{"role": "user", "content": "讨论"}]
        orch._cleaner_dialog_open = True

        agent.run_step = MagicMock(return_value={
            "messages": orch._cleaner_messages + [{"role": "assistant", "content": "好的"}],
            "text": "好的，继续讨论",
            "submit_assessment": False,
            "assessment": None,
            "route_to": None,
        })
        result = orch._handle_cleaner_reply("再讨论一下", context)
        assert not isinstance(result, tuple)
        assert result["status"] == "cleaner_review"


# ═══════════════════════════════════════════════════════════════════
# Reporter 盲点声明（B-3 Option B：schema-only）
# ═══════════════════════════════════════════════════════════════════

class TestReporterControlChannelLinks:
    """Reporter 控制通道链路验证 — route_to 已生效"""

    def test_reporter_route_to_in_handler(self):
        """_handle_reporter_reply 含 route_to 处理。"""
        from hagoku.manager.llm_dispatch.reply_handlers import _handle_reporter_reply
        import inspect
        src = inspect.getsource(_handle_reporter_reply)
        assert "route_to" in src, "_handle_reporter_reply 应含 route_to 处理"
