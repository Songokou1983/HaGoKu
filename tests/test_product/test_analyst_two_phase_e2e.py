"""C-2: 端到端冒烟 — Analyst 纯通道模式（Phase D 扁平化）

用 mock LLM 模拟完整对话剧本，验证 _handle_analyst_reply 纯通道行为：
不再有首波/二段/route_to 跳转逻辑，所有调用统一 delegate 到 _handle_reply。
"""
from unittest.mock import MagicMock, patch
import pandas as pd
import pytest

from hagoku.config import HaGoKuConfig
from hagoku.manager.orchestrator import Orchestrator
from hagoku.observability.events import EventType


class TestAnalystTwoPhaseE2E:
    """纯通道剧本：_handle_analyst_reply → _handle_reply → run_step → scout_review"""

    @pytest.fixture
    def orch(self):
        orch = Orchestrator(HaGoKuConfig())
        orch._df_clean = pd.DataFrame({
            "channel": ["A", "B", "A", "B"],
            "roi": [0.5, 0.3, 0.6, 0.4],
            "cost": [100, 200, 150, 180],
        })
        orch._df_raw = orch._df_clean
        orch._stage = "analyst"
        orch._context = {
            "query": "哪个渠道ROI最高",
            "column_semantics": [
                {"column_name": "channel", "display_name": "渠道", "suggested_role": "feature", "used_in_analysis": True},
                {"column_name": "roi", "display_name": "ROI", "suggested_role": "target", "used_in_analysis": True},
                {"column_name": "cost", "display_name": "成本", "suggested_role": "feature", "used_in_analysis": True},
            ],
            "column_descriptions": {},
            "column_display_names": {},
        }
        return orch

    @staticmethod
    def _make_step_result(text="", submit_analysis=False, findings=None, route_to=None):
        """构造 run_step 返回值。"""
        return {
            "messages": [{"role": "assistant", "content": text}],
            "text": text,
            "submit_findings": submit_analysis,
            "findings": findings,
            "route_to": route_to,
        }

    def test_full_two_phase_e2e(self, orch):
        """纯通道剧本：多次调用 _handle_analyst_reply → 每次调 run_step → scout_review"""
        from hagoku.agents.agent import DataAnalystAgent
        orch._agent = DataAnalystAgent.__new__(DataAnalystAgent)
        orch._agent.llm_config = orch.config.llm
        orch._agent.event_bus = orch.event_bus
        orch._agent.prompt = "test"

        from hagoku.context.project_context import ProjectContext
        pc = ProjectContext(run_id="flat_pipe", analysis_goal="测试ROI")
        orch._context = {"_project_context": pc, "query": "测试ROI", "column_semantics": []}

        # ── 第 1 步：用户输入 → run_step 返回文本 ──
        orch._agent.run_step = MagicMock(return_value=self._make_step_result(
            text="首波完成",
        ))

        emits = []
        with patch.object(orch.event_bus, "emit", wraps=lambda et, ag, data=None: emits.append((et, ag, data))):
            result = orch._handle_analyst_reply("确认", orch._context)

        # 断言：纯通道返回 scout_review
        assert result["status"] == "scout_review"

        # 断言：USER_INPUT_REQUESTED emit 已发送（现在通过 ack 的 need_input 返回，
        # 但 _handle_analyst_reply 仍触发 _handle_reply 的空文本分支的 event emit）
        user_events = [e for e in emits if e[0] == EventType.USER_INPUT_REQUESTED]
        # 主路径不 emit，改为检查返回值
        if not user_events:
            assert result.get("need_input") is True, "respond 应返回 need_input"

        # P0-2 修复后：add_user_feedback 由 respond() 外层统一写入
        user_entries = [e for e in pc.entries if e.type == "user_feedback" and e.stage == "analyst"]
        assert len(user_entries) == 0, f"handler 不应写入 user_feedback（由 respond 统一），实际: {user_entries}"

        # ── 第 2 步：用户继续对话 ──
        orch._agent.run_step = MagicMock(return_value=self._make_step_result(
            text="已执行 t 检验，p=0.03",
        ))
        result2 = orch._handle_analyst_reply("换 t 检验试试", orch._context)
        assert not isinstance(result2, tuple), "无 route_to 不应切换"
        assert result2["status"] == "scout_review"
        assert "p=0.03" in result2.get("message", "")

        # ── 第 3 步：带 route_to 的返回（handler 忽略 route_to，只返回 dict） ──
        orch._agent.run_step = MagicMock(return_value=self._make_step_result(
            text="好的，回到字段理解",
            route_to={"stage": "scout", "reason": "方向不对"},
        ))
        result3 = orch._handle_analyst_reply("方向不对，回去重看字段", orch._context)
        assert isinstance(result3, dict)
        assert result3["status"] == "scout_review"

        # ── 第 4 步：空输入 → 不调 run_step ──
        result4 = orch._handle_analyst_reply("", orch._context)
        assert result4["status"] == "scout_review"
        assert result4["message"] == ""

        # ── 第 5 步：route_to(reporter) 在纯通道中被忽略 ──
        orch._agent.run_step = MagicMock(return_value=self._make_step_result(
            text="好的，切换到报告",
            route_to={"stage": "reporter", "reason": "用户要求"},
        ))
        result5 = orch._handle_analyst_reply("够了，去写报告", orch._context)
        assert isinstance(result5, dict)
        assert result5["status"] == "scout_review"
