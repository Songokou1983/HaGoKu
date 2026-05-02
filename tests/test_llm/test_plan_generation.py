"""Manager AI 计划生成测试

测试 Orchestrator._create_plan 的三层决策逻辑：
- Tier 1: 规则匹配 + rule_weight ≥ 0.9 → 直接返回规则计划
- Tier 2: 规则匹配 + 混合模式 → LLM 调整规则计划
- Tier 3: 无规则匹配 + llm_weight > 0 → LLM 从零生成计划
- 降级: LLM 失败 → 规则计划或通用计划
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from hagokyu.config import HaGoKuConfig, ManagerModeConfig, LLMConfig
from hagokyu.llm.plan_schema import (
    DEFAULT_EXPLORATORY_FOCUS,
    VALID_ANALYST_FOCUS,
    VALID_AGENTS,
    LLMPlanResponse,
)
from hagokyu.llm.prompts import (
    PLAN_ADJUSTMENT_USER,
    PLAN_GENERATION_SYSTEM,
    PLAN_GENERATION_USER,
)
from hagokyu.manager.orchestrator import Orchestrator


# ── Fixtures ────────────────────────────────────────────────────


@pytest.fixture
def config_pure_rule() -> HaGoKuConfig:
    """纯规则模式配置"""
    cfg = HaGoKuConfig()
    cfg.manager.mode = "pure_rule"
    cfg.manager.rule_weight = 1.0
    cfg.manager.llm_weight = 0.0
    return cfg


@pytest.fixture
def config_local_weak() -> HaGoKuConfig:
    """本地弱 AI 模式配置"""
    cfg = HaGoKuConfig()
    cfg.manager.mode = "local_weak"
    cfg.manager.rule_weight = 0.9
    cfg.manager.llm_weight = 0.1
    return cfg


@pytest.fixture
def config_local_strong() -> HaGoKuConfig:
    """本地强 AI 模式配置（混合模式）"""
    cfg = HaGoKuConfig()
    cfg.manager.mode = "local_strong"
    cfg.manager.rule_weight = 0.5
    cfg.manager.llm_weight = 0.5
    return cfg


@pytest.fixture
def config_cloud() -> HaGoKuConfig:
    """云端模式配置"""
    cfg = HaGoKuConfig()
    cfg.manager.mode = "cloud"
    cfg.manager.rule_weight = 0.1
    cfg.manager.llm_weight = 0.9
    return cfg


def _make_llm_response(
    plan_name: str = "趋势分析",
    agents: list[str] | None = None,
    analyst_focus: list[str] | None = None,
    target: str | None = None,
    query: str = "",
    reasoning: str = "test reasoning",
) -> LLMPlanResponse:
    """创建模拟的 LLM 响应"""
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
    """LLMPlanResponse 结构化输出测试"""

    def test_valid_response(self):
        resp = _make_llm_response(query="销量趋势如何")
        assert resp.plan_name == "趋势分析"
        assert "scout" in resp.agents
        assert "reporter" in resp.agents
        assert resp.analyst_focus == ["regression"]

    def test_all_valid_focus_values(self):
        """确保所有 VALID_ANALYST_FOCUS 值都能通过 schema"""
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
        """确保所有 VALID_AGENTS 值都能通过 schema"""
        for agent in VALID_AGENTS:
            resp = LLMPlanResponse(
                plan_name="test",
                agents=[agent],
                analyst_focus=["regression"],  # analyst_focus 是必填字段
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
        """确保默认探索性焦点都是有效值"""
        for f in DEFAULT_EXPLORATORY_FOCUS:
            assert f in VALID_ANALYST_FOCUS


# ── Prompt 测试 ────────────────────────────────────────────────


class TestPrompts:
    """Prompt 模板测试"""

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
        assert "trend, regression" in result

    def test_system_prompt_lists_all_focus_types(self):
        """系统提示应列出所有可用分析类型"""
        for focus in VALID_ANALYST_FOCUS:
            assert focus in PLAN_GENERATION_SYSTEM


# ── Tier 1: 规则匹配路径 ──────────────────────────────────────


class TestTier1RulePath:
    """Tier 1: 规则匹配 + 高权重 → 直接返回规则计划"""

    def test_pure_rule_with_match(self, config_pure_rule):
        orch = Orchestrator(config=config_pure_rule)
        plan = orch._create_plan("销量趋势如何变化", "pure_rule")
        assert plan["plan_name"] == "趋势分析"
        assert plan.get("rule_match") is None  # 规则计划不带此字段
        assert "trend" in plan["analyst_focus"]

    def test_pure_rule_no_match(self, config_pure_rule):
        orch = Orchestrator(config=config_pure_rule)
        plan = orch._create_plan("这个数据有什么特点", "pure_rule")
        assert plan["plan_name"] == "通用分析"
        assert plan["rule_match"] is False

    def test_local_weak_with_match(self, config_local_weak):
        """local_weak + 规则匹配 = 不调 LLM"""
        orch = Orchestrator(config=config_local_weak)
        plan = orch._create_plan("A/B测试结果有差异吗", "local_weak")
        assert plan["plan_name"] == "差异比较"

    def test_llm_plan_enabled_false(self, config_local_strong):
        """总开关关闭 → 纯规则行为"""
        config_local_strong.manager.llm_plan_enabled = False
        orch = Orchestrator(config=config_local_strong)
        plan = orch._create_plan("销量趋势", "local_strong")
        # 规则匹配 → 直接返回
        assert plan["plan_name"] == "趋势分析"


# ── Tier 2: 混合模式 ─────────────────────────────────────────


class TestTier2HybridMode:
    """Tier 2: 规则匹配 + 混合模式 → LLM 调整规则计划"""

    @patch.object(Orchestrator, "_call_llm_for_plan")
    def test_hybrid_llm_adjusts(self, mock_llm, config_local_strong):
        """local_strong + 规则匹配 → LLM 调整"""
        mock_llm.return_value = {
            "plan_name": "销量趋势分析",
            "agents": ["scout", "cleaner", "analyst", "reporter"],
            "analyst_focus": ["trend", "regression"],
            "target": "销量",
            "query": "销量趋势",
            "reasoning": "用户关注销量变化趋势",
        }
        orch = Orchestrator(config=config_local_strong)
        plan = orch._create_plan("销量趋势", "local_strong")
        assert plan["plan_name"] == "销量趋势分析"
        assert plan["rule_match"] is True
        assert plan["llm_adjusted"] is True
        # 验证调用了 adjust 模式
        mock_llm.assert_called_once()
        call_kwargs = mock_llm.call_args
        assert call_kwargs[1]["mode"] == "adjust" if "mode" in call_kwargs[1] else call_kwargs[0][2] == "adjust"

    @patch.object(Orchestrator, "_call_llm_for_plan")
    def test_hybrid_llm_fails_fallback(self, mock_llm, config_local_strong):
        """LLM 失败 → 降级到规则计划"""
        mock_llm.return_value = None
        orch = Orchestrator(config=config_local_strong)
        plan = orch._create_plan("销量趋势", "local_strong")
        assert plan["plan_name"] == "趋势分析"
        assert plan["rule_match"] is True


# ── Tier 3: LLM 生成 ─────────────────────────────────────────


class TestTier3LLMGeneration:
    """Tier 3: 无规则匹配 + llm_weight > 0 → LLM 从零生成"""

    @patch.object(Orchestrator, "_call_llm_for_plan")
    def test_llm_generates_plan(self, mock_llm, config_cloud):
        """cloud 模式 + 无规则匹配 → LLM 生成"""
        mock_llm.return_value = {
            "plan_name": "多维关联分析",
            "agents": ["scout", "cleaner", "analyst", "reporter"],
            "analyst_focus": ["correlation", "regression"],
            "target": None,
            "query": "这个数据集有什么隐藏模式",
            "reasoning": "用户问题开放，建议探索性分析",
        }
        orch = Orchestrator(config=config_cloud)
        plan = orch._create_plan("这个数据集有什么隐藏模式", "cloud")
        assert plan["plan_name"] == "多维关联分析"
        assert plan["llm_generated"] is True
        assert plan["rule_match"] is False

    @patch.object(Orchestrator, "_call_llm_for_plan")
    def test_llm_fails_no_rule_match(self, mock_llm, config_cloud):
        """LLM 失败 + 无规则匹配 → 通用计划"""
        mock_llm.return_value = None
        orch = Orchestrator(config=config_cloud)
        plan = orch._create_plan("这个数据集有什么隐藏模式", "cloud")
        assert plan["plan_name"] == "通用分析"
        assert plan["rule_match"] is False

    @patch.object(Orchestrator, "_call_llm_for_plan")
    def test_local_weak_no_match_triggers_llm(self, mock_llm, config_local_weak):
        """local_weak + 无规则匹配 → 仍调用 LLM"""
        mock_llm.return_value = {
            "plan_name": "探索性分析",
            "agents": ["scout", "cleaner", "analyst", "reporter"],
            "analyst_focus": ["regression", "correlation"],
            "query": "数据有什么模式",
            "reasoning": "开放性问题",
        }
        orch = Orchestrator(config=config_local_weak)
        plan = orch._create_plan("数据有什么模式", "local_weak")
        mock_llm.assert_called_once()
        assert plan["llm_generated"] is True


# ── _call_llm_for_plan 核心逻辑 ────────────────────────────────


class TestCallLlmForPlan:
    """_call_llm_for_plan 核心调用逻辑测试"""

    @patch("hagokyu.llm.client.create_structured_llm_client")
    def test_successful_call(self, mock_create_client):
        """成功调用 LLM 返回计划"""
        mock_client = MagicMock()
        mock_create_client.return_value = mock_client

        mock_response = _make_llm_response(
            plan_name="趋势分析",
            analyst_focus=["trend", "regression"],
            query="销量趋势",
        )
        mock_client.chat.completions.create.return_value = mock_response

        config = HaGoKuConfig()
        config.manager.rule_weight = 0.5
        config.manager.llm_weight = 0.5
        orch = Orchestrator(config=config)
        result = orch._call_llm_for_plan("销量趋势", mode="generate")

        assert result is not None
        assert result["plan_name"] == "趋势分析"
        assert "trend" in result["analyst_focus"]
        assert "scout" in result["agents"]
        assert "reporter" in result["agents"]

    @patch("hagokyu.llm.client.create_structured_llm_client")
    def test_invalid_focus_filtered(self, mock_create_client):
        """LLM 返回无效 analyst_focus → 过滤为默认值"""
        mock_client = MagicMock()
        mock_create_client.return_value = mock_client

        # 模拟 LLM 返回无效值
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
        result = orch._call_llm_for_plan("test", mode="generate")

        assert result is not None
        # 无效值被过滤，降级到默认探索性焦点
        assert result["analyst_focus"] == DEFAULT_EXPLORATORY_FOCUS

    @patch("hagokyu.llm.client.create_structured_llm_client")
    def test_missing_scout_reporter_added(self, mock_create_client):
        """LLM 返回的 agents 缺少 scout/reporter → 自动补充"""
        mock_client = MagicMock()
        mock_create_client.return_value = mock_client

        mock_response = LLMPlanResponse(
            plan_name="test",
            agents=["analyst"],  # 缺少 scout 和 reporter
            analyst_focus=["regression"],
            query="test",
            reasoning="test",
        )
        mock_client.chat.completions.create.return_value = mock_response

        config = HaGoKuConfig()
        orch = Orchestrator(config=config)
        result = orch._call_llm_for_plan("test", mode="generate")

        assert result is not None
        assert "scout" in result["agents"]
        assert "reporter" in result["agents"]
        assert "analyst" in result["agents"]

    @patch("hagokyu.llm.client.create_structured_llm_client")
    def test_llm_exception_returns_none(self, mock_create_client):
        """LLM 异常 → 返回 None"""
        mock_create_client.side_effect = ConnectionError("llama-server down")

        config = HaGoKuConfig()
        orch = Orchestrator(config=config)
        result = orch._call_llm_for_plan("test", mode="generate")

        assert result is None

    @patch("hagokyu.llm.client.create_structured_llm_client")
    def test_llm_timeout_returns_none(self, mock_create_client):
        """LLM 超时 → 返回 None"""
        mock_client = MagicMock()
        mock_create_client.return_value = mock_client
        mock_client.chat.completions.create.side_effect = TimeoutError("timeout")

        config = HaGoKuConfig()
        orch = Orchestrator(config=config)
        result = orch._call_llm_for_plan("test", mode="generate")

        assert result is None

    @patch("hagokyu.llm.client.create_structured_llm_client")
    def test_lazy_client_initialization(self, mock_create_client):
        """LLM 客户端懒初始化：第一次调用才创建"""
        mock_client = MagicMock()
        mock_create_client.return_value = mock_client

        mock_response = _make_llm_response(query="test")
        mock_client.chat.completions.create.return_value = mock_response

        config = HaGoKuConfig()
        orch = Orchestrator(config=config)

        # 初始时客户端为 None
        assert orch._llm_client is None

        # 调用后客户端被初始化
        orch._call_llm_for_plan("test", mode="generate")
        assert orch._llm_client is not None
        mock_create_client.assert_called_once()

        # 第二次调用不重新创建
        orch._call_llm_for_plan("test2", mode="generate")
        mock_create_client.assert_called_once()  # 仍然只调用了一次


# ── _generic_plan 测试 ────────────────────────────────────────


class TestGenericPlan:
    """通用计划测试"""

    def test_generic_plan_structure(self):
        config = HaGoKuConfig()
        config.manager.rule_weight = 1.0
        config.manager.llm_weight = 0.0
        orch = Orchestrator(config=config)
        plan = orch._generic_plan("test query")
        assert plan["plan_name"] == "通用分析"
        assert "scout" in plan["agents"]
        assert "cleaner" in plan["agents"]
        assert "analyst" in plan["agents"]
        assert "reporter" in plan["agents"]
        assert plan["rule_match"] is False


# ── 事件发射测试 ──────────────────────────────────────────────


class TestEventEmission:
    """确保 LLM 计划生成会发射正确的事件"""

    @patch.object(Orchestrator, "_call_llm_for_plan")
    def test_plan_created_event(self, mock_llm, config_cloud):
        """LLM 生成计划 → 发射 PLAN_CREATED 事件"""
        mock_llm.return_value = {
            "plan_name": "探索性分析",
            "agents": ["scout", "cleaner", "analyst", "reporter"],
            "analyst_focus": ["correlation"],
            "query": "数据有什么模式",
            "reasoning": "开放性问题",
        }
        orch = Orchestrator(config=config_cloud)
        orch._create_plan("数据有什么模式", "cloud")

        # 检查是否有 PLAN_CREATED 事件
        plan_events = [
            e for e in orch.event_bus.events
            if e.event_type.value == "plan_created"
        ]
        assert len(plan_events) == 1
        assert plan_events[0].data["source"] == "llm"

    @patch.object(Orchestrator, "_call_llm_for_plan")
    def test_plan_adjusted_event(self, mock_llm, config_local_strong):
        """LLM 调整计划 → 发射 PLAN_ADJUSTED 事件"""
        mock_llm.return_value = {
            "plan_name": "调整后趋势分析",
            "agents": ["scout", "cleaner", "analyst", "reporter"],
            "analyst_focus": ["trend"],
            "query": "销量趋势",
            "reasoning": "微调",
        }
        orch = Orchestrator(config=config_local_strong)
        orch._create_plan("销量趋势", "local_strong")

        adjusted_events = [
            e for e in orch.event_bus.events
            if e.event_type.value == "plan_adjusted"
        ]
        assert len(adjusted_events) == 1

    def test_llm_failure_emits_thinking(self):
        """LLM 失败 → 发射 AGENT_THINKING 事件记录失败信息"""
        with patch("hagokyu.llm.client.create_structured_llm_client") as mock_create:
            mock_create.side_effect = ConnectionError("server down")
            config = HaGoKuConfig()
            config.manager.rule_weight = 0.1
            config.manager.llm_weight = 0.9
            orch = Orchestrator(config=config)
            plan = orch._create_plan("test query", "cloud")

            assert plan["plan_name"] == "通用分析"  # 降级
            thinking_events = [
                e for e in orch.event_bus.events
                if e.event_type.value == "agent_thinking"
            ]
            assert any("LLM" in e.data.get("thought", "") for e in thinking_events)
