# 项目切换 — 架构文档 v7

> 基于铁律 13 和实际验证结果。描述当前工作状态，不是理想态。

## 一、职责分离

项目切换涉及两个独立事件，由不同机制处理：

| 事件 | 触发时机 | 处理者 | 做什么 |
|------|---------|--------|------|
| 用户切换项目 | `currentProject` 变化 | `useEffect([currentProject])` + `prevRef` | 清理旧 UI 状态（不含 messages） |
| 后端快照到达 | WS `state_snapshot` | `handleStateSnapshot` | 替换 messages + 同步 project 信息 |

**为什么不能合并**：`useEffect` 是同步的（React render 阶段），`handleStateSnapshot` 是异步的（WS 到达）。合并意味着清理必须等快照——但快照可能延迟、可能不到达。分离意味着清理立即执行，快照到达后填充——各自独立，互不依赖。

## 二、数据流

```
用户点击项目 B
  │
  ├─ switchToProject("B")
  │    ├─ setCurrentProject("B")           ← store 同步
  │    └─ send("switch_project", {B})      ← WS 异步
  │
  ├─ [同步] useEffect([currentProject])
  │    └─ prevRef 守卫 → 清理 UI 状态（不碰 messages）
  │
  └─ [异步] WS state_snapshot 到达
       └─ handleStateSnapshot
            ├─ syncFromSnapshot(ms)        ← 替换 messages
            ├─ setPhase("running"/"setup")  ← 根据快照
            └─ setCurrentProject/DataPath   ← 同步项目信息
```

## 三、唯一真相源

| 数据 | 唯一写入点 | 机制 |
|------|-----------|------|
| **messages** | `handleStateSnapshot` → `syncFromSnapshot` | WS 快照 |
| **phase** | `handleStateSnapshot`（快照）/ `useEffect`（清理） | 快照优先 |
| **本地 UI state** | `useEffect([currentProject])` | 切换时清空 |
| **project_name/data_path** | `handleStateSnapshot` | WS 快照 |

messages 不走 useEffect（铁律 13 合规）。useEffect 只清理 UI state，不写 messages。

## 四、入口

只有一个切换入口：`ProjectPanel` 项目面板点击。
（分析页下拉只设项目上下文，不触发切换。）

应用启动恢复：`App.tsx` mount 时调 `switchToProject`。

统一函数：`switchToProject(name, send, setCurrentProject)`。

## 五、当前代码位置

| 职责 | 文件:行 |
|------|--------|
| 统一触发 | `utils/switchProject.ts` |
| 启动恢复 | `App.tsx:135` |
| 项目面板切换 | `ProjectPanel.tsx:489` |
| 清理 UI state | `AnalyzePanel.tsx:127-151` |
| 快照应用 | `handlers.ts:27-100` |

## 六、验收

| # | 功能 | 验证 |
|---|------|------|
| F1 | 启动恢复 test0729 对话 | 重启应用 → 48 条消息出现 |
| F2 | 项目面板切换 A→B | B 对话出现 |
| F3 | 切换至空项目 | setup 界面 |
| F4 | 分析中锁定 | 切换被拒 |
| F5 | 停止后切换 | 正常 |
| F6 | 反复切换 | 每次正确 |
| F7 | 删除后清空 | setup |
