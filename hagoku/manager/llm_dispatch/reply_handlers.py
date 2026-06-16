"""各阶段用户回复路由处理。Phase C: 阶段切换权交给 LLM route_to，暂停权交给 ask_user。"""
from __future__ import annotations

from typing import Any

from ..payloads.scout_payload import (
    scout_field_review_pause_payload,
)
from ...observability.events import EventType

# ═══════════════════════════════════════════════════════════════
# Phase C: 4 个 handler 收缩为 ~15 行 —— 只做三件事：
#   1. 把用户原话写入 ProjectContext（Phase B 已做）
#   2. 调 agent（内部走 to_messages_for_llm）
#   3. 根据 _pending_ask_user / _*_route_to 机械执行
# ═══════════════════════════════════════════════════════════════


def _handle_scout_reply(self, user_input: str, context: dict) -> dict | tuple:
    """Scout 阶段用户回复处理 — 通道直达。

    用户输入 → 对话历史 → LLM 自己看、自己决定。
    代码不截流，不单独调 LLM 解析。和 reporter handler 同模式。
    """
    # 空输入 = 首次展示——LLM 文本已由 run_scout_phase 直接 emit，这里只处理 ask_user
    if not user_input or not user_input.strip():
        ask = context.pop("_pending_ask_user", None)
        if ask:
            self.event_bus.emit(EventType.USER_INPUT_REQUESTED, "scout", ask)
            return ("stay", None)
        # 信号：分析暂停，前端显示输入框。文本已通过流式发送。
        self.event_bus.emit(EventType.USER_INPUT_REQUESTED, "scout", {"message": ""})
        return {"status": "scout_review", "message": ""}

    # 用户输入进对话历史，LLM 自己处理
    project_ctx = context.get("_project_context")
    if project_ctx:
        project_ctx.add_user_feedback("scout", context.get("interaction_revision", 0), raw_text=user_input)

    # 用户输入已由 add_user_feedback 写入 ProjectContext → build_prompt 历史。
    # run_step 的 user_input 传空，避免 build_messages 再追加一遍（×2）。
    result = self._agent.run_step(context, self._df_raw, "")
    self._log_channel("scout", "run_step_done", text=result.get("text","")[:80])

    # Phase C: ask_user 优先
    ask = context.pop("_pending_ask_user", None)
    if ask:
        self.event_bus.emit(EventType.USER_INPUT_REQUESTED, "scout", ask)
        return ("stay", None)

    # Phase C: route_to 切换
    route_to = result.get("route_to")
    if route_to:
        target = route_to.get("stage")
        if target and target != "scout":
            return ("switch", target, {"_route_reason": route_to.get("reason", "")})

    # 留在 scout：发信号让前端显示输入框。文本已通过流式发送，不在此重复。
    self.event_bus.emit(EventType.USER_INPUT_REQUESTED, "scout", {"message": ""})
    reply_text = result.get("text", "")
    return {"status": "scout_review", "message": reply_text}


def _handle_cleaner_reply(self, user_input: str, context: dict) -> dict | tuple:
    """Cleaner 评估阶段用户回复 — Phase C: LLM 驱动的阶段切换。

    首次：运行 assess 评估。后续：自由对话，LLM 通过 route_to 表达切换。
    """
    df = self._df_raw if self._df_raw is not None else self._df_clean

    # 首次评估（首波展示）
    assessment = context.get("_cleaner_assessment")
    if assessment is None:
        context["_user_feedback"] = user_input
        assessment = self._agent.assess(df, context)
        context["_cleaner_assessment"] = assessment
        self._cleaner_dialog_open = True
        self.event_bus.emit(EventType.USER_INPUT_REQUESTED, "cleaner", {
            "cleaning_assessment": assessment,
            "message": "清洗评估完成。你可以接受或提出调整。",
        })
        self.event_bus.emit(EventType.AGENT_COMPLETED, "cleaner", {"result_summary": "清洗评估完成"})
        return {"status": "cleaner_review", "message": "", "cleaning_assessment": assessment}

    # 对话模式 — Phase D: self._agent 由 orchestrator 保证已初始化
    if user_input:
        project_ctx = context.get("_project_context")
        if project_ctx:
            project_ctx.add_user_feedback("cleaner", context.get("interaction_revision", 0), raw_text=user_input)

    result = self._agent.run_step(context, df, user_input or "")

    # Phase C: ask_user 优先
    ask = context.pop("_pending_ask_user", None)
    if ask:
        self.event_bus.emit(EventType.USER_INPUT_REQUESTED, "cleaner", ask)
        return ("stay", None)

    # Phase C: route_to 切换（唯一阶段切换入口——无关键词分支）
    route_to = result.get("route_to")
    if route_to:
        target = route_to.get("stage")
        if target and target in {"scout", "analyst", "reporter"}:
            return ("switch", target, {"_route_reason": route_to.get("reason", "")})

    return {"status": "cleaner_review", "message": result.get("text", ""),
            "cleaning_assessment": assessment}


def _run_analyst_first_pass(self, context: dict) -> None:
    """阶段 1：自动跑首波分析，循环 run_step 直到 LLM 收敛或调 submit_first_pass。"""
    import json as _json

    max_rounds = 20
    findings = None
    first_pass_text = ""

    for _round in range(max_rounds):
        result = self._agent.run_step(context, self._df_clean)

        if result.get("submit_analysis"):
            findings = result.get("findings")
            break

        if findings is None:
            project_ctx = context.get("_project_context")
            if project_ctx:
                for entry in reversed(project_ctx.entries):
                    if entry.type == "tool_exchange" and entry.stage == "analyst":
                        for tc in (entry.tool_calls or []):
                            if tc.name == "submit_first_pass":
                                try:
                                    findings = _json.loads(tc.result) if tc.result else {}
                                except (_json.JSONDecodeError, TypeError):
                                    findings = {}
                                break
                        break
        if findings is not None:
            break

        if not result.get("text") and not findings:
            break

        first_pass_text = result.get("text", "")

    if findings:
        summary = _rewrite_as_written_summary(self, findings)
    else:
        raise RuntimeError(
            "首波自动分析未产生有效统计发现（findings 为空）。"
            "请确认字段「参与分析」标记正确，并查看 ~/.hagoku/llm_dumps/ 诊断。"
        )

    self.event_bus.emit(EventType.USER_INPUT_REQUESTED, "analyst", {
        "message": summary,
        "analyst_first_pass_summary": summary,
    })


def _rewrite_as_written_summary(self, findings: dict) -> str:
    """调 LLM 把原始统计 findings 重写为 3-5 段书面概括化发现。"""
    import json as _json
    from ...llm.client import create_raw_client
    from ...observability.llm_dump import dump_messages
    from hagoku.channel import build_messages

    system = (
        "你是数据分析师，把以下统计结果重写为 3-5 段书面发现。\n"
        "每段必须含 [发现] / [统计依据] / [局限或解读] 三要素标记。\n"
        "不许编造未在输入中出现的统计数字。\n"
        "不许给「建议进入报告阶段」等诱导用户终止的句式。\n"
        "用中文输出。"
    )
    user_content = _json.dumps(findings, ensure_ascii=False, default=str)
    # EXEMPT: 辅助 LLM — 统计 findings → 书面摘要转换，无状态数据变换，非对话延续
    messages = build_messages(query=user_content, user_input=user_content, system_extra=system)
    dump_messages("analyst_rewrite_summary", messages, model=self.config.llm.model)

    client = create_raw_client(self.config.llm)
    resp = client.chat.completions.create(
        model=self.config.llm.model,
        messages=messages,
        temperature=0.3,
        max_tokens=2048,
    )
    result = (resp.choices[0].message.content or "").strip()
    dump_messages(
        "analyst_rewrite_summary_response",
        messages + [{"role": "assistant", "content": result}],
        model=self.config.llm.model,
    )
    return result


def _handle_analyst_reply(self, user_input: str, context: dict) -> dict | tuple:
    """Analyst 对话阶段 — Phase C: LLM 驱动的阶段切换与暂停。"""
    # Phase D: self._agent 由 orchestrator 保证已初始化
    if not self._analyst_first_pass_done:
        _run_analyst_first_pass(self, context)
        self._analyst_first_pass_done = True
        if user_input:
            project_ctx = context.get("_project_context")
            if project_ctx:
                project_ctx.add_user_feedback("analyst", context.get("interaction_revision", 0), raw_text=user_input)
        return {"status": "analyst_review", "message": ""}

    if user_input:
        project_ctx = context.get("_project_context")
        if project_ctx:
            project_ctx.add_user_feedback("analyst", context.get("interaction_revision", 0), raw_text=user_input)

    result = self._agent.run_step(context, self._df_clean, user_input or "")

    # Phase C: ask_user 优先
    ask = context.pop("_pending_ask_user", None)
    if ask:
        self.event_bus.emit(EventType.USER_INPUT_REQUESTED, "analyst", ask)
        return ("stay", None)

    # Phase C: route_to 切换
    route_to = result.get("route_to")
    if route_to:
        target = route_to.get("stage")
        if target and target in {"scout", "cleaner", "reporter"}:
            return ("switch", target, {"_route_reason": route_to.get("reason", "")})

    if result.get("submit_analysis"):
        findings = result["findings"]
        violations, violations_md = self._check_mandatory_guardrails(findings.get("findings", []))
        return ("switch", "reporter", {"findings": findings})

    return {"status": "analyst_review", "message": result.get("text", "")}


def _handle_reporter_reply(self, user_input: str, context: dict) -> dict | tuple:
    """Reporter 阶段 — Phase C: LLM 驱动的阶段切换与暂停。"""
    # Phase D: self._agent 由 orchestrator 保证已初始化
    if user_input:
        project_ctx = context.get("_project_context")
        if project_ctx:
            project_ctx.add_user_feedback("reporter", context.get("interaction_revision", 0), raw_text=user_input)

    result = self._agent.run_step(context, None, user_input or "")

    # Phase C: ask_user 优先
    ask = context.pop("_pending_ask_user", None)
    if ask:
        self.event_bus.emit(EventType.USER_INPUT_REQUESTED, "reporter", ask)
        return ("stay", None)

    # Phase C: route_to 切换
    route_to = result.get("route_to")
    if route_to:
        target = route_to.get("stage")
        if target and target in {"scout", "cleaner", "analyst"}:
            return ("switch", target, {"_route_reason": route_to.get("reason", "")})

    return {"status": "reporter_done", "message": result.get("text", "")}


def respond(self, user_input: dict) -> dict[str, Any]:
    """Phase C: 处理用户回复 — 路由到当前 stage handler，机械执行返回。

    user_input: {"text": "用户回复", "stage": "当前阶段"}
    """
    text = user_input.get("text", "").strip()
    self._log_channel("orchestrator", "respond_enter", text=text[:80], stage=self._stage)
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
    result = handler(text, self._context)

    # 律 2：raw_text 写入 ProjectContext
    project_ctx = ctx.get("_project_context") if ctx else None
    if project_ctx and text:
        project_ctx.add_user_feedback(
            stage=self._stage,
            revision=getattr(self, '_respond_revision', 0),
            raw_text=text,
        )
        setattr(self, '_respond_revision', getattr(self, '_respond_revision', 0) + 1)

    # handler 返回 ("switch", "X") → 切换阶段，递归继续
    if isinstance(result, tuple) and len(result) >= 2 and result[0] == "switch":
        self._stage = result[1]
        if len(result) > 2 and isinstance(result[2], dict):
            self._context.update(result[2])
        # 递归：下一阶段自动跑首轮
        return self.respond(user_input)

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
    _rewrite_as_written_summary = _rewrite_as_written_summary
    _handle_analyst_reply = _handle_analyst_reply
    _handle_reporter_reply = _handle_reporter_reply
    respond = respond
    _ensure_memory_for_respond = _ensure_memory_for_respond
