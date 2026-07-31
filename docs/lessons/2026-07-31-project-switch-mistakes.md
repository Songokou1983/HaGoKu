# 7月29-31日 错误记录

## 错误1：syncFromSnapshot 全量替换 → 破坏实时事件渲染

- **现象**：用户输入不显示、ask_user 卡片不显示
- **原因**：把 `syncFromSnapshot` 从合并逻辑改为全量替换。项目切换时的快照到达后，`handleStateSnapshot` 调 `syncFromSnapshot` 替换全部消息，所有通过实时事件创建的 askUser 卡片和用户消息被覆盖
- **修复**：恢复合并逻辑——`syncFromSnapshot` 保留本地独有的 user 消息和工作流卡片

## 错误2：respond 后推快照 → 多余数据路径破坏实时交互

- **现象**：ask_user 卡片出现后立即消失
- **原因**：在 ws_handler respond 完成后调用 `build_snapshot` 推送快照。LLM 调用 ask_user 后 respond 完成，快照顾推，替换了刚刚创建的 askUser 卡片
- **修复**：删除 respond 后推快照的代码。实时对话不需要这个路径

## 错误3：persist 改为空函数 → 破坏 localStorage 缓存

- **现象**：重启后消息不恢复
- **原因**：把 `persist` 从 localStorage 写入改为空函数，基于"前端不持久化"的错误架构概念
- **修复**：恢复 `persist` 的 localStorage 写入

## 错误4：删除 addUserMsg → 用户看不到自己发的消息

- **现象**：打字后输入框清空但对话区不显示
- **原因**：删了 `addUserMsg(outgoing)`，错误理解"唯一真相源"为"前端只能有一条路收到数据"
- **修复**：恢复 `addUserMsg`。用户消息前端先显示，后端确认后再通过后续事件同步

## 错误5：创建 active_project 文件 → 第二真相源

- **现象**：删除项目后重启仍试图恢复已删项目
- **原因**：新增了 `~/.hagoku/active_project` 文件做持久化，但 create/delete 都忘记更新它
- **修复**：删除整个 active_project 文件机制。localStorage 才是前端项目选择的唯一记录

## 错误6：编造"快照是唯一真相源"概念 → 整体架构偏差

- **现象**：所有设计和改动围绕一个不存在的概念
- **原因**：把"后端 session 是数据真相"理解成了"前端只能通过快照接收数据"，忽视了事件驱动的事实
- **修复**：文档重写。明确区分两个通道——快照管状态同步（项目切换、重启），事件管实时交互（打字、回复、ask_user）

## 错误7：分析页删除项目下拉 → 冗余改动

- **现象**：用户无法在分析页切换项目上下文
- **原因**：在修项目切换时，把分析页的项目选择下拉也删了，认为"只有一个入口"
- **修复**：恢复下拉。项目切换和项目上下文选择是两回事

## 错误8：handleStateSnapshot 删守卫 → 清理逻辑断层

- **现象**：切换项目后旧数据残留
- **原因**：删了 `project_name !== currentProject` 守卫，把清理职责全移到 useEffect，但 useEffect 和 handleStateSnapshot 有竞态
- **修复**：保留原守卫逻辑不变

## 错误9：respond 后 _pending_ask_user 检查 → 条件错误

- **现象**：还是挡不住快照顾推
- **原因**：`_pending_ask_user` 在 `_handle_reply` 里被 pop 了，ws_handler 检查时已经是 None
- **修复**：整个 respond 后推快照的方案本身就是错的，直接删除
