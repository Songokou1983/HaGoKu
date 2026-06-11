# Web UI 一次性交付 brief v4（2026-06-11）

> **交付模式**：**一个 PR、一次做完**。不分 A/B/C/D 里程碑，不设中间合并点。
>
> **读者**：实施开发（AI 或人）。按本文清单逐项勾选，全部完成后再提 PR。
>
> **前置**：Collapse Phase D + Meta v2 已落地；dump ↔ 真实 messages 对齐（`860e15e`）。
>
> **父 brief**：[`2026-06-11-collapse-to-single-agent-brief.md`](2026-06-11-collapse-to-single-agent-brief.md)、[`2026-06-11-meta-layer-v2-brief.md`](2026-06-11-meta-layer-v2-brief.md)。
>
> **触及范围**：`hagoku_web/` 为主 + 少量后端（事件枚举、流式 LLM、可选 1 行 `role=`）。

---

## §0 交付后用户应感受到什么

| 角色 | 一句话 |
|------|--------|
| **分析师用户** | 一个严肃的数据分析师，分四步做完；**说话像对话（流式出字）**；工具调用看得见；提问有专用 UI；发完回复不会「死机」 |
| **维护者** | 侧栏「开发者」进 Prompt Lab，试跑→对比→应用→审 lessons；dump 能预览真实 messages |

**协议不变**：WS / snapshot / Kanban 仍用 `scout`/`cleaner`/`analyst`/`reporter` stage key；**只改用户可见文案**为 4 关注点中文。

---

## §1 设计锚点（不可推翻）

**Industrial Data Terminal**：深色 IDE、`app-accent` 唯一强调色、Fira 字体、1px 边框、150–200ms 动效、`prefers-reduced-motion` 尊重。

**禁止**：emoji 图标、霓虹风、换字体体系、玻璃拟态铺底、「Oops」式错误文案。

**记忆点**：Pipeline = **分析进度轨**（不是四个同事）；Prompt Lab = **实验室分区**（不与分析同权重）。

---

## §2 一次性交付范围总表

开发按 **CO-01 → CO-28** 实施；编号仅便于勾选，**无阶段依赖说明**——同一 PR 内自行安排编码顺序即可。

| ID | 模块 | 要点 |
|----|------|------|
| **IA & 叙事** | | |
| CO-01 | 侧栏 IA | 四组：工作区 / 参考 / 运行 / 开发者；`lab` 进开发者组 |
| CO-02 | `focusAreas.ts` | 4 关注点常量 + `focusLabel` / `focusDesc` / `focusPlaceholder` |
| CO-03 | 全站文案 | App 副标题、Pipeline、Kanban、Commands、EventTable agent 列 |
| CO-04 | Analyze 上下文 | PanelHeader「当前：理解字段」；placeholder 用 `focusPlaceholder` |
| CO-05 | Pipeline 兜底 | `agent_started` 且 agent 空 → 用 `waitingAgent` / snapshot.stage |
| **共享组件** | | |
| CO-06 | `ActionButton` | primary / secondary / danger / ghost + loading |
| CO-07 | `StatusBanner` | error / success / info + dismiss |
| **Prompt Lab** | | |
| CO-08 | 面板重写 | Tailwind、双栏、状态机（idle/dirty/running/result/compare/apply_ok/error） |
| CO-09 | 工作流 UI | 试跑 → 对比 → 应用（confirm）→ 审计 lessons **分区展示** |
| CO-10 | Dump | 点选 fetch 详情；messages 预览 Tab；载入最后 user 消息到测试框 |
| CO-11 | Lab 测试 | `PromptLabPanel.test.tsx`：无 emoji、dirty、试跑结果、审计/应用分栏 |
| **分析页 · 接线既有组件** | | |
| CO-12 | 后端 `TOOL_EXCHANGE` | `events.py` 枚举 + `project_context` 正确 emit |
| CO-13 | `ToolExchangeTurn` | `useWsEventHandler` + `ConvoFeed`；Tailwind；无 emoji |
| CO-14 | `AskUserPrompt` | ask payload + `state_snapshot.pending_ask_user` 重连 |
| CO-15 | `ThinkingStrip` | `agent_thinking` 不进 ConvoFeed 刷屏 |
| CO-16 | `replyPending` | 发 respond 后 processing 条，不立刻 `waitingAgent=null` |
| CO-17 | `InputBar` | Analyze 等待区复用（受控 value/ref/footerHint），删重复 textarea 逻辑 |
| **流式对话** | | |
| CO-18 | 后端 stream | `agent_stream_delta` / `agent_stream_end`；`run_step` + cleaner 叙事轮 `stream=True` |
| CO-19 | 前端 stream | ConvoFeed 增量 append + 光标；`stream_id` 合并 |
| CO-20 | 流式边界 | 表结构 / tool JSON / Scout 推断 **不流**；prose / ask question / assistant_pre_text **流** |
| CO-21 | 流式失败 | 中断可见；dump 仍记完整 message；`llm.stream_enabled` false → batch（设置页说明） |
| CO-22 | 减动画 | `prefers-reduced-motion`：无打字机装饰；stream 仍可用或直出全文（二选一，文档写明） |
| **类型 & 清理** | | |
| CO-23 | `types/events.ts` | `state_snapshot`、`tool_exchange`、`agent_stream_*` |
| CO-24 | 删 `LogView` | 无引用则删除文件，或保留须在 PR 说明 — **默认删** |
| CO-25 | 测试 | `useWsEventHandler` 单测：ask / tool_exchange / stream_delta 分支 |
| **可选后端 1 行** | | |
| CO-26 | `agent.role` | `run_scout_phase` 设 `self.role = "scout"`（CO-05 仍不足时） |

---

## §3 信息架构（CO-01）

**文件**：`hagoku_web/src/App.tsx`

```
HaGoKu Studio
数据分析师 · 专业工具箱

── 工作区 ──   项目 · 分析 · 报告
── 参考 ──     知识库 · 命令指引
── 运行 ──     看板 · 运行日志
── 开发者 ──   Prompt Lab · 设置
```

`NAV_ITEMS` 带 `section: "work"|"ref"|"ops"|"dev"`，map 时插分组标题；`lab` 在 settings 前。

---

## §4 关注点叙事（CO-02～05）

### CO-02 `constants/focusAreas.ts`

```ts
export const FOCUS_AREAS = {
  scout:    { key: "scout",    label: "理解字段", desc: "字段语义与目标对齐", order: 1 },
  cleaner:  { key: "cleaner",  label: "评估清洗", desc: "缺失值与异常策略", order: 2 },
  analyst:  { key: "analyst",  label: "跑统计",   desc: "检验、效应量与诊断", order: 3 },
  reporter: { key: "reporter", label: "写报告",   desc: "结论与双轨 HTML",   order: 4 },
} as const;
```

### CO-03 改文案

| 文件 | 改什么 |
|------|--------|
| `App.tsx` | 副标题「数据分析师 · 专业工具箱」 |
| `PipelineBar.tsx` | label 用关注点；running 格 `ring-1 ring-app-accent` |
| `KanbanPanel.tsx` / `CommandsPanel.tsx` | 中文关注点；Commands 标题「各关注点可用命令」 |
| `EventTable.tsx` | agent 列中文 + `title={stageKey}` tooltip |

### CO-04 Analyze 上下文

- `PanelHeader` 副标题：`当前：{focusLabel(waitingAgent ?? currentStage)}`
- placeholder：`focusPlaceholder(waitingAgent)`（替换硬编码分支）

### CO-05 Pipeline 兜底

`useWsEventHandler.ts`：`agent_started` 且 `!d.agent` → `resolveAgentKey(waitingAgent ?? snap.stage)`。

---

## §5 Prompt Lab（CO-08～11）

**API（不改路由）**：

| 动作 | 端点 |
|------|------|
| 加载 prompt | GET `/api/prompt-lab/current-prompt` |
| 试跑 | POST `/api/prompt-lab/run` |
| 对比 | POST `/api/prompt-lab/compare` |
| 应用 | POST `/api/prompt-lab/apply` |
| 审计 | POST `/api/prompt-lab/audit-lessons` |
| Dump | GET `dumps` / `dump/{filename}` |

**布局**（`PromptLabPanel.tsx` + CO-06/07）：

- `PanelHeader` + dirty badge
- Toolbar：`试运行` | `对比磁盘版` | spacer | `应用`(danger+confirm) | `审计 lessons`(ghost)
- `lg:grid-cols-2`：左 editor（行/字数）；右测试消息 + Tabs（输出 | 对比 | Gate | **Messages**）
- 底栏 Dump 列表；空态指引开 `HAGOKU_DUMP_LLM`
- **审计结果与 apply 结果不得共用同一 state**

**Dump（CO-10）**：点项 → fetch → 展示 stage/model/messages 条数；「载入为测试消息」= 最后一条 `role=user` content。

---

## §6 分析页 Copilot 体验（CO-12～17）

### CO-12 后端修复 tool_exchange（必做）

```python
# hagoku/observability/events.py
TOOL_EXCHANGE = "tool_exchange"

# hagoku/context/project_context.py
self._event_bus.emit(EventType.TOOL_EXCHANGE, stage, {...})
```

### CO-13 ToolExchangeTurn

- 事件：`tool_exchange`，字段 `tool_calls[]`、`assistant_pre_text`
- `ConvoMessage` 扩展 `toolExchange?: {...}`
- 默认折叠；Lucide 图标；error 行高亮

### CO-14 AskUserPrompt

识别 `user_input_requested` 纯 ask payload（有 `question`+`expected_format`，无 review 表）：

| format | UI |
|--------|-----|
| `yes_no` | 是 / 否 |
| `choice` | options 按钮 |
| `free_text` | 内嵌输入 + 发送 |

`state_snapshot.pending_ask_user` 重连恢复。`onReply` → `submitUserReply`。

### CO-15 ThinkingStrip

```
Pipeline
ThinkingStrip  ← 单条，合并最新 agent_thinking
ConvoFeed
```

`agent_thinking` **禁止**再 push `ConvoMessage`。

### CO-16 发送后 processing

| 态 | UI |
|----|-----|
| `waitingAgent` | 输入区 + 快捷按钮 |
| `replyPending` | `Loader2` + 「分析师正在处理你的回复…」 |
| 下一事件 | 清 `replyPending`，恢复或进入新等待 |

`submitUserReply`：**不要**在 send 成功后立刻 `setWaitingAgent(null)`。

### CO-17 InputBar 收敛

扩展受控 props；Analyze 等待区统一用 `InputBar`；保留 IME-safe Enter、快捷按钮在外层。

---

## §7 流式出字（CO-18～22）— 对话感核心

> 维护方明确要求：**字一个个出来**。本交付 **真 token 流** 为默认路径；非「先 batch 再打字机动画」的阉割方案。

### 7.1 流什么 / 不流什么

| 流式 | 不流式 |
|------|--------|
| analyst/cleaner 对话 prose | field_review / cleaning_review / analyst_review 表 |
| `ask_user.question` | tool 参数 JSON |
| `assistant_pre_text` | Scout submit_field_inference |
| | 报告 HTML |

顺序：**stream prose → `tool_exchange` 块 → 或 `user_input_requested` 表**。

### 7.2 后端（CO-18）

| 文件 | 改动 |
|------|------|
| `hagoku/observability/events.py` | `AGENT_STREAM_DELTA`、`AGENT_STREAM_END` |
| `hagoku/llm/client.py` | `stream_chat_completion()` 生成器；失败 `raise RuntimeError` |
| `hagoku/agents/agent.py` | `run_step`、cleaner 叙事轮：`stream=True`；delta → emit；**tool_calls 缓冲至 finish** 再 dispatch |
| `hagoku/config` | `llm.stream_enabled: bool = True`（或 env）；false 时回退 batch emit 整段 `message` |
| `tests/` | mock stream；delta 顺序 + tool dispatch 与现网一致 |

**payload 建议**：

```json
{ "stream_id": "uuid", "delta": "据", "agent": "analyst" }
{ "stream_id": "uuid", "agent": "analyst" }  // stream_end
```

stream 结束后照常 `dump_messages` **完整** assistant message（`860e15e`）。

### 7.3 前端（CO-19～22）

| 文件 | 改动 |
|------|------|
| `useWsEventHandler` | `agent_stream_delta` merge；`agent_stream_end` 关光标 |
| `ConvoFeed` | `streaming` 气泡末尾 `▍`；自动滚底 |
| `AnalyzePanel` | `replyPending` 期间可隐藏 processing 条若已有 stream 光标（避免双指示） |
| `SettingsPanel` | `stream_enabled` 说明文案（配置中性） |

**重连**：snapshot **不**恢复半条流；只恢复已完成消息或 pending ask。

**减动画**：`prefers-reduced-motion: reduce` → 仍接收 delta 但 **不做额外打字机动画**（直显累积文本）。

---

## §8 既有资产接线状态（开发对照）

| 资产 | 路径 | 交付要求 |
|------|------|----------|
| PromptLabPanel | `panels/PromptLabPanel.tsx` | CO-08～10 重写 |
| ToolExchangeTurn | `components/ToolExchangeTurn.tsx` | CO-13 接线，禁止留死代码 |
| AskUserPrompt | `components/AskUserPrompt.tsx` | CO-14 接线 |
| InputBar | `components/InputBar.tsx` | CO-17 接线 |
| LogView | `components/LogView.tsx` | CO-24 删除 |
| ThinkingStrip | 新建 | CO-15 |
| ActionButton / StatusBanner | 新建 | CO-06/07 |

### 事件消费矩阵（完成后）

```
event                  ConvoFeed  ThinkingStrip  Pipeline  EventPanel
agent_stream_delta        ●           —            —          —
agent_stream_end          ●           —            —          —
tool_exchange             ●           —            —          ●
agent_thinking            —           ●            —          ●
user_input_requested      ●           —            ●          —
agent_started             —           —            ●          ●
tool_called/result        —           —            —          ●
state_snapshot            ●           —            ●          —
```

---

## §9 明确不做

| 项 | 原因 |
|----|------|
| 重命名 `AgentKey` / WS stage | 编排未改 |
| lessons CRUD 页 | 另 brief |
| Light mode / 新字体体系 | 后续 |
| orchestrator 逻辑 | 后端范围外 |
| Prompt Lab SSE（可选） | 时间不够可省略；**分析页流式不可省略** |

---

## §10 一次性验收（全部勾选才合 PR）

### 10.1 自动化

- [ ] `cd hagoku_web && npm test` 绿
- [ ] `pytest` 全绿（基线 538+，含 stream / tool_exchange 新测）
- [ ] `prefers-reduced-motion` 手动 spot check

### 10.2 叙事 & Lab

- [ ] 侧栏开发者组可进 Prompt Lab
- [ ] 试跑 → 对比 → 应用（gate 可见）→ 审计 lessons **分栏**
- [ ] Dump messages 预览 + 载入测试消息
- [ ] 全站无用户可见「多 Agent」「Scout/Cleaner…」

### 10.3 分析 Copilot

- [ ] analyst 对话 **首 token 明显早于整段结束**（真流式）
- [ ] ConvoFeed 可见 tool 折叠块
- [ ] `ask_user` yes_no/choice/free_text 三态 + 刷新恢复
- [ ] ThinkingStrip 不刷屏
- [ ] 发「确认继续」后 processing 可见，不闪没
- [ ] 字段/清洗/统计 **表仍整块出现**，不流式
- [ ] 运行日志页仍正常

### 10.4 纪律

- [ ] 无 emoji 按钮
- [ ] 危险操作有 confirm + 可读 gate 文本
- [ ] LLM/流式失败用户可见（铁律 7）
- [ ] doctrine + information_arrival 测试不红

### 10.5 Smoke 脚本（手工 10 分钟）

1. 上传 CSV → 开始分析 → 字段表确认 → 进入 cleaner → **看流式字 + tool 块**
2. analyst 自由对话一轮 → **逐字出字** → 若有 ask → 点按钮回复
3. 发回复 → processing → 下一暂停
4. Prompt Lab 试跑 + 点 dump 看 messages
5. 断开重连 → pending ask / 字段表恢复
6. 设置关闭 stream（若实现）→ 仍可用 batch 整段

---

## §11 文件清单（PR touch list）

```
hagoku_web/src/
├── App.tsx
├── constants/focusAreas.ts                    # 新建
├── types/events.ts
├── components/
│   ├── ActionButton.tsx                       # 新建
│   ├── StatusBanner.tsx                       # 新建
│   ├── ThinkingStrip.tsx                      # 新建
│   ├── ToolExchangeTurn.tsx                   # 改
│   ├── AskUserPrompt.tsx                      # 改
│   └── InputBar.tsx                           # 改
├── panels/
│   ├── PromptLabPanel.tsx                     # 重写
│   ├── AnalyzePanel.tsx
│   ├── AnalyzePanel/ConvoFeed.tsx
│   ├── AnalyzePanel/types.ts
│   ├── AnalyzePanel/PipelineBar.tsx
│   ├── AnalyzePanel/hooks/useWsEventHandler.ts
│   ├── AnalyzePanel/hooks/useAnalyzeSession.ts
│   ├── KanbanPanel.tsx
│   ├── CommandsPanel.tsx
│   └── EventTable.tsx (components/)
└── panels/__tests__/
    ├── PromptLabPanel.test.tsx
    └── AnalyzePanel/__tests__/useWsEventHandler.test.tsx  # 新建

hagoku/
├── observability/events.py                    # TOOL_EXCHANGE + STREAM_*
├── context/project_context.py                 # emit 修复
├── llm/client.py                              # stream_chat_completion
├── agents/agent.py                            # stream 路径
└── config.py 或 llm 配置                      # stream_enabled

tests/
├── test_context/test_tool_exchange.py         # emit 断言
└── test_agents/ 或 test_llm/                  # stream mock
```

**删除**：`hagoku_web/src/components/LogView.tsx`（若无其他引用）。

---

## §12 PR 模板（复制进 PR body）

```markdown
## Summary
Web UI 一次性交付：侧栏 IA、4 关注点叙事、Prompt Lab 产品化、分析页 Copilot（工具透明/ask_user/思考条/processing）、真流式对话。

## Backend
- EventType.TOOL_EXCHANGE + AGENT_STREAM_DELTA/END
- agent.run_step / cleaner 叙事轮 stream=True
- llm.stream_enabled 回退 batch

## Screenshots
- [ ] 侧栏四组
- [ ] Prompt Lab 工作流 + dump messages
- [ ] 分析页流式气泡 + tool 块 + ask 按钮
- [ ] processing 条

## Test plan
- [ ] npm test
- [ ] pytest
- [ ] §10.5 smoke 1–6
```

**建议 commit message**（单 commit 或少量 logical commits 同一 PR）：

```
feat(web): 一次性交付 IA、Prompt Lab、Copilot 交互与流式对话

- 侧栏分区 + 4 关注点叙事
- Prompt Lab 状态机 / dump messages 预览
- 接线 ToolExchangeTurn、AskUserPrompt、ThinkingStrip、InputBar
- 后端 tool_exchange + LLM stream 事件；前端 ConvoFeed 增量渲染
```

---

## §13 建议编码顺序（仅给开发排任务用，非交付里程碑）

同一 PR 内推荐顺序，减少返工：

1. 后端：`events.py` → `project_context` → `llm/client` stream → `agent.py`
2. 前端基础：`focusAreas` + `ActionButton` + `StatusBanner` + `types/events`
3. `App` IA + 叙事文件批量改文案
4. `useWsEventHandler` 大改（tool / ask / thinking / stream / snapshot / CO-05）
5. `ConvoFeed` + `ThinkingStrip` + `AnalyzePanel` + `InputBar`
6. `PromptLabPanel` 重写
7. 测试 + smoke

**预估工作量**：7–9 人天（含流式联调），**一次 PR 交付**。
