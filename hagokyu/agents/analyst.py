"""HaGoKu Analyst Agent — 数理分析核心，精、准、狠"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

import pandas as pd

from ..config import LLMConfig
from ..guardrails.statistical import StatisticalGuardrails
from ..observability.event_bus import EventBus
from ..observability.events import EventType
from ..tools.analysis import (
    anova,
    check_test_assumptions,
    correlation,
    cross_validate,
    interaction_analysis,
    kruskal_wallis,
    mann_whitney_u,
    multiple_comparison_correction,
    regression,
    ttest,
)
from ..tools.analysis_registry import analysis_registry, load_plugins
from ..tools.power_analysis import (
    assess_power_for_data,
    interpret_nonsignificant_result,
    power_ttest,
    power_anova,
    power_correlation,
    power_regression,
)
from .base import DataAgentBase
from .scout import DataContext, SemanticType


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


class AnalystAgent(DataAgentBase):
    """数理分析员：用统计方法挖出数据背后的真相"""

    def __init__(self, llm_config: LLMConfig, event_bus: EventBus) -> None:
        super().__init__(
            role="Analyst",
            goal="用统计方法回答你的问题，每个结论都有数据支撑，不会乱下结论",
            backstory=(
                "【你的职责】统计分析：用统计方法挖出数据背后的结论，每个结论都有 p 值、效应量、置信区间支撑。\n\n"
                "【你的边界】\n"
                "- 只做统计分析和结论输出，不做数据清洗，不生成报告文件\n"
                "- 观测数据不能声称因果，只能说「存在关联」\n"
                "- 数据量不够时，先告知功效不足，不要硬跑\n\n"
                "【第一步：查记忆】\n"
                "如果 memory 有这个项目的历史分析模式（之前跑过什么分析、什么结论），\n"
                "先查看已有哪些分析结果，避免重复分析，优先在已有结论上扩展。\n\n"
                "【第二步：执行分析】\n"
                "1. 对比类问题（哪组更好）：t 检验或 Mann-Whitney U\n"
                "2. 多组对比：ANOVA 或 Kruskal-Wallis\n"
                "3. 找关系（哪些因素影响结果）：回归分析\n"
                "4. 趋势/时间序列：趋势分析或时间序列分析\n"
                "5. 相关性：Pearson 或 Spearman 相关系数\n"
                "6. 广告/营销效果：ROI/ROAS/LTV/CAC 分析\n"
                "7. 渠道归因：首次/末次触达/线性归因\n"
                "8. 转化漏斗：funnel 转化率分析\n\n"
                "【功效分析】\n"
                "1. 分析前：评估当前数据量能否检测到中等效应\n"
                "2. 分析后：结果不显著时，判断是「真的没效应」还是「数据不够」\n\n"
                "【结论质量标准】\n"
                "1. 每个结论必须附带 p 值或检验统计量\n"
                "2. 显著结果必须附带效应量（说明实际大小）\n"
                "3. 估计结果必须附带置信区间\n"
                "4. 回归模型必须附带诊断结果\n\n"
                "【第三步：写记忆】\n"
                "执行完成后，把本次分析的类型和结论保存到 memory，\n"
                "供下次分析时判断哪些分析已经跑过、哪些还需要补充。\n\n"
                "【输出要求】\n"
                "- 结论用商业语言表述，不要只给统计数字\n"
                "- 结论必须包含统计学意义（p 值）和实际意义（效应量）\n"
            ),
            llm_config=llm_config,
            event_bus=event_bus,
        )
        self.guardrails = StatisticalGuardrails()

    def run(
        self,
        df: pd.DataFrame,
        context: DataContext,
        plan: dict[str, Any],
        phase: str = "full",
    ) -> tuple[list[AnalysisResult], list[dict[str, Any]]] | dict[str, Any]:
        """
        执行统计分析

        Args:
            df: 清洗后的数据
            context: 数据上下文
            plan: Manager 的分析计划
            phase: "full"=完整分析, "preliminary"=初步发现，返回供用户确认方向

        Returns:
            phase="full": (分析结果列表, 商业指标列表)
            phase="preliminary": {
                "status": "analyst_preliminary",
                "power_warnings": list[str],
                "business_metrics": list[dict],
                "preliminary_findings": list[dict],  # 每个分析类型的初步发现摘要
                "suggested_focus": str,               # 建议重点关注的方向
            }
        """
        self.start()

        try:
            results: list[AnalysisResult] = []
            business_metrics: list[dict[str, Any]] = []
            focus = plan.get("analyst_focus", [])
            target_col = plan.get("target")
            query = plan.get("query", "")
            n = len(df)

            self.emit_thinking(f"分析计划: focus={focus}, target={target_col}")

            # ── 功效预检：在跑分析前告诉用户数据够不够 ──────────
            power_warnings = self._check_power_before_analysis(df, context, focus, n)
            for warning in power_warnings:
                self.emit_thinking(f"💡 {warning}")

            # ── 商业指标检测 ─────────────────────────────────
            business_metrics = self._detect_business_metrics(df, context, query)

            # 根据计划执行分析
            if "regression" in focus or "causal" in focus:
                result = self._do_regression(df, context, target_col, query)
                if result:
                    results.append(result)

            if "hypothesis_test" in focus or "effect_size" in focus:
                result = self._do_hypothesis_test(df, context, target_col)
                if result:
                    results.append(result)

            if "trend" in focus or "time_series" in focus:
                result = self._do_trend_analysis(df, context, target_col)
                if result:
                    results.append(result)

            if "correlation" in focus:
                result = self._do_correlation_analysis(df, context)
                if result:
                    results.append(result)

            # 如果没有匹配到特定分析类型，做通用分析
            if not results:
                results = self._auto_analyze(df, context, target_col, query)

            # ── phase="preliminary"：初步发现阶段，暂停供用户确认分析方向 ──
            if phase == "preliminary":
                self.emit_thinking("初步分析完成，等待用户确认分析方向...")
                self.emit_event(EventType.AGENT_COMPLETED, {
                    "agent": "Analyst",
                    "result_summary": f"初步发现 {len(results)} 个，待用户确认方向",
                })
                # 汇总每个分析类型的初步发现
                preliminary_findings = []
                for r in results:
                    preliminary_findings.append({
                        "type": r.analysis_type,
                        "question": r.question,
                        "p_value": r.p_value,
                        "significance": r.significance,
                        "effect_size": r.effect_size,
                        "effect_type": r.effect_type,
                        "top_features": getattr(r, "top_features", [])[:5] if hasattr(r, "top_features") else [],
                        "trend_direction": getattr(r, "trend_direction", None) if hasattr(r, "trend_direction") else None,
                    })
                # 建议重点方向（基于初步结果）
                suggested = ""
                if results:
                    top = results[0]
                    if top.significance == "significant":
                        suggested = f"初步发现「{top.question}」具有统计显著性，建议重点分析"
                    else:
                        suggested = "初步结果均不显著，建议扩大样本或调整分析维度"
                return {
                    "status": "analyst_preliminary",
                    "power_warnings": power_warnings,
                    "business_metrics": business_metrics,
                    "preliminary_findings": preliminary_findings,
                    "suggested_focus": suggested,
                }

            # 增强诊断：对回归结果做交叉验证
            for result in results:
                if result.analysis_type == "regression" and result.raw_result:
                    self._enhance_with_cv(df, context, result, target_col)

            # 增强诊断：对多结果做多重比较校正
            if len(results) > 1:
                self._apply_multiple_comparison(results)

            # 增强诊断：尝试交互效应分析
            if "regression" in focus or "causal" in focus:
                interaction_result = self._do_interaction_analysis(df, context, target_col)
                if interaction_result:
                    results.append(interaction_result)

            # 🎯 情绪价值：分析完成的鼓励
            if results:
                n_sig = sum(1 for r in results if r.significance == "significant")
                if n_sig > 0:
                    self.emit_thinking(f"🎉 找到 {n_sig} 项显著发现！数据在说话")
                else:
                    self.emit_thinking("本次分析未发现显著结果——这也是有价值的结论，至少排除了这些可能性")

            # ── 功效解读：对不显著结果判断原因 ─────────────
            for result in results:
                if result.significance != "significant" and result.p_value is not None:
                    power_interp = self._interpret_result_power(
                        result, df, context, n
                    )
                    if power_interp:
                        self.emit_thinking(f"💡 {power_interp}")

            # 对每个结果运行统计护栏
            for result in results:
                guardrail_results = self.guardrails.check(result.to_dict())
                result.guardrail_results = [gr.model_dump() for gr in guardrail_results]

                # 质量检查事件
                violations = self.guardrails.get_violations(guardrail_results)
                if violations:
                    self.emit_event(
                        EventType.QUALITY_CHECK,
                        {
                            "verdict": "fail" if violations.get("mandatory") else "warning",
                            "detail": f"{sum(len(v) for v in violations.values())} 个护栏问题",
                        },
                    )

                # 如果有强制级违规，补充说明
                mandatory_violations = [gr for gr in guardrail_results if not gr.passed and gr.severity.value == "mandatory"]
                if mandatory_violations:
                    for mv in mandatory_violations:
                        self.emit_thinking(f"🚫 统计质量问题（严重）: {mv.message}")

            # LLM 总结分析结论（自然语言回复）
            if results:
                top = results[0]
                summary_parts = [f"**{top.question}**："]
                if top.p_value is not None:
                    sig = "显著" if top.significance == "significant" else "不显著"
                    summary_parts.append(f"p={top.p_value:.4f}（{sig}）")
                if top.effect_size is not None:
                    summary_parts.append(f"效应量={top.effect_size:.3f}")
                if top.conclusion_plain:
                    summary_parts.append(top.conclusion_plain)
                result_summary = "，".join(summary_parts)

                llm_response = self.call_llm(
                    prompt=(
                        f"向用户用 1-2 句话解释这个分析结论：\n{result_summary}\n"
                        f"如果 p < 0.05，用肯定语气说发现了什么。\n"
                        f"如果 p >= 0.05，用中性语气说没有发现显著关系，并提示可能原因。\n"
                        f"商业场景下，这个结论意味着什么？"
                    ),
                    system="你是专业数据分析师，用商业易懂的语言解释统计结论。100字以内。",
                )
                if llm_response:
                    self.emit_thinking(f"📊 结论：{llm_response}")

            self.complete({"n_results": len(results), "n_business_metrics": len(business_metrics)})
            # 附上商业指标到结果中（Reporter 需要）
            return results, business_metrics

        except Exception as e:
            # 不崩溃：发射警告，返回已有的部分结果（如果有的话）
            self.fail("分析过程遇到问题")
            self.emit_event(EventType.AGENT_THINKING, {
                "thought": f"⚠️ 分析过程中出现问题，将尝试继续生成报告: {e}",
            })
            # preliminary 阶段出错也返回结构化数据
            if phase == "preliminary":
                return {
                    "status": "analyst_preliminary",
                    "power_warnings": power_warnings,
                    "business_metrics": business_metrics,
                    "preliminary_findings": [],
                    "suggested_focus": "分析遇到问题，请检查数据或重试",
                    "error": str(e),
                }
            return results if results else [], []

    def _do_regression(
        self,
        df: pd.DataFrame,
        context: DataContext,
        target_col: str | None,
        query: str,
    ) -> AnalysisResult | None:
        """回归分析"""
        if not target_col:
            # 尝试从上下文中找目标变量
            target_candidates = context.get_target_candidates()
            if not target_candidates:
                self.emit_thinking("无法确定因变量，跳过回归分析")
                return None
            target_col = target_candidates[0].column_name

        # 确定自变量：直接使用 Scout 推导的 variable_roles（已排除 identifier/ignore）
        # Scout.derive_from_column_semantics() 已完成 role 归类，无需重复过滤
        variable_roles = context.variable_roles or {}
        numeric_features = [
            col
            for col, role in variable_roles.items()
            if role in ("numeric_feature", "binary_feature")
            and col in df.columns
            and col != target_col
        ]

        if not numeric_features:
            self.emit_thinking("无数值型自变量，跳过回归")
            return None

        # 只保留数据中实际存在的列
        available_features = [f for f in numeric_features if f in df.columns]
        if not available_features:
            return None

        self.emit_thinking(f"回归分析: {target_col} ~ {'+'.join(available_features[:5])}")

        # 假设检验前置检查
        self.emit_tool_call("check_test_assumptions", "regression")
        assumption_check = check_test_assumptions(
            df, "regression", target=target_col, features=available_features
        )
        if not assumption_check.get("all_assumptions_met", True):
            warnings = assumption_check.get("warnings", [])
            if warnings:
                self.emit_thinking(f"⚠️ 假设检查: {'; '.join(warnings)}")
            rec = assumption_check.get("recommendation")
            if rec:
                self.emit_thinking(f"💡 建议: {rec}")

        self.emit_tool_call("regression", f"target={target_col}")

        try:
            reg_result = regression(df, target_col, available_features, method="ols")
            if "error" in reg_result:
                self.emit_tool_error(f"回归分析失败: {reg_result['message']}")
                return None
            self.emit_tool_result(f"R²={reg_result.get('r_squared', 'N/A'):.3f}")

            # 诊断
            if reg_result.get("diagnostics"):
                diag = reg_result["diagnostics"]
                self.emit_tool_call("diagnose_regression")
                self.emit_tool_result(
                    f"DW={diag.get('autocorrelation', {}).get('statistic', 'N/A'):.2f}"
                    if diag.get("autocorrelation") else "诊断完成"
                )

            # 构建结论
            r_sq = reg_result.get("r_squared", 0)
            f_p = reg_result.get("f_pvalue", 1)
            coeffs = reg_result.get("coefficients", {})
            p_values = reg_result.get("p_values", {})

            # 找显著的自变量
            significant_predictors = [
                f for f in available_features
                if f in p_values and p_values[f] < 0.05
            ]

            if r_sq is not None:
                conclusion = (
                    f"回归模型 R²={r_sq:.3f}，"
                    f"{'模型整体显著' if f_p is not None and 0 <= f_p < 0.05 else '模型整体不显著'}。"
                )
                if significant_predictors:
                    conclusion += f"显著预测变量: {', '.join(significant_predictors[:3])}。"
            else:
                conclusion = "回归分析完成。"

            reg_result["target"] = target_col
            reg_result["features"] = available_features
            return AnalysisResult(
                result_id=uuid4().hex[:8],
                analysis_type="regression",
                question=f"{target_col} 的预测因素是什么？",
                conclusion_plain=conclusion,
                conclusion_statistical=str(reg_result.get("coefficients", {})),
                p_value=f_p,
                effect_size=reg_result.get("effect_size"),
                effect_type=reg_result.get("effect_type", ""),
                significance="significant" if f_p is not None and 0 <= f_p < 0.05 else "not_significant",
                sample_size=reg_result.get("n_obs"),
                diagnostics=reg_result.get("diagnostics"),
                raw_result=reg_result,
            )

        except Exception as e:
            self.emit_tool_error(f"回归分析遇到问题，可能需要检查数据质量或样本量")
            return None

    def _do_hypothesis_test(
        self,
        df: pd.DataFrame,
        context: DataContext,
        target_col: str | None,
    ) -> AnalysisResult | None:
        """假设检验"""
        # 找分组变量
        cat_cols = [
            sem.column_name
            for sem in context.column_semantics
            if sem.inferred_type in (SemanticType.CATEGORICAL, SemanticType.BOOLEAN, SemanticType.ORDINAL)
            and sem.column_name in df.columns
        ]

        num_cols = [
            sem.column_name
            for sem in context.column_semantics
            if sem.inferred_type == SemanticType.NUMERIC
            and sem.suggested_role != "identifier"
            and sem.column_name in df.columns
        ]

        if not target_col:
            target_col = num_cols[0] if num_cols else None

        if not target_col or not cat_cols:
            self.emit_thinking("无法确定检验变量组合，跳过假设检验")
            return None

        # 选第一个分类变量做分组
        group_col = cat_cols[0]
        n_groups = df[group_col].nunique()

        self.emit_thinking(f"假设检验: {target_col} by {group_col} ({n_groups} 组)")

        # 假设检验前置检查
        test_type = "ttest" if n_groups == 2 else "anova"
        self.emit_tool_call("check_test_assumptions", test_type)
        assumption_check = check_test_assumptions(
            df, test_type, target=target_col, group_col=group_col
        )
        if not assumption_check.get("all_assumptions_met", True):
            warnings = assumption_check.get("warnings", [])
            if warnings:
                self.emit_thinking(f"⚠️ 假设检查: {'; '.join(warnings)}")
            rec = assumption_check.get("recommendation")
            if rec:
                self.emit_thinking(f"💡 建议: {rec}")
                # 如果正态性不满足，自动切换到非参数方法
                if "正态性" in "; ".join(warnings):
                    if n_groups == 2:
                        self.emit_thinking("自动切换到 Mann-Whitney U 检验")
                        test_type = "mann_whitney"
                    else:
                        self.emit_thinking("自动切换到 Kruskal-Wallis H 检验")
                        test_type = "kruskal_wallis"

        self.emit_tool_call("ttest" if n_groups == 2 else "anova", f"{target_col} by {group_col}")

        try:
            if n_groups == 2:
                groups = df.groupby(group_col)[target_col]
                group_names = list(groups.groups.keys())
                g1 = groups.get_group(group_names[0]).dropna()
                g2 = groups.get_group(group_names[1]).dropna()

                # 数据不足检查
                if len(g1) < 3 or len(g2) < 3:
                    self.emit_thinking(f"某组数据不足 (n1={len(g1)}, n2={len(g2)})，跳过假设检验")
                    return None

                # 如果假设检查建议非参数方法，使用 Mann-Whitney U
                if test_type == "mann_whitney":
                    test_result = mann_whitney_u(g1, g2)
                    if "error" in test_result:
                        self.emit_tool_error(f"非参数检验失败（适用于非正态数据），可能需要检查数据分布")
                        return None
                    self.emit_tool_result(f"p={test_result['p_value']:.4f}, r={test_result['effect_size']:.3f}")
                    sig = "significant" if test_result["p_value"] < 0.05 else "not_significant"
                    medians = [float(g1.median()), float(g2.median())]
                    conclusion = (
                        f"{group_names[0]} (Mdn={medians[0]:.2f}) vs "
                        f"{group_names[1]} (Mdn={medians[1]:.2f})，"
                        f"{'差异显著' if sig == 'significant' else '差异不显著'}"
                        f"(U={test_result['statistic']:.1f}, p={test_result['p_value']:.4f}, r={test_result['effect_size']:.3f})"
                    )
                    test_result["target"] = target_col
                    test_result["group_col"] = group_col
                    return AnalysisResult(
                        result_id=uuid4().hex[:8],
                        analysis_type="hypothesis_test_mann_whitney",
                        question=f"不同 {group_col} 组的 {target_col} 有差异吗？",
                        conclusion_plain=conclusion,
                        p_value=test_result["p_value"],
                        effect_size=test_result["effect_size"],
                        effect_type=test_result.get("effect_type", ""),
                        significance=sig,
                        sample_size=len(df),
                        test_statistic=test_result.get("statistic"),
                        raw_result=test_result,
                    )

                test_result = ttest(g1, g2)
                if "error" in test_result:
                    self.emit_tool_error(f"两组均值比较检验失败，可能需要检查数据正态性或样本量")
                    return None
                self.emit_tool_result(f"p={test_result['p_value']:.4f}, d={test_result['effect_size']:.3f}")

                sig = "significant" if test_result["p_value"] < 0.05 else "not_significant"
                means = [float(g1.mean()), float(g2.mean())]
                conclusion = (
                    f"{group_names[0]} (M={means[0]:.2f}) vs "
                    f"{group_names[1]} (M={means[1]:.2f})，"
                    f"{'差异显著' if sig == 'significant' else '差异不显著'}"
                    f"(p={test_result['p_value']:.4f}, d={test_result['effect_size']:.3f})"
                )

            else:
                # 如果假设检查建议非参数方法，使用 Kruskal-Wallis
                if test_type == "kruskal_wallis":
                    test_result = kruskal_wallis(df, dv=target_col, between=group_col)
                    if "error" in test_result:
                        self.emit_tool_error(f"多组均值比较检验失败，可能需要检查数据分布或样本量")
                        return None
                    self.emit_tool_result(f"p={test_result['p_value']:.4f}, η²_H={test_result['effect_size']:.3f}")
                    sig = "significant" if test_result["p_value"] < 0.05 else "not_significant"
                    conclusion = (
                        f"{n_groups} 组 {target_col} 中位数"
                        f"{'差异显著' if sig == 'significant' else '差异不显著'}"
                        f"(H={test_result['statistic']:.2f}, p={test_result['p_value']:.4f}, η²_H={test_result['effect_size']:.3f})"
                    )
                    test_result["target"] = target_col
                    test_result["group_col"] = group_col
                    return AnalysisResult(
                        result_id=uuid4().hex[:8],
                        analysis_type="hypothesis_test_kruskal_wallis",
                        question=f"不同 {group_col} 组的 {target_col} 有差异吗？",
                        conclusion_plain=conclusion,
                        p_value=test_result["p_value"],
                        effect_size=test_result["effect_size"],
                        effect_type=test_result.get("effect_type", ""),
                        significance=sig,
                        sample_size=len(df),
                        test_statistic=test_result.get("statistic"),
                        raw_result=test_result,
                    )

                test_result = anova(df, dv=target_col, between=group_col)
                if "error" in test_result:
                    self.emit_tool_error(f"多组均值比较（方差分析）失败，可能需要检查数据正态性和方差齐性")
                    return None
                self.emit_tool_result(f"p={test_result['p_value']:.4f}, η²={test_result['effect_size']:.3f}")

                sig = "significant" if test_result["p_value"] < 0.05 else "not_significant"
                conclusion = (
                    f"{n_groups} 组 {target_col} 均值"
                    f"{'差异显著' if sig == 'significant' else '差异不显著'}"
                    f"(F={test_result['f_statistic']:.2f}, p={test_result['p_value']:.4f}, η²={test_result['effect_size']:.3f})"
                )

            test_result["target"] = target_col
            test_result["group_col"] = group_col
            return AnalysisResult(
                result_id=uuid4().hex[:8],
                analysis_type="hypothesis_test",
                question=f"不同 {group_col} 组的 {target_col} 有差异吗？",
                conclusion_plain=conclusion,
                p_value=test_result["p_value"],
                effect_size=test_result["effect_size"],
                effect_type=test_result.get("effect_type", ""),
                significance=sig,
                sample_size=len(df),
                test_statistic=test_result.get("statistic", test_result.get("f_statistic")),
                raw_result=test_result,
            )

        except Exception:
            self.emit_tool_error("统计检验遇到问题，可能与数据质量或检验条件有关")
            return None

    def _do_trend_analysis(
        self,
        df: pd.DataFrame,
        context: DataContext,
        target_col: str | None,
    ) -> AnalysisResult | None:
        """趋势分析（简化版：基于时间变量的回归）"""
        # 找时间变量
        time_cols = [
            sem.column_name
            for sem in context.column_semantics
            if sem.inferred_type == SemanticType.DATETIME
            and sem.column_name in df.columns
        ]

        if not time_cols or not target_col:
            self.emit_thinking("无法确定时间变量或目标变量，跳过趋势分析")
            return None

        time_col = time_cols[0]

        self.emit_thinking(f"趋势分析: {target_col} over {time_col}")
        self.emit_tool_call("regression", f"trend: {target_col} ~ {time_col}")

        try:
            # 将时间转为数值
            df_trend = df.copy()
            df_trend["_time_numeric"] = pd.to_datetime(df_trend[time_col]).astype(int) / 1e18

            result = regression(df_trend, target_col, ["_time_numeric"], method="ols")

            coeff = result.get("coefficients", {}).get("_time_numeric", 0)
            p_val = result.get("p_values", {}).get("_time_numeric", 1)
            r_sq = result.get("r_squared", 0)

            direction = "上升" if coeff > 0 else "下降"
            sig = "significant" if p_val < 0.05 else "not_significant"
            conclusion = (
                f"{target_col} 呈{direction}趋势"
                f"(β={coeff:.4f}, p={p_val:.4f}, R²={r_sq:.3f})"
                if p_val < 0.05
                else f"{target_col} 无显著时间趋势 (p={p_val:.4f})"
            )
            self.emit_tool_result(conclusion)

            result["target"] = target_col
            result["time_col"] = time_col
            return AnalysisResult(
                result_id=uuid4().hex[:8],
                analysis_type="trend_analysis",
                question=f"{target_col} 随时间变化趋势如何？",
                conclusion_plain=conclusion,
                p_value=p_val,
                effect_size=r_sq,
                effect_type="r_squared",
                significance=sig,
                sample_size=len(df),
                raw_result=result,
            )

        except Exception:
            self.emit_tool_error("趋势分析遇到问题，可能需要检查时间序列数据格式")
            return None

    def _do_correlation_analysis(
        self,
        df: pd.DataFrame,
        context: DataContext,
    ) -> AnalysisResult | None:
        """相关性分析"""
        numeric_cols = [
            sem.column_name
            for sem in context.column_semantics
            if sem.inferred_type == SemanticType.NUMERIC
            and sem.suggested_role != "identifier"
            and sem.column_name in df.columns
        ]

        if len(numeric_cols) < 2:
            return None

        # 找最强的相关
        best_corr = None
        best_pair = (numeric_cols[0], numeric_cols[1])  # 默认值，防止未赋值
        best_abs_r = 0

        for i, col1 in enumerate(numeric_cols):
            for col2 in numeric_cols[i + 1:]:
                try:
                    result = correlation(df, col1, col2)
                    abs_r = abs(result["statistic"])
                    if abs_r > best_abs_r:
                        best_abs_r = abs_r
                        best_corr = result
                        best_pair = (col1, col2)
                except Exception:
                    continue

        if best_corr is None:
            return None

        col1, col2 = best_pair
        r = best_corr["statistic"]
        p = best_corr["p_value"]

        best_corr["col1"] = col1
        best_corr["col2"] = col2

        sig = "significant" if p < 0.05 else "not_significant"
        direction = "正" if r > 0 else "负"
        strength = "强" if abs(r) > 0.7 else ("中" if abs(r) > 0.4 else "弱")
        conclusion = f"{col1} 与 {col2} 呈{strength}{direction}相关 (r={r:.3f}, p={p:.4f})"

        self.emit_tool_call("correlation", f"{col1} vs {col2}")
        self.emit_tool_result(conclusion)

        return AnalysisResult(
            result_id=uuid4().hex[:8],
            analysis_type="correlation",
            question=f"{col1} 与 {col2} 之间的关系？",
            conclusion_plain=conclusion,
            p_value=p,
            effect_size=abs(r),
            effect_type="pearson_r",
            significance=sig,
            sample_size=best_corr["n_observations"],
            raw_result=best_corr,
        )

    def _enhance_with_cv(
        self,
        df: pd.DataFrame,
        context: DataContext,
        result: AnalysisResult,
        target_col: str | None,
    ) -> None:
        """增强回归结果：添加交叉验证"""
        raw = result.raw_result
        features = [
            k for k in raw.get("coefficients", {}).keys()
            if k != "const" and k in df.columns
        ]
        target = target_col or result.question.split("的")[0] if "的" in result.question else None

        if not target or target not in df.columns or len(features) < 1:
            return

        self.emit_thinking("执行 5-fold 交叉验证...")
        self.emit_tool_call("cross_validate", f"target={target}, k=5")
        try:
            cv_result = cross_validate(df, target, features, k_folds=5)
            if "error" not in cv_result:
                # 附加到 diagnostics
                if result.diagnostics is None:
                    result.diagnostics = {}
                result.diagnostics["cross_validation"] = cv_result

                gap = cv_result.get("generalization_gap", 0)
                test_mean = cv_result.get("test_mean", 0)
                overfit = cv_result.get("overfitting_detected", False)
                self.emit_tool_result(
                    f"CV R²: train={cv_result['train_mean']:.3f}, test={test_mean:.3f}, "
                    f"gap={gap:.3f}{' ⚠️ 过拟合' if overfit else ''}"
                )
            else:
                self.emit_tool_result(f"交叉验证跳过: {cv_result.get('message', '')}")
        except Exception as e:
            self.emit_tool_result(f"交叉验证跳过: {e}")

    def _apply_multiple_comparison(self, results: list[AnalysisResult]) -> None:
        """对多个分析结果应用多重比较校正"""
        p_values = []
        for r in results:
            if r.p_value is not None and not isinstance(r.p_value, str):
                p_values.append(float(r.p_value))

        if len(p_values) < 2:
            return

        self.emit_thinking(f"多重比较校正: {len(p_values)} 个 p 值")
        self.emit_tool_call("multiple_comparison_correction", "method=bh")
        try:
            correction = multiple_comparison_correction(p_values, method="bh")
            self.emit_tool_result(correction.get("correction_note", "完成"))

            # 将校正结果附加到每个结果
            for i, result in enumerate(results):
                if i < len(correction.get("adjusted_p", [])):
                    if result.raw_result is None:
                        result.raw_result = {}
                    result.raw_result["multiple_comparison"] = {
                        "original_p": correction["original_p"][i],
                        "adjusted_p": correction["adjusted_p"][i],
                        "still_significant": correction["significant"][i],
                        "method": "Benjamini-Hochberg",
                    }
                    # 如果校正后不再显著，更新 significance
                    if not correction["significant"][i] and result.significance == "significant":
                        result.significance = "not_significant_after_correction"
                        self.emit_thinking(
                            f"⚠️ {result.analysis_type}: p={correction['original_p'][i]:.4f} "
                            f"→ 调整后 p={correction['adjusted_p'][i]:.4f}，不再显著"
                        )
        except Exception as e:
            self.emit_tool_result(f"多重比较校正跳过: {e}")

    def _do_interaction_analysis(
        self,
        df: pd.DataFrame,
        context: DataContext,
        target_col: str | None,
    ) -> AnalysisResult | None:
        """交互效应分析"""
        if not target_col or target_col not in df.columns:
            return None

        # 找两个数值型自变量
        numeric_features = [
            sem.column_name
            for sem in context.column_semantics
            if sem.inferred_type == SemanticType.NUMERIC
            and sem.suggested_role != "identifier"
            and sem.column_name in df.columns
            and sem.column_name != target_col
        ]

        if len(numeric_features) < 2:
            self.emit_thinking("交互分析需要至少 2 个数值型自变量，跳过")
            return None

        # 选前两个做交互分析
        feat1, feat2 = numeric_features[0], numeric_features[1]

        self.emit_thinking(f"交互分析: {target_col} ~ {feat1}×{feat2}")
        self.emit_tool_call("interaction_analysis", f"{feat1}×{feat2}")

        try:
            result = interaction_analysis(df, target_col, feat1, feat2)
            result["target"] = target_col
            if "error" in result:
                self.emit_tool_result(f"交互分析跳过: {result['message']}")
                return None

            sig = result.get("significance", "not_significant")
            self.emit_tool_result(
                f"交互项 p={result['p_value']:.4f}, "
                f"{'显著' if sig == 'significant' else '不显著'}, "
                f"R² 改善={result.get('r_squared_improvement', 'N/A')}"
            )

            return AnalysisResult(
                result_id=uuid4().hex[:8],
                analysis_type="interaction_analysis",
                question=f"{feat1} 和 {feat2} 对 {target_col} 是否存在交互效应？",
                conclusion_plain=result.get("interpretation", ""),
                p_value=result.get("p_value"),
                effect_size=result.get("effect_size"),
                effect_type=result.get("effect_type", ""),
                significance=sig,
                sample_size=result.get("n_observations"),
                raw_result=result,
            )
        except Exception:
            self.emit_tool_error("交互效应分析失败，可能需要更多变量数据")
            return None

    def _auto_analyze(
        self,
        df: pd.DataFrame,
        context: DataContext,
        target_col: str | None,
        query: str,
    ) -> list[AnalysisResult]:
        """
        自动分析：注册表驱动的方法发现 + 专项方法执行

        架构说明：
        - 注册表按意图关键词查找适用的分析方法
        - 专项方法（_do_regression 等）封装了复杂的执行逻辑（假设检验前置、多步诊断等）
        - 商业方法通过注册表发现，由 _detect_business_metrics 统一执行
        """
        results = []
        intent = query.lower()

        # 1. 注册表驱动：按意图发现适用的分析方法
        statistical_methods = analysis_registry.find(
            intent=intent,
            context=context,
            df=df,
            tags=["statistical", "comparison", "correlation", "regression"],
        )

        # 2. 专项方法执行（封装了复杂逻辑）
        # 这些方法包含假设前置检查、自动切换非参数等内部逻辑
        targeted_executed = set()

        for method in statistical_methods[:5]:
            if method.name in targeted_executed:
                continue

            if method.name == "regression":
                result = self._do_regression(df, context, target_col, query)
                if result:
                    results.append(result)
                    targeted_executed.add("regression")

            elif method.name in ("ttest", "mann_whitney", "anova", "kruskal_wallis", "chi_square"):
                result = self._do_hypothesis_test(df, context, target_col)
                if result:
                    results.append(result)
                    targeted_executed.add("hypothesis_test")

            elif method.name == "correlation":
                result = self._do_correlation_analysis(df, context)
                if result:
                    results.append(result)
                    targeted_executed.add("correlation")

        # 3. 如果注册表没匹配到，执行兜底专项分析
        if not targeted_executed:
            # 回归兜底
            result = self._do_regression(df, context, target_col, query)
            if result:
                results.append(result)
            # 假设检验兜底
            result = self._do_hypothesis_test(df, context, target_col)
            if result:
                results.append(result)
            # 相关性兜底
            result = self._do_correlation_analysis(df, context)
            if result:
                results.append(result)

        return results

    # ── 功效分析 ─────────────────────────────────────────

    def _check_power_before_analysis(
        self,
        df: pd.DataFrame,
        context: DataContext,
        focus: list[str],
        n: int,
    ) -> list[str]:
        """
        分析前的功效预检：告诉用户数据量够不够

        在跑分析之前评估功效，帮助用户理解结论的可靠性
        """
        warnings = []

        if n < 30:
            warnings.append(
                f"⚠️ 数据量偏少（n={n}），检验功效可能不足。"
                f"如果结果不显著，可能是真的没效应，也可能是数据不够。"
            )
            return warnings

        # 根据分析类型评估
        if "hypothesis_test" in focus or "effect_size" in focus:
            n_groups = self._count_groups(df, context)
            if n_groups >= 2:
                n_per_group = n // n_groups
                if n_per_group < 15:
                    warnings.append(
                        f"⚠️ 每组样本量偏少（n={n_per_group}），"
                        f"检测中等效应（d≈0.5）的功效可能不足。"
                    )
                elif n_per_group >= 30:
                    power_info = power_ttest(n_per_group, n_per_group, effect_size=0.5)
                    if "error" not in power_info:
                        power_pct = power_info.get("power", 0) * 100
                        if power_pct >= 80:
                            warnings.append(f"✅ 每组 n={n_per_group}，检测中等效应功效约 {power_pct:.0f}%，足够。")
                        else:
                            warnings.append(f"⚠️ 每组 n={n_per_group}，检测中等效应功效约 {power_pct:.0f}%，偏低。")

        if "regression" in focus or "causal" in focus:
            n_predictors = len([f for f in context.features if f in df.columns])
            if n_predictors > 0:
                if n < 10 * n_predictors:
                    warnings.append(
                        f"⚠️ 样本量 n={n} 与自变量数 {n_predictors} 的比例偏低，"
                        f"可能导致过拟合或估计不稳定（经验规则：n ≥ 10 × 自变量数）。"
                    )

        if "correlation" in focus:
            if n < 30:
                warnings.append(
                    f"⚠️ 相关分析需要足够样本量（n={n}），"
                    f"当前样本量下只能检测到较强的相关性。"
                )

        return warnings

    def _interpret_result_power(
        self,
        result: AnalysisResult,
        df: pd.DataFrame,
        context: DataContext,
        n: int,
    ) -> str | None:
        """
        对不显著结果做功效解读

        核心问题：p > 0.05 是因为真的没效应，还是因为数据不够？
        """
        if result.significance == "significant":
            return None

        es = result.effect_size
        es_type = result.effect_type or "cohen_d"
        if es is None:
            return None

        interp = interpret_nonsignificant_result(
            p_value=result.p_value or 1.0,
            effect_size=es,
            effect_type=es_type,
            n=result.sample_size or n,
            alpha=0.05,
        )

        if "error" in interp:
            return None

        verdict = interp.get("verdict", "")
        suggestion = interp.get("suggestion", "")

        if verdict == "likely_no_effect":
            return (
                f"功效解读：效应量 {es:.3f}（{interp.get('effect_interpretation', {}).get('label', '')}），"
                f"结果不显著更可能是效应本身很小或不存在。"
            )
        elif verdict == "possibly_underpowered":
            power = interp.get("estimated_power", 0)
            return (
                f"功效解读：检测到 {es:.3f} 效应，但当前样本量功效约 {power:.0%}（低于 80%）。"
                f"结果不显著可能是数据不够，建议增加样本后再分析。"
            )

        return None

    def _count_groups(self, df: pd.DataFrame, context: DataContext) -> int:
        """统计分组数（用于功效预检）"""
        cat_cols = [
            sem.column_name
            for sem in context.column_semantics
            if sem.inferred_type in (SemanticType.CATEGORICAL, SemanticType.BOOLEAN, SemanticType.ORDINAL)
            and sem.column_name in df.columns
        ]
        if not cat_cols:
            return 2
        return max(df[col].nunique() for col in cat_cols[:1])

    # ── 商业指标检测 ───────────────────────────────────

    def _detect_business_metrics(
        self,
        df: pd.DataFrame,
        context: DataContext,
        query: str,
    ) -> list[dict[str, Any]]:
        """
        自动检测商业指标

        架构：注册表做意图发现，专项函数执行（含智能列匹配）
        新增商业指标 = 在 business.py 添加函数 + 在注册表注册即可
        """
        metrics: list[dict[str, Any]] = []
        intent = query.lower()

        # 注册表发现适用的商业方法
        biz_methods = analysis_registry.find(
            intent=intent,
            context=context,
            df=df,
            tags=["business"],
        )

        # 按方法名执行（带智能列匹配）
        for method in biz_methods[:6]:
            mname = method.name
            mtype = mname.replace("calc_", "").replace("attribution_analysis", "attribution")

            if mtype == "roi":
                revenue_col, cost_col = self._find_cols(
                    df, ["revenue", "销售额", "收入", "gmv", "sales"],
                    ["cost", "成本", "广告费", "花费", "spend"]
                )
                if revenue_col and cost_col:
                    from ..tools.business import calc_roi
                    result = calc_roi(df[revenue_col].sum(), df[cost_col].sum())
                    if "error" not in result:
                        result["type"] = "roi"
                        metrics.append(result)

            elif mtype == "roas":
                rev_col, ad_col = self._find_cols(
                    df, ["revenue", "销售额", "收入"],
                    ["ad", "广告", "spend", "花费"]
                )
                if rev_col and ad_col:
                    from ..tools.business import calc_roas
                    result = calc_roas(df[rev_col].sum(), df[ad_col].sum())
                    if "error" not in result:
                        result["type"] = "roas"
                        metrics.append(result)

            elif mtype == "ltv":
                cust_col, rev_col = self._find_cols(
                    df, ["user", "customer", "客户", "用户", "id"],
                    ["revenue", "ltv", "value", "销售额", "消费"]
                )
                if cust_col and rev_col:
                    from ..tools.business import calc_ltv
                    result = calc_ltv(df, cust_col, rev_col)
                    if "error" not in result:
                        result["type"] = "ltv"
                        metrics.append(result)

            elif mtype == "cac":
                cust_col, cost_col = self._find_cols(
                    df, ["user", "customer", "客户", "新用户"],
                    ["cost", "成本", "广告", "花费"]
                )
                if cust_col and cost_col:
                    from ..tools.business import calc_cac
                    result = calc_cac(df, cust_col, cost_col)
                    if "error" not in result:
                        result["type"] = "cac"
                        metrics.append(result)

            elif mtype == "funnel":
                stage_col = self._find_single_col(
                    df, ["stage", "阶段", "步骤", "step", "status", "状态"]
                )
                if stage_col:
                    from ..tools.business import funnel_analysis
                    result = funnel_analysis(df, stage_col)
                    if "error" not in result:
                        result["type"] = "funnel"
                        metrics.append(result)

            elif mtype == "attribution":
                channel_col = self._find_single_col(
                    df, ["channel", "渠道", "source", "来源", "medium"]
                )
                if channel_col:
                    conv_col = self._find_single_col(
                        df, ["conversion", "转化", "purchase", "buy", "成交", "order"]
                    )
                    if conv_col:
                        from ..tools.business import attribution_analysis
                        result = attribution_analysis(df, conv_col, channel_col, method="last_touch")
                        if "error" not in result:
                            result["type"] = "attribution"
                            metrics.append(result)

            elif mtype == "cagr":
                from ..tools.business import calc_cagr
                growth_cols = self._find_numeric_pairs(df)
                for col1, col2 in growth_cols[:3]:
                    result = calc_cagr([df[col1].sum(), df[col2].sum()])
                    if "error" not in result and result.get("cagr") is not None:
                        result["type"] = "growth"
                        result["from_col"] = col1
                        result["to_col"] = col2
                        metrics.append(result)

        return metrics

    def _find_cols(
        self, df: pd.DataFrame, candidates1: list[str], candidates2: list[str]
    ) -> tuple[str | None, str | None]:
        """从候选列表中匹配两列"""
        col_lower = {c.lower(): c for c in df.columns}
        col1 = next((col_lower[c] for c in candidates1 if c.lower() in col_lower), None)
        col2 = next((col_lower[c] for c in candidates2 if c.lower() in col_lower), None)
        return col1, col2

    def _find_single_col(self, df: pd.DataFrame, candidates: list[str]) -> str | None:
        """从候选列表中匹配单列"""
        col_lower = {c.lower(): c for c in df.columns}
        return next((col_lower[c.lower()] for c in candidates if c.lower() in col_lower), None)

    def _find_numeric_pairs(self, df: pd.DataFrame) -> list[tuple[str, str]]:
        """找所有数值列对（用于增长分析）"""
        pairs = []
        num_cols = [c for c in df.columns if df[c].dtype in (int, float) and df[c].nunique() > 1]
        for i, c1 in enumerate(num_cols):
            for c2 in num_cols[i + 1:]:
                pairs.append((c1, c2))
        return pairs
