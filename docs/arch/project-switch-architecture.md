# 项目切换架构设计

## 问题

当前项目切换由三条独立路径并发执行，互不协调：

- **路径 A**（ProjectPanel）：REST `/switch` → workspace store
- **路径 B**（AnalyzePanel useEffect）：REST `/switch` → `syncFromSnapshot`
- **路径 C**（WS `state_snapshot`）：`handleStateSnapshot` → `_setMessages`

三条路径发出两个并发 REST 请求、同时 WS 也推送同一份数据。写入顺序不确定，最后一个执行者获胜。

## 目标

项目切换作为**显式事务**，一步接一步，不并行不竞态。

## 设计

### 单一入口

```
用户点击项目 → switchToProject(projectName)
                   │
                   ├─ 1. 断开旧连接：WS send("switch_project")
                   │      后端：取消旧 EventBus 订阅 + 建立新订阅
                   │
                   ├─ 2. 等待 WS state_snapshot 到达
                   │      后端在订阅切换后立即推送快照
                   │
                   ├─ 3. 清空前端状态
                   │      clearMessages()
                   │      清 review/pending/gate 状态
                   │      setPhase("setup")
                   │
                   ├─ 4. 加载快照
                   │      syncFromSnapshot(ms)
                   │      setPhase(snap.messages.length > 0 ? "running" : "setup")
                   │
                   └─ 5. 完成
```

### 路径变化

```
改前（三条独立路径）：
  setCurrentProject(p)
    ├─ REST /switch → store        ← 冗余
    ├─ useEffect → REST /switch    ← 冗余
    └─ WS state_snapshot → handler ← 单独走
    三路并发→竞态

改后（单一事务）：
  switchToProject(p)
    ├─ WS send("switch_project")   ← 触发后端切换 EventBus + 推送快照
    └─ handleStateSnapshot         ← WS 快照到达后→统一处理
    单路串行→无竞态
```

### 改动清单

| 文件 | 改什么 | 改后 |
|------|--------|------|
| `ProjectPanel.tsx` | `onSelect` | 不再发 REST `/switch`，只 `setCurrentProject(p)` + `send("switch_project")` |
| `AnalyzePanel.tsx` | `useEffect([currentProject])` | 不再 `fetch /switch`，只做：清空状态 + 等待 WS 快照 |
| `handlers.ts` | `handleStateSnapshot` | 不再校验 `project_name`（WS 推送的是当前项目无需校验），直接清空旧状态 + 加载消息 |
| `ProjectPanel.tsx` | `fetch → setSnapshot` | 删掉，WS 快照负责 |
| `AnalyzePanel.tsx` | `fetch → syncFromSnapshot` | 删掉，WS 快照负责 |

### 不做的事

- 不加新的 store/context
- 不重建 WS 连接
- 不改后端 `/switch` REST 端点（保留供其他场景）

### 竞态消除

| 旧竞态 | 消除方式 |
|--------|---------|
| 双重 REST 调用 | 两条 REST 全部删除，只留 WS |
| `setSnapshot` vs `syncFromSnapshot` 写入顺序 | 单一路径，无冲突 |
| `handleStateSnapshot.project_name` 守卫死代码 | 不再需要校验——WS 推送的就是当前项目 |
| 快速切换 A→B→C | WS 是串行的，`send("switch_project", "C")` 在 A 和 B 之后处理 |
