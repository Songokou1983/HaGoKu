"""Analyst 对话式分析守门测试 — submit_analysis 唯一退出 + 30 轮上限。
"""

import pytest
import pandas as pd


class _FakeEB:
    def emit(self, *a, **kw):
        pass


def test_analyst_submit_analysis_唯一退出():
    """只有 submit_analysis 退出，代码不响应关键词。"""
    import hagoku.llm.client as llm_mod
    from hagoku.config import LLMConfig

    _orig = llm_mod.create_raw_client
    round_count = [0]

    class FakeMsg:
        def __init__(self, content, tool_calls=None):
            self.content = content
            self.tool_calls = tool_calls or []

    class FakeResp:
        def __init__(self, msg):
            self.choices = [type("c", (), {"message": msg})()]

    class FakeClient:
        class chat:
            class completions:
                @staticmethod
                def create(*, model, messages, **kw):
                    round_count[0] += 1
                    if round_count[0] == 1:
                        return FakeResp(FakeMsg("可以了"))
                    tc = type("tc", (), {
                        "id": "1",
                        "function": type("fn", (), {
                            "name": "submit_analysis",
                            "arguments": '{"findings":[{"title":"t","detail":"d","evidence_columns":["X"],"confidence":"high"}],"method_used":[],"summary":"ok"}'
                        })()
                    })()
                    return FakeResp(FakeMsg("", [tc]))

    llm_mod.create_raw_client = lambda c: FakeClient()

    try:
        from hagoku.agents.analyst.agent import AnalystAgent
        agent = AnalystAgent(LLMConfig(model="t", model_quick="t"), event_bus=_FakeEB())
        replies = ["可以了"]
        def fake_pause(stage, data):
            return replies.pop(0) if replies else None
        agent._pause_and_wait = fake_pause

        findings = agent.run(
            pd.DataFrame({"X": [1]}),
            {"column_semantics": [], "query": "test"},
        )
        assert round_count[0] >= 2, f"至少 2 轮，实际 {round_count[0]}"
        assert len(findings.get("findings", [])) > 0
    finally:
        llm_mod.create_raw_client = _orig


def test_analyst_30轮上限():
    """30 轮不提交 submit_analysis 应 raise RuntimeError。"""
    import hagoku.llm.client as llm_mod
    from hagoku.config import LLMConfig

    _orig = llm_mod.create_raw_client

    class FakeResp:
        def __init__(self):
            m = type("m", (), {"content": "思考中...", "tool_calls": None})()
            self.choices = [type("c", (), {"message": m})()]

    class FakeClient:
        class chat:
            class completions:
                @staticmethod
                def create(*, model, messages, **kw):
                    return FakeResp()

    llm_mod.create_raw_client = lambda c: FakeClient()

    try:
        from hagoku.agents.analyst.agent import AnalystAgent
        agent = AnalystAgent(LLMConfig(model="t", model_quick="t"), event_bus=_FakeEB())
        agent._pause_and_wait = lambda stage, data: "继续"

        with pytest.raises(RuntimeError, match="30 轮"):
            agent.run(pd.DataFrame({"X": [1]}), {"column_semantics": [], "query": "test"})
    finally:
        llm_mod.create_raw_client = _orig
