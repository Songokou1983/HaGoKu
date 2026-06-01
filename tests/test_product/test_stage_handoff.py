"""阶段衔接守门测试 — 下游 Agent 注入 messages_history（律 3）。
"""


def test_build_prompt_messages_history_分组():
    """ProjectContext.build_prompt 的 messages_history 按 agent 分组。

    - 当前 agent 自身条目进 messages_history
    - 上游条目进 upstream_summary
    - 顺序 user → assistant（G 修复后）
    """
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


def test_下游_agent_实际注入_messages_history():
    """守门：Agent 真实发给 LLM 的 messages 包含 messages_history 条目。

    monkeypatch create_raw_client 截获 messages，
    验证 Cleaner 的 assess() 已 extend messages_history。
    """
    from hagoku.context.project_context import ProjectContext
    from hagoku.agents.cleaner.agent import CleanerAgent

    ctx_proj = ProjectContext(run_id="test_gate", analysis_goal="Gate")
    ctx_proj.add_user_feedback(stage="cleaner", revision=0, raw_text="锚点_确认_A")
    ctx_proj.add_agent_response(
        stage="cleaner", revision=0, content="ok",
        snapshot={"target": "X", "features": [], "pending": []},
    )
    ctx_proj.add_user_feedback(stage="cleaner", revision=1, raw_text="锚点_确认_B")
    ctx_proj.add_agent_response(
        stage="cleaner", revision=1, content="ok",
        snapshot={"target": "X", "features": [], "pending": []},
    )

    import hagoku.llm.client as llm_mod
    captured: list = []
    _orig = llm_mod.create_raw_client

    class FakeClient:
        class chat:
            class completions:
                @staticmethod
                def create(*, model, messages, **kwargs):
                    captured.append(messages)
                    raise RuntimeError("stop")

    llm_mod.create_raw_client = lambda config: FakeClient()
    try:
        from hagoku.config import LLMConfig
        agent = CleanerAgent(LLMConfig(model="t", model_quick="t"), event_bus=None)
        context = {
            "_project_context": ctx_proj,
            "column_semantics": [
                {"column_name": "X", "used_in_analysis": True, "display_name": "X",
                 "role": "target", "needs_user_input": False},
            ],
        }
        agent.assess(df=__import__("pandas").DataFrame({"X": [1]}), context=context, cleaning_rules="skip all cols")
    except RuntimeError:
        pass
    finally:
        llm_mod.create_raw_client = _orig

    assert captured, "未调 LLM"
    flat = " | ".join(
        m.get("role", "?") + ":" + str(m.get("content", ""))[:60]
        for m in captured[0]
    )
    assert "锚点_确认_A" in flat, f"缺锚点 A: {flat[:300]}"
    assert "锚点_确认_B" in flat, f"缺锚点 B: {flat[:300]}"
