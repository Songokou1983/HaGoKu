"""阶段衔接守门测试 — 下游 Agent 注入 messages_history（律 3）。
"""

import pytest
import pandas as pd


def test_build_prompt_messages_history_分组():
    """ProjectContext.build_prompt 的 messages_history 按 agent 分组。"""
    from hagoku.context.project_context import ProjectContext

    ctx = ProjectContext(run_id="test_run", analysis_goal="测试目标")
    ctx.add_user_feedback(stage="cleaner", revision=0, raw_text="确认继续")
    ctx.add_agent_response(
        stage="cleaner", revision=0, content="评估完成",
        snapshot={"target": "X", "features": [], "pending": []},
    )

    block = ctx.build_prompt("cleaner", context={})
    mh = block.get("messages_history", [])
    assert len(mh) >= 2, f"messages_history 应至少 2 条，实际 {len(mh)}"
    assert mh[0]["role"] == "user", f"第 1 条应为 user"
    assert mh[1]["role"] == "assistant", f"第 2 条应为 assistant"


def test_conv_history已退役():
    """Cleaner 路径不应依赖 _conversation_history。"""
    from hagoku.agents.cleaner.agent import CleanerAgent
    import inspect

    src = inspect.getsource(CleanerAgent.assess)
    assert '"_conversation_history"' not in src, (
        "assess() 仍引用 _conversation_history，应退役"
    )


class _FakeEventBus:
    def emit(self, *args, **kwargs):
        pass


class _FakeClient:
    captured_ref = None  # set by test
    class chat:
        class completions:
            @staticmethod
            def create(*, model, messages, **kwargs):
                if _FakeClient.captured_ref is not None:
                    _FakeClient.captured_ref.append(messages)
                raise RuntimeError("stop")


@pytest.mark.parametrize("agent_key", ["cleaner", "analyst", "reporter"])
def test_下游_agent_实际注入_messages_history(agent_key):
    """守门：3 个 Agent LLM messages 必须包含 messages_history 锚点字符串。"""
    from hagoku.context.project_context import ProjectContext
    from hagoku.config import LLMConfig

    stage = agent_key
    anchor_a = f"锚点_{agent_key}_A"
    anchor_b = f"锚点_{agent_key}_B"

    ctx_proj = ProjectContext(run_id=f"gate_{agent_key}", analysis_goal="Gate")
    ctx_proj.add_user_feedback(stage=stage, revision=0, raw_text=anchor_a)
    ctx_proj.add_agent_response(
        stage=stage, revision=0, content="ok",
        snapshot={"target": "X", "features": [], "pending": []},
    )
    ctx_proj.add_user_feedback(stage=stage, revision=1, raw_text=anchor_b)
    ctx_proj.add_agent_response(
        stage=stage, revision=1, content="ok",
        snapshot={"target": "X", "features": [], "pending": []},
    )

    captured: list = []

    if agent_key == "reporter":
        from hagoku.agents.reporter.agent import ReporterAgent

        class _ReporterFakeClient:
            class chat:
                class completions:
                    @staticmethod
                    def create(*, model, messages, **kwargs):
                        captured.append(messages)
                        raise RuntimeError("stop")

        agent = ReporterAgent.__new__(ReporterAgent)
        agent.llm_config = LLMConfig(model="t")
        agent.event_bus = _FakeEventBus()
        agent._llm_client = _ReporterFakeClient()
        agent.role = "reporter"

        block = ctx_proj.build_prompt("reporter", context={})
        system_prompt = "报告员"
        system_prompt += "\n\n" + block["system_prefix"] + "\n\n" + block["upstream_summary"]
        try:
            agent._call_llm(
                system=system_prompt,
                user="测试",
                messages_history=block.get("messages_history", []),
            )
        except RuntimeError:
            pass

    else:
        import hagoku.llm.client as llm_mod
        _orig = llm_mod.create_raw_client
        _FakeClient.captured_ref = captured
        llm_mod.create_raw_client = lambda config: _FakeClient()

        try:
            if agent_key == "cleaner":
                from hagoku.agents.cleaner.agent import CleanerAgent
                agent = CleanerAgent(LLMConfig(model="t"), event_bus=None)
                ctx_dict = {
                    "_project_context": ctx_proj,
                    "column_semantics": [
                        {"column_name": "X", "used_in_analysis": True, "display_name": "X",
                         "role": "target", "needs_user_input": False},
                    ],
                }
                agent.assess(df=pd.DataFrame({"X": [1]}), context=ctx_dict, cleaning_rules="skip")
            else:
                from hagoku.agents.analyst.agent import AnalystAgent
                agent = AnalystAgent(LLMConfig(model="t"), event_bus=_FakeEventBus())
                agent.prompt = "test"
                # Phase B: 对话历史写进 ProjectContext，run_step 只传 context + df + user_input
                ctx_proj.add_user_feedback("analyst", 0, anchor_a)
                ctx_proj.add_agent_response("analyst", 0, "ok")
                ctx_proj.add_user_feedback("analyst", 1, anchor_b)
                context_dict = {
                    "_project_context": ctx_proj,
                    "analysis_goal": "Gate",
                    "query": "Gate",
                    "column_semantics": [
                        {"column_name": "X", "used_in_analysis": True, "display_name": "X",
                         "role": "target", "needs_user_input": False},
                    ],
                }
                agent.run_step(
                    context=context_dict,
                    df=pd.DataFrame({"X": [1]}),
                    user_input=anchor_b,
                )
        except RuntimeError:
            pass
        finally:
            llm_mod.create_raw_client = _orig

    assert captured, f"[{agent_key}] 未调 LLM"
    flat = " | ".join(
        m.get("role", "?") + ":" + str(m.get("content", ""))[:60]
        for m in captured[0]
    )
    assert anchor_a in flat, f"[{agent_key}] 缺锚点 A: {flat[:300]}"
    assert anchor_b in flat, f"[{agent_key}] 缺锚点 B: {flat[:300]}"


def test_upstream_summary_不重复():
    """任务 J：upstream_summary 中每 stage 只出现一次。"""
    from hagoku.context.project_context import ProjectContext
    ctx = ProjectContext(run_id="dedup", analysis_goal="test")
    for i in range(5):
        ctx.add_agent_response(stage="scout", revision=i, content="ok",
            snapshot={"target": "X", "features": [], "pending": []})
    block = ctx.build_prompt("cleaner", context={})
    assert block["upstream_summary"].count("scout 阶段完成") <= 1


def test_cleaner看到scout用户原话():
    """任务 I：Cleaner 的 upstream_summary 含 Scout 用户原话。"""
    from hagoku.context.project_context import ProjectContext
    ctx = ProjectContext(run_id="p3", analysis_goal="test")
    ctx.add_user_feedback(stage="scout", revision=0, raw_text="只用店铺周期收入")
    ctx.add_agent_response(stage="scout", revision=0, content="ok",
        snapshot={"target": "X", "features": [], "pending": []})
    block = ctx.build_prompt("cleaner", context={})
    assert "只用店铺周期收入" in block["upstream_summary"]
