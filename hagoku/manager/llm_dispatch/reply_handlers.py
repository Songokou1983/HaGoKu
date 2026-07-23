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
            self.event_bus.emit(EventType.USER_INPUT_REQUESTED, "", ask)
        else:
            self.event_bus.emit(EventType.USER_INPUT_REQUESTED, "", {"message": ""})
        return {"status": "scout_review", "message": ""}

    # ── 调 LLM ──
    df = self._df_clean if self._df_clean is not None else self._df_raw
    result = self._agent.run_step(context, df, user_input)
    self._log_channel("analyst", "run_step_done", text=result.get("text", ""))

    # ── ask_user 优先 ──
    ask = context.pop("_pending_ask_user", None)
    if ask:
        # 存回 context 供 save_state 和 snapshot 持久化
        context["_pending_ask_user"] = ask
        self.event_bus.emit(EventType.USER_INPUT_REQUESTED, "", ask)
        return {"status": "scout_review", "message": ""}

    # ── 留在当前 ──
    self.event_bus.emit(EventType.USER_INPUT_REQUESTED, "", {"message": ""})
    return {"status": "scout_review", "message": result.get("text", "")}


# ── respond（外层入口）────────────────────────────

def respond(self, user_input: dict) -> dict[str, Any]:
    """处理用户回复 — 消息由 HTTP save_user_msg 落盘，此处不重复写入。"""

    text = user_input.get("text", "").strip()

    with self._respond_lock:
        return _respond_impl(self, user_input)


def _respond_impl(self, user_input: dict) -> dict[str, Any]:
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

    # ── 清除上次停止标记 ──
    self._respond_cancelled = False

    ctx = getattr(self, '_context', None)
    if ctx is not None:
        if text:
            ctx["_pending_command_text"] = text

    # 写 Session（外层 respond 已提前写入，此处不重复）

    result = _handle_reply(self, text, ctx or {})
    self.save_state()
    return result



# ── Mixin ──────────────────────────────────────

class ReplyHandlersMixin:
    _handle_reply = _handle_reply
    respond = respond
