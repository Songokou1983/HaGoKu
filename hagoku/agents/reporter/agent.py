"""
Reporter Agent — 报告员（LLM 原生版）

从 prompt.md 读取角色定义，从 memory.md 读取/保存报告历史。
LLM 决定所有叙事内容（headline、摘要、章节），代码只负责：
- 结构化组装 ReportData / ReportSection
- 调用 ReportGenerator 产生文件
- 调用图表工具
- 记忆读写
- 交互流程（pause / done）
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from ...observability.event_bus import EventBus
from ...observability.events import EventType
from ...tools.reporting import ReportData, ReportGenerator, ReportSection
from ...tools.visualization import generate_data_overview_charts
from ..base import BaseAgent
from ..types import InteractionResult


class ReporterAgent(BaseAgent):
    """报告员：让分析结果说话，LLM 决定说什么、怎么说"""
    role = "reporter"
    _memory_yaml_key = "reports"

    def __init__(
        self,
        llm_config: Any = None,
        event_bus: EventBus | None = None,
        llm_client: Any | None = None,
        orchestrator: Any | None = None,
    ) -> None:
        super().__init__(llm_config=llm_config, event_bus=event_bus,
                         orchestrator=orchestrator, llm_client=llm_client)
        if not self.event_bus:
            raise ValueError("ReporterAgent 需要 event_bus 参数")

        # Reporter 特有字段
        self._results: list[dict] = []
        self._context: dict = {}
        self._cleaning_summary: dict = {}
        self._pending_data: dict = {}

    def run_step(self, context: dict, df=None, user_input: str = "") -> dict:
        """单步执行：跑 1 轮 LLM，处理 tool_calls。

        Phase B: messages 不再外部传入——由 project_ctx.to_messages_for_llm() 统一构建。
        """
        import json as _json
        from hagoku.tools.registry import agent_tools as _agt
        from hagoku.context.project_context import ToolCallRecord
        from ...llm.client import create_raw_client

        client = create_raw_client(self.llm_config)
        _tools = _agt.to_openai("reporter")

        project_ctx = context.get("_project_context")
        if project_ctx is None:
            raise RuntimeError("Reporter.run_step: _project_context 未设置，信息通道断裂")

        agent_extra = getattr(self, 'prompt', '')
        messages = project_ctx.to_messages_for_llm(
            "reporter", context, user_input or "生成报告",
            agent_system_extra=agent_extra,
        )

        from ...observability.llm_dump import dump_messages
        dump_messages("reporter_run_step", messages, model=self.llm_config.model,
                      extra={"tools": [t["function"]["name"] for t in _tools]})

        resp = client.chat.completions.create(
            model=self.llm_config.model, messages=messages,
            temperature=0.3, max_tokens=4096, tools=_tools, tool_choice="auto",
        )
        msg = resp.choices[0].message
        txt = (msg.content or "").strip()
        tc_list = getattr(msg, "tool_calls", None)

        dump_messages("reporter_run_step_response", messages + [{"role": "assistant", "content": txt, "tool_calls": [{"function": {"name": tc.function.name, "arguments": tc.function.arguments}} for tc in (tc_list or [])] if tc_list else None}], model=self.llm_config.model)

        # 写回 ProjectContext
        project_ctx.add_agent_response("reporter", context.get("interaction_revision", 0), txt or "(tool calls)")

        route_to_args = None

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
                project_ctx.add_tool_exchange("reporter", context.get("interaction_revision", 0), tool_records,
                                              assistant_content=txt)

        return {
            "text": txt,
            "route_to": route_to_args,
        }

    # ── memory 读写 ──────────────────────────────────────────

    def _load_memory(self) -> dict:
        path = Path(__file__).parent / "memory.md"
        if path.exists():
            content = path.read_text(encoding="utf-8")
            match = re.search(r"```yaml\n(reports:.*?)```", content, re.DOTALL)
            if match:
                try:
                    return yaml.safe_load(match.group(1)) or {}
                except yaml.YAMLError:
                    return {}
        return {"reports": {}}

    def _save_memory(self) -> None:
        path = Path(__file__).parent / "memory.md"
        content = path.read_text(encoding="utf-8")

        reports_yaml = yaml.dump(
            {"reports": self.memory.get("reports") or {}},
            default_flow_style=False,
            allow_unicode=True,
        ).rstrip()

        pattern = r"```yaml\nreports:.*?```"
        if re.search(pattern, content, re.DOTALL):
            content = re.sub(
                pattern, f"```yaml\n{reports_yaml}\n```", content, flags=re.DOTALL
            )
        else:
            content = re.sub(r"reports:.*", reports_yaml, content)

        path.write_text(content, encoding="utf-8")

    # ── LLM 调用 ────────────────────────────────────────────

    def _call_llm_with_tools(
        self, system: str, user: str,
        messages_history: list[dict[str, str]] | None = None,
    ) -> dict:
        """调用 LLM（function calling），返回 submit_report 工具调用的参数 dict。

        Phase B: 优先走 project_ctx.to_messages_for_llm()；保留 system/user/history 兼容旧调用。
        """
        if self._llm_client is None:
            raise RuntimeError("ReporterAgent 没有 LLM 客户端")

        # Phase B: 统一走 ProjectContext.to_messages_for_llm()
        ctx = getattr(self, '_context', {}) or {}
        project_ctx = ctx.get("_project_context")
        if project_ctx is None:
            raise RuntimeError("Reporter._call_llm_with_tools: _project_context 未设置，信息通道断裂")
        agent_extra = getattr(self, 'prompt', '')
        _messages = project_ctx.to_messages_for_llm(
            "reporter", ctx, user,
            agent_system_extra=agent_extra,
        )

        try:
            response = self._llm_client.chat.completions.create(
                model=self.llm_config.model,
                messages=_messages,
                temperature=0.3,
                max_tokens=4096,
                tools=self._report_tools(),
                tool_choice={"type": "function", "function": {"name": "submit_report"}},
            )
        except Exception as e:
            raise RuntimeError(f"Reporter LLM 调用失败: {e}")
        msg = response.choices[0].message
        tc = getattr(msg, "tool_calls", None)
        if tc and len(tc) > 0:
            import json as _json
            args_str = tc[0].function.arguments if hasattr(tc[0], "function") else "{}"
            try:
                return _json.loads(args_str)
            except _json.JSONDecodeError:
                pass
        raise RuntimeError("Reporter: LLM 未调用 submit_report 工具")

    _call_llm = _call_llm_with_tools  # 兼容旧调用方

    @staticmethod
    def _report_tools() -> list[dict]:
        return [{
            "type": "function",
            "function": {
                "name": "submit_report",
                "description": "提交报告内容的 JSON 结构。调用此工具完成报告生成。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "headline": {"type": "string"},
                        "executive_summary": {"type": "string"},
                        "metric_cards": {"type": "array"},
                        "sections": {"type": "array"},
                        "findings": {"type": "array"},
                        "disclaimers": {"type": "array"},
                    },
                    "required": ["title", "headline", "executive_summary"],
                },
            },
        }]

    # ── 核心：run() ─────────────────────────────────────────

    def run(
        self,
        results: list[dict],
        context: dict,
        cleaning_summary: dict | None = None,
        *,
        project_name: str = "分析项目",
        query: str = "",
        output_path: str | None = None,
        df: Any | None = None,
        business_metrics: list[dict] | None = None,
        template: str | None = None,
        formats: list[str] | None = None,
    ) -> ReportData:
        """
        生成分析报告（orchestrator 调用的主入口）。

        LLM 决定叙事内容，代码负责结构化组装和文件产出。
        """
        self._emit(EventType.AGENT_STARTED, {"goal": "让分析结果说话"})

        try:
            # 1. 让 LLM 生成报告内容 JSON
            llm_output = self._generate_report_via_llm(
                results=results,
                context=context,
                cleaning_summary=cleaning_summary or {},
                project_name=project_name,
                query=query,
                business_metrics=business_metrics,
            )

            # 2. 结构化为 ReportData
            report = self._build_report_data(
                llm_output=llm_output,
                context=context,
                cleaning_summary=cleaning_summary or {},
                project_name=project_name,
                query=query,
            )

            # 3. 数据概览图表（代码负责：工具调用）
            charts_dir = Path(output_path).parent / "charts" if output_path else None
            if df is not None and charts_dir:
                try:
                    overview_charts = generate_data_overview_charts(
                        df, output_dir=charts_dir, interactive=True,
                    )
                    if overview_charts:
                        chart_section = ReportSection(
                            title="📊 数据概况",
                            content="",
                            charts=overview_charts,
                            level=2,
                        )
                        report.sections.insert(1, chart_section)
                except Exception:
                    pass

            # 4. 生成文件（代码负责：工具调用）
            if output_path:
                generator = ReportGenerator()
                fmt_list = formats or (["html"] if output_path.endswith(".html") else ["md"])
                for fmt in fmt_list:
                    if fmt == "html":
                        p = output_path if output_path.endswith(".html") else f"{output_path}.html"
                        generator.generate_html(report, output_path=p, template_name=template)
                    elif fmt == "md":
                        p = output_path.replace(".html", ".md") if ".html" in str(output_path) else f"{output_path}.md"
                        generator.generate_markdown(report, output_path=p)

            # 5. 更新记忆
            self._update_own_memory(project_name, report.headline or "", results)

            self._emit(EventType.AGENT_COMPLETED, {
                "result_summary": f"生成 {len(report.sections)} 个章节",
                "output_path": str(output_path) if output_path else "",
                "project_name": project_name,
            })

            return report

        except Exception as e:
            self._emit(EventType.AGENT_FAILED, {"error": str(e)})
            return ReportData(
                project_name=project_name,
                query=query,
                sections=[ReportSection(title="⚠️ 报告生成失败", content=str(e), level=1)],
                data_summary={},
                findings_summary=[],
                headline="报告生成失败",
                metric_cards=[],
            )

    def _generate_report_via_llm(
        self,
        results: list[dict],
        context: dict,
        cleaning_summary: dict,
        project_name: str,
        query: str,
        business_metrics: list[dict] | None,
    ) -> dict:
        """调用 LLM 生成报告内容的 JSON 结构"""
        # 构建传给 LLM 的上下文
        results_text = json.dumps(results, ensure_ascii=False, indent=2, default=str)
        context_text = json.dumps(context, ensure_ascii=False, indent=2, default=str)
        biz_text = json.dumps(business_metrics or [], ensure_ascii=False, indent=2, default=str)
        cleaning_text = json.dumps(cleaning_summary, ensure_ascii=False, indent=2, default=str)

        # 加载历史记忆参考
        history = self.memory.get("reports", {}).get(project_name, [])
        history_text = json.dumps(history[-3:] if history else [], ensure_ascii=False, indent=2)

        # ── 构建证据溯源字段映射（律 5：首选 column_semantics）──
        field_display_names = context.get("column_display_names", {}) or {}
        field_descriptions = context.get("column_descriptions", {}) or {}
        column_semantics = context.get("column_semantics", [])

        # 字段溯源映射表：让 LLM 在写结论时能精准引用字段的中文名称
        field_evidence_lines = []
        for sem in column_semantics:
            col = sem.get("column_name", "")
            if not col:
                continue
            sem_type = sem.get("semantic_type", "")
            # 律 5：display_name / description 首选 column_semantics，兜底旧 dict
            display = sem.get("display_name", "") or field_display_names.get(col, "")
            desc = sem.get("description", "") or field_descriptions.get(col, "")
            parts = [f"  - `{col}`"]
            if display:
                parts.append(f"中文名：{display}")
            if desc:
                parts.append(f"含义：{desc}")
            if sem_type:
                parts.append(f"类型：{sem_type}")
            field_evidence_lines.append(" | ".join(parts))
        field_evidence_text = (
            "\n".join(field_evidence_lines)
            if field_evidence_lines
            else "（暂无字段映射）"
        )

        # ── 清洗操作详情（供局限性引用）───────────────────────
        cleaning_ops = cleaning_summary.get("operations", []) if cleaning_summary else []
        cleaning_ops_text = ""
        if cleaning_ops:
            ops_lines = []
            for op in cleaning_ops[:20]:
                col = op.get("column", "")
                strat = op.get("strategy", "")
                reason = op.get("reason", "")[:100]
                ra = op.get("rows_affected", 0)
                ops_lines.append(
                    f"  - `{col}`: {strat}（影响 {ra} 行，原因：{reason}）"
                )
            cleaning_ops_text = "\n".join(ops_lines)

        # ── 上游摘要（Scribe 交接笔记）─────────────────────────
        upstream_summary = context.get("upstream_summary", "") or ""

        # ── 历史对比结构化指引 ─────────────────────────────────
        history_guidance = ""
        if history and isinstance(history, list) and len(history) > 0:
            prev_keys = set()
            for prev_report in history[-3:]:
                prev_findings = prev_report.get("key_findings", [])
                for pf in prev_findings:
                    if isinstance(pf, str):
                        prev_keys.add(pf)
            hist_count = len(history)
            prev_keys_str = ", ".join(sorted(prev_keys)) if prev_keys else "无"
            history_guidance = f"""
## 历史对比指引
本项目有历史报告（最近 {hist_count} 份）。请在你的输出中增加一个 `history_comparison` section：

**必须做的事**：
1. 对比本次结论与历史结论的一致性：上次也显著的，这次还显著吗？效应量变了吗？
2. 标注新增发现：哪些是本次新出现的？（上次没提到）
3. 标注消失/变化的发现：哪些上次显著这次不显著了？可能的解释是什么？
4. 变化诊断：如果同一变量的效应量有变化（如系数从 0.82 → 0.75），给一个可能的原因（数据更新？清洗策略不同？控制变量增减？）

历史结论关键词（供对比）：{prev_keys_str}
"""
        else:
            history_guidance = (
                "\n## 历史对比\n本项目暂无历史报告，本次为首版报告。可跳过历史对比 section。\n"
            )

        user_prompt = f"""## 系统角色
{self.prompt}

## 当前项目
- 项目名：{project_name}
- 研究问题：{query}

## 数据上下文
{context_text}

## 字段溯源映射（Scout → 证据链）
每个字段的中文名称和业务含义如下。撰写"关键发现"时，必须引用对应字段的中文名：
{field_evidence_text}

## 数据清洗摘要
{cleaning_text}

## 清洗操作详情（供局限性引用）
{cleaning_ops_text if cleaning_ops_text else "（无清洗操作）"}

## 上游交接笔记（Analyst → Reporter）
{upstream_summary if upstream_summary else "（暂无交接笔记）"}

## 商业指标
{biz_text}

## 分析结果
{results_text}

## 历史报告参考
{history_text}
{history_guidance}

## 输出要求
请严格按照以下 JSON schema 输出报告内容（只输出 JSON，不要任何额外文本）：

```json
{{
  "headline": "一句话核心发现（≤80字）",
  "executive_summary": "整体人话解读（2-4句话，非技术背景可读）",
  "metric_cards": [
    {{"value": "数值", "label": "标签", "trend": "up|down|null"}}
  ],
  "findings_summary": [
    {{
      "analysis_type": "...",
      "question": "...",
      "headline": "一句话结论（≤60字）",
      "conclusion_plain": "人话结论",
      "p_value": 0.01,
      "effect_size": 0.5,
      "effect_type": "cohen_d",
      "significance": "significant|not_significant",
      "limitations": ["局限1", "局限2"],
      "evidence_source_fields": ["引用的字段中文名列表"],
      "cleaning_impact": "该结论受清洗操作的影响说明"
    }}
  ],
  "sections": [
    {{
      "title": "📈 章节标题",
      "content": "章节详细内容（markdown）",
      "headline": "吸引力层一句话",
      "plain_explanation": "核心价值层人话解读",
      "level": 2,
      "metric_cards": [...],
      "findings": [{{"同 findings_summary 格式"}}]
    }}
  ],
  "history_comparison": {{
    "has_history": true/false,
    "title": "🔄 与历史对比",
    "content": "历史对比详情（markdown）",
    "sustained_findings": ["延续的发现"],
    "new_findings": ["新增发现"],
    "changed_findings": [{{
      "topic": "变化主题",
      "previous": "历史状态",
      "current": "当前状态",
      "possible_reason": "可能原因"
    }}]
  }}
}}
```

关键规则：
1. headline 必须一句话讲清楚最重要的发现，≤80字
2. executive_summary 让非技术人员也能看懂
3. metric_cards 提取 3-5 个最关键指标
4. 每个 section 包含吸引力层（headline）+ 核心价值层（plain_explanation）
5. 每个 finding 必须包含 evidence_source_fields（引用字段的中文名称，如「广告支出」「用户评分」）
6. 每个 finding 必须包含 cleaning_impact（说明该结论是否受清洗操作影响）
7. 如果有历史报告，必须输出 history_comparison section
8. 不要编造数据，所有数值必须来自分析结果
"""

        system = "你是 HaGoKu Studio 的专业报告员。你的任务是把数据分析结果变成一份谁都看得懂的报告。只输出 JSON，不要任何解释。"

        # ── ProjectContext 注入（阶段 3）──
        project_ctx = context.get("_project_context")
        rpt_history: list[dict] = []
        if project_ctx:
            ctx_block = project_ctx.build_prompt("reporter", context)
            system += "\n\n" + ctx_block["system_prefix"] + "\n\n" + ctx_block["upstream_summary"]
            rpt_history = ctx_block.get("messages_history", [])

        self._emit(EventType.AGENT_THINKING, {"thought": "正在通过 LLM 生成报告内容..."})

        return self._call_llm_with_tools(system=system, user=user_prompt, messages_history=rpt_history)



    def _build_report_data(
        self,
        llm_output: dict,
        context: dict,
        cleaning_summary: dict,
        project_name: str,
        query: str,
    ) -> ReportData:
        """将 LLM JSON 输出转换为 ReportData 对象"""
        sections = []
        for sec in llm_output.get("sections", []):
            sections.append(ReportSection(
                title=sec.get("title", ""),
                content=sec.get("content", ""),
                level=sec.get("level", 2),
                headline=sec.get("headline"),
                plain_explanation=sec.get("plain_explanation"),
                metric_cards=sec.get("metric_cards"),
                findings=sec.get("findings"),
            ))

        return ReportData(
            project_name=project_name,
            query=query,
            sections=sections,
            data_summary={
                "n_rows": context.get("n_rows", 0),
                "n_cols": context.get("n_cols", 0),
                "quality_score": context.get("quality_score", 0),
            },
            cleaning_summary=cleaning_summary,
            findings_summary=llm_output.get("findings_summary", []),
            headline=llm_output.get("headline", ""),
            metric_cards=llm_output.get("metric_cards", []),
            executive_summary=llm_output.get("executive_summary"),
        )

    # ── 交互式接口 ────────────────────────────────────────

    def begin(
        self,
        results: list[dict],
        context: dict,
        cleaning_summary: dict | None = None,
        *,
        project_name: str = "分析项目",
        query: str = "",
        df: Any | None = None,
        business_metrics: list[dict] | None = None,
    ) -> InteractionResult:
        """开始 Reporter 交互：预览 → 确认 → 生成"""
        self._results = results
        self._context = context
        self._cleaning_summary = cleaning_summary or {}
        self._phase = "confirm_report"

        self._emit(EventType.AGENT_STARTED, {"goal": "让分析结果说话"})

        # 先让 LLM 生成预览（headline + 摘要）
        n_sig = sum(1 for r in results if r.get("significance") == "significant")

        if self.orchestrator:
            self.orchestrator.block_task("reporter", "等用户确认生成报告")

        return self._pause(
            phase="confirm_report",
            message=f"分析完成：{len(results)} 项分析，{n_sig} 项显著发现。确认生成报告？",
            needs_confirmation=True,
            confirmation_prompt="确认生成报告",
            pending_items=results[:3] if results else [],
            data={
                "n_results": len(results),
                "n_significant": n_sig,
                "project_name": project_name,
                "query": query,
                "df": df,
                "business_metrics": business_metrics or [],
            },
        )

    def respond(
        self,
        user_input: dict,
        output_path: str | None = None,
    ) -> InteractionResult:
        """处理用户确认，生成最终报告"""
        if self._phase not in ("confirm_report",):
            return self._done("done", "阶段错误，请重新开始", {})

        confirmed = user_input.get("confirmed", True)
        if not confirmed:
            if self.orchestrator:
                self.orchestrator.unblock_task("reporter")
            return self._done("done", "报告生成已取消", {})

        if self.orchestrator:
            self.orchestrator.unblock_task("reporter")

        data = self._pending_data

        report = self.run(
            results=self._results,
            context=self._context,
            cleaning_summary=self._cleaning_summary,
            project_name=data.get("project_name", "分析项目"),
            query=data.get("query", ""),
            output_path=output_path,
            df=data.get("df"),
            business_metrics=data.get("business_metrics"),
        )

        return self._done(
            phase="done",
            message=f"✅ 报告已生成！共 {len(report.sections)} 个章节",
            data={
                "report_sections": len(report.sections),
                "key_findings_count": len(report.findings_summary) if report.findings_summary else 0,
            },
        )

    # ── 记忆更新 ──────────────────────────────────────────

    def _update_own_memory(
        self, project_id: str, headline: str, results: list[dict],
    ) -> None:
        """更新报告记忆"""
        if not isinstance(self.memory.get("reports"), dict):
            self.memory["reports"] = {}

        if project_id not in self.memory["reports"]:
            self.memory["reports"][project_id] = []

        self.memory["reports"][project_id].append({
            "date": datetime.now().strftime("%Y-%m-%d"),
            "headline": headline,
            "n_results": len(results),
            "significant": any(r.get("significance") == "significant" for r in results),
        })

        self._save_memory()

    # ── InteractionMixin 要求的方法 ─────────────────────────

    def _pause(
        self, phase: str, message: str, needs_confirmation: bool = False,
        confirmation_prompt: str = "", pending_items: list | None = None,
        actions: list | None = None,
        data: dict | None = None,
    ) -> InteractionResult:
        """暂停等待用户交互（和 Scout/Analyst 一致）"""
        self._phase = phase
        if data:
            self._pending_data = data
        return InteractionResult(
            phase=phase,
            message=message,
            needs_confirmation=needs_confirmation,
            confirmation_prompt=confirmation_prompt,
            pending_items=pending_items or [],
            actions=actions or [],
            final=False,
            data=data or {},
        )

    def _done(self, phase: str, message: str, data: dict, actions: list | None = None) -> InteractionResult:
        """完成交互"""
        self._phase = phase
        return InteractionResult(
            phase=phase,
            message=message,
            needs_confirmation=False,
            actions=actions or [],
            final=True,
            data=data,
        )