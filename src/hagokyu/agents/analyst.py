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
    chi_square,
    correlation,
    cross_validate,
    interaction_analysis,
    kruskal_wallis,
    mann_whitney_u,
    multiple_comparison_correction,
    regression,
    ttest,
)
from ..tools.diagnostics import diagnose_regression, generate_diagnostic_plots
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
            goal="用统计方法回答研究问题，效应量和 p 值缺一不可",
            backstory=(
                "你是数理分析员。你遵循严格的统计准则："
                "1. 没有统计检验不许下结论\n"
                "2. 显著性必须配效应量\n"
                "3. 点估计必须配置信区间\n"
                "4. 建模后必须做诊断\n"
                "5. 观测数据不能声称因果，除非用了因果推断方法\n"
                "你选择的统计方法必须匹配数据特征和问题类型。"
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
    ) -> list[AnalysisResult]:
        """
        执行统计分析

        Args:
            df: 清洗后的数据
            context: 数据上下文
            plan: Manager 的分析计划

        Returns:
            分析结果列表
        """
        self.start()

        try:
            results: list[AnalysisResult] = []
            focus = plan.get("analyst_focus", [])
            target_col = plan.get("target")
            query = plan.get("query", "")

            self.emit_thinking(f"分析计划: focus={focus}, target={target_col}")

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
                        self.emit_thinking(f"🚫 强制级违规: {mv.rule} - {mv.message}")

            self.complete({"n_results": len(results)})
            return results

        except Exception as e:
            self.fail(str(e))
            raise

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

        # 确定自变量
        numeric_features = [
            sem.column_name
            for sem in context.column_semantics
            if sem.inferred_type in (SemanticType.NUMERIC, SemanticType.BOOLEAN)
            and sem.suggested_role != "identifier"
            and sem.column_name != target_col
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
                    f"{'模型整体显著' if f_p and f_p < 0.05 else '模型整体不显著'}。"
                )
                if significant_predictors:
                    conclusion += f"显著预测变量: {', '.join(significant_predictors[:3])}。"
            else:
                conclusion = "回归分析完成。"

            return AnalysisResult(
                result_id=uuid4().hex[:8],
                analysis_type="regression",
                question=f"{target_col} 的预测因素是什么？",
                conclusion_plain=conclusion,
                conclusion_statistical=str(reg_result.get("coefficients", {})),
                p_value=f_p,
                effect_size=reg_result.get("effect_size"),
                effect_type=reg_result.get("effect_type", ""),
                significance="significant" if f_p and f_p < 0.05 else "not_significant",
                sample_size=reg_result.get("n_obs"),
                diagnostics=reg_result.get("diagnostics"),
                raw_result=reg_result,
            )

        except Exception as e:
            self.emit_tool_error(f"回归分析失败: {e}")
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
                        self.emit_tool_error(f"Mann-Whitney U 检验失败: {test_result['message']}")
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
                    self.emit_tool_error(f"t 检验失败: {test_result['message']}")
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
                        self.emit_tool_error(f"Kruskal-Wallis 检验失败: {test_result['message']}")
                        return None
                    self.emit_tool_result(f"p={test_result['p_value']:.4f}, η²_H={test_result['effect_size']:.3f}")
                    sig = "significant" if test_result["p_value"] < 0.05 else "not_significant"
                    conclusion = (
                        f"{n_groups} 组 {target_col} 中位数"
                        f"{'差异显著' if sig == 'significant' else '差异不显著'}"
                        f"(H={test_result['statistic']:.2f}, p={test_result['p_value']:.4f}, η²_H={test_result['effect_size']:.3f})"
                    )
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
                    self.emit_tool_error(f"ANOVA 失败: {test_result['message']}")
                    return None
                self.emit_tool_result(f"p={test_result['p_value']:.4f}, η²={test_result['effect_size']:.3f}")

                sig = "significant" if test_result["p_value"] < 0.05 else "not_significant"
                conclusion = (
                    f"{n_groups} 组 {target_col} 均值"
                    f"{'差异显著' if sig == 'significant' else '差异不显著'}"
                    f"(F={test_result['f_statistic']:.2f}, p={test_result['p_value']:.4f}, η²={test_result['effect_size']:.3f})"
                )

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

        except Exception as e:
            self.emit_tool_error(f"假设检验失败: {e}")
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

        except Exception as e:
            self.emit_tool_error(f"趋势分析失败: {e}")
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
        except Exception as e:
            self.emit_tool_error(f"交互分析失败: {e}")
            return None

    def _auto_analyze(
        self,
        df: pd.DataFrame,
        context: DataContext,
        target_col: str | None,
        query: str,
    ) -> list[AnalysisResult]:
        """自动分析：根据数据特征选择分析方法"""
        results = []

        # 1. 如果有目标变量和数值预测变量 → 回归
        result = self._do_regression(df, context, target_col, query)
        if result:
            results.append(result)

        # 2. 如果有分类变量和数值变量 → 假设检验
        result = self._do_hypothesis_test(df, context, target_col)
        if result:
            results.append(result)

        # 3. 如果有多个数值变量 → 相关性
        result = self._do_correlation_analysis(df, context)
        if result:
            results.append(result)

        return results
