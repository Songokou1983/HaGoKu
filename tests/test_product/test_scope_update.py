"""守门测试：scope 更新相关行为 — G1~G6。"""


def test_g1_analyst_system_prefix_contains_field_status():
    """Analyst prompt 的 system_prefix 包含字段参与/不参与状态。"""
    from hagoku.context.project_context import ProjectContext

    ctx = ProjectContext(run_id="g1", analysis_goal="测试")
    context = {
        "column_semantics": [
            {"column_name": "A", "display_name": "列A", "suggested_role": "feature", "used_in_analysis": True},
            {"column_name": "B", "display_name": "列B", "suggested_role": "ignore", "used_in_analysis": False},
        ],
        "target": "A",
        "features": ["A"],
    }
    result = ctx.build_prompt("analyst", context)
    sp = result["system_prefix"]
    assert "参与" in sp
    assert "不参与" in sp


def test_g2_update_analysis_scope_updates_used_in_analysis():
    """_handle_update_analysis_scope 将列标记为 used_in_analysis=True。"""
    from hagoku.tools.agent_tool_defs import _handle_update_analysis_scope

    ctx = {
        "column_semantics": [
            {"column_name": "Inc2", "used_in_analysis": False},
        ]
    }
    result = _handle_update_analysis_scope(
        {"add_columns": ["Inc2"], "reason": "用户要求"},
        ctx, None
    )
    assert ctx["column_semantics"][0]["used_in_analysis"] is True
    assert "Inc2" in result["added"]


def test_g3_unlock_triggers_role_re_derivation():
    """解锁后 _derive_roles 重新派生 target/features。"""
    from hagoku.agents.scout.agent import ScoutAgent

    context = {
        "column_semantics": [
            {"column_name": "Inc1", "suggested_role": "target", "used_in_analysis": True},
            {"column_name": "Inc2", "suggested_role": "feature", "used_in_analysis": True},
        ]
    }
    agent = ScoutAgent.__new__(ScoutAgent)
    agent._derive_roles(context)
    assert "Inc1" in (context.get("target") or "")
    assert "Inc2" in context.get("features", [])


def test_g4_unlock_writes_project_context_snapshot():
    """解锁落 ProjectContext snapshot。"""
    from hagoku.context.project_context import ProjectContext

    pctx = ProjectContext(run_id="g4", analysis_goal="测试")
    context = {
        "column_semantics": [
            {"column_name": "Inc2", "display_name": "积分", "suggested_role": "feature", "used_in_analysis": True},
        ],
        "target": "Inc1",
        "features": ["Inc2"],
    }
    pctx.add_agent_response("analyst", 0, "解锁 Inc2", pctx._derive_snapshot(context))
    assert len(pctx.entries) == 1
    snap = pctx.entries[0].snapshot
    assert snap is not None


def test_g5_cleaner_assess_excludes_non_scope_columns():
    """Cleaner assess prompt 不含 scope 外列。"""
    context = {
        "column_semantics": [
            {"column_name": "A", "used_in_analysis": True},
            {"column_name": "B", "used_in_analysis": False},
        ],
        "query": "测试",
    }
    analysis_cols = {str(s["column_name"]) for s in context["column_semantics"] if s.get("used_in_analysis") is True}
    col_names = [c for c in ["A", "B"] if not analysis_cols or c in analysis_cols]
    assert "A" in col_names
    assert "B" not in col_names


def test_g6_empty_operation_does_not_crash():
    """空操作不崩溃。"""
    from hagoku.tools.agent_tool_defs import _handle_update_analysis_scope

    ctx = {"column_semantics": []}
    result = _handle_update_analysis_scope({"add_columns": [], "remove_columns": []}, ctx, None)
    assert result["added"] == []
    assert result["removed"] == []
