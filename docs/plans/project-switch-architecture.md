# 唯一真相源 — 完整架构

> 后端 session 是唯一真相。前端只展示快照。所有场景走同一条通道。

## 一、数据真理

系统只有一份数据：后端 session。前端不存储、不缓存、不预览、不保留。

```
session.json（唯一真相）
  → build_snapshot()
  → WS: state_snapshot
  → handleStateSnapshot（唯一写入点）
  → 前端渲染
```

任何偏离这条链的操作都是 bug。

## 二、快照何时推送

唯一触发：**WS 连接时**。后端在 `ws_handler` 的 `ws_handler` 协程开头推送一次当前快照。

不需要其他推送时机。用户发送消息后，消息已经通过 HTTP 保存到 session。LLM 响应写入 session。下次 WS 连接（重连或下一次连接）时，新快照自然包含全部内容。

但如果 session 在 WS 存活期间更新了（用户发消息、LLM 响应），前端如何知道？答案是：**每次 session 写入后，主动推送一次快照**。这样前端始终与后端同步。

推送时机：
- WS 连接时
- 用户消息保存到 session 后
- LLM 响应完成后（run_step 结束）
- 项目切换完成时

## 三、前端唯一写入点

`handleStateSnapshot` 是前端对话状态的唯一写入点。它做的事：

1. 接收快照
2. `messages = snap.messages`（全量替换，不做任何合并或保留）
3. `phase = snap.messages.length > 0 ? "running" : "setup"`
4. `currentProject = snap.project_name`
5. `currentDataPath = snap.data_path`

没有其他函数独立写 messages。`addUserMsg` 是即时预览——消息发送后立即显示，但快照到达时全量替换。快照是真相，预览是体验。

## 四、用户发送消息的完整链路

```
用户输入 "hello" → 回车
  → HTTP POST /save_user_msg → 写入 session
  → WS: send("respond", {text: "hello"})
  → 后端: _respond_impl → _handle_reply → run_step
  → LLM 响应写入 session
  → 后端推送快照
  → handleStateSnapshot 接收 → 前端显示
```

用户消息出现在对话中的时机：快照到达时。在此之前，前端不显示任何内容。

## 五、项目切换的完整链路

```
用户点击项目 B
  → switchToProject("B")
  → setCurrentProject("B")
  → send("switch_project", {project: "B"})
  → 后端: switch_project("B")
      → 保存旧项目状态
      → _load_project("B") → restore_session
      → build_snapshot()
      → 推送快照
  → handleStateSnapshot 接收 → 全部替换为 B 的内容
```

## 六、启动恢复的完整链路

```
应用启动
  → 后端在构造时 _restore_active_project()
    → 读取 active_project 文件
    → _load_project(name) → restore_session
    → _active_orch 就绪
  → WS 连接
  → 后端推送当前快照
  → handleStateSnapshot 接收 → 前端显示
```

## 七、快照内容

```
{
  project_name: string,
  query: string,
  data_path: string,
  report_url: string | null,
  messages: [...],
  stage: string | null,
  gate_open: boolean
}
```

messages 数组直接来自 session.messages 的渲染结果。前端不做任何二次处理。

## 八、不存在的东西

- `addUserMsg` 即时预览，快照到达时全量替换（预览是 UX，不是真相）
- ❌ `persist` / localStorage — 前端不持久化
- ❌ `syncFromSnapshot` 的"保留本地消息"逻辑 — 全量替换
- ❌ `useEffect` 清理 messages — handleStateSnapshot 负责
- ❌ 分析页项目下拉切换 — 唯一入口是左侧项目面板
- ❌ 启动时前端主动发 switch_project — 后端自动恢复

## 九、入口

唯一项目切换入口：项目面板。
应用启动由后端自动恢复。

## 十、当前状态

| 文档要求 | 实际 | 
|---------|------|
| addUserMsg 即时预览 | ✅ 预览+快照全量替换 |
| 无 persist | ✅ 空函数，无副作用 |
| 无 localStorage 消息缓存 | ✅ 已删 |
| syncFromSnapshot 全量替换 | ✅ |
| 响应后推快照 | ✅ ws_handler.py respond 完成后推送 |
| 项目切换后推快照 | ✅ app.switch_project → build_snapshot |
| 后端自动恢复活跃项目 | ✅ _restore_active_project |
| 分析页无切换 | ✅ 已删下拉切换 |
| 无 useEffect 清理 messages | ✅ useEffect 仅清理 UI state |
| 用户消息保存后推快照 | ⚠️ 未实现——消息通过 respond 后快照送达 |
