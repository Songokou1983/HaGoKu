"""
Analyst Agent — 数理分析员

从 prompt.md 读取角色定义，从 memory.md 读取/保存分析模式
"""

from __future__ import annotations

import logging
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
from ...guardrails.parsers import deep_validate
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

logger = logging.getLogger("hagoku.analyst")

from ..constants import (
    ANALYST_DEDUP_SIMILARITY,
    CLEANING_IMPACT_HIGH_THRESHOLD,
    CLEANING_IMPACT_MEDIUM_THRESHOLD,

    CROSS_VALIDATION_FOLDS_DEFAULT,
    DW_LOWER_BOUND,
    DW_UPPER_BOUND,
    LLM_TOKEN_RATE_MIN,
    POWER_ADEQUATE_PER_GROUP,
    POWER_EFFECT_SIZE_DEFAULT,
    POWER_MIN_PER_GROUP_SAMPLE,
    POWER_MIN_TOTAL_SAMPLE,
    POWER_REGRESSION_RATIO,
    POWER_TARGET_PCT,
    SIGNIFICANCE_LABEL_CORRECTED,
    SIGNIFICANCE_LABEL_NOT_SIG,
    SIGNIFICANCE_LABEL_SIG,
    SIGNIFICANCE_THRESHOLD,
)


class NeedUserClarification(Exception):
    """LLM 无法确定分析策略时需要用户澄清"""
    def __init__(self, message: str, *, options: list[str] | None = None, context: dict | None = None):
        super().__init__(message)
        self.message = message
        self.options = options or []
        self.context = context or {}


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

    # ── 分析方法注册表（P1.1 修复：支持 LLM 动态扩展分析类型） ──
    # 格式：{ analysis_type: handler_method_name }
    # 所有 handler 统一签名为 (df, context, step: dict) → dict | None
    # 子类或运行时可通过 register_analysis_type() 扩展
    _ANALYSIS_DISPATCH: dict[str, str] = {
        "regression": "_do_regression",
        "hypothesis_test": "_do_hypothesis_test",
        "correlation": "_do_correlation",
        "trend_analysis": "_do_trend",
    }

    @classmethod
    def register_analysis_type(cls, analysis_type: str, method_name: str) -> None:
        """注册新的分析方法类型，支持 LLM 动态扩展。"""
        cls._ANALYSIS_DISPATCH[analysis_type] = method_name

    def _dispatch_analysis(self, atype: str, df, context, step: dict) -> dict | None:
        """通过注册表分发——所有 handler 统一接收 (df, context, step)，自行提取所需参数。"""
        method_name = self._ANALYSIS_DISPATCH.get(atype)
        if method_name is None:
            logger.debug("未注册的分析类型 '%s'，跳过", atype)
            return None
        handler = getattr(self, method_name, None)
        if handler is None:
            logger.warning("注册表指向不存在的方法 '%s' for '%s'", method_name, atype)
            return None
        return handler(df, context, step)

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

        # 使用 yaml.dump 序列化整个 memory 结构，避免正则替换脆弱性
        memory_yaml = yaml.dump(
            self.memory,
            default_flow_style=False,
            allow_unicode=True,
            sort_keys=False,
        )

        # 找到 yaml 代码块的起止边界并完整替换
        fence_start = "```yaml\n"
        fence_end = "\n```"
        start_idx = content.find(fence_start)
        if start_idx != -1:
            # 找到 fence_start 之后的第一个 fence_end
            after_start = start_idx + len(fence_start)
            end_idx = content.find(fence_end, after_start)
            if end_idx != -1:
                content = (
                    content[:start_idx]
                    + fence_start
                    + memory_yaml.strip()
                    + content[end_idx:]
                )

        path.write_text(content, encoding="utf-8")

    def _emit(self, event_type: EventType, data: dict | None = None) -> None:
        self.event_bus.emit(event_type=event_type, agent=self.role, data=data or {})

    # ── 核心逻辑 ────────────────────────────────────────────

    def run(
        self,
        df: pd.DataFrame,
        context: dict,
        plan: dict,
        project_id: str | None = None,
        phase: str = "full",
        *,
        emit_completed: bool = True,
    ) -> tuple[list[dict], list[dict]]:
        """
        执行统计分析

        Args:
            df: 清洗后的数据
            context: 数据上下文
            plan: 分析计划
            project_id: 项目 ID
            phase: "full"=完整分析, "preliminary"=初步发现
            emit_completed: 为 False 时 full 阶段结束时不再发 AGENT_COMPLETED（由编排层在用户确认后再发）。

        Returns:
            phase="full": (分析结果列表, 商业指标列表)
            phase="preliminary": 初步发现字典
        """
        self._emit(EventType.AGENT_STARTED, {"goal": "用统计方法挖出数据真相"})

        results = []
        business_metrics: list[dict[str, Any]] = []
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

        # ==== CHANNEL ZONE: LLM 自主选择分析方法，禁止硬编码分支 ====
        # LLM 根据数据画像（列类型/角色/缺失率/清洗影响）和用户提问，
        # 输出结构化分析计划（JSON），代码仅做机械分发，不做语义判断。
        analysis_steps = self._plan_analysis_via_llm(df, context, target_col, query)

        if analysis_steps:
            for step in analysis_steps:
                atype = step["analysis_type"]
                result = self._dispatch_analysis(atype, df, context, step)
                if result:
                    result["method_reason"] = step.get("reason", "")
                    result["method_name"] = step.get("method_name", "")
                    results.append(result)

        # 如果 LLM 计划为空或全部失败，不执行代码预设的机械序列
        # 而是增强上下文后重试一次，仍失败则抛出异常请求用户澄清
        if not results:
            self._emit(EventType.AGENT_THINKING, {"thought": "LLM 未生成分析计划，正在增强上下文重试..."})
            retry_steps = self._plan_analysis_via_llm(
                df, context, target_col, query, retry=True
            )
            if retry_steps:
                for step in retry_steps:
                    result = self._dispatch_analysis(step["analysis_type"], df, context, step)
                    if result:
                        result["method_reason"] = step.get("reason", "")
                        result["method_name"] = step.get("method_name", "")
                        results.append(result)

            if not results:
                # 两次 LLM 调用都失败 → 向用户请求澄清，不执行机械分析
                raise NeedUserClarification(
                    f"无法自动确定「{query or '当前数据'}」的分析策略。"
                    f"数据包含 {len(df.columns)} 列、{len(df)} 行。"
                    f"请告诉我您更关注哪些方面？例如：差异对比、相关性、趋势、预测建模等。"
                )

        # phase="preliminary"：只返回初步发现，不做增强诊断
        if phase == "preliminary":
            self._emit(EventType.AGENT_COMPLETED, {
                "result_summary": f"初步发现 {len(results)} 个，待确认"
            })
            suggested = ""
            if results:
                top = results[0]
                if top.get("significance") == SIGNIFICANCE_LABEL_SIG:
                    suggested = f"初步发现「{top.get('question', '')}」具有统计显著性，建议重点分析"
                else:
                    suggested = "初步结果均不显著，建议扩大样本或调整分析维度"
            return {  # type: ignore[return-value]
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

        # 统计护栏 + 结构化输出验证
        for result in results:
            guardrail_results = self.guardrails.check(result)
            result["guardrail_results"] = [gr.model_dump() for gr in guardrail_results]

            violations = self.guardrails.get_violations(guardrail_results)
            if violations:
                self._emit(EventType.QUALITY_CHECK, {
                    "verdict": "fail" if violations.get("mandatory") else "warning",  # type: ignore[call-overload]
                    "detail": f"{sum(len(v) for v in violations.values())} 个护栏问题",
                })

            # P1.2 接线：对结论文本做深度校验（解析器已接入，不再死代码）
            conclusion_text = result.get("conclusion_plain", "")
            if conclusion_text:
                deep_result = deep_validate(conclusion_text)
                if deep_result.get("hallucination_warnings"):
                    logger.warning("Analyst 结论疑似幻觉: %s", deep_result["hallucination_warnings"])
                    self._emit(EventType.QUALITY_CHECK, {
                        "verdict": "warning",
                        "detail": f"结论文本可疑: {'; '.join(deep_result['hallucination_warnings'][:3])}",
                    })
                result["_deep_validation"] = deep_result

        # 更新记忆
        self._update_own_memory(results, project_id)

        # 学习：将分析场景和方法写入知识库
        self._learn_from_results(results, focus, n, context, project_id)

        if emit_completed:
            self._emit(EventType.AGENT_COMPLETED, {"result_summary": f"完成 {len(results)} 项分析"})

        return results, business_metrics

    # ── 交互式接口 ────────────────────────────────────────

    def begin(  # type: ignore[override]
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

    def respond(  # type: ignore[override]
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
            return self.begin(self._df, self._context, self._plan)  # type: ignore[arg-type]
        else:
            if self.scribe:
                self.scribe.unblock_task("analyst")
            return self._done("done", "分析已结束", {})

    def _do_regression(self, df, context, step: dict) -> dict | None:
        """回归分析"""
        target_col = step.get("target_col", "")
        query = step.get("question", "")
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
            significant_predictors = [f for f in available_features if f in p_values and p_values[f] < SIGNIFICANCE_THRESHOLD]

            sig = "significant" if f_p is not None and 0 <= f_p < SIGNIFICANCE_THRESHOLD else SIGNIFICANCE_LABEL_NOT_SIG

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
            logger.warning("回归分析执行失败", exc_info=True)
            return None

    def _do_hypothesis_test(self, df, context, step: dict) -> dict | None:
        """假设检验"""
        target_col = step.get("target_col", "")
        group_col = step.get("group_col")
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

        # 优先使用 LLM 选择的 group_col；回退方案也要让用户知情
        if group_col and group_col in df.columns and df[group_col].nunique() >= 2:
            pass  # LLM 选择有效
        elif cat_cols:
            # P1 修复：不再静默回退 cat_cols[0]
            candidates = [(c, int(df[c].nunique())) for c in cat_cols if df[c].nunique() >= 2]
            if len(candidates) == 1:
                group_col = candidates[0][0]
            elif len(candidates) > 1:
                parts = [f"{c} ({n} 组)" for c, n in candidates]
                raise NeedUserClarification(
                    f"请选择用于比较 '{target_col}' 的分组变量：\n" +
                    "\n".join(f"  · {p}" for p in parts),
                    options=[c for c, _ in candidates],
                    context={"target_col": target_col, "candidates": [c for c, _ in candidates]},
                )
            else:
                group_col = None
        else:
            group_col = None

        if not group_col:
            raise NeedUserClarification(
                f"需要为 '{target_col}' 指定分组变量进行假设检验，但当前数据中没有可用"
                "的分类列（需要至少 2 组且每组不少于 2 个样本）。",
                context={"target_col": target_col},
            )
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
                sig = "significant" if p_val < SIGNIFICANCE_THRESHOLD else "not_significant"

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
                sig = "significant" if p_val < SIGNIFICANCE_THRESHOLD else "not_significant"

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
            logger.warning("假设检验执行失败", exc_info=True)
            return None

    def _do_correlation(self, df, context, step: dict | None = None) -> dict | None:
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
                    logger.debug("correlation 计算异常，跳过该列对", exc_info=True)
                    continue

        if best_corr is None:
            return None

        col1, col2 = best_pair
        r = best_corr["statistic"]
        p = best_corr["p_value"]
        sig = "significant" if p < SIGNIFICANCE_THRESHOLD else "not_significant"

        direction = CORRELATION_DIRECTION_POS if r > 0 else CORRELATION_DIRECTION_NEG
        strength = CORRELATION_LABEL_STRONG if abs(r) > CORRELATION_THRESHOLD_STRONG_ABS else (CORRELATION_LABEL_MODERATE if abs(r) > CORRELATION_THRESHOLD_MODERATE_ABS else CORRELATION_LABEL_WEAK)
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

    def _do_trend(self, df, context, step: dict) -> dict | None:
        """趋势分析"""
        target_col = step.get("target_col", "")
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
            sig = "significant" if p_val < SIGNIFICANCE_THRESHOLD else "not_significant"

            conclusion = (
                f"{target_col} 呈{direction}趋势"
                f"(β={coeff:.4f}, p={p_val:.4f})"
                if p_val < SIGNIFICANCE_THRESHOLD
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
            logger.warning("趋势分析执行失败", exc_info=True)
            return None

    # ==== CHANNEL ZONE: LLM 驱动分析规划，禁止硬编码方法分发 ====
    def _plan_analysis_via_llm(
        self, df: "pd.DataFrame", context: dict, target_col: str | None, query: str,
        retry: bool = False
    ) -> list[dict]:
        """调用 LLM 根据数据画像和用户提问输出结构化分析计划。

        返回分析步骤列表，每项包含：
        - analysis_type: 分析方法标识
        - question: 研究问题
        - target_col: 目标变量（可选）
        - group_col: 分组变量（可选）
        - columns: 参与分析的列列表
        - reason: 为什么选择这个方法（给用户的解释）
        - method_name: 中文方法名称
        """
        import json as _json

        # 构建数据画像摘要
        col_summaries = []
        for colname in df.columns:
            col_sem = next(
                (s for s in context.get("column_semantics", []) if s.get("column_name") == colname),
                {},
            )
            col_summaries.append({
                "列名": colname,
                "类型": col_sem.get("inferred_type", "未知"),
                "角色": col_sem.get("suggested_role", "未知"),
                "说明": col_sem.get("description", ""),
                "缺失率": f"{df[colname].isna().mean():.1%}",
                "唯一值数": int(df[colname].nunique()),
            })

        # 从分析注册表动态构建可用方法描述（支持插件扩展）
        from ...tools.analysis_registry import analysis_registry
        available_methods = analysis_registry.describe_all(enabled_only=True)

        system_prompt = (
            "你是一位资深数据分析师。【推理链路】分析目标 → 字段含义 → 选择方法 → 分析数据 → 得出可验证结论 → 解释结果。每一步依赖上一步。\n\n"
            "## 分析计划生成规则\n"
            "1. 首先理解用户的提问意图（预测？对比？探索？趋势？）\n"
            "2. 根据意图从可用方法列表中选择最合适的方法\n"
            "3. 如果有目标变量和多个特征列 → 优先回归分析\n"
            "4. 如果有分组列和目标变量 → 考虑假设检验\n"
            "5. 如果有日期列 → 考虑趋势分析\n"
            "6. 如果用户问题模糊，用相关性分析进行探索\n"
            "7. 回归/假设检验前建议先做前提检测\n"
            "8. 样本量 < 50 时建议补充功效分析\n"
            "9. 不要过度分析——只选最相关的方法，2-3 个步骤通常足够\n"
            "10. 清洗影响是上游 Cleaner 留下的信息，用于判断数据可靠性，不是分析步骤\n\n"
            "输出一个 JSON 对象，字段 `steps` 为数组。每项包含：\n"
            '  - analysis_type: 方法标识（只能从可用方法列表里选）\n'
            '  - question: 这个分析步骤要回答什么问题（自然语言）\n'
            '  - target_col: 目标变量列名（regression/hypothesis_test 需填，没有则为 null）\n'
            '  - group_col: 分组变量列名（hypothesis_test 需填，没有则为 null）\n'
            '  - columns: 参与分析的列名列表\n'
            '  - reason: 为什么选这个方法（自然语言，不要出现技术术语）\n'
            '  - method_name: 方法的中文名称'
            f"\n\n{self.prompt}"
        )

        # 清洗影响信息
        cleaning_impact = context.get("_cleaning_impact", {})
        cleaning_section = ""
        if cleaning_impact:
            cleaning_section = f"\n\n## 数据清洗影响（来自上游 Cleaner）\n```json\n{_json.dumps(cleaning_impact, ensure_ascii=False, default=str)}\n```\n\n请在选择分析方法时考虑：目标变量是否被清洗过，是否存在均值偏移。"

        if retry:
            # 重试模式：使用增强上下文
            user_prompt = self._enrich_for_retry(df, context, query)
            user_prompt += f"\n## 可用分析方法\n```json\n{_json.dumps(available_methods, ensure_ascii=False)}\n```"
            user_prompt += cleaning_section
        else:
            user_prompt = (
                f"## 用户提问\n{query}\n\n"
                f"## 数据集信息\n样本量: {len(df)} 行\n列数: {len(df.columns)} 列\n"
            )
            if target_col:
                user_prompt += f"已识别目标变量: {target_col}\n"
            user_prompt += f"\n## 列画像\n```json\n{_json.dumps(col_summaries, ensure_ascii=False, default=str)}\n```"
            user_prompt += f"\n## 可用分析方法\n```json\n{_json.dumps(available_methods, ensure_ascii=False)}\n```"
            user_prompt += cleaning_section

        # ── ProjectContext 注入（阶段 3）──
        project_ctx = context.get("_project_context")
        if project_ctx:
            ctx_block = project_ctx.build_prompt("analyst", context)
            system_prompt += "\n\n" + ctx_block["system_prefix"] + "\n\n" + ctx_block["upstream_summary"]

        from ...llm.client import create_raw_client

        client = create_raw_client(self.llm_config)
        try:
            response = client.chat.completions.create(
                model=self.llm_config.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.0,
                max_tokens=2048,
                response_format={"type": "json_object"},
            )
            raw = response.choices[0].message.content or ""
        except Exception as e:
            raise RuntimeError(
                f"Analyst LLM 分析规划失败：LLM 不可达，请检查 API 配置。原始错误: {e}"
            ) from e

        # 解析 JSON
        try:
            result = _json.loads(raw)
        except _json.JSONDecodeError:
            import re
            try:
                cleaned = raw.strip()
                cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
                cleaned = re.sub(r"\s*```\s*$", "", cleaned)
                cleaned = cleaned.strip()
                result = _json.loads(cleaned)
            except _json.JSONDecodeError:
                try:
                    match = re.search(r"\{.*\}", raw, re.DOTALL)
                    if match:
                        result = _json.loads(match.group())
                    else:
                        raise
                except Exception as e:
                    raise RuntimeError(
                        f"Analyst LLM 输出解析失败：通道异常，必须修复后重跑。原始错误: {e}"
                    ) from e

        steps = result.get("steps") or []
        if not steps:
            return []

        # 校验并标准化
        # valid_types 从分析注册表动态获取，新增方法无需改代码（P2 修复）
        from ...tools.analysis_registry import analysis_registry as _reg
        _all_methods = _reg.list_all(enabled_only=True)
        valid_types = {m.name for m in _all_methods}
        # 合并内置类型（非注册表方法但代码支持）
        valid_types |= {
            "trend_analysis", "cross_validate",
            "multiple_comparison_correction", "check_test_assumptions",
            "power_analysis",
        }
        valid_columns = set(df.columns)
        normalized: list[dict] = []
        for step in steps:
            atype = step.get("analysis_type", "")
            if atype not in valid_types:
                continue
            question = step.get("question", "")
            if not question or not isinstance(question, str):
                continue
            tcol = step.get("target_col")
            if tcol and tcol not in valid_columns:
                tcol = None
            gcol = step.get("group_col")
            if gcol and gcol not in valid_columns:
                gcol = None
            cols = [c for c in (step.get("columns") or []) if c in valid_columns]
            normalized.append({
                "analysis_type": atype,
                "question": question,
                "target_col": tcol,
                "group_col": gcol,
                "columns": cols,
                "reason": step.get("reason", ""),
                "method_name": step.get("method_name", ""),
            })

        return normalized

    def _enrich_for_retry(
        self, df: "pd.DataFrame", context: dict, query: str
    ) -> str:
        """增强 LLM 重试上下文：注入更多列语义、上游笔记。

        当首次 LLM 调用未能生成有效分析计划时，此方法构建更详细的
        上下文提示，帮助 LLM 做出决策。
        """
        # 提取 Scribe 笔记（如果有）
        scribe_notes = context.get("_scribe_note", "")
        # 提取数据分布信息
        import json as _json

        enriched = [
            f"## 用户提问\n{query or '无明确提问，请根据数据特征选择探索性分析'}",
            f"\n## 数据集概览\n- 样本量: {len(df)} 行\n- 列数: {len(df.columns)} 列\n- 数值列: {len(df.select_dtypes(include='number').columns)} 个\n- 分类列: {len(df.select_dtypes(include=['object', 'category']).columns)} 个",
        ]

        # 列角色汇总（比 col_summaries 更精炼）
        col_roles = {}
        for s in context.get("column_semantics", []):
            col_roles[s.get("column_name", "")] = s.get("suggested_role", "unknown")
        enriched.append(f"\n## 列角色: {_json.dumps(col_roles, ensure_ascii=False)}")

        # 日期列提示
        time_cols = [
            s["column_name"]
            for s in context.get("column_semantics", [])
            if s.get("inferred_type") == "datetime"
        ]
        if time_cols:
            enriched.append(f"\n⚠️ 检测到日期列: {time_cols}，强烈建议考虑趋势分析")

        # 分类列提示（用于假设检验group_col选择）
        cat_cols = [
            s["column_name"]
            for s in context.get("column_semantics", [])
            if s.get("inferred_type") in ("categorical", "boolean", "ordinal")
        ]
        if cat_cols:
            enriched.append(f"\n⚠️ 可用的分组列: {cat_cols}，请从中选择 group_col")

        # 上游笔记
        if scribe_notes:
            enriched.append(f"\n## 上游 Scribe 笔记\n{scribe_notes}")

        # 清洗影响
        cleaning_impact = context.get("_cleaning_impact", {})
        if cleaning_impact:
            enriched.append(f"\n## 数据清洗影响\n{_json.dumps(cleaning_impact, ensure_ascii=False, default=str)}")
            enriched.append("选择分析方法时请考虑目标变量是否被清洗过，是否存在均值偏移")

        # 指导性建议
        enriched.append("\n## 分析方向建议")
        enriched.append("- 如果数据有明确的数值目标列+多个数值特征 → 用回归分析")
        enriched.append("- 如果有分组列+数值指标 → 用假设检验")
        enriched.append("- 如果问题模糊 → 用相关性分析做探索")
        enriched.append("- 如果有日期列 → 优先趋势分析")
        enriched.append("- 选 1-2 个最合适的方法即可，不要过度分析")

        return "\n".join(enriched)


    def _check_power(self, df, context, focus, n) -> list[str]:
        """功效预检"""
        warnings = []

        if n < POWER_MIN_TOTAL_SAMPLE:
            warnings.append(f"⚠️ 数据量偏少（n={n}），检验功效可能不足。")
            return warnings

        if "hypothesis_test" in focus:
            cat_cols = [
                s["column_name"] for s in context.get("column_semantics", [])
                if s.get("inferred_type") in ("categorical", "boolean", "ordinal")
                and s["column_name"] in df.columns
            ]
            if cat_cols:
                # 从 plan / context 推断分组列；不静默回退 cat_cols[0]
                group_candidate = (
                    context.get("_plan_group_col") or
                    next(
                        (s["column_name"] for s in context.get("column_semantics", [])
                         if s.get("suggested_role") == "group"),
                        None,
                    ) or
                    next(
                        (s["column_name"] for s in context.get("column_semantics", [])
                         if s.get("column_name") in cat_cols
                         and s.get("suggested_role") not in ("identifier", "ignore")),
                        None,
                    )
                )
                if group_candidate:
                    n_groups = df[group_candidate].nunique()
                    n_per_group = n // n_groups
                    if n_per_group < POWER_MIN_PER_GROUP_SAMPLE:
                        warnings.append(f"⚠️ 每组样本量偏少（n={n_per_group}），检测中等效应功效可能不足。")
                    elif n_per_group >= POWER_ADEQUATE_PER_GROUP:
                        try:
                            power_info = power_ttest(n_per_group, n_per_group, effect_size=POWER_EFFECT_SIZE_DEFAULT)
                            if "error" not in power_info:
                                power_pct = power_info.get("power", 0.0)
                                if power_pct >= POWER_TARGET_PCT:
                                    warnings.append(f"✅ 每组 n={n_per_group}，检测中等效应功效约 {power_pct:.0f}%，足够。")
                        except Exception:
                            pass

        if "regression" in focus:
            n_predictors = len([f for f in context.get("features", []) if f in df.columns])
            if n_predictors > 0 and n < POWER_REGRESSION_RATIO * n_predictors:
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
            cv_result = cross_validate(df, target, features, k_folds=self._config.analysis.k_folds)
            if "error" not in cv_result:
                if result.get("diagnostics") is None:
                    result["diagnostics"] = {}
                result["diagnostics"]["cross_validation"] = cv_result
        except Exception:
            logger.warning("交叉验证增强失败", exc_info=True)

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
                        result["significance"] = SIGNIFICANCE_LABEL_CORRECTED
        except Exception:
            logger.warning("多重比较校正失败", exc_info=True)

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
            if existing and existing[0]["similarity"] > ANALYST_DEDUP_SIMILARITY:
                continue
            analyst_knowledge.learn(
                scenario=scenario,
                method=method,
                method_code="",
                confidence=0.8 if significance == SIGNIFICANCE_LABEL_SIG else 0.6,
                tags=focus + [f"n={n}", significance],
                metadata={"project": project_id, "result": str(result.get("conclusion_plain", ""))[:100]},
            )
