# Phase C 详细设计稿 — 阶段切换 LLM 化（2026-06-11）

> **文档定位**：架构审核方出具的 Phase C 落地设计，一次性完整执行包，交付实施 AI 执行。
>
> **上游 brief**：[`2026-06-11-collapse-to-single-agent-brief.md`](2026-06-11-collapse-to-single-agent-brief.md) §3 Phase C
>
> **前置条件**：Phase B 7 个 commit 已合并（截至 `33010c8`），570 tests 绿。
>
> **关键设计决策（待用户审）**：
> - 阶段切换权**完全交给 LLM**——orchestrator/reply_handlers 不再做"判断"，只做"机械执行"
> - kanban **保留**作为 UI 显示对象（不删 db），但 agent **不再调** `block_task` / `unblock_task`
> - `ask_user` 工具补"暂停"语义：LLM 调用 → orchestrator emit `USER_INPUT_REQUESTED` → WS 推送 → UI 暂停
> - **不动 prompt.md**（铁律 10）——本 Phase 只动通道，不动 LLM 教学

---

## 目录

- §0 来龙去脉 + 调研事实
- §1 真实工作量
- §2 工具升级：`done_with_stage` + `route_to` 整合
- §3 `reply_handlers.py` 改造 — 删硬编码确认词
- §4 `ask_user` 暂停路径接通
- §5 kanban 降级路径
- §6 WS / UI 影响
- §7 测试改造
- §8 真 LLM 冒烟测试
- §9 律的减法清单
- §10 风险点 + 应对
- §11 4 个 CO-C 任务的精确执行顺序
- §12 终审清单
- §13 不做什么
- §14 审核方对开发者的硬规则
- §15 完成标准

---

## §0 来龙去脉 + 调研事实

### 0.1 触发

Phase B 完成后，通道单一性已建立（chat 物理唯一，LLM 看到完整推理链）。但**阶段切换权仍在代码手里**——这是项目「LLM 主导」信条与「现实架构」之间的最后一个大裂口。

### 0.2 调研发现的精确现状

审核方在 [Phase C 立项调研](81c47fe2-fa7d-4599-8ca6-7c296bf1098d) 摸清当前代码：

| 项 | 现状 |
|---|---|
| `self._stage` 命中 | **5 处**（159/195/300/390 init/reset；reply_handlers 内 `("switch", X)` 反射赋值）|
| 阶段切换机制 | **3 层并存**：code 硬编码确认词 + LLM `route_to` + kanban 事件驱动 |
| 硬编码确认词 | `reply_handlers.py:26-30`（scout）+ `:147-152`（cleaner）— 2 处 |
| `route_to` 工具 | **已注册** 4 agent；handler 完整；测试覆盖；但**只是"可选路径"**——code 仍优先看确认词 |
| `done_with_stage` | **0 处**——brief 假设有，实际没有 |
| `ask_user` 工具 | **已注册**但仅 analyst；handler 仅返回 `{question, options}`；**无暂停语义** |
| `USER_INPUT_REQUESTED` emit | **6 处全在 reply_handlers**（agent 层 0 处）|
| kanban.block_task / unblock_task | **被 5 处 agent 调用**（scout/cleaner/reporter 共 6 block + 4 unblock）|
| kanban 读决策 | **0 处**——pipeline 阶段由 `_stage` 决定，kanban 仅同步显示 |
| WS UI | `PipelineBar` 走 WS 事件（不读 kanban.db）；`KanbanPanel` 走 REST 拉 kanban.db |

### 0.3 brief 校正

| brief 假设 | 实际 | 影响 |
|---|---|---|
| 「`route_to` 已部分存在，统一升级」 | route_to 完整存在；但 code 硬编码确认词仍**抢在 route_to 前面判** | 不是"升级 route_to"，是**删确认词分支**让 route_to 成为唯一入口 |
| 「新增 `done_with_stage` 工具」 | 0 处 | 评估是否真有必要——`route_to(stage="cleaner")` 已能表达同样语义 |
| 「`kanban.db` 降级为 UI 显示」 | 已经主要是显示，仅 block/unblock 还有控制语义 | 真正要做的是**删 agent 层 block/unblock 调用**，db 本身不动 |
| 「暂停做成 chat turn」 | 当前暂停是 reply_handlers code 决定的 emit | 真正要做的是**让 LLM `ask_user` 触发 emit**，code 不主动判 |

### 0.4 真正要根除的反模式（用调研结果重新陈述）

| 反模式 | 现存位置 | 危害 |
|---|---|---|
| **形态 1**：code 关键词匹配中文确认词决定阶段 | `reply_handlers.py:26-30, 147-152` | **铁律 1 违规**——LLM 主导原则被代码越权 |
| **形态 2**：code 主动判断"该暂停了" → emit USER_INPUT_REQUESTED | reply_handlers 6 处 | 暂停时机是 LLM 的判断（"我需要用户决策"），不是 code 的判断 |
| **形态 3**：agent 调 `block_task` / `unblock_task` 做门控 | scout/cleaner/reporter 共 10 处 | block 是 UI 状态展示，不该由 agent 决定流程是否阻塞 |
| **形态 4**：硬编码"4-stage pipeline 顺序"在 code 里 | `_STAGE_HANDLERS` dict + kanban promote 规则 | LLM 应该能跳过阶段（如直接 reporter）；目前 code 强制按序 |

---

## §1 Phase C 真实工作量

| 文件 | 净改动行数估算 | 类别 |
|---|---|---|
| `hagoku/tools/agent_tool_defs.py` | +50 / -10 | `route_to` 升级 + `ask_user` schema 加 `expected_format` |
| `hagoku/manager/llm_dispatch/reply_handlers.py` | -180 / +60 | 删 4 个 handler 的硬编码确认词 + 改为机械执行 route_to |
| `hagoku/manager/orchestrator.py` | -20 / +30 | `respond()` 简化；加 `ask_user` → emit 暂停的桥接 |
| `hagoku/agents/scout/agent.py` | -10 | 删 block_task / unblock_task 调用 |
| `hagoku/agents/cleaner/agent.py` | -10 | 同上 |
| `hagoku/agents/reporter/agent.py` | -10 | 同上 |
| `hagoku/storage/kanban.py` | +5 / 0 | block_task/unblock_task 加 `DeprecationWarning`（不删，保 db schema 兼容）|
| `hagoku/manager/payloads/*.py` | -50 | 删 code 主动构造的暂停 payload 桥接 |
| `hagoku_web/src/...` | +30 / -10 | 适配 `ask_user` 工具调用的新事件展示 |
| `tests/test_product/test_*` | +100 / -150 | 删硬编码确认词测试；加 route_to / ask_user 行为测试 |
| **合计净** | **约 -240 行代码** | **工期估算 3-5 天** |

---

## §2 工具升级：`done_with_stage` + `route_to` 整合

### 2.1 决策：保留 `route_to`，**不新增 `done_with_stage`**

调研显示 `route_to` 已完整存在且 4 agent 都能调。新加 `done_with_stage` 会产生两个语义重叠工具，违反铁律 4（决策位置律）。

设计稿采纳：**只用 `route_to`，brief 提到的 `done_with_stage` 语义合并进 `route_to`**。

### 2.2 `route_to` schema 微调（让 LLM 更清楚什么时候用）

**当前**：

```python
name="route_to"
description="表达流程意图。不传 stage 留在当前阶段（继续对话）；传 stage 切换阶段（scout/cleaner/analyst/reporter）"
```

**改为**（更明确暂停 vs 切换）：

```python
name="route_to"
description=(
    "声明你接下来要去哪里。三种用法：\n"
    "1. 切换阶段 → 传 stage（scout/cleaner/analyst/reporter），表示『本阶段我做完了，去下一个』\n"
    "2. 留在当前阶段 → 不传 stage，表示『我还有话要说，继续这条对话』\n"
    "3. 提前结束 → 传 stage='reporter'，跳过中间阶段直接收尾\n"
    "\n"
    "这是你控制 pipeline 流向的唯一方式——代码不再用任何关键词（如『确认』『继续』）替你判断。"
)
parameters={
    "type": "object",
    "properties": {
        "stage": {"type": "string", "enum": ["scout", "cleaner", "analyst", "reporter"]},
        "reason": {"type": "string", "description": "切换原因——告诉用户和后续 AI 为什么走这条路"},
    },
    "required": ["reason"],  # ← 改：reason 强制（让 LLM 自觉解释判断）
}
```

> **关键改动**：`reason` 从可选变必填。理由：（1）让 LLM 显式说明判断；（2）UI 渲染时有内容展示；（3）后人审 dump 能看到 LLM 思路。

### 2.3 `ask_user` schema 升级

**当前**：仅 analyst 可调，handler 返回 `{question, options}`，**无暂停语义**。

**改为**：4 agent 全部可调（暂停是任意阶段都该有的能力）+ handler 触发暂停事件。

```python
name="ask_user"
description=(
    "向用户提问并暂停等待回复。**调用此工具会让 pipeline 进入暂停状态，等用户在 UI 回复**。\n"
    "适用场景：你需要用户做方向性决策（如『要不要把 outlier 移除』），单靠数据无法判断。\n"
    "不适用：你只是想说一段话——那直接输出文本即可，不要用此工具。"
)
parameters={
    "type": "object",
    "properties": {
        "question": {"type": "string", "description": "问题文本"},
        "options": {
            "type": "array", "items": {"type": "string"},
            "description": "可选回复项（让用户从中选）；若开放问题不传"
        },
        "expected_format": {
            "type": "string",
            "enum": ["choice", "free_text", "yes_no"],
            "description": "期望回复格式——UI 据此渲染单选/输入框/确认按钮"
        },
    },
    "required": ["question", "expected_format"],
}
agents=["scout", "cleaner", "analyst", "reporter"]  # ← 改：4 个全部
```

### 2.4 工具实现（dispatch handler）

**`route_to` handler** 不变——已正确返回 `{stage, reason}`，由 `reply_handlers` 消费。

**`ask_user` handler 升级**：

```python
def _handle_ask_user(args: dict, context: dict, df) -> dict:
    """处理 LLM 的 ask_user 调用——触发暂停信号写入 context。

    orchestrator/reply_handlers 检测到 context["_pending_ask_user"] 后：
      1. emit USER_INPUT_REQUESTED 事件（payload 含 question/options/expected_format）
      2. 设置 _stage 仍为当前阶段（不切换）
      3. respond() 返回，等待 WS 收到用户回复后再走一轮
    """
    pending = {
        "question": args.get("question", ""),
        "options": args.get("options", []),
        "expected_format": args.get("expected_format", "free_text"),
        "asked_by_stage": context.get("_current_stage", "unknown"),
    }
    context["_pending_ask_user"] = pending
    return pending
```

> 注：`context["_current_stage"]` 由 orchestrator 在每次进 handler 时写入——见 §3.3。

---

## §3 `reply_handlers.py` 改造 — 删硬编码确认词

### 3.1 当前违规清单（精确行号）

| 行号 | 内容 | 违规类型 |
|---|---|---|
| 26-30 | `if user_text in ("确认", "好的", "继续", ...): return ("switch", "cleaner")` | 形态 1（中文关键词分支）|
| 147-152 | 同上，cleaner→analyst | 形态 1 |
| 83-87 | `if not applied: return ("switch", "cleaner")` | 形态 2（code 替 LLM 判 "无更新就走"）|
| 26-30 上下文 | 空输入补发字段表逻辑 | 形态 2（code 决定何时重发 UI）|

### 3.2 改造后的 handler 形态

**每个 `_handle_*_reply` 收缩为 ~15 行**——只做三件事：

1. 把用户原话写入 ProjectContext（Phase B 已做）
2. 调 agent.run_step()（agent 内部走 to_messages_for_llm）
3. 根据 `context["_*_route_to"]` / `context["_pending_ask_user"]` 机械执行

**核心改造 — `_handle_scout_reply`（示意）**：

```python
def _handle_scout_reply(self, user_input: str, context: dict) -> tuple:
    """Scout 阶段用户回复处理 — 纯通道转发，不做语义判断。

    决策路径（按优先级）：
    1. LLM 调了 ask_user → emit USER_INPUT_REQUESTED，留在 scout 等用户
    2. LLM 调了 route_to(stage=X) → switch X
    3. 其他 → 留在 scout，等下一轮用户输入
    """
    # 1. 调 scout_reply（已走 ProjectContext + build_messages）
    self._apply_scout_reply_with_llm(user_input, context)

    # 2. 检查 ask_user 暂停
    ask = context.pop("_pending_ask_user", None)
    if ask:
        self._emit(EventType.USER_INPUT_REQUESTED, "scout", ask)
        return ("stay", None)

    # 3. 检查 route_to 切换
    route = context.pop("_scout_route_to", None)
    if route and route.get("stage"):
        return ("switch", route["stage"], {"reason": route.get("reason", "")})

    # 4. 默认留在当前阶段（LLM 没说要走，就继续）
    return ("stay", None)
```

> **没有**关键词分支、没有"是否首次"判断、没有"空输入补发字段表"——这些都让 LLM 自己处理。

**对照 cleaner / analyst / reporter handler**：同模式，删硬编码分支。

### 3.3 `orchestrator.respond()` 微调

```python
def respond(self, user_input: dict) -> None:
    """处理用户回复 — 路由到当前 stage 的 handler。"""
    text = user_input.get("text", "")
    stage = self._stage or "scout"

    # 把当前 stage 写入 context（供 ask_user handler 标记 asked_by_stage）
    self._context["_current_stage"] = stage

    handler_name = self._STAGE_HANDLERS.get(stage)
    if not handler_name:
        raise RuntimeError(f"未知阶段: {stage}")

    handler = getattr(self, handler_name)
    result = handler(text, self._context)

    action = result[0]
    if action == "switch":
        target = result[1]
        # 写入 ProjectContext（stage_transition entry）
        self._project_ctx.add_stage_transition(target, content=result[2].get("reason", ""))
        self._stage = target
        # 递归继续处理（首轮自动跑下一阶段）
        self.respond({"text": ""})
    # action == "stay" → 等下一次 WS respond
```

> 比当前实现少了所有 if-elif 链；只机械执行 handler 返回的 `("switch" / "stay", ...)`。

---

## §4 `ask_user` 暂停路径接通

### 4.1 数据流

```
LLM 在 run_step 内调 ask_user(question, expected_format)
       ↓
agent_tool_defs._handle_ask_user → context["_pending_ask_user"] = {...}
       ↓
agent.run_step 返回，回到 reply_handlers
       ↓
reply_handlers._handle_*_reply 检测 context["_pending_ask_user"]
       ↓
orchestrator._emit(USER_INPUT_REQUESTED, stage, ask_payload)
       ↓
WSBridge.on_event → 前端 useWsEventHandler
       ↓
前端按 expected_format 渲染（单选 / 输入框 / 确认按钮）
       ↓
用户回复 → WS cmd=respond → orchestrator.respond()
       ↓
新 user_input 写入 ProjectContext → 下一轮 agent.run_step 看到完整对话
```

### 4.2 关键不变

- `USER_INPUT_REQUESTED` 事件名**不变**（前端无需改 event handler）
- `expected_format` 是新字段——前端兼容旧 payload（无此字段时按 `free_text` 处理）
- 暂停期间 `_stage` 不变——用户回复后继续当前 stage

### 4.3 ask_user 与 route_to 的优先级

**LLM 同时调了两个时**：`ask_user` 优先（先暂停问用户，等回复后再决定是否切换）。

这是 §3.2 handler 内的判断顺序——先看 `_pending_ask_user`，再看 `_*_route_to`。

---

## §5 kanban 降级路径

### 5.1 当前 agent 层 block/unblock 调用

| 文件 | 行号 | 调用 | 用途 |
|---|---|---|---|
| `agents/scout/agent.py` | 332 | block | 字段推断完等用户确认 |
| `agents/scout/agent.py` | 413 | block | LLM 字段更新后等用户确认 |
| `agents/scout/agent.py` | 437 | unblock | 用户确认后解锁 |
| `agents/cleaner/agent.py` | 468 | block | assess 完等用户确认清洗方案 |
| `agents/cleaner/agent.py` | 527 | block | 同上（另一分支） |
| `agents/cleaner/agent.py` | 579 | unblock | 用户确认后解锁 |
| `agents/reporter/agent.py` | 598 | block | 报告完成等用户最终确认 |
| `agents/reporter/agent.py` | 628, 632 | unblock | 解锁路径 |

**共 10 处**。

### 5.2 改造方案

**全部删除**——理由：

1. block/unblock 本质是"等用户输入"——这语义已由 `USER_INPUT_REQUESTED` 事件表达
2. 双写（kanban blocked + emit USER_INPUT_REQUESTED）违反铁律 4（决策位置律）
3. kanban.db 仍保留——UI 通过 WS 事件 + ProjectContext 重建 kanban 状态视图

### 5.3 kanban.py 内 block/unblock 方法保留 + 加 DeprecationWarning

```python
def block_task(self, task_id, reason, actor="system") -> bool:
    """[Phase C 起 deprecated] agent 不应直接调 block_task。

    阶段控制权已交给 LLM——LLM 调 ask_user 工具表达暂停意图，
    orchestrator 据此 emit USER_INPUT_REQUESTED。kanban 块状态由
    UI 层根据事件流自行计算，不再由 agent 写入。

    保留此方法仅为 orchestrator._on_event 在收到 USER_INPUT_REQUESTED
    后同步 kanban 用（让旧 KanbanPanel REST 调用仍能看到 blocked 状态）。
    """
    import warnings
    warnings.warn(
        "kanban.block_task 应仅由 orchestrator._on_event 间接调用，"
        "agent 不应直接调。Phase C 之后将彻底移除。",
        DeprecationWarning, stacklevel=2
    )
    # 实际写 db 逻辑保留不变
    ...
```

### 5.4 orchestrator 在 emit `USER_INPUT_REQUESTED` 时同步 kanban

```python
def _on_event(self, event):
    """事件桥——把 LLM/handler 的事件同步到 kanban 显示。"""
    ...
    if event.event_type == EventType.USER_INPUT_REQUESTED:
        # 同步 kanban：当前 stage task 进入 blocked
        active_task = self.kanban.get_active_task(event.agent)
        if active_task:
            self.kanban.block_task(active_task["id"], event.data.get("question", "等用户回复"))
    elif event.event_type == EventType.AGENT_THINKING and self._just_unblocked(event.agent):
        # 用户回复后，下一次 agent thinking → unblock
        active_task = self.kanban.get_active_task(event.agent)
        if active_task and active_task["status"] == "blocked":
            self.kanban.unblock_task(active_task["id"])
```

> **效果**：kanban 完全降级为**事件消费者**，不再是控制者。agent 不感知 kanban 存在。

---

## §6 WS / UI 影响

### 6.1 WS 层（`ws_handler.py`）

**改动 1**：`_build_state_snapshot` 重连快照——增加 `pending_ask_user` 字段

```python
def _build_state_snapshot(orch):
    snap = {
        "stage": orch._stage,
        "phase": orch._phase,
        ...
    }
    pending = orch._context.get("_pending_ask_user")
    if pending:
        snap["pending_ask_user"] = pending  # 重连时恢复暂停 UI
    return snap
```

**改动 2**：`cmd=respond` 处理空 text——当前空 text 被 skip，Phase C 后空 text 是合法的"我没回复，请 LLM 再想想"信号。改为：

```python
# 旧：if not text: return
# 新：空 text 也走 respond 流程，让 LLM 决定怎么办（可能继续思考、可能再问）
orch.respond({"text": text, "stage": orch._stage})
```

### 6.2 前端（`hagoku_web/src/`）

**改动 1**：`useWsEventHandler.ts` 处理 `USER_INPUT_REQUESTED` 时读 `expected_format`：

```typescript
case "user_input_requested": {
  const fmt = event.data?.expected_format ?? "free_text";
  setPendingAskUser({
    question: event.data.question,
    options: event.data.options ?? [],
    format: fmt,  // "choice" | "free_text" | "yes_no"
  });
  break;
}
```

**改动 2**：渲染组件分 3 种：

| `expected_format` | UI 渲染 |
|---|---|
| `choice` | 单选按钮组（用 `options`）|
| `free_text` | 输入框（提示文本 = `question`）|
| `yes_no` | 两个确认按钮（"是"/"否"）|

**改动 3**：`PipelineBar` **不变**——仍按 WS `agent_started`/`agent_completed` 事件渲染进度。

**改动 4**：`KanbanPanel` **不变**——仍 REST 拉 `kanban.db`（kanban 现在是显示对象，UI 行为不变）。

### 6.3 `route_to` 在 UI 的展示

LLM 调 `route_to(stage="cleaner", reason="字段已确认完毕")` 时，UI 应展示这个 `reason`：

```typescript
case "stage_transition": {
  appendChatTurn({
    role: "system",
    content: `→ 切换到 ${event.data.stage}：${event.data.reason}`,
    style: "transition",  // 灰色小字
  });
  break;
}
```

需 orchestrator emit `STAGE_TRANSITION` 事件（含 reason）——见 §3.3 改造里 `add_stage_transition` 调用。

---

## §7 测试改造

### 7.1 必删测试（验证旧硬编码行为）

| 文件 | 测试 | 删除原因 |
|---|---|---|
| `tests/test_product/test_*` | 任何断言 `_handle_scout_reply("确认")` → switch | 行为已改 |
| `tests/test_product/test_*` | 任何断言 `("继续",)` → cleaner | 同上 |
| `tests/test_agents/test_scout_uia_prompt.py` | 已在 Phase A 删 | N/A |

### 7.2 必加测试（验证新行为）

| 测试名 | 验证 |
|---|---|
| `test_scout_route_to_triggers_switch` | LLM 调 `route_to(stage="cleaner")` → orchestrator 切换 stage |
| `test_scout_stay_when_no_route_to` | LLM 没调 route_to → 留在 scout，等下次 respond |
| `test_ask_user_emits_pause_event` | LLM 调 `ask_user(question="..", expected_format="choice")` → 收到 `USER_INPUT_REQUESTED` 事件含 `expected_format` |
| `test_ask_user_overrides_route_to` | LLM 同时调 ask_user + route_to → ask_user 优先（先暂停问） |
| `test_keyword_confirm_no_longer_works` | 用户输入"确认" + LLM 没调 route_to → 留在当前 stage（旧行为是切下一阶段） |
| `test_kanban_block_unblock_deprecated` | agent 调 `kanban.block_task` 触发 `DeprecationWarning` |
| `test_kanban_synced_via_events` | LLM 调 ask_user → kanban 对应 task 状态变为 blocked |

### 7.3 全量 pytest 预期

Phase B 完结时 570 passed。Phase C：
- 删 ~10 个测试（硬编码确认词相关）
- 加 ~7 个测试（新行为）
- **预期 567 passed**

---

## §8 真 LLM 冒烟测试设计

### 8.1 冒烟脚本

宿主机跑：

```bash
HAGOKU_DUMP_LLM=1 python <一个能跑全流程的脚本或手动 UI 走全程>
```

### 8.2 验证点

| # | 行为 | 期望 |
|---|---|---|
| V1 | 用户说"我看完字段了，进入清洗吧" | LLM 调 `route_to(stage="cleaner", reason="...")` → 阶段切换 |
| V2 | 用户说"还有问题没确认" | LLM 留在 scout（**code 不再按"确认"二字判断**）|
| V3 | LLM 主动调 `ask_user(question="要移除 outlier 吗？", expected_format="yes_no")` | UI 弹出 "是/否" 按钮，pipeline 暂停 |
| V4 | 用户在 UI 选"是"回复 | WS cmd=respond → LLM 收到回复继续 |
| V5 | LLM 直接 `route_to(stage="reporter")` 跳过 analyst | orchestrator 切到 reporter（**不阻止跳过**）|
| V6 | LLM 不调任何工具，只输出文本 | 留在当前 stage |

### 8.3 dump 对比

跟 Phase B 同样需要改前 / 改后 dump 对比——开发者宿主机执行。

---

## §9 律的减法清单（Phase C 完成后）

| 律 / 反模式 | 当前 | Phase C 后 |
|---|---|---|
| **铁律 1（零硬编码语义）** | reply_handlers 2 处中文确认词分支违反 | **0 处违反**——硬编码全删 |
| **律 8（控制通道律 4-agent 部分）** | code 决定阶段切换 | **由 LLM `route_to` 决定** |
| **CLAUDE.md「绝对不能做」** | 已含"if-elif 中文分支判断" | 加注："Phase C 后 reply_handlers 内已无此模式" |
| **触发词速查表「if-elif 中文分支」** | 仅警告 | 改为"已由 architecture 防御" |
| **kanban.block/unblock by agent** | 10 处调用 | **0 处**——由 orchestrator 事件桥代劳 |

---

## §10 风险点 + 应对

| # | 风险 | 概率 | 影响 | 应对 |
|---|---|---|---|---|
| R1 | LLM 在 prompt 没教够时不主动调 `route_to` → 卡在 scout 死循环 | 高 | 高 | 不动 prompt（铁律 10），但**改造前先 dump 验证**：4 agent 当前 prompt 是否都已教 `route_to` 使用方法 |
| R2 | `ask_user` 升级为 4 agent 共用后，cleaner/reporter 滥用（动不动问用户）| 中 | 中 | 不强制 prompt 改；冒烟观察滥用率，必要时 Phase F 一并调 prompt |
| R3 | 删硬编码确认词后，用户习惯说"确认"以为有效 | 高 | 中 | UI 提示"请明确说明你的选择"；LLM prompt 已让它自然理解中文 |
| R4 | kanban deprecation warning 让测试输出嘈杂 | 低 | 低 | `pytest -W ignore::DeprecationWarning` 或在 conftest 配置 |
| R5 | UI 旧 `expected_format` 缺失时回退 free_text → 用户体验降级 | 低 | 低 | 兼容代码内已处理 |
| R6 | `respond({"text": ""})` 走 LLM 一遍可能引发死循环（LLM 啥都不调，handler 返 stay） | 中 | 高 | 加循环计数器：连续 3 次空回复 → emit error，**不**改 prompt 兜底 |
| R7 | `_pending_ask_user` 没被 handler 消费（pop 漏调）→ 下一轮重复 emit | 低 | 中 | handler 必须 `context.pop("_pending_ask_user", None)`；加单测 |
| R8 | route_to(stage="reporter") 跳过 cleaner/analyst → reporter 拿不到 findings | 中 | 中 | reporter prompt 已能处理"无 findings"（继承现有行为）；不在 Phase C 改 |

---

## §11 4 个 CO-C 任务的精确执行顺序

### CO-C0（预备，0.5 天）

| 子任务 | 操作 |
|---|---|
| C0-1 | 把 `~/.hagoku/llm_dumps` 备份为 `~/.hagoku/llm_dumps.before_phase_c` |
| C0-2 | 跑 `pytest tests/ -q` 确认起点 570 passed |
| C0-3 | 跑一次手动全流程冒烟（可选，但推荐）保留改前行为录像/截图 |

**Commit**：无

---

### CO-C1：工具升级（route_to + ask_user）— 0.5 天

| 子任务 | 操作 |
|---|---|
| C1-1 | `agent_tool_defs.py` 改 `route_to` description + `reason` 改为 required |
| C1-2 | `ask_user` agents 列表改为 4 个；schema 加 `expected_format`；handler 写 `context["_pending_ask_user"]` |
| C1-3 | 新加测试 `tests/test_tools/test_ask_user_pause.py`（覆盖 handler 写 context + 4 agent 可调）|
| C1-4 | 跑 `pytest tests/test_tools/ -v` |

**Commit message**：

```
[CO-C1] feat(tools): route_to reason 强制 + ask_user 升级支持暂停语义

- route_to.description 更清晰区分"切换/留下/跳过"3 种用法；reason 改 required
- ask_user 从 analyst-only 改为 4 agent 共用
- ask_user schema 新增 expected_format（choice/free_text/yes_no）
- _handle_ask_user 写 context["_pending_ask_user"] 供 orchestrator 桥接暂停事件
- 加测试覆盖 4 agent 可调 + handler 写 context

为 CO-C2/C3 反模式根除铺路。
```

---

### CO-C2：reply_handlers 删硬编码分支 + orchestrator 简化 — 1.5 天

⚠️ **本步动手前必须再次报告审核方**——铁律 -2 + brief §2.2 红线 L2。

| 子任务 | 操作 | 验证 |
|---|---|---|
| C2-1 | `_handle_scout_reply` 重写为 §3.2 形态 | `pytest tests/test_product/test_*scout*` |
| C2-2 | `_handle_cleaner_reply` 同 | `pytest tests/test_product/test_*cleaner*` |
| C2-3 | `_handle_analyst_reply` 同 | `pytest tests/test_product/test_*analyst*` |
| C2-4 | `_handle_reporter_reply` 同 | `pytest tests/test_product/test_*reporter*` |
| C2-5 | `orchestrator.respond` 简化 + `_current_stage` 注入 | `pytest tests/test_manager/ -v` |
| C2-6 | 删旧硬编码确认词测试，加 7 个新行为测试（见 §7.2）| `pytest tests/ -q` 应 567 passed |

**Commit message**：

```
[CO-C2] refactor(reply_handlers): 删硬编码确认词分支 + 阶段切换交给 LLM

删除：
- _handle_scout_reply 中"确认/好的/继续"等关键词分支（铁律 1 违规）
- _handle_cleaner_reply 中同类分支
- code 主动判断"该暂停了"的 emit USER_INPUT_REQUESTED 逻辑

改为：
- 每个 handler 收缩为 ~15 行——只检查 context["_pending_ask_user"] 和 _*_route_to
- 阶段切换完全由 LLM route_to 决定
- 暂停完全由 LLM ask_user 决定
- orchestrator.respond 删 if-elif 链，机械执行 handler 返回

测试：
- 删 10 个旧硬编码行为测试
- 加 7 个新行为测试（route_to / ask_user 路径）
- pytest tests/ → 567 passed
```

---

### CO-C3：删 agent 层 kanban block/unblock + 加事件桥 — 1 天

| 子任务 | 操作 | 验证 |
|---|---|---|
| C3-1 | scout/cleaner/reporter 各 agent.py 删 block_task / unblock_task 调用（共 10 处）| `rg -n 'block_task\|unblock_task' hagoku/agents/` → 0 |
| C3-2 | `kanban.block_task` / `unblock_task` 加 DeprecationWarning | hook 不拦（DeprecationWarning 不算违规）|
| C3-3 | `orchestrator._on_event` 加 USER_INPUT_REQUESTED → kanban.block_task 桥接 | 单测：emit USER_INPUT_REQUESTED → 对应 task 变 blocked |
| C3-4 | 加测试 `test_kanban_synced_via_events`（§7.2）| 绿 |

**Commit message**：

```
[CO-C3] refactor(kanban): agent 不再直调 block/unblock，改由 orchestrator 事件桥同步

- scout/cleaner/reporter 共 10 处 block_task/unblock_task 调用删除
- kanban.block_task/unblock_task 加 DeprecationWarning（保留方法供事件桥使用）
- orchestrator._on_event 新增 USER_INPUT_REQUESTED → kanban 同步逻辑

效果：
- kanban 完全降级为"事件消费者+UI 显示对象"
- agent 不再感知 kanban 存在
- 双权威消除（铁律 4 落实）
```

---

### CO-C4：WS + 前端适配 — 1 天

| 子任务 | 操作 | 验证 |
|---|---|---|
| C4-1 | `ws_handler._build_state_snapshot` 加 `pending_ask_user` 字段 | 单测重连恢复 |
| C4-2 | `ws_handler` cmd=respond 移除空 text skip | 单测空 text 走 LLM |
| C4-3 | `useWsEventHandler.ts` 处理 `expected_format` | 前端 build pass |
| C4-4 | 新增 `AskUserPrompt` 子组件（3 种渲染） | 手动 UI 测 |
| C4-5 | `stage_transition` 事件展示 reason | UI 截图 |

**Commit message**：

```
[CO-C4] feat(ui): ask_user 暂停按 expected_format 渲染 + stage_transition 展示 reason

后端：
- ws_handler._build_state_snapshot 重连快照含 pending_ask_user
- cmd=respond 移除空 text skip——空 text 是合法信号（"让 LLM 再想想"）

前端：
- useWsEventHandler 处理 USER_INPUT_REQUESTED 的 expected_format
- AskUserPrompt 组件按 choice/free_text/yes_no 分 3 种渲染
- stage_transition 事件渲染 LLM reason（让用户看到 AI 切换原因）

UI 透明化继续：用户看到 AI 调用 ask_user / route_to 的真实意图。
```

---

## §12 终审清单（Phase C 完成）

```markdown
# Phase C 完成汇报

## 改动统计
- 净代码减少：__ 行（预期 ~240）
- 删测试：__ 个；加测试：__ 个
- 4 个 commit 哈希：CO-C1 __, CO-C2 __, CO-C3 __, CO-C4 __

## grep 反模式（应全 0）
- reply_handlers 中文确认词分支：`rg '"确认"|"好的"|"继续"' hagoku/manager/llm_dispatch/` → __
- agent 层 block_task/unblock_task：`rg 'block_task\|unblock_task' hagoku/agents/` → __
- code 主动 emit USER_INPUT_REQUESTED：`rg 'USER_INPUT_REQUESTED' hagoku/manager/llm_dispatch/` → 应仅在 handler 检测 ask_user 后 emit，不在 code 决策路径

## 测试
pytest tests/ → ___ passed / ___ failed（预期 567 passed）

## 真 LLM 冒烟（6 个验证点）
- V1 route_to(cleaner)：__
- V2 LLM 无意切换时留下：__
- V3 ask_user 触发暂停：__
- V4 用户回复后继续：__
- V5 跳阶段（→reporter）：__
- V6 LLM 纯文本不调工具：__

## dump 对比
- 改前 dump 路径：~/.hagoku/llm_dumps.before_phase_c
- "LLM 看到信息变少"问题：__（必须"无"）

## 律的减法
- 铁律 1（零硬编码语义）：reply_handlers 内 0 违反
- 律 8 控制通道律 4-agent 部分：阶段控制权 100% 在 LLM
- agent 不感知 kanban：✓

## 风险残留
- __（如无填"无"）
```

---

## §13 不做什么（明确边界）

- ❌ 不动任何 prompt.md（铁律 10）
- ❌ 不动统计护栏 / 工具实现
- ❌ 不删 kanban.db / kanban.py（保留作 UI 显示）
- ❌ 不动 ProjectContext 核心结构
- ❌ 不引入 `done_with_stage` 新工具
- ❌ 不"顺手"做 Phase D 的 4-agent 合 1
- ❌ 不改 Meta 层基建

---

## §14 审核方对开发者的硬规则

1. 本设计稿用户已审（待定），CO-C1/C3/C4 可按本稿直接执行
2. **CO-C2（删硬编码确认词）动手前必须再次报告审核方**——铁律 -2，单独门禁
3. 任何回滚都不许 `git revert`，只能正向修复（铁律 -1）
4. 任何"我觉得"判断都不算数——必须给 grep / 测试输出做证据
5. 4 个 commit 严格独立
6. 任何超出设计稿范围的改动 → 先停下来问审核方
7. 全套测试任何 FAIL → 停下来贴 stderr
8. CO-C4 前端改动如调研发现现有架构与本稿假设不符 → 报告审核方

---

## §15 完成标准

Phase C **完成** ≡ 同时满足：

- [ ] 4 个 CO-C commit 全部合入 phase-b/c-channel-单点化（或新分支）
- [ ] §11 每步验证全绿
- [ ] §12 终审清单完整且全绿
- [ ] §8 真 LLM 冒烟 6 个验证点全过（宿主机执行）
- [ ] 律的减法清单已记录（Phase F 统一落 PROJECT.md/CLAUDE.md）
- [ ] 风险残留经审核方接受

Phase C 完成后才能开 Phase D 设计稿（**最大不可逆点**）。
