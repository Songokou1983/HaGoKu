"""Manager 计划生成测试

测试 Orchestrator._create_plan 的 LLM 驱动决策：
- LLM 成功 → 返回 LLM 生成的计划
- LLM 失败 → 降级到通用计划
- 无效 analyst_focus → 过滤为默认值
- 缺少 scout/reporter → 自动补充
- 事件发射验证
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from hagoku.config import HaGoKuConfig
from hagoku.llm.plan_schema import (
    DEFAULT_EXPLORATORY_FOCUS,
    VALID_ANALYST_FOCUS,
    VALID_AGENTS,
    LLMPlanResponse,
)
from hagoku.llm.prompts import (
    PLAN_ADJUSTMENT_USER,
    PLAN_GENERATION_SYSTEM,
    PLAN_GENERATION_USER,
)
from hagoku.manager.orchestrator import Orchestrator


# ── Fixtures ────────────────────────────────────────────────────


@pytest.fixture
def config() -> HaGoKuConfig:
    return HaGoKuConfig()


def _make_llm_response(
    plan_name: str = "趋势分析",
    agents: list[str] | None = None,
    analyst_focus: list[str] | None = None,
    target: str | None = None,
    query: str = "",
    reasoning: str = "test reasoning",
) -> LLMPlanResponse:
    return LLMPlanResponse(
        plan_name=plan_name,
        agents=agents or ["scout", "cleaner", "analyst", "reporter"],
        analyst_focus=analyst_focus or ["regression"],
        target=target,
        query=query,
        reasoning=reasoning,
    )


# ── Schema 测试 ────────────────────────────────────────────────


class TestLLMPlanResponse:
    def test_valid_response(self):
        resp = _make_llm_response(query="销量趋势如何")
        assert resp.plan_name == "趋势分析"
        assert "scout" in resp.agents
        assert "reporter" in resp.agents

    def test_all_valid_focus_values(self):
        for focus in VALID_ANALYST_FOCUS:
            resp = LLMPlanResponse(
                plan_name="test",
                agents=["scout", "analyst", "reporter"],
                analyst_focus=[focus],
                query="test",
                reasoning="test",
            )
            assert focus in resp.analyst_focus

    def test_all_valid_agents(self):
        for agent in VALID_AGENTS:
            resp = LLMPlanResponse(
                plan_name="test",
                agents=[agent],
                analyst_focus=["regression"],
                query="test",
                reasoning="test",
            )
            assert agent in resp.agents

    def test_target_optional(self):
        resp = _make_llm_response(target=None)
        assert resp.target is None

    def test_target_set(self):
        resp = _make_llm_response(target="销量")
        assert resp.target == "销量"

    def test_default_exploratory_focus(self):
        for f in DEFAULT_EXPLORATORY_FOCUS:
            assert f in VALID_ANALYST_FOCUS


# ── Prompt 测试 ────────────────────────────────────────────────


class TestPrompts:
    def test_generation_user_format(self):
        result = PLAN_GENERATION_USER.format(query="销量和广告费的关系")
        assert "销量和广告费的关系" in result

    def test_adjustment_user_format(self):
        result = PLAN_ADJUSTMENT_USER.format(
            query="销量趋势",
            plan_name="趋势分析",
            agents="scout, cleaner, analyst, reporter",
            analyst_focus="trend, regression",
            target="销量",
        )
        assert "销量趋势" in result
        assert "趋势分析" in result

    def test_system_prompt_mentions_key_analysis_types(self):
        key_terms = ["回归", "假设检验", "一起涨一起跌", "趋势", "因果"]
        for term in key_terms:
            assert term in PLAN_GENERATION_SYSTEM, f"缺少关键分析类型: {term}"


# ── _create_plan 测试（纯 LLM 驱动）────────────────────────────


class TestCreatePlanLLM:
    """_create_plan：LLM 唯一决策引擎，无规则分支"""

    @patch.object(Orchestrator, "_call_llm_for_plan")
    def test_llm_success_returns_plan(self, mock_call, config):
        """LLM 成功 → 返回 LLM 生成的计划"""
        mock_call.return_value = {
            "plan_name": "销量趋势分析",
            "agents": ["scout", "cleaner", "analyst", "reporter"],
            "analyst_focus": ["trend", "regression"],
            "query": "销量趋势如何变化",
            "reasoning": "用户问趋势",
            "llm_generated": True,
        }
        orch = Orchestrator(config=config)
        plan = orch._create_plan("销量趋势如何变化")
        assert plan["plan_name"] == "销量趋势分析"
        assert "trend" in plan["analyst_focus"]
        assert plan["llm_generated"] is True
        mock_call.assert_called_once()

    @patch.object(Orchestrator, "_call_llm_for_plan")
    def test_llm_fails_raises_runtime_error(self, mock_call, config):
        """LLM 失败 → 抛出 RuntimeError，不再静默降级"""
        mock_call.side_effect = RuntimeError("LLM 不可达")
        orch = Orchestrator(config=config)
        with pytest.raises(RuntimeError):
            orch._create_plan("任何问题")

    @patch.object(Orchestrator, "_call_llm_for_plan")
    def test_plan_name_contains_semantic_match(self, mock_call, config):
        """LLM 生成的 plan_name 包含语义相关内容（宽松匹配）"""
        mock_call.return_value = {
            "plan_name": "销量趋势分析",
            "agents": ["scout", "cleaner", "analyst", "reporter"],
            "analyst_focus": ["trend"],
            "query": "销量趋势如何变化",
            "reasoning": "趋势问题",
            "llm_generated": True,
        }
        orch = Orchestrator(config=config)
        plan = orch._create_plan("销量趋势如何变化")
        # LLM 主导：不强制等值，用包含判断
        assert "趋势" in plan["plan_name"] or "trend" in str(plan.get("plan_name", "")).lower()
        assert "trend" in plan["analyst_focus"]


# ── _call_llm_for_plan 核心逻辑 ────────────────────────────────


class TestCallLlmForPlan:
    @patch("hagoku.manager.orchestrator.create_structured_llm_client")
    def test_successful_call(self, mock_create_client):
        mock_client = MagicMock()
        mock_create_client.return_value = mock_client
        mock_response = _make_llm_response(
            plan_name="趋势分析",
            analyst_focus=["trend", "regression"],
            query="销量趋势",
        )
        mock_client.chat.completions.create.return_value = mock_response

        config = HaGoKuConfig()
        orch = Orchestrator(config=config)
        result = orch._call_llm_for_plan("销量趋势")

        assert result is not None
        assert result["plan_name"] == "趋势分析"
        assert "trend" in result["analyst_focus"]
        assert "scout" in result["agents"]
        assert "reporter" in result["agents"]

    @patch("hagoku.manager.orchestrator.create_structured_llm_client")
    def test_invalid_focus_filtered(self, mock_create_client):
        mock_client = MagicMock()
        mock_create_client.return_value = mock_client
        mock_response = LLMPlanResponse(
            plan_name="test",
            agents=["scout", "analyst", "reporter"],
            analyst_focus=["invalid_type", "another_bad"],
            query="test",
            reasoning="test",
        )
        mock_client.chat.completions.create.return_value = mock_response

        config = HaGoKuConfig()
        orch = Orchestrator(config=config)
        result = orch._call_llm_for_plan("test")

        assert result is not None
        assert result["analyst_focus"] == DEFAULT_EXPLORATORY_FOCUS

    @patch("hagoku.manager.orchestrator.create_structured_llm_client")
    def test_missing_scout_reporter_added(self, mock_create_client):
        mock_client = MagicMock()
        mock_create_client.return_value = mock_client
        mock_response = LLMPlanResponse(
            plan_name="test",
            agents=["analyst"],
            analyst_focus=["regression"],
            query="test",
            reasoning="test",
        )
        mock_client.chat.completions.create.return_value = mock_response

        config = HaGoKuConfig()
        orch = Orchestrator(config=config)
        result = orch._call_llm_for_plan("test")

        assert result is not None
        assert "scout" in result["agents"]
        assert "reporter" in result["agents"]
        assert "analyst" in result["agents"]

    @patch("hagoku.manager.orchestrator.create_structured_llm_client")
    def test_llm_exception_raises_runtime_error(self, mock_create_client):
        mock_create_client.side_effect = ConnectionError("llama-server down")

        config = HaGoKuConfig()
        orch = Orchestrator(config=config)
        with pytest.raises(RuntimeError):
            orch._call_llm_for_plan("test")

    @patch("hagoku.manager.orchestrator.create_structured_llm_client")
    def test_llm_timeout_raises_runtime_error(self, mock_create_client):
        mock_client = MagicMock()
        mock_create_client.return_value = mock_client
        mock_client.chat.completions.create.side_effect = TimeoutError("timeout")

        config = HaGoKuConfig()
        orch = Orchestrator(config=config)
        with pytest.raises(RuntimeError):
            orch._call_llm_for_plan("test")

    @patch("hagoku.manager.orchestrator.create_structured_llm_client")
    def test_lazy_client_initialization(self, mock_create_client):
        mock_client = MagicMock()
        mock_create_client.return_value = mock_client
        mock_response = _make_llm_response(query="test")
        mock_client.chat.completions.create.return_value = mock_response

        config = HaGoKuConfig()
        orch = Orchestrator(config=config)

        assert orch._llm_client is None

        orch._call_llm_for_plan("test")
        assert orch._llm_client is not None
        mock_create_client.assert_called_once()

        orch._call_llm_for_plan("test2")
        mock_create_client.assert_called_once()


# ── 事件发射测试 ──────────────────────────────────────────────


class TestEventEmission:
    @patch("hagoku.manager.orchestrator.create_structured_llm_client")
    def test_plan_created_event(self, mock_create_client, config):
        """LLM 成功生成计划时发射 PLAN_CREATED 事件。mock LLM 客户端层，
        让真实 _call_llm_for_plan / _create_plan 执行并发射事件。"""
        mock_client = MagicMock()
        mock_create_client.return_value = mock_client
        mock_response = _make_llm_response(
            plan_name="探索性分析",
            analyst_focus=["correlation"],
            query="数据有什么模式",
            reasoning="开放性问题",
        )
        mock_client.chat.completions.create.return_value = mock_response

        orch = Orchestrator(config=config)
        orch._create_plan("数据有什么模式")

        plan_events = [
            e for e in orch.event_bus.events
            if e.event_type.value == "plan_created"
        ]
        assert len(plan_events) == 1
        assert plan_events[0].data["source"] == "llm"

    @patch("hagoku.manager.orchestrator.create_structured_llm_client")
    def test_llm_failure_emits_thinking_and_raises(self, mock_create):
        mock_create.side_effect = ConnectionError("server down")
        config = HaGoKuConfig()
        orch = Orchestrator(config=config)
        with pytest.raises(RuntimeError):
            orch._create_plan("test query")

        thinking_events = [
            e for e in orch.event_bus.events
            if e.event_type.value == "agent_thinking"
        ]
        assert any("LLM" in e.data.get("thought", "") for e in thinking_events)
