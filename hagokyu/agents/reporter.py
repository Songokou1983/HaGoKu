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
from ._interactive import InteractionMixin
from .types import InteractionResult


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


class ReporterAgent(DataAgentBase, InteractionMixin):
    """报告员：用吸引力层抓住用户，用核心价值层留住用户"""

    def __init__(
        self,
        llm_config: LLMConfig,
        event_bus: EventBus,
        scribe: "ScribeAgent | None" = None,
    ) -> None:
        super().__init__(
            role="reporter",
            goal="给你一份看得懂的报告：一句话说清楚关键发现，底下有细节支撑",
            backstory=(
                "【你的职责】报告生成：把分析结果变成一份谁都看得懂的报告，核心发现要一句话说清楚。\n\n"
                "【你的边界】\n"
                "- 只负责组织已有的分析结论，不自己做统计分析\n"
                "- 不编造数据，所有内容必须来自传入的分析结果\n\n"
                "【第一步：查记忆】\n"
                "如果 memory 有这个项目的历史报告（上次报告的核心发现是什么），\n"
                "先查看是否有一贯的发现方向，本次是否有新结论或与历史结论有变化。\n\n"
                "【第二步：生成报告】\n"
                "1. 一句话核心发现（吸引眼球）\n"
                "2. 双轨结构：吸引力层（决策者看）+ 核心价值层（分析师看）\n"
                "3. 每个图表都有解读，不只是数据展示\n"
                "4. 与历史报告对比：如果发现变了，要特别标注「新发现」\n\n"
                "【第三步：写记忆】\n"
                "执行完成后，把本次核心发现总结保存到 memory，\n"
                "供下次报告生成时对比，判断是否出现新结论。\n\n"
                "【输出要求】\n"
                "- 报告语言简洁：非技术背景的人也能看懂\n"
                "- 核心发现一句话说清，细节在下方支撑\n"
                "- 统计结论附上 p 值和效应量，商业结论给出可执行建议\n"
            ),
            llm_config=llm_config,
            event_bus=event_bus,
        )
        self.scribe = scribe

        # 交互状态
        self._phase = "begin"
        self._results: list[AnalysisResult] = []
        self._context: DataContext | None = None
        self._cleaning_summary: dict[str, Any] = {}
        self._report_data: dict[str, Any] = {}
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
        business_metrics: list[dict[str, Any]] | None = None,
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

            # ── 商业指标 ─────────────────────────────────
            if business_metrics:
                biz_section = self._build_business_metrics_section(business_metrics)
                if biz_section:
                    sections.append(biz_section)

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

            # LLM 总结关键发现（自然语言回复给用户）
            if key_findings:
                findings_text = "\n".join(
                    f"- {f.get('question', '')}: {f.get('conclusion_plain', '')}"
                    for f in key_findings[:5]
                )
                llm_response = self.call_llm(
                    prompt=(
                        f"基于以下分析发现，向用户用 2-3 句话总结核心结论和可操作建议：\n{findings_text}\n"
                        f"语气：专业但易懂，像资深数据分析师在向决策者汇报。\n"
                        f"格式：结论 + 建议，各一句话。"
                    ),
                    system="你是专业数据分析师，向决策者总结分析结论和行动建议。简洁有力，2-3句话。",
                )
                if llm_response:
                    self.emit_thinking(f"📋 总结：{llm_response}")

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

    # ── 交互式接口 ────────────────────────────────────────

    def begin(
        self,
        results: list[AnalysisResult],
        context: DataContext,
        cleaning_summary: dict[str, Any] | None = None,
        *,
        project_name: str = "分析项目",
        query: str = "",
        df: pd.DataFrame | None = None,
        business_metrics: list[dict[str, Any]] | None = None,
    ) -> InteractionResult:
        """
        开始 Reporter 交互。

        流程：预览报告结构 → 确认模板 → 生成报告 → 完成
        """
        self._results = results
        self._context = context
        self._cleaning_summary = cleaning_summary or {}

        self.start()  # emits AGENT_STARTED → Scribe claims task

        self._phase = "confirm_template"

        # 提取关键信息用于确认
        key_findings = self._extract_key_findings(results)
        n_sig = sum(1 for f in key_findings if f.get("significance") == "significant")

        templates = [
            {"id": "default", "name": "标准报告", "desc": "通用双轨结构"},
            {"id": "executive_brief", "name": "高管简报", "desc": "一句话结论 + 关键指标卡片"},
            {"id": "business_analysis", "name": "业务分析", "desc": "含 ROI/渠道分析"},
            {"id": "ab_test", "name": "A/B测试", "desc": "对比实验结论"},
        ]

        # block，等用户确认模板
        if self.scribe:
            self.scribe.block_task("reporter", "等用户选择报告模板")
        return self._pause(
            phase="confirm_template",
            message=f"分析完成：{len(results)} 项分析，{n_sig} 项显著发现。请选择报告模板：",
            needs_confirmation=True,
            confirmation_prompt="选择报告模板",
            pending_items=templates,
            data={
                "n_results": len(results),
                "n_significant": n_sig,
                "key_findings": key_findings[:3],
                "project_name": project_name,
                "query": query,
                "business_metrics": business_metrics or [],
            },
        )

    def respond(
        self,
        user_input: dict,
        *,
        output_path: str | None = None,
        formats: list[str] | None = None,
        template: str | None = None,
        user_mode: str = "standard",
        df: pd.DataFrame | None = None,
    ) -> InteractionResult:
        """
        处理用户对模板的确认响应，生成最终报告。
        """
        if self._phase != "confirm_template":
            return self._done("done", "阶段错误，请重新开始", {})

        selected_template = user_input.get("selected_template", "default")
        if not template:
            template = selected_template

        # 解除 block
        if self.scribe:
            self.scribe.unblock_task("reporter")

        # 生成报告
        report = self.run(
            results=self._results,
            context=self._context,
            cleaning_summary=self._cleaning_summary,
            project_name=self._report_data.get("project_name", "分析项目"),
            query=self._report_data.get("query", ""),
            output_path=output_path,
            formats=formats,
            template=template,
            user_mode=user_mode,
            df=df,
            business_metrics=self._report_data.get("business_metrics"),
        )

        # Reporter 是最后一环，直接完成
        self.complete({"n_sections": len(report.sections), "n_findings": len(report.findings_summary) if report.findings_summary else 0})

        return self._done(
            phase="done",
            message=f"✅ 报告已生成！共 {len(report.sections)} 个章节",
            data={
                "report_sections": len(report.sections),
                "key_findings_count": len(report.findings_summary) if report.findings_summary else 0,
            },
        )

    # ── 商业指标章节 ──────────────────────────────────────

    def _build_business_metrics_section(self, metrics: list[dict[str, Any]]) -> ReportSection | None:
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
                metric_cards.append({
                    "value": roi_pct,
                    "label": "ROI（投资回报率）",
                    "trend": "up" if roi > 0 else "down" if roi < 0 else None,
                })
                interp = m.get("interpretation", "")
                content_parts.append(f"• ROI = {roi_pct}：{interp}")

            elif m_type == "roas":
                roas = m.get("roas", m.get("avg_roas", 0))
                roas_str = f"{roas:.1f}x"
                metric_cards.append({
                    "value": roas_str,
                    "label": "ROAS（广告回报）",
                    "trend": "up" if roas >= 4 else "down" if roas < 1 else None,
                })
                interp = m.get("interpretation", "")
                content_parts.append(f"• ROAS = {roas_str}：{interp}")

            elif m_type == "ltv":
                ltv = m.get("avg_ltv", 0)
                metric_cards.append({"value": f"{ltv:.2f}", "label": "LTV（用户生命周期价值）"})
                interp = m.get("interpretation", "")
                content_parts.append(f"• 平均 LTV = {ltv:.2f}：{interp}")

            elif m_type == "cac":
                cac = m.get("cac", 0)
                metric_cards.append({"value": f"{cac:.2f}", "label": "CAC（获客成本）"})
                interp = m.get("interpretation", "")
                content_parts.append(f"• 平均 CAC = {cac:.2f}：{interp}")

            elif m_type == "ltv_cac":
                ratio = m.get("ratio", 0)
                metric_cards.append({
                    "value": f"{ratio:.1f}x",
                    "label": "LTV/CAC",
                    "trend": "up" if ratio >= 3 else "down",
                })
                interp = m.get("interpretation", "")
                content_parts.append(f"• LTV/CAC = {ratio:.1f}x：{interp}")

            elif m_type == "growth":
                growth = m.get("growth_percent", "N/A")
                metric_cards.append({
                    "value": growth,
                    "label": "增长率",
                    "trend": "up" if growth and growth.startswith("+") else "down",
                })
                interp = m.get("interpretation", "")
                content_parts.append(f"• {interp}")

            elif m_type == "funnel":
                funnel = m.get("funnel", [])
                total_conv = m.get("total_conversion_percent", "N/A")
                biggest_drop = m.get("biggest_drop_stage", "")
                metric_cards.append({"value": total_conv, "label": "总体转化率"})
                funnel_lines = [f"• 漏斗共 {len(funnel)} 个阶段，总体转化 {total_conv}"]
                if biggest_drop:
                    funnel_lines.append(f"  最大流失在「{biggest_drop}」")
                for stage in funnel:
                    stage_name = stage.get("stage", "")
                    rate = stage.get("from_previous_rate", 1.0)
                    funnel_lines.append(f"  - {stage_name}: {rate*100:.1f}%")
                content_parts.extend(funnel_lines)

            elif m_type == "attribution":
                attrs = m.get("attribution", {})
                method = m.get("method", "unknown")
                best = m.get("best_channel", "")
                content_parts.append(f"• 归因方法：{method}，最优渠道：{best}")
                for ch, pct in sorted(attrs.items(), key=lambda x: x[1], reverse=True)[:5]:
                    content_parts.append(f"  - {ch}: {pct}%")

            elif m_type == "payback":
                period = m.get("payback_period")
                metric_cards.append({
                    "value": f"{period}期" if period else "未回本",
                    "label": "回本周期",
                })
                interp = m.get("interpretation", "")
                content_parts.append(f"• {interp}")

        if not content_parts:
            return None

        return ReportSection(
            title="💰 商业指标",
            content="\n".join(content_parts),
            level=2,
            metric_cards=metric_cards if metric_cards else None,
        )

    # ── 吸引力层：一眼抓住 ──────────────────────────────────

    def _generate_headline(self, results: list[AnalysisResult], context: DataContext) -> str:
        """生成报告顶部一句话结论（吸引力层核心）"""
        significant = [r for r in results if r.significance == "significant"]
        if not significant:
            if results:
                n = len(results)
                return (
                    f"{n} 项分析完成，未发现显著差异——"
                    "这本身也是重要结论，至少说明这些方向上目前数据不足以得出强结论"
                )
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
            parts.append(
                f"{len(not_sig)} 项分析未达显著水平。这不是分析失败——"
                "它告诉我们：目前的数据还不足以在这些方向上得出强结论。"
                "如果这个结论对你有用，可以考虑增加数据量后再分析。"
            )

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
