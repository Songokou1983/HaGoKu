"""
DataAnalystAgent — 唯一数据分析师（Phase D：4 agent 合 1）

从 agents/prompt.md 读取统一 prompt（4 关注点），
所有工具对 LLM 可见，LLM 通过 route_to 声明关注点切换。
"""

from __future__ import annotations

import json as _json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from hagoku.config import LLMConfig
from hagoku.observability.event_bus import EventBus
from hagoku.observability.events import EventType
from hagoku.context.project_context import ToolCallRecord
from hagoku.agents.base import BaseAgent
from hagoku.agents.constants import (
    SCOUT_INFER_MAX_TOKENS,
    SCOUT_INFER_TEMPERATURE,
    SCOUT_LABEL_PREVIEW_LEN,
    SCOUT_LABEL_TRUNCATE_LEN,
    SCOUT_TOP_VALUES_MAX_UNIQUE,
)

logger = logging.getLogger("hagoku.agent")


# ── 模块级工具（从 scout 迁入，D7 删 scout/ 后无需改 import）─────────

def _format_sample_preview(df: pd.DataFrame, col: str, *, limit: int = 5) -> str:
    """提取样本值直白串，不做格式判断——让 LLM 自行理解。"""
    try:
        vals = df[col].dropna().unique()
    except Exception:
        return ""
    if len(vals) == 0:
        return ""
    return ", ".join(str(v).strip() for v in vals[:limit])


class DataAnalystAgent(BaseAgent):
    """数据分析师 — 唯一 agent。

    一套 chat、一套 prompt、全部工具可见。
    LLM 自己按 4 个关注点（理解字段/评估清洗/跑统计/写报告）切换焦点，
    通过 route_to 声明 phase tag。
    """

    ROLE = "analyst"

    def __init__(
        self,
        llm_config: LLMConfig,
        event_bus: EventBus,
        orchestrator: Any | None = None,
        llm_client: Any | None = None,
    ) -> None:
        super().__init__(llm_config=llm_config, event_bus=event_bus,
                         orchestrator=orchestrator, llm_client=llm_client)
        self._context: dict | None = None
        self._df: pd.DataFrame | None = None

    # ── prompt ──────────────────────────────────────────────────────

    def _load_prompt(self) -> str:
        p = Path(__file__).parent / "prompt.md"
        if p.exists():
            return p.read_text(encoding="utf-8")
        return ""

    # ═══════════════════════════════════════════════════════════════
    # 关注点 1：理解字段（从 scout 迁入）
    # ═══════════════════════════════════════════════════════════════

    def run_scout_phase(
        self,
        data_path: str,
        query: str = "",
        project_id: str | None = None,
        memory_project: dict | None = None,
    ) -> dict:
        """执行「理解字段」关注点——加载数据、画像、推断语义、构建上下文。

        Phase D: 从 scout.run() 整体迁入。替代 orchestrator 中 scout.run() 调用。
        """
        from hagoku.tools.data_io import load_data
        from hagoku.tools.profiling import generate_profile

        self._emit(EventType.AGENT_STARTED, {"goal": "理解数据字段和质量问题"})
        try:
            df = load_data(data_path)
            self._emit(EventType.TOOL_CALLED, {"tool": "load_data", "args_summary": data_path})
            self._emit(EventType.TOOL_RESULT, {"summary": f"加载成功: {len(df)} 行, {len(df.columns)} 列"})
            self._df = df

            self._emit(EventType.AGENT_THINKING, {"thought": "生成数据画像..."})
            profile = generate_profile(df)
            self._emit(EventType.TOOL_RESULT, {"summary": f"质量={profile['quality_score']:.0%}"})

            column_semantics = self.infer_field_semantics(df, query, memory_project)

            context = {
                "data_path": data_path,
                "query": query,
                "n_rows": len(df),
                "n_cols": len(df.columns),
                "column_semantics": column_semantics,
                "quality_score": profile["quality_score"],
                "missing_summary": profile.get("missing_summary", {}),
                "warnings": [],
                "column_descriptions": {},
            }
            context["_scout_conclusions"] = {
                "participating": [s["column_name"] for s in column_semantics if s.get("used_in_analysis")],
                "excluded": [s["column_name"] for s in column_semantics if s.get("used_in_analysis") is False],
            }

            # 项目记忆 / 角色派生 / 质量警告 / 描述生成 / 学习 / 写记忆
            # Phase D 过渡期：留在 scout 模块（D7 一并迁移）
            from hagoku.agents.scout.agent import ScoutAgent as _ScoutRef
            _tmp = _ScoutRef.__new__(_ScoutRef)
            _tmp.llm_config = self.llm_config
            _tmp.event_bus = self.event_bus
            _tmp.orchestrator = self.orchestrator
            if memory_project and project_id:
                _tmp._apply_project_memory(context, memory_project)
            _tmp._derive_roles(context)

            if profile.get("duplicate_rate", 0) > 0.05:
                context["warnings"].append(f"重复行率 {profile['duplicate_rate']:.1%} 较高")
            if profile.get("missing_summary", {}).get("null_rate", 0) > 0.1:
                context["warnings"].append(f"缺失率 {profile['missing_summary']['null_rate']:.1%} 较高")

            _tmp._generate_field_descriptions(context, df)
            _tmp._learn_from_results(context, project_id)
            _tmp._update_own_memory(context, project_id)

            self._emit(EventType.AGENT_COMPLETED, {
                "result_summary": f"理解 {len(context['column_semantics'])} 个字段"
            })
            self._context = context
            return context

        except FileNotFoundError:
            self._emit(EventType.AGENT_FAILED, {"error": "数据文件未找到"})
            return {"error": "数据文件未找到"}
        except Exception as e:
            self._emit(EventType.AGENT_FAILED, {"error": str(e)})
            return {"error": str(e)}

    def infer_field_semantics(
        self,
        df: pd.DataFrame,
        query: str,
        memory_project: dict | None = None,
    ) -> list[dict]:
        """字段语义推断 — 从 scout._infer_all_semantics 整体迁入。

        Phase D: 整体搬迁，不重写。D7 删 scout/ 后此方法独立存在。
        """
        from hagoku.llm.client import create_raw_client
        from hagoku.channel import build_messages
        from hagoku.agents.types import build_submit_field_inference_schema

        # 构建每列的 profile 摘要
        column_list: list[dict] = []
        for col in df.columns:
            p = self._profile_column(df[col], col, df)
            sample_vals = _format_sample_preview(df, col, limit=5)
            column_list.append({
                "name": col, "dtype": p.get("dtype", "object"),
                "n_unique": p.get("n_unique", 0), "n_total": p.get("n_total", 0),
                "null_pct": p.get("null_pct", 0),
                "sample_values": sample_vals if sample_vals else "",
                "top_values": p.get("top_values", {}),
                "min": p.get("min"), "max": p.get("max"),
                "mean": p.get("mean"), "median": p.get("median"),
                "q25": p.get("q25"), "q75": p.get("q75"),
                "distribution_summary": p.get("distribution_summary", ""),
                "time_min": p.get("time_min"), "time_max": p.get("time_max"),
            })

        payload = {"user_query": query, "n_rows": len(df), "n_cols": len(df.columns), "columns": column_list}

        memory_notes = ""
        if memory_project:
            fields = memory_project.get("fields", {})
            display_names = memory_project.get("display_names", {})
            if fields or display_names:
                lines = ["\n\n【项目记忆 — 以下是历史分析中的字段记录，请沿用其中文名称和业务含义；但字段角色（target/feature/ignore）需根据当前分析目标重新判断：】"]
                for col, desc in fields.items():
                    dn = display_names.get(col, "")
                    if dn:
                        lines.append(f"  - {col}: 中文名称「{dn}」，含义：{desc}")
                    else:
                        lines.append(f"  - {col}: 含义：{desc}")
                memory_notes = "\n".join(lines)

        command_context = ""
        try:
            ctx = getattr(self, "_context", {}) or {}
            pt = (ctx.get("_pending_command_text") or "").strip()
            if pt:
                command_context = f"\n\n【用户最近提出的指令/纠正（必须采纳并执行，优先级高于其他所有信息）：】\n{pt}"
        except Exception:
            pass

        _schema = build_submit_field_inference_schema()
        submit_tool = {
            "type": "function",
            "function": {
                "name": "submit_field_inference",
                "description": "提交字段语义推断结果。",
                "parameters": _schema,
            }
        }

        analysis_goal_line = ""
        if query and query.strip():
            analysis_goal_line = (
                f"\n\n【最高优先级 — 用户分析目标】\n「{query.strip()}」\n\n"
                "给每个字段翻译一个中文名。现在调用 submit_field_inference。\n"
            )

        system_prompt = (
            "直接调用 submit_field_inference，给每个字段一个中文名。不要做其他操作。\n"
            "建议角色：与目标直接相关的字段→target/feature，无关的→ignore。\n"
            f"{analysis_goal_line}{memory_notes}{command_context}"
        )
        user_prompt_str = _json.dumps(payload, ensure_ascii=False, default=str)

        client = create_raw_client(self.llm_config)
        self._emit(EventType.AGENT_THINKING, {"thought": "正在推理字段语义..."})

        from hagoku.observability.llm_dump import dump_messages
        dump_messages(
            "agent_infer_field_semantics",
            [{"role": "system", "content": system_prompt},
             {"role": "user", "content": "请分析以下数据集的字段语义：\n```json\n" + user_prompt_str + "\n```"}],
            model=self.llm_config.model,
            extra={"query": query, "tools": ["submit_field_inference"]},
        )

        try:
            ctx = self._context or {}
            project_ctx = ctx.get("_project_context")
            if project_ctx:
                messages = project_ctx.to_messages_for_llm(
                    "scout", {"query": query, "column_semantics": []},
                    f"请分析以下数据集的字段语义：\n```json\n{user_prompt_str}\n```",
                    agent_system_extra=system_prompt,
                )
            else:
                messages = build_messages(
                    query=query or "",
                    user_input=f"请分析以下数据集的字段语义：\n```json\n{user_prompt_str}\n```",
                    system_extra=system_prompt,
                )
            response = client.chat.completions.create(
                model=self.llm_config.model,
                messages=messages,
                temperature=SCOUT_INFER_TEMPERATURE,
                max_tokens=SCOUT_INFER_MAX_TOKENS,
                tools=[submit_tool],
                tool_choice={"type": "function", "function": {"name": "submit_field_inference"}},
            )
        except Exception as e:
            raise RuntimeError(f"字段推断失败：LLM 不可达，请检查 API 配置。原始错误: {e}") from e

        raw_text = response.choices[0].message.content or ""
        import re as _re
        raw_text = _re.sub(r"<think>.*?</think>", "", raw_text, flags=_re.DOTALL).strip()
        tool_calls = response.choices[0].message.tool_calls

        tc = tool_calls or []
        dump_messages(
            "agent_infer_field_semantics_response",
            [{"role": "assistant", "content": raw_text,
              "tool_calls": [{"function": {"name": t.function.name, "arguments": t.function.arguments}} for t in tc]}],
            model=self.llm_config.model,
        )

        results: list[dict] = []
        if tool_calls:
            for t in tool_calls:
                if t.function.name == "submit_field_inference":
                    try:
                        args = _json.loads(t.function.arguments)
                        for col_data in args.get("columns", []):
                            col_data["column_name"] = col_data.get("name", col_data.get("column_name", ""))
                            col_data.setdefault("used_in_analysis", True)
                            col_data.setdefault("needs_user_input", col_data.get("confidence", 1.0) < 0.8)
                            results.append(col_data)
                    except (_json.JSONDecodeError, TypeError):
                        pass
        if not results:
            try:
                parsed = _json.loads(raw_text)
                if isinstance(parsed, dict) and "columns" in parsed:
                    for col_data in parsed["columns"]:
                        col_data["column_name"] = col_data.get("name", col_data.get("column_name", ""))
                        col_data.setdefault("used_in_analysis", True)
                        col_data.setdefault("needs_user_input", col_data.get("confidence", 1.0) < 0.8)
                        results.append(col_data)
            except (_json.JSONDecodeError, TypeError):
                pass

        return results

    def _profile_column(self, series: pd.Series, name: str, df: pd.DataFrame) -> dict:
        """对单列做数据画像（从 scout._profile_column 迁入）。"""
        n_total = len(series)
        n_null = int(series.isna().sum())
        n_unique = series.nunique()
        profile: dict[str, Any] = {
            "column_name": name, "dtype": str(series.dtype),
            "n_total": n_total, "n_null": n_null,
            "null_pct": round(n_null / n_total, 4) if n_total > 0 else 0,
            "n_unique": n_unique,
        }
        if pd.api.types.is_numeric_dtype(series):
            non_null = series.dropna()
            if len(non_null) > 0:
                profile.update({
                    "min": float(non_null.min()) if hasattr(non_null, "min") else None,
                    "q25": float(non_null.quantile(0.25)),
                    "median": float(non_null.median()),
                    "q75": float(non_null.quantile(0.75)),
                    "max": float(non_null.max()) if hasattr(non_null, "max") else None,
                    "mean": round(float(non_null.mean()), 4),
                    "std": round(float(non_null.std()), 4),
                })
                parts: list[str] = []
                for key in ["min", "q25", "median", "q75", "max"]:
                    v = profile.get(key)
                    if v is not None:
                        parts.append(f"{v:.6g}" if isinstance(v, float) else str(v))
                    else:
                        parts.append("-")
                profile["distribution_summary"] = " ~ ".join(parts)
        if n_unique < SCOUT_TOP_VALUES_MAX_UNIQUE and n_unique > 0:
            vc = series.value_counts().head(5)
            profile["top_values"] = {str(v)[:SCOUT_LABEL_TRUNCATE_LEN]: int(c) for v, c in vc.items()}
        if pd.api.types.is_datetime64_any_dtype(series):
            non_null = series.dropna()
            if len(non_null) > 0:
                profile["time_min"] = str(non_null.min())
                profile["time_max"] = str(non_null.max())
        return profile

    # ═══════════════════════════════════════════════════════════════
    # 关注点 2：评估清洗（从 cleaner 委托）
    # ═══════════════════════════════════════════════════════════════

    def assess(self, df: pd.DataFrame, context: dict, cleaning_rules: str = "") -> dict:
        """评估清洗需求 — Phase D 委托 CleanerAgent.assess。D7 后内联。"""
        from hagoku.agents.cleaner import CleanerAgent
        c = CleanerAgent(self.llm_config, self.event_bus, llm_client=None)
        return c.assess(df, context, cleaning_rules)

    def _load_cleaning_rules(self) -> str:
        from hagoku.agents.cleaner import CleanerAgent
        return CleanerAgent._load_cleaning_rules(CleanerAgent.__new__(CleanerAgent))

    # ═══════════════════════════════════════════════════════════════
    # 通用：run_step（Phase B/C 接口）
    # ═══════════════════════════════════════════════════════════════

    def run_step(
        self,
        context: dict,
        df: pd.DataFrame | None = None,
        user_input: str = "",
    ) -> dict:
        """单步执行：跑 1 轮 LLM，处理 tool_calls。

        Phase D：统一 tool dispatch。
        """
        from hagoku.tools.registry import agent_tools as _agt
        from hagoku.llm.client import create_raw_client

        if df is None:
            df = getattr(self, '_df', None)
        client = create_raw_client(self.llm_config)
        _tools = _agt.to_openai()  # Phase D: 全集，不再按 agent 过滤

        project_ctx = context.get("_project_context")
        if project_ctx is None:
            raise RuntimeError("DataAnalystAgent.run_step: _project_context 未设置")

        phase_hint = context.get("_current_phase", "")
        agent_extra = self.prompt
        if phase_hint:
            agent_extra = f"【当前关注点：{phase_hint}】\n\n" + agent_extra

        messages = project_ctx.to_messages_for_llm(
            "analyst", context, user_input,
            agent_system_extra=agent_extra,
        )

        from hagoku.observability.llm_dump import dump_messages
        dump_messages("agent_run_step", messages, model=self.llm_config.model,
                      extra={"tools": [t["function"]["name"] for t in _tools]})

        resp = client.chat.completions.create(
            model=self.llm_config.model, messages=messages,
            temperature=0.3, max_tokens=4096, tools=_tools, tool_choice="auto",
        )
        msg = resp.choices[0].message
        txt = (msg.content or "").strip()
        tc_list = getattr(msg, "tool_calls", None)

        dump_messages("agent_run_step_response",
            messages + [{"role": "assistant", "content": txt,
             "tool_calls": [{"function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                            for tc in (tc_list or [])] if tc_list else None}],
            model=self.llm_config.model)

        revision = context.get("interaction_revision", 0)
        project_ctx.add_agent_response("analyst", revision, txt or "(tool calls)")

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
                if fn.name == "submit_report":
                    # reporter 的 submit_report — 返回报告参数
                    findings = _agt.dispatch(fn.name, args, context, df)
                    continue
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
                project_ctx.add_tool_exchange("analyst", revision, tool_records, assistant_content=txt)

        return {
            "text": txt, "route_to": route_to_args,
            "submit_analysis": findings is not None, "findings": findings,
            "submit_assessment": assessment is not None, "assessment": assessment,
        }
