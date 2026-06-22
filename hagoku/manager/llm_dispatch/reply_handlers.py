"""各阶段用户回复路由处理。Phase C: 阶段切换权交给 LLM route_to，暂停权交给 ask_user。"""
from __future__ import annotations

from typing import Any

from ...observability.events import EventType

# ═══════════════════════════════════════════════════════════════
# Phase C: 4 个 handler 收缩为 ~15 行 —— 只做三件事：
#   1. 把用户原话写入 ProjectContext（Phase B 已做）
#   2. 调 agent（内部走 to_messages_for_llm）
#   3. 根据 _pending_ask_user / _*_route_to 机械执行
# ═══════════════════════════════════════════════════════════════


def _handle_scout_reply(self, user_input: str, context: dict) -> dict | tuple:
    """Scout 阶段用户回复处理 — 纯通道：不生成任何用户可见内容。"""
    # 空输入 = 首次暂停，发信号让前端显示输入框
    if not user_input or not user_input.strip():
        ask = context.pop("_pending_ask_user", None)
        if ask:
            self.event_bus.emit(EventType.USER_INPUT_REQUESTED, "scout", ask)
            return ("stay", None)
        # 首次展示：流式已送达LLM文本，这里只发信号
        self.event_bus.emit(EventType.USER_INPUT_REQUESTED, "scout", {"message": ""})
        return {"status": "scout_review", "message": ""}

    # 用户有输入 → LLM 自己看、自己决定
    result = self._agent.run_step(context, self._df_raw, "")
    self._log_channel("scout", "run_step_done", text=result.get("text",""))

    ask = context.pop("_pending_ask_user", None)
    if ask:
        self.event_bus.emit(EventType.USER_INPUT_REQUESTED, "scout", ask)
        return ("stay", None)

    route_to = result.get("route_to")
    if route_to:
        target = route_to.get("stage")
        if target and target != "scout":
            return ("switch", target, {"_route_reason": route_to.get("reason", "")})

    # 留在 scout：只透传 LLM 文本
    self.event_bus.emit(EventType.USER_INPUT_REQUESTED, "scout", {"message": ""})
    return {"status": "scout_review", "message": result.get("text", "")}


def _handle_cleaner_reply(self, user_input: str, context: dict) -> dict | tuple:
    """Cleaner 阶段 — 纯通道：LLM 自己评估、自己输出。"""
    df = self._df_raw if self._df_raw is not None else self._df_clean

    # 首次评估：跑 assess（内部调 LLM），后续对话：调 run_step
    assessment = context.get("_cleaner_assessment")
    if assessment is None:
        context["_user_feedback"] = user_input
        assessment = self._agent.assess(df, context)
        context["_cleaner_assessment"] = assessment
        self._cleaner_dialog_open = True
        self.event_bus.emit(EventType.USER_INPUT_REQUESTED, "cleaner", {"message": ""})
        self.event_bus.emit(EventType.AGENT_COMPLETED, "cleaner", {"result_summary": "清洗评估完成"})
        return {"status": "cleaner_review", "message": ""}

    result = self._agent.run_step(context, df, user_input or "")

    ask = context.pop("_pending_ask_user", None)
    if ask:
        self.event_bus.emit(EventType.USER_INPUT_REQUESTED, "cleaner", ask)
        return ("stay", None)

    route_to = result.get("route_to")
    if route_to:
        target = route_to.get("stage")
        if target and target in {"scout", "analyst", "reporter"}:
            return ("switch", target, {"_route_reason": route_to.get("reason", "")})

    self.event_bus.emit(EventType.USER_INPUT_REQUESTED, "cleaner", {"message": ""})
    return {"status": "cleaner_review", "message": result.get("text", "")}


def _run_analyst_first_pass(self, context: dict) -> None:
    """阶段 1：自动跑首波分析。LLM 流式输出直接到前端。"""
    self._agent.run_step(context, self._df_clean)
    self.event_bus.emit(EventType.USER_INPUT_REQUESTED, "analyst", {"message": ""})


def _handle_analyst_reply(self, user_input: str, context: dict) -> dict | tuple:
    """Analyst 阶段 — 纯通道。"""
    if not self._analyst_first_pass_done:
        _run_analyst_first_pass(self, context)
        self._analyst_first_pass_done = True
        return {"status": "analyst_review", "message": ""}

    result = self._agent.run_step(context, self._df_clean, user_input or "")

    ask = context.pop("_pending_ask_user", None)
    if ask:
        self.event_bus.emit(EventType.USER_INPUT_REQUESTED, "analyst", ask)
        return ("stay", None)

    route_to = result.get("route_to")
    if route_to:
        target = route_to.get("stage")
        if target and target in {"scout", "cleaner", "reporter"}:
            return ("switch", target, {"_route_reason": route_to.get("reason", "")})

    self.event_bus.emit(EventType.USER_INPUT_REQUESTED, "analyst", {"message": ""})
    return {"status": "analyst_review", "message": result.get("text", "")}


def _handle_reporter_reply(self, user_input: str, context: dict) -> dict | tuple:
    """Reporter 阶段 — 纯通道。"""
    result = self._agent.run_step(context, None, user_input or "")

    ask = context.pop("_pending_ask_user", None)
    if ask:
        self.event_bus.emit(EventType.USER_INPUT_REQUESTED, "reporter", ask)
        return ("stay", None)

    route_to = result.get("route_to")
    if route_to:
        target = route_to.get("stage")
        if target and target in {"scout", "cleaner", "analyst"}:
            return ("switch", target, {"_route_reason": route_to.get("reason", "")})

    self.event_bus.emit(EventType.USER_INPUT_REQUESTED, "reporter", {"message": ""})
    return {"status": "reporter_done", "message": result.get("text", "")}


def respond(self, user_input: dict) -> dict[str, Any]:
    """Phase C: 处理用户回复 — 路由到当前 stage handler，机械执行返回。

    user_input: {"text": "用户回复", "stage": "当前阶段"}
    """
    text = user_input.get("text", "").strip()
    self._log_channel("orchestrator", "respond_enter", text=text, stage=self._stage)
    if self._is_cancel_requested():
        return {"status": "cancelled", "message": "分析已中止"}
    if self._error:
        return {"status": "error", "message": str(self._error)}

    # R6 防护：连续空回复死循环检测
    if not text:
        empty_count = getattr(self, '_empty_respond_count', 0) + 1
        setattr(self, '_empty_respond_count', empty_count)
        if empty_count >= 3:
            self._error = RuntimeError("连续 3 次空回复，可能存在死循环。请刷新页面重试。")
            return {"status": "error", "message": str(self._error)}
    else:
        setattr(self, '_empty_respond_count', 0)

    # Phase C: 注入 _current_stage 供 ask_user handler 使用
    ctx = getattr(self, '_context', None)
    if ctx is not None:
        ctx["_current_stage"] = self._stage

    handler_name = self._STAGE_HANDLERS.get(self._stage)
    if handler_name is None:
        return {"status": "error", "message": f"未知阶段: {self._stage}"}

    handler = getattr(self, handler_name)
    # 律 1+律 2：用户最新指令注入 _pending_command_text，供下一阶段首轮 LLM 调用
    # （infer_field_semantics / assess 读取此字段注入 prompt）
    if ctx is not None and text:
        ctx["_pending_command_text"] = text
    # 律 2：raw_text 先写入 ProjectContext，再调 handler——确保 LLM 看到用户原话
    session = ctx.get("_session") if ctx else None
    if session and text:
        session.add("user", text)
    result = handler(text, self._context)

    # handler 返回 ("switch", "X") → 切换阶段，递归继续
    if isinstance(result, tuple) and len(result) >= 2 and result[0] == "switch":
        self._stage = result[1]
        if len(result) > 2 and isinstance(result[2], dict):
            self._context.update(result[2])
        # 递归：下一阶段自动跑首轮（text 置空，避免 add_user_feedback 再写一遍）
        self.save_state()
        return self.respond({"text": "", "stage": self._stage})

    # 保存状态供 app 重启恢复
    self.save_state()
    return result


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


# ── Mixin class ────────────────────────────────────────────

class ReplyHandlersMixin:
    _handle_scout_reply = _handle_scout_reply
    _handle_cleaner_reply = _handle_cleaner_reply
    _run_analyst_first_pass = _run_analyst_first_pass
    _handle_analyst_reply = _handle_analyst_reply
    _handle_reporter_reply = _handle_reporter_reply
    respond = respond
    _ensure_memory_for_respond = _ensure_memory_for_respond
