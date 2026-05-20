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
from .._interactive import InteractionMixin
from ..types import InteractionResult


class ReporterAgent(InteractionMixin):
    """报告员：让分析结果说话，LLM 决定说什么、怎么说"""

    def __init__(
        self,
        *args: Any,
        event_bus: EventBus | None = None,
        llm_client: Any | None = None,
        scribe: Any | None = None,
        **kwargs: Any,
    ) -> None:
        # 兼容旧签名的第一个位置参数 llm_config（忽略）
        self.role = "reporter"
        self.event_bus = event_bus or args[1] if len(args) > 1 else event_bus  # type: ignore[assignment]
        self.scribe = scribe
        self._llm_client = llm_client
        if not self.event_bus:
            raise ValueError("ReporterAgent 需要 event_bus 参数")

        # 运行时加载 prompt + memory
        self.prompt = self._load_prompt()
        self.memory = self._load_memory()

        # 交互状态
        self._phase = "begin"
        self._results: list[dict] = []
        self._context: dict = {}
        self._cleaning_summary: dict = {}
        self._pending_data: dict = {}

    # ── prompt / memory 读写 ────────────────────────────────

    def _load_prompt(self) -> str:
        path = Path(__file__).parent / "prompt.md"
        if path.exists():
            return path.read_text(encoding="utf-8")
        return ""

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

    def _call_llm(self, system: str, user: str) -> str:
        """调用 LLM，返回文本响应"""
        if self._llm_client is None:
            raise RuntimeError("ReporterAgent 没有 LLM 客户端")
        # 使用底层 raw 接口（和 Scout/Analyst 一致）
        if hasattr(self._llm_client, "chat_raw"):
            return self._llm_client.chat_raw(system=system, user=user)
        if hasattr(self._llm_client, "chat"):
            resp = self._llm_client.chat(system=system, messages=[{"role": "user", "content": user}])
            if isinstance(resp, dict):
                return resp.get("content", "")
            return str(resp)
        raise RuntimeError(f"不支持的 LLM 客户端类型: {type(self._llm_client)}")

    def _emit(self, event_type: EventType, data: dict | None = None) -> None:
        self.event_bus.emit(event_type=event_type, agent=self.role, data=data or {})

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

        user_prompt = f"""## 系统角色
{self.prompt}

## 当前项目
- 项目名：{project_name}
- 研究问题：{query}

## 数据上下文
{context_text}

## 数据清洗摘要
{cleaning_text}

## 商业指标
{biz_text}

## 分析结果
{results_text}

## 历史报告参考
{history_text}

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
      "limitations": ["局限1", "局限2"]
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
  ]
}}
```

关键规则：
1. headline 必须一句话讲清楚最重要的发现，≤80字
2. executive_summary 让非技术人员也能看懂
3. metric_cards 提取 3-5 个最关键指标
4. 每个 section 包含吸引力层（headline）+ 核心价值层（plain_explanation）
5. 如果有历史报告，对比标注新发现/变化
6. 不要编造数据，所有数值必须来自分析结果
"""

        system = "你是 HaGoKu Studio 的专业报告员。你的任务是把数据分析结果变成一份谁都看得懂的报告。只输出 JSON，不要任何解释。"

        self._emit(EventType.AGENT_THINKING, {"thought": "正在通过 LLM 生成报告内容..."})

        response = self._call_llm(system=system, user=user_prompt)

        # 解析 LLM 返回的 JSON
        return self._parse_llm_json(response)

    def _parse_llm_json(self, response: str) -> dict:
        """从 LLM 响应中提取 JSON"""
        # 尝试直接解析
        response = response.strip()
        try:
            return json.loads(response)
        except json.JSONDecodeError:
            pass

        # 尝试提取 ```json ... ``` 块
        match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", response, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                pass

        # 尝试提取 { ... } 最外层
        match = re.search(r"\{.*\}", response, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass

        # ==== CHANNEL ZONE: 保底输出，禁止语义推断 ====
        # 当 LLM 返回的 JSON 无法解析时，用原始文本作为报告内容的兜底占位。
        # 这不是"代码替代 LLM 生成报告"，而是"LLM 已产出文本但格式损坏时，保留内容不丢失"。
        self._emit(EventType.AGENT_THINKING, {
            "thought": f"⚠️ 无法解析 LLM 输出为 JSON，使用 fallback。原始输出前 200 字：{response[:200]}"
        })
        return {
            "headline": "分析报告",
            "executive_summary": response[:500] if response else "报告生成中...",
            "metric_cards": [],
            "findings_summary": [],
            "sections": [{"title": "📊 分析结果", "content": response[:1000] if response else "", "level": 2}],
        }

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

        if self.scribe:
            self.scribe.block_task("reporter", "等用户确认生成报告")

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
            if self.scribe:
                self.scribe.unblock_task("reporter")
            return self._done("done", "报告生成已取消", {})

        if self.scribe:
            self.scribe.unblock_task("reporter")

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
