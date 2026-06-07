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

        # 交互状态
        self._phase = "begin"
        self._df: pd.DataFrame | None = None
        self._context: dict | None = None
        self._plan: dict[str, Any] = {}
        self._preliminary_results: dict | None = None

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

    def run_step(self, messages: list[dict], context: dict, df: pd.DataFrame | None = None) -> dict:
        """单步执行：跑 1 轮 LLM，处理 tool_calls，返回 (messages, findings or None)"""
        import json as _json
        from hagoku.tools.registry import agent_tools as _agt
        from ...llm.client import create_raw_client

        if df is None:
            df = getattr(self, '_df', None)
        client = create_raw_client(self.llm_config)
        _tools = _agt.to_openai("analyst")

        resp = client.chat.completions.create(
            model=self.llm_config.model, messages=messages,
            temperature=0.3, max_tokens=4096, tools=_tools, tool_choice="auto",
        )
        msg = resp.choices[0].message
        txt = (msg.content or "").strip()
        tc_list = getattr(msg, "tool_calls", None)
        findings = None

        if tc_list:
            tool_results = []
            for tc in tc_list:
                fn = tc.function
                args = _json.loads(fn.arguments) if fn.arguments else {}
                result = _agt.dispatch(fn.name, args, context, df)
                if fn.name == "submit_analysis":
                    findings = result
                    break
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
        }

    def _emit(self, event_type: EventType, data: dict | None = None) -> None:
        self.event_bus.emit(event_type=event_type, agent=self.role, data=data or {})

    # ── 核心逻辑 ────────────────────────────────────────────

    def run(
        self,
        df: pd.DataFrame,
        context: dict,
        plan: dict | None = None,
        project_id: str | None = None,
        phase: str = "full",
        *,
        emit_completed: bool = True,
    ) -> dict:
        # F-083/F-084: 旧对话式入口（30 轮循环）。事件驱动架构使用 run_step()。
        # 仅保留供 begin() → respond() 旧交互路径使用，长期应迁移到 run_step()。
        """对话式分析循环。LLM 自由探索，submit_analysis 工具退出。

        将 plan 参数改为可选（兼容旧调用方）。分析不再走 JSON 计划路径，
        而是 through LLM 对话 + 工具调用。
        """
        import json as _json
        from hagoku.tools.registry import agent_tools as _agt

        self._emit(EventType.AGENT_STARTED, {"goal": "对话式数据分析"})

        query = context.get("query", "") or context.get("analysis_goal", "")
        project_ctx = context.get("_project_context")
        _tools = _agt.to_openai("analyst")

        # 拼 system prompt
        system = (
            "你是专业数据分析师。可以用工具探索数据、跑统计检验、向用户提问、提议分析方法。\n"
            "每次集中做一个操作，用清晰的文字配合工具输出。\n"
            "想给用户多选题时用 ask_user 工具，开放式讨论用纯文本。\n"
            "方法建议用 propose_method 工具。\n"
            "准备好了就调 submit_analysis 提交分析发现，结束分析。\n"
            "confidence 取 high/medium/low 三选一。\n"
        )

        system += (
            "\n\n"
            "【分析范围解锁】\n"
            "分析开始时已设定核心关注字段。如果用户要求纳入新字段，先调 get_column_stats 检查数据质量。\n"
            "根据 get_column_stats 返回的空值率和数据类型，自行判断数据质量是否满足分析要求。\n"
            "数据可用 → 调 update_analysis_scope 纳入。\n"
            "数据质量问题严重 → 告知用户具体问题（空值率、类型不匹配等），建议重置分析从字段理解阶段重跑。若用户坚持纳入，回复「不管，直接加」。」\n"
        )

        if project_ctx:
            ctx_block = project_ctx.build_prompt("analyst", context)
            system += "\n\n" + ctx_block["system_prefix"] + "\n\n" + ctx_block["upstream_summary"]

        messages: list[dict] = [{"role": "system", "content": system}]
        if project_ctx:
            # F-085: 旧 session 的 tool_call_id 在新 session 无效（OpenAI 协议绑定），
            # 但丢弃消息会让 LLM 丢失工具调用上下文。此处将 tool 消息和含 tool_calls
            # 的 assistant 消息转为可读摘要，让 LLM 知道历史中发生了什么。
            history_lines: list[str] = []
            tool_results_log: list[str] = []
            for m in ctx_block.get("messages_history", []):
                role = m.get("role", "")
                if role == "tool":
                    content = m.get("content", "")
                    if content:
                        # 截断长工具输出，保留关键信息
                        short = content[:200].replace("\n", " ")
                        tool_results_log.append(f"  → 结果: {short}")
                    continue
                if role == "assistant" and m.get("tool_calls"):
                    tool_names = [
                        tc.get("function", {}).get("name", "?")
                        for tc in m.get("tool_calls", [])
                    ]
                    tool_results_log.append(f"[调用了 {'、'.join(tool_names)}]")
                    continue
                messages.append(m)
            if tool_results_log:
                summary = "【上轮分析工具调用摘要】\n" + "\n".join(tool_results_log[-20:])
                history_lines.append(summary)
            if history_lines:
                messages.insert(1, {"role": "system", "content": "\n".join(history_lines)})

        intro = f"分析目标：{query}\n可用列：{', '.join(df.columns)}\n数据行数：{len(df)}"
        messages.append({"role": "user", "content": intro})

        from ...llm.client import create_raw_client
        client = create_raw_client(self.llm_config)

        # F-086: 轮数上限依据——典型分析场景（探索→检验→结论）通常 8-15 轮，
        # 30 轮提供 2x 安全余量。LLM 未在时限内调 submit_analysis 时硬中断。
        max_rounds = int(getattr(self.llm_config, 'analyst_max_rounds', None) or 30)
        warn_at = max_rounds - 5
        for round_idx in range(max_rounds):
            if round_idx >= warn_at:
                messages.append({"role": "system", "content": "（已分析多轮，请准备 submit_analysis 提交发现）"})

            resp = client.chat.completions.create(
                model=self.llm_config.model, messages=messages,
                temperature=0.3, max_tokens=4096, tools=_tools, tool_choice="auto",
            )
            msg = resp.choices[0].message
            txt = (msg.content or "").strip()
            tc_list = getattr(msg, "tool_calls", None)
            findings = None

            if tc_list:
                tool_call_blocks = []
                tool_results: list[dict] = []
                for tc in tc_list:
                    fn = tc.function
                    try:
                        args = _json.loads(fn.arguments) if fn.arguments else {}
                    except _json.JSONDecodeError:
                        continue
                    result = _agt.dispatch(fn.name, args, context, df)

                    if fn.name == "submit_analysis":
                        findings = result
                        break

                    tc_id = getattr(tc, "id", "") or ""
                    tool_call_blocks.append({
                        "id": tc_id, "type": "function",
                        "function": {"name": fn.name, "arguments": fn.arguments},
                    })
                    tool_results.append({
                        "role": "tool", "tool_call_id": tc_id,
                        "content": _json.dumps(result, ensure_ascii=False, default=str),
                    })

                if findings is not None:
                    break

                if tool_call_blocks:
                    assistant_block: dict = {"role": "assistant", "content": txt or None}
                    assistant_block["tool_calls"] = tool_call_blocks
                    messages.append(assistant_block)
                    messages.extend(tool_results)
            elif txt:
                messages.append({"role": "assistant", "content": txt})

            # ProjectContext 写入（每轮）
            if project_ctx:
                project_ctx.add_agent_response(
                    stage="analyst", revision=round_idx,
                    content=txt or "[工具调用]",
                    snapshot=project_ctx._derive_snapshot(context),
                )

        if findings is None:
            raise RuntimeError(f"Analyst: {max_rounds} 轮未提交 submit_analysis，分析中断")

        if findings:
            context["findings"] = findings

        self._emit(EventType.AGENT_COMPLETED, {
            "result_summary": findings.get("summary", ""),
        })
        return findings


    def begin(  # type: ignore[override]
        self,
        df: pd.DataFrame,
        context: dict,
        plan: dict,
    ) -> InteractionResult:
        """
        开始 Analyst 交互。

        流程：执行分析 → 确认结果 → 完成
        """
        self._df = df
        self._context = context
        self._plan = plan

        self._emit(EventType.AGENT_STARTED, {"goal": "用统计方法挖出数据真相"})

        try:
            # 运行完整分析
            results, business_metrics = self.run(df, context, plan)
            self._phase = "next_step"

            n_sig = sum(1 for r in results if r.get("significance") == "significant")
            summary = f"完成 {len(results)} 项分析，{n_sig} 项显著发现"

            # block，等用户确认进入下一步
            if self.orchestrator:
                self.orchestrator.block_task("analyst", "等用户确认进入报告阶段")

            return self._pause(
                phase="next_step",
                message=summary + "\n\n建议进入「报告阶段」，是否确认？",
                actions=["生成报告", "继续分析", "结束分析"],
                pending_items=[],
                data={
                    "n_results": len(results),
                    "n_significant": n_sig,
                    "business_metrics": len(business_metrics),
                    "results_preview": results[:3],
                },
            )

        except Exception as e:
            self._emit(EventType.AGENT_FAILED, {"error": str(e)})
            raise RuntimeError(f"Analyst 通道失败：{e}") from e

    def respond(  # type: ignore[override]
        self,
        user_input: dict,
    ) -> InteractionResult:
        """
        处理用户对分析结果的响应。
        """
        if self._phase != "next_step":
            return self._done("done", "阶段错误，请重新开始", {})

        action = user_input.get("action", "")
        if action == "生成报告":
            if self.orchestrator:
                self.orchestrator.unblock_task("analyst")
            return self._pause(
                phase="next_step",
                message="正在进入报告阶段...",
                actions=[],
                pending_items=[],
                data={"proceed_to": "reporter"},
            )
        elif action == "继续分析":
            if self.orchestrator:
                self.orchestrator.unblock_task("analyst")
            # 重新执行分析
            return self.begin(self._df, self._context, self._plan)  # type: ignore[arg-type]
        else:
            if self.orchestrator:
                self.orchestrator.unblock_task("analyst")
            return self._done("done", "分析已结束", {})

