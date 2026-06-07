"""各阶段用户回复路由处理。CH-5 从 orchestrator.py 拆分。"""
from __future__ import annotations

from typing import Any

from ..payloads.scout_payload import (
    scout_field_review_pause_payload,
    scout_user_input_received_payload,
)
from .scout_reply import apply_scout_user_field_reply_to_context
from ...observability.events import EventType

def _handle_scout_reply(self, user_input: str, context: dict) -> dict | tuple:
    """处理 Scout 字段对齐阶段的用户回复。空输入=首次展示字段表。"""
    if not user_input or not user_input.strip():
        scout_msg = scout_field_review_pause_payload(context)
        scout_msg = self._attach_pause_dialogue_message("scout", scout_msg)
        # 空输入 = 首次展示或重连后补发：emit 事件确保前端收到
        self.event_bus.emit(EventType.USER_INPUT_REQUESTED, "scout", scout_msg)
        return {
            "status": "scout_review",
            "message": "",
            "field_review": scout_msg.get("field_review"),
        }
    # 纯确认（进入下一阶段）→ 不调 LLM，直接切 Cleaner
    if user_input.strip() in ("可以进入下一阶段了", "确认", "好的", "OK", "ok", "继续", "下一步", "进入下一阶段"):
        self.event_bus.emit(EventType.AGENT_COMPLETED, "scout", {
            "result_summary": "字段理解完成",
        })
        return ("switch", "cleaner")

    applied = apply_scout_user_field_reply_to_context(
        context, user_input,
        llm_client=self.llm_quick_raw,
        llm_model=self.config.llm.model_quick or self.config.llm.model,
    )
    if applied and self.memory:
        self._persist_scout_field_updates(self._project_name, applied, context)
    if not applied:
        self.event_bus.emit(EventType.AGENT_COMPLETED, "scout", {
            "result_summary": "字段理解完成",
        })
        return ("switch", "cleaner")
    scout_msg = scout_field_review_pause_payload(context)
    scout_msg = self._attach_pause_dialogue_message("scout", scout_msg)
    # 通知前端字段已更新
    self.event_bus.emit(EventType.USER_INPUT_REQUESTED, "scout", scout_msg)
    return {
        "status": "scout_review",
        "message": "",
        "field_review": scout_msg.get("field_review"),
    }

def _handle_cleaner_reply(self, user_input: str, context: dict) -> dict | tuple:
    """处理 Cleaner 评估阶段的用户回复。首次调用运行评估，后续直接进入下一阶段。"""
    assessment = context.get("_cleaner_assessment")
    if assessment is None:
        from hagoku.agents.cleaner import CleanerAgent
        cleaner = CleanerAgent(self.config.llm, self.event_bus, llm_client=self.llm_quick)
        cleaning_rules = cleaner._load_cleaning_rules()
        context["_user_feedback"] = user_input
        # F-082: Cleaner 评估优先用原始数据 _df_raw（用户原始数据特征
        # 是清洗决策的依据）；若不可用（如 resume 跳过了原始加载），回退 _df_clean
        df = self._df_raw if self._df_raw is not None else self._df_clean
        assessment = cleaner.assess(df, context, cleaning_rules)
        context["_cleaner_assessment"] = assessment
        # 通知前端展示清洗评估
        self.event_bus.emit(EventType.USER_INPUT_REQUESTED, "cleaner", {
            "cleaning_assessment": assessment,
            "message": "清洗评估完成",
        })
        self.event_bus.emit(EventType.AGENT_COMPLETED, "cleaner", {
            "result_summary": "清洗评估完成",
        })
        return {"status": "cleaner_review", "message": "", "cleaning_assessment": assessment}
    # 用户确认 → 进入下一阶段
    return ("switch", "analyst")

def _run_analyst_first_pass(self, context: dict) -> None:
    """阶段 1：自动跑首波分析，循环 run_step 直到 LLM 收敛或调 submit_first_pass。

    拿到原始 findings 后调 LLM 重写为书面概括化结论，emit USER_INPUT_REQUESTED。
    """
    import json as _json

    max_rounds = 20
    findings = None
    first_pass_text = ""

    for _round in range(max_rounds):
        result = self._analyst_agent.run_step(self._analyst_messages, context, self._df_clean)
        self._analyst_messages = result["messages"]

        if result.get("submit_analysis"):
            findings = result.get("findings")
            break

        # 检查本轮是否调了 submit_first_pass
        if self._analyst_messages:
            last_msg = self._analyst_messages[-1]
            if last_msg.get("role") == "tool":
                # tool 消息在上一条 assistant 之后 — 检查上一条 assistant 的 tool_calls
                for i in range(len(self._analyst_messages) - 2, -1, -1):
                    m = self._analyst_messages[i]
                    if m.get("role") == "assistant" and m.get("tool_calls"):
                        for tc in m["tool_calls"]:
                            if tc.get("function", {}).get("name") == "submit_first_pass":
                                # dispatch 结果在 tool 消息中
                                try:
                                    findings = _json.loads(last_msg.get("content", "{}"))
                                except (_json.JSONDecodeError, TypeError):
                                    findings = {}
                                break
                        break
            if findings is not None:
                break

        # LLM 无 tool_calls 且无文本 → 收敛
        if not result.get("text") and not findings:
            break

        first_pass_text = result.get("text", "")

    # 重写为书面概括
    if findings:
        summary = _rewrite_as_written_summary(self, findings)
    elif first_pass_text:
        summary = first_pass_text
    else:
        summary = "首波自动分析完成。请提出你的问题或方向调整。"
        self._analyst_messages.append({
            "role": "assistant",
            "content": "首波自动分析完成，等待用户输入。",
        })

    # emit 给前端
    self.event_bus.emit(EventType.USER_INPUT_REQUESTED, "analyst", {
        "message": summary,
        "analyst_first_pass_summary": summary,
    })


def _rewrite_as_written_summary(self, findings: dict) -> str:
    """调 LLM 把原始统计 findings 重写为 3-5 段书面概括化发现。

    每段含 [发现] / [统计依据] / [局限或解读] 三要素。
    """
    import json as _json
    from ...llm.client import create_raw_client

    system = (
        "你是数据分析师，把以下统计结果重写为 3-5 段书面发现。\n"
        "每段必须含 [发现] / [统计依据] / [局限或解读] 三要素标记。\n"
        "不许编造未在输入中出现的统计数字。\n"
        "不许给「建议进入报告阶段」等诱导用户终止的句式。\n"
        "用中文输出。"
    )
    user_content = _json.dumps(findings, ensure_ascii=False, default=str)

    client = create_raw_client(self.config.llm)
    resp = client.chat.completions.create(
        model=self.config.llm.model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user_content},
        ],
        temperature=0.3,
        max_tokens=2048,
    )
    return (resp.choices[0].message.content or "").strip()


def _handle_analyst_reply(self, user_input: str, context: dict) -> dict | tuple:
    """处理 Analyst 对话阶段的用户回复。

    首次进入时自动跑首波分析（阶段 1），产出书面概括化结论。
    后续回复进入自由对话（阶段 2）。
    """
    if self._analyst_agent is None:
        from hagoku.agents.analyst import AnalystAgent
        self._analyst_agent = AnalystAgent(self.config.llm, self.event_bus, llm_client=self.llm_deep)
        self._analyst_messages = []

    if not self._analyst_first_pass_done:
        # 阶段 1：自动跑首波分析（不消耗用户输入）
        _run_analyst_first_pass(self, context)
        self._analyst_first_pass_done = True
        # 用户首次进入时尾话保留，作为阶段 2 第一条用户消息
        if user_input:
            self._analyst_messages.append({"role": "user", "content": user_input})
        return {"status": "analyst_review", "message": ""}

    if user_input:
        self._analyst_messages.append({"role": "user", "content": user_input})

    result = self._analyst_agent.run_step(self._analyst_messages, context, self._df_clean)
    self._analyst_messages = result["messages"]

    # 优先判 route_to：LLM 主动表达流程意图
    route_to = result.get("route_to")
    if route_to:
        target = route_to.get("stage")
        if target and target in {"scout", "cleaner", "reporter"}:
            return ("switch", target, {"_route_reason": route_to.get("reason", "")})
        # target == "analyst" 或空 → 留在当前阶段，继续对话

    if result.get("submit_analysis"):
        findings = result["findings"]
        # 护栏检查
        violations, violations_md = self._check_mandatory_guardrails(findings.get("findings", []))
        return ("switch", "reporter", {"findings": findings})
    return {"status": "analyst_review", "message": result.get("text", "")}

def _handle_reporter_reply(self, user_input: str, context: dict) -> dict:
    """Reporter 阶段不互动，直接返回。"""
    return {"status": "reporter_done"}

def respond(self, user_input: dict) -> dict[str, Any]:
    """
    处理 Agent 暂停后的用户响应，继续工作流。

    事件驱动版：根据 self._stage 路由到对应的 handler，
    handler 返回 ("switch", "X") 时自动切换阶段并递归重试。

    user_input 格式:
      {"text": "用户的回复内容", "stage": "当前阶段"}

    Returns:
        与 run() 返回格式相同的 dict
    """
    text = user_input.get("text", "").strip()
    if self._is_cancel_requested():
        return {"status": "cancelled", "message": "分析已中止"}

    if self._error:
        return {"status": "error", "message": str(self._error)}

    handler_name = self._STAGE_HANDLERS.get(self._stage)
    if handler_name is None:
        return {"status": "error", "message": f"未知阶段: {self._stage}"}

    handler = getattr(self, handler_name)
    result = handler(text, self._context)

    # 律 2：raw_text 写入 ProjectContext，保留用户原话
    project_ctx = self._context.get("_project_context") if self._context else None
    if project_ctx and text:
        project_ctx.add_user_feedback(
            stage=self._stage,
            revision=getattr(self, '_respond_revision', 0),
            raw_text=text,
        )
        setattr(self, '_respond_revision', getattr(self, '_respond_revision', 0) + 1)

    # handler 返回 ("switch", "X") → 切换阶段并递归
    if isinstance(result, tuple) and len(result) >= 2 and result[0] == "switch":
        self._stage = result[1]
        if len(result) > 2 and isinstance(result[2], dict):
            self._context.update(result[2])
        return self.respond(user_input)

    return result

def _ensure_memory_for_respond(self, project_name: str) -> None:
    """确保 self.memory 已初始化（供 WebSocket respond() 路径使用）。"""
    if self.memory is not None:
        return
    if self.output_mgr is None:
        self.output_mgr = OutputManager(self.config.output, project_name)
    schema_file = self.output_mgr.project_dir / "progress.yaml"
    self.memory = MemoryManager(self.db, progress_path=schema_file)
