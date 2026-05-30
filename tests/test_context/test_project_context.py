# tests/test_context/test_project_context.py
"""ProjectContext 单元测试 — 不依赖 EventBus 和真实 LLM。"""
from __future__ import annotations

import pytest

from hagoku.context.project_context import ContextEntry, ProjectContext


class TestProjectContext:
    """ProjectContext 数据模型测试"""

    def test_add_entry_appends(self):
        ctx = ProjectContext(run_id="r1", analysis_goal="分析ROI")
        ctx.add_entry(ContextEntry(
            type="user_feedback", stage="scout", revision=1,
            timestamp="2026-01-01T00:00:00", content="测试",
            raw_user_text="Code是店铺编号",
        ))
        assert len(ctx.entries) == 1
        assert ctx.entries[0].raw_user_text == "Code是店铺编号"

    def test_add_user_feedback_preserves_raw_text(self):
        """律 2：用户原话必须在 raw_user_text 中保留。"""
        ctx = ProjectContext(run_id="r1", analysis_goal="分析ROI")
        ctx.add_user_feedback(stage="scout", revision=1, raw_text="Period的中文名是周次")
        assert ctx.entries[0].raw_user_text == "Period的中文名是周次"
        assert ctx.entries[0].type == "user_feedback"

    def test_entries_are_append_only(self):
        """entries 只增不改，历史不可变。"""
        ctx = ProjectContext(run_id="r1", analysis_goal="分析ROI")
        ctx.add_user_feedback(stage="scout", revision=1, raw_text="第一轮")
        ctx.add_user_feedback(stage="scout", revision=2, raw_text="第二轮")
        assert len(ctx.entries) == 2
        assert ctx.entries[0].raw_user_text == "第一轮"
        assert ctx.entries[1].raw_user_text == "第二轮"

    def test_build_prompt_system_prefix_has_goal(self):
        """律 1：analysis_goal 永远在 system_prefix 首行。"""
        ctx = ProjectContext(run_id="r1", analysis_goal="分析各渠道ROI")
        result = ctx.build_prompt("scout", {"column_semantics": []})
        assert "分析各渠道ROI" in result["system_prefix"]

    def test_build_prompt_system_prefix_has_field_state(self):
        """system_prefix 包含从 column_semantics 派生的字段状态。"""
        ctx = ProjectContext(run_id="r1", analysis_goal="分析ROI")
        context = {
            "column_semantics": [
                {"column_name": "Code", "display_name": "店铺编号", "suggested_role": "feature", "used_in_analysis": True, "needs_user_input": False},
                {"column_name": "Period", "display_name": "周次", "suggested_role": "identifier", "used_in_analysis": False, "needs_user_input": True},
            ],
            "target": "Revenue",
            "features": ["Code"],
        }
        result = ctx.build_prompt("scout", context)
        assert "Code" in result["system_prefix"]
        assert "店铺编号" in result["system_prefix"]
        assert "Period" in result["system_prefix"]
        assert "Revenue" in result["system_prefix"]

    def test_build_prompt_history_context_includes_current_stage(self):
        """history_context 包含当前阶段的 user_feedback + agent_response。"""
        ctx = ProjectContext(run_id="r1", analysis_goal="分析ROI")
        ctx.add_user_feedback(stage="scout", revision=1, raw_text="Code是店铺编号")
        ctx.add_agent_response(stage="scout", revision=1, content="已更新 Code→店铺编号")

        result = ctx.build_prompt("scout", {"column_semantics": []})
        assert "Code是店铺编号" in result["history_context"]
        assert "已更新 Code→店铺编号" in result["history_context"]

    def test_build_prompt_history_context_excludes_other_stages_dialog(self):
        """上游阶段的对话细节不出现在当前阶段的 history_context 中（仅保留 snapshot 摘要）。"""
        ctx = ProjectContext(run_id="r1", analysis_goal="分析ROI")
        ctx.add_user_feedback(stage="scout", revision=1, raw_text="Code是店铺编号")
        ctx.add_agent_response(stage="scout", revision=1, content="已更新", snapshot={"target": "Revenue", "features": ["Code"], "pending": []})

        result = ctx.build_prompt("cleaner", {"column_semantics": []})
        # upstream 的对话细节不应出现
        assert "Code是店铺编号" not in result["history_context"]
        # 但 snapshot 摘要应出现
        assert "scout" in result["history_context"]

    def test_build_prompt_with_command_context(self):
        """_pending_command_text 应出现在 system_prefix 中。"""
        ctx = ProjectContext(run_id="r1", analysis_goal="分析ROI")
        context = {
            "column_semantics": [],
            "_pending_command_text": "/goal 改为分析利润趋势",
        }
        result = ctx.build_prompt("scout", context)
        assert "分析利润趋势" in result["system_prefix"]

    def test_snapshot_derived_from_column_semantics(self):
        """律 5：snapshot 从 column_semantics 实时派生，不平行存储。"""
        ctx = ProjectContext(run_id="r1", analysis_goal="分析ROI")
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

    def test_empty_context_does_not_crash(self):
        """空 context → build_prompt 正常返回，不抛异常。"""
        ctx = ProjectContext(run_id="r1", analysis_goal="分析ROI")
        result = ctx.build_prompt("scout", {})
        assert "system_prefix" in result
        assert "history_context" in result
        assert "分析ROI" in result["system_prefix"]
