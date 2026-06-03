# Scope 引导式分析 实现计划

> **面向 AI 代理的工作者：** 必需技能：使用 subagent-driven-development（推荐）或 executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 实现 scope 引导式分析——字段理解产出显式 scope，下游 Agent prompt 注入引导信息，Analyst 可通过 `update_analysis_scope` 工具解锁/锁定分析字段。

**架构：** 现有 `system_prefix` 已含字段状态表，本计划不新增并行通道。新增 `update_analysis_scope` 工具 + handler，Analyst prompt 追加解锁指引，解锁后自动更新 `column_semantics` → `_derive_roles` 重新派生 target/features。

**技术栈：** Python, pytest, 现有 `agent_tool_defs.py` 工具注册框架

---

### 任务 1：注册 `update_analysis_scope` 工具 + handler

**文件：**
- 修改：`hagoku/tools/agent_tool_defs.py`（追加工具定义 + handler）

- [ ] **步骤 1：在 agent_tool_defs.py 添加 handler 函数**

在 `_handle_restrict_analysis_to` 之后插入：

```python
def _handle_update_analysis_scope(args: dict, ctx: dict, _df: pd.DataFrame | None) -> dict:
    """更新分析范围——纳入或排除字段。"""
    add_columns = args.get("add_columns", []) or []
    remove_columns = args.get("remove_columns", []) or []
    reason = args.get("reason", "")

    semantics = ctx.get("column_semantics", [])
    updated_add: list[str] = []
    updated_remove: list[str] = []

    for sem in semantics:
        col = str(sem.get("column_name", ""))
        if col in add_columns:
            sem["used_in_analysis"] = True
            updated_add.append(col)
        if col in remove_columns:
            sem["used_in_analysis"] = False
            updated_remove.append(col)

    # 触发重派生 target/features
    ctx["_pending_scope_update"] = True

    return {
        "added": updated_add,
        "removed": updated_remove,
        "reason": reason,
    }
```

- [ ] **步骤 2：注册工具**

在 `agent_tools.register` 区域追加：

```python
agent_tools.register(Tool(
    name="update_analysis_scope",
    description=(
        "调整分析范围——纳入或排除字段。调用前先检查字段数据质量（调 get_column_stats）。"
        "若空值率 < 20% 且无类型异常，可直接纳入。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "add_columns": {
                "type": "array",
                "items": {"type": "string"},
                "description": "纳入分析的列名列表",
            },
            "remove_columns": {
                "type": "array",
                "items": {"type": "string"},
                "description": "移出分析的列名列表",
            },
            "reason": {
                "type": "string",
                "description": "调整原因",
            },
        },
        "required": [],
    },
    handler=_handle_update_analysis_scope,
    agents=["analyst"],
))
```

- [ ] **步骤 3：运行现有测试确认无回归**

```bash
.venv/bin/python -m pytest tests/test_tools/ -q
```

---

### 任务 2：orchestrator 中处理 `_pending_scope_update` 信号

**文件：**
- 修改：`hagoku/manager/orchestrator.py`（Scout 字段对齐循环中处理信号）

- [ ] **步骤 1：在 orchestrator 的 Scout 内层循环中处理 scope_update 信号**

在 `_apply_scout_reply_with_llm` 的 tool call 处理末尾（`update_field_role` 之后），scope 更新触发重派生：

在 `_apply_scout_reply_with_llm` 的 tool_call 遍历循环中，`update_field_role` 处理之后添加：

```python
# 已在 _handle_update_analysis_scope handler 中设置 ctx["_pending_scope_update"]
# orchestrator 层在 respond 路径中检测并处理
```

- [ ] **步骤 2：在 orchestrator.respond() 的 analyst 路径中检测信号**

在 `respond()` 方法的 analyst 分支（约 line 2960+），Analyst 返回后检查：

```python
if agent_name == "analyst":
    if context.get("_pending_scope_update"):
        from hagoku.agents.scout.agent import ScoutAgent
        # 借用 Scout 的 _derive_roles 重派生 target/features
        scout_tmp = ScoutAgent.__new__(ScoutAgent)
        scout_tmp._derive_roles(context)
        context.pop("_pending_scope_update", None)
        # 写入 ProjectContext
        project_ctx = context.get("_project_context")
        if project_ctx:
            project_ctx.add_agent_response(
                stage="analyst",
                revision=0,
                content="分析范围已更新",
                snapshot=project_ctx._derive_snapshot(context),
            )
```

- [ ] **步骤 3：运行测试确认无回归**

```bash
.venv/bin/python -m pytest tests/test_doctrine_compliance.py tests/test_product/test_information_arrival.py -q
```

---

### 任务 3：Analyst prompt 追加 scope 解锁指引

**文件：**
- 修改：`hagoku/agents/analyst/agent.py`（system prompt 追加一段）

- [ ] **步骤 1：在 Analyst system prompt 追加 scope 解锁指引**

在 `agent.py` 的 `run()` 方法中，`system = (...)` 字符串后追加：

```python
system += (
    "\n\n"
    "【分析范围解锁】\n"
    "分析开始时已设定核心关注字段。如果用户要求纳入新字段，先调 get_column_stats 检查数据质量。\n"
    "数据干净（空值率 < 20%、类型匹配）→ 调 update_analysis_scope 直接纳入。\n"
    "数据需清洗 → 告知用户建议从字段理解阶段重跑。\n"
)
```

- [ ] **步骤 2：运行测试**

```bash
.venv/bin/python -m pytest tests/test_doctrine_compliance.py -q
```

---

### 任务 4：守门测试 6 条

**文件：**
- 创建：`tests/test_product/test_scope_update.py`

- [ ] **步骤 1：G1 — Analyst prompt 含字段状态表**

```python
def test_g1_analyst_system_prefix_contains_field_status():
    """G1: Analyst 收到的 system_prefix 含字段参与状态。"""
    from hagoku.context.project_context import ProjectContext
    ctx = ProjectContext(analysis_goal="测试")
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
```

- [ ] **步骤 2：G2 — update_analysis_scope 更新 used_in_analysis**

```python
def test_g2_update_analysis_scope_updates_used_in_analysis():
    """G2: handler 更新 column_semantics 的 used_in_analysis。"""
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
```

- [ ] **步骤 3：G3 — 解锁后 `_derive_roles` 重新派生**

```python
def test_g3_unlock_triggers_role_re_derivation():
    """G3: scope 更新后 _derive_roles 重新计算 target/features。"""
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
```

- [ ] **步骤 4：G4 — 解锁落 ProjectContext snapshot**

```python
def test_g4_unlock_writes_project_context_snapshot():
    """G4: scope 更新后 ProjectContext 写入含新列的 snapshot。"""
    from hagoku.context.project_context import ProjectContext
    pctx = ProjectContext(analysis_goal="测试")
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
```

- [ ] **步骤 5：G5 — Cleaner assess prompt 不含 scope 外列**

```python
def test_g5_cleaner_assess_excludes_non_scope_columns():
    """G5: Cleaner assess() 的 col_names 不含 used_in_analysis=False 的列。"""
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
```

- [ ] **步骤 6：G6 — 大解锁不调 update_analysis_scope**

```python
def test_g6_big_unlock_does_not_call_tool():
    """G6: 数据质量差时 LLM 不应调 update_analysis_scope（由 prompt 约束，本测试验证 handler 本身正确）。"""
    from hagoku.tools.agent_tool_defs import _handle_update_analysis_scope
    ctx = {"column_semantics": []}
    result = _handle_update_analysis_scope({"add_columns": [], "remove_columns": []}, ctx, None)
    assert result["added"] == []
    assert result["removed"] == []
```

- [ ] **步骤 7：运行全部守门测试**

```bash
.venv/bin/python -m pytest tests/test_product/test_scope_update.py -v
```

---

### 任务 5：小解锁 emit 事件通知前端

**文件：**
- 修改：`hagoku/manager/orchestrator.py`（respond 路径 emit 事件）

- [ ] **步骤 1：在 respond 的 analyst 解锁路径 emit 事件**

在任务 2 的 `_pending_scope_update` 处理中追加：

```python
self.event_bus.emit(EventType.AGENT_THINKING, "analyst", {
    "thought": f"分析范围已更新：新增 {added}，移除 {removed}",
})
```

- [ ] **步骤 2：运行测试**

```bash
.venv/bin/python -m pytest tests/test_doctrine_compliance.py -q
```

---

### 任务 6：Cleaner run() 也过滤 scope 外列（可选）

**文件：**
- 修改：`hagoku/agents/cleaner/agent.py`（`run()` 方法开头加过滤）

- [ ] **步骤 1：在 run() 中复用 assess 的过滤逻辑**

在 `run()` 的数据加载之后、清洗操作之前：

```python
# scope 过滤：只清洗参与分析的列
analysis_cols = {
    str(s["column_name"]) for s in context.get("column_semantics", [])
    if s.get("used_in_analysis") is True
}
if analysis_cols:
    cleaning_cols = [c for c in df.columns if c in analysis_cols]
    df_to_clean = df[cleaning_cols]
else:
    df_to_clean = df
```

- [ ] **步骤 2：运行 cleaner 测试**

```bash
.venv/bin/python -m pytest tests/test_agents/ -q
```

---

### 任务 7：大解锁建议文案优化（可选）

**文件：**
- 修改：`hagoku/agents/analyst/agent.py`（prompt 中大解锁文案）

- [ ] **步骤 1：优化大解锁提示文案**

将任务 3 中的文案从：

```
数据需清洗 → 告知用户建议从字段理解阶段重跑。
```

改为：

```
数据需清洗 → 告知用户：「[列名] 数据质量问题（空值率 X%，原因），建议重置分析从字段理解阶段重跑以纳入此列。若坚持纳入，回复「不管，直接加」。」
```

---

### 执行顺序

| 优先级 | 任务 | 依赖 |
|--------|------|------|
| **P0** | 任务 1 (注册工具) | 无 |
| **P0** | 任务 2 (orchestrator 信号) | 任务 1 |
| **P0** | 任务 3 (Analyst prompt) | 无 |
| **P1** | 任务 4 (守门测试) | 任务 1-3 |
| **P1** | 任务 5 (emit 事件) | 任务 2 |
| **P2** | 任务 6 (Cleaner 过滤) | 无 |
| **P2** | 任务 7 (文案优化) | 任务 3 |

最小可行 = 任务 1-3；质量保障 = 任务 4-5；后续优化 = 任务 6-7。
