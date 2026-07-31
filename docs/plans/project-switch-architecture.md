# HaGoKu 对话系统 — 架构文档

## 一、用户发消息

```
用户输入文字 → 回车
  ├─ 前端立即显示这条消息（addUserMsg）
  ├─ HTTP PUT /save_user_msg → 写入后端 session
  └─ WS: send("respond")
       └─ 后端 run_step → LLM 回复
            └─ agent_stream_delta 事件一条条推到前端 → 逐字显示
```

## 二、AI 问用户

```
LLM 调用 ask_user 工具
  └─ 后端 emit user_input_requested 事件
       ├─ question / expected_format / options
       └─ 前端收到 → 创建卡片（AskUserPrompt）→ 用户看到
            └─ 用户回复 → 回到第一节
```

## 三、项目切换

```
用户点项目 B
  ├─ 前端 setCurrentProject("B")
  ├─ WS: send("switch_project", {project: "B"})
  ├─ 后端 switch_project → _load_project → build_snapshot
  └─ WS: state_snapshot → 前端替换消息列表
```

## 四、启动恢复

```
打开应用
  ├─ 前端 localStorage 有 currentProject
  ├─ App mount → send("switch_project")
  └─ 同第三节
```

## 五、后端 session 是真相

- 所有消息存在 `session.json`
- 项目切换时通过 `state_snapshot` 批量同步
- 实时对话时通过 `agent_stream_delta` / `user_input_requested` 事件传递
- 前端不另存消息（无 localStorage 缓存对话）

## 六、卡片位置规则

卡片（ask_user / field_review / cleaning_review / analyst_review）是对话的一部分，出现后就固定在它的位置。不重复追加，不重新定位。

- 首次创建时写入 session（通过前端 live event 回调或后端首次触发）
- 后续暂停只新增 ask_user 卡片（每次暂停是新问题），已存在的 field_review 不重复写

## 七、代码位置

| 功能 | 前端 | 后端 |
|------|------|------|
| 用户打字显示 | `AnalyzePanel.tsx:submitUserReply` → `addUserMsg` | — |
| AI 流式回复 | `handlers.ts:agent_stream_delta` | `agent.py:run_step` 流式 |
| AI 提问卡片 | `handlers.ts:user_input_requested` → `AskUserPrompt` | `reply_handlers.py:_handle_reply` → emit |
| 项目切换 | `ProjectPanel.tsx` → `switchToProject` | `app.py:switch_project` → `build_snapshot` |
| 启动恢复 | `App.tsx` mount → `switchToProject` | 同上 |
| 消息持久化 | — | `reply_handlers.py:save_user_msg` → session |
