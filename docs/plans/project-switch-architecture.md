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
## 七、迁移路径

**不变的是功能**：S1-S8 每步都必须全过。**变的是代码**：逐步从"多写入点"收敛到"handleStateSnapshot 单写入点"。

### 基线功能（当前已实现）

| # | 功能 | 用户看到 |
|---|------|---------|
| F1 | 启动恢复 | 打开应用 → 上次项目的对话出现 |
| F2 | 项目面板切换 | 点项目列表 → 对话切换 |
| F3 | 分析页下拉切换 | 分析页选项目 → 对话切换 |
| F4 | 切换至空项目 | 切换到无历史项目 → setup 界面 |
| F5 | 分析中锁定 | 分析进行中点其他项目 → 拒绝提示 |
| F6 | 停止后切换 | 停止 → 点其他项目 → 正常切换 |
| F7 | 反复切换 | A→B→A→B → 每次正确 |
| F8 | 删除后清空 | 删除当前项目 → 面板自动清空 |

### 步骤 1：统一触发（代码改，功能不变）

**功能**：F1-F8 全部保持。

**代码变化**：三处 `send("switch_project", ...)` 替换为一个 `switchToProject(name)` 函数。ProjectPanel、ProjectFileSelectors、App.tsx 都调用它。

**验证**：F1-F8 全部通过 → 进入步骤 2。

### 步骤 2：清理逻辑移入 handleStateSnapshot（代码改，功能不变）

**功能**：F1-F8 全部保持。

**代码变化**：AnalyzePanel useEffect 中的清理逻辑（9 个 setState + sess.resetAll + store 重置）移到 handleStateSnapshot 内，在检测到 project_name 变化时执行。useEffect 清空。

**验证**：F1-F8 全部通过。确认无闪烁、无消息丢失 → 进入步骤 3。

### 步骤 3：删除 useEffect 和 prevRef（代码改，功能不变）

**功能**：F1-F8 全部保持。

**代码变化**：删除已空的 useEffect 和 prevProjectRef。WsEventDeps 中移除不再需要的字段。

**验证**：F1-F8 全部通过 → 进入步骤 4。

### 步骤 4：sess 状态纳入快照管理（技术债，暂缓）

**功能**：F1-F8 全部保持。

**代码变化**：resetAll 管理的 14 个 sess 状态改为由 handleStateSnapshot 根据快照字段管理。需要后端 snapshot 新增对应字段。改动范围大，标记为技术债，不阻塞步骤 1-3。

### 每步守护

```
cd hagoku_web && npx tsc --noEmit        # 零错误
cd .. && pytest tests/ -q                  # 全绿
# F1-F8 手动验证全部通过
```

**回退规则**：任一步验证失败 → `git revert` 回到上一步。不允许在当前步内修补。

## 八、守门

```bash
# handleStateSnapshot 之外无状态写入
grep -rn "setPhase\|setCurrentProject\|setCurrentDataPath\|syncFromSnapshot\|clearMessages\|_setMessages" \
  hagoku_web/src/ --include='*.ts' --include='*.tsx' \
  | grep -v handleStateSnapshot | grep -v useConversation | grep -v useAnalyzeSession
# 预期：仅在 switchToProject 中有 setCurrentProject
```
