"""LLM 计划生成的结构化输出 Schema

定义 LLM 返回分析计划的数据模型，以及合法的分析类型和 Agent 列表常量。
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

# Analyst 支持的分析类型（与 analyst.py 中的 focus 映射一致）
VALID_ANALYST_FOCUS: list[str] = [
    "regression",
    "causal",
    "hypothesis_test",
    "effect_size",
    "trend",
    "time_series",
    "correlation",
]

# 合法的 Agent 列表
VALID_AGENTS: list[str] = ["scout", "cleaner", "analyst", "reporter"]

# 默认探索性分析焦点（当 LLM 返回无效值时的降级选择）
DEFAULT_EXPLORATORY_FOCUS: list[str] = ["regression", "hypothesis_test", "correlation"]


class LLMPlanResponse(BaseModel):
    """LLM 生成的分析计划结构化输出"""

    plan_name: str = Field(
        description="Human-readable plan name in Chinese, e.g. '趋势分析' or '综合探索性分析'",
    )
    agents: list[Literal["scout", "cleaner", "analyst", "reporter"]] = Field(
        description=(
            "Which agents to invoke. Always include scout and reporter. "
            "Include cleaner and analyst for statistical analysis."
        ),
    )
    analyst_focus: list[str] = Field(
        description=(
            "Analysis focus areas for the Analyst agent. "
            "Valid values: regression, causal, hypothesis_test, effect_size, "
            "trend, time_series, correlation. Choose 1-3 most relevant."
        ),
    )
    target: str | None = Field(
        default=None,
        description="Name of the target/dependent variable if identifiable from the query, else null",
    )
    query: str = Field(
        description="The user's original query, echoed back",
    )
    reasoning: str = Field(
        description="Brief reasoning for why this plan was chosen (1-2 sentences)",
    )
