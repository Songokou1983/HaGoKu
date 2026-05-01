"""HaGoKu Reporter Agent — 报告员，让分析结果说话"""

from __future__ import annotations

from typing import Any

from ..config import LLMConfig
from ..guardrails.statistical import GuardrailResult, Severity, StatisticalGuardrails
from ..observability.event_bus import EventBus
from ..tools.reporting import ReportData, ReportGenerator, ReportSection
from .analyst import AnalysisResult
from .base import DataAgentBase
from .scout import DataContext


class ReporterAgent(DataAgentBase):
    """报告员：用吸引力层抓住用户，用核心价值层留住用户"""

    def __init__(self, llm_config: LLMConfig, event_bus: EventBus) -> None:
        super().__init__(
            role="Reporter",
            goal="生成精准、有洞察的报告，吸引力层 + 核心价值层",
            backstory=(
                "你是报告员。你写报告遵循两个原则：\n"
                "1. 吸引力层：用关键数字和结论快速抓住读者注意力\n"
                "2. 核心价值层：用完整的统计证据支撑每个结论\n"
                "你绝不写空洞的'数据表明...'，每个结论都配 p 值、效应量和置信区间。"
                "你把复杂的统计结果翻译成人话，但不丢失严谨性。"
            ),
            llm_config=llm_config,
            event_bus=event_bus,
        )

    def run(
        self,
        results: list[AnalysisResult],
        context: DataContext,
        cleaning_summary: dict[str, Any] | None = None,
        *,
        project_name: str = "分析项目",
        query: str = "",
        output_path: str | None = None,
        formats: list[str] | None = None,
        template_dir: str | None = None,
    ) -> ReportData:
        """
        生成分析报告

        Args:
            results: 分析结果列表
            context: 数据上下文
            cleaning_summary: 清洗摘要
            project_name: 项目名
            query: 研究问题
            output_path: 输出路径
            formats: 输出格式列表 (html / md / json)
            template_dir: 自定义模板目录

        Returns:
            ReportData 报告数据
        """
        self.start()

        try:
            formats = formats or ["html"]

            # 1. 构建报告结构
            self.emit_thinking("构建报告结构...")

            sections = []

            # 核心发现摘要
            key_findings = self._extract_key_findings(results)
            if key_findings:
                sections.append(ReportSection(
                    title="🎯 核心发现",
                    content=self._summarize_key_findings(key_findings),
                    findings=key_findings,
                    level=2,
                ))

            # 详细分析结果
            for result in results:
                section = self._build_result_section(result)
                sections.append(section)

            # 护栏检查报告
            guardrail_section = self._build_guardrail_section(results)
            if guardrail_section:
                sections.append(guardrail_section)

            # 2. 构建报告数据
            report = ReportData(
                project_name=project_name,
                query=query,
                sections=sections,
                data_summary={
                    "n_rows": context.n_rows,
                    "n_cols": context.n_cols,
                    "quality_score": context.quality_score,
                    "null_rate": context.missing_summary.get("null_rate", "N/A"),
                },
                cleaning_summary=cleaning_summary,
                findings_summary=[f.to_dict() for f in key_findings],
            )

            # 3. 生成报告文件
            generator = ReportGenerator(
                template_dir=template_dir,
            )

            self.emit_tool_call("generate_report", f"formats={formats}")

            if output_path:
                if "html" in formats:
                    html_path = output_path if output_path.endswith(".html") else f"{output_path}.html"
                    generator.generate_html(report, output_path=html_path)
                    self.emit_tool_result(f"HTML: {html_path}")

                if "md" in formats:
                    md_path = output_path.replace(".html", ".md") if output_path.endswith(".html") else f"{output_path}.md"
                    generator.generate_markdown(report, output_path=md_path)
                    self.emit_tool_result(f"Markdown: {md_path}")

                if "json" in formats:
                    json_path = output_path.replace(".html", ".json") if output_path.endswith(".html") else f"{output_path}.json"
                    generator.generate_json(report, output_path=json_path)
                    self.emit_tool_result(f"JSON: {json_path}")
            else:
                # 只生成 HTML
                html = generator.generate_html(report)
                self.emit_tool_result(f"HTML 报告已生成 ({len(html)} 字符)")

            self.complete({"n_sections": len(sections), "n_findings": len(key_findings)})
            return report

        except Exception as e:
            self.fail(str(e))
            raise

    def _extract_key_findings(self, results: list[AnalysisResult]) -> list[dict[str, Any]]:
        """提取关键发现（显著性 + 大效应量）"""
        findings = []

        for result in results:
            # 检查是否有强制级护栏违规
            has_mandatory_violation = any(
                gr.get("severity") == "mandatory" and not gr.get("passed", True)
                for gr in result.guardrail_results
            )

            finding = {
                "analysis_type": result.analysis_type,
                "question": result.question,
                "conclusion_plain": result.conclusion_plain,
                "p_value": result.p_value,
                "effect_size": result.effect_size,
                "effect_type": result.effect_type,
                "confidence_interval": result.confidence_interval,
                "significance": result.significance,
                "has_guardrail_issue": has_mandatory_violation,
            }
            findings.append(finding)

        return findings

    def _summarize_key_findings(self, findings: list[dict[str, Any]]) -> str:
        """总结核心发现"""
        if not findings:
            return "未发现显著结果。"

        significant = [f for f in findings if f.get("significance") == "significant"]
        n_total = len(findings)

        if significant:
            return f"在 {n_total} 项分析中，{len(significant)} 项达到统计显著水平（p < 0.05）。"
        else:
            return f"在 {n_total} 项分析中，未发现统计显著的结果。这本身也是重要信息。"

    def _build_result_section(self, result: AnalysisResult) -> ReportSection:
        """构建单个分析结果的章节"""
        # 章节标题
        title_map = {
            "regression": "📈 回归分析",
            "hypothesis_test": "🔬 假设检验",
            "trend_analysis": "📈 趋势分析",
            "correlation": "🔗 相关性分析",
            "chi_square_test": "📊 卡方检验",
        }
        title = title_map.get(result.analysis_type, f"📊 {result.analysis_type}")

        # 内容
        content = result.conclusion_plain

        # 发现
        finding = {
            "question": result.question,
            "conclusion_plain": result.conclusion_plain,
            "conclusion_statistical": result.conclusion_statistical,
            "p_value": result.p_value,
            "effect_size": result.effect_size,
            "effect_type": result.effect_type,
            "confidence_interval": result.confidence_interval,
            "significance": result.significance,
        }

        # 子章节：诊断
        subsections = []
        if result.diagnostics:
            diag_items = []
            for key, val in result.diagnostics.items():
                if isinstance(val, dict) and "verdict" in val:
                    met = val.get("met", True)
                    icon = "✅" if met else "⚠️"
                    diag_items.append(f"{icon} {key}: {val['verdict']}")

            if diag_items:
                subsections.append(ReportSection(
                    title="诊断",
                    content="\n".join(diag_items),
                    level=3,
                ))

        return ReportSection(
            title=title,
            content=content,
            findings=[finding],
            subsections=subsections,
            level=2,
        )

    def _build_guardrail_section(self, results: list[AnalysisResult]) -> ReportSection | None:
        """构建护栏检查报告章节"""
        all_issues: list[dict[str, Any]] = []

        for result in results:
            for gr in result.guardrail_results:
                if not gr.get("passed", True):
                    all_issues.append({
                        "rule": gr.get("rule", ""),
                        "severity": gr.get("severity", ""),
                        "message": gr.get("message", ""),
                        "suggestion": gr.get("suggestion", ""),
                        "analysis_type": result.analysis_type,
                    })

        if not all_issues:
            return None

        # 按严重级别分组
        mandatory = [i for i in all_issues if i["severity"] == "mandatory"]
        warning = [i for i in all_issues if i["severity"] == "warning"]
        suggestion = [i for i in all_issues if i["severity"] == "suggestion"]

        content_parts = []
        if mandatory:
            content_parts.append(f"🚫 强制级违规 {len(mandatory)} 项：")
            for m in mandatory:
                content_parts.append(f"  - {m['rule']}: {m['message']}")
        if warning:
            content_parts.append(f"⚠️ 警告 {len(warning)} 项")
        if suggestion:
            content_parts.append(f"💡 建议 {len(suggestion)} 项")

        return ReportSection(
            title="🛡️ 统计护栏检查",
            content="\n".join(content_parts),
            level=2,
        )
