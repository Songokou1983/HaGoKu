"""测试 Orchestrator 失败与降级路径

本文件验证 1.5 缺口的当前实现状态：
- Agent 失败时 Orchestrator 是否按产品设计降级或终止
- 护栏 can_output 与 Reporter 收紧路径可追踪

关键发现（2026-05-12）：
1. Agent 失败 → 硬终止（无降级）：orchestrator.py L713-717
2. guardrails.can_output() 存在但从未在 Orchestrator→Reporter 路径中被调用
3. Analyst 自己有 guardrails 实例并做检查，但结果不阻塞 Reporter
"""

import pytest
from unittest.mock import MagicMock, patch

from hagoku.guardrails.statistical import StatisticalGuardrails, Severity


class TestGuardrailsCanOutput:
    """验证 can_output() 方法本身是正确的（隔离测试）"""

    def test_can_output_returns_true_when_no_mandatory_violations(self):
        """无强制级违规时 can_output 返回 True"""
        g = StatisticalGuardrails()
        results = g.check({
            "conclusion_plain": "有显著差异",
            "p_value": 0.01,
            "effect_size": 0.5,
            "confidence_interval": [1.0, 2.0],
        })
        assert g.can_output(results) is True

    def test_can_output_returns_false_when_mandatory_violation(self):
        """有强制级违规时 can_output 返回 False"""
        g = StatisticalGuardrails()
        # 下结论但没有统计检验 → MANDATORY 违规
        results = g.check({
            "conclusion_plain": "有显著差异",
            # 缺少 p_value
        })
        assert g.can_output(results) is False

    def test_can_output_ignores_warning_violations(self):
        """警告级违规不阻止输出"""
        g = StatisticalGuardrails()
        results = g.check({
            "conclusion_plain": "有显著差异",
            "p_value": 0.01,
            "effect_size": 0.5,
            "confidence_interval": [1.0, 2.0],
            "sample_size": 5,  # 小样本 → WARNING，但不阻止输出
        })
        assert g.can_output(results) is True


class TestOrchestratorGuardrailsUsage:
    """验证 Orchestrator 中 guardrails 的使用情况

    关键缺口：orchestrator.guardrails 实例化但从未调用
    """

    def test_orchestrator_has_guardrails_instance(self):
        """Orchestrator 实例化 StatisticalGuardrails"""
        from hagoku.config import HaGoKuConfig
        from hagoku.manager.orchestrator import Orchestrator

        config = HaGoKuConfig()
        orch = Orchestrator(config)

        # Orchestrator 有 guardrails 属性
        assert hasattr(orch, "guardrails")
        assert isinstance(orch.guardrails, StatisticalGuardrails)

    def test_orchestrator_guardrails_never_called_in_run(self):
        """验证 orchestrator.guardrails 从未在 run() 中被调用

        这是 1.5 的核心问题：can_output() 从未被用来决定是否调用 Reporter
        """
        from hagoku.manager.orchestrator import Orchestrator

        # 检查 run() 方法的源代码中是否调用了 guardrails
        import inspect
        source = inspect.getsource(Orchestrator.run)

        # can_output 不在 run() 源代码中
        assert "can_output" not in source
        # guardrails.check 不在 run() 源代码中
        assert "guardrails.check" not in source


class TestAnalystGuardrailsIntegration:
    """验证 Analyst 中 guardrails 的使用情况

    Analyst 有自己的 guardrails 实例并在结果上调用 check()
    """

    def test_analyst_has_guardrails_instance(self):
        """Analyst 实例化自己的 StatisticalGuardrails"""
        from hagoku.agents.analyst import AnalystAgent
        from hagoku.config import HaGoKuConfig
        from hagoku.observability.event_bus import EventBus

        config = HaGoKuConfig()
        event_bus = EventBus()
        analyst = AnalystAgent(config.llm, event_bus)

        assert hasattr(analyst, "guardrails")
        assert isinstance(analyst.guardrails, StatisticalGuardrails)

    def test_analyst_calls_guardrails_check_on_results(self):
        """Analyst 在结果上调用 guardrails.check()"""
        from hagoku.agents.analyst import AnalystAgent
        import inspect

        # 检查 run() 方法的源代码中是否调用了 guardrails.check
        source = inspect.getsource(AnalystAgent.run)
        assert "guardrails.check" in source


class TestFailurePath:
    """验证 Agent 失败时的路径

    当前实现：硬终止，无降级
    orchestrator.py L713-717:
        except Exception as e:
            duration_ms = int((datetime.now() - run_start).total_seconds() * 1000)
            self.db.fail_run(run_id, duration_ms=duration_ms)
            self.event_bus.emit(EventType.RUN_FAILED, "manager", {"error": str(e)})
            raise
    """

    def test_orchestrator_exception_causes_hard_fail(self):
        """Agent 异常导致硬失败（无降级）"""
        import inspect
        from hagoku.manager.orchestrator import Orchestrator

        source = inspect.getsource(Orchestrator.run)

        # 确认有 try-except 块
        assert "except Exception as e:" in source
        # 确认调用 fail_run
        assert "fail_run" in source
        # 确认发射 RUN_FAILED 事件
        assert "RUN_FAILED" in source
        # 确认重新抛出异常
        assert "raise" in source

    def test_no_graceful_degradation_on_agent_failure(self):
        """当前无优雅降级机制"""
        import inspect
        from hagoku.manager.orchestrator import Orchestrator

        source = inspect.getsource(Orchestrator.run)

        # 检查是否有降级逻辑（如 "degrade", "fallback", "retry"）
        degradation_keywords = ["degrade", "fallback", "retry", "retry_on"]
        has_degradation = any(kw in source.lower() for kw in degradation_keywords)

        # 当前实现没有降级
        assert has_degradation is False


class TestReporterGuardrailsIntegration:
    """验证 Reporter 是否调用 guardrails

    关键缺口：Reporter.run() 从未调用 can_output() 来决定是否生成报告
    """

    def test_reporter_run_does_not_call_can_output(self):
        """Reporter.run() 不调用 can_output()"""
        from hagoku.agents.reporter import ReporterAgent
        import inspect

        source = inspect.getsource(ReporterAgent.run)

        # can_output 不在 Reporter.run() 中
        assert "can_output" not in source
        # guardrails 不在 Reporter.run() 中
        assert "guardrails" not in source

    def test_validate_analysis_output_is_different_from_can_output(self):
        """Reporter 调用的 validate_analysis_output ≠ guardrails.can_output()

        validate_analysis_output 是文本解析（检查是否包含 p_value 等字符串）
        can_output 是护栏引擎（检查 MANDATORY 违规）
        两者功能不同，不可互换
        """
        from hagoku.guardrails.parsers import validate_analysis_output

        # validate_analysis_output 检查文本中是否有特定字段
        # 匹配 "p = 0.042" 或 "p < 0.001" 等模式
        text_with_pvalue = "p = 0.01，效应量 d = 0.5"
        result1 = validate_analysis_output(text_with_pvalue)
        assert result1["has_pvalue"] is True

        # 但这不等于 guardrails.can_output()
        # guardrails 需要结构化结果 dict，不是文本
        from hagoku.guardrails.statistical import StatisticalGuardrails

        g = StatisticalGuardrails()
        structured_result = {
            "conclusion_plain": "有显著差异",
            # 缺少 p_value
        }
        results = g.check(structured_result)
        assert g.can_output(results) is False  # 强制级违规

        # 验证两个方法检查的是不同维度
        assert result1["has_pvalue"] is True  # 文本中有 "p = 0.01"
        assert g.can_output(results) is False  # 但结构化结果没有 p_value
