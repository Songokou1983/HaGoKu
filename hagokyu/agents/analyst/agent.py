"""
Analyst Agent — 数理分析员

从 prompt.md 读取角色定义，从 memory.md 读取/保存分析模式
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .._scribe.agent import ScribeAgent
from uuid import uuid4

import pandas as pd
import yaml

from ...config import LLMConfig
from ...guardrails.statistical import StatisticalGuardrails
from ...observability.event_bus import EventBus
from ...observability.events import EventType
from ...tools.analysis import (
    check_test_assumptions,
    correlation,
    cross_validate,
    kruskal_wallis,
    mann_whitney_u,
    multiple_comparison_correction,
    regression,
    ttest,
)
from ...tools.power_analysis import power_ttest
from .._interactive import InteractionMixin
from ..types import InteractionResult
from . import knowledge as analyst_knowledge


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


class AnalystAgent(InteractionMixin):
    """数理分析员：用统计方法挖出数据背后的真相"""

    def __init__(
        self,
        llm_config: LLMConfig,
        event_bus: EventBus,
        scribe: "ScribeAgent | None" = None,
        llm_client: Any | None = None,
    ) -> None:
        self.role = "analyst"
        self.llm_config = llm_config
        self.event_bus = event_bus
        self.scribe = scribe
        self._llm_client = llm_client  # 外部传入的 LLM 客户端（双层策略用）

        self.prompt = self._load_prompt()
        self.memory = self._load_memory()
        self.guardrails = StatisticalGuardrails()

        # 交互状态
        self._phase = "begin"
        self._df: pd.DataFrame | None = None
        self._context: dict | None = None
        self._plan: dict[str, Any] = {}
        self._preliminary_results: dict | None = None

    def _load_prompt(self) -> str:
        path = Path(__file__).parent / "prompt.md"
        if path.exists():
            return path.read_text(encoding="utf-8")
        return ""

    def _load_memory(self) -> dict:
        path = Path(__file__).parent / "memory.md"
        if path.exists():
            content = path.read_text(encoding="utf-8")
            match = re.search(r"```yaml\n(analysis_patterns:.*?)```", content, re.DOTALL)
            if match:
                try:
                    return yaml.safe_load(match.group(1)) or {}
                except yaml.YAMLError:
                    return {}
        return {"analysis_patterns": {}}

    def _save_memory(self) -> None:
        path = Path(__file__).parent / "memory.md"
        content = path.read_text(encoding="utf-8")

        patterns_yaml = yaml.dump(
            self.memory.get("analysis_patterns", {}),
            default_flow_style=False,
            allow_unicode=True
        )

        pattern = r"```yaml\nanalysis_patterns:.*?```"
        if re.search(pattern, content, re.DOTALL):
            content = re.sub(pattern, f"```yaml\nanalysis_patterns:\n{patterns_yaml}```", content, flags=re.DOTALL)
        else:
            content = re.sub(r"analysis_patterns: \{\}", f"analysis_patterns:\n{patterns_yaml}", content)

        path.write_text(content, encoding="utf-8")

    def _emit(self, event_type: EventType, data: dict = None) -> None:
        self.event_bus.emit(event_type=event_type, agent=self.role, data=data or {})

    # ── 核心逻辑 ────────────────────────────────────────────

    def run(
        self,
        df: pd.DataFrame,
        context: dict,
        plan: dict,
        project_id: str | None = None,
        phase: str = "full",
    ) -> tuple[list[dict], list[dict]]:
        """
        执行统计分析

        Args:
            df: 清洗后的数据
            context: 数据上下文
            plan: 分析计划
            project_id: 项目 ID
            phase: "full"=完整分析, "preliminary"=初步发现

        Returns:
            phase="full": (分析结果列表, 商业指标列表)
            phase="preliminary": 初步发现字典
        """
        self._emit(EventType.AGENT_STARTED, {"goal": "用统计方法挖出数据真相"})

        results = []
        business_metrics = []
        focus = plan.get("analyst_focus", [])
        target_col = plan.get("target")
        query = plan.get("query", "")
        n = len(df)

        self._emit(EventType.AGENT_THINKING, {"thought": f"分析计划: focus={focus}, target={target_col}"})

        # 检索相关分析方法经验
        recalled = analyst_knowledge.recall(
            f"{query} {' '.join(focus)} n={n}",
            top_k=2,
        )
        if recalled:
            hint = "参考经验：" + " | ".join(f"{r['metadata'].get('method','?')}({r['metadata'].get('scenario','')}相似度{r['similarity']:.0%})" for r in recalled)
            self._emit(EventType.AGENT_THINKING, {"thought": hint})

        # 功效预检
        power_warnings = self._check_power(df, context, focus, n)
        for warning in power_warnings:
            self._emit(EventType.AGENT_THINKING, {"thought": warning})

        # 执行分析
        if "regression" in focus or "causal" in focus:
            result = self._do_regression(df, context, target_col, query)
            if result:
                results.append(result)

        if "hypothesis_test" in focus or "effect_size" in focus:
            result = self._do_hypothesis_test(df, context, target_col)
            if result:
                results.append(result)

        if "correlation" in focus:
            result = self._do_correlation(df, context)
            if result:
                results.append(result)

        if "trend" in focus or "time_series" in focus:
            result = self._do_trend(df, context, target_col)
            if result:
                results.append(result)

        # 兜底
        if not results:
            results = self._auto_analyze(df, context, target_col, query)

        # phase="preliminary"：只返回初步发现，不做增强诊断
        if phase == "preliminary":
            self._emit(EventType.AGENT_COMPLETED, {
                "result_summary": f"初步发现 {len(results)} 个，待确认"
            })
            suggested = ""
            if results:
                top = results[0]
                if top.get("significance") == "significant":
                    suggested = f"初步发现「{top.get('question', '')}」具有统计显著性，建议重点分析"
                else:
                    suggested = "初步结果均不显著，建议扩大样本或调整分析维度"
            return {
                "status": "analyst_preliminary",
                "power_warnings": power_warnings,
                "business_metrics": business_metrics,
                "preliminary_findings": results,
                "suggested_focus": suggested,
            }

        # 交叉验证
        for result in results:
            if result["analysis_type"] == "regression":
                self._enhance_with_cv(df, result, target_col)

        # 多重比较校正
        if len(results) > 1:
            self._apply_multiple_comparison(results)

        # 统计护栏
        for result in results:
            guardrail_results = self.guardrails.check(result)
            result["guardrail_results"] = [gr.model_dump() for gr in guardrail_results]

            violations = self.guardrails.get_violations(guardrail_results)
            if violations:
                self._emit(EventType.QUALITY_CHECK, {
                    "verdict": "fail" if violations.get("mandatory") else "warning",
                    "detail": f"{sum(len(v) for v in violations.values())} 个护栏问题",
                })

        # 更新记忆
        self._update_own_memory(results, project_id)

        # 学习：将分析场景和方法写入知识库
        self._learn_from_results(results, focus, n, context, project_id)

        self._emit(EventType.AGENT_COMPLETED, {"result_summary": f"完成 {len(results)} 项分析"})

        return results, business_metrics

    # ── 交互式接口 ────────────────────────────────────────

    def begin(
        self,
        df: pd.DataFrame,
        context: dict,
        plan: dict,
    ) -> InteractionResult:
        """
        开始 Analyst 交互。

        流程：执行分析 → 确认结果 → 完成
        """
        self._df = df
        self._context = context
        self._plan = plan

        self._emit(EventType.AGENT_STARTED, {"goal": "用统计方法挖出数据真相"})

        try:
            # 运行完整分析
            results, business_metrics = self.run(df, context, plan)
            self._phase = "next_step"

            n_sig = sum(1 for r in results if r.get("significance") == "significant")
            summary = f"完成 {len(results)} 项分析，{n_sig} 项显著发现"

            # block，等用户确认进入下一步
            if self.scribe:
                self.scribe.block_task("analyst", "等用户确认进入报告阶段")

            return self._pause(
                phase="next_step",
                message=summary + "\n\n建议进入「报告阶段」，是否确认？",
                actions=["生成报告", "继续分析", "结束分析"],
                pending_items=[],
                data={
                    "n_results": len(results),
                    "n_significant": n_sig,
                    "business_metrics": len(business_metrics),
                    "results_preview": results[:3],
                },
            )

        except Exception as e:
            self._emit(EventType.AGENT_FAILED, {"error": str(e)})
            return self._done("done", f"Analyst 失败: {e}", {"error": str(e)})

    def respond(
        self,
        user_input: dict,
    ) -> InteractionResult:
        """
        处理用户对分析结果的响应。
        """
        if self._phase != "next_step":
            return self._done("done", "阶段错误，请重新开始", {})

        action = user_input.get("action", "")
        if action == "生成报告":
            if self.scribe:
                self.scribe.unblock_task("analyst")
            return self._pause(
                phase="next_step",
                message="正在进入报告阶段...",
                actions=[],
                pending_items=[],
                data={"proceed_to": "reporter"},
            )
        elif action == "继续分析":
            if self.scribe:
                self.scribe.unblock_task("analyst")
            # 重新执行分析
            return self.begin(self._df, self._context, self._plan)
        else:
            if self.scribe:
                self.scribe.unblock_task("analyst")
            return self._done("done", "分析已结束", {})

    def _do_regression(self, df, context, target_col, query) -> dict | None:
        """回归分析"""
        if not target_col:
            target_candidates = [s for s in context.get("column_semantics", []) if s.get("suggested_role") == "target"]
            if not target_candidates:
                return None
            target_col = target_candidates[0]["column_name"]

        variable_roles = context.get("variable_roles", {})
        numeric_features = [
            col for col, role in variable_roles.items()
            if role in ("numeric_feature", "binary_feature")
            and col in df.columns
            and col != target_col
        ]

        if not numeric_features:
            return None

        available_features = [f for f in numeric_features if f in df.columns]
        if not available_features:
            return None

        self._emit(EventType.AGENT_THINKING, {"thought": f"回归分析: {target_col} ~ {'+'.join(available_features[:5])}"})

        # 假设检验前置检查
        assumption_check = check_test_assumptions(df, "regression", target=target_col, features=available_features)
        if not assumption_check.get("all_assumptions_met", True):
            warnings = assumption_check.get("warnings", [])
            if warnings:
                self._emit(EventType.AGENT_THINKING, {"thought": f"⚠️ 假设检查: {'; '.join(warnings)}"})

        try:
            reg_result = regression(df, target_col, available_features, method="ols")
            if "error" in reg_result:
                return None

            r_sq = reg_result.get("r_squared", 0)
            f_p = reg_result.get("f_pvalue", 1)
            p_values = reg_result.get("p_values", {})
            significant_predictors = [f for f in available_features if f in p_values and p_values[f] < 0.05]

            sig = "significant" if f_p is not None and 0 <= f_p < 0.05 else "not_significant"

            conclusion = (
                f"回归模型 R²={r_sq:.3f}，"
                f"{'模型整体显著' if sig == 'significant' else '模型整体不显著'}。"
            )
            if significant_predictors:
                conclusion += f"显著预测变量: {', '.join(significant_predictors[:3])}。"

            reg_result["target"] = target_col
            reg_result["features"] = available_features

            return {
                "result_id": uuid4().hex[:8],
                "analysis_type": "regression",
                "question": f"{target_col} 的预测因素是什么？",
                "conclusion_plain": conclusion,
                "p_value": f_p,
                "effect_size": reg_result.get("effect_size"),
                "effect_type": reg_result.get("effect_type", ""),
                "significance": sig,
                "sample_size": reg_result.get("n_obs"),
                "diagnostics": reg_result.get("diagnostics"),
                "raw_result": reg_result,
            }

        except Exception:
            return None

    def _do_hypothesis_test(self, df, context, target_col) -> dict | None:
        """假设检验"""
        cat_cols = [
            s["column_name"]
            for s in context.get("column_semantics", [])
            if s.get("inferred_type") in ("categorical", "boolean", "ordinal")
            and s["column_name"] in df.columns
        ]

        num_cols = [
            s["column_name"]
            for s in context.get("column_semantics", [])
            if s.get("inferred_type") == "numeric"
            and s.get("suggested_role") != "identifier"
            and s["column_name"] in df.columns
        ]

        if not target_col and num_cols:
            target_col = num_cols[0]

        if not target_col or not cat_cols:
            return None

        group_col = cat_cols[0]
        n_groups = df[group_col].nunique()

        self._emit(EventType.AGENT_THINKING, {"thought": f"假设检验: {target_col} by {group_col} ({n_groups} 组)"})

        try:
            if n_groups == 2:
                groups = df.groupby(group_col)[target_col]
                group_names = list(groups.groups.keys())
                g1 = groups.get_group(group_names[0]).dropna()
                g2 = groups.get_group(group_names[1]).dropna()

                if len(g1) < 3 or len(g2) < 3:
                    return None

                # 检查正态性，自动切换非参数
                assumption_check = check_test_assumptions(df, "ttest", target=target_col, group_col=group_col)
                use_nonparam = not assumption_check.get("all_assumptions_met", True)

                if use_nonparam:
                    test_result = mann_whitney_u(g1, g2)
                else:
                    test_result = ttest(g1, g2)

                if "error" in test_result:
                    return None

                p_val = test_result["p_value"]
                sig = "significant" if p_val < 0.05 else "not_significant"

                if use_nonparam:
                    medians = [float(g1.median()), float(g2.median())]
                    conclusion = (
                        f"{group_names[0]} (Mdn={medians[0]:.2f}) vs "
                        f"{group_names[1]} (Mdn={medians[1]:.2f})，"
                        f"{'差异显著' if sig == 'significant' else '差异不显著'}"
                        f"(U={test_result['statistic']:.1f}, p={p_val:.4f})"
                    )
                else:
                    means = [float(g1.mean()), float(g2.mean())]
                    conclusion = (
                        f"{group_names[0]} (M={means[0]:.2f}) vs "
                        f"{group_names[1]} (M={means[1]:.2f})，"
                        f"{'差异显著' if sig == 'significant' else '差异不显著'}"
                        f"(p={p_val:.4f}, d={test_result['effect_size']:.3f})"
                    )

                test_result["target"] = target_col
                test_result["group_col"] = group_col

                return {
                    "result_id": uuid4().hex[:8],
                    "analysis_type": "hypothesis_test",
                    "question": f"不同 {group_col} 组的 {target_col} 有差异吗？",
                    "conclusion_plain": conclusion,
                    "p_value": p_val,
                    "effect_size": test_result.get("effect_size"),
                    "effect_type": test_result.get("effect_type", ""),
                    "significance": sig,
                    "sample_size": len(df),
                    "raw_result": test_result,
                }

            else:
                # 多组：Kruskal-Wallis
                test_result = kruskal_wallis(df, dv=target_col, between=group_col)
                if "error" in test_result:
                    return None

                p_val = test_result["p_value"]
                sig = "significant" if p_val < 0.05 else "not_significant"

                conclusion = (
                    f"{n_groups} 组 {target_col} 均值"
                    f"{'差异显著' if sig == 'significant' else '差异不显著'}"
                    f"(H={test_result['statistic']:.2f}, p={p_val:.4f})"
                )

                test_result["target"] = target_col
                test_result["group_col"] = group_col

                return {
                    "result_id": uuid4().hex[:8],
                    "analysis_type": "hypothesis_test",
                    "question": f"不同 {group_col} 组的 {target_col} 有差异吗？",
                    "conclusion_plain": conclusion,
                    "p_value": p_val,
                    "effect_size": test_result.get("effect_size"),
                    "effect_type": test_result.get("effect_type", ""),
                    "significance": sig,
                    "sample_size": len(df),
                    "raw_result": test_result,
                }

        except Exception:
            return None

    def _do_correlation(self, df, context) -> dict | None:
        """相关性分析"""
        num_cols = [
            s["column_name"]
            for s in context.get("column_semantics", [])
            if s.get("inferred_type") == "numeric"
            and s.get("suggested_role") != "identifier"
            and s["column_name"] in df.columns
        ]

        if len(num_cols) < 2:
            return None

        best_corr = None
        best_pair = (num_cols[0], num_cols[1])
        best_abs_r = 0

        for i, col1 in enumerate(num_cols):
            for col2 in num_cols[i + 1:]:
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

        self._emit(EventType.AGENT_THINKING, {"thought": conclusion})

        return {
            "result_id": uuid4().hex[:8],
            "analysis_type": "correlation",
            "question": f"{col1} 与 {col2} 之间的关系？",
            "conclusion_plain": conclusion,
            "p_value": p,
            "effect_size": abs(r),
            "effect_type": "pearson_r",
            "significance": sig,
            "sample_size": best_corr["n_observations"],
            "raw_result": best_corr,
        }

    def _do_trend(self, df, context, target_col) -> dict | None:
        """趋势分析"""
        time_cols = [
            s["column_name"]
            for s in context.get("column_semantics", [])
            if s.get("inferred_type") == "datetime"
            and s["column_name"] in df.columns
        ]

        if not time_cols or not target_col:
            return None

        time_col = time_cols[0]

        try:
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
                f"(β={coeff:.4f}, p={p_val:.4f})"
                if p_val < 0.05
                else f"{target_col} 无显著时间趋势 (p={p_val:.4f})"
            )

            result["target"] = target_col
            result["time_col"] = time_col

            return {
                "result_id": uuid4().hex[:8],
                "analysis_type": "trend_analysis",
                "question": f"{target_col} 随时间变化趋势如何？",
                "conclusion_plain": conclusion,
                "p_value": p_val,
                "effect_size": r_sq,
                "effect_type": "r_squared",
                "significance": sig,
                "sample_size": len(df),
                "raw_result": result,
            }

        except Exception:
            return None

    def _auto_analyze(self, df, context, target_col, query) -> list[dict]:
        """兜底自动分析"""
        results = []

        result = self._do_regression(df, context, target_col, query)
        if result:
            results.append(result)

        result = self._do_hypothesis_test(df, context, target_col)
        if result:
            results.append(result)

        result = self._do_correlation(df, context)
        if result:
            results.append(result)

        return results

    def _check_power(self, df, context, focus, n) -> list[str]:
        """功效预检"""
        warnings = []

        if n < 30:
            warnings.append(f"⚠️ 数据量偏少（n={n}），检验功效可能不足。")
            return warnings

        if "hypothesis_test" in focus:
            cat_cols = [s["column_name"] for s in context.get("column_semantics", []) if s.get("inferred_type") in ("categorical", "boolean")]
            if cat_cols:
                n_groups = df[cat_cols[0]].nunique()
                n_per_group = n // n_groups
                if n_per_group < 15:
                    warnings.append(f"⚠️ 每组样本量偏少（n={n_per_group}），检测中等效应功效可能不足。")
                elif n_per_group >= 30:
                    power_info = power_ttest(n_per_group, n_per_group, effect_size=0.5)
                    if "error" not in power_info:
                        power_pct = power_info.get("power", 0) * 100
                        if power_pct >= 80:
                            warnings.append(f"✅ 每组 n={n_per_group}，检测中等效应功效约 {power_pct:.0f}%，足够。")

        if "regression" in focus:
            n_predictors = len([f for f in context.get("features", []) if f in df.columns])
            if n_predictors > 0 and n < 10 * n_predictors:
                warnings.append(f"⚠️ 样本量 n={n} 与自变量数 {n_predictors} 的比例偏低。")

        return warnings

    def _enhance_with_cv(self, df, result, target_col) -> None:
        """交叉验证"""
        raw = result.get("raw_result", {})
        features = [k for k in raw.get("coefficients", {}).keys() if k != "const" and k in df.columns]
        target = target_col or result.get("question", "").split("的")[0] if "的" in result.get("question", "") else None

        if not target or target not in df.columns or len(features) < 1:
            return

        try:
            cv_result = cross_validate(df, target, features, k_folds=5)
            if "error" not in cv_result:
                if result.get("diagnostics") is None:
                    result["diagnostics"] = {}
                result["diagnostics"]["cross_validation"] = cv_result
        except Exception:
            pass

    def _apply_multiple_comparison(self, results) -> None:
        """多重比较校正"""
        p_values = []
        for r in results:
            if r.get("p_value") is not None and not isinstance(r.get("p_value"), str):
                p_values.append(float(r["p_value"]))

        if len(p_values) < 2:
            return

        try:
            correction = multiple_comparison_correction(p_values, method="bh")

            for i, result in enumerate(results):
                if i < len(correction.get("adjusted_p", [])):
                    if result.get("raw_result") is None:
                        result["raw_result"] = {}
                    result["raw_result"]["multiple_comparison"] = {
                        "original_p": correction["original_p"][i],
                        "adjusted_p": correction["adjusted_p"][i],
                        "still_significant": correction["significant"][i],
                    }
                    if not correction["significant"][i] and result["significance"] == "significant":
                        result["significance"] = "not_significant_after_correction"
        except Exception:
            pass

    def _update_own_memory(self, results: list[dict], project_id: str | None) -> None:
        """更新分析模式记忆"""
        if not project_id:
            return

        if "analysis_patterns" not in self.memory:
            self.memory["analysis_patterns"] = {}

        for result in results:
            if project_id not in self.memory["analysis_patterns"]:
                self.memory["analysis_patterns"][project_id] = []

            self.memory["analysis_patterns"][project_id].append({
                "type": result.get("analysis_type"),
                "question": result.get("question"),
                "significance": result.get("significance"),
                "date": datetime.now().strftime("%Y-%m-%d"),
            })

        self._save_memory()

    def _learn_from_results(
        self,
        results: list[dict],
        focus: list[str],
        n: int,
        context: dict,
        project_id: str | None,
    ) -> None:
        """将分析场景和方法选择写入知识库"""
        if not results or not project_id:
            return

        for result in results:
            method = result.get("analysis_type", "")
            significance = result.get("significance", "")
            # 构建场景描述
            target_col = context.get("target", "")
            # 简单场景描述
            scenario = f"{','.join(focus)} n={n} target={target_col}"
            # 检查是否已有相似条目
            existing = analyst_knowledge.recall(scenario, top_k=1)
            if existing and existing[0]["similarity"] > 0.85:
                continue
            analyst_knowledge.learn(
                scenario=scenario,
                method=method,
                method_code="",
                confidence=0.8 if significance == "yes" else 0.6,
                tags=focus + [f"n={n}", significance],
                metadata={"project": project_id, "result": str(result.get("conclusion_plain", ""))[:100]},
            )
