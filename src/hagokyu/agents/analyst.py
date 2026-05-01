"""HaGoKu Analyst Agent — 数理分析核心，精、准、狠"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

import pandas as pd

from ..config import LLMConfig
from ..guardrails.statistical import StatisticalGuardrails
from ..observability.event_bus import EventBus
from ..tools.analysis import (
    anova,
    chi_square,
    correlation,
    kruskal_wallis,
    mann_whitney_u,
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
        self.emit_tool_call("regression", f"target={target_col}")

        try:
            reg_result = regression(df, target_col, available_features, method="ols")
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
        self.emit_tool_call("ttest" if n_groups == 2 else "anova", f"{target_col} by {group_col}")

        try:
            if n_groups == 2:
                groups = df.groupby(group_col)[target_col]
                group_names = list(groups.groups.keys())
                g1 = groups.get_group(group_names[0]).dropna()
                g2 = groups.get_group(group_names[1]).dropna()

                test_result = ttest(g1, g2)
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
                test_result = anova(df, dv=target_col, between=group_col)
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
