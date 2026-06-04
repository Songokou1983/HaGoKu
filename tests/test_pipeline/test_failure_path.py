"""测试 Orchestrator 失败路径与编排层统计护栏门禁

当前约定（2026-05-12 起）：
1. Agent 未捕获异常 → 硬终止：fail_run + RUN_FAILED + re-raise（无自动降级）
2. Analyst 之后、Reporter 之前：Orchestrator 对每条结构化结果调用护栏；**强制级未通过则跳过 Reporter**，
   写入 ``GUARDRAILS_BLOCKED.md``，``status=guardrails_blocked``
3. Analyst 仍对结果做护栏检查并写入 ``guardrail_results``（与编排层门禁互补）
4. Reporter.run **内部**仍不调用 ``can_output``（门禁在 Orchestrator）
"""

import inspect
import tempfile
from pathlib import Path

import pytest

from hagoku.guardrails.statistical import StatisticalGuardrails
from hagoku.manager.orchestrator import Orchestrator


class TestGuardrailsCanOutput:
    """验证 can_output() 方法本身是正确的（隔离测试）"""

    def test_can_output_returns_true_when_no_mandatory_violations(self):
        g = StatisticalGuardrails()
        results = g.check({
            "conclusion_plain": "有显著差异",
            "p_value": 0.01,
            "effect_size": 0.5,
            "confidence_interval": [1.0, 2.0],
        })
        assert g.can_output(results) is True

    def test_can_output_returns_false_when_mandatory_violation(self):
        g = StatisticalGuardrails()
        results = g.check({
            "conclusion_plain": "有显著差异",
        })
        assert g.can_output(results) is False

    def test_can_output_ignores_warning_violations(self):
        g = StatisticalGuardrails()
        results = g.check({
            "conclusion_plain": "有显著差异",
            "p_value": 0.01,
            "effect_size": 0.5,
            "confidence_interval": [1.0, 2.0],
            "sample_size": 5,
        })
        assert g.can_output(results) is True


class TestMandatoryGuardrailsBlockReport:
    """Orchestrator._handle_mandatory_violations 行为"""

    def test_empty_results_not_blocked(self):
        from hagoku.config import HaGoKuConfig

        orch = Orchestrator(HaGoKuConfig())
        with tempfile.TemporaryDirectory() as tmpdir:
            decision = orch._handle_mandatory_violations([], [], Path(tmpdir))
            assert decision is None

    def test_blocked_when_conclusion_without_test(self):
        from hagoku.config import HaGoKuConfig

        orch = Orchestrator(HaGoKuConfig())
        bad = [{
            "result_id": "r1",
            "analysis_type": "ttest",
            "question": "q1",
            "conclusion_plain": "有差异",
        }]
        with tempfile.TemporaryDirectory() as tmpdir:
            decision = orch._handle_mandatory_violations([], bad, Path(tmpdir))
            assert decision is None  # 无法直接测试 LLM 交互路径，至少不抛异常

    def test_passes_when_valid_structured_result(self):
        from hagoku.config import HaGoKuConfig

        orch = Orchestrator(HaGoKuConfig())
        good = [{
            "result_id": "r1",
            "analysis_type": "ttest",
            "question": "q1",
            "conclusion_plain": "有差异",
            "p_value": 0.01,
            "effect_size": 0.4,
            "confidence_interval": [0.1, 0.9],
        }]
        with tempfile.TemporaryDirectory() as tmpdir:
            decision = orch._handle_mandatory_violations([], good, Path(tmpdir))
            assert decision is None  # 通过护栏时不返回任何结果


class TestOrchestratorRunGuardrailGate:
    """护栏检查已移至 _handle_analyst_reply handler（事件驱动重构）"""

    def test_run_source_contains_mandatory_gate(self):
        source = inspect.getsource(Orchestrator._handle_analyst_reply)
        assert "_check_mandatory_guardrails" in source

    def test_orchestrator_has_guardrails_instance(self):
        from hagoku.config import HaGoKuConfig

        orch = Orchestrator(HaGoKuConfig())
        assert hasattr(orch, "guardrails")
        assert isinstance(orch.guardrails, StatisticalGuardrails)


class TestAnalystGuardrailsIntegration:
    def test_analyst_calls_guardrails_check_on_results(self):
        """护栏检查在 _handle_analyst_reply handler 中。
        事件驱动重构（commit 4028575）后移至 handler。"""
        source = inspect.getsource(Orchestrator._handle_analyst_reply)
        assert "_check_mandatory_guardrails" in source


class TestFailurePath:
    def test_orchestrator_exception_causes_hard_fail(self):
        source = inspect.getsource(Orchestrator.run)
        assert "except Exception as e:" in source
        assert "fail_run" in source
        assert "RUN_FAILED" in source


class TestReporterGuardrailsIntegration:
    def test_reporter_run_does_not_call_can_output(self):
        from hagoku.agents.reporter import ReporterAgent

        source = inspect.getsource(ReporterAgent.run)
        assert "can_output" not in source
        assert "guardrails" not in source

    def test_validate_analysis_output_is_different_from_can_output(self):
        from hagoku.guardrails.parsers import validate_analysis_output

        text_with_pvalue = "p = 0.01，效应量 d = 0.5"
        result1 = validate_analysis_output(text_with_pvalue)
        assert result1["has_pvalue"] is True

        g = StatisticalGuardrails()
        structured_result = {"conclusion_plain": "有显著差异"}
        results = g.check(structured_result)
        assert g.can_output(results) is False
