# 项目切换 — 理想架构

> 基于铁律 13（唯一真相源）和通道原则设计。
> 不管现有代码实现——只描述"应该是什么样"。

## 一、单通道

整个系统只有一条数据路径：

```
触发（任一处）
  → WS: switch_project
  → 后端: 恢复 session → build_snapshot
  → WS: state_snapshot
  → handleStateSnapshot（唯一写入点）
```

三个入口汇入同一条通道：

| 入口 | 场景 |
|------|------|
| 项目面板点击 | 用户主动切换 |
| 分析页下拉选项目 | 同上 |
| 应用启动 | localStorage 有 active project |

## 二、handleStateSnapshot 是唯一写入点

`handleStateSnapshot` 收到快照后，原子性地完成以下操作。**没有任何其他函数、useEffect、事件处理器直接写这些状态**：

| 操作 | 说明 |
|------|------|
| `syncFromSnapshot(messages)` | 替换消息列表 |
| `setPhase("running")` 或 `"setup"` | 根据快照是否有消息 |
| `setCurrentProject(snap.project_name)` | 同步项目名 |
| `setCurrentDataPath(snap.data_path)` | 同步数据路径 |
| 同步 agent 状态条 | 根据 snap.stage |
| 清空 review 卡片 ID | 如果 project_name 变化 |

**切换时的旧状态清理**：handleStateSnapshot 在处理新快照前，检测 `snap.project_name !== 当前 project_name`，如果是 → 先执行清理（清 review ID、清本地 UI 标记），再应用新快照。清理和应用在同一个函数调用内完成，不需要 useEffect。

**切换期间的视觉过渡**：在 `send("switch_project")` 返回后、快照到达前，不需要任何中间状态。如果快照在 16ms 内到达（正常情况），React 批量处理，用户看不到中间帧。如果快照延迟（网络慢），消息列表短暂显示旧内容，快照到达后替换——这也比先清空再填充的闪烁好。

## 三、不需要的东西

以下在理想架构中不存在：

- ❌ `useEffect([currentProject])` 清理 UI 状态 — 清理是 handleStateSnapshot 的职责
- ❌ `prevRef` 守卫区分首次挂载和切换 — handleStateSnapshot 自己处理
- ❌ `resetAll()` 方法供 useEffect 调用 — handleStateSnapshot 处理所有状态
- ❌ 多个 `send("switch_project")` 调用点 — 统一为一个触发函数
- ❌ 任何在 handleStateSnapshot 之外的 `setMessages` / `clearMessages` 调用

## 四、统一触发

所有需要切换项目的地方，调用同一个函数：

```typescript
function switchToProject(name: string) {
  setCurrentProject(name);                    // 同步 store（UI 立即响应）
  send("switch_project", { project: name });  // 触发后端
  // 不做任何状态清理 — handleStateSnapshot 负责
}
```

在以下位置调用：
- `ProjectPanel` 项目列表点击
- `ProjectFileSelectors` 下拉选择
- `App` 启动恢复（mount 时）

## 五、handleStateSnapshot 完整逻辑

```
handleStateSnapshot(snap):
  if !snap: return

  // 1. 如果项目变了 → 先清理
  if snap.project_name !== currentProject:
    clearReviewCards()
    setGateOpen(false)
    setPhase(null)  // 过渡态，等消息处理完再设

  // 2. 同步项目信息
  setCurrentProject(snap.project_name)
  setCurrentDataPath(snap.data_path || "")

  // 3. 同步消息
  if snap.messages.length > 0:
    renderAndSyncFromSnapshot(snap.messages)
    setPhase("running")
  else:
    clearMessages()
    setPhase("setup")

  // 4. 同步其他快照字段
  if snap.gate_open: setGateOpen(true)
  if snap.report_url: setReportUrl(snap.report_url)

  // 5. 同步 agent 状态条
  syncAgentStates(snap.stage)

  // 6. 项目被删除 → 全清
  if !snap.project_name && snap.messages.length == 0:
    clearAll()
```

## 六、与现有代码的差距

| 理想 | 现有 | 差距 |
|------|------|------|
| handleStateSnapshot 做清理 | useEffect + prevRef 做清理 | 清理逻辑分散两处 |
| 一个 `switchToProject` 函数 | 多处散调 send("switch_project") | 不一致（已部分修复） |
| 无 resetAll 概念 | useAnalyzeSession.resetAll() | sess 状态也应由 snapshot 管理 |
| App mount 触发 switchToProject | App.tsx useEffect | 功能一致，命名不统一 |

## 七、迁移路径

**不做一次性重写。** 当前代码已工作（项目切换正常、启动恢复正常、三个入口均补齐）。差距是架构清洁度问题，非功能缺陷。下一步改代码时优先收敛到理想架构：

1. 逐步把 useEffect 中的清理逻辑移到 handleStateSnapshot（保持功能不变）
2. 统一触发点为 `switchToProject(name)` 函数
## 七、迁移路径（不改功能，逐步收敛）

**原则**：每一步完成后，8 个场景（S1-S8）必须全部通过。任一步失败 → 回退 → 修到通过再继续。

### 当前状态（基线）

| 功能 | 状态 |
|------|:--:|
| 项目面板切换 | ✅ |
| 分析页下拉切换 | ✅ |
| 启动恢复 | ✅ |
| 8 场景验收 | ⬜ 待你验证 |

### 步骤 1：统一触发函数（不改行为）

创建 `switchToProject(name)` 函数，替代三处散调的 `send("switch_project", ...)`。

```typescript
// 新函数（放在 hooks/ 或 utils/）
function switchToProject(name: string, send: SendFn, setCurrentProject: SetFn) {
  setCurrentProject(name);
  send("switch_project", { project: name });
}
```

**改动**：`ProjectPanel.tsx:488-489`、`ProjectFileSelectors.tsx:72`/`AnalyzePanel.tsx:309`、`App.tsx:135` — 三处替换为调用 `switchToProject`。

**行为不变**：函数内部做的就是原来两行代码。零功能变化。

**验证**：S1-S8 全部通过。`tsc --noEmit` 零错误。

### 步骤 2：handleStateSnapshot 接管清理（不改行为，移代码）

当前 useEffect（`AnalyzePanel.tsx:127-151`）清理 9 个本地 state + sess.resetAll() + store 字段。

目标：把这段清理逻辑移到 `handleStateSnapshot` 内，在检测到项目变化时执行。

```typescript
// handleStateSnapshot 新增
if (snap.project_name && snap.project_name !== currentProject) {
  // 以下代码与 AnalyzePanel.tsx:136-150 完全一致
  setPhase("setup");
  setQueryText("");
  setThinkingText(null);
  setReplyPending(false);
  // _setDataPath 不在 handleStateSnapshot 可访问范围内 → 用 deps
  setExcelSheets([]);
  setSheetName("");
  setAuxSheets([]);
  setPresetName("");
  // sess.resetAll() → 需要在 deps 中暴露
  setCurrentDataPath("");
  useWorkspaceStore.getState().resetRunUiState();
  useWorkspaceStore.getState().setLastError(null);
  useWorkspaceStore.getState().setReportFiles([]);
  useWorkspaceStore.getState().setSnapshot(null);
}
```

**关键**：`handleStateSnapshot` 通过 `deps` 访问这些 setter。需要在 `WsEventDeps` 类型中添加缺失的字段（`setQueryText`, `setThinkingText`, `setReplyPending`, `_setDataPath`, `setExcelSheets`, `setSheetName`, `setAuxSheets`, `setPresetName`, `sessResetAll`），然后从 `AnalyzePanel` 传入。

**同时**：useEffect 中的清理代码删除，只保留空 useEffect（或加注释标记"已移至 handleStateSnapshot"）。

**验证**：S1-S8 全部通过。确认消息不重复、不丢失、不闪烁。

### 步骤 3：移除 useEffect 和 prevRef

步骤 2 验证通过后，`AnalyzePanel.tsx:127-151` 的 useEffect 已空。删除它和 `prevProjectRef`。

**改动**：删除 25 行代码。

**验证**：S1-S8 全部通过。

### 步骤 4：用快照管理 sess 状态

当前 `sess.resetAll()` 重置 14 个 useAnalyzeSession 状态。理想架构中这些应由快照或 handleStateSnapshot 管理。

**不急于做**：sess 状态和消息不同——它们是 UI 交互状态（如 review 卡片 ID、gateOpen），不是持久化数据。让 handleStateSnapshot 管理它们需要后端 snapshot 包含这些字段，改动范围大。

**标记为技术债**：当前 resetAll 模式可接受，不影响唯一真相源原则（消息已走 handleStateSnapshot）。

### 每步守护

```bash
# 步骤 1-3 每步结束后运行
cd hagoku_web && npx tsc --noEmit          # 零错误
cd .. && python3 -m pytest tests/ -q         # 全绿
grep -rn 'setMessages\|clearMessages' hagoku_web/src/panels/AnalyzePanel/ \
  --include='*.ts' --include='*.tsx' \
  | grep -v useConversation | grep -v types.ts | grep -v _setMessages
# 预期：无输出（消息写入只在 handleStateSnapshot）
```

### 不可回退的改动

每一步均独立 commit。如果步骤 2 验证失败，`git revert` 回到步骤 1 状态。不允许"修修补补继续往前走"——必须回到上一个干净状态，重新设计方案。

## 八、守门

```bash
# handleStateSnapshot 之外无状态写入
grep -rn "setPhase\|setCurrentProject\|setCurrentDataPath\|syncFromSnapshot\|clearMessages\|_setMessages" \
  hagoku_web/src/ --include='*.ts' --include='*.tsx' \
  | grep -v handleStateSnapshot | grep -v useConversation | grep -v useAnalyzeSession
# 预期：仅在 switchToProject 中有 setCurrentProject
```
