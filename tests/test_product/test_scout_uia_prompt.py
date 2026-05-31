"""TDD: 验证 Scout 发给 LLM 的 prompt 包含 used_in_analysis / ignore 的完整指令

RED 阶段：测试应该失败 — 证明当前 prompt 缺少关键指令导致「全部勾选」
"""
import pytest
from unittest.mock import MagicMock, patch

from hagoku.config import HaGoKuConfig
from hagoku.agents.scout.agent import ScoutAgent


def test_scout_prompt_contains_ignore_role_instruction():
    """TDD-RED: Scout 的 system prompt 必须包含明确指令——
    与目标无关的字段应设为 ignore（而非 feature）。

    这是「字段全选」问题的根因修复——如果 LLM 把无关字段判为 feature,
    下游 used_in_analysis 全为 true, 用户看到全部勾选。

    若此测试失败: prompt 中缺少 ignore 指令 → LLM 不会主动用 ignore → 全选。
    """
    import pandas as pd

    cfg = HaGoKuConfig()
    agent = ScoutAgent(cfg.llm, event_bus=MagicMock())

    df = pd.DataFrame({
        "StoreID": [1, 2],
        "Revenue": [100.0, 200.0],
        "Quantity": [5, 10],
    })

    # 捕获 system prompt
    captured_system: list[str] = []

    def mock_create_raw_client(llm_config):
        client = MagicMock()
        def _create(*, model, messages, tools, temperature, max_tokens, tool_choice=None):
            captured_system.append(messages[0]["content"])
            resp = MagicMock()
            resp.choices = [MagicMock()]
            resp.choices[0].message = MagicMock()
            resp.choices[0].message.tool_calls = []
            resp.choices[0].message.content = (
                '{"columns":['
                '{"name":"StoreID","inferred_type":"id","suggested_role":"identifier","display_name":"ID","description":"","confidence":0.9,"needs_user_input":false},'
                '{"name":"Revenue","inferred_type":"numeric","suggested_role":"target","display_name":"收入","description":"","confidence":0.9,"needs_user_input":false},'
                '{"name":"Quantity","inferred_type":"numeric","suggested_role":"feature","display_name":"数量","description":"","confidence":0.8,"needs_user_input":false}'
                ']}'
            )
            return resp
        client.chat.completions.create = _create
        return client

    with patch("hagoku.llm.client.create_raw_client", mock_create_raw_client):
        agent._infer_all_semantics(df, query="分析收入的变化趋势")

    assert len(captured_system) >= 1, "应恰好调用 LLM 一次"
    prompt = captured_system[0]

    # DEBUG: 打印实际 prompt 内容
    print(f"\n=== 实际 system prompt ({len(prompt)} chars) ===")
    print(prompt)
    print("=== end prompt ===\n")

    # ── 断言清单 ──

    # 1. 分析目标（已移除——由 ProjectContext.system_prefix 注入）
    # （不再在 Agent 自身 prompt 中检验 analysis_goal）

    # 2. 必须包含「ignore」指令（解决「全部勾选」的核心）
    assert "ignore" in prompt.lower(), (
        "❌ Scout prompt 中未提及 ignore 角色。"
        "LLM 会把无关字段全判为 feature → used_in_analysis=true。\n"
        f"prompt 尾段:\n{prompt[-800:]}"
    )

    # 3. 无关→ignore 的语义必须传达
    has_irrelevant_instruction = (
        "无关" in prompt or "不参与" in prompt or "排除" in prompt
    )
    assert has_irrelevant_instruction, (
        "❌ prompt 未说明「与目标无关的字段应该如何处理」。\n"
        f"prompt:\n{prompt[:1500]}"
    )

    # 4. used_in_analysis 在 tool schema 中，不在 prompt 里
    # prompt 只给流程和词汇，不说结论。used_in_analysis 是 schema 字段，LLM 会自己判断。
    # 如果 prompt 里出现了 used_in_analysis 的映射指令（如 identifier→false），那才是违规。


def test_scout_llm_output_used_in_analysis_preserved():
    """TDD: 验证 LLM 输出的 used_in_analysis=false 不被代码覆盖。

    若此测试失败: prompt 正确但代码层某处覆盖了 LLM 的 false → true。
    """
    import pandas as pd

    cfg = HaGoKuConfig()
    agent = ScoutAgent(cfg.llm, event_bus=MagicMock())

    df = pd.DataFrame({"A": [1, 2], "B": [3.0, 4.0]})

    def mock_create_raw_client(llm_config):
        client = MagicMock()
        def _create(*, model, messages, tools, temperature, max_tokens, tool_choice=None):
            resp = MagicMock()
            resp.choices = [MagicMock()]
            resp.choices[0].message = MagicMock()
            resp.choices[0].message.tool_calls = []
            resp.choices[0].message.content = (
                '{"columns":['
                '{"name":"A","inferred_type":"id","suggested_role":"identifier",'
                '"display_name":"ID","description":"","confidence":0.9,"needs_user_input":false,"used_in_analysis":false},'
                '{"name":"B","inferred_type":"numeric","suggested_role":"target",'
                '"display_name":"值","description":"","confidence":0.9,"needs_user_input":false,"used_in_analysis":true}'
                ']}'
            )
            return resp
        client.chat.completions.create = _create
        return client

    with patch("hagoku.llm.client.create_raw_client", mock_create_raw_client):
        semantics = agent._infer_all_semantics(df, query="分析 B")

    sem_a = next(s for s in semantics if s["column_name"] == "A")
    sem_b = next(s for s in semantics if s["column_name"] == "B")

    assert sem_a["used_in_analysis"] is False, (
        f"❌ LLM 输出 used_in_analysis=false，但被代码覆盖。A={sem_a}"
    )
    assert sem_b["used_in_analysis"] is True, (
        f"❌ LLM 输出 used_in_analysis=true，但被代码覆盖。B={sem_b}"
    )

