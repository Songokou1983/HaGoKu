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


def _description_is_user_facing_meaningful(col_name: str, desc: str) -> bool:
    """检查描述是否提供了超出列名本身的结构性信息（从 scout/agent.py 迁入）。"""
    d = (desc or "").strip()
    if not d:
        return False
    if d == col_name:
        return False
    prefix = col_name + "（"
    if d.startswith(prefix) and d.endswith("）"):
        return False
    return True


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

        # CO-26: 设置 role 供 Pipeline 兜底（agent_started 无 agent 时前端回退用）
        self.role = "scout"

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
                "_column_info": {c: str(df[c].dtype) for c in df.columns},
            }
            # 传播 ask_user 到 orchestrator
            agent_ctx = self._context or {}
            if agent_ctx.get("_pending_ask_user"):
                context["_pending_ask_user"] = agent_ctx["_pending_ask_user"]
            context["_scout_conclusions"] = {
                "participating": [],
                "excluded": [],
            }
            if column_semantics and "column_name" in column_semantics[0]:
                context["_scout_conclusions"] = {
                    "participating": [s["column_name"] for s in column_semantics if s.get("used_in_analysis")],
                    "excluded": [s["column_name"] for s in column_semantics if s.get("used_in_analysis") is False],
                }

            # Phase D: 项目记忆 / 角色派生 / 质量警告
            if memory_project and project_id:
                self._apply_project_memory(context, memory_project)
            self._derive_roles(context)

            if profile.get("duplicate_rate", 0) > 0.05:
                context["warnings"].append(f"重复行率 {profile['duplicate_rate']:.1%} 较高")
            if profile.get("missing_summary", {}).get("null_rate", 0) > 0.1:
                context["warnings"].append(f"缺失率 {profile['missing_summary']['null_rate']:.1%} 较高")

            self._generate_field_descriptions(context, df)
            self._learn_from_results(context, project_id)
            self._update_own_memory(context, project_id)

            # 收口双写初始化：首次推断完成后同步旧字典，不等待用户第一次纠正
            from hagoku.manager.payloads.scout_payload import sync_legacy_dicts
            sync_legacy_dicts(context)

            self._emit(EventType.AGENT_COMPLETED, {
                "result_summary": f"理解 {len(context.get('_column_info', context['column_semantics']))} 个字段"
            })
            self._context = context
            return context

        except FileNotFoundError:
            self._emit(EventType.AGENT_FAILED, {"error": "数据文件未找到"})
            return {"error": "数据文件未找到"}
        # 其他异常（包括 LLM 不可达的 RuntimeError）不捕获，直接传播
        # 让调用方感知失败——Iron Law 7：失败在场

    def infer_field_semantics(
        self,
        df: pd.DataFrame,
        query: str,
        memory_project: dict | None = None,
    ) -> list[dict]:
        """字段语义推断 — 委托 run_step 统一路径。

        Phase D: 整体搬迁，不重写。D7 删 scout/ 后此方法独立存在。
        """
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
        user_content = f"请分析以下数据集的字段语义：\n```json\n{_json.dumps(payload, ensure_ascii=False, default=str)}\n```"

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
            actx = getattr(self, "_context", {}) or {}
            pt = (actx.get("_pending_command_text") or "").strip()
            if pt:
                command_context = f"\n\n【用户最近提出的指令/纠正（必须采纳并执行，优先级高于其他所有信息）：】\n{pt}"
        except Exception:
            actx = {}

        extra_prefix = ""
        if query and query.strip():
            extra_prefix += f"\n\n【用户分析目标】\n{query.strip()}\n"
        extra_prefix += memory_notes + command_context
        if extra_prefix.strip():
            user_content = extra_prefix + "\n" + user_content

        self._emit(EventType.AGENT_THINKING, {"thought": "正在推理字段语义..."})

        # ── 复用 run_step 统一路径（全量工具 + 流式 + 跟进轮）──
        project_ctx = (self._context or {}).get("_project_context")
        if project_ctx is None:
            raise RuntimeError(
                "infer_field_semantics: _project_context 未设置，无法构造 messages。"
                " 请检查 understand_data → _init_context 是否正确初始化了 ProjectContext。"
            )
        context = {
            "_project_context": project_ctx,
            "_current_stage": "scout",
            "query": query,
            "column_semantics": [],
            "_column_info": {c: str(df[c].dtype) for c in df.columns},
            "_pending_command_text": (actx.get("_pending_command_text") or "").strip() if actx else "",
        }
        result = self.run_step(context, df, user_content)
        raw_text = result.get("text", "")
        cs = context.get("column_semantics", [])
        if cs and any("column_name" in s for s in cs):
            return cs
        return [{"_scout_text": raw_text}]

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

    # ── Scout helper stubs（Phase E: ✅ 已实现）─────────

    def _apply_project_memory(self, context: dict, memory_project: dict) -> None:
        """应用项目记忆到 context — 预填充字段描述和中文名。"""
        fields = memory_project.get("fields", {})
        display_names = memory_project.get("display_names", {})
        if not fields and not display_names:
            return
        descriptions = context.get("column_descriptions", {})
        for col, desc in fields.items():
            if col not in descriptions:
                descriptions[col] = desc
        context["column_descriptions"] = descriptions
        if display_names:
            dnames = context.get("column_display_names", {})
            for col, dn in display_names.items():
                if col not in dnames:
                    dnames[col] = dn
            context["column_display_names"] = dnames

    def _derive_roles(self, context: dict) -> None:
        """从 column_semantics 派生 target/features。"""
        semantics = context.get("column_semantics", [])
        target = None
        features = []
        for s in semantics:
            role = s.get("suggested_role", "")
            if role == "target" and target is None:
                target = s["column_name"]
            elif role in ("feature", "target"):
                features.append(s["column_name"])
        if target:
            context["target"] = target
        context["features"] = features

    def _generate_field_descriptions(self, context: dict, df: pd.DataFrame) -> None:
        """从 column_semantics 同步旧字典（column_descriptions / column_display_names）。

        收口双写的初始化桥梁：Scout 首次推断完成后立刻调用，确保旧路径不为空，
        无需等待用户第一次纠正才触发 sync_legacy_dicts。
        """
        from hagoku.manager.payloads.scout_payload import sync_legacy_dicts
        sync_legacy_dicts(context)

    def _learn_from_results(self, context: dict, project_id: str | None) -> None:
        """从推断结果学习 — 将用户确认的字段理解保存为 lesson。"""
        semantics = context.get("column_semantics", [])
        confirmed = [s for s in semantics if s.get("confirmed_by_user")]
        if not confirmed or not project_id:
            return
        try:
            from hagoku.memory.lessons import LessonStore
            store = LessonStore()
            for s in confirmed:
                col = s.get("column_name", "")
                dn = s.get("display_name", "")
                desc = s.get("description", "")
                if col and (dn or desc):
                    store.save(
                        scenario=f"字段理解: {col}",
                        what_worked=f"用户确认 {col} 为「{dn or desc}」",
                        what_failed="",
                        lesson=f"项目 {project_id} 中，字段 {col} 的中文名为「{dn}」，含义：{desc}",
                    )
        except Exception:
            logger.debug("学习记录保存失败（非关键路径）", exc_info=True)

    def _update_own_memory(self, context: dict, project_id: str | None) -> None:
        """更新项目记忆 — 持久化字段描述供下次分析复用。"""
        if not project_id:
            return
        descriptions = context.get("column_descriptions", {})
        display_names = context.get("column_display_names", {})
        if not descriptions and not display_names:
            return
        try:
            from hagoku.memory.projects._manager import MemoryManager
            mm = context.get("_memory_manager")
            if mm is None:
                return
            mm.persist_field_descriptions(
                project_id, descriptions,
                column_display_names=display_names,
            )
        except Exception:
            logger.debug("项目记忆更新失败（非关键路径）", exc_info=True)

    # ═══════════════════════════════════════════════════════════════
    # 关注点 2：评估清洗
    # ═══════════════════════════════════════════════════════════════

    def assess(self, df: pd.DataFrame, context: dict) -> dict:
        """评估清洗需求——复用 run_step 统一路径。"""
        query = context.get("query", "") or context.get("analysis_goal", "")
        user_feedback = context.get("_user_feedback", "") or ""

        analysis_cols = {str(s["column_name"]) for s in context.get("column_semantics", [])
                         if s.get("used_in_analysis") is True}
        col_names = [c for c in df.columns if not analysis_cols or c in analysis_cols]

        project_ctx = context.get("_project_context")
        if project_ctx is None:
            raise RuntimeError("DataAnalystAgent.assess: _project_context 未设置")

        intro = f"【核心任务】根据分析目标评估每列是否需要清洗。\n分析目标：{query or '未指定'}\n可用列：{', '.join(col_names)}\n数据行数：{len(df)}"
        if user_feedback:
            intro += f"\n用户反馈：{user_feedback}"
        revision = context.get("interaction_revision", 0)
        project_ctx.add_user_feedback("cleaner", revision, raw_text=intro)

        context["_current_stage"] = "cleaner"
        context.setdefault("_column_info", {c: str(df[c].dtype) for c in df.columns})

        # 循环 run_step 直到 LLM 调 submit_assessment（最多 5 轮）
        result = self.run_step(context, df, "")
        if result.get("submit_assessment"):
            return result["assessment"]
        return {"summary": "", "columns": []}

    # ═══════════════════════════════════════════════════════════════
    # 通用：run_step（Phase B/C 接口）
    # ═══════════════════════════════════════════════════════════════

    def run_step(
        self,
        context: dict,
        df: pd.DataFrame | None = None,
        user_input: str = "",
        tools: list | None = None,
    ) -> dict:
        """单步执行：跑 1 轮 LLM，处理 tool_calls。

        Phase D：统一 tool dispatch。
        """
        from hagoku.tools.registry import agent_tools as _agt
        from hagoku.llm.client import create_raw_client

        if df is None:
            df = getattr(self, '_df', None)
        client = create_raw_client(self.llm_config)
        if tools is not None:
            _tools = [t for t in _agt.to_openai() if t["function"]["name"] in tools]
        else:
            _tools = _agt.to_openai()  # 全量工具

        project_ctx = context.get("_project_context")
        if project_ctx is None:
            raise RuntimeError("DataAnalystAgent.run_step: _project_context 未设置")

        agent_extra = self.prompt
        phase_hint = context.get("_current_stage", "")
        if phase_hint:
            stage_names = {"scout": "理解字段", "cleaner": "评估清洗", "analyst": "统计分析", "reporter": "撰写报告"}
            agent_extra = f"【当前关注点：{stage_names.get(phase_hint, phase_hint)}】\n\n" + agent_extra

        # P2: 字段元数据持久化——首轮后 context._column_info 注入 system prompt
        col_info = context.get("_column_info")
        if col_info:
            cols_str = ", ".join(f"{k}({v})" for k, v in col_info.items())
            agent_extra += f"\n数据集字段: {cols_str}\n"

        messages = project_ctx.to_messages_for_llm(
            "analyst", context, user_input,
            agent_system_extra=agent_extra,
        )

        from hagoku.observability.llm_dump import dump_messages
        dump_messages("agent_run_step", messages, model=self.llm_config.model,
                      extra={"tools": [t["function"]["name"] for t in _tools]})

        # CO-18: 流式路径 vs batch 回退
        use_stream = getattr(self.llm_config, "stream_enabled", True)
        txt = ""
        tc_list = None

        if use_stream:
            from hagoku.llm.client import stream_chat_completion
            from hagoku.llm.sanitize import stream_safe_append, strip_llm_think
            stream_id = _json.dumps({"ts": datetime.now(timezone.utc).isoformat()})
            full_text = ""
            safe_emitted = 0
            final_tool_calls_raw: list[dict] = []
            agent_key = phase_hint or "analyst"
            for chunk in stream_chat_completion(
                client, self.llm_config.model, messages,
                temperature=0.3, max_tokens=4096, tools=_tools,
            ):
                if chunk["type"] == "delta":
                    full_text, delta, safe_emitted = stream_safe_append(
                        full_text, chunk["content"], safe_emitted,
                    )
                    if delta:
                        self._emit(EventType.AGENT_STREAM_DELTA, {
                            "stream_id": stream_id, "delta": delta,
                            "agent": agent_key,
                        })
                elif chunk["type"] == "end":
                    full_text = chunk.get("content", full_text)
                    final_tool_calls_raw = chunk.get("tool_calls") or []
                    self._emit(EventType.AGENT_STREAM_END, {
                        "stream_id": stream_id, "agent": agent_key,
                    })
            txt = strip_llm_think(full_text).strip()
            # 将 stream 收集的 tool_calls 还原为 OpenAI 对象形式供后续 dispatch
            if final_tool_calls_raw:
                class _FakeTC:
                    def __init__(self, d):
                        self.id = d.get("id", "")
                        self.function = type("F", (), {
                            "name": d.get("function", {}).get("name", ""),
                            "arguments": d.get("function", {}).get("arguments", ""),
                        })()
                tc_list = [_FakeTC(tc) for tc in final_tool_calls_raw]
        else:
            resp = client.chat.completions.create(
                model=self.llm_config.model, messages=messages,
                temperature=0.3, max_tokens=4096, tools=_tools, tool_choice="auto",
            )
            msg = resp.choices[0].message
            from hagoku.llm.sanitize import strip_llm_think
            txt = strip_llm_think((msg.content or "")).strip()
            tc_list = getattr(msg, "tool_calls", None)

        dump_messages("agent_run_step_response",
            messages + [{"role": "assistant", "content": txt,
             "tool_calls": [{"function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                            for tc in (tc_list or [])] if tc_list else None}],
            model=self.llm_config.model)

        revision = context.get("interaction_revision", 0)
        stage = context.get("_current_stage", "analyst")
        project_ctx.add_agent_response(stage, revision, txt or "(tool calls)")

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
                if fn.name == "submit_findings":
                    findings = _agt.dispatch(fn.name, args, context, df)
                    continue
                if fn.name == "submit_assessment":
                    assessment = _agt.dispatch(fn.name, args, context, df)
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
                project_ctx.add_tool_exchange(stage, revision, tool_records, assistant_content=txt)

        # 工具调用后继续：循环直到 LLM 不再调工具
        # 工具调用后继续：让 LLM 看结果再回复
        if tc_list:
            msgs2 = project_ctx.to_messages_for_llm(
                stage, context, "",
                agent_system_extra=agent_extra,
            )
            resp2 = client.chat.completions.create(
                model=self.llm_config.model,
                messages=msgs2,
                temperature=0.3,
                max_tokens=4096,
                tools=_tools,
            )
            msg2 = resp2.choices[0].message
            txt = (msg2.content or "").strip()
            tc2 = getattr(msg2, "tool_calls", None)
            if tc2:
                recs2 = []
                for t in tc2:
                    fn = t.function
                    try:
                        a = _json.loads(fn.arguments) if fn.arguments else {}
                    except (_json.JSONDecodeError, TypeError):
                        continue
                    # 第二轮同样检测控制工具（与第一轮逻辑对齐）
                    if fn.name == "route_to":
                        route_to_args = _agt.dispatch(fn.name, a, context, df)
                        continue
                    if fn.name == "submit_findings":
                        findings = _agt.dispatch(fn.name, a, context, df)
                        continue
                    if fn.name == "submit_assessment":
                        assessment = _agt.dispatch(fn.name, a, context, df)
                        continue
                    try:
                        r = _agt.dispatch(fn.name, a, context, df)
                        recs2.append(ToolCallRecord(
                            tool_call_id=getattr(t, "id", "") or "",
                            name=fn.name, arguments=fn.arguments,
                            result=_json.dumps(r, ensure_ascii=False, default=str),
                        ))
                    except Exception as exc:
                        recs2.append(ToolCallRecord(
                            tool_call_id=getattr(t, "id", "") or "",
                            name=fn.name, arguments=fn.arguments,
                            result="", error=str(exc),
                        ))
                if recs2:
                    project_ctx.add_tool_exchange(stage, revision, recs2, assistant_content=txt)

        return {
            "text": txt, "route_to": route_to_args,
            "submit_findings": findings is not None, "findings": findings,
            "submit_assessment": assessment is not None, "assessment": assessment,
        }
