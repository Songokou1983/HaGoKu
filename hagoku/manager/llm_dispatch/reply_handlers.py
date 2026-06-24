"""用户回复路由处理 — 纯通道。"""

from __future__ import annotations

from typing import Any

from ...observability.events import EventType


def _handle_reply(self, user_input: str, context: dict) -> dict | tuple:
    """统一回复处理——所有阶段同一模式。"""

    stage = self._stage
    if not stage:
        return {"status": "error", "message": "未知阶段"}

    # ── 首次进入特殊处理 ──
    if not user_input or not user_input.strip():
        # Scout 空输入 → 首次暂停信号
        if stage == "scout":
            ask = context.pop("_pending_ask_user", None)
            if ask:
                self.event_bus.emit(EventType.USER_INPUT_REQUESTED, stage, ask)
                return ("stay", None)
            self.event_bus.emit(EventType.USER_INPUT_REQUESTED, stage, {"message": ""})
            return {"status": "scout_review", "message": ""}

        # Cleaner 空输入 → 如已有评估直接展示
        if stage == "cleaner" and context.get("_cleaner_assessment"):
            self._cleaner_dialog_open = True
            self.event_bus.emit(EventType.USER_INPUT_REQUESTED, stage, {"message": ""})
            return {"status": "cleaner_review", "message": ""}

    if stage == "cleaner" and context.get("_cleaner_assessment") is None:
        df = self._df_raw if self._df_raw is not None else self._df_clean
        context["_user_feedback"] = user_input
        assessment = self._agent.assess(df, context)
        context["_cleaner_assessment"] = assessment
        self._cleaner_dialog_open = True
        self.event_bus.emit(EventType.USER_INPUT_REQUESTED, stage, {"message": ""})
        self.event_bus.emit(EventType.AGENT_COMPLETED, stage, {"result_summary": "清洗评估完成"})
        return {"status": "cleaner_review", "message": ""}

    if stage == "analyst" and not self._analyst_first_pass_done:
        self._run_analyst_first_pass(context)
        self._analyst_first_pass_done = True
        self.event_bus.emit(EventType.USER_INPUT_REQUESTED, stage, {"message": ""})
        return {"status": "analyst_review", "message": ""}

    # ── 正常对话：调 LLM ──
    df = (self._df_raw if stage in ("scout", "cleaner")
          else self._df_clean if stage == "analyst"
          else None)
    result = self._agent.run_step(context, df, user_input or "")
    self._log_channel(stage, "run_step_done", text=result.get("text", ""))

    # ── ask_user 优先 ──
    ask = context.pop("_pending_ask_user", None)
    if ask:
        self.event_bus.emit(EventType.USER_INPUT_REQUESTED, stage, ask)
        return ("stay", None)

    # ── 留在当前阶段 ──
    self.event_bus.emit(EventType.USER_INPUT_REQUESTED, stage, {"message": ""})
    status = "reporter_done" if stage == "reporter" else f"{stage}_review"
    return {"status": status, "message": result.get("text", "")}


# ── respond（外层入口）────────────────────────────

def respond(self, user_input: dict) -> dict[str, Any]:
    """处理用户回复 — 写 Session → 调 handler → 处理 stage 切换。"""
    text = user_input.get("text", "").strip()
    self._log_channel("orchestrator", "respond_enter", text=text, stage=self._stage)

    if self._is_cancel_requested():
        return {"status": "cancelled", "message": "分析已中止"}
    if self._error:
        return {"status": "error", "message": str(self._error)}

    # R6 防护
    if not text:
        empty_count = getattr(self, '_empty_respond_count', 0) + 1
        setattr(self, '_empty_respond_count', empty_count)
        if empty_count >= 3:
            self._error = RuntimeError("连续 3 次空回复，可能存在死循环。请刷新页面重试。")
            return {"status": "error", "message": str(self._error)}
    else:
        setattr(self, '_empty_respond_count', 0)

    ctx = getattr(self, '_context', None)
    if ctx is not None:
        ctx["_current_stage"] = self._stage
        if text:
            ctx["_pending_command_text"] = text

    # 写 Session
    session = ctx.get("_session") if ctx else None
    if session and text:
        session.add("user", text)

    # 通过别名路由（兼容测试 mock 旧 handler 的场景）
    handler = getattr(self, f"_handle_{self._stage}_reply", None) if self._stage else None
    if handler:
        result = handler(text, ctx or {})
    else:
        result = _handle_reply(self, text, ctx or {})

    # stage 切换：只更新阶段，不做任何自动操作。LLM 主导一切。
    if isinstance(result, tuple) and len(result) >= 2 and result[0] == "switch":
        old_stage = self._stage
        self._stage = result[1]
        if len(result) > 2 and isinstance(result[2], dict):
            self._context.update(result[2])
        self.save_state()
        self.event_bus.emit(EventType.AGENT_COMPLETED, old_stage, {"result_summary": f"切换到 {self._stage}"})
        self.event_bus.emit(EventType.USER_INPUT_REQUESTED, self._stage, {"message": ""})
        return {"status": f"{self._stage}_review", "message": "", "phase_switched": True}

    self.save_state()
    return result


# ── 别名（兼容旧测试）─────────────────────────

def _run_analyst_first_pass(self, context: dict) -> None:
    """阶段 1：自动跑首波分析。LLM 流式输出直接到前端。"""
    self._agent.run_step(context, self._df_clean)
    self.event_bus.emit(EventType.USER_INPUT_REQUESTED, "analyst", {"message": ""})


def _handle_scout_reply(self, user_input, context):
    self._stage = "scout"
    return _handle_reply(self, user_input, context)

def _handle_cleaner_reply(self, user_input, context):
    self._stage = "cleaner"
    return _handle_reply(self, user_input, context)

def _handle_analyst_reply(self, user_input, context):
    self._stage = "analyst"
    return _handle_reply(self, user_input, context)

def _handle_reporter_reply(self, user_input, context):
    self._stage = "reporter"
    return _handle_reply(self, user_input, context)


# ── Mixin ──────────────────────────────────────

def _ensure_memory_for_respond(self, project_name: str) -> None:
    """确保 self.memory 已初始化。"""
    if self.memory is not None:
        return
    if self.output_mgr is None:
        from ...storage.output import OutputManager
        self.output_mgr = OutputManager(self.config.output, project_name)
    schema_file = self.output_mgr.project_dir / "progress.yaml"
    from ...storage.memory import MemoryManager
    self.memory = MemoryManager(self.db, progress_path=schema_file)


class ReplyHandlersMixin:
    _handle_reply = _handle_reply
    _handle_scout_reply = _handle_scout_reply
    _handle_cleaner_reply = _handle_cleaner_reply
    _handle_analyst_reply = _handle_analyst_reply
    _handle_reporter_reply = _handle_reporter_reply
    _run_analyst_first_pass = _run_analyst_first_pass
    respond = respond
    _ensure_memory_for_respond = _ensure_memory_for_respond
