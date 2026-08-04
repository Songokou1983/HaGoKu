"""
DataAnalystAgent — 唯一数据分析师（Phase D：4 agent 合 1）

从 agents/prompt.md 读取统一 prompt，所有工具对 LLM 可见。
"""

from __future__ import annotations

import json as _json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from hagoku.agents.constants import (
    SCOUT_INFER_MAX_TOKENS,
    SCOUT_LABEL_TRUNCATE_LEN,
    SCOUT_TOP_VALUES_MAX_UNIQUE,
)
from hagoku.config import LLMConfig
from hagoku.context.session import ToolCallRecord
from hagoku.observability.event_bus import EventBus
from hagoku.observability.events import EventType

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


# ── 流式 tool_calls 还原辅助（从 run_step 提升到模块级）─────────

class _FakeTC:
    """从流式 dict 构造伪 ToolCall 对象供 dispatch 使用。"""
    def __init__(self, d: dict):
        self.id = d.get("id", "")
        self.function = type("F", (), {
            "name": d.get("function", {}).get("name", ""),
            "arguments": d.get("function", {}).get("arguments", ""),
        })()


class DataAnalystAgent:
    """数据分析师 — 唯一 agent。

    一套 chat、一套 prompt、全部工具可见。
    LLM 按 prompt 描述的自然流程与用户交互。
    """

    role = "analyst"

    def __init__(
        self,
        llm_config: LLMConfig,
        event_bus: EventBus,
        orchestrator: Any | None = None,
        llm_client: Any | None = None,
    ) -> None:
        self.llm_config = llm_config
        self.event_bus = event_bus
        self.orchestrator = orchestrator
        self.prompt = self._load_prompt()
        self._context: dict | None = None
        self._df: pd.DataFrame | None = None

    def _emit(self, event_type: EventType, data: dict | None = None) -> None:
        if self.event_bus:
            self.event_bus.emit(event_type=event_type, agent=self.role, data=data or {})

    # ── prompt ──────────────────────────────────────────────────────

    def _load_prompt(self) -> str:
        """加载 prompt。优先读取用户激活的预设，否则用默认 prompt.md。"""
        from pathlib import Path as _Path

        # 检查用户激活的预设
        active_file = _Path.home() / ".hagoku" / "active_preset"
        if active_file.exists():
            preset_id = active_file.read_text(encoding="utf-8").strip()
            preset_path = _Path(__file__).parent / "presets" / f"{preset_id}.md"
            if preset_path.exists():
                return preset_path.read_text(encoding="utf-8")

        # 回退到默认 prompt.md
        p = _Path(__file__).parent / "prompt.md"
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
        sheet_name: int | str = 0,
        aux_sheets: list[str] | None = None,
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
            # ── 多 sheet Excel 检测 ──
            data_path_obj = Path(data_path)
            if data_path_obj.suffix.lower() in (".xlsx", ".xls"):
                try:
                    xl = pd.ExcelFile(data_path)
                    _ = xl.sheet_names  # 触发读取以验证文件有效
                except Exception:
                    pass

            try:
                df = load_data(data_path, sheet_name=sheet_name)
                data_load_error = None
            except Exception as e:
                df = pd.DataFrame()
                data_load_error = str(e)
            self._emit(EventType.TOOL_CALLED, {"tool": "load_data", "args_summary": data_path})

            # 加载辅助 sheet（参考数据）
            aux_info: list[dict] = []
            for sn in (aux_sheets or []):
                if sn == sheet_name:
                    continue
                try:
                    aux_df = load_data(data_path, sheet_name=sn)
                    aux_info.append({
                        "sheet": sn,
                        "rows": len(aux_df),
                        "cols": len(aux_df.columns),
                        "columns": list(aux_df.columns),
                    })
                except Exception:
                    pass
            self._emit(EventType.TOOL_RESULT, {"summary": f"加载成功: {len(df)} 行, {len(df.columns)} 列"})
            self._df = df

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
                "_aux_sheets": aux_info,
                "_data_load_error": data_load_error,
            }
            # Phase D: 项目记忆 / 角色派生 / 质量警告
            if memory_project and project_id:
                self._apply_project_memory(context, memory_project)

            self._learn_from_results(context, project_id)
            self._update_own_memory(context, project_id)

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
        """构建字段 profile。不再内嵌 run_step——LLM 首次交互时自己探索。"""
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
        return column_list

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
    # 通用：_call_llm_step（从 run_step 提取——消除第1轮/后续轮重复）
    # ═══════════════════════════════════════════════════════════════

    def _call_llm_step(
        self,
        client,
        messages: list,
        tools: list,
        dump_tag: str,
        *,
        round_label: str = "",
    ):
        """调用 LLM 一轮（流式优先，batch 回退）。纯函数，不写 session。

        返回 (text, tool_calls_list | None)。
        """
        from hagoku.llm.client import stream_chat_completion
        from hagoku.llm.sanitize import stream_safe_append, strip_llm_think
        from hagoku.observability.llm_dump import dump_messages

        use_stream = getattr(self.llm_config, "stream_enabled", True)
        txt = ""
        tc_list = None

        if use_stream:
            ts = {"ts": datetime.now(timezone.utc).isoformat()}
            if round_label:
                ts["round"] = round_label
            stream_id = _json.dumps(ts)
            full_text = ""
            safe_emitted = 0
            final_tool_calls_raw: list[dict] = []
            agent_key = "analyst"
            for chunk in stream_chat_completion(
                client, self.llm_config.model, messages,
                temperature=0.3, max_tokens=SCOUT_INFER_MAX_TOKENS, tools=tools,
            ):
                # 用户点了停止 → 提前结束流式
                if getattr(self, 'orchestrator', None) is not None and self.orchestrator.is_respond_cancelled():
                    break
                if chunk["type"] == "delta":
                    full_text, delta, safe_emitted = stream_safe_append(
                        full_text, chunk["content"], safe_emitted,
                    )
                    if delta:
                        if safe_emitted == len(delta):
                            ch = getattr(self, '_log_channel', None)
                            if ch:
                                ch(agent_key, "stream_start", stream_id=stream_id)
                        self._emit(EventType.AGENT_STREAM_DELTA, {
                            "stream_id": stream_id, "delta": delta,
                            "agent": agent_key,
                        })
                elif chunk["type"] == "end":
                    full_text = chunk.get("content", full_text)
                    final_tool_calls_raw = chunk.get("tool_calls") or []
                    ch = getattr(self, '_log_channel', None)
                    if ch:
                        ch(agent_key, "stream_end", stream_id=stream_id, text_len=len(full_text))
                    self._emit(EventType.AGENT_STREAM_END, {
                        "stream_id": stream_id, "agent": agent_key,
                    })
            txt = strip_llm_think(full_text).strip()
            if final_tool_calls_raw:
                tc_list = [_FakeTC(tc) for tc in final_tool_calls_raw]
        else:
            resp = client.chat.completions.create(
                model=self.llm_config.model, messages=messages,
                temperature=0.3, max_tokens=SCOUT_INFER_MAX_TOKENS, tools=tools, tool_choice="auto",
            )
            msg = resp.choices[0].message
            txt = strip_llm_think((msg.content or "")).strip()
            tc_list = getattr(msg, "tool_calls", None)

        dump_messages(dump_tag,
            messages + [{"role": "assistant", "content": txt,
             "tool_calls": [{"function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                            for tc in (tc_list or [])] if tc_list else None}],
            model=self.llm_config.model)

        return txt, tc_list

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
        """单轮执行：一次 LLM 调用 + 工具 dispatch → 返回。对标 Claude Code 模型。"""
        from hagoku.llm.client import create_raw_client
        from hagoku.tools.registry import agent_tools as _agt
        from hagoku.observability.llm_dump import dump_messages

        if df is None:
            df = getattr(self, '_df', None)
        client = create_raw_client(self.llm_config)
        if tools is not None:
            _tools = [t for t in _agt.to_openai() if t["function"]["name"] in tools]
        else:
            _tools = _agt.to_openai()

        session = context.get("_session")
        if session is None:
            from hagoku.context.session import Session
            session = Session(analysis_goal=context.get("query", ""))
            context["_session"] = session

        agent_extra = self.prompt
        col_info = context.get("_column_info")
        if col_info:
            agent_extra += "\n数据集字段: " + ", ".join(f"{k}({v})" for k, v in col_info.items())
        aux_info = context.get("_aux_sheets")
        if aux_info:
            aux_lines = ["  " + a['sheet'] + ": " + str(a['rows']) + "行, " + str(a['cols']) + "列" for a in aux_info]
            agent_extra += "\n参考数据（副表单）：\n" + "\n".join(aux_lines)
        load_err = context.get("_data_load_error")
        if load_err:
            agent_extra += f"\n⚠️ 数据加载失败：{load_err}\n请告知用户此错误，并建议检查文件格式或表单名称。"

        messages = session.to_llm_messages(system_extra=agent_extra, user_input=user_input)
        dump_messages("agent_run_step", messages, model=self.llm_config.model,
                      extra={"tools": [t["function"]["name"] for t in _tools]})

        txt, tc_list = self._call_llm_step(client, messages, _tools, "agent_run_step_response")

        # ── 工具循环：LLM 调工具 → 自动续轮，不调 → 自然停。对标 Claude Code。──
        _round = 0
        while tc_list and _round < 20:
            _round += 1
            # 批量执行工具
            tool_records = []
            for tc in tc_list:
                fn = tc.function
                try:
                    args = _json.loads(fn.arguments) if fn.arguments else {}
                except (_json.JSONDecodeError, TypeError):
                    tool_records.append(ToolCallRecord(
                        tool_call_id=getattr(tc, "id", "") or "",
                        name=fn.name, arguments=fn.arguments,
                        result="", error=f"参数解析失败：{str(fn.arguments)[:200]}",
                    ))
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
                oai_calls = [
                    {"id": tc.tool_call_id, "type": "function",
                     "function": {"name": tc.name, "arguments": tc.arguments}}
                    for tc in tool_records
                ]
                results = [
                    {"content": tc.error or tc.result, "tool_call_id": tc.tool_call_id}
                    for tc in tool_records
                ]
                session.add_tool_call(txt, oai_calls, results)
                # 工具执行后推 snapshot
                try:
                    from hagoku.api.ws_handler import WSBridge, _fastapi_app
                    app = _fastapi_app
                    if app is not None:
                        hagoku_app = getattr(app.state, 'hagoku_app', None)
                        if hagoku_app is not None:
                            snap = hagoku_app.build_snapshot()
                            if snap:
                                WSBridge.get().push_snapshot(snap)
                except Exception:
                    logger.exception("agent push_snapshot 失败")

            # 用户点了停止
            if getattr(self, 'orchestrator', None) is not None and self.orchestrator.is_respond_cancelled():
                break

            # 自动续轮：让 LLM 看到工具结果
            agent_extra2 = self.prompt
            if col_info:
                agent_extra2 += "\n数据集字段: " + ", ".join(f"{k}({v})" for k, v in col_info.items())
            if aux_info:
                aux_lines2 = ["  " + a['sheet'] + ": " + str(a['rows']) + "行, " + str(a['cols']) + "列" for a in aux_info]
                agent_extra2 += "\n参考数据（副表单）：\n" + "\n".join(aux_lines2)
            load_err2 = context.get("_data_load_error")
            if load_err2:
                agent_extra2 += f"\n⚠️ 数据加载失败：{load_err2}\n请告知用户此错误，并建议检查文件格式或表单名称。"
            msgs_next = session.to_llm_messages(system_extra=agent_extra2, user_input="")
            dump_messages(f"agent_run_step_r{_round + 1}", msgs_next, model=self.llm_config.model,
                          extra={"tools": [t["function"]["name"] for t in _tools]})
            txt, tc_list = self._call_llm_step(
                client, msgs_next, _tools,
                f"agent_run_step_r{_round + 1}_response",
            )
            if not tc_list and session and txt:
                session.add("assistant", txt)

        if _round == 0 and txt and session:
            session.add("assistant", txt)

        return {"text": txt}
