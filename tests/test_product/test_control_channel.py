# tests/test_product/test_control_channel.py
"""律 8（控制通道）契约测试 — CH-6。

每个 Agent 的工具集中必须至少有一个控制类工具，
允许 LLM 主动表达「本阶段完成 / 留在当前阶段 / 跳转」。
"""
from __future__ import annotations

import pytest
from hagoku.tools.registry import agent_tools

# 控制工具标识模式：名称含 route_/done_with_/submit_/request_ 等流程控制语义
CONTROL_TOOL_PATTERNS = ("route_", "done_with_", "request_", "submit_")
AGENTS = ["scout", "cleaner", "analyst", "reporter"]


def _control_tools_for(agent: str) -> list[str]:
    """返回该 agent 工具集中名称匹配控制模式的工具名列表。"""
    tools = agent_tools.to_openai(agent)
    names = [t["function"]["name"] for t in tools]
    return [n for n in names if any(n.startswith(p) for p in CONTROL_TOOL_PATTERNS)]


class TestControlChannel:
    @pytest.mark.parametrize("agent", AGENTS)
    def test_agent_has_at_least_one_control_tool(self, agent):
        """律 8：该 agent 的工具集中必须存在至少一个控制类工具。"""
        ctl = _control_tools_for(agent)
        assert len(ctl) > 0, (
            f"律 8 残缺：Agent '{agent}' 无控制类工具。\n"
            f"现有工具：{', '.join(t['function']['name'] for t in agent_tools.to_openai(agent))}\n"
            f"控制工具应允许 LLM 表达「本阶段完成 / 跳转 / 请求更多输入」。\n"
            f"预期匹配模式：{CONTROL_TOOL_PATTERNS}"
        )

    def test_route_to_accepts_stage_parameter(self):
        """route_to 工具必须包含 stage 参数，允许 LLM 指定目标阶段。"""
        tools = {t["function"]["name"]: t["function"] for t in agent_tools.to_openai("scout")}
        rt = tools.get("route_to")
        assert rt is not None, "route_to 工具不存在（控制通道断裂）"
        params = rt.get("parameters", {}).get("properties", {})
        assert "stage" in params, (
            f"route_to 缺少 'stage' 参数，LLM 无法指定目标阶段。\n"
            f"现有参数：{list(params.keys())}"
        )
        # stage 的 enum 应覆盖全部 4 阶段
        stage_enum = params["stage"].get("enum", [])
        for s in AGENTS:
            assert s in stage_enum, (
                f"route_to stage.enum 缺 '{s}'，LLM 无法跳转到该阶段"
            )

    def test_route_to_available_to_all_agents(self):
        """route_to 必须对所有 4 个 Agent 可用。"""
        for agent in AGENTS:
            tools = {t["function"]["name"] for t in agent_tools.to_openai(agent)}
            assert "route_to" in tools, (
                f"律 8 残缺：'{agent}' 的工具集无 route_to。\n"
                f"当前工具：{sorted(tools)}"
            )
