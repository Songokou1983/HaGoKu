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

    def test_build_prompt_history_context_includes_current_stage(self, ctx):
        """messages_history 包含当前阶段的 user_feedback + agent_response。"""
        ctx.add_user_feedback(stage="scout", revision=1, raw_text="Code是店铺编号")
        ctx.add_agent_response(stage="scout", revision=1, content="已更新 Code→店铺编号")

        result = ctx.build_prompt("scout", {"column_semantics": []})
        msgs = result["messages_history"]
        assert len(msgs) == 2
        assert msgs[0]["role"] == "user" and "Code是店铺编号" in msgs[0]["content"]
        assert msgs[1]["role"] == "assistant" and "已更新" in msgs[1]["content"]

    def test_build_prompt_history_context_includes_cross_stage_dialog(self, ctx):
        """上下文保真律：跨阶段的对话也必须出现在 messages_history 中。"""
        ctx.add_user_feedback(stage="scout", revision=1, raw_text="Code是店铺编号")
        ctx.add_agent_response(stage="scout", revision=1, content="已更新", snapshot={"target": "Revenue", "features": ["Code"], "pending": []})

        result = ctx.build_prompt("cleaner", {"column_semantics": []})
        # 跨阶段对话必须在 messages_history 中
        found = False
        for msg in result["messages_history"]:
            if "Code是店铺编号" in msg.get("content", ""):
                found = True
        assert found, "跨阶段用户原话应在 messages_history 中"

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
        assert "messages_history" in result
        assert result["messages_history"] == []

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
        assert result["messages_history"] == []


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


def test_subscribe_持久引用_AGENT_COMPLETED_拿到正确_snapshot():
    """守门：subscribe(context_ref=空dict) → dict 被 update 后 → AGENT_COMPLETED 拿到的 snapshot 非空。

    验证 必修 3：context dict 引用稳定，snapshot 不因 context 延迟填充而丢失。
    """
    from hagoku.observability.event_bus import EventBus
    from hagoku.observability.events import EventType

    ctx = ProjectContext(run_id="r1", analysis_goal="分析ROI")
    ref = {}
    bus = EventBus()
    ctx.subscribe(bus, context_ref=ref)

    # 模拟 scout.run() 完成后 context 被填充
    ref.update({
        "column_semantics": [
            {"column_name": "Revenue", "display_name": "收入", "used_in_analysis": True},
        ],
        "target": "Revenue",
        "features": ["Code"],
    })

    bus.emit(EventType.AGENT_COMPLETED, "scout", {"result_summary": "完成"})

    assert len(ctx.entries) == 1
    assert ctx.entries[0].type == "agent_response"
    assert ctx.entries[0].snapshot is not None
    assert len(ctx.entries[0].snapshot.get("fields", [])) == 1
    assert ctx.entries[0].snapshot["target"] == "Revenue"


# ── _on_event _context_ref is None 回归测试（CH-3 fixup）──

def test_on_event_agent_completed_without_context_ref_raises():
    """_context_ref is None 时 AGENT_COMPLETED → raise RuntimeError，不静默降级。
    律 7 守门：通道断裂必须 raise，logging.warning + ctx={} 是违规。"""
    from hagoku.observability.events import Event, EventType
    from datetime import datetime

    ctx = ProjectContext(run_id="r1", analysis_goal="分析ROI")
    # 不 subscribe，_context_ref 保持默认 None
    event = Event(
        event_id="e1",
        event_type=EventType.AGENT_COMPLETED,
        timestamp=datetime.now(),
        agent="scout",
        data={"result_summary": "完成"},
    )
    with pytest.raises(RuntimeError, match="信息通道断裂"):
        ctx._on_event(event)


def test_on_event_user_input_received_without_context_ref_raises():
    """_context_ref is None 时 USER_INPUT_RECEIVED → raise RuntimeError。"""
    from hagoku.observability.events import Event, EventType
    from datetime import datetime

    ctx = ProjectContext(run_id="r1", analysis_goal="分析ROI")
    event = Event(
        event_id="e2",
        event_type=EventType.USER_INPUT_RECEIVED,
        timestamp=datetime.now(),
        agent="scout",
        data={"reply": "Code是店铺编号"},
    )
    with pytest.raises(RuntimeError, match="信息通道断裂"):
        ctx._on_event(event)


def test_一轮scout反馈不产生重复entries():
    """守门：一轮 _apply_scout_reply_with_llm + emit USER_INPUT_RECEIVED
    应恰好产生 1 user_feedback + 1 agent_response，不能重复。"""
    from hagoku.observability.event_bus import EventBus
    from hagoku.observability.events import EventType
    from hagoku.context.project_context import ProjectContext

    ctx = ProjectContext(run_id="r1", analysis_goal="分析ROI")
    ref = {"column_semantics": [], "interaction_revision": 1}
    bus = EventBus()
    ctx.subscribe(bus, context_ref=ref)

    # 模拟 USER_INPUT_RECEIVED 事件（orchestrator L2291）
    bus.emit(EventType.USER_INPUT_RECEIVED, "scout", {"reply": "Code是店铺编号"})

    # 模拟 _apply_scout_reply_with_llm 完成后的 add_agent_response
    ctx.add_agent_response(stage="scout", revision=1, content="已更新", snapshot={})

    feedbacks = [e for e in ctx.entries if e.type == "user_feedback"]
    responses = [e for e in ctx.entries if e.type == "agent_response"]
    assert len(feedbacks) == 1, f"期望 1 条 user_feedback，实际 {len(feedbacks)}"
    assert len(responses) == 1, f"期望 1 条 agent_response，实际 {len(responses)}"
    assert len(ctx.entries) == 2, f"期望总计 2 条 entries，实际 {len(ctx.entries)}"
