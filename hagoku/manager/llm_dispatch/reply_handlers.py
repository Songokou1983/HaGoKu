"""用户回复路由处理 — 纯通道。"""

from __future__ import annotations

from typing import Any

from ...observability.events import EventType


def _save_review_cards(context: dict, ask: dict | None = None) -> None:
    """将 context 中的 review 数据写入 Session——仅当 LLM 正在等待用户确认时。"""
    ask = ask or context.get("_pending_ask_user")
    if not ask:
        return
    session = context.get("_session")
    if not session:
        return

    # ask_user 卡片（每次 ask 都写，因为是新的暂停点）
    session.add_workflow_card("ask_user", {
        "question": ask.get("question", ""),
        "expected_format": ask.get("expected_format", ""),
        "options": ask.get("options", []),
    })

    # field_review: 从 column_semantics 构建（检查所有消息去重，不只看最后一条）
    cs = context.get("column_semantics", [])
    if cs and context.get("n_rows"):
        # 检查是否已有相同的 field_review
        already = any(
            m.get("role") == "workflow" and m.get("type") == "field_review"
            for m in (session.messages or [])
        )
        if already:
            return
        rows = []
        for s in cs:
            if isinstance(s, dict) and "column_name" in s:
                rows.append({
                    "field_name": s.get("column_name", ""),
                    "chinese_name": s.get("display_name") or s.get("chinese_name") or None,
                    "meaning": s.get("description", ""),
                    "suggested_role": s.get("suggested_role") or None,
                    "used_in_analysis": s.get("used_in_analysis"),
                    "evidence": s.get("evidence", ""),
                })
        if rows:
            session.add_workflow_card("field_review", {
                "field_review": {"n_rows": context["n_rows"], "n_cols": context.get("n_cols", len(rows)), "rows": rows},
            })


def _handle_reply(self, user_input: str, context: dict) -> dict:
    """纯通道——不做阶段路由，LLM 自然推进。"""

    # ── 首次暂停 ──
    if not user_input or not user_input.strip():
        ask = context.pop("_pending_ask_user", None)
        _save_review_cards(context, ask)
        self.event_bus.emit(EventType.USER_INPUT_REQUESTED, "", ask or {})
        return {"status": "scout_review", "message": ""}

    # 用户已回复，清除上一次 ask_user 的残留信号
    context.pop("_pending_ask_user", None)

    df = self._df_clean if self._df_clean is not None else self._df_raw
    result = self._agent.run_step(context, df, user_input)

    ask = context.pop("_pending_ask_user", None)
    if ask:
        _save_review_cards(context, ask)
        self.event_bus.emit(EventType.USER_INPUT_REQUESTED, "", ask)
        return {"status": "scout_review", "message": ""}

    self.event_bus.emit(EventType.USER_INPUT_REQUESTED, "")
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

    # ── 清除上次停止标记，标记处理中 ──
    self._respond_cancelled = False
    self._processing = True

    ctx = getattr(self, '_context', None)
    if ctx is not None:
        if text:
            ctx["_pending_command_text"] = text

    # 写 Session（外层 respond 已提前写入，此处不重复）

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
