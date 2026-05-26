"""HaGoKu Studio 统计护栏核心"""

from __future__ import annotations

from enum import Enum
from typing import Any, Protocol

from pydantic import BaseModel


class Severity(Enum):
    """护栏严重级别"""

    MANDATORY = "mandatory"  # 阻止输出
    WARNING = "warning"  # 标注警告但允许输出
    SUGGESTION = "suggestion"  # 建议但不过问


class GuardrailResult(BaseModel):
    """单条护栏检查结果"""

    rule: str
    severity: Severity
    passed: bool
    message: str = ""
    suggestion: str | None = None

    def __str__(self) -> str:
        icons = {
            Severity.MANDATORY: "🚫",
            Severity.WARNING: "⚠️",
            Severity.SUGGESTION: "💡",
        }
        status = "✅" if self.passed else icons[self.severity]
        text = f"{status} [{self.severity.value}] {self.rule}"
        if self.message:
            text += f": {self.message}"
        if self.suggestion:
            text += f" → {self.suggestion}"
        return text


class GuardrailRule(Protocol):
    """护栏规则协议"""

    @property
    def rule_name(self) -> str: ...

    @property
    def severity(self) -> Severity: ...

    def check(self, analysis_result: dict[str, Any]) -> GuardrailResult: ...


# ── 强制级规则 ────────────────────────────────────────────────


class NoConclusionWithoutTest:
    """没有统计检验不许下结论"""

    @property
    def rule_name(self) -> str:
        return "no_conclusion_without_test"

    @property
    def severity(self) -> Severity:
        return Severity.MANDATORY

    def check(self, analysis_result: dict[str, Any]) -> GuardrailResult:
        has_conclusion = bool(analysis_result.get("conclusion_plain"))
        has_test = analysis_result.get("p_value") is not None or analysis_result.get("test_statistic") is not None
        passed = not has_conclusion or has_test
        return GuardrailResult(
            rule=self.rule_name,
            severity=self.severity,
            passed=passed,
            message="下了结论但没有数据支撑，可能是分析类型选错了" if not passed else "",
            suggestion="请检查是否选对了分析类型，或确认数据是否跑了这个检验" if not passed else None,
        )


class MustReportEffectSize:
    """报告显著性必须配效应量"""

    @property
    def rule_name(self) -> str:
        return "must_report_effect_size"

    @property
    def severity(self) -> Severity:
        return Severity.MANDATORY

    def check(self, analysis_result: dict[str, Any]) -> GuardrailResult:
        has_significance = analysis_result.get("p_value") is not None
        has_effect_size = analysis_result.get("effect_size") is not None
        passed = not has_significance or has_effect_size
        return GuardrailResult(
            rule=self.rule_name,
            severity=self.severity,
            passed=passed,
            message="只说明了有没有差异，没说差异有多大，结论不够完整" if not passed else "",
            suggestion="请同时报告效应量（效应量告诉你差异的实际大小，比 p 值更重要）" if not passed else None,
        )


class MustReportCI:
    """点估计必须配置信区间"""

    @property
    def rule_name(self) -> str:
        return "must_report_ci"

    @property
    def severity(self) -> Severity:
        return Severity.MANDATORY

    def check(self, analysis_result: dict[str, Any]) -> GuardrailResult:
        has_point_estimate = (
            analysis_result.get("point_estimate") is not None
            or analysis_result.get("coefficient") is not None
            or analysis_result.get("coefficients") is not None
        )
        # 兼容 regression 的 confidence_intervals (复数) 和 ttest 的 confidence_interval (单数)
        has_ci = (
            analysis_result.get("confidence_interval") is not None
            or analysis_result.get("confidence_intervals") is not None
        )
        passed = not has_point_estimate or has_ci
        return GuardrailResult(
            rule=self.rule_name,
            severity=self.severity,
            passed=passed,
            message="只给了估计值，没说这个估计靠不靠谱" if not passed else "",
            suggestion="请加上置信区间，说明这个估计值的可信范围" if not passed else None,
        )


class NoCausalClaimWithoutMethod:
    """观测数据必须用因果推断方法才能声称因果"""

    @property
    def rule_name(self) -> str:
        return "no_causal_claim_without_method"

    @property
    def severity(self) -> Severity:
        return Severity.MANDATORY

    def check(self, analysis_result: dict[str, Any]) -> GuardrailResult:
        # 信任 LLM 的自我声明：causal_method 由 LLM 自行设置。
        # 代码不再扫描自然语言文本检测因果语义——语义判断是 LLM 的职责。
        # 仅做结构性校验：如果 LLM 声明了因果方法，必须是非空字符串。
        has_causal_method = analysis_result.get("causal_method") is not None
        is_experimental = analysis_result.get("design_type") == "experimental"

        if has_causal_method:
            cm = analysis_result.get("causal_method")
            causal_method_valid = isinstance(cm, str) and cm.strip() != ""
        else:
            causal_method_valid = True  # LLM 未声明因果 → 通过

        passed = causal_method_valid or is_experimental
        return GuardrailResult(
            rule=self.rule_name,
            severity=self.severity,
            passed=passed,
            message="因果方法声明无效，请提供有效的因果推断方法或改为相关性描述" if not passed else "",
            suggestion="如果分析不涉及因果推断，请移除 causal_method 字段；否则填写具体方法名" if not passed else None,
        )


class MustDiagnoseModel:
    """建模后必须做残差诊断"""

    @property
    def rule_name(self) -> str:
        return "must_diagnose_model"

    @property
    def severity(self) -> Severity:
        return Severity.MANDATORY

    def check(self, analysis_result: dict[str, Any]) -> GuardrailResult:
        is_modeling = analysis_result.get("analysis_type", "") in (
            "regression", "linear_regression", "logistic_regression",
            "ols", "glm", "mixed_model",
        )
        has_diagnostics = bool(analysis_result.get("diagnostics"))
        passed = not is_modeling or has_diagnostics
        return GuardrailResult(
            rule=self.rule_name,
            severity=self.severity,
            passed=passed,
            message="回归模型可能不适用于这份数据" if not passed else "",
            suggestion="请检查数据是否适合做回归分析，或尝试其他分析方法" if not passed else None,
        )


# ── 警告级规则 ────────────────────────────────────────────────


class AssumptionsViolated:
    """统计假设不满足时标注"""

    @property
    def rule_name(self) -> str:
        return "assumptions_violated"

    @property
    def severity(self) -> Severity:
        return Severity.WARNING

    def check(self, analysis_result: dict[str, Any]) -> GuardrailResult:
        assumptions = analysis_result.get("assumptions", {})
        # analysis tools store assumptions as nested dicts: {"normality_group1": {"p_value": 0.03, "met": False}}
        violated = [
            name for name, value in assumptions.items()
            if isinstance(value, dict) and not value.get("met", True)
        ]
        passed = len(violated) == 0
        return GuardrailResult(
            rule=self.rule_name,
            severity=self.severity,
            passed=passed,
            message="数据可能不适合当前的分析方法" if not passed else "",
            suggestion="请尝试其他分析方法，或检查数据格式是否正确" if not passed else None,
        )


class SmallSampleSize:
    """样本量不足时警告"""

    @property
    def rule_name(self) -> str:
        return "small_sample_size"

    @property
    def severity(self) -> Severity:
        return Severity.WARNING

    # 基本阈值：参数方法 ≥ 30，非参数 ≥ 10
    PARAM_THRESHOLD = 30
    NONPARAM_THRESHOLD = 10

    def check(self, analysis_result: dict[str, Any]) -> GuardrailResult:
        n = analysis_result.get("sample_size") or analysis_result.get("n_obs")
        if n is None:
            return GuardrailResult(rule=self.rule_name, severity=self.severity, passed=True)

        is_parametric = analysis_result.get("analysis_type", "") not in (
            "mann_whitney", "wilcoxon", "kruskal_wallis",
            "spearman", "bootstrap", "permutation",
        )
        threshold = self.PARAM_THRESHOLD if is_parametric else self.NONPARAM_THRESHOLD
        passed = n >= threshold

        return GuardrailResult(
            rule=self.rule_name,
            severity=self.severity,
            passed=passed,
            message=f"数据量偏少（{n}条），结论可能不可靠" if not passed else "",
            suggestion="建议增加数据量，或确认是否选对了分析列" if not passed else None,
        )


class HighVIF:
    """多重共线性超标时警告"""

    @property
    def rule_name(self) -> str:
        return "high_vif"

    @property
    def severity(self) -> Severity:
        return Severity.WARNING

    VIF_THRESHOLD = 10.0

    def check(self, analysis_result: dict[str, Any]) -> GuardrailResult:
        # VIF 数据可能在 diagnostics["vif"] 或 assumptions["multicollinearity"]["vif"]
        vif_data = analysis_result.get("vif", {})
        if not vif_data:
            diagnostics = analysis_result.get("diagnostics", {})
            vif_data = diagnostics.get("vif", {})
        if not vif_data:
            assumptions = analysis_result.get("assumptions", {})
            mc = assumptions.get("multicollinearity", {})
            vif_data = mc.get("vif", {})
        if not vif_data:
            # 没有做 VIF 检查，不做判断
            return GuardrailResult(rule=self.rule_name, severity=self.severity, passed=True)

        high_vif_vars = {var: vif for var, vif in vif_data.items() if isinstance(vif, (int, float)) and vif > self.VIF_THRESHOLD}
        passed = len(high_vif_vars) == 0
        return GuardrailResult(
            rule=self.rule_name,
            severity=self.severity,
            passed=passed,
            message="某些列包含的信息太相似，可能影响模型准确性" if not passed else "",
            suggestion="请检查是否有重复或冗余的列，移除冗余列后重新分析" if not passed else None,
        )


class PotentialOverfitting:
    """训练测试差异过大时警告"""

    @property
    def rule_name(self) -> str:
        return "potential_overfitting"

    @property
    def severity(self) -> Severity:
        return Severity.WARNING

    RATIO_THRESHOLD = 0.15  # 训练/测试 R² 差异超过 15% 警告

    def check(self, analysis_result: dict[str, Any]) -> GuardrailResult:
        # cross_validate() returns train_mean/test_mean/generalization_gap/overfitting_detected
        train_score = (
            analysis_result.get("train_mean")
            or analysis_result.get("train_r_squared")
            or analysis_result.get("train_score")
        )
        test_score = (
            analysis_result.get("test_mean")
            or analysis_result.get("test_r_squared")
            or analysis_result.get("test_score")
        )
        # 也检查 diagnostics 中嵌套的 CV 结果
        if train_score is None or test_score is None:
            cv = analysis_result.get("cross_validation", {})
            if train_score is None:
                train_score = cv.get("train_mean") or cv.get("train_r_squared") or cv.get("train_score")
            if test_score is None:
                test_score = cv.get("test_mean") or cv.get("test_r_squared") or cv.get("test_score")
        if train_score is None or test_score is None:
            return GuardrailResult(rule=self.rule_name, severity=self.severity, passed=True)

        gap = abs(train_score - test_score)
        passed = gap <= self.RATIO_THRESHOLD
        return GuardrailResult(
            rule=self.rule_name,
            severity=self.severity,
            passed=passed,
            message="模型只在这份数据上有效，换份数据就不准了" if not passed else "",
            suggestion="建议简化模型，或增加数据量后重新建模" if not passed else None,
        )


class CleaningHighImpact:
    """清洗操作影响了 >10% 数据时警告"""

    @property
    def rule_name(self) -> str:
        return "cleaning_high_impact"

    @property
    def severity(self) -> Severity:
        return Severity.WARNING

    IMPACT_THRESHOLD = 0.10

    def check(self, analysis_result: dict[str, Any]) -> GuardrailResult:
        # cleaning_impact 可能在 analysis_result 顶层或 cleaning_report 中
        impact = analysis_result.get("cleaning_impact")
        if impact is None:
            cleaning_report = analysis_result.get("cleaning_report", {})
            impact = cleaning_report.get("impact_rate")

        if impact is None:
            return GuardrailResult(rule=self.rule_name, severity=self.severity, passed=True)

        # impact 可能是 dict {rows_removed: 50, total_rows: 500} 或 float
        if isinstance(impact, dict):
            removed = impact.get("rows_removed", 0)
            total = impact.get("total_rows", 1)
            ratio = removed / total if total > 0 else 0
        elif isinstance(impact, (int, float)):
            ratio = impact
        else:
            ratio = 0

        passed = ratio <= self.IMPACT_THRESHOLD
        return GuardrailResult(
            rule=self.rule_name,
            severity=self.severity,
            passed=passed,
            message=f"很多数据被删掉了（{ratio:.1%}），可能影响结论准确性" if not passed else "",
            suggestion="请检查原始数据是否有问题，或确认分析列是否选对了" if not passed else None,
        )


# ── 提示级规则 ────────────────────────────────────────────────


class SuggestNonlinear:
    """残差模式暗示非线性时建议"""

    @property
    def rule_name(self) -> str:
        return "suggest_nonlinear"

    @property
    def severity(self) -> Severity:
        return Severity.SUGGESTION

    def check(self, analysis_result: dict[str, Any]) -> GuardrailResult:
        diagnostics = analysis_result.get("diagnostics", {})
        residual_pattern = diagnostics.get("residual_pattern", {})
        # _detect_residual_pattern() returns {"pattern": str, "met": bool, "verdict": str}
        if isinstance(residual_pattern, dict):
            pattern_name = residual_pattern.get("pattern", "")
        else:
            # 兼容直接传字符串的情况
            pattern_name = str(residual_pattern)
        has_nonlinear_pattern = pattern_name in ("u_shape", "inverted_u", "funnel", "curved")

        return GuardrailResult(
            rule=self.rule_name,
            severity=self.severity,
            passed=not has_nonlinear_pattern,
            message="数据里存在曲线关系，当前的分析方法捕捉不到" if has_nonlinear_pattern else "",
            suggestion="建议尝试其他能处理曲线关系的方法重新分析" if has_nonlinear_pattern else None,
        )


class SuggestInteraction:
    """变量间可能存在交互效应时建议"""

    @property
    def rule_name(self) -> str:
        return "suggest_interaction"

    @property
    def severity(self) -> Severity:
        return Severity.SUGGESTION

    def check(self, analysis_result: dict[str, Any]) -> GuardrailResult:
        interaction_hints = analysis_result.get("interaction_hints", [])
        has_hints = len(interaction_hints) > 0

        return GuardrailResult(
            rule=self.rule_name,
            severity=self.severity,
            passed=not has_hints,
            message="有些因素的影响取决于其他因素，不能单独来看" if has_hints else "",
            suggestion="可以尝试分不同维度分别分析，或增加数据量后再深入研究" if has_hints else None,
        )


class MissingNotRandom:
    """缺失非随机时建议谨慎处理"""

    @property
    def rule_name(self) -> str:
        return "missing_not_random"

    @property
    def severity(self) -> Severity:
        return Severity.SUGGESTION

    def check(self, analysis_result: dict[str, Any]) -> GuardrailResult:
        missing_mechanism = analysis_result.get("missing_mechanism", "")
        # cleaning tools 返回小写 ("mar", "mnar")，兼容大小写
        if isinstance(missing_mechanism, str):
            missing_mechanism = missing_mechanism.upper()
        elif isinstance(missing_mechanism, dict):
            # 如果是 {column: mechanism} 字典，检查是否有任何列非 MCAR
            missing_mechanism = "MNAR" if any(
                v.upper() in ("MAR", "MNAR") for v in missing_mechanism.values() if isinstance(v, str)
            ) else ""
        is_not_random = missing_mechanism in ("MAR", "MNAR")

        return GuardrailResult(
            rule=self.rule_name,
            severity=self.severity,
            passed=not is_not_random,
            message="缺失的数据可能有规律，删掉这些数据可能影响结论准确性" if is_not_random else "",
            suggestion="请检查原始数据，或确认分析列是否选对了" if is_not_random else None,
        )


class ConsiderPowerAnalysis:
    """建议做功效分析确认样本量足够"""

    @property
    def rule_name(self) -> str:
        return "consider_power_analysis"

    @property
    def severity(self) -> Severity:
        return Severity.SUGGESTION

    def check(self, analysis_result: dict[str, Any]) -> GuardrailResult:
        has_power = analysis_result.get("power_analysis") is not None
        has_test = analysis_result.get("p_value") is not None

        # 如果做了检验但没做功效分析，建议
        need_suggest = has_test and not has_power

        return GuardrailResult(
            rule=self.rule_name,
            severity=self.severity,
            passed=not need_suggest,
            message="数据量可能不足以检测到真实存在的差异" if need_suggest else "",
            suggestion="建议增加数据量后再分析，或接受结论不确定性较高的现实" if need_suggest else None,
        )


# ── 护栏引擎 ─────────────────────────────────────────────────


class StatisticalGuardrails:
    """统计护栏引擎：确保分析不犯低级错误"""

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        """
        Args:
            config: 护栏配置，可覆盖默认阈值
        """
        self.config = config or {}
        self._thresholds = self._load_thresholds()

        self.mandatory_rules: list[GuardrailRule] = [
            NoConclusionWithoutTest(),
            MustReportEffectSize(),
            MustReportCI(),
            NoCausalClaimWithoutMethod(),
            MustDiagnoseModel(),
        ]

        self.warning_rules: list[GuardrailRule] = [
            AssumptionsViolated(),
            SmallSampleSize(),
            HighVIF(),
            PotentialOverfitting(),
            CleaningHighImpact(),
        ]

        self.suggestion_rules: list[GuardrailRule] = [
            SuggestNonlinear(),
            SuggestInteraction(),
            MissingNotRandom(),
            ConsiderPowerAnalysis(),
        ]

    def _load_thresholds(self) -> dict[str, Any]:
        """加载阈值配置"""
        defaults = {
            "cleaning_impact_warning": 0.10,
            "vif_threshold": 10.0,
            "overfit_gap_threshold": 0.15,
            "param_sample_threshold": 30,
            "nonparam_sample_threshold": 10,
        }
        defaults.update(self.config.get("thresholds", {}))
        return defaults

    @property
    def all_rules(self) -> list[GuardrailRule]:
        """所有规则"""
        return self.mandatory_rules + self.warning_rules + self.suggestion_rules

    def check(self, analysis_result: dict[str, Any]) -> list[GuardrailResult]:
        """
        检查分析结果，返回所有护栏检查结果

        Args:
            analysis_result: 分析结果字典，包含 p_value, effect_size, conclusion 等

        Returns:
            所有规则的检查结果列表
        """
        results = []
        for rule in self.all_rules:
            try:
                result = rule.check(analysis_result)
                results.append(result)
            except Exception:
                results.append(GuardrailResult(
                    rule=rule.rule_name,
                    severity=rule.severity,
                    passed=False,
                    message="护栏检查执行出错",
                ))
        return results

    def check_mandatory(self, analysis_result: dict[str, Any]) -> list[GuardrailResult]:
        """只检查强制级规则"""
        return [
            rule.check(analysis_result)
            for rule in self.mandatory_rules
        ]

    def can_output(self, results: list[GuardrailResult]) -> bool:
        """是否有强制级违规阻止输出"""
        return not any(
            r.severity == Severity.MANDATORY and not r.passed
            for r in results
        )

    def get_violations(self, results: list[GuardrailResult]) -> dict[Severity, list[GuardrailResult]]:
        """按严重级别分组获取违规"""
        violations: dict[Severity, list[GuardrailResult]] = {
            Severity.MANDATORY: [],
            Severity.WARNING: [],
            Severity.SUGGESTION: [],
        }
        for r in results:
            if not r.passed:
                violations[r.severity].append(r)
        return violations

    def format_report(self, results: list[GuardrailResult]) -> str:
        """格式化护栏报告"""
        lines = ["📊 统计护栏检查结果", "─" * 40]

        violations = self.get_violations(results)
        total = len(results)
        passed = sum(1 for r in results if r.passed)

        lines.append(f"总计: {passed}/{total} 通过")

        if violations[Severity.MANDATORY]:
            lines.append(f"\n🚫 需要关注的问题 ({len(violations[Severity.MANDATORY])}):")
            for v in violations[Severity.MANDATORY]:
                lines.append(f"  • {v.message}")
                if v.suggestion:
                    lines.append(f"    → {v.suggestion}")

        if violations[Severity.WARNING]:
            lines.append(f"\n⚠️ 注意 ({len(violations[Severity.WARNING])}):")
            for v in violations[Severity.WARNING]:
                lines.append(f"  • {v.message}")

        if violations[Severity.SUGGESTION]:
            lines.append(f"\n💡 供参考 ({len(violations[Severity.SUGGESTION])}):")
            for v in violations[Severity.SUGGESTION]:
                lines.append(f"  • {v.message}")

        if self.can_output(results):
            lines.append("\n✅ 强制级护栏通过，可生成正式报告")
        else:
            lines.append("\n🚫 存在强制级违规：按产品规则不应输出正式报告（编排层将跳过 Reporter）")

        return "\n".join(lines)
