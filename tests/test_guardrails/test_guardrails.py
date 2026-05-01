"""测试统计护栏"""

import pytest

from hagokyu.guardrails.statistical import (
    NoConclusionWithoutTest,
    MustReportEffectSize,
    MustReportCI,
    NoCausalClaimWithoutMethod,
    MustDiagnoseModel,
    StatisticalGuardrails,
    Severity,
)


class TestNoConclusionWithoutTest:
    def test_pass_no_conclusion(self):
        rule = NoConclusionWithoutTest()
        result = rule.check({"conclusion_plain": ""})
        assert result.passed

    def test_pass_conclusion_with_test(self):
        rule = NoConclusionWithoutTest()
        result = rule.check({
            "conclusion_plain": "有显著差异",
            "p_value": 0.01,
        })
        assert result.passed

    def test_fail_conclusion_without_test(self):
        rule = NoConclusionWithoutTest()
        result = rule.check({
            "conclusion_plain": "有显著差异",
        })
        assert not result.passed
        assert result.severity == Severity.MANDATORY


class TestMustReportEffectSize:
    def test_pass_no_significance(self):
        rule = MustReportEffectSize()
        result = rule.check({"p_value": None})
        assert result.passed

    def test_pass_significance_with_effect(self):
        rule = MustReportEffectSize()
        result = rule.check({
            "p_value": 0.01,
            "effect_size": 0.5,
        })
        assert result.passed

    def test_fail_significance_without_effect(self):
        rule = MustReportEffectSize()
        result = rule.check({
            "p_value": 0.01,
        })
        assert not result.passed


class TestMustReportCI:
    def test_pass_no_point_estimate(self):
        rule = MustReportCI()
        result = rule.check({})
        assert result.passed

    def test_fail_point_estimate_without_ci(self):
        rule = MustReportCI()
        result = rule.check({
            "coefficient": 2.31,
        })
        assert not result.passed

    def test_pass_point_estimate_with_ci(self):
        rule = MustReportCI()
        result = rule.check({
            "coefficient": 2.31,
            "confidence_interval": "[1.82, 2.80]",
        })
        assert result.passed


class TestNoCausalClaimWithoutMethod:
    def test_fail_causal_claim_without_method(self):
        rule = NoCausalClaimWithoutMethod()
        result = rule.check({
            "conclusion_plain": "广告导致销售额增加",
        })
        assert not result.passed

    def test_pass_causal_claim_with_method(self):
        rule = NoCausalClaimWithoutMethod()
        result = rule.check({
            "conclusion_plain": "广告导致销售额增加",
            "causal_method": "IV",
        })
        assert result.passed

    def test_pass_no_causal_claim(self):
        rule = NoCausalClaimWithoutMethod()
        result = rule.check({
            "conclusion_plain": "广告和销售额正相关",
        })
        assert result.passed


class TestMustDiagnoseModel:
    def test_fail_regression_without_diagnostics(self):
        rule = MustDiagnoseModel()
        result = rule.check({
            "analysis_type": "regression",
        })
        assert not result.passed

    def test_pass_regression_with_diagnostics(self):
        rule = MustDiagnoseModel()
        result = rule.check({
            "analysis_type": "regression",
            "diagnostics": {"residual_normality": {"met": True}},
        })
        assert result.passed

    def test_pass_non_regression(self):
        rule = MustDiagnoseModel()
        result = rule.check({
            "analysis_type": "ttest",
        })
        assert result.passed


class TestStatisticalGuardrails:
    def test_check_returns_all_rules(self):
        g = StatisticalGuardrails()
        results = g.check({})
        assert len(results) >= 14  # 5 mandatory + 5 warning + 4 suggestion

    def test_can_output_with_no_violations(self):
        g = StatisticalGuardrails()
        results = g.check({"conclusion_plain": ""})
        assert g.can_output(results)

    def test_cannot_output_with_mandatory_violation(self):
        g = StatisticalGuardrails()
        results = g.check({
            "conclusion_plain": "显著差异",
            # 没有 p_value → no_conclusion_without_test 违规
        })
        assert not g.can_output(results)

    def test_format_report(self):
        g = StatisticalGuardrails()
        results = g.check({"conclusion_plain": ""})
        report = g.format_report(results)
        assert "统计护栏" in report
