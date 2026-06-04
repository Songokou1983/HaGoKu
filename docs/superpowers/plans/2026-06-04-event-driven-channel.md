# 事件驱动通道 实现计划

> **面向 AI 代理的工作者：** 必需技能：使用 subagent-driven-development（推荐）或 executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** `orchestrator.run()` 不再阻塞线程——每次执行一个阶段后返回，后续交互由 `respond()` 驱动。LLM 通过 `route_to` 工具决定阶段切换。

**架构：** `run()` 拆为入口（Scout 推断）→ 设置 `self._stage="scout"` → 返回。`respond()` 根据 `self._stage` 路由到 handler。状态（`_stage`、`_context`、`_df_clean`）存 `self.*`。各阶段 Agent LLM 调 `route_to` 切换阶段。

**技术栈：** Python, pytest, 现有 orchestrator/ws_handler 框架

---

### 任务 1：注册 `route_to` 工具

**文件：**
- 修改：`hagoku/tools/agent_tool_defs.py`（追加工具定义 + handler）

- [ ] **步骤 1：在 agent_tool_defs.py 末尾添加 handler + 注册**

```python
def _handle_route_to(args: dict, ctx: dict, _df: pd.DataFrame | None) -> dict:
    """LLM 表达流程意图。留在当前阶段或切换到下一阶段。"""
    stage = args.get("stage")
    reason = args.get("reason", "")
    # handler 只返回数据，不执行路由。路由由 orchestrator 根据返回值执行。
    return {"stage": stage, "reason": reason}


agent_tools.register(Tool(
    name="route_to",
    description="表达流程意图。不传 stage 留在当前阶段（继续对话）；传 stage 切换阶段（scout/cleaner/analyst/reporter）",
    parameters={
        "type": "object",
        "properties": {
            "stage": {"type": "string", "enum": ["scout", "cleaner", "analyst", "reporter"]},
            "reason": {"type": "string", "description": "切换原因"},
        },
        "required": [],
    },
    handler=_handle_route_to,
    agents=["scout", "cleaner", "analyst", "reporter"],
))
```

- [ ] **步骤 2：运行测试**

```bash
.venv/bin/python -m pytest tests/test_tools/ -q
```

---

### 任务 2：orchestrator 状态管理基础设施

**文件：**
- 修改：`hagoku/manager/orchestrator.py`（`__init__` 加状态字段 + `_reset()`）

- [ ] **步骤 1：在 `__init__` 添加状态字段**

在现有 `__init__` 末尾追加：

```python
# 事件驱动状态机字段
self._stage: str = ""
self._df_clean: pd.DataFrame | None = None
self._df_raw: pd.DataFrame | None = None
self._analyst_messages: list[dict] = []
self._analyst_agent: Any = None
self._error: Exception | None = None
```

- [ ] **步骤 2：添加 `_reset()` 方法**

```python
def _reset_run_state(self) -> None:
    """新一轮分析前清理上次残留。"""
    self._stage = ""
    self._df_clean = None
    self._df_raw = None
    self._analyst_messages = []
    self._analyst_agent = None
    self._error = None
```

- [ ] **步骤 3：在 `run()` 入口调用 `_reset_run_state()`**

```python
def run(self, ...):
    if self._error:
        self._reset_run_state()
    # ... 继续现有逻辑
```

- [ ] **步骤 4：运行测试**

```bash
.venv/bin/python -m pytest tests/test_doctrine_compliance.py tests/test_product/test_information_arrival.py -q
```

---

### 任务 3：拆分 `run()` —— Scout 推断 → 设置 stage → 返回

**文件：**
- 修改：`hagoku/manager/orchestrator.py`（`run()` 中 Scout 完成后不继续执行 Cleaner，设置 `self._stage="scout"` 并返回）

- [ ] **步骤 1：修改 `run()` 中的 Scout 完成点**

在 Scout 推断 + 字段表展示后（约 line 2024），原来继续执行 Cleaner。改为设置 stage 并返回：

```python
# 原来：Scout 字段对齐 → while True 循环 → break → Cleaner
# 改为：
scout_msg = scout_field_review_pause_payload(context)
scout_msg["interaction_revision"] = interaction_revision
scout_msg = self._attach_pause_dialogue_message("scout", scout_msg)
user_reply_scout = self._pause_and_wait("scout", scout_msg)
if user_reply_scout == HAGOKU_CANCEL_PAUSE_TOKEN:
    return self._finish_run_cancelled(run_id, project_name, run_start, run_dir)

# 设置状态并返回
self._stage = "scout"
self._context = context
self._df_clean = df_clean
self._df_raw = df_raw
self._run_id = run_id
self._project_name = project_name
self._run_start = run_start
self._run_dir = run_dir
self.event_bus.emit(EventType.AGENT_COMPLETED, "scout", {
    "result_summary": "字段理解完成",
})
return {"status": "scout_review", "message": "字段理解完成"}
```

- [ ] **步骤 2：运行测试确认无回归**

```bash
.venv/bin/python -m pytest tests/test_doctrine_compliance.py tests/test_product/test_information_arrival.py -q
```

---

### 任务 4：新增 stage handler 函数

**文件：**
- 修改：`hagoku/manager/orchestrator.py`（新增 4 个 handler）

- [ ] **步骤 1：添加 `_handle_scout_reply()`**

```python
def _handle_scout_reply(self, user_input: str, context: dict) -> dict:
    """处理 Scout 字段对齐阶段的用户回复。"""
    applied = apply_scout_user_field_reply_to_context(
        context, user_input,
        llm_client=self.llm_quick_raw,
        llm_model=self.config.llm.model_quick or self.config.llm.model,
    )
    # 检查 LLM 是否调了 route_to（通过检查 tool_calls）
    # 简化：由 Agent LLM 调 route_to，这里只处理字段更新
    if applied and self.memory:
        self._persist_scout_field_updates(self._project_name, applied, context)

    # 重新展示字段表
    scout_msg = scout_field_review_pause_payload(context)
    scout_msg = self._attach_pause_dialogue_message("scout", scout_msg)
    return {
        "status": "scout_review",
        "message": "",
        "field_review": scout_msg.get("field_review"),
    }
```

- [ ] **步骤 2：添加 `_handle_cleaner_reply()`**

```python
def _handle_cleaner_reply(self, user_input: str, context: dict) -> dict:
    """处理 Cleaner 评估阶段的用户回复。"""
    cleaning_rules = self._cleaner._load_cleaning_rules()
    context["_user_feedback"] = user_input
    assessment = self._cleaner.assess(self._df_raw, context, cleaning_rules)
    context["_cleaner_assessment"] = assessment
    return {
        "status": "cleaner_review",
        "message": "",
        "cleaning_assessment": assessment,
    }
```

- [ ] **步骤 3：添加 `_handle_analyst_reply()`**

```python
def _handle_analyst_reply(self, user_input: str, context: dict) -> dict:
    """处理 Analyst 对话阶段的用户回复。"""
    if self._analyst_messages:
        self._analyst_messages.append({"role": "user", "content": user_input})
    result = self._analyst_agent.run_step(self._analyst_messages, context)
    self._analyst_messages = result["messages"]
    if result.get("submit_analysis"):
        return {"status": "analyst_done", "findings": result["findings"]}
    return {
        "status": "analyst_review",
        "message": result.get("text", ""),
    }
```

- [ ] **步骤 4：添加 `_handle_reporter_reply()`**

```python
def _handle_reporter_reply(self, user_input: str, context: dict) -> dict:
    """Reporter 阶段不互动，直接返回。"""
    return {"status": "reporter_done"}
```

- [ ] **步骤 5：运行测试**

```bash
.venv/bin/python -m pytest tests/test_doctrine_compliance.py -q
```

---

### 任务 5：`respond()` 路由改造

**文件：**
- 修改：`hagoku/manager/orchestrator.py`（`respond()` 方法根据 `self._stage` 路由）
- 修改：`hagoku/api/ws_handler.py`（`respond` 命令调用新路由）

- [ ] **步骤 1：添加路由表**

```python
_STAGE_HANDLERS = {
    "scout": "_handle_scout_reply",
    "cleaner": "_handle_cleaner_reply",
    "analyst": "_handle_analyst_reply",
    "reporter": "_handle_reporter_reply",
}
```

- [ ] **步骤 2：修改 `respond()` 入口**

```python
def respond(self, user_input: dict, project_name: str | None = None) -> dict:
    """处理 Agent 暂停后的用户响应。根据 self._stage 路由。"""
    agent_name = user_input.get("agent", "")
    phase = user_input.get("phase", "")
    text = user_input.get("text", "").strip()

    if self._error:
        return {"status": "error", "message": str(self._error)}

    if agent_name == "scout" and phase == "confirm_fields":
        return self._handle_scout_reply(text, self._context)

    handler_name = _STAGE_HANDLERS.get(self._stage)
    if handler_name:
        handler = getattr(self, handler_name)
        return handler(text, self._context)

    return {"status": "unknown_stage", "stage": self._stage}
```

- [ ] **步骤 3：运行测试**

```bash
.venv/bin/python -m pytest tests/test_doctrine_compliance.py tests/test_product/test_information_arrival.py -q
```

---

### 任务 6：Analyst 单步改造

**文件：**
- 修改：`hagoku/agents/analyst/agent.py`（新增 `run_step()` 方法，保留 `run()` 兼容）

- [ ] **步骤 1：新增 `run_step()` 方法**

```python
def run_step(self, messages: list[dict], context: dict) -> dict:
    """单步执行：跑一轮 LLM，返回结果。不循环，不暂停。"""
    import json as _json
    from hagoku.tools.registry import agent_tools as _agt
    from ...llm.client import create_raw_client

    client = create_raw_client(self.llm_config)
    _tools = _agt.to_openai("analyst")

    resp = client.chat.completions.create(
        model=self.llm_config.model, messages=messages,
        temperature=0.3, max_tokens=4096, tools=_tools, tool_choice="auto",
    )
    msg = resp.choices[0].message
    txt = (msg.content or "").strip()
    tc_list = getattr(msg, "tool_calls", None)

    findings = None
    if tc_list:
        tool_results = []
        for tc in tc_list:
            fn = tc.function
            args = _json.loads(fn.arguments) if fn.arguments else {}
            result = _agt.dispatch(fn.name, args, context, None)
            if fn.name == "submit_analysis":
                findings = result
                break
            tc_id = getattr(tc, "id", "") or ""
            tool_results.append({
                "role": "tool", "tool_call_id": tc_id,
                "content": _json.dumps(result, ensure_ascii=False, default=str),
            })
        if tool_results:
            assistant_block = {"role": "assistant", "content": txt or None}
            assistant_block["tool_calls"] = [...]
            messages.append(assistant_block)
            messages.extend(tool_results)
    elif txt:
        messages.append({"role": "assistant", "content": txt})

    return {
        "messages": messages,
        "text": txt,
        "submit_analysis": findings is not None,
        "findings": findings,
    }
```

- [ ] **步骤 2：运行测试**

```bash
.venv/bin/python -m pytest tests/test_agents/test_analyst_run.py -q
```

---

### 任务 7：ws_handler 适配

**文件：**
- 修改：`hagoku/api/ws_handler.py`（废弃 phase 自动转 full + respond 路由）

- [ ] **步骤 1：废弃 phase 自动转 full**

```python
# 在 analyze 命令处理中，phase = payload.get("phase", "full") 之后
if phase in ("analyst_first", "cleaning_first"):
    phase = "full"
```

- [ ] **步骤 2：运行测试**

```bash
.venv/bin/python -m pytest tests/test_doctrine_compliance.py -q
```

---

### 执行顺序

| 优先级 | 任务 | 依赖 |
|--------|------|------|
| P0 | 任务 1 (route_to 工具) | 无 |
| P0 | 任务 2 (状态管理基础设施) | 无 |
| P0 | 任务 3 (拆分 run() Scout 段) | 任务 2 |
| P0 | 任务 4 (stage handler) | 任务 2 |
| P0 | 任务 5 (respond() 路由) | 任务 3,4 |
| P1 | 任务 6 (Analyst 单步) | 任务 4 |
| P1 | 任务 7 (ws_handler 适配) | 无 |
