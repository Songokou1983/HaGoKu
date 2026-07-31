# 通道消息管理 — 施工规范

> **唯一准则**：Session.messages 是消息的唯一真相源。前端 messages state 通过 useConversation 方法写入，不直接暴露 setMessages。

---

## 完整数据流（当前状态，2026-08-01）

```
用户输入文字
  │
  ├─ [前端] addUserMsg(text)              ← useConversation:26 幂等写入 + persist
  ├─ [HTTP] POST /api/save_user_msg       ← server.py:85 → session.add("user", text)
  └─ [WS] send("respond", {text})
       │
       └─ ws_handler.py:442  →  ack "respond_received"
            →  asyncio.create_task(_process())   ← fire-and-forget, 不阻塞 ws_handler
                 │
                 └─ _respond_task(orch, text) → respond() → _handle_reply(text, ctx)
                      │
                      ├─ text 为空 → pop _pending_ask_user → _save_review_cards() → emit USER_INPUT_REQUESTED
                      │
                      └─ text 非空 → pop _pending_ask_user → agent.run_step(ctx, df, user_input)
                           │
                           ├─ session.to_llm_messages() → _call_llm_step → LLM
                           │    └─ 流式 delta → EventBus.STREAM_DELTA → WS → [前端] agent_stream_delta → _setMessages
                           │
                           ├─ LLM 返回 tool_calls → dispatch → session.add_tool_call()
                           │    └─ emit TOOL_EXCHANGE → WS → [前端] tool_exchange → _setMessages
                           │
                           └─ _pending_ask_user → break
                                → _handle_reply pop → _save_review_cards(ctx, ask)
                                │    ├─ session.add_workflow_card("ask_user", ...)
                                │    └─ session.add_workflow_card("field_review", ...)  ← 仅首次
                                │
                                └─ emit USER_INPUT_REQUESTED(question, field_review, ...)
                                     → WS → [前端] user_input_requested → _setMessages (cards)

WS 重连 / 项目切换
  │
  └─ build_snapshot() → session.messages (lock) → 渲染为前端格式
       │  ├─ role=workflow → fieldReview / cleaningReview / askUser 卡片
       │  ├─ role=tool → 合并为 toolExchange 卡片
       │  └─ role=assistant/user → content + tool_calls
       │
       └─ state_snapshot → WS → [前端] handleStateSnapshot
            ├─ snap.messages.length > 0 → syncFromSnapshot(ms)  ← 替换本地消息（保留本地 user）
            └─ snap.messages.length = 0 → _setMessages([])        ← ⚠️ 违规：绕过 useConversation
```

---

## 当前违规点

### 前端：20 处 `deps._setMessages` 裸调

全部在 `handlers.ts`。按替换难度分级：

**A 级：直接替换为已有方法（6 处）**

| 行 | 当前的写法 | 替换为 |
|:--:|-----------|--------|
| 67 | `_setMessages([])` （空快照清空） | `deps.clearMessages()` |
| 87 | `_setMessages([])` （项目删除清空） | `deps.clearMessages()` |
| 212 | `_setMessages(prev => prev.map(...streaming:false))` | `deps.endStream()` |
| 332 | `_setMessages(prev => [...prev, {role:"agent", text:agentMsg}])` | `deps.addAgentMsg(agentMsg, d.timestamp)` |
| 357 | `_setMessages(prev => [...prev, {role:"system", text:line}])` | `deps.addSystemMsg(line, d.timestamp)` |
| 360,362 | 同上 | 同上 |

**B 级：替换为 addWorkflowCard / updateWorkflowCard（8 处）**

| 行 | 内容 | 替换为 |
|:--:|------|--------|
| 253 | askUser 卡片创建 | `deps.addWorkflowCard({ askUser: {question, expected_format, options}, timestamp })` |
| 262 | field_review 原地更新 | `deps.updateWorkflowCard(deps.activeFieldReviewId, { fieldReview: fr, timestamp })` |
| 266 | field_review 卡片创建 | `deps.addWorkflowCard({ id: wfId, fieldReview: fr, timestamp })` |
| 287 | cleaning_review 原地更新 | `deps.updateWorkflowCard(deps.activeCleaningReviewId, { cleaningReview: cr, timestamp })` |
| 291 | cleaning_review 卡片创建 | `deps.addWorkflowCard({ id: cid, cleaningReview: cr, timestamp })` |
| 309 | analyst_review 原地更新 | `deps.updateWorkflowCard(deps.activeAnalystReviewId, { analystReview: ar, timestamp })` |
| 313 | analyst_review 卡片创建 | `deps.addWorkflowCard({ id: aid, analystReview: ar, timestamp })` |
| 325 | gate prompt 卡片 | `deps.addWorkflowCard({ text: prompt, timestamp })` |

**C 级：需要扩展 useConversation 方法（4 处）**

| 行 | 内容 | 需要的扩展 |
|:--:|------|-----------|
| 173 | tool_exchange 卡片（role="agent" + toolExchange） | 新增 `addToolExchangeCard()` 或使用 `addRawMsg` |
| 197-205 | agent_stream_delta（streamId 搜索 + 追加） | `addAgentMsg` 加 `streamId` 参数 |
| 273 | message 文本（role="workflow"） | 可用 `addSystemMsg(msgText, timestamp)` — 但当前 role 是 workflow 不是 system |
| 303 | cleaning_assessment（role="agent" + html table） | `addAgentMsg` 加可选 `html` 字段 |

**D 级：暴露给外部（2 处）**

| 位置 | 违规 |
|:--:|------|
| `useConversation.ts:132` | `_setMessages: setMessages` 暴露给所有调用方 |
| `types.ts:132` | `_setMessages` 是 `WsEventDeps` 的正式类型成员 |

---

## 施工顺序

### 第一轮：A 级 + B 级（14 处，直接替换）

**改动**：逐条替换为上表中的 useConversation 方法。

**验证**：
```bash
# 施工后 grep，预期只剩 C 级 4 处 + useConversation 内部的 setMessages
grep -n '_setMessages' hagoku_web/src/panels/AnalyzePanel/hooks/handlers.ts
npx tsc --noEmit
```

---

### 第二轮：C 级（4 处，需扩展方法）

**2a. `addAgentMsg` 加 `streamId` 参数**

当前签名：`(text: string, timestamp?: string)`

扩展为：`(text: string, timestamp?: string, opts?: { streamId?: string })`

逻辑：如果 `streamId` 存在，从后往前搜同 streamId 的 streaming 消息并追加；否则保持现有行为（追加到最后一条 agent 消息或新建）。

handlers.ts:197-205 替换为：`deps.addAgentMsg(delta, d.timestamp, { streamId })`

**2b. `addAgentMsg` 加 `html` 字段**

handlers.ts:303 的 cleaning_assessment 需要渲染 HTML 表格。当前 `addAgentMsg` 只接受 text。

扩展 `ConvoMessage` 类型（如果尚未有 html 字段）和 `addAgentMsg` 签名，支持可选的 `html` 字符串。

**2c. tool_exchange 卡片（行 173）**

两种方案：
- A：新增 `addToolExchangeCard(data)` 方法到 useConversation
- B：用现有的 `addRawMsg` 直接传完整消息对象

推荐 A——tool_exchange 是一个明确的消息类型，应该有对应方法。但它是 agent 消息的子类型，可以复用 `addAgentMsg` 加一个 `toolExchange` 参数。

**2d. message 文本卡片（行 273）**

当前是用 `role: "workflow"` 创建的纯文本卡片。`addSystemMsg` 用 `role: "system"`。区别仅在于 role 名，前端渲染逻辑可能依赖 role 做样式区分。需确认后决定：统一为 system role 还是 preserved workflow role。

---

### 第三轮：删 `_setMessages` 暴露

**条件**：前两轮完成后，handlers.ts 中 `_setMessages` 调用归零。

1. `useConversation.ts:132` — 删除 `_setMessages: setMessages`
2. `types.ts:132` — 删除 `_setMessages` 类型
3. `AnalyzePanel.tsx:105` — 解构中删除 `_setMessages`
4. `AnalyzePanel.tsx:158` — deps 中删除 `_setMessages`

**验证**：
```bash
grep '_setMessages' hagoku_web/src/panels/AnalyzePanel/types.ts          # → 0
grep '_setMessages:' hagoku_web/src/panels/AnalyzePanel/hooks/useConversation.ts  # → 0
grep '_setMessages' hagoku_web/src/panels/AnalyzePanel.tsx               # → 0
grep 'deps\._setMessages' hagoku_web/src/panels/AnalyzePanel/hooks/handlers.ts  # → 0
npx tsc --noEmit
npx vitest run
```

---

## 验收（每轮结束后执行）

| # | 检查 | 命令 |
|---|------|------|
| 1 | TS 编译 | `npx tsc --noEmit` → 零错误 |
| 2 | 前端测试 | `npx vitest run` → 全绿 |
| 3 | 后端测试 | `pytest tests/` → 全绿 |
| 4 | 手动：正常分析 | 消息不重复、不丢失 |
| 5 | 手动：关闭重开 | 对话完整恢复，卡片位置正确 |
| 6 | 手动：清除历史 | 无旧数据残留 |
| 7 | 手动：项目切换 | 无跨项目数据污染 |

---

## 施工前自检（grep = 停）

```bash
# 1. 新增 _setMessages 调用？
grep -n '_setMessages' hagoku_web/src/panels/AnalyzePanel/hooks/handlers.ts

# 2. 新增 session.add() 调用？
grep -rn 'session\.add(' hagoku/ --include='*.py' | grep -v 'add_tool_call\|add_workflow_card'

# 3. 新增 setMessages 暴露？
grep -n '_setMessages:' hagoku_web/src/panels/AnalyzePanel/hooks/useConversation.ts

# 4. WsEventDeps 中有 _setMessages？
grep -n '_setMessages' hagoku_web/src/panels/AnalyzePanel/types.ts

# 5. 新增 localStorage.setItem 写对话数据？
grep -rn 'localStorage\.setItem.*hagoku' hagoku_web/src/ --include='*.ts' --include='*.tsx'
```

---

## 参考：后端现状（本轮不施工）

后端 Session 的写入路径和 `build_snapshot` 的渲染逻辑已经正确：

- `Session` 类有 `threading.Lock`（`session.py:36`），所有写方法和 `to_llm_messages` 获取锁
- `build_snapshot()` 读 `session.messages` 时获取锁（`app.py:170`）
- workflow 卡片通过 `add_workflow_card()` 存入 Session，`to_llm_messages()` 过滤掉（`session.py:97`）
- `build_snapshot()` 将 workflow 渲染为前端卡片格式（`app.py:181-193`）

待后端统一的事项（可延后）：
- `save_msg`（`ws_handler.py:440`）和 HTTP `save_user_msg`（`server.py:85`）是用户消息的两个写入点 → 可以合并
- `_save_review_cards` 写入时机是 emit USER_INPUT_REQUESTED 之前 → 如果写入和 emit 之间崩溃，前端收到事件但 Session 没有卡片

> 这些问题不影响当前施工（前端统一入口），记录在此供后续审计。
