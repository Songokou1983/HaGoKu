"""TDD: 验证 Scout 代码层不覆盖 LLM 输出的 used_in_analysis 决策。
历史：本文件原含 test_scout_prompt_contains_ignore_role_instruction（关键词匹配 prompt 内容），
已于 Phase A 收尾删除——见 CLAUDE.md §铁律 10 刹车 A（禁止对提示词内容做关键词匹配测试）。
"""
from unittest.mock import MagicMock, patch

from hagoku.config import HaGoKuConfig
from hagoku.agents.scout.agent import ScoutAgent


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

