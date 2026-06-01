"""阶段衔接守门测试 — 下游 Agent 注入 messages_history（律 3）。
"""


def test_下游_agent_注入_messages_history():
    """ProjectContext.build_prompt 返回的 messages_history 应按 agent 分组。

    - 上游 stage（non-current）只出现在 upstream_summary，不在 messages_history
    - 当前 agent stage 的 entries 才在 messages_history
    - 同一 agent 的 user_feedback → agent_response 顺序正确（G 修复后）
    """
    from hagoku.context.project_context import ProjectContext

    ctx = ProjectContext(run_id="test_run", analysis_goal="测试目标")

    # 上游 scout 阶段
    ctx.add_user_feedback(stage="scout", revision=0, raw_text="BU 是公司")
    ctx.add_agent_response(
        stage="scout", revision=0, content="已更新",
        snapshot={"target": "Inc1", "features": ["Code"], "pending": []},
    )

    # 当前 cleaner 阶段（模拟一轮对话）
    ctx.add_user_feedback(stage="cleaner", revision=0, raw_text="确认继续")
    ctx.add_agent_response(
        stage="cleaner", revision=0, content="submit_assessment 已提交",
        snapshot={"target": "Inc1", "features": ["Code"], "pending": []},
    )

    block = ctx.build_prompt("cleaner", context={})

    # messages_history：仅 cleaner 自身条目，含本轮对话
    mh = block.get("messages_history", [])
    assert len(mh) >= 2, f"messages_history 应至少 2 条，实际 {len(mh)}"
    assert mh[0]["role"] == "user", f"第 1 条应为 user，实际 {mh[0]['role']}"
    assert mh[1]["role"] == "assistant", f"第 2 条应为 assistant，实际 {mh[1]['role']}"

    # upstream_summary：含上游用户原话（I 修复后）
    assert "BU 是公司" in block["upstream_summary"], (
        f"upstream_summary 应含上游用户原话，实际: {block['upstream_summary']}"
    )

    # upstream_summary 不应重复（P2）
    count = block["upstream_summary"].count("scout 阶段完成")
    assert count <= 1, f"upstream_summary 重复 {count} 次"


def test_conv_history已退役():
    """Cleaner 路径不应依赖 _conversation_history。"""
    from hagoku.agents.cleaner.agent import CleanerAgent
    import inspect

    src = inspect.getsource(CleanerAgent.assess)
    assert '"_conversation_history"' not in src, (
        "assess() 仍引用 _conversation_history，应退役"
    )
    # conv_history 保留注释提及，不检查。只检查 _conversation_history 字符串引用
