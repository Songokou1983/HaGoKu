# tests/test_context/test_project_context.py
"""ProjectContext 单元测试 — 不依赖 EventBus 和真实 LLM。"""
from __future__ import annotations

import pytest

from hagoku.context.project_context import ProjectContext


@pytest.fixture
def ctx():
    return ProjectContext(run_id="r1", analysis_goal="分析ROI")


class TestProjectContext:
    """ProjectContext 数据模型测试"""

    def test_add_entry_appends(self, ctx):
        ctx.add_user_feedback(stage="scout", revision=1, raw_text="Code是店铺编号")
        assert len(ctx.entries) == 1
        assert ctx.entries[0].raw_user_text == "Code是店铺编号"

    def test_add_user_feedback_preserves_raw_text(self, ctx):
        """律 2：用户原话必须在 raw_user_text 中保留。"""
        ctx.add_user_feedback(stage="scout", revision=1, raw_text="Period的中文名是周次")
        assert ctx.entries[0].raw_user_text == "Period的中文名是周次"
        assert ctx.entries[0].type == "user_feedback"

    def test_entries_are_append_only(self, ctx):
        """entries 只增不改，历史不可变。"""
        ctx.add_user_feedback(stage="scout", revision=1, raw_text="第一轮")
        ctx.add_user_feedback(stage="scout", revision=2, raw_text="第二轮")
        assert len(ctx.entries) == 2
        assert ctx.entries[0].raw_user_text == "第一轮"
        assert ctx.entries[1].raw_user_text == "第二轮"

    def test_build_prompt_system_prefix_has_goal(self, ctx):
        """律 1：analysis_goal 永远在 system_prefix 首行。"""
        result = ctx.build_prompt("scout", {"column_semantics": []})
        assert "分析ROI" in result["system_prefix"]

    def test_build_prompt_system_prefix_has_field_state(self, ctx):
        """system_prefix 包含从 column_semantics 派生的字段状态。"""
        context = {
            "column_semantics": [
                {"column_name": "Code", "display_name": "店铺编号", "suggested_role": "feature", "used_in_analysis": True, "needs_user_input": False},
                {"column_name": "Period", "display_name": "周次", "suggested_role": "identifier", "used_in_analysis": False, "needs_user_input": True},
            ],
            "target": "Revenue",
            "features": ["Code"],
        }
        result = ctx.build_prompt("scout", context)
        assert "Code(店铺编号): 参与  role=feature" in result["system_prefix"]
        assert "Period(周次): 不参与  role=identifier" in result["system_prefix"]
        assert "待确认字段: Period" in result["system_prefix"]

    def test_build_prompt_history_context_includes_current_stage(self, ctx):
        """history_context 包含当前阶段的 user_feedback + agent_response。"""
        ctx.add_user_feedback(stage="scout", revision=1, raw_text="Code是店铺编号")
        ctx.add_agent_response(stage="scout", revision=1, content="已更新 Code→店铺编号")

        result = ctx.build_prompt("scout", {"column_semantics": []})
        assert "Code是店铺编号" in result["history_context"]
        assert "已更新 Code→店铺编号" in result["history_context"]

    def test_build_prompt_history_context_excludes_other_stages_dialog(self, ctx):
        """上游阶段的对话细节不出现在当前阶段的 history_context 中（仅保留 snapshot 摘要）。"""
        ctx.add_user_feedback(stage="scout", revision=1, raw_text="Code是店铺编号")
        ctx.add_agent_response(stage="scout", revision=1, content="已更新", snapshot={"target": "Revenue", "features": ["Code"], "pending": []})

        result = ctx.build_prompt("cleaner", {"column_semantics": []})
        # upstream 的对话细节不应出现
        assert "Code是店铺编号" not in result["history_context"]
        # 但 snapshot 摘要应出现
        assert "scout" in result["history_context"]

    def test_build_prompt_with_command_context(self, ctx):
        """_pending_command_text 应出现在 system_prefix 中。"""
        context = {
            "column_semantics": [],
            "_pending_command_text": "/goal 改为分析利润趋势",
        }
        result = ctx.build_prompt("scout", context)
        assert "分析利润趋势" in result["system_prefix"]

    def test_snapshot_derived_from_column_semantics(self, ctx):
        """律 5：snapshot 从 column_semantics 实时派生，不平行存储。"""
        context = {
            "column_semantics": [
                {"column_name": "Code", "display_name": "店铺编号", "used_in_analysis": True},
                {"column_name": "X", "display_name": "", "used_in_analysis": None},
            ],
        }
        snapshot = ctx._derive_snapshot(context)
        assert len(snapshot["fields"]) == 2
        assert snapshot["fields"][0]["participating"] is True
        assert snapshot["fields"][1]["participating"] is None

    def test_empty_context_does_not_crash(self, ctx):
        """空 context → build_prompt 正常返回，不抛异常。"""
        result = ctx.build_prompt("scout", {})
        assert "system_prefix" in result
        assert "history_context" in result
        assert "分析ROI" in result["system_prefix"]

    # ── _derive_snapshot 边界测试 ──

    @pytest.mark.parametrize("used_in_analysis,expected_participating", [
        (True, True), (False, False), (None, None),
    ])
    def test_derive_snapshot_participating(self, ctx, used_in_analysis, expected_participating):
        context = {
            "column_semantics": [
                {"column_name": "Code", "used_in_analysis": used_in_analysis},
            ],
        }
        snapshot = ctx._derive_snapshot(context)
        assert snapshot["fields"][0]["participating"] is expected_participating

    def test_derive_snapshot_empty_column_name_skipped(self, ctx):
        context = {
            "column_semantics": [
                {"column_name": "", "display_name": "空", "used_in_analysis": True},
            ],
        }
        snapshot = ctx._derive_snapshot(context)
        assert len(snapshot["fields"]) == 0

    def test_derive_snapshot_missing_keys_defaults(self, ctx):
        context = {
            "column_semantics": [
                {},
            ],
        }
        snapshot = ctx._derive_snapshot(context)
        assert len(snapshot["fields"]) == 0

    # ── add_agent_response / add_stage_transition 独立测试 ──

    def test_add_agent_response_creates_entry(self, ctx):
        ctx.add_agent_response(stage="scout", revision=1, content="已更新")
        assert len(ctx.entries) == 1
        assert ctx.entries[0].type == "agent_response"
        assert ctx.entries[0].content == "已更新"

    def test_add_agent_response_with_snapshot(self, ctx):
        snapshot = {"target": "Revenue", "features": ["Code"]}
        ctx.add_agent_response(stage="scout", revision=1, content="完成", snapshot=snapshot)
        assert ctx.entries[0].snapshot == snapshot

    def test_add_stage_transition_creates_entry(self, ctx):
        ctx.add_stage_transition(stage="cleaner")
        assert len(ctx.entries) == 1
        assert ctx.entries[0].type == "stage_transition"
        assert ctx.entries[0].stage == "cleaner"
        assert ctx.entries[0].revision == 0

    def test_add_stage_transition_custom_content(self, ctx):
        ctx.add_stage_transition(stage="scout", content="开始探索")
        assert ctx.entries[0].content == "开始探索"

    # ── build_prompt 空 entries 场景 ──

    def test_build_prompt_with_no_entries_history_is_empty(self, ctx):
        result = ctx.build_prompt("scout", {"column_semantics": []})
        assert result["history_context"] == ""


class TestProjectContextEventBus:
    """ProjectContext + EventBus 集成测试"""

    def test_agent_started_adds_stage_transition(self):
        from hagoku.observability.event_bus import EventBus
        from hagoku.observability.events import EventType

        ctx = ProjectContext(run_id="r1", analysis_goal="分析ROI")
        bus = EventBus()
        ctx.subscribe(bus, context_ref={})

        bus.emit(EventType.AGENT_STARTED, "scout", {"goal": "数据侦察"})
        assert len(ctx.entries) == 1
        assert ctx.entries[0].type == "stage_transition"
        assert ctx.entries[0].stage == "scout"

    def test_agent_completed_adds_response_with_snapshot(self):
        from hagoku.observability.event_bus import EventBus
        from hagoku.observability.events import EventType

        ctx = ProjectContext(run_id="r1", analysis_goal="分析ROI")
        bus = EventBus()
        test_ctx = {
            "column_semantics": [
                {"column_name": "Code", "display_name": "店铺", "used_in_analysis": True},
            ],
            "target": "Revenue",
            "features": ["Code"],
            "interaction_revision": 2,
        }
        ctx.subscribe(bus, context_ref=test_ctx)

        bus.emit(EventType.AGENT_COMPLETED, "scout", {"result_summary": "完成"})
        assert len(ctx.entries) == 1
        assert ctx.entries[0].type == "agent_response"
        assert ctx.entries[0].snapshot is not None
        assert ctx.entries[0].snapshot["target"] == "Revenue"

    def test_user_input_received_adds_feedback(self):
        from hagoku.observability.event_bus import EventBus
        from hagoku.observability.events import EventType

        ctx = ProjectContext(run_id="r1", analysis_goal="分析ROI")
        bus = EventBus()
        ctx.subscribe(bus, context_ref={"interaction_revision": 1})

        bus.emit(EventType.USER_INPUT_RECEIVED, "scout", {"reply": "Code是店铺编号"})
        assert len(ctx.entries) == 1
        assert ctx.entries[0].type == "user_feedback"
        assert ctx.entries[0].raw_user_text == "Code是店铺编号"

    def test_multiple_events_accumulate(self):
        """EventBus 多次事件 → entries 正常累积。"""
        from hagoku.observability.event_bus import EventBus
        from hagoku.observability.events import EventType

        ctx = ProjectContext(run_id="r1", analysis_goal="分析ROI")
        bus = EventBus()
        ctx.subscribe(bus, context_ref={})

        bus.emit(EventType.AGENT_STARTED, "scout", {})
        bus.emit(EventType.USER_INPUT_RECEIVED, "scout", {"reply": "反馈1"})
        bus.emit(EventType.USER_INPUT_RECEIVED, "scout", {"reply": "反馈2"})

        assert len(ctx.entries) == 3
        assert ctx.entries[1].raw_user_text == "反馈1"
        assert ctx.entries[2].raw_user_text == "反馈2"
