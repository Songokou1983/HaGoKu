"""
DataAnalystAgent — 唯一数据分析师（Phase D：4 agent 合 1）

从 agents/prompt.md 读取统一 prompt（4 关注点），
所有工具对 LLM 可见，LLM 通过 route_to 声明关注点切换。
"""

from __future__ import annotations

import json as _json
import logging
from pathlib import Path
from typing import Any

import pandas as pd

from hagoku.config import LLMConfig
from hagoku.observability.event_bus import EventBus
from hagoku.observability.events import EventType
from hagoku.context.project_context import ToolCallRecord
from hagoku.agents.base import BaseAgent

logger = logging.getLogger("hagoku.agent")


class DataAnalystAgent(BaseAgent):
    """数据分析师 — 唯一 agent。

    一套 chat、一套 prompt、全部工具可见。
    LLM 自己按 4 个关注点（理解字段/评估清洗/跑统计/写报告）切换焦点，
    通过 route_to 声明 phase tag（仅作 LLM 自参考，不做工具过滤）。
    """

    ROLE = "analyst"  # prompt.md 目录名

    def __init__(
        self,
        llm_config: LLMConfig,
        event_bus: EventBus,
        orchestrator: Any | None = None,
        llm_client: Any | None = None,
    ) -> None:
        super().__init__(llm_config=llm_config, event_bus=event_bus,
                         orchestrator=orchestrator, llm_client=llm_client)

    # ── prompt 加载（统一 prompt.md）─────────────────────────────────

    def _load_prompt(self) -> str:
        """读取统一 prompt.md（4 关注点）。"""
        p = Path(__file__).parent / "prompt.md"
        if p.exists():
            return p.read_text(encoding="utf-8")
        return ""

    # ── 核心入口 ────────────────────────────────────────────────────

    def run_step(
        self,
        context: dict,
        df: pd.DataFrame | None = None,
        user_input: str = "",
    ) -> dict:
        """单步执行：跑 1 轮 LLM，处理 tool_calls。

        Phase D：统一 tool dispatch（含 submit_assessment / submit_analysis /
        submit_first_pass / submit_report / route_to / ask_user）。
        """
        from hagoku.tools.registry import agent_tools as _agt
        from hagoku.llm.client import create_raw_client

        if df is None:
            df = getattr(self, '_df', None)
        client = create_raw_client(self.llm_config)
        _tools = _agt.to_openai("analyst")  # D4 改为全集

        project_ctx = context.get("_project_context")
        if project_ctx is None:
            raise RuntimeError("DataAnalystAgent.run_step: _project_context 未设置")

        # Phase D: 注入当前关注点 phase 到 system 前缀
        phase_hint = context.get("_current_phase", "")
        agent_extra = self.prompt  # base.py __init__ 已加载到 self.prompt
        if phase_hint:
            agent_extra = f"【当前关注点：{phase_hint}】\n\n" + agent_extra

        messages = project_ctx.to_messages_for_llm(
            "analyst", context, user_input,
            agent_system_extra=agent_extra,
        )

        # ── LLM dump ──
        from hagoku.observability.llm_dump import dump_messages
        dump_messages(
            "agent_run_step",
            messages,
            model=self.llm_config.model,
            extra={"tools": [t["function"]["name"] for t in _tools]},
        )

        resp = client.chat.completions.create(
            model=self.llm_config.model, messages=messages,
            temperature=0.3, max_tokens=4096, tools=_tools, tool_choice="auto",
        )
        msg = resp.choices[0].message
        txt = (msg.content or "").strip()
        tc_list = getattr(msg, "tool_calls", None)

        dump_messages(
            "agent_run_step_response",
            messages + [{"role": "assistant", "content": txt,
             "tool_calls": [{"function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                            for tc in (tc_list or [])] if tc_list else None}],
            model=self.llm_config.model,
        )

        # 写回 ProjectContext
        revision = context.get("interaction_revision", 0)
        project_ctx.add_agent_response("analyst", revision, txt or "(tool calls)")

        # ── 统一 tool dispatch（所有 submit_* + route_to + ask_user）──
        route_to_args = None
        findings = None
        assessment = None

        if tc_list:
            tool_records = []
            for tc in tc_list:
                fn = tc.function
                try:
                    args = _json.loads(fn.arguments) if fn.arguments else {}
                except (_json.JSONDecodeError, TypeError):
                    continue

                # Phase C: route_to 优先（与 ask_user 同级优先）
                if fn.name == "route_to":
                    route_to_args = _agt.dispatch(fn.name, args, context, df)
                    continue
                if fn.name == "submit_analysis":
                    findings = _agt.dispatch(fn.name, args, context, df)
                    continue
                if fn.name == "submit_assessment":
                    assessment = _agt.dispatch(fn.name, args, context, df)
                    continue
                if fn.name == "submit_first_pass":
                    findings = _agt.dispatch(fn.name, args, context, df)
                    continue

                # 通用工具执行
                try:
                    result = _agt.dispatch(fn.name, args, context, df)
                    tool_records.append(ToolCallRecord(
                        tool_call_id=getattr(tc, "id", "") or "",
                        name=fn.name, arguments=fn.arguments,
                        result=_json.dumps(result, ensure_ascii=False, default=str),
                    ))
                except Exception as exc:
                    tool_records.append(ToolCallRecord(
                        tool_call_id=getattr(tc, "id", "") or "",
                        name=fn.name, arguments=fn.arguments,
                        result="", error=str(exc),
                    ))
            if tool_records:
                project_ctx.add_tool_exchange("analyst", revision, tool_records,
                                              assistant_content=txt)

        return {
            "text": txt,
            "route_to": route_to_args,
            "submit_analysis": findings is not None,
            "findings": findings,
            "submit_assessment": assessment is not None,
            "assessment": assessment,
        }
