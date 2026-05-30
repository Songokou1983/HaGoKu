# ProjectContext 上下文记忆系统 实现计划

> **面向 AI 代理的工作者：** 必需技能：使用 subagent-driven-development（推荐）或 executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 构建统一的 Agent 上下文记忆系统 `ProjectContext`，替代分散的 `_session_messages`/`_conversation_history`/`utterances`，让所有 Agent 在一次 run 内共享完整的对话脉络和当前状态。

**架构：** 新增 `hagoku/context/project_context.py`，作为 EventBus 的被动消费者（与 Scribe 平级），监听 AGENT_STARTED / COMPLETED / USER_INPUT_RECEIVED 事件自动追加 entries。提供 `build_prompt(agent)` 方法为每个 Agent 拼装 system_prefix（当前状态）+ history_context（对话历史）。两阶段实施：先并行旧路径，再替换。

**技术栈：** Python 3.10+ dataclasses, EventBus subscriber pattern, pytest

---

## 阶段 1：搭骨架

### 任务 1：创建 ProjectContext 数据模型

**文件：**
- 创建：`hagoku/context/__init__.py`
- 创建：`hagoku/context/project_context.py`

- [ ] **步骤 1：创建 package init**

```python
# hagoku/context/__init__.py
"""HaGoKu 上下文记忆系统"""
```

- [ ] **步骤 2：编写 ProjectContext 和 ContextEntry**

```python
# hagoku/context/project_context.py
"""ProjectContext — 一次分析 run 的统一上下文记忆。

作为 EventBus 的被动消费者（与 Scribe 平级），自动记录所有 Agent 交互。
不做任何流程控制——只记录和查询。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal


@dataclass
class ContextEntry:
    """一条上下文记录。追加式，不可删除。"""

    type: Literal["goal", "agent_response", "user_feedback", "stage_transition"]
    stage: str                     # scout / cleaner / analyst / reporter
    revision: int                  # 阶段内轮数，从 0 开始
    timestamp: str                 # ISO-8601
    content: str                   # 人类可读摘要
    raw_user_text: str | None = None    # 律 2：用户原话（type=user_feedback 时必填）
    snapshot: dict[str, Any] | None = None  # type=agent_response 时附带


@dataclass
class ProjectContext:
    """一次分析 run 的完整上下文记忆。"""

    run_id: str
    analysis_goal: str
    entries: list[ContextEntry] = field(default_factory=list)

    # ── 追加接口 ──

    def add_entry(self, entry: ContextEntry) -> None:
        """追加一条记录。不可删除，不可修改已有记录。"""
        self.entries.append(entry)

    def add_user_feedback(
        self,
        stage: str,
        revision: int,
        raw_text: str,
        content: str = "",
    ) -> None:
        """记录用户反馈（律 2：保留原话）。"""
        self.entries.append(ContextEntry(
            type="user_feedback",
            stage=stage,
            revision=revision,
            timestamp=datetime.now(timezone.utc).isoformat(),
            content=content or raw_text[:200],
            raw_user_text=raw_text,
        ))

    def add_agent_response(
        self,
        stage: str,
        revision: int,
        content: str,
        snapshot: dict[str, Any] | None = None,
    ) -> None:
        """记录 Agent 响应，可附带字段状态快照。"""
        self.entries.append(ContextEntry(
            type="agent_response",
            stage=stage,
            revision=revision,
            timestamp=datetime.now(timezone.utc).isoformat(),
            content=content,
            snapshot=snapshot,
        ))

    def add_stage_transition(self, stage: str, content: str = "") -> None:
        """记录阶段切换。"""
        self.entries.append(ContextEntry(
            type="stage_transition",
            stage=stage,
            revision=0,
            timestamp=datetime.now(timezone.utc).isoformat(),
            content=content or f"进入 {stage} 阶段",
        ))

    # ── 快照生成（律 5：从 column_semantics 实时派生，不平行存储）──

    def _derive_snapshot(self, context: dict[str, Any]) -> dict[str, Any]:
        """从 context 的权威数据结构派生当前状态快照。"""
        semantics = context.get("column_semantics") or []
        fields = []
        pending = []
        for s in semantics:
            col = str(s.get("column_name", ""))
            if not col:
                continue
            fields.append({
                "name": col,
                "display": str(s.get("display_name", "") or ""),
                "role": str(s.get("suggested_role", "") or ""),
                "participating": bool(s.get("used_in_analysis")) if s.get("used_in_analysis") is not None else None,
            })
            if s.get("needs_user_input"):
                pending.append(col)

        return {
            "fields": fields,
            "target": context.get("target"),
            "features": context.get("features") or [],
            "pending": pending,
        }

    # ── 上下文拼装 ──

    def build_prompt(self, agent: str, context: dict[str, Any]) -> dict[str, str]:
        """为指定 Agent 拼装上下文注入块。

        Returns:
            {"system_prefix": str, "history_context": str}
        """
        # 1. system_prefix：分析目标 + 当前字段状态 + 角色 + 命令上下文
        snapshot = self._derive_snapshot(context)
        target = snapshot.get("target") or "（未设置）"
        features = snapshot.get("features") or []
        pending = snapshot.get("pending") or []
        cmd_text = (context.get("_pending_command_text") or "").strip()

        lines = [
            f"分析目标: {self.analysis_goal}",
            "",
            "当前字段状态:",
        ]
        for f in snapshot.get("fields", []):
            status = "参与" if f["participating"] is True else ("不参与" if f["participating"] is False else "待定")
            lines.append(f"  {f['name']}({f['display']}): {status}  role={f['role']}")

        lines.extend([
            "",
            f"目标变量: {target}",
            f"特征变量: {', '.join(features) if features else '（未设置）'}",
        ])
        if pending:
            lines.append(f"待确认字段: {', '.join(pending)}")
        if cmd_text:
            lines.extend(["", f"用户指令: {cmd_text}"])

        system_prefix = "\n".join(lines)

        # 2. history_context：当前阶段的对话历史 + 上游阶段快照摘要
        current_stage_entries = [e for e in self.entries if e.stage == agent]
        upstream_entries = [e for e in self.entries if e.stage != agent]

        history_parts: list[str] = []

        # 上游阶段：仅保留 agent_response 的 snapshot 摘要
        if upstream_entries:
            history_parts.append("【上游阶段摘要】")
            for e in upstream_entries:
                if e.type == "agent_response" and e.snapshot:
                    t = e.snapshot.get("target", "")
                    f = e.snapshot.get("features", [])
                    p = e.snapshot.get("pending", [])
                    summary = f"{e.stage} 阶段完成: target={t}, features={f}"
                    if p:
                        summary += f", 待确认={p}"
                    history_parts.append(summary)
                elif e.type == "stage_transition":
                    history_parts.append(f"→ {e.content}")
            history_parts.append("")

        # 当前阶段：完整对话历史
        if current_stage_entries:
            history_parts.append(f"【{agent} 阶段对话】")
            for e in current_stage_entries:
                if e.type == "user_feedback":
                    history_parts.append(f"用户: {e.raw_user_text or e.content}")
                elif e.type == "agent_response":
                    history_parts.append(f"Agent: {e.content}")
                elif e.type == "stage_transition":
                    history_parts.append(f"── {e.content} ──")
            history_parts.append("")

        history_context = "\n".join(history_parts)

        return {
            "system_prefix": system_prefix,
            "history_context": history_context,
        }
```

- [ ] **步骤 3：编写 EventBus 消费者回调**

在 `ProjectContext` 类中添加 `_on_event` 方法和 `subscribe` 方法：

```python
# 追加到 ProjectContext 类中

def subscribe(self, event_bus: Any, context_ref: dict[str, Any]) -> None:
    """注册为 EventBus 消费者。context_ref 是 orchestrator 的 context dict 引用。"""
    self._event_bus = event_bus
    self._context_ref = context_ref
    event_bus.subscribe(self._on_event)

def _on_event(self, event: Any) -> None:
    """EventBus 回调：监听关键事件并自动记录。"""
    from hagoku.observability.events import EventType

    etype = event.event_type
    agent = event.agent
    data = event.data or {}

    if etype == EventType.AGENT_STARTED:
        self.add_stage_transition(
            stage=agent,
            content=data.get("goal", f"{agent} 开始"),
        )

    elif etype == EventType.AGENT_COMPLETED:
        ctx = getattr(self, "_context_ref", {})
        snapshot = self._derive_snapshot(ctx) if ctx else None
        self.add_agent_response(
            stage=agent,
            revision=ctx.get("interaction_revision", 0) if ctx else 0,
            content=data.get("result_summary", data.get("message", f"{agent} 完成")),
            snapshot=snapshot,
        )

    elif etype == EventType.USER_INPUT_RECEIVED:
        ctx = getattr(self, "_context_ref", {})
        revision = ctx.get("interaction_revision", 0) if ctx else 0
        raw = data.get("reply", "")
        self.add_user_feedback(
            stage=agent,
            revision=revision,
            raw_text=raw,
            content=raw[:200] if raw else "",
        )
```

- [ ] **步骤 4：Commit**

```bash
git add hagoku/context/__init__.py hagoku/context/project_context.py
git commit -m "feat: 新增 ProjectContext 上下文记忆数据模型"
```

---

### 任务 2：编写 ProjectContext 单元测试

**文件：**
- 创建：`tests/test_context/__init__.py`
- 创建：`tests/test_context/test_project_context.py`

- [ ] **步骤 1：创建测试文件**

```python
# tests/test_context/__init__.py
```

- [ ] **步骤 2：编写测试用例**

```python
# tests/test_context/test_project_context.py
"""ProjectContext 单元测试 — 不依赖 EventBus 和真实 LLM。"""
from __future__ import annotations

import pytest

from hagoku.context.project_context import ContextEntry, ProjectContext


class TestProjectContext:
    """ProjectContext 数据模型测试"""

    def test_add_entry_appends(self):
        ctx = ProjectContext(run_id="r1", analysis_goal="分析ROI")
        ctx.add_entry(ContextEntry(
            type="user_feedback", stage="scout", revision=1,
            timestamp="2026-01-01T00:00:00", content="测试",
            raw_user_text="Code是店铺编号",
        ))
        assert len(ctx.entries) == 1
        assert ctx.entries[0].raw_user_text == "Code是店铺编号"

    def test_add_user_feedback_preserves_raw_text(self):
        """律 2：用户原话必须在 raw_user_text 中保留。"""
        ctx = ProjectContext(run_id="r1", analysis_goal="分析ROI")
        ctx.add_user_feedback(stage="scout", revision=1, raw_text="Period的中文名是周次")
        assert ctx.entries[0].raw_user_text == "Period的中文名是周次"
        assert ctx.entries[0].type == "user_feedback"

    def test_entries_are_append_only(self):
        """entries 只增不改，历史不可变。"""
        ctx = ProjectContext(run_id="r1", analysis_goal="分析ROI")
        ctx.add_user_feedback(stage="scout", revision=1, raw_text="第一轮")
        ctx.add_user_feedback(stage="scout", revision=2, raw_text="第二轮")
        assert len(ctx.entries) == 2
        assert ctx.entries[0].raw_user_text == "第一轮"
        assert ctx.entries[1].raw_user_text == "第二轮"

    def test_build_prompt_system_prefix_has_goal(self):
        """律 1：analysis_goal 永远在 system_prefix 首行。"""
        ctx = ProjectContext(run_id="r1", analysis_goal="分析各渠道ROI")
        result = ctx.build_prompt("scout", {"column_semantics": []})
        assert "分析各渠道ROI" in result["system_prefix"]

    def test_build_prompt_system_prefix_has_field_state(self):
        """system_prefix 包含从 column_semantics 派生的字段状态。"""
        ctx = ProjectContext(run_id="r1", analysis_goal="分析ROI")
        context = {
            "column_semantics": [
                {"column_name": "Code", "display_name": "店铺编号", "suggested_role": "feature", "used_in_analysis": True, "needs_user_input": False},
                {"column_name": "Period", "display_name": "周次", "suggested_role": "identifier", "used_in_analysis": False, "needs_user_input": True},
            ],
            "target": "Revenue",
            "features": ["Code"],
        }
        result = ctx.build_prompt("scout", context)
        assert "Code" in result["system_prefix"]
        assert "店铺编号" in result["system_prefix"]
        assert "Period" in result["system_prefix"]
        assert "Revenue" in result["system_prefix"]
        assert "Period" in result["system_prefix"]  # 待确认字段

    def test_build_prompt_history_context_includes_current_stage(self):
        """history_context 包含当前阶段的 user_feedback + agent_response。"""
        ctx = ProjectContext(run_id="r1", analysis_goal="分析ROI")
        ctx.add_user_feedback(stage="scout", revision=1, raw_text="Code是店铺编号")
        ctx.add_agent_response(stage="scout", revision=1, content="已更新 Code→店铺编号")

        result = ctx.build_prompt("scout", {"column_semantics": []})
        assert "Code是店铺编号" in result["history_context"]
        assert "已更新 Code→店铺编号" in result["history_context"]

    def test_build_prompt_history_context_excludes_other_stages_dialog(self):
        """上游阶段的对话细节不出现在当前阶段的 history_context 中（仅保留 snapshot 摘要）。"""
        ctx = ProjectContext(run_id="r1", analysis_goal="分析ROI")
        ctx.add_user_feedback(stage="scout", revision=1, raw_text="Code是店铺编号")
        ctx.add_agent_response(stage="scout", revision=1, content="已更新", snapshot={"target": "Revenue", "features": ["Code"], "pending": []})

        result = ctx.build_prompt("cleaner", {"column_semantics": []})
        # upstream 的对话细节不应出现
        assert "Code是店铺编号" not in result["history_context"]
        # 但 snapshot 摘要应出现
        assert "scout" in result["history_context"]

    def test_build_prompt_with_command_context(self):
        """_pending_command_text 应出现在 system_prefix 中。"""
        ctx = ProjectContext(run_id="r1", analysis_goal="分析ROI")
        context = {
            "column_semantics": [],
            "_pending_command_text": "/goal 改为分析利润趋势",
        }
        result = ctx.build_prompt("scout", context)
        assert "分析利润趋势" in result["system_prefix"]

    def test_snapshot_derived_from_column_semantics(self):
        """律 5：snapshot 从 column_semantics 实时派生，不平行存储。"""
        ctx = ProjectContext(run_id="r1", analysis_goal="分析ROI")
        context = {
            "column_semantics": [
                {"column_name": "Code", "display_name": "店铺编号", "used_in_analysis": True},
                {"column_name": "X", "display_name": "", "used_in_analysis": None},
            ],
        }
        snapshot = ctx._derive_snapshot(context)
        assert len(snapshot["fields"]) == 2
        assert snapshot["fields"][0]["participating"] is True
        assert snapshot["fields"][1]["participating"] is None

    def test_empty_context_does_not_crash(self):
        """空 context → build_prompt 正常返回，不抛异常。"""
        ctx = ProjectContext(run_id="r1", analysis_goal="分析ROI")
        result = ctx.build_prompt("scout", {})
        assert "system_prefix" in result
        assert "history_context" in result
        assert "分析ROI" in result["system_prefix"]
```

- [ ] **步骤 3：运行测试验证通过**

```bash
.venv/bin/python -m pytest tests/test_context/test_project_context.py -v
```
预期：11 passed

- [ ] **步骤 4：Commit**

```bash
git add tests/test_context/__init__.py tests/test_context/test_project_context.py
git commit -m "test: ProjectContext 单元测试（11 条）"
```

---

### 任务 3：将 ProjectContext 集成到 Orchestrator

**文件：**
- 修改：`hagoku/manager/orchestrator.py`

- [ ] **步骤 1：在 Orchestrator 初始化时创建 ProjectContext**

在 `run()` 方法中，Scribe 初始化之后（约 L1941），添加 ProjectContext 初始化：

```python
# 在 self.scribe = ScribeAgent(...) 之后添加：
from ..context.project_context import ProjectContext
self._project_context = ProjectContext(
    run_id=run_id,
    analysis_goal=query,
)
self._project_context.subscribe(self.event_bus, context_ref=None)
```

注意：`subscribe` 需要 `context_ref` 作为 context dict 的引用，但此时 context dict 还未创建。先传 None，后续在 context 创建后更新引用。

- [ ] **步骤 2：在 context 创建后更新 ProjectContext 的 context_ref**

在 Scout 执行完成、context dict 创建后（约 L2029），更新引用：

```python
# 在 context = scout.run(...) 之后添加：
if hasattr(self, '_project_context'):
    self._project_context._context_ref = context
```

- [ ] **步骤 3：在 run() 方法中初始化 context_ref 变量**

在 `run()` 方法开头声明 `context` 变量前，将 None 赋值给它，这样 subscribe 时的 context_ref 是有效的：

```python
# 在 run() 方法中，context = None 声明后，_project_context 初始化前：
# （ProjectContext 用 run_id + query 初始化，context_ref 初始为 None，后续更新）
```

- [ ] **步骤 4：运行现有测试，确认无回归**

```bash
.venv/bin/python -m pytest tests/test_product/test_agent_interaction_contract.py -q
.venv/bin/python -m pytest tests/test_product/test_information_arrival.py -q
.venv/bin/python -m pytest --tb=short -q
```

预期：无新增失败

- [ ] **步骤 5：Commit**

```bash
git add hagoku/manager/orchestrator.py
git commit -m "feat: Orchestrator 集成 ProjectContext（阶段1：并行旧路径）"
```

---

### 任务 4：编写 EventBus 集成测试

**文件：**
- 修改：`tests/test_context/test_project_context.py`

- [ ] **步骤 1：新增 EventBus 集成测试**

在测试文件末尾追加：

```python
class TestProjectContextEventBus:
    """ProjectContext + EventBus 集成测试"""

    def test_agent_started_adds_stage_transition(self):
        from hagoku.observability.event_bus import EventBus
        from hagoku.observability.events import EventType

        ctx = ProjectContext(run_id="r1", analysis_goal="分析ROI")
        bus = EventBus()
        ctx.subscribe(bus, context_ref={})

        bus.emit(EventType.AGENT_STARTED, "scout", {"goal": "数据侦察"})
        assert len(ctx.entries) == 1
        assert ctx.entries[0].type == "stage_transition"
        assert ctx.entries[0].stage == "scout"

    def test_agent_completed_adds_response_with_snapshot(self):
        from hagoku.observability.event_bus import EventBus
        from hagoku.observability.events import EventType

        ctx = ProjectContext(run_id="r1", analysis_goal="分析ROI")
        bus = EventBus()
        test_ctx = {
            "column_semantics": [
                {"column_name": "Code", "display_name": "店铺", "used_in_analysis": True},
            ],
            "target": "Revenue",
            "features": ["Code"],
            "interaction_revision": 2,
        }
        ctx.subscribe(bus, context_ref=test_ctx)

        bus.emit(EventType.AGENT_COMPLETED, "scout", {"result_summary": "完成"})
        assert len(ctx.entries) == 1
        assert ctx.entries[0].type == "agent_response"
        assert ctx.entries[0].snapshot is not None
        assert ctx.entries[0].snapshot["target"] == "Revenue"

    def test_user_input_received_adds_feedback(self):
        from hagoku.observability.event_bus import EventBus
        from hagoku.observability.events import EventType

        ctx = ProjectContext(run_id="r1", analysis_goal="分析ROI")
        bus = EventBus()
        ctx.subscribe(bus, context_ref={"interaction_revision": 1})

        bus.emit(EventType.USER_INPUT_RECEIVED, "scout", {"reply": "Code是店铺编号"})
        assert len(ctx.entries) == 1
        assert ctx.entries[0].type == "user_feedback"
        assert ctx.entries[0].raw_user_text == "Code是店铺编号"

    def test_multiple_events_accumulate(self):
        """EventBus 多次事件 → entries 正常累积。"""
        from hagoku.observability.event_bus import EventBus
        from hagoku.observability.events import EventType

        ctx = ProjectContext(run_id="r1", analysis_goal="分析ROI")
        bus = EventBus()
        ctx.subscribe(bus, context_ref={})

        bus.emit(EventType.AGENT_STARTED, "scout", {})
        bus.emit(EventType.USER_INPUT_RECEIVED, "scout", {"reply": "反馈1"})
        bus.emit(EventType.USER_INPUT_RECEIVED, "scout", {"reply": "反馈2"})

        assert len(ctx.entries) == 3
        assert ctx.entries[1].raw_user_text == "反馈1"
        assert ctx.entries[2].raw_user_text == "反馈2"
```

- [ ] **步骤 2：运行测试验证通过**

```bash
.venv/bin/python -m pytest tests/test_context/test_project_context.py -v
```
预期：15 passed (11 + 4)

- [ ] **步骤 3：Commit**

```bash
git add tests/test_context/test_project_context.py
git commit -m "test: ProjectContext EventBus 集成测试（4 条）"
```

---

## 阶段 2：突破字段理解

### 任务 5：修改 _apply_scout_reply_with_llm 使用 build_prompt

**文件：**
- 修改：`hagoku/manager/orchestrator.py`（L866–1250 区域）

- [ ] **步骤 1：在 _apply_scout_reply_with_llm 函数开头获取 ProjectContext**

在函数签名不改变的前提下，从 context dict 获取 ProjectContext 引用（orchestrator 会在 context 中注入）：

```python
# 在 _apply_scout_reply_with_llm 中，field_state 构建之后、session_msgs 分支之前，添加：
project_ctx = context.get("_project_context")
```

- [ ] **步骤 2：替换 session_msgs 分支逻辑**

将 L1017–1024 的逻辑改为：

```python
# ── 使用 ProjectContext.build_prompt 替代旧的 _session_messages ──
if project_ctx:
    ctx_block = project_ctx.build_prompt("scout", context)
    # system_prefix 注入到 system role；history_context + raw 作为 user
    messages = [
        {"role": "system", "content": system_msg + "\n\n" + ctx_block["system_prefix"]},
        {"role": "user", "content": ctx_block["history_context"] + "\n\n【当前用户输入】\n" + raw},
    ]
else:
    # 降级：没有 ProjectContext 时回退旧路径
    session_msgs = context.get("_session_messages", [])
    if session_msgs:
        messages = list(session_msgs)
        messages.append({"role": "user", "content": raw})
    else:
        messages = [
            {"role": "system", "content": system_msg},
            {"role": "user", "content": raw},
        ]
```

- [ ] **步骤 3：在 Orchestrator.run() 中将 ProjectContext 注入 context**

在 `apply_scout_user_field_reply_to_context` 调用前（约 L2234），确保 context 中有 `_project_context`：

```python
# 在 Scout 多轮循环开始前添加：
context["_project_context"] = getattr(self, '_project_context', None)
```

- [ ] **步骤 4：运行现有测试确认无回归**

```bash
.venv/bin/python -m pytest tests/test_product/test_agent_interaction_contract.py -q
.venv/bin/python -m pytest tests/test_context/test_project_context.py -v
```
预期：无新增失败

- [ ] **步骤 5：Commit**

```bash
git add hagoku/manager/orchestrator.py
git commit -m "feat: _apply_scout_reply_with_llm 接入 ProjectContext.build_prompt（修复断裂点 1/2/3）"
```

---

### 任务 6：清理旧的 _session_messages 手动拼接逻辑

**文件：**
- 修改：`hagoku/manager/orchestrator.py`
- 修改：`hagoku/agents/scout/agent.py`

- [ ] **步骤 1：移除 orchestrator 中的 _session_messages 追加逻辑**

在 `_apply_scout_reply_with_llm` 中（约 L1070–1083），移除旧的 session_msgs 追加代码，改为仅通过 ProjectContext 记录：

```python
# 旧代码（移除）：
# if session_msgs:
#     state_after = [...]
#     session_msgs.append({"role": "assistant", "content": assistant_turn})
#     context["_session_messages"] = session_msgs

# 新代码：
# ProjectContext 已经通过 EventBus 回调自动记录了 AGENT_COMPLETED，
# 此处不需要手动追加入口。如需额外信息，通过 project_ctx 追加：
if project_ctx:
    applied_summary = ", ".join(applied) if applied else "无字段更新"
    project_ctx.add_agent_response(
        stage="scout",
        revision=context.get("interaction_revision", 0),
        content=applied_summary,
        snapshot=project_ctx._derive_snapshot(context),
    )
```

- [ ] **步骤 2：移除 Scout Agent 中的 _session_messages 初始化**

在 `hagoku/agents/scout/agent.py` 中（L803），移除 `self._session_messages` 赋值：

```python
# 移除：
# self._session_messages = [
#     {"role": "system", "content": system_prompt},
#     {"role": "user", "content": f"请分析以下数据集的字段语义..."},
#     {"role": "assistant", "content": raw_text or _json.dumps(result, ensure_ascii=False)},
# ]
```

同时移除 context dict 中的 `"_session_messages"` 字段注入（L225, L319）：

```python
# 移除 context dict 中的这行：
# "_session_messages": getattr(self, "_session_messages", []),
```

- [ ] **步骤 3：运行全量测试确认无回归**

```bash
.venv/bin/python -m pytest --tb=short -q
```
预期：无新增失败

- [ ] **步骤 4：Commit**

```bash
git add hagoku/manager/orchestrator.py hagoku/agents/scout/agent.py
git commit -m "refactor: 移除 _session_messages 旧路径，由 ProjectContext 统一接管"
```

---

### 任务 7：新增信息抵达正向断言（律 6）

**文件：**
- 修改：`tests/test_product/test_information_arrival.py`

- [ ] **步骤 1：新增 ProjectContext 相关断言**

在测试文件中追加：

```python
def test_project_context_injects_goal_to_prompt():
    """律 1 + 律 6：build_prompt 的 system_prefix 首行必须包含 analysis_goal。"""
    from hagoku.context.project_context import ProjectContext

    ctx = ProjectContext(run_id="test", analysis_goal="分析销售趋势")
    result = ctx.build_prompt("scout", {"column_semantics": []})
    first_line = result["system_prefix"].strip().split("\n")[0]
    assert "分析销售趋势" in first_line, f"system_prefix 首行不含分析目标: {first_line}"


def test_project_context_preserves_user_raw_text():
    """律 2 + 律 6：user_feedback entry 必须保留 raw_user_text。"""
    from hagoku.context.project_context import ProjectContext

    ctx = ProjectContext(run_id="test", analysis_goal="分析ROI")
    ctx.add_user_feedback(stage="scout", revision=1, raw_text="Period是周次")
    assert ctx.entries[0].raw_user_text == "Period是周次"


def test_project_context_history_includes_full_stage_dialog():
    """律 3 + 律 6：同一阶段的多轮对话必须全部出现在 history_context 中。"""
    from hagoku.context.project_context import ProjectContext

    ctx = ProjectContext(run_id="test", analysis_goal="分析ROI")
    ctx.add_user_feedback(stage="scout", revision=1, raw_text="第一轮纠正")
    ctx.add_agent_response(stage="scout", revision=1, content="已处理第一轮")
    ctx.add_user_feedback(stage="scout", revision=2, raw_text="第二轮纠正")
    ctx.add_agent_response(stage="scout", revision=2, content="已处理第二轮")

    result = ctx.build_prompt("scout", {"column_semantics": []})
    assert "第一轮纠正" in result["history_context"]
    assert "第二轮纠正" in result["history_context"]
    assert result["history_context"].index("第一轮纠正") < result["history_context"].index("第二轮纠正"), \
        "对话顺序应保持时间序"
```

- [ ] **步骤 2：运行测试验证通过**

```bash
.venv/bin/python -m pytest tests/test_product/test_information_arrival.py -v -k "project_context"
```
预期：3 passed

- [ ] **步骤 3：Commit**

```bash
git add tests/test_product/test_information_arrival.py
git commit -m "test: 新增 ProjectContext 信息抵达正向断言（律 1/2/3/6）"
```

---

### 任务 8：最终回归验证

- [ ] **步骤 1：运行铁律规定的三组测试**

```bash
.venv/bin/python -m pytest tests/test_doctrine_compliance.py -q
.venv/bin/python -m pytest tests/test_product/test_information_arrival.py -q
.venv/bin/python -m pytest --tb=short -q
```

预期：三组全绿

- [ ] **步骤 2：确认无新增 ruff 警告**

```bash
.venv/bin/python -m ruff check hagoku/context/ hagoku/manager/orchestrator.py
```

- [ ] **步骤 3：最终 Commit**

```bash
git add -A
git commit -m "chore: 阶段2完成 — ProjectContext 上下文记忆系统全部落地"
```
