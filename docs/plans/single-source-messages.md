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

## 九、2026-07-24 通道重构全记录

### 9.1 问题全景

当天从"inputSnapshot 重构"开始，逐步发现了五个层次的问题。前三个是补丁思维造成的直接 bug，后两个是架构层面的通道分裂。

---

### 9.2 发现一：useEffect 死循环

**现象**：`syncFromSnapshot` 无限调用，`[snapshot] sync msgs=42` 每秒刷屏多次。

**根因**：`AnalyzePanel.tsx:144` useEffect 依赖数组写了 `[currentProject, syncFromSnapshot]`。`syncFromSnapshot` 每次渲染都是新引用 → 触发 effect → fetch snapshot → setMessages → 重新渲染 → 新引用 → 死循环。

**修复**：删掉 `syncFromSnapshot` 依赖，改为 `[currentProject]`。snapshot 只在项目切换时拉取。

**教训**：useEffect 依赖数组里不能放内联函数。要么用 useCallback 稳定引用，要么不依赖它。

---

### 9.3 发现二：a44d494——工具调用后 LLM 返回空

**现象**：LLM 调完工具后不输出结果，系统直接发 `USER_INPUT_REQUESTED` 等用户输入。

**根因链**：

```
a44d494 (防重复补丁)
  → _call_llm_step: if session and txt and NOT final_tool_calls_raw
  → LLM 返回 text+tool_calls 时，text 不存盘
  → 等 add_tool_call 补存 → 时机在工具调度之后
  → 如果工具调度出问题，text 永远丢失

6e3bded (事件瘦身)
  → _handle_reply: pop _pending_ask_user 后立刻存回
  → 信号永不消失 → run_step 每轮直接 break
  → 工具调度后 LLM 根本不会被调
```

**两重 bug 叠加**：
1. `_pending_ask_user` 永不消失 → 工具循环直接 break（`6e3bded` 引入）
2. text 存盘时机太晚 → 即使循环跑了，LLM 也可能看不到自己的输出（`a44d494` 引入）

**修复**：
- `_pending_ask_user`：pop 后不再存回；用户回复时主动清一次残留
- `_call_llm_step`：纯函数化，不写 session；session 写入全集中在 `run_step`
- `run_step`：先存 assistant(txt+tool_calls) → 再调度工具 → 再存 tool 结果

**教训**：补丁互相踩踏。两个独立的"优化"（防重复 + 事件瘦身）各自引入 bug，组合起来直接把工具循环废了。

---

### 9.4 发现三：清除历史不生效

**现象**：点击"清除历史"前端清空了，但重启后数据全部恢复。

**根因链**：

```
1. clear-history API 参数 request 缺类型注解 → FastAPI 当成 query param → 422 错误
2. 前端 .catch(() => {}) 静默吞错误 → 用户看不到报错
3. ClearHistoryButton 先调 onClear() → cancel_analysis → save_state() 写 runs/
   再调 fetch(clear-history) → rm -rf runs/
   → save_state 比 rm 慢时，runs/ 被重建
```

**修复**：
- API: `request` → `request: Request`
- 前端: 先 fetch API → 再 onClear（`.then/.catch` 都调）
- 后端: `orch._session = None` + `orch._df_raw/df_clean = None` + `project.json` 重置 current_run_id

**教训**：竞态条件 + 静默吞错 = 用户看到的和实际发生的完全不同。

---

### 9.5 发现四：输入框位置靠内容撑

**现象**：`4d32207` 加 `min-h-0` 想让 flex-1 生效，反而让空 ConvoFeed 塌缩为 0，输入框跑到顶部。

**根本问题**：布局设计从第一天就错了。输入框用 `flex-1` 靠内容撑位置，而不是用绝对定位/Grid 保证位置。

**修复**：输入框改为 `absolute bottom-0`，对话区 `absolute inset-0 overflow-y-auto pb-[100px]`。位置由布局保证，与内容无关。

**教训**：其他 IDE（VS Code、ChatGPT）的输入框都是绝对定位。flex 布局中 `flex-1` 的语义是"分配剩余空间"不是"占满剩余空间"——内容为空就给 0。

---

### 9.6 发现五：review 卡片双通道——本次重构的核心问题

**现象**：
- 重启后 field_review 表格挂在消息列表最底部（位置错）
- 重复重启会重复追加（累积）
- live 分析中 review 卡片从未显示（`6e3bded` 清空事件数据后两端都断了）

**根因**：review 卡片（field_review / cleaning_review / ask_user）和对话消息走**两条独立通道**：

```
通道 A：Session.messages → snapshot.messages → syncFromSnapshot → 对话消息
通道 B：context.column_semantics → snapshot.field_review → addWorkflowCard → 卡片
```

两条通道的数据各自序列化、各自恢复，前端各自处理。位置永远对不齐。

**架构修复**：合并为一条通道——Session.messages。

```
Session.messages（唯一真相源）
  ├── user / assistant / tool 消息    ← LLM 需要的
  ├── workflow 消息（field_review 等）  ← 前端 UI 需要的
  │
  ├── to_llm_messages()  → 过滤 workflow → 给 LLM
  └── build_snapshot()   → 全量透传 → 给前端 syncFromSnapshot
```

**具体改动**：
1. `Session.add_workflow_card()` — workflow 消息存入 messages
2. `to_llm_messages()` — 过滤 role="workflow"
3. `build_snapshot()` — workflow 消息渲染为前端格式，含在 messages 中
4. `reply_handlers._save_review_cards()` — 暂停时从 context 构建并写入 Session
5. 前端删除独立的 `addWorkflowCard` 调用，`syncFromSnapshot` 自然恢复
6. 删除 `app._build_field_review`（逻辑移到 `_save_review_cards`）

**效果**：
- 重启后：snapshot.messages 含 workflow 卡片 → syncFromSnapshot → 自然在正确位置
- live：LLM 暂停 → `_save_review_cards` 写入 Session → `build_snapshot` 透传
- `addWorkflowCard` 去重逻辑不再需要（来源唯一）

**教训**：只要存在两条通道，它们就会在某个时刻分歧。补丁（去重、位置修复、条件互斥）永远补不完。合并通道是唯一的根治方案。

---

### 9.7 补丁链全景

| 补丁 | 试图解决的问题 | 引入的新问题 |
|------|--------------|------------|
| `a44d494` 加 `not final_tool_calls_raw` | 防重复 assistant 消息 | text 存盘时机太晚 |
| `6e3bded` 事件不带数据 | 统一数据源 | `_pending_ask_user` 永不消失 |
| `fab9c7c` 删 snapshot review 卡片 | 重复追加 | live 卡片也断了 |
| `4d32207` 加 `min-h-0` | flex-1 不生效 | 空内容塌缩 |

四条补丁链最终都指向同一个根因：**数据有多个源头，各自独立处理。** 补丁在源头上互相踩踏。

### 9.8 最终架构

```
Session.messages  ← 唯一真相源
    │
    ├── add()              user / assistant / tool
    ├── add_tool_call()    assistant(txt+tool_calls) + tool results
    ├── add_workflow_card() field_review / ask_user / cleaning_review
    │
    ├── to_llm_messages()  → 过滤 workflow → 给 LLM
    └── build_snapshot()   → 全量渲染 → 给前端

run_step: 唯一 session 写入编排者
    _call_llm_step → 纯函数（不写 session）
    session 写入顺序: add_tool_call(txt,calls,[]) → dispatch → add("tool",result)

---

## 十、通道全量审计与字典（2026-07-24 全面审计）

> 本章是对全部 8 条数据流的完整边界分析，覆盖正常路径、异常点、不完整状态、并发风险。
> 每条风险都有修复方案、深度评估、测试要求。这是通道的"字典"——遇到任何边界问题时先查本章。

### 10.1 审计范围

| 数据流 | 入口 | 出口 | 涉及文件 |
|--------|------|------|---------|
| 1. 分析启动 | `analyze` WS 命令 | `run_scout_phase` 完成 | ws_handler, orchestrator, agent |
| 2. 用户回复 | `respond` WS 命令 | `run_step` → 前端 ack | ws_handler, reply_handlers, agent |
| 3. 消息落盘 | `save_msg` WS 命令 | session.json | ws_handler, session |
| 4. 分析取消 | `cancel_analysis` WS 命令 | context 清除 | ws_handler, orchestrator |
| 5. 回复取消 | `cancel_respond` WS 命令 | `_respond_cancelled` 标志 | ws_handler, orchestrator |
| 6. 快照构建 | WS 重连 / switch_project | snapshot dict | app, session |
| 7. 持久化恢复 | 进程重启 | 状态重建 | session, orchestrator, app |
| 8. LLM 交互 | `_call_llm_step` | 流/batch 响应 | agent |

### 10.2 全量风险登记（按严重度排序）

#### 🔴 高风险（4 项）

##### R1：LLM 纯文本响应不入 Session

- **现状**：`run_step` 工具循环 `if not tc_list: break` 直接跳出，`txt` 不写入 Session
- **影响**：重启后 LLM 所有纯文本回复丢失。对话历史在工具调用之间出现空白
- **触发条件**：LLM 任何一次不调工具的回复
- **修复**：break 前加 `if session: session.add("assistant", txt)`
- **位置**：`agent.py:564` 和 `agent.py:568`（第一轮和工具轮后两处）
- **注意**：`txt` 可能为空字符串（LLM 返回空）。空文本不入 Session（符合 `add()` 语义）
- **测试**：模拟 LLM 返回纯文本 → 验证 session.messages 最后一条是 assistant

##### R2：`cancel_respond` 在流式输出时无效

- **现状**：`_respond_cancelled` 只在 `run_step` 工具循环检查（`agent.py:642`）。`_call_llm_step` 的流式 for 循环不检查
- **影响**：LLM 流式输出长文本时点击停止无反应
- **触发条件**：LLM 正在输出纯文本（无 tool_calls），用户点停止
- **修复**：`_call_llm_step` 流式循环内检查 `is_respond_cancelled()`，取消时提前结束
- **位置**：`agent.py:_call_llm_step` 流式 for 循环内
- **注意**：取消时 `txt` 是已收到的部分文本，`tc_list` 未形成。这是预期行为——用户看到的就是已输出的内容
- **测试**：模拟长流式输出 + 中途调 `request_cancel_respond()` → 验证循环提前退出 + `tc_list` 为 None

##### R3：`save_msg` 和 `respond` 分离导致用户消息可能丢失

- **现状**：前端先发 `save_msg` 写用户消息到 Session，再发 `respond` 调 LLM。如果 `save_msg` 时 orchestrator 为 None，消息静默丢失
- **影响**：重启后对话历史缺失用户消息，LLM 上下文不完整
- **触发条件**：前端 WS 重连期间快速发消息（orch 尚未创建）、或 `save_msg` 本身因任何原因跳过
- **修复**：`_handle_reply` 兜底写入用户消息。幂等检查：最后一条不是同内容 user 消息才写
- **位置**：`reply_handlers.py:_handle_reply` 用户回复分支
- **注意**：`save_msg` 保留不删（兼容性）。幂等检查避免×2 重复
- **测试**：模拟 `save_msg` 跳过（不调 orch）→ `_handle_reply` 兜底写入 → 验证 session 有且只有一条 user 消息

##### R4：Session 写入无锁

- **现状**：`add()` / `add_tool_call()` / `add_workflow_card()` 被不同线程调用。事件循环线程（`save_msg`）和 executor 线程（`run_step`）并发写 `session.messages`
- **影响**：并发写可能丢数据。`_maybe_save` 的 `tmp + os.replace` 在多线程下可能覆盖
- **触发条件**：`save_msg` 和 `respond` 的 executor 恰好同时操作同一个 Session
- **修复**：Session 加 `threading.Lock()`，所有写方法（含 `_maybe_save`）获取锁，读方法（`to_llm_messages`）拷贝时获取锁
- **位置**：`session.py:Session` 类
- **注意**：Python GIL 保证单个 `list.append` 原子性，但不保证多次 append（`add_tool_call` 做 3+N 次 append）的整体原子性。锁是唯一保证
- **测试**：多线程并发写 session → 验证无数据丢失 + 无损坏

#### 🟡 中风险（4 项）

##### R5：snapshot 构建时读不一致

- **现状**：`build_snapshot()` 遍历 `session.messages` 时，`add_tool_call()` 可能正在追加新元素
- **影响**：snapshot 可能看到不完整的一轮 tool exchange（如只有 assistant 没有 tool 结果）
- **触发条件**：WS 重连恰好在一轮 tool exchange 中间
- **修复**：R4 的锁同时覆盖读。`build_snapshot` 读 session.messages 时获取锁拷贝
- **位置**：`app.py:build_snapshot`
- **注意**：在 R4 修复后，`to_llm_messages` 和 `build_snapshot` 都需要读锁

##### R6：`session.json` 与 `orch_state.json` 双文件不同步

- **现状**：`_maybe_save()` 和 `save_state()` 各自独立写文件，时间点不同
- **影响**：恢复时 session 可能落后于 orch_state（或相反），上下文与对话历史不一致
- **触发条件**：两次写入之间的进程崩溃
- **修复**：`save_state()` 开头先调 `session.save(path)` 强制同步。确保 session.json 在 orch_state.json 之前更新
- **位置**：`orchestrator.py:save_state`
- **注意**：不能保证原子性（两个文件），但保证恢复时 session 不落后。配合 R4 锁，写入顺序确定

##### R7：项目切换时飞行中的 respond 线程

- **现状**：`switch_project` 设 `_active_orch = None` 后，旧 orch 上的 executor 线程可能仍在运行 `respond`
- **影响**：旧 `respond` 的 `save_state()` 写旧项目 run_dir。但旧 orch 已不被 app 跟踪，数据写入"孤儿目录"
- **触发条件**：分析进行中切换项目
- **修复**：`switch_project` 前调 `old_orch.request_cancel_respond()` 发中断信号
- **位置**：`app.py:switch_project`
- **注意**：配合 R2 修复，流式循环会响应取消。不等待——只发信号
- **测试**：模拟分析进行中切换项目 → 验证旧 orch 的飞行中 respond 在下一个检查点退出

##### R8：LLM 网络异常无重试

- **现状**：`stream_chat_completion` 的 `HTTP 400/5xx` 直接抛 `RuntimeError`，穿透所有调用栈
- **影响**：瞬时网络波动导致整个分析中断
- **触发条件**：API 返回 5xx（服务端临时故障）
- **修复**：5xx 重试 1 次（sleep 1s），400 不重试（消息格式问题，重试无意义）。重试前后各一次 try/except
- **位置**：`agent.py:_call_llm_step`
- **注意**：重试发生在 LLM 调用内部，不重复 emit 流式事件（重试是新请求）
- **测试**：mock API 返回 503 → 验证重试一次 → 第二次仍失败则 raise

### 10.3 没落在修复方案中的已知限制（设计决策）

| 限制 | 原因 | 风险等级 |
|------|------|---------|
| 流式输出中途崩溃，部分文本不持久化 | 流式文本在 stream_end 才存盘。在 delta 频次（每 token）存盘开销太大 | 低（前端已收到并显示） |
| `_pending_ask_user` 不在 Session 中，重启不恢复 | 该信号已改为一次性消费，重启后 LLM 从对话历史自然判断 | 低（session 中有 ask_user tool call） |
| `build_snapshot` 任意异常返回 None | 快照是诊断辅助，不应阻塞主流程。None → 前端降级为空白，比带错误数据好 | 低 |
| 并发 respond 的 ack 先于锁 | ack 是为了防止 WS ping/pong 堆积。先 ack 后处理是故意设计 | 低 |
| 多个 tool call 之间的无原子性 | Python 不支持真正的多操作原子性。通过锁+顺序写入保证足够的安全性 | 低 |

### 10.4 每条修复的验证要求

| 风险 | 验证方式 | 预期结果 |
|------|---------|---------|
| R1 | 单元测试：mock LLM 返回纯文本 → 检查 session | `session.messages[-1]` 是 assistant，content 匹配 |
| R2 | 单元测试：流式循环中调 cancel → 检查提前退出 | `tc_list` 为 None，`txt` 为部分文本 |
| R3 | 单元测试：无 `save_msg` 直接调 `_handle_reply` → 检查 session | 用户消息在 session 中 |
| R4 | 并发测试：10 线程同时写 session → 检查完整性 | 无数据丢失，消息计数正确 |
| R5 | 单元测试：写 session 同时调 `to_llm_messages` → 检查快照 | 快照自洽（assistant.tool_calls 数量 = tool 结果数量） |
| R6 | 验证 `save_state` 调用时序 | session.json 的 mtime ≤ orch_state.json 的 mtime |
| R7 | 切换项目时验证 `_respond_cancelled` | 标志已设置为 True |
| R8 | 单元测试：mock API 503 → 验证重试 | 第一次 503 → sleep → 第二次 503 → raise |

### 10.5 项目切换数据流审计（2026-08-01）

#### 完整数据流

```
用户点击项目列表中的项目
  │
  ├─ ProjectPanel.onSelect()
  │    ├─ setCurrentProject(p)
  │    │    └─ workspace store → localStorage + React 重渲染
  │    │
  │    ├─ WS: send("switch_project", {project: p})      ← EventBus 订阅切换的关键
  │    │    └─ ws_handler → 切换 EventBus 订阅 + 推送 state_snapshot
  │    │
  │    └─ REST: fetch /api/projects/{p}/switch           ← fallback
  │         └─ 后端返回 snapshot → 写入 workspace store
  │
  ├─ WS 意外重连时
  │    handleStateSnapshot(snap)
  │      if snap.project_name != currentProject → clear
  │      setCurrentProject → 触发下面的 useEffect
  │
  └─ useEffect([currentProject])
       fetch /switch
         snap?.messages ? [] → clearMessages + setPhase("setup")
         snap?.messages ? [...] → syncFromSnapshot + setPhase("running")
```

#### 已知断裂点（已修复）

| # | 位置 | 来源 | 修复 |
|---|------|------|------|
| 1 | `AnalyzePanel.tsx:118` `.length` | `7aa88ba` 引入 | `5fdc49e`: 改为 `snap?.messages` |
| 2 | `ProjectPanel.tsx` 不走 WS | 设计遗漏 | `015e954`: 加 `send("switch_project")` |
| 3 | `handleStateSnapshot` WS 路径 vs REST 路径双写 | 双路径共存 | 不作为：REST 走 store, WS 走 useConversation，互不冲突 |

#### 已修复的检查

- [x] `send` 使用模块级 `_ws`，多组件调用安全
- [x] `handleStateSnapshot` 第 42 行：项目不同时 `_setMessages([])` 清空
- [x] `handleStateSnapshot` 第 69-77 行：空 `project_name` + 空 `messages` → 清分析面板
- [x] `localStorage` 按项目名 key 隔离（`_storageKey()` + 项目名 suffix）
- [x] `loadSession()` 死代码已清除（`cc0e249`）
- [x] `resetRunUiState()` 不清 agent 状态——改用精确清理

### 10.6 项目切换架构（2026-08-01）

三条独立路径 → 单一事务。详见 [docs/arch/project-switch-architecture.md](../arch/project-switch-architecture.md)。

**核心变化**：
- 删除两条冗余 REST `/switch` 调用
- WS `state_snapshot` 作为唯一数据源
- `handleStateSnapshot` 作为唯一处理入口
- `ProjectPanel.onSelect` 只做 `setCurrentProject` + `send("switch_project")`

**状态**：待实现。
