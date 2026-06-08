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
from .._interactive import InteractionMixin
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


class AnalystAgent(InteractionMixin):
    """数理分析员：用统计方法挖出数据背后的真相"""

    # ── 分析方法注册表（P1.1 修复：支持 LLM 动态扩展分析类型） ──
    def __init__(
        self,
        llm_config: LLMConfig,
        event_bus: EventBus,
        orchestrator: Any | None = None,
        llm_client: Any | None = None,
    ) -> None:
        self.role = "analyst"
        self.llm_config = llm_config
        self.event_bus = event_bus
        self.orchestrator = orchestrator  # 看板 block/unblock 通过 orchestrator 走
        self._llm_client = llm_client  # 外部传入的 LLM 客户端（双层策略用）

        self.prompt = self._load_prompt()
        self.memory = self._load_memory()
        self.guardrails = StatisticalGuardrails()

    def _load_prompt(self) -> str:
        path = Path(__file__).parent / "prompt.md"
        if path.exists():
            return path.read_text(encoding="utf-8")
        return ""

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
        """拼装 system prompt 头部消息。

        包含：
        1. prompt.md 内容（Analyst 角色定义、能力、工具使用说明）
        2. ProjectContext 上下文（分析目标、字段状态、上游摘要）

        每次调用重拼，不永久存储到对话历史中。
        """
        system_msgs: list[dict] = []

        # 1. prompt.md 作为第一条 system 消息
        prompt = getattr(self, 'prompt', '')
        if prompt:
            system_msgs.append({"role": "system", "content": prompt})

        # 2. ProjectContext 上下文注入
        project_ctx = context.get("_project_context")
        if project_ctx:
            ctx_block = project_ctx.build_prompt("analyst", context)
            parts: list[str] = []
            if ctx_block.get("system_prefix"):
                parts.append(ctx_block["system_prefix"])
            if ctx_block.get("upstream_summary"):
                parts.append(ctx_block["upstream_summary"])
            if parts:
                system_msgs.append({"role": "system", "content": "\n\n".join(parts)})

        return system_msgs

    def run_step(self, messages: list[dict], context: dict, df: pd.DataFrame | None = None) -> dict:
        """单步执行：跑 1 轮 LLM，处理 tool_calls，返回 (messages, findings or None)

        messages 视为对话历史（仅含 user/assistant/tool 角色）；
        每次调用前重新拼装 system prompt 头部，确保 LLM 不失明。
        """
        import json as _json
        from hagoku.tools.registry import agent_tools as _agt
        from ...llm.client import create_raw_client

        if df is None:
            df = getattr(self, '_df', None)
        client = create_raw_client(self.llm_config)
        _tools = _agt.to_openai("analyst")

        # 拼装 system prompt 头部（每次重拼，不永久存储到 messages）
        composed = self._compose_system_messages(context) + messages

        # 确保至少有一条 user 消息（部分 API 如 MiniMax 要求非空 user content）
        if not any(m.get("role") == "user" for m in composed):
            intro = f"分析目标：{context.get('query', '') or context.get('analysis_goal', '数据分析')}"
            composed.append({"role": "user", "content": intro})

        resp = client.chat.completions.create(
            model=self.llm_config.model, messages=composed,
            temperature=0.3, max_tokens=4096, tools=_tools, tool_choice="auto",
        )
        msg = resp.choices[0].message
        txt = (msg.content or "").strip()
        tc_list = getattr(msg, "tool_calls", None)
        findings = None
        route_to_args = None

        if tc_list:
            tool_results = []
            for tc in tc_list:
                fn = tc.function
                args = _json.loads(fn.arguments) if fn.arguments else {}
                result = _agt.dispatch(fn.name, args, context, df)
                if fn.name == "submit_analysis":
                    findings = result
                    break
                if fn.name == "route_to":
                    route_to_args = result
                tc_id = getattr(tc, "id", "") or ""
                tool_results.append({
                    "role": "tool", "tool_call_id": tc_id,
                    "content": _json.dumps(result, ensure_ascii=False, default=str),
                })
            if tool_results:
                assistant_block = {"role": "assistant", "content": txt or None}
                assistant_block["tool_calls"] = [
                    {"id": getattr(tc, "id", ""), "type": "function",
                     "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                    for tc in tc_list if getattr(tc, "function", None)
                ]
                messages.append(assistant_block)
                messages.extend(tool_results)
        elif txt:
            messages.append({"role": "assistant", "content": txt})

        return {
            "messages": messages,
            "text": txt,
            "submit_analysis": findings is not None,
            "findings": findings,
            "route_to": route_to_args,
        }

    def _emit(self, event_type: EventType, data: dict | None = None) -> None:
        self.event_bus.emit(event_type=event_type, agent=self.role, data=data or {})

