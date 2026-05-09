"""
Reporter Agent — 报告员

从 prompt.md 读取角色定义，从 memory.md 读取/保存报告历史
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from ...config import LLMConfig
from ...guardrails.parsers import validate_analysis_output
from ...observability.event_bus import EventBus
from ...observability.events import EventType
from ...tools.reporting import ReportData, ReportGenerator, ReportSection
from ...tools.visualization import generate_data_overview_charts, generate_insight_charts
from .._interactive import InteractionMixin
from ..types import InteractionResult


class ReporterAgent(InteractionMixin):
    """报告员：让分析结果说话"""

    def __init__(
        self,
        llm_config: LLMConfig,
        event_bus: EventBus,
        scribe: "ScribeAgent | None" = None,
        llm_client: Any | None = None,
    ) -> None:
        self.role = "reporter"
        self.llm_config = llm_config
        self.event_bus = event_bus
        self.scribe = scribe
        self._llm_client = llm_client  # 外部传入的 LLM 客户端（双层策略用）

        self.prompt = self._load_prompt()
        self.memory = self._load_memory()

        # 交互状态
        self._phase = "begin"
        self._results: list[dict] = []
        self._context: dict = {}
        self._cleaning_summary: dict = {}

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
            self.memory.get("reports", {}),
            default_flow_style=False,
            allow_unicode=True
        )

        pattern = r"```yaml\nreports:.*?```"
        if re.search(pattern, content, re.DOTALL):
            content = re.sub(pattern, f"```yaml\nreports:\n{reports_yaml}```", content, flags=re.DOTALL)
        else:
            content = re.sub(r"reports: \{\}", f"reports:\n{reports_yaml}", content)

        path.write_text(content, encoding="utf-8")

    def _emit(self, event_type: EventType, data: dict = None) -> None:
        self.event_bus.emit(event_type=event_type, agent=self.role, data=data or {})

    # ── 核心逻辑 ────────────────────────────────────────────

    def run(
        self,
        results: list[dict],
        context: dict,
        cleaning_summary: dict = None,
        project_id: str = "分析项目",
        query: str = "",
        output_path: str = None,
        df: pd.DataFrame = None,
        business_metrics: list[dict] = None,
    ) -> ReportData:
        """
        生成分析报告

        Returns:
            ReportData
        """
        self._emit(EventType.AGENT_STARTED, {"goal": "让分析结果说话"})

        # 查历史
        history = self._get_project_history(project_id)

        try:
            # 1. 提取关键发现
            key_findings = self._extract_key_findings(results)

            # 2. 生成 headline
            headline = self._generate_headline(results, context)

            # 3. 生成 metric cards
            metric_cards = self._generate_metric_cards(results, context)

            # 4. 构建章节
            sections = []

            # 核心发现
            if key_findings:
                sections.append(ReportSection(
                    title="🎯 核心发现",
                    content=self._summarize_findings(key_findings),
                    findings=key_findings,
                    level=2,
                    headline=headline,
                    plain_explanation=self._generate_overall_plain(results),
                ))

            # 商业指标
            if business_metrics:
                biz_section = self._build_business_metrics_section(business_metrics)
                if biz_section:
                    sections.append(biz_section)

            # 数据概览图表
            charts_dir = Path(output_path).parent / "charts" if output_path else None
            if df is not None and charts_dir:
                try:
                    overview_charts = generate_data_overview_charts(df, output_dir=charts_dir, interactive=True)
                    if overview_charts:
                        sections.insert(1, ReportSection(
                            title="📊 数据概况",
                            content="",
                            charts=overview_charts,
                            level=2,
                        ))
                except Exception:
                    pass

            # 详细结果
            for result in results:
                section = self._build_result_section(result)
                sections.append(section)

            # 报告数据
            report = ReportData(
                project_name=project_id,
                query=query,
                sections=sections,
                data_summary={
                    "n_rows": context.get("n_rows", 0),
                    "n_cols": context.get("n_cols", 0),
                    "quality_score": context.get("quality_score", 0),
                },
                cleaning_summary=cleaning_summary or {},
                findings_summary=key_findings,
                headline=headline,
                metric_cards=metric_cards,
                user_mode="standard",
            )

            # 生成文件
            if output_path:
                generator = ReportGenerator()
                if output_path.endswith(".html") or ".html" in str(output_path):
                    generator.generate_html(report, output_path=output_path)
                elif output_path.endswith(".md"):
                    generator.generate_markdown(report, output_path=output_path)

            # 更新记忆
            self._update_own_memory(project_id, headline, len(key_findings), results)

            self._emit(EventType.AGENT_COMPLETED, {"result_summary": f"生成 {len(sections)} 个章节"})

            return report

        except Exception as e:
            self._emit(EventType.AGENT_FAILED, {"error": str(e)})
            return ReportData(
                project_name=project_id,
                query=query,
                sections=[ReportSection(title="⚠️ 报告生成失败", content=str(e), level=1)],
                data_summary={},
                findings_summary=[],
                headline="报告生成失败",
                metric_cards=[],
                user_mode="standard",
            )

    # ── 交互式接口 ────────────────────────────────────────

    def begin(
        self,
        results: list[dict],
        context: dict,
        cleaning_summary: dict = None,
        project_id: str = "分析项目",
        query: str = "",
        df: pd.DataFrame = None,
        business_metrics: list[dict] = None,
    ) -> InteractionResult:
        """
        开始 Reporter 交互。

        流程：预览报告结构 → 确认 → 生成报告 → 完成
        Reporter 是最后一环，直接完成。
        """
        self._results = results
        self._context = context
        self._cleaning_summary = cleaning_summary or {}
        self._phase = "confirm_report"

        self._emit(EventType.AGENT_STARTED, {"goal": "让分析结果说话"})

        key_findings = self._extract_key_findings(results)
        n_sig = sum(1 for f in key_findings if f.get("significance") == "significant")

        # block，等用户确认
        if self.scribe:
            self.scribe.block_task("reporter", "等用户确认生成报告")
        return self._pause(
            phase="confirm_report",
            message=f"分析完成：{len(results)} 项分析，{n_sig} 项显著发现。确认生成报告？",
            needs_confirmation=True,
            confirmation_prompt="确认生成报告",
            pending_items=key_findings[:3] if key_findings else [],
            data={
                "n_results": len(results),
                "n_significant": n_sig,
                "project_id": project_id,
                "query": query,
                "df": df,
                "business_metrics": business_metrics or [],
            },
        )

    def respond(
        self,
        user_input: dict,
        output_path: str = None,
    ) -> InteractionResult:
        """
        处理用户确认，生成最终报告。
        """
        if self._phase not in ("confirm_report",):
            return self._done("done", "阶段错误，请重新开始", {})

        confirmed = user_input.get("confirmed", True)  # 默认确认

        if not confirmed:
            if self.scribe:
                self.scribe.unblock_task("reporter")
            return self._done("done", "报告生成已取消", {})

        # 解除 block
        if self.scribe:
            self.scribe.unblock_task("reporter")

        data = self._context.get("_report_data", {})

        report = self.run(
            results=self._results,
            context=self._context,
            cleaning_summary=self._cleaning_summary,
            project_id=data.get("project_id", "分析项目"),
            query=data.get("query", ""),
            output_path=output_path,
            df=data.get("df"),
            business_metrics=data.get("business_metrics"),
        )

        self._emit(EventType.AGENT_COMPLETED, {
            "result_summary": f"报告生成完成：{len(report.sections)} 个章节"
        })

        return self._done(
            phase="done",
            message=f"✅ 报告已生成！共 {len(report.sections)} 个章节",
            data={
                "report_sections": len(report.sections),
                "key_findings_count": len(report.findings_summary) if report.findings_summary else 0,
            },
        )

    def _get_project_history(self, project_id: str) -> list[dict]:
        """获取项目历史报告"""
        return self.memory.get("reports", {}).get(project_id, [])

    def _generate_headline(self, results: list[dict], context: dict) -> str:
        """生成一句话 headline"""
        significant = [r for r in results if r.get("significance") == "significant"]

        if not significant:
            if results:
                return f"{len(results)} 项分析完成，未发现显著差异"
            return "分析完成，暂无发现"

        best = max(significant, key=lambda r: abs(r.get("effect_size") or 0))
        headline = best.get("conclusion_plain", "").split("。")[0]
        if len(headline) > 80:
            headline = headline[:77] + "..."

        return headline or f"发现 {len(significant)} 项统计显著结果"

    def _generate_metric_cards(self, results: list[dict], context: dict) -> list[dict]:
        """生成指标卡片"""
        cards = []

        # 样本量
        if context.get("n_rows"):
            cards.append({"value": f"{context['n_rows']:,}", "label": "样本量"})

        # 显著发现
        n_sig = sum(1 for r in results if r.get("significance") == "significant")
        n_total = len(results)
        if n_total > 0:
            cards.append({
                "value": f"{n_sig}/{n_total}",
                "label": "显著发现",
                "trend": "up" if n_sig > n_total / 2 else None,
            })

        # 最大效应量
        sig_with_es = [r for r in results if r.get("significance") == "significant" and r.get("effect_size") is not None]
        if sig_with_es:
            best = max(sig_with_es, key=lambda r: abs(r.get("effect_size") or 0))
            cards.append({
                "value": f"{abs(best.get('effect_size')):.2f}",
                "label": f"最大效应量 ({best.get('effect_type', '')})",
            })

        return cards

    def _check_analyst_completeness(self, text: str) -> dict[str, bool]:
        """验证 Analyst 输出是否包含必要的统计结论"""
        result = validate_analysis_output(text)
        missing = [k for k, v in result.items() if not v]
        if missing:
            self._emit(EventType.AGENT_THINKING, {
                "thought": f"⚠️ Analyst 输出缺少: {', '.join(missing)}"
            })
        return result

    def _extract_key_findings(self, results: list[dict]) -> list[dict]:
        """提取关键发现"""
        findings = []

        for result in results:
            significance = result.get("significance", "")
            headline = result.get("conclusion_plain", "").split("。")[0]
            if len(headline) > 60:
                headline = headline[:57] + "..."

            # 验证 Analyst 输出的结构完整性
            validation_text = result.get("conclusion_statistical") or result.get("conclusion_plain") or ""
            completeness_check = self._check_analyst_completeness(validation_text)

            limitations = []
            missing_items = [k for k, v in completeness_check.items() if not v]
            if missing_items:
                limitations.append(f"解析验证缺少: {', '.join(missing_items)}")

            finding = {
                "analysis_type": result.get("analysis_type"),
                "question": result.get("question"),
                "conclusion_plain": result.get("conclusion_plain"),
                "p_value": result.get("p_value"),
                "effect_size": result.get("effect_size"),
                "effect_type": result.get("effect_type"),
                "significance": significance,
                "headline": headline,
                "plain_explanation": result.get("conclusion_plain"),
                "limitations": limitations,
            }

            findings.append(finding)

        return findings

    def _summarize_findings(self, findings: list[dict]) -> str:
        """总结发现"""
        if not findings:
            return "未发现显著结果。"

        n_sig = sum(1 for f in findings if f.get("significance") == "significant")
        n_total = len(findings)

        return f"在 {n_total} 项分析中，{n_sig} 项达到统计显著水平（p < 0.05）。"

    def _generate_overall_plain(self, results: list[dict]) -> str:
        """生成整体人话解读"""
        significant = [r for r in results if r.get("significance") == "significant"]
        not_sig = [r for r in results if r.get("significance") != "significant"]

        parts = []
        if significant:
            parts.append(f"在 {len(results)} 项分析中，{len(significant)} 项达到统计显著水平（p < 0.05）。")
            for r in significant[:3]:
                if r.get("conclusion_plain"):
                    parts.append(f"• {r['conclusion_plain']}")

        if not_sig:
            parts.append(f"{len(not_sig)} 项分析未达显著水平。这不是失败——它告诉我们：目前数据不足以得出强结论。")

        return "\n".join(parts) if parts else "分析完成。"

    def _build_result_section(self, result: dict) -> ReportSection:
        """构建单个结果章节"""
        title_map = {
            "regression": "📈 回归分析",
            "hypothesis_test": "🔬 假设检验",
            "trend_analysis": "📈 趋势分析",
            "correlation": "🔗 相关性分析",
        }
        title = title_map.get(result.get("analysis_type", ""), "📊 分析结果")

        headline = result.get("conclusion_plain", "").split("。")[0]
        if len(headline) > 80:
            headline = headline[:77] + "..."

        metric_cards = []
        if result.get("p_value") is not None:
            sig_label = "显著 ✅" if result.get("significance") == "significant" else "不显著"
            metric_cards.append({"value": f"p={result['p_value']:.4f}", "label": sig_label})
        if result.get("effect_size") is not None:
            metric_cards.append({
                "value": f"{abs(result['effect_size']):.2f}",
                "label": f"{result.get('effect_type', '效应量')}",
            })

        return ReportSection(
            title=title,
            content=result.get("conclusion_plain", ""),
            findings=[result],
            level=2,
            headline=headline,
            metric_cards=metric_cards,
            plain_explanation=result.get("conclusion_plain"),
        )

    def _build_business_metrics_section(self, metrics: list[dict]) -> ReportSection | None:
        """构建商业指标章节"""
        if not metrics:
            return None

        content_parts = []
        metric_cards = []

        for m in metrics:
            m_type = m.get("type", "unknown")

            if m_type == "roi":
                roi = m.get("roi", m.get("avg_roi", 0))
                roi_pct = f"{roi:.1f}%" if isinstance(roi, (int, float)) else "N/A"
                metric_cards.append({"value": roi_pct, "label": "ROI"})
                content_parts.append(f"• ROI = {roi_pct}")

            elif m_type == "roas":
                roas = m.get("roas", m.get("avg_roas", 0))
                roas_str = f"{roas:.1f}x"
                metric_cards.append({"value": roas_str, "label": "ROAS"})
                content_parts.append(f"• ROAS = {roas_str}")

        if not content_parts:
            return None

        return ReportSection(
            title="💰 商业指标",
            content="\n".join(content_parts),
            level=2,
            metric_cards=metric_cards,
        )

    def _update_own_memory(self, project_id: str, headline: str, n_findings: int, results: list[dict]) -> None:
        """更新报告记忆"""
        if "reports" not in self.memory:
            self.memory["reports"] = {}

        if project_id not in self.memory["reports"]:
            self.memory["reports"][project_id] = []

        self.memory["reports"][project_id].append({
            "date": datetime.now().strftime("%Y-%m-%d"),
            "headline": headline,
            "n_findings": n_findings,
            "significant": any(r.get("significance") == "significant" for r in results),
        })

        self._save_memory()
