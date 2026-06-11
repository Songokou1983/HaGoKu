"""
Analyst Agent — 数理分析员

从 prompt.md 读取角色定义，从 memory.md 读取/保存分析模式
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    pass
from uuid import uuid4

import pandas as pd
import yaml

from ...config import LLMConfig
from ...guardrails.statistical import StatisticalGuardrails
from ...guardrails.parsers import deep_validate
from ...observability.event_bus import EventBus
from ...observability.events import EventType
from ...tools.analysis import (
    check_test_assumptions,
    correlation,
    cross_validate,
    kruskal_wallis,
    mann_whitney_u,
    multiple_comparison_correction,
    regression,
    ttest,
)
from ...tools.power_analysis import power_ttest
from ..base import BaseAgent
from ..types import InteractionResult
from . import knowledge as analyst_knowledge

logger = logging.getLogger("hagoku.analyst")

from ..constants import (
    ANALYST_DEDUP_SIMILARITY,
    CLEANING_IMPACT_HIGH_THRESHOLD,
    CLEANING_IMPACT_MEDIUM_THRESHOLD,

    CROSS_VALIDATION_FOLDS_DEFAULT,
    DW_LOWER_BOUND,
    DW_UPPER_BOUND,
    LLM_TOKEN_RATE_MIN,
    POWER_ADEQUATE_PER_GROUP,
    POWER_EFFECT_SIZE_DEFAULT,
    POWER_MIN_PER_GROUP_SAMPLE,
    POWER_MIN_TOTAL_SAMPLE,
    POWER_REGRESSION_RATIO,
    POWER_TARGET_PCT,
    SIGNIFICANCE_LABEL_CORRECTED,
    SIGNIFICANCE_LABEL_NOT_SIG,
    SIGNIFICANCE_LABEL_SIG,
    SIGNIFICANCE_THRESHOLD,
)


class NeedUserClarification(Exception):
    """LLM 无法确定分析策略时需要用户澄清"""
    def __init__(self, message: str, *, options: list[str] | None = None, context: dict | None = None):
        super().__init__(message)
        self.message = message
        self.options = options or []
        self.context = context or {}


@dataclass
class AnalysisResult:
    """单个分析结果"""
    result_id: str
    analysis_type: str
    question: str
    conclusion_plain: str = ""
    conclusion_statistical: str = ""
    p_value: float | None = None
    effect_size: float | None = None
    effect_type: str = ""
    confidence_interval: str | None = None
    significance: str = ""
    sample_size: int | None = None
    test_statistic: float | None = None
    diagnostics: dict[str, Any] | None = None
    guardrail_results: list[dict[str, Any]] = field(default_factory=list)
    raw_result: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "result_id": self.result_id,
            "analysis_type": self.analysis_type,
            "question": self.question,
            "conclusion_plain": self.conclusion_plain,
            "conclusion_statistical": self.conclusion_statistical,
            "p_value": self.p_value,
            "effect_size": self.effect_size,
            "effect_type": self.effect_type,
            "confidence_interval": self.confidence_interval,
            "significance": self.significance,
            "sample_size": self.sample_size,
            "test_statistic": self.test_statistic,
            "diagnostics": self.diagnostics,
            "guardrail_results": self.guardrail_results,
        }


class AnalystAgent(BaseAgent):
    """数理分析员：用统计方法挖出数据背后的真相"""
    role = "analyst"
    _memory_yaml_key = "analysis_patterns"

    def __init__(
        self,
        llm_config: LLMConfig,
        event_bus: EventBus,
        orchestrator: Any | None = None,
        llm_client: Any | None = None,
    ) -> None:
        super().__init__(llm_config=llm_config, event_bus=event_bus,
                         orchestrator=orchestrator, llm_client=llm_client)
        self.guardrails = StatisticalGuardrails()

    def _load_memory(self) -> dict:
        path = Path(__file__).parent / "memory.md"
        if path.exists():
            content = path.read_text(encoding="utf-8")
            match = re.search(r"```yaml\n(analysis_patterns:.*?)```", content, re.DOTALL)
            if match:
                try:
                    return yaml.safe_load(match.group(1)) or {}
                except yaml.YAMLError:
                    return {}
        return {"analysis_patterns": {}}

    def _save_memory(self) -> None:
        path = Path(__file__).parent / "memory.md"
        content = path.read_text(encoding="utf-8")

        # 使用 yaml.dump 序列化整个 memory 结构，避免正则替换脆弱性
        memory_yaml = yaml.dump(
            self.memory,
            default_flow_style=False,
            allow_unicode=True,
            sort_keys=False,
        )

        # 找到 yaml 代码块的起止边界并完整替换
        fence_start = "```yaml\n"
        fence_end = "\n```"
        start_idx = content.find(fence_start)
        if start_idx != -1:
            # 找到 fence_start 之后的第一个 fence_end
            after_start = start_idx + len(fence_start)
            end_idx = content.find(fence_end, after_start)
            if end_idx != -1:
                content = (
                    content[:start_idx]
                    + fence_start
                    + memory_yaml.strip()
                    + content[end_idx:]
                )

        path.write_text(content, encoding="utf-8")

    def _compose_system_messages(self, context: dict) -> list[dict]:
        """[Phase B 兼容] 仍保留方法签名供过渡期，但不再使用。
        所有 LLM 调用点已改为 project_ctx.to_messages_for_llm()。
        """
        return []

    def run_step(self, context: dict, df: pd.DataFrame | None = None, user_input: str = "") -> dict:
        """单步执行：跑 1 轮 LLM，处理 tool_calls。

        Phase B: messages 不再外部传入——由 project_ctx.to_messages_for_llm() 统一构建。
        """
        import json as _json
        from hagoku.tools.registry import agent_tools as _agt
        from hagoku.context.project_context import ToolCallRecord
        from ...llm.client import create_raw_client

        if df is None:
            df = getattr(self, '_df', None)
        client = create_raw_client(self.llm_config)
        _tools = _agt.to_openai("analyst")

        project_ctx = context.get("_project_context")
        if project_ctx is None:
            raise RuntimeError("Analyst.run_step: _project_context 未设置，信息通道断裂")

        agent_extra = getattr(self, 'prompt', '')
        messages = project_ctx.to_messages_for_llm(
            "analyst", context, user_input,
            agent_system_extra=agent_extra,
        )

        # ── LLM dump（CH-4 观察通道）──
        from ...observability.llm_dump import dump_messages
        dump_messages(
            "analyst_run_step",
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

        # ── Response dump ──
        dump_messages(
            "analyst_run_step_response",
            messages + [{"role": "assistant", "content": txt,
             "tool_calls": [{"function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                            for tc in (tc_list or [])] if tc_list else None}],
            model=self.llm_config.model,
        )

        # 写回 ProjectContext
        project_ctx.add_agent_response("analyst", context.get("interaction_revision", 0), txt or "(tool calls)")

        findings = None
        route_to_args = None

        if tc_list:
            tool_records = []
            for tc in tc_list:
                fn = tc.function
                try:
                    args = _json.loads(fn.arguments) if fn.arguments else {}
                except (_json.JSONDecodeError, TypeError):
                    continue
                if fn.name == "submit_analysis":
                    findings = _agt.dispatch(fn.name, args, context, df)
                    break
                if fn.name == "route_to":
                    route_to_args = _agt.dispatch(fn.name, args, context, df)
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
                project_ctx.add_tool_exchange("analyst", context.get("interaction_revision", 0), tool_records,
                                              assistant_content=txt)

        return {
            "text": txt,
            "submit_analysis": findings is not None,
            "findings": findings,
            "route_to": route_to_args,
        }

