# 项目切换架构重构 — 设计文档 v2

> 状态：设计完成。阶段 0 代码已就位。v3 通过铁律 13 + 功能回归双维审计。
> 审计版本：v3（2026-07-29，闭合 v1 gap、v2 合规、v3 prevRef 守卫）

## 一、问题诊断（已确认）

### 1.1 当前项目切换流程（标注所有断裂点）

```
用户点击项目 B
  │
  ├─ ProjectPanel.onSelect()
  │    ├─ setCurrentProject("B")         ← workspace store，同步
  │    └─ send("switch_project", {B})    ← WS 命令
  │
  ├─ 后端 ws_handler:293
  │    ├─ app.is_busy() ? → 拒绝（⚠️ bug ①）
  │    ├─ app.switch_project("B")
  │    │    ├─ 保存旧 orch state
  │    │    ├─ _load_project("B") → 恢复 orch 或新建空 orch
  │    │    └─ build_snapshot() → 返回快照
  │    ├─ 切换 EventBus 订阅
  │    └─ WS push: state_snapshot
  │
  └─ 前端 handleStateSnapshot(snap)
       ├─ snap.project_name !== deps.currentProject ? → 清空（⚠️ 守卫不触发 ②）
       ├─ snap.messages 非空 → syncFromSnapshot(ms)
       ├─ snap.messages 为空 → _setMessages([]) + setPhase("setup")
       ├─ snap.data_path ? → setCurrentDataPath（⚠️ 空值不清理 ③）
       └─ ⚠️ 其他 34 个 state 无任何处理
```

### 1.2 6 个根因

| # | 严重度 | 位置 | 问题 | 影响 |
|---|--------|------|------|------|
| ① | 🔴 P0 | `app.py:88` | `is_busy()` 用 `_respond_cancelled` 判断——正常完成后永远 True | 分析结束无法切换 |
| ② | 🔴 P0 | `handlers.ts:46` | 守卫被 `setCurrentProject` 同步绕过 | 项目切换的去重/清理逻辑跳过 |
| ③ | 🔴 P0 | `AnalyzePanel.tsx` | 39 个状态中 29 个在项目切换时无人清理 | phase/queryText/dataPath 等残留 |
| ④ | 🟡 P1 | `app.py:231` | `build_snapshot` data_path="" → falsy → 前端不设 setCurrentDataPath | 旧 dataPath 永不清 |
| ⑤ | 🟡 P1 | `AnalyzePanel.tsx` | `useEffect([currentProject])` 被删除（`36bc342`） | 失去唯一切换响应点 |
| ⑥ | 🟡 P1 | `ws_handler.py:297` | `is_busy()` 阻塞只发 error | 用户被卡住无提示 |

---

## 二、完整状态盘点（共 39 个）

### 2.1 AnalyzePanel 本地 useState（9 个）

| # | 状态 | 文件:行 | 默认值 | 需重置为 |
|---|------|--------|--------|---------|
| 1 | `phase` | `:42` | `"setup"` | `"setup"` |
| 2 | `queryText` | `:43` | `""` | `""` |
| 3 | `thinkingText` | `:46` | `null` | `null` |
| 4 | `replyPending` | `:49` | `false` | `false` |
| 5 | `dataPath` | `:57` | `""` | `""` |
| 6 | `excelSheets` | `:86` | `[]` | `[]` |
| 7 | `sheetName` | `:87` | `""` | `""` |
| 8 | `auxSheets` | `:88` | `[]` | `[]` |
| 9 | `presetName` | `:52` | `""` | `""` |

### 2.2 useConversation（1 个）

| # | 状态 | 默认值 | 重置方式 |
|---|------|--------|---------|
| 10 | `messages` | `[]` | `clearMessages()` 或 `syncFromSnapshot([])` |

### 2.3 useAnalyzeSession（14 个）

| # | 状态 | 默认值 | 需重置为 |
|---|------|--------|---------|
| 11 | `agentElapsed` | `{scout:0,...}` | 同上 |
| 12 | `waitingAgent` | `null` | `null` |
| 13 | `replyText` | `""` | `""` |
| 14 | `resultReportUrl` | `null` | `null` |
| 15 | `guardrailsBlocked` | `false` | `false` |
| 16 | `blockedRunId` | `null` | `null` |
| 17 | `activeFieldReviewId` | `null` | `null` |
| 18 | `activeFieldReviewRevision` | `-1` | `-1` |
| 19 | `activeCleaningReviewId` | `null` | `null` |
| 20 | `activeCleaningReviewRevision` | `-1` | `-1` |
| 21 | `activeAnalystReviewId` | `null` | `null` |
| 22 | `activeAnalystReviewRevision` | `-1` | `-1` |
| 23 | `gateOpen` | `false` | `false` |
| 24 | `fieldReviewScrollNonce` | `0` | `0` |

### 2.4 useFileUpload（7 个）

| # | 状态 | 默认值 | 需重置为 |
|---|------|--------|---------|
| 25 | `projectFiles` | `[]` | `[]` |
| 26 | `filesLoading` | `false` | `false` |
| 27 | `showFileDropdown` | `false` | `false` |
| 28 | `showProjectDropdown` | `false` | `false` |
| 29 | `uploading` | `false` | `false` |
| 30 | `uploadError` | `null` | `null` |
| 31 | `fileExists` | `false` | `false` |

> **⚠️ 冲突点**：useFileUpload 已有 `useEffect([currentProject, loadFiles])`（`:41-52`），切换项目时自动 fetch `/detail` 回填 `dataPath`。新加的清理 effect 必须在它**之前**注册（按 hook 调用顺序：useFileUpload 在 AnalyzePanel 第 78 行调用，新 effect 在第 112 行调用 → React 先执行 useFileUpload 的 effect → 设 dataPath → 新 effect 后执行 → 清空 dataPath → 竞态。**修复见阶段 2 实施细节**）。

### 2.5 workspace store（8 个）

| # | 状态 | 需重置为 |
|---|------|---------|
| 32 | `status` | 不动 |
| 33 | `agents` | `resetRunUiState()` |
| 34 | `currentProject` | ProjectPanel 已设置 ✅ |
| 35 | `currentDataPath` | `""` |
| 36 | `snapshot` | `null` |
| 37 | `lastError` | `null` |
| 38 | `reportFiles` | `[]` |

### 2.6 已自动处理的（1 个）

| # | 状态 | 处理方式 |
|---|------|---------|
| 39 | `currentProject`（已有） | ProjectPanel 的 `setCurrentProject` 已设置 ✅ |

**统计**：39 个状态，10 个已有处理（messages + currentProject + useFileUpload 7个自动加载 + workspace status不动），**29 个无清理逻辑**。

---

## 三、设计原则

1. **单一清理入口。** 一个 `useEffect([currentProject])` 触发所有重置。不分散。

2. **先清后建。** useEffect 清零 UI 状态 → WS snapshot 异步到达 → 覆盖 messages/phase/data_path。messages 不走 useEffect（铁律 13）。

3. **防闪烁 + 铁律合规。** useEffect 设 `setPhase("setup")`（React 18 批量处理）。**不调 `clearMessages()`**——消息唯一写入点仍是 `handleStateSnapshot`。prevRef 守卫跳过首次挂载。

4. **状态注册表驱动。** STATE_REGISTRY.md 是所有 state 的权威清单。改代码 → 更新注册表 → CI 比对。

5. **`is_busy()` 语义正确。** 用 `_processing` flag，不和取消标志混用。

6. **WS 优先。** 快照走 WS。WS 断连时，cleanup effect 已设 phase="setup"，重连后 snapshot 自然恢复。

---

## 四、分阶段实施计划

### 阶段 0：`is_busy()` 修复（已完成代码，待验证）

**目标**：分析正常完成后可以切换。

**已改文件**：
- `hagoku/manager/orchestrator.py`：`__init__` 加 `self._processing = False`；`request_cancel_respond()` 加 `self._processing = False`
- `hagoku/manager/llm_dispatch/reply_handlers.py`：`_respond_impl` 用 `try/finally` 包裹 `_processing` 的设/清
- `hagoku/app.py`：`is_busy()` 改为 `return self._active_orch._processing`

**`_processing` 状态转换表**：

| 事件 | `_processing` | `_respond_cancelled` |
|------|:--:|:--:|
| 构造 / 恢复 orch | `False` | `False` |
| respond 开始 | `True` | `False` |
| respond 正常结束 | `False` | `False` |
| 用户点停止 | `False` | `True` |
| respond 中抛异常 | `False`（finally） | 不变 |

**验证**：
- [ ] 分析进行中 → 切换 → 被拒绝
- [ ] 分析正常完成 → 切换 → 成功
- [ ] 用户点停止 → 切换 → 成功
- [ ] `restore_session` 恢复的 orch `_processing` 为 `False`（构造函数已保证 ✅）

---

### 阶段 1：`useAnalyzeSession.resetAll()` + 本地 state 清理

**目标**：useAnalyzeSession 暴露一个 `resetAll()` 方法（复用 `handleReset` 逻辑但去掉 WS 命令和 store 操作），供 useEffect 单次调用。

**改 1：`useAnalyzeSession.ts`** — 加 `resetAll()`

```typescript
// 在 handleReset 之前加
const resetAll = useCallback(() => {
  setAgentElapsed({ scout: 0, cleaner: 0, analyst: 0, reporter: 0 });
  setWaitingAgent(null);
  setReplyText("");
  setResultReportUrl(null);
  setGuardrailsBlocked(false);
  setBlockedRunId(null);
  setActiveFieldReviewId(null);
  setActiveFieldReviewRevision(-1);
  setFieldReviewScrollNonce(0);
  setActiveCleaningReviewId(null);
  setActiveCleaningReviewRevision(-1);
  setActiveAnalystReviewId(null);
  setActiveAnalystReviewRevision(-1);
  setGateOpen(false);
}, []);  // 空依赖——setter 是稳定的

// handleReset 改为调 resetAll + WS/store 操作
const handleReset = useCallback(() => {
  send("cancel_analysis", {});
  resetAll();
  resetRunUiState();
  setPhase("setup");
  clearMessages();
  useWorkspaceStore.getState().resetAgentStates();
}, [send, resetAll, resetRunUiState, setPhase, clearMessages]);
```

**返回值加** `resetAll`。

**改 2：`AnalyzePanel.tsx`** — 加 `useEffect([currentProject])` + `useRef` 守卫

```typescript
const prevProjectRef = useRef<string | null>(null);

useEffect(() => {
  const prev = prevProjectRef.current;
  prevProjectRef.current = currentProject;

  // 跳过：首次挂载（prev=null→有项目）、同项目不变、清空项目
  if (prev === currentProject) return;
  if (prev === null && currentProject) return;
  if (!currentProject) return;

  // ── 真正切换（prev 和 currentProject 不同且都不是 null）──

  // 1. 本地 state（由本组件的 useState setter 操作）
  setPhase("setup");
  setQueryText("");
  setThinkingText(null);
  setReplyPending(false);
  _setDataPath("");           // 清空本地 dataPath 副本
  setExcelSheets([]);
  setSheetName("");
  setAuxSheets([]);
  setPresetName("");

  // 2. useAnalyzeSession 状态（单次调用替代 14 个散调）
  sess.resetAll();

  // 3. workspace store（不含 messages — 铁律 13：消息唯一写入点 = handleStateSnapshot）
  setCurrentDataPath("");
  useWorkspaceStore.getState().resetRunUiState();
  useWorkspaceStore.getState().setLastError(null);
  useWorkspaceStore.getState().setReportFiles([]);
  useWorkspaceStore.getState().setSnapshot(null);

  // ⚠️ 不调 clearMessages() — 消息由 handleStateSnapshot 的 syncFromSnapshot 负责替换
  //    铁律 13：消息只有一个写入点
}, [currentProject]);  // sess.resetAll 是 useCallback([]) → 稳定引用，不放 deps
```

**prevRef 守卫状态机**：

| 触发场景 | prev | currentProject | 行为 |
|---------|------|---------------|------|
| 首次挂载（有 localStorage 项目） | `null` → `"A"` | `"A"` | 跳过（`prev === null`） |
| 用户点击切换 A→B | `"A"` | `"B"` | **执行清理** |
| WS 重连推快照 | `"B"` | `"B"` | 跳过（`prev === currentProject`） |
| 清空项目（点 X） | `"A"` | `null` | 跳过（`!currentProject`） |

**改 3：防闪烁 + 铁律 13 合规** — cleanup 设 `setPhase("setup")`（React 18 批量处理保证 snapshot 同 render 覆盖）。**不调 `clearMessages()`**——消息替换只走 `handleStateSnapshot`，遵守铁律 13。

```typescript
// cleanup effect 内：
setPhase("setup");  // ✅ UI 状态，不违规
// ❌ clearMessages() — 铁律 13 禁止，不在本条 effect 中调用
```

**执行顺序保证**（React 按 hook 注册顺序执行 effect）：

```
AnalyzePanel render:
  hook #1: useFileUpload     ← useEffect([currentProject]) 注册
  hook #2: useConversation   ← 无依赖 currentProject 的 effect
  hook #3: useAnalyzeSession ← 无依赖 currentProject 的 effect
  hook #4: 新清理 effect    ← useEffect([currentProject]) 注册（含 prevRef 守卫）

currentProject 真正切换时执行顺序：
  1. useFileUpload effect  ← fetch /files + /detail（异步，微任务）
  2. 新清理 effect         ← 同步清零 UI state + setPhase("setup")
                              ⚠️ 不碰 messages（铁律 13）

  … 微任务：useFileUpload 的 fetch resolve → 回填 dataPath、projectFiles
  … WS 到达：handleStateSnapshot → syncFromSnapshot 替换 messages + phase="running"
  … WS 断连：已由 cleanup 设 phase="setup"，messages 保持旧值等重连恢复
```

**验证**：
- [ ] 刷新页面（首次挂载）→ WS 快照恢复，不被 useEffect 清空
- [ ] 项目 A 分析中 → 切换到空项目 B → 面板 UI 清空，messages 由空快照替换，显示 setup
- [ ] 切换后有历史快照 → messages 由 syncFromSnapshot 替换，phase 变 running
- [ ] 同一项目切换（A→A 再点一次）→ 不触发清理（prevRef 跳过）

---

### 阶段 2：`handleStateSnapshot` 精简

**目标**：只负责应用快照数据，不做清理判断。

**当前 handleStateSnapshot（100 行）→ 精简后保留的 5 个职责**：

| 职责 | 保留 | 理由 |
|------|:--:|------|
| ① 快照消息 → ConvoMessage[] 渲染 + syncFromSnapshot | ✅ | 核心职责 |
| ② snap.data_path → setCurrentDataPath | ✅ | 核心职责 |
| ③ snap.gate_open → setGateOpen | ✅ | 核心职责 |
| ④ snap.project_name → setCurrentProject + agent 状态条 | ✅ | 核心职责 |
| ⑤ 项目删除（空 project_name + 空 messages → 清面板） | ✅ | 独立触发路径 |
| ⑥ 项目切换守卫（行 46-54） | ❌ 删除 | 阶段 1 useEffect 替代 |
| ⑦ askUser 的 workflow 卡片追加 | ❌ 删除 | 已由 live 事件处理（行 76 注释确认） |

**精简后的代码**：

```typescript
export function handleStateSnapshot(deps: WsEventDeps, msg: any): boolean {
  const snap = (msg as any).data;
  if (!snap) return false;
  const {
    syncFromSnapshot, _setMessages, addSystemMsg: addSys,
    setActiveFieldReviewId, setActiveFieldReviewRevision,
    setActiveCleaningReviewId, setActiveCleaningReviewRevision,
    setActiveAnalystReviewId, setActiveAnalystReviewRevision,
    setGateOpen, setPhase, setWaitingAgent,
    setCurrentProject, setCurrentDataPath, setFieldReviewScrollNonce,
  } = deps;

  const roleMap: Record<string, ConvoMessage["role"]> = {
    user: "user", assistant: "agent", agent: "agent",
    workflow: "workflow", tool: "system",
  };

  // ── ① 消息同步 ──
  if (Array.isArray(snap.messages)) {
    if (snap.messages.length > 0) {
      const ms: ConvoMessage[] = snap.messages
        .filter((m: any) => m.role !== "tool")
        .map((m: any) => ({
          id: uid(), role: roleMap[m.role] || "system",
          text: m.content || "", timestamp: m.timestamp || "",
          ...(m.toolExchange ? { toolExchange: m.toolExchange } : {}),
          ...(m.tool_calls ? { tool_calls: m.tool_calls } : {}),
        }));
      syncFromSnapshot(ms);
      setPhase?.("running");
    } else {
      // 空消息 → 该设 setup（当前代码已有此行为，保留）
      _setMessages?.([]);
      setPhase?.("setup");
    }
  }

  // ── ②④ 项目信息同步 ──
  if (snap.project_name && setCurrentProject) setCurrentProject(snap.project_name);
  if (snap.data_path && setCurrentDataPath) setCurrentDataPath(snap.data_path);
  if (snap.gate_open) setGateOpen(true);

  // ── ④ agent 状态条同步 ──
  const agentOrder = ["scout", "cleaner", "analyst", "reporter"];
  const doneIdx = agentOrder.indexOf(snap.stage);
  const states: Record<string, string> = {};
  for (let i = 0; i < 4; i++) {
    const a = agentOrder[i];
    if (i < doneIdx) states[a] = "done";
    else if (i === doneIdx) states[a] = "running";
    else states[a] = "idle";
  }
  for (const [a, s] of Object.entries(states)) {
    useWorkspaceStore.getState().setAgentStatus(a, s as AgentStatus);
  }

  // ── ⑤ 项目被删除 → 全清 ──
  if (!snap.project_name && snap.messages && snap.messages.length === 0) {
    _setMessages?.([]);
    setActiveFieldReviewId(null); setActiveFieldReviewRevision(-1); setFieldReviewScrollNonce(0);
    setActiveCleaningReviewId(null); setActiveCleaningReviewRevision(-1);
    setActiveAnalystReviewId(null); setActiveAnalystReviewRevision(-1);
    setPhase?.("setup");
    deps.setCurrentProject?.(null);
    useWorkspaceStore.getState().setCurrentProject(null);
  }
  return true;
}
```

> **注意**：保留了 agent 状态条同步（当前行 77-88）和项目删除处理（当前行 89-98），这两块不能删——删了 agent 进度条不更新、删项目后分析面板不清。

**验证**：
- [ ] 场景同阶段 1 + 阶段 2

---

### 阶段 3（原阶段 4）：`build_snapshot()` 补全输出

**目标**：新项目返回完整空快照。

**当前代码**（`app.py:228-234`）已经输出 `data_path` 和 `project_name`。但 `ctx.get('data_path', '')` 可能返回 `None`（如果 ctx 中没有该 key）。改为 `ctx.get('data_path') or ""` 确保非 None。

**改动**：`app.py:build_snapshot()`

```python
snap: dict[str, Any] = {
    "project_name": getattr(orch, '_project_name', '') or "",
    "query": ctx.get('query') or "",
    "data_path": ctx.get('data_path') or "",   # 改：'' → or ""
    ...
}
```

**验证**：
- [ ] 新项目 `build_snapshot()` 返回 `{"project_name": "B", "messages": [], ...}`

---

### 阶段 4：STATE_REGISTRY.md + 守门测试

**目标**：锁死状态清单。后续改代码必须同步更新。

**新文件 1**：`hagoku_web/src/panels/AnalyzePanel/STATE_REGISTRY.md`

格式：Markdown 表格，三张表（本地 useState / hook 内部 / store）。每行：状态名、位置、默认值、切换时行为、当前 handler。

**新文件 2**：`tests/test_frontend/test_state_registry.py`

**守门策略**（简化版）：
- 不解析 MD、不对比 AST
- 只做三件事：
  1. `grep 'useState' AnalyzePanel.tsx | wc -l` → 对比注册表的本地 state 行数
  2. `grep 'useState' useAnalyzeSession.ts | wc -l` → 对比注册表的 hook state 行数
  3. 注册表中 `handler: 缺失` 的行 = 测试失败

**验证**：
- [ ] 加新 useState → grep 数量 > 注册表行数 → 测试失败
- [ ] 注册表有 `缺失` → 测试失败
- [ ] 改完代码更新注册表 → 数量匹配 → 测试通过

---

### 阶段 5：全量回归 + 11 场景验收

**场景矩阵**（比 v1 多 1 个）：

| # | 场景 | 步骤 | 预期 |
|---|------|------|------|
| S1 | 分析完成→切换空项目 | Run→完成→点空项目 | 面板清空，显示 setup |
| S2 | 分析完成→切换有历史项目 | Run→完成→点历史项目 | 恢复历史对话 |
| S3 | 分析进行中→切换 | 分析中→点其他项目 | 提示"分析进行中"，不切换 |
| S4 | 停止分析→切换 | 分析中→点停止→切换 | 正常切换 |
| S5 | WS 断连→切换 | 断网→点项目 | useEffect 清空 + setup，重连后恢复 |
| S6 | 新建项目→切换 | 创建空项目→点它 | setup 界面，无残留 |
| S7 | 删除当前项目→自动清 | 删项目→WS 空快照 | setup 界面（走 handleStateSnapshot 路径 ⑤） |
| S8 | 同一项目反复切换 | A→B→A→B | 每次正确恢复/清空 |
| S9 | 切换后立即分析 | 切到 B→Start | 分析正常启动，无旧数据污染 |
| S10 | is_busy 正常 | Run→完成→切换 | 不被阻塞 |
| S11 | 切换后 WS 重连推快照 | A→B→断开→重连→收到 B 的快照 | 恢复 B 的对话（不走 useEffect，走 handleStateSnapshot） |

**验证命令**：
- `pytest tests/` 全绿
- `npx tsc --noEmit` 零错误
- `grep -r 'setMessages' hagoku_web/src/panels/AnalyzePanel/` 仅 useConversation 内部

---

## 五、checklist

### 阶段 0 checklist
- [ ] `_processing` 在 `Orchestrator.__init__` 初始化
- [ ] `request_cancel_respond()` 设 `_processing = False`
- [ ] `_respond_impl` try/finally 管理 `_processing`
- [ ] `is_busy()` 读 `_processing`
- [ ] `restore_session` 恢复的 orch `_processing == False`（构造函数保证）
- [ ] pytest 相关测试通过

### 阶段 1 checklist
- [ ] `useAnalyzeSession.resetAll()` 覆盖全部 14 个 sess state
- [ ] `resetAll` 用 `useCallback([])` 空依赖
- [ ] `handleReset` 复用 `resetAll()`
- [ ] AnalyzePanel 加 `prevProjectRef = useRef(null)` 守卫
- [ ] useEffect 用 prevRef 跳过：首次挂载、同项目不变、清空项目
- [ ] useEffect 清理 9 个本地 state（含 `setPhase("setup")`）
- [ ] 调用 `sess.resetAll()`
- [ ] cleanup 不调 `clearMessages()` — 铁律 13 合规
- [ ] 清理 workspace store 5 个字段（currentDataPath、agents、lastError、reportFiles、snapshot）
- [ ] useEffect deps 只有 `[currentProject]`（`sess.resetAll` 不放 deps）
- [ ] 不产生 infinite loop
- [ ] 刷新页面：快照恢复不被 useEffect 清空

### 阶段 2 checklist
- [ ] 保留职责 ① 消息同步（含 ConvoMessage 渲染逻辑 + syncFromSnapshot）
- [ ] 保留职责 ②④ data_path/gate_open/project_name/agent 状态条同步
- [ ] 保留职责 ⑤ 项目删除处理
- [ ] 删除行 46-54 的守卫逻辑
- [ ] 删除 askUser 的 workflow 追加逻辑（注释确认已由 live 事件处理）
- [ ] 空 snapshot 设 `_setMessages([])` + `setPhase("setup")`（当前行为保留）

### 阶段 3 checklist
- [ ] `data_path` 用 `or ""` 替代 `get(..., '')` 防止 None
- [ ] 新项目 `build_snapshot()` 不返回 None

### 阶段 4 checklist
- [ ] STATE_REGISTRY.md 三张表覆盖全部 39 个状态
- [ ] 每个状态标注"切换时行为"和"当前 handler"
- [ ] 守门测试：grep useState 数量 = 注册表行数
- [ ] 守门测试：注册表无 `缺失`

### 阶段 5 checklist
- [ ] 11 个场景全部手动验证
- [ ] `pytest tests/` 全量通过
- [ ] `npx tsc --noEmit` 零错误
- [ ] `grep setMessages` 外部无调用

---

## 六、文件改动清单

| 阶段 | 文件 | 操作 | 预估行数 |
|------|------|------|---------|
| 0 | `orchestrator.py` | 加 `_processing` flag | +2 |
| 0 | `reply_handlers.py` | try/finally 包裹 | +3 |
| 0 | `app.py` | `is_busy()` 改实现 | +1/-1 |
| 1 | `useAnalyzeSession.ts` | 加 `resetAll()`，改 `handleReset` | +20/-15 |
| 1 | `AnalyzePanel.tsx` | 加 useEffect([currentProject]) | +35 |
| 2 | `handlers.ts` | 精简 handleStateSnapshot | -15/+5 |
| 3 | `app.py` | build_snapshot 补全 | +1/-1 |
| 4 | `STATE_REGISTRY.md` | 新建 | +70 |
| 4 | `test_state_registry.py` | 新建 | +30 |
| **合计** | **8 文件** | | **~160 行净增** |

---

## 七、回退策略

- 每阶段独立 commit，独立 revert
- 阶段 0：独立修 bug
- 阶段 1：`resetAll()` + useEffect —— 核心改动，可独立回退
- 阶段 2：依赖阶段 1（删了守卫后不能留下缺口），一起 revert
- 阶段 3：后端小补，独立
- 阶段 4：纯文档+测试，零风险

---

## 八、已知风险（v2 已闭合）

| 风险 | 状态 |
|------|:--:|
| useEffect deps 引用不稳定 → 循环 | ✅ `sess.resetAll` 用 `useCallback([])`，不放 deps |
| useEffect 设 phase → 闪烁 | ✅ cleanup 设 "setup"，React 18 批量处理保证同 render 中 snapshot 覆盖 |
| 首次挂载 useEffect 破坏快照恢复 | ✅ prevRef 守卫：`prev === null → currentProject` 跳过 |
| handleStateSnapshot 精简漏功能 | ✅ 保留 agent 状态、项目删除、ConvoMessage 渲染 |
| useEffect 和 useFileUpload 竞态 | ✅ React effect 按注册顺序执行，新 effect 在 useFileUpload 之后注册 |
| 删除守卫后断连重连误清 | ✅ 重连时 project_name 相同 → prevRef 跳过 |
| syncFromSnapshot 漏 ConvoMessage 渲染 | ✅ 阶段 2 保留完整渲染逻辑 |
| WS 快照在 useEffect 之前到达 | ✅ prevRef 守卫保证首次挂载跳过；真正切换时 snapshot 异步到达在 effect 之后 |
| restore_session 的 _processing | ✅ 构造函数设 `False` |
| WS 重连后再次收到同一快照 | ✅ syncFromSnapshot 内部去重 |
| `clearMessages()` 违反铁律 13 | ✅ 已从 useEffect 中删除，消息只走 handleStateSnapshot |

---

## 九、审计日志

| 版本 | 日期 | 审计结论 | 变更 |
|------|------|---------|------|
| v1 | 2026-07-29 | 5 gap + 3 遗漏 | 初始设计 |
| v2 | 2026-07-29 | 0 gap，0 遗漏 | resetAll 重构、防闪烁、handleStateSnapshot 补全、守门简化 |
| v3 | 2026-07-29 | 铁律 13 + 功能回归双维审计通过 | 删 clearMessages（铁律 13）、加 prevRef 守卫（防首次挂载误清） |
