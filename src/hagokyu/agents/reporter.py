"""HaGoKu Reporter Agent — 报告员，让分析结果说话"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from ..config import LLMConfig
from ..guardrails.statistical import GuardrailResult, Severity, StatisticalGuardrails
from ..observability.event_bus import EventBus
from ..tools.reporting import ReportData, ReportGenerator, ReportSection
from ..tools.visualization import generate_data_overview_charts, generate_insight_charts
from .analyst import AnalysisResult
from .base import DataAgentBase
from .scout import DataContext


# ── 效应量大小判断 ──────────────────────────────────────────

def _effect_size_magnitude(effect_size: float | None, effect_type: str = "") -> str:
    """判断效应量大小等级"""
    if effect_size is None:
        return "unknown"
    es = abs(effect_size)
    # inf 表示完美拟合，单独处理
    if es == float("inf"):
        return "perfect"
    if "cohen" in effect_type.lower() or "d" in effect_type.lower():
        if es >= 0.8: return "large"
        if es >= 0.5: return "medium"
        return "small"
    if "eta" in effect_type.lower() or "f_sq" in effect_type.lower():
        if es >= 0.14: return "large"
        if es >= 0.06: return "medium"
        return "small"
    if "cramer" in effect_type.lower() or "v" in effect_type.lower():
        if es >= 0.16: return "large"
        if es >= 0.07: return "medium"
        return "small"
    # 通用
    if es >= 0.5: return "large"
    if es >= 0.2: return "medium"
    return "small"


def _format_effect_size(effect_size: float | None, effect_type: str = "") -> str:
    """格式化效应量显示"""
    if effect_size is None:
        return "N/A"
    es = abs(effect_size)
    if es == float("inf"):
        return "完美拟合 (R²≈1)"
    # 保留合理小数位
    if es >= 100:
        return f"{es:.0f}"
    if es >= 10:
        return f"{es:.1f}"
    return f"{es:.2f}"


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
        template: str | None = None,
        template_dir: str | None = None,
        user_mode: str = "standard",
        df: pd.DataFrame | None = None,
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
            template: 报告模板 (default/academic/brief/business_analysis/ab_test/executive_brief/data_audit)
            template_dir: 自定义模板目录
            user_mode: 用户模式 (quick / standard / expert)
            df: 清洗后数据（用于生成图表）

        Returns:
            ReportData 报告数据
        """
        self.start()

        try:
            formats = formats or ["html"]

            # 1. 构建报告结构 — 双轨
            self.emit_thinking("构建双轨报告：吸引力层 + 核心价值层...")

            # 图表输出目录
            charts_dir = None
            if output_path:
                charts_dir = Path(output_path).parent / "charts"

            sections = []

            # 核心发现摘要
            key_findings = self._extract_key_findings(results)
            if key_findings:
                sections.append(ReportSection(
                    title="🎯 核心发现",
                    content=self._summarize_key_findings(key_findings),
                    findings=key_findings,
                    level=2,
                    # 吸引力层
                    headline=self._generate_headline(results, context),
                    # 核心价值层
                    plain_explanation=self._generate_overall_plain(results),
                ))

            # 2. 数据概览图表
            overview_charts: list[dict[str, Any]] = []
            if df is not None and charts_dir:
                self.emit_thinking("生成数据概览图表...")
                self.emit_tool_call("generate_charts", "data_overview")
                try:
                    overview_charts = generate_data_overview_charts(
                        df, output_dir=charts_dir, interactive=True,
                    )
                    self.emit_tool_result(f"生成 {len(overview_charts)} 个概览图表")
                except Exception as e:
                    self.emit_tool_result(f"概览图表生成跳过: {e}")

            # 3. 洞察图表（从分析结果驱动）
            insight_charts: list[dict[str, Any]] = []
            if df is not None and charts_dir:
                self.emit_thinking("生成洞察图表...")
                self.emit_tool_call("generate_charts", "insight")
                try:
                    # 将 AnalysisResult 转为 dict 格式供 generate_insight_charts
                    result_dicts = []
                    for r in results:
                        rd = r.to_dict()
                        rd["raw_result"] = r.raw_result
                        result_dicts.append(rd)

                    insight_charts = generate_insight_charts(
                        df, result_dicts,
                        context=context.to_dict() if hasattr(context, "to_dict") else None,
                        output_dir=charts_dir,
                        interactive=True,
                    )
                    self.emit_tool_result(f"生成 {len(insight_charts)} 个洞察图表")
                except Exception as e:
                    self.emit_tool_result(f"洞察图表生成跳过: {e}")

            # 详细分析结果 — 双轨（附加图表）
            for result in results:
                section = self._build_result_section(result, user_mode)

                # 将对应的洞察图表附加到 section
                for chart in insight_charts:
                    # 匹配同类型的图表
                    chart_title = chart.get("title", "")
                    if result.analysis_type in chart_title or any(
                        kw in chart_title for kw in result.question.split()[:3]
                    ):
                        section.charts.append(chart)

                sections.append(section)

            # 数据概况章节（附加概览图表）
            data_section = ReportSection(
                title="📊 数据概况",
                content="",
                charts=overview_charts,
                level=2,
            )
            # 插入到 sections 前面（核心发现之后）
            if overview_charts:
                sections.insert(1 if len(sections) > 0 else 0, data_section)

            # 护栏检查报告
            guardrail_section = self._build_guardrail_section(results)
            if guardrail_section:
                sections.append(guardrail_section)

            # 4. 构建报告数据
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
                findings_summary=key_findings,
                # 双轨新增
                headline=self._generate_headline(results, context),
                metric_cards=self._generate_metric_cards(results, context),
                user_mode=user_mode,
            )

            # 3. 生成报告文件
            generator = ReportGenerator(
                template_dir=template_dir,
            )

            self.emit_tool_call("generate_report", f"formats={formats}, template={template or 'default'}")

            if output_path:
                if "html" in formats:
                    html_path = output_path if output_path.endswith(".html") else f"{output_path}.html"
                    generator.generate_html(report, output_path=html_path, template_name=template)
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
                html = generator.generate_html(report, template_name=template)
                self.emit_tool_result(f"HTML 报告已生成 ({len(html)} 字符)")

            self.complete({"n_sections": len(sections), "n_findings": len(key_findings)})
            return report

        except Exception as e:
            self.fail(str(e))
            # 报告生成失败 → 尝试最小化文本报告
            self.emit_event(EventType.AGENT_THINKING, {
                "thought": f"⚠️ Reporter 报告生成失败（{e}），生成最小化摘要",
            })
            key_findings = self._extract_key_findings(results)
            return ReportData(
                project_name=project_name,
                query=query,
                sections=[
                    ReportSection(
                        title="⚠️ 分析摘要（报告生成失败）",
                        content=f"分析过程出错: {e}\n\n共生成 {len(results)} 个结果。",
                        findings=key_findings,
                        level=1,
                    ),
                ],
                data_summary={
                    "n_rows": context.n_rows,
                    "n_cols": context.n_cols,
                    "quality_score": context.quality_score,
                    "null_rate": context.missing_summary.get("null_rate", "N/A"),
                },
                cleaning_summary=cleaning_summary or {},
                findings_summary=key_findings,
                headline="分析完成（报告部分失败）",
                metric_cards=[],
                user_mode=user_mode,
            )

    # ── 吸引力层：一眼抓住 ──────────────────────────────────

    def _generate_headline(self, results: list[AnalysisResult], context: DataContext) -> str:
        """生成报告顶部一句话结论（吸引力层核心）"""
        significant = [r for r in results if r.significance == "significant"]
        if not significant:
            if results:
                return f"分析完成，{len(results)} 项检验未发现统计显著结果——这本身也是重要信息"
            return "分析完成，暂无发现"

        # 取效应量最大的显著结果
        best = max(significant, key=lambda r: abs(r.effect_size) if r.effect_size else 0)
        if best.conclusion_plain:
            # 截取第一句作为 headline
            first_sentence = best.conclusion_plain.split("。")[0]
            if len(first_sentence) > 80:
                first_sentence = first_sentence[:77] + "..."
            return first_sentence

        return f"发现 {len(significant)} 项统计显著结果"

    def _generate_metric_cards(
        self, results: list[AnalysisResult], context: DataContext
    ) -> list[dict[str, Any]]:
        """生成关键指标卡片"""
        cards = []

        # 样本量卡片
        if context.n_rows:
            cards.append({"value": f"{context.n_rows:,}", "label": "样本量"})

        # 显著发现数
        n_sig = sum(1 for r in results if r.significance == "significant")
        n_total = len(results)
        if n_total > 0:
            cards.append({
                "value": f"{n_sig}/{n_total}",
                "label": "显著发现",
                "trend": "up" if n_sig > n_total / 2 else None,
            })

        # 最大效应量
        significant = [r for r in results if r.significance == "significant" and r.effect_size is not None]
        if significant:
            best = max(significant, key=lambda r: abs(r.effect_size) if r.effect_size else 0)
            magnitude = _effect_size_magnitude(best.effect_size, best.effect_type)
            cards.append({
                "value": _format_effect_size(best.effect_size, best.effect_type),
                "label": f"最大效应量 ({best.effect_type})" if best.effect_type else "最大效应量",
                "trend": "up" if magnitude in ("medium", "large", "perfect") else None,
            })

        # 数据质量
        if context.quality_score:
            cards.append({"value": f"{context.quality_score:.2f}", "label": "数据质量"})

        return cards

    # ── 核心价值层：深入看到的真东西 ────────────────────────

    def _generate_overall_plain(self, results: list[AnalysisResult]) -> str:
        """生成整体人话解读"""
        significant = [r for r in results if r.significance == "significant"]
        not_sig = [r for r in results if r.significance != "significant"]

        parts = []
        if significant:
            parts.append(f"在 {len(results)} 项分析中，{len(significant)} 项达到统计显著水平（p < 0.05）。")
            for r in significant[:3]:  # 最多列3个
                if r.conclusion_plain:
                    parts.append(f"• {r.conclusion_plain}")
        if not_sig:
            parts.append(f"{len(not_sig)} 项分析未达显著水平，这本身也是有价值的信息——说明这些方向上数据不足以支持强烈结论。")

        return "\n".join(parts) if parts else "分析完成。"

    def _extract_key_findings(self, results: list[AnalysisResult]) -> list[dict[str, Any]]:
        """提取关键发现（双轨：headline + 人话 + 统计证据 + 局限性 + 追溯）"""
        findings = []

        for result in results:
            # 检查是否有强制级护栏违规
            has_mandatory_violation = any(
                gr.get("severity") == "mandatory" and not gr.get("passed", True)
                for gr in result.guardrail_results
            )

            # 吸引力层：一句话 headline
            headline = result.conclusion_plain.split("。")[0] if result.conclusion_plain else ""
            if len(headline) > 60:
                headline = headline[:57] + "..."

            # 核心价值层：人话解读
            plain_explanation = result.conclusion_plain if result.conclusion_plain else ""

            # 核心价值层：局限性
            limitations = []
            if result.diagnostics:
                for key, val in result.diagnostics.items():
                    if isinstance(val, dict) and not val.get("met", True):
                        limitations.append(f"{key}: {val.get('verdict', '未通过')}")
            if has_mandatory_violation:
                limitations.append("存在强制级护栏违规，结论需谨慎解读")
            if result.significance != "significant":
                limitations.append("结果未达统计显著，可能是样本量不足或效应确实不存在")
            if result.p_value is not None and result.p_value is not None and 0.05 < result.p_value < 0.10:
                limitations.append("p 值在 0.05-0.10 之间，为边缘显著，需更大样本验证")

            # 核心价值层：证据追溯
            evidence_trace = ""
            if result.conclusion_statistical:
                evidence_trace = result.conclusion_statistical
            elif result.p_value is not None:
                parts = [f"p={result.p_value:.4f}"]
                if result.effect_size is not None:
                    es_str = _format_effect_size(result.effect_size, result.effect_type)
                    parts.append(f"{result.effect_type}={es_str}")
                evidence_trace = ", ".join(parts)

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
                # 双轨新增
                "headline": headline,
                "plain_explanation": plain_explanation,
                "limitations": limitations,
                "evidence_trace": evidence_trace,
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

    def _build_result_section(self, result: AnalysisResult, user_mode: str = "standard") -> ReportSection:
        """构建单个分析结果的章节（双轨）"""
        # 章节标题
        title_map = {
            "regression": "📈 回归分析",
            "hypothesis_test": "🔬 假设检验",
            "trend_analysis": "📈 趋势分析",
            "correlation": "🔗 相关性分析",
            "chi_square_test": "📊 卡方检验",
        }
        title = title_map.get(result.analysis_type, f"📊 {result.analysis_type}")

        # 吸引力层：headline
        headline = result.conclusion_plain.split("。")[0] if result.conclusion_plain else None
        if headline and len(headline) > 80:
            headline = headline[:77] + "..."

        # 吸引力层：指标卡片
        metric_cards = []
        if result.p_value is not None:
            sig_label = "显著 ✅" if result.significance == "significant" else "不显著"
            metric_cards.append({"value": f"p={result.p_value:.4f}", "label": sig_label})
        if result.effect_size is not None:
            magnitude = _effect_size_magnitude(result.effect_size, result.effect_type)
            magnitude_label = {"large": "大", "medium": "中", "small": "小", "perfect": "完美"}.get(magnitude, "")
            metric_cards.append({
                "value": _format_effect_size(result.effect_size, result.effect_type),
                "label": f"{result.effect_type} ({magnitude_label}效应)" if magnitude_label else result.effect_type,
            })
        if result.confidence_interval:
            metric_cards.append({"value": result.confidence_interval, "label": "95% CI"})

        # 核心价值层
        plain_explanation = result.conclusion_plain if result.conclusion_plain else None
        statistical_detail = result.conclusion_statistical if result.conclusion_statistical else None

        # 诊断信息中文解释
        DIAGNOSTIC_CHINESE = {
            "residual_normality": "残差正态性",
            "heteroscedasticity": "异方差性",
            "autocorrelation": "自相关",
            "multicollinearity": "多重共线性",
            "vif": "方差膨胀因子(VIF)",
            "durbin_watson": "Durbin-Watson检验",
            "normality_group1": "第一组正态性",
            "normality_group2": "第二组正态性",
            "equal_variance": "方差齐性",
        }
        DIAGNOSTIC_HINTS = {
            "residual_normality": "残差应接近正态分布，否则模型估计可能不准确",
            "heteroscedasticity": "残差方差应恒定，否则标准误差估计有偏",
            "autocorrelation": "相邻残差应独立，否则标准误差估计有偏",
            "multicollinearity": "VIF>10表示严重共线性，系数估计不稳定",
            "durbin_watson": "DW值接近2表示无自相关，1.5-2.5之间可接受",
        }

        # 局限性
        limitations = []
        if result.diagnostics:
            for key, val in result.diagnostics.items():
                if isinstance(val, dict) and not val.get("met", True):
                    chinese_name = DIAGNOSTIC_CHINESE.get(key, key)
                    limitations.append(f"⚠️ {chinese_name}未达标")
        if result.significance != "significant":
            limitations.append("结果未达统计显著水平")

        # 证据追溯
        evidence_trace = ""
        if result.conclusion_statistical:
            evidence_trace = f"→ {result.conclusion_statistical}"

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
            # 双轨
            "headline": headline,
            "plain_explanation": plain_explanation,
            "limitations": limitations,
            "evidence_trace": evidence_trace,
        }

        # 子章节：诊断（带中文解释）
        subsections = []
        if result.diagnostics and user_mode != "quick":
            diag_items = []
            for key, val in result.diagnostics.items():
                if isinstance(val, dict) and "verdict" in val:
                    met = val.get("met", True)
                    icon = "✅" if met else "⚠️"
                    chinese_name = DIAGNOSTIC_CHINESE.get(key, key)
                    hint = DIAGNOSTIC_HINTS.get(key, "")
                    if hint:
                        diag_items.append(f"{icon} {chinese_name}: {hint}")
                    else:
                        diag_items.append(f"{icon} {chinese_name}")

            if diag_items:
                subsections.append(ReportSection(
                    title="诊断",
                    content="\n".join(diag_items),
                    level=3,
                ))

        return ReportSection(
            title=title,
            content=result.conclusion_plain,
            findings=[finding],
            subsections=subsections,
            level=2,
            # 吸引力层
            headline=headline,
            metric_cards=metric_cards,
            # 核心价值层
            plain_explanation=plain_explanation,
            statistical_detail=statistical_detail,
            limitations=limitations,
            evidence_trace=evidence_trace,
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
        limitations = []
        if mandatory:
            content_parts.append(f"🚫 强制级违规 {len(mandatory)} 项：")
            for m in mandatory:
                content_parts.append(f"  - {m['rule']}: {m['message']}")
            limitations.append(f"存在 {len(mandatory)} 项强制级统计护栏违规，结论需极度谨慎")
        if warning:
            content_parts.append(f"⚠️ 警告 {len(warning)} 项")
            limitations.append(f"存在 {len(warning)} 项警告级统计问题")
        if suggestion:
            content_parts.append(f"💡 建议 {len(suggestion)} 项")

        return ReportSection(
            title="🛡️ 统计护栏检查",
            content="\n".join(content_parts),
            level=2,
            limitations=limitations,
        )
