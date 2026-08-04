"""用户回复路由处理 — 纯通道。"""

from __future__ import annotations

from typing import Any

import logging

_log = logging.getLogger("hagoku.reply_handlers")


def _push_snapshot(self, context: dict) -> None:
    """通过 WS 推送当前 Session 状态快照。"""
    try:
        from hagoku.api.ws_handler import WSBridge, _fastapi_app
        app = _fastapi_app
        if app is None:
            return
        hagoku_app = getattr(app.state, 'hagoku_app', None)
        if hagoku_app is None:
            return
        snap = hagoku_app.build_snapshot()
        if not snap:
            return
        WSBridge.get().push_snapshot(snap)
    except Exception:
        _log.exception("_push_snapshot 失败")


def _handle_reply(self, user_input: str, context: dict) -> dict:
    """纯通道——每轮一次 LLM 调用 + 工具 dispatch，自然停顿等用户。"""

    df = self._df_clean if self._df_clean is not None else self._df_raw
    result = self._agent.run_step(context, df, user_input or "")
    return {"status": "scout_review", "message": result.get("text", "")}


# ── respond（外层入口）────────────────────────────

def respond(self, user_input: dict) -> dict[str, Any]:
    """处理用户回复 — 消息由 WS respond 写入 Session。"""

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

    if not text:
        empty_count = getattr(self, '_empty_respond_count', 0) + 1
        setattr(self, '_empty_respond_count', empty_count)
        if empty_count >= 3:
            self._error = RuntimeError("连续 3 次空回复，可能存在死循环。请刷新页面重试。")
            return {"status": "error", "message": str(self._error)}
    else:
        setattr(self, '_empty_respond_count', 0)

    self._respond_cancelled = False
    self._processing = True

    ctx = getattr(self, '_context', None)
    if ctx is not None:
        if text:
            ctx["_pending_command_text"] = text

    try:
        result = _handle_reply(self, text, ctx or {})
        self.save_state()
        return result
    finally:
        self._processing = False



# ── Mixin ──────────────────────────────────────

class ReplyHandlersMixin:
    _handle_reply = _handle_reply
    respond = respond
