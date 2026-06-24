"""用户回复路由处理 — 纯通道。"""

from __future__ import annotations

from typing import Any

from ...observability.events import EventType


def _handle_reply(self, user_input: str, context: dict) -> dict:
    """纯通道——不做阶段路由，LLM 自然推进。"""

    # ── 首次暂停 ──
    if not user_input or not user_input.strip():
        ask = context.pop("_pending_ask_user", None)
        if ask:
            self.event_bus.emit(EventType.USER_INPUT_REQUESTED, "scout", ask)
        else:
            self.event_bus.emit(EventType.USER_INPUT_REQUESTED, "scout", {"message": ""})
        return {"status": "scout_review", "message": ""}

    # ── 调 LLM ──
    df = self._df_clean if self._df_clean is not None else self._df_raw
    result = self._agent.run_step(context, df, user_input)
    self._log_channel("analyst", "run_step_done", text=result.get("text", ""))

    # ── 被动观测：LLM 调了 submit_* 说明阶段推进了 ──
    if result.get("submit_assessment"):
        self._stage = "analyst"
        context["_cleaner_assessment"] = result.get("assessment") or {}
    if result.get("submit_findings"):
        self._stage = "reporter"
        context["_analyst_findings"] = result.get("findings") or {}

    # ── ask_user 优先 ──
    ask = context.pop("_pending_ask_user", None)
    if ask:
        self.event_bus.emit(EventType.USER_INPUT_REQUESTED, "scout", ask)
        return {"status": "scout_review", "message": ""}

    # ── 留在当前 ──
    self.event_bus.emit(EventType.USER_INPUT_REQUESTED, "scout", {"message": ""})
    return {"status": "scout_review", "message": result.get("text", "")}


# ── respond（外层入口）────────────────────────────

def respond(self, user_input: dict) -> dict[str, Any]:
    """处理用户回复 — 写 Session → 调 handler → 处理 stage 切换。"""
    text = user_input.get("text", "").strip()
    self._log_channel("orchestrator", "respond_enter", text=text)

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

    result = _handle_reply(self, text, ctx or {})
    self.save_state()
    return result


# ── 存根（兼容旧测试）─────────────────────

def _handle_scout_reply(self, user_input, context):
    return _handle_reply(self, user_input, context)

def _handle_cleaner_reply(self, user_input, context):
    return _handle_reply(self, user_input, context)

def _handle_analyst_reply(self, user_input, context):
    return _handle_reply(self, user_input, context)

def _handle_reporter_reply(self, user_input, context):
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
    respond = respond
    _ensure_memory_for_respond = _ensure_memory_for_respond
