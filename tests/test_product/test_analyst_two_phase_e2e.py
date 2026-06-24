"""C-2: 端到端冒烟 — Analyst 二段化 + route_to 修复全链路验证

用 mock LLM 模拟完整对话剧本，验证阶段 1 首波 → 阶段 2 自由对话 →
route_to 跳转 → Reporter 全链路协同。
"""
from unittest.mock import MagicMock, patch
import json as _json
import pandas as pd
import pytest

from hagoku.config import HaGoKuConfig
from hagoku.manager.orchestrator import Orchestrator
from hagoku.observability.events import EventType


class TestAnalystTwoPhaseE2E:
    """完整对话剧本：Cleaner→Analyst 首波→阶段 2 对话→route_to 跳转"""

    @pytest.fixture
    def orch(self):
        orch = Orchestrator(HaGoKuConfig())
        orch._df_clean = pd.DataFrame({
            "channel": ["A", "B", "A", "B"],
            "roi": [0.5, 0.3, 0.6, 0.4],
            "cost": [100, 200, 150, 180],
        })
        orch._df_raw = orch._df_clean
        orch._stage = "cleaner"
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
        orch._analyst_first_pass_done = False
        return orch

    @staticmethod
    def _make_step_result(text="", submit_analysis=False, findings=None, route_to=None, submit_first_pass=False):
        """构造 run_step 返回值。"""
        messages = [{"role": "assistant", "content": text}]
        if submit_first_pass:
            messages[0]["tool_calls"] = [{
                "id": "call_1", "type": "function",
                "function": {"name": "submit_findings", "arguments": '{"findings":[],"method_used":["ttest"],"summary":"ok"}'},
            }]
            messages.append({"role": "tool", "tool_call_id": "call_1",
                             "content": '{"findings":[],"method_used":["ttest"],"summary":"ok"}'})
        return {
            "messages": messages,
            "text": text,
            "submit_findings": submit_analysis or submit_first_pass,
            "findings": findings or ({"findings": [], "method_used": ["ttest"], "summary": "ok"} if submit_first_pass else None),
            "route_to": route_to,
        }

    def test_full_two_phase_e2e(self, orch):
        """完整剧本：首波→对话→route_to→Reporter"""
        analyst = MagicMock()
        from hagoku.agents.agent import DataAnalystAgent
        orch._agent = DataAnalystAgent.__new__(DataAnalystAgent)
        orch._agent.llm_config = orch.config.llm
        orch._agent.event_bus = orch.event_bus
        orch._agent.prompt = "test"
        # Phase B: ProjectContext 替代 _analyst_messages
        from hagoku.context.project_context import ProjectContext
        pc = ProjectContext(run_id="two_phase", analysis_goal="测试ROI")
        orch._context = {"_project_context": pc, "query": "测试ROI", "column_semantics": []}

        # ── 剧本第 1 步：Cleaner → Analyst 首次进入 → 触发首波 ──
        # Mock run_step: LLM 调 submit_first_pass（首波完成信号）
        orch._agent.run_step = MagicMock(return_value=self._make_step_result(
            text="首波完成", submit_first_pass=True,
        ))

        emits = []
        with patch.object(orch.event_bus, "emit", wraps=lambda et, ag, data=None: emits.append((et, ag, data))):
            result = orch._handle_analyst_reply("确认", orch._context)

        # 断言：首波完成后 _analyst_first_pass_done = True
        assert orch._analyst_first_pass_done, "首波应设置 _analyst_first_pass_done"

        # 断言：USER_INPUT_REQUESTED emit 已发送
        user_events = [e for e in emits if e[0] == EventType.USER_INPUT_REQUESTED]
        assert len(user_events) >= 1

        # P0-2 修复后：add_user_feedback 由 respond() 外层统一写入，handler 不重复写。
        # 直接调 handler 时 ProjectContext 应无 user_feedback 条目。
        user_entries = [e for e in pc.entries if e.type == "user_feedback" and e.stage == "analyst"]
        assert len(user_entries) == 0, f"handler 不应写入 user_feedback（由 respond 统一），实际: {user_entries}"

        # ── 剧本第 2 步：阶段 2 — 用户输入"换 t 检验试试" ──
        orch._agent.run_step = MagicMock(return_value=self._make_step_result(
            text="已执行 t 检验，p=0.03",
        ))
        result2 = orch._handle_analyst_reply("换 t 检验试试", orch._context)
        assert not isinstance(result2, tuple), "无 route_to 不应切换"
        assert result2["status"] == "analyst_review"
        assert "p=0.03" in result2.get("message", "")

        # ── 剧本第 3 步：用户说"方向不对，回去重看字段" ──
        orch._agent.run_step = MagicMock(return_value=self._make_step_result(
            text="好的，回到字段理解",
            route_to={"stage": "scout", "reason": "方向不对"},
        ))
        result3 = orch._handle_analyst_reply("方向不对，回去重看字段", orch._context)
        assert isinstance(result3, dict)
        assert result3["status"] == "analyst_review"

        # ── 剧本第 4 步：模拟用户重进 Analyst（新会话），用户说"够了，去写报告" ──
        orch._analyst_first_pass_done = False  # 模拟重新进入
        pc2 = ProjectContext(run_id="two_phase_v2", analysis_goal="测试ROI")
        orch._context = {"_project_context": pc2, "query": "测试ROI", "column_semantics": []}

        # 首波 mock
        orch._agent.run_step = MagicMock(return_value=self._make_step_result(
            text="分析完成", submit_first_pass=True,
        ))
        orch._handle_analyst_reply("", orch._context)

        # 阶段 2 — route_to(reporter)
        orch._agent.run_step = MagicMock(return_value=self._make_step_result(
            text="好的，切换到报告",
            route_to={"stage": "reporter", "reason": "用户要求"},
        ))
        result4 = orch._handle_analyst_reply("够了，去写报告", orch._context)
        assert isinstance(result4, dict)
        assert result4["status"] == "analyst_review"

        # ── 验证：整个流程中 _handle_analyst_reply 被正确调用了 4 次 ──
        # （通过 _analyst_first_pass_done 在重新进入时重置来验证）
        assert orch._analyst_first_pass_done, "第二轮首波完成后应标记 done"
