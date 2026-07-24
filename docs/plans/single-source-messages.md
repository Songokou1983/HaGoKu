# 通道消息状态管理 —— 架构文档与经验总录

> 本文档记录 HaGoKu 通道消息模块从 v0.1 至今的全部架构演进、历史错误、经验教训、以及当前重构方案。
> 每次改动此模块前必须读本文档。

---

## 一、模块定位

通道消息状态管理负责：

- **前端**：对话消息 `ConvoMessage[]` 的创建、更新、持久化
- **后端**：`Session.messages` 的读写、snapshot 构建、LLM 上下文构造
- **桥接**：WS 事件 → 前端渲染、snapshot → 前端恢复

该模块是"用户看到什么"的最后一道关卡。错误直接影响用户对 LLM 输出完整性的感知。

---

## 二、架构演进历史

### Phase 1：多写入点各自为政（v0.1 ~ v2.2）

**架构**：
```
前端消息来源：
  ├── localStorage（持久化缓存）
  ├── state_snapshot（WS 重连恢复）
  ├── WS 事件流（agent_stream_delta、user_input_requested、tool_exchange）
  └── 用户操作（submitUserReply）

四个来源各自调用 setMessages，互不知晓。
```

**已知问题**：
- 用户消息 ×2（`019fcc9` 修复 respond 双重写）
- snapshot 覆盖本地消息（`87afcdc` 修复为保留本地）
- 后续又改为全量覆盖（`6ea2ef9` "后端 session 唯一真相源"）
- 消息重复反复出现（`493ca01`、`22b3e5f` 多次去重修复）
- 对话历史截断（`0f77208` 取消 50 条限制）

**教训**：
> 补丁思维：同一问题反复出现 → 加代码堵。四个数据源各存各的，没有单一真相源。每个堵一个出口，永远堵不完。（CHANNEL.md 反模式 7）

### Phase 2：session 为唯一真相源（v2.3 ~ 至今）

**架构变更**（`6ea2ef9`）：
- 前端不再独立维护消息 → snapshot 全量覆盖
- localStorage 仅首屏加速，不参与状态管理
- HTTP POST 落盘独立于 WS，消息不丢
- 前端 persist 同步写替代 useEffect 异步写

**残留问题**：
- snapshot 替换消息和后续卡片追加分离执行，中间可被 live 事件穿插
- 8 个 `setMessages` 写入点各自追加，无统一幂等

### Phase 3：本次重构（当前方案）

关闭 `useConversation` 对外的 `setMessages`，只保留幂等方法。所有写入经过唯一入口。

---

## 三、当前架构全景（改前）

### 3.1 写入点清单

| # | 函数 | 触发时机 | 写入方式 |
|---|------|---------|---------|
| 1 | `handleStateSnapshot:L52` | WS 连接/重连 | `setMessages(snapMsgs)` 全量替换 |
| 2 | `handleStateSnapshot:L75` | snapshot 含 field_review | `setMessages([...prev, card])` 追加 |
| 3 | `handleStateSnapshot:L86` | snapshot 含 cleaning_review | 同上 |
| 4 | `handleStateSnapshot:L96` | snapshot 含 analyst_message | 同上 |
| 5 | `handleEvent:L286` | user_input_requested (askUser) | 同上 |
| 6 | `handleEvent:L294` | user_input_requested (field_review) | 同上 |
| 7 | `handleEvent:L230` | agent_stream_delta | 同上/原地更新 |
| 8 | 用户操作 | 发送消息 | `addUserMsg` |

### 3.2 典型错误路径

**askUser 重复（2026-07-24 发现）**：

```
snapshot 到达 → setMessages(snapMsgs)     // 替换
            → setMessages([...prev, ask]) // 追加（来自 snap.pending_ask_user）
WS 事件到达 → setMessages([...prev, ask]) // 再追加（来自 live 事件）
WS 重连    → 以上重复
= 用户看到 3-4 条相同的 askUser 卡片
```

**字段表新旧混搭（2026-07-24 发现）**：

```
分析 A 完成 → context.column_semantics 残留
清除历史   → cancel_analysis，context 不清
分析 B 启动 → snapshot 带旧 column_semantics → 渲染旧表
LLM 输出新表 → user_input_requested 带新表 → 追加新表
= 新旧两张字段表混在一起
```

**工具结果重复 5 条（2026-07-24 发现）**：

```
LLM 调 4 次 trend_decomposition → 4 次返回同一结果
add_tool_call 原样存储 4 条 tool 消息
LLM 下次看到 4 条相同结果 → 上下文膨胀 → 行为异常
```

---

## 四、本次重构方案

### 4.1 核心原则

> 消息数组只有一个主人。外部代码不直接碰 messages state。

### 4.2 新接口

```
addUserMsg(text)          → 追加 user 消息，同文本不重复
addSystemMsg(text)        → 追加 system 消息，同文本不重复
addAgentMsg(text, html?)  → 流式追加，非流式幂等
addWorkflowCard(card)     → 同类型同内容跳过
  card: { fieldReview?, cleaningReview?, analystReview?, askUser? }
updateWorkflowCard(id, u) → 原地更新
syncFromSnapshot(snap)    → 对比合并
clear()                   → 清空
```

不对外暴露 `setMessages`。

### 4.3 幂等规则

```
addUserMsg / addSystemMsg：
  上一条同 role + 同 text → 跳过

addAgentMsg：
  上一条是 agent 且无 tool_calls → 追加到上一条 text
  否则同 addUserMsg

addWorkflowCard：
  fieldReview 已存在 → 跳过
  cleaningReview 已存在 → 跳过
  analystReview 已存在 → 跳过
  askUser 同 question → 跳过

syncFromSnapshot(snap)：
  以 snap.messages 为基准
  本地独有且 role==="user" 且 timestamp 比 snapshot 新 → 保留
  其他本地独有 → 删除
```

### 4.4 改动文件

| 文件 | 改动 |
|------|------|
| `useConversation.ts` | +syncFromSnapshot、封闭 setMessages、所有方法加幂等 |
| `handlers.ts` | 全部 setMessages 替换为方法调用 |
| `types.ts` | WsEventDeps 删除 setMessages |
| `AnalyzePanel.tsx` | deps 传方法 |
| `useAnalyzeSession.ts` | 去 setMessages 参数 |

### 4.5 风险管理

| 风险 | 缓解 |
|------|------|
| 功能回退 | 每次 commit 前跑全量测试 |
| 遗漏调用点 | grep setMessages 确认全覆盖后删类型 |
| 流式消息丢失 | addAgentMsg 保留流式追加逻辑 |
| 性能 | 幂等检查 O(n)，n<200 可忽略 |

---

## 五、历史经验总录

以下经验来自 CHANNEL.md、CLAUDE.md、以及本次审查的全部发现。

### 经验 1：数据源越多，去重越难（v0.1~至今）

四个数据源各自写 → 补丁堵 → 又出现 → 再堵。直到"session 为唯一真相源"才根治。

**提炼**：单一真相源 > N 个同步机制。

### 经验 2：不看 dump 就改代码 = 猜（2026-06-25）

每个 bug 修了 5 次才找到根因。dump 是 LLM 行为的事实依据。

**提炼**：先看 dump 再说话。铁律 0。

### 经验 3：代码替 LLM 做判断永远会错（2026-06-25）

加映射表"代码猜阶段"→ 一天后炸回来。加 had_tools"代码猜 LLM 在说话"→ 也错了。

**提炼**：问自己——这个判断 LLM 能不能自己做？能 → 改 prompt，不能 → 写代码。

### 经验 4：补丁链的致命性（2026-06-25）

不出表 → 改循环上限 → 一路到底 → 拆循环 → 卡住 → 撤回。9 个 commit，2 个撤回。

**提炼**：修 bug 前先找根因。症状不是根因。

### 经验 5：数据多存储 = 必然不一致（2026-07-16）

前端 messages、localStorage、后端 session 三处各存 → 补丁堵了 6 小时。

**提炼**：同一问题反复出现 → 先问架构。改结构 > 加代码。

### 经验 6：pop 后存回 = 自己炸自己（2026-07-24）

`_pending_ask_user` pop 后又存回 → 下次 respond 再触发 → 死循环。

**提炼**：副作用不能藏着。pop 就是删，存就是留。不能两样都做。

### 经验 7：流结束存盘，不止一处（2026-07-24）

`session.add` 三个地方：流结束、batch 结束、add_tool_call。message 同一个内容可能来自不同入口。

**提炼**：一个 LLM 回复对应一个 session 写入点。不是三个点都用同一份 txt。

### 经验 8：snapshot 补全不能只看缺什么（2026-07-24）

补 field_review → 忘了同项目检查 → 旧数据混入新分析。补 report_url → 忘了 session 为空时不生成。

**提炼**：补数据要思考"什么时候这个数据不该存在"。补 = 加条件，不是裸加字段。

### 经验 9：幂等应该在最外层（2026-07-24）

在 handlers.ts 加去重 → 堵了一个入口，其他入口还能绕过。在 useConversation 加去重 → 全堵。

**提炼**：约束放在离数据最近的地方。入口层约束 > 调用层约束。

---

## 六、验收标准

| 场景 | 预期 |
|------|------|
| 正常分析全程 | 消息不重复、不丢失 |
| 分析中关闭重开 | 对话完整恢复，无重复卡片 |
| 清除历史后新分析 | 无旧数据残留 |
| 新建项目 | 无其他项目数据 |
| ask_user 暂停/回复 | 卡片出现一次，回复后消失 |
| 流式输出 | delta 正常追加，不产生重复 agent 消息 |
| 全量测试 | `pytest tests/` + `npx vitest run` 全绿 |
| setMessages 外部调用 | grep 结果为 0 |

---

## 七、分阶段实施计划

### 第一阶段：useConversation 封闭（1 次 commit）

**目标**：useConversation 不再对外暴露 `setMessages`，所有写入通过幂等方法。

**改动**：
- `useConversation.ts`：+syncFromSnapshot、+幂等逻辑、-暴露 setMessages
- 每个方法内部加幂等，不改变方法签名和调用方

**验证**：`npx tsc --noEmit` 编译通过。若有调用方引用 `setMessages`，编译报错 → 定位并替换。

**回退**：git revert 单 commit。

---

### 第二阶段：handlers.ts 迁移（1 次 commit）

**目标**：handlers.ts 中所有裸 `setMessages` 替换为 useConversation 方法。

**改动**：
- `handleStateSnapshot`：`setMessages(snapMsgs)` → `syncFromSnapshot(snap)`
- 分离的 workflow 卡片追加 → 已在第一阶段并入 syncFromSnapshot
- `user_input_requested`（askUser/fieldReview/cleaningReview/analystReview）→ `addWorkflowCard(card)`
- `agent_stream_delta`：保留流式追加逻辑，改用 `addAgentMsg(delta)`
- `agent_failed` / `run_completed` → `addSystemMsg(text)`

**验证**：`grep 'setMessages' handlers.ts` 返回 0。

**回退**：git revert 单 commit。

---

### 第三阶段：类型系统清理（1 次 commit）

**目标**：删除 `WsEventDeps.setMessages`，前端不再有任何直接写入 messages 的路径。

**改动**：
- `types.ts`：删除 `setMessages` 类型定义
- `useAnalyzeSession.ts`：删除 `setMessages` 参数和透传
- `AnalyzePanel.tsx`：deps 中去掉 `setMessages`，传入 useConversation 方法引用
- 编译确认无残留引用

**验证**：`npx tsc --noEmit` 零错误。`grep 'setMessages' src/` 仅 useConversation 内部出现。

**回退**：git revert。

---

### 第四阶段：全量测试 + 验收（最后 commit）

**目标**：确认功能无回退。

**步骤**：
1. `pytest tests/` 全量通过
2. `npx vitest run` 全量通过
3. 手动测试场景（正常分析、关闭重开、清除历史、新建项目、ask_user 暂停恢复）

**验收**：6 个场景全部符合预期。

---

### 总改动量估算

| 阶段 | 文件数 | 增删行 |
|------|--------|--------|
| 一 | 1 | +30 |
| 二 | 1 | -50/+20 |
| 三 | 3 | -10/+5 |
| 四 | 0 | 0 |
| **合计** | **5** | **~45 行净增** |

每个阶段独立 commit，可独立 revert。阶段之间不相互依赖编译——每阶段结束后代码处于可编译可运行状态。

---

## 八、后端统一（Phase 2）

### 8.1 当前问题

后端有三套独立的数据流构建机制，各自向同一个前端推送：

```
Session.add() ──→ EventBus ──→ user_input_requested 事件
                        ├──→ agent_stream_delta 事件
                        └──→ tool_exchange 事件

build_snapshot() ──→ state_snapshot ──→ 全量覆盖
```

三套数据的格式不同：
- Event 数据：`{ event_type, agent, data: { question, options, ... } }`
- Snapshot 数据：`{ project_name, query, messages, field_review, pending_ask_user, ... }`
- Session 数据：`{ analysis_goal, messages: [{ role, content, tool_calls, ... }] }`

前端需要理解三种不同的数据格式，各自用不同的路径写进消息数组。这是为什么总有重复的根源——不是前端没做去重，是三个生产者各自发送重叠的数据。

### 8.2 目标架构

```
Session（唯一真相源）
    │
    ├──→ to_llm_messages()        LLM 上下文
    │
    ├──→ to_frontend_snapshot()   全量快照（格式和事件统一）
    │
    └──→ on_change() ──→ EventBus 变更通知（不携带数据，前端自行拉取）
```

后端只对外暴露一个数据源：Session。事件不再携带数据——只通知"Session 变了"。前端收到通知后主动从 snapshot 获取最新状态。

### 8.3 分阶段

**第五阶段：Snapshot 与事件格式统一**

- `build_snapshot()` 输出格式与 `user_input_requested` 等事件格式对齐
- 前端 `syncFromSnapshot` 可以处理两种数据

**第六阶段：事件瘦身**

- `EventBus.emit` 事件不再携带 data payload
- 事件变为纯通知：`{ type: "session_changed" }`
- 前端收到通知 → 通过 WS 请求最新 snapshot → `syncFromSnapshot`

**第七阶段：Session 统一写入**

- 所有状态变更（field_review、cleaning_review、report_url）只写入 Session
- Event 和 snapshot 都从 Session 派生，不做二次计算

### 8.4 总改动量估算

| 阶段 | 后端文件 | 前端文件 | 增删行 |
|------|---------|---------|--------|
| 五 | 3 | 1 | ~30 |
| 六 | 2 | 2 | ~-40/+20 |
| 七 | 4 | 0 | ~20 |
| **合计** | **9** | **3** | **~30 行净增** |

### 8.5 整体架构图（Phase 1 + Phase 2 全貌）

```
┌─────────────────────────────────────────────────┐
│                    后端                          │
│                                                 │
│  Session ──→ to_frontend_snapshot() ──┐         │
│     │                                  │         │
│     └──→ on_change() → EventBus ──→ WS ──→ 前端 │
│                                                 │
└─────────────────────────────────────────────────┘
                                                    │
┌───────────────────────────────────────────────────┘
│
│  ┌──────────────────────────────────────┐
│  │              前端                     │
│  │                                      │
│  │  useConversation                     │
│  │  ├── syncFromSnapshot(snap)          │
│  │  ├── addAgentMsg(delta)              │
│  │  ├── addUserMsg(text)                │
│  │  ├── addSystemMsg(text)              │
│  │  ├── addWorkflowCard(card)           │
│  │  └── updateWorkflowCard(id, updates) │
│  │                                      │
│  │  全部幂等，setMessages 不对外暴露      │
│  └──────────────────────────────────────┘
│
│  handlers.ts → 只调用 useConversation 方法
│  ConvoFeed → 只读 messages
│
└──────────────────────────────────────────────
```

---

## 九、2026-07-24 首次实现教训

### 问题：关闭重开后前端恢复的不是关闭前看到的内容

**根因**：`7aa88ba` 重构 `app.py:build_snapshot()` 为后端预渲染格式（tool 消息 → toolExchange 卡片），但 **`ws_handler.py:_build_state_snapshot()` 没有被同步更新**。两套 snapshot 格式同时存在，同一份 session.json 数据经过两条不同的流水线，产出两份不同的前端视图。

**核心教训**：snapshot 的重建逻辑必须是**唯一的**。只要存在两个 snapshot 构建路径，它们就会在某个时刻分歧。

### 问题：输入框被顶到屏幕顶部

**根因**：`4d32207` 尝试用 `min-h-0` 修复 flex-1 不生效，但 `min-h-0` 在消息为空时让 ConvoFeed 塌缩为 0 高度。

**修复**：`min-h-0` → `min-h-[120px]`，确保 ConvoFeed 即使无消息也有保底高度。真正的根因是消息为空——这通常由 snapshot 格式不一致导致。

### 问题：roleMap 缺少 "agent" → 工具卡片被标为 system

**根因**：`7aa88ba` 的后端渲染中，toolExchange 卡片使用 `role: "agent"`，但前端 `roleMap` 只有 `user/assistant/tool` 三个映射。

**修复**：`roleMap` 增加 `agent: "agent"` 映射。

### 修复清单（2026-07-24）

| 修复 | 位置 | 说明 |
|------|------|------|
| 删除 `_build_state_snapshot` | `ws_handler.py` | 重复代码，统一走 `app.build_snapshot()` |
| 删除语义默认值 `"—"` | `app.py:_build_field_review` | 铁律 1：LLM 没给的值代码不准填 |
| ConvoFeed `min-h-0` → `min-h-[120px]` | `ConvoFeed.tsx` | 防止空消息时塌缩 |
| `roleMap` 加 `agent: "agent"` | `AnalyzePanel.tsx` | 工具卡片 role 正确 |
| 删除僵尸测试 | `test_doctrine_fix_f038.py` | 引用了不存在的 `hagoku.tools.business` |
| `_build_field_review` 加 session 检查 | `app.py` | 清历史后不残留旧 field_review |
