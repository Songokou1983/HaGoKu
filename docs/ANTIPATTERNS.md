# 反模式经验录

记录本项目中反复出现的错误模式，每一条都是至少踩过两次的坑。

---

## 反模式 1：代码搬运 LLM 文本

**触发**：LLM 输出的文本没到前端 → 代码从 context/column_semantics 里取出 LLM 文本 → 通过 event/return 再发一遍

**为什么错**：代码不知道流式有没有到达、什么时候到达。一旦流式正常送达，搬运就造成双倍输出。一旦流式没到，搬运是掩盖真问题。

**正确做法**：查为什么流式没到。是没走流式分支（batch 调用）？是 event_bus 断了？是前端没渲染？修通道，不搬运。

**历史**：
- 2026-06-22：刹车 D 已记录此模式（`_scout_text → payload → message`），但之后又犯了 3 次
- 第 1 次：`scout_field_review_pause_payload` 取 `_scout_text` 发到前端
- 第 2 次：handler 里遍历 column_semantics 取 `_scout_text` → emit
- 第 3 次：agent.py 里附加 `_scout_text` sentinel 让 handler 取

**守门**：self_check 第 8 项第 5 层

---

## 反模式 2：只流式第 1 轮，后续轮用 batch

**触发**：`run_step` 工具循环里，第 1 轮走流式，第 2+ 轮走 batch。LLM 在第 4-5 轮才输出表格 → 文本直接丢失。

**为什么错**：代码假设 LLM 第 1 轮就会输出结果。实际上 LLM 可能需要 3-6 轮探索。每一轮 LLM 的输出都是用户应该看到的。

**正确做法**：所有轮都走流式。

**历史**：
- 2026-06-18：大修时只给第 1 轮加了流式，后续轮用 batch
- 2026-06-22 上午：发现字段表不输出，绕了一大圈（加减 `_scout_text` sentinel、加减 msg_text 提取），根因是后续轮文本没流式
- 2026-06-22 下午：修复——后续轮也走流式

**守门**：self_check 第 4 项「流式通道」检查 infer 流式，但只测第 1 轮

---

## 反模式 3：代码替 LLM 做阶段决策

**触发**：LLM 没调 `route_to`，代码检测 `submit_assessment`/`submit_findings` 然后自动切阶段

**为什么错**：LLM 有 `route_to` 工具。代码不应该假设"LLM 调了 X 工具就等于想切到 Y 阶段"。阶段切换是 LLM 的决策，代码只执行 `route_to`。

**正确做法**：代码只检测 `route_to`。如果 LLM 没调，就不切。如果这导致卡住 → 查 prompt。

**历史**：
- 2026-06-22 上午：给 scout/cleaner/analyst handler 加了 submit_assessment/findings 检测作为"兜底"
- 2026-06-22 下午：全部删除，回归纯 `route_to` 检测

---

## 反模式 4：守门太窄，漏掉整个类别的违规

**触发**：守门检查了某一种模式（如 `_column_profiles`），以为是全部。同文件里 150 行的内容生成函数完全漏网。

**为什么错**：守门应该从原则出发（"代码不能生成用户可见内容"），而不是从"我们上次在哪里犯了错"出发。

**正确做法**：守门从禁止键集合、函数命名模式、AST 结构等维度全仓扫描。每次发现新的违规模式 → 加到守门里。

**历史**：
- 2026-06-18：守门第 8 项只检测 `_column_profiles` 使用
- 2026-06-22：150 行的 `scout_field_review_pause_payload` + 70 行的 `cleaning_review_pause_payload` 完全漏网，守门点了 15 天绿灯
- 2026-06-22：守门扩展到 5 层 AST 扫描

---

## 反模式 5：用户消息在前端显示两次（×2）

**触发**：用户输入一条消息，前端会话里显示两条相同的用户气泡。

**已知来源**：
1. **`add_user_feedback` 时序错误**（已修复）：`respond()` 先调 handler（触发 LLM）后写 ProjectContext，LLM 看不到用户回复。修复后又出现新变体。
2. **`_pending_command_text` 注入**：`respond()` 写 `_pending_command_text`，`infer_field_semantics` 把它拼进 user message → 对话历史里 user_feedback 有一条，初始 user message 里又包含一次 → LLM 看到两条。
3. **React StrictMode**：开发环境下组件双渲染，`useEffect` 中的 `setMessages` 可能被调两次。
4. **`state_snapshot` 回放**：WebSocket 重连时 `_build_state_snapshot` 把 ProjectContext 的 user_feedback 条目映射为 `role: "user"` 消息回放，与已有的前端消息叠加。

**排查方法**：
1. 先读 dump 确认 LLM messages 里用户消息是否出现两次（后端问题） vs 只出现一次（前端问题）
2. 如果是后端：检查 `_pending_command_text` 是否和 `add_user_feedback` 造成了双重写入
3. 如果是前端：检查 React DevTools 看消息数组是否有重复条目

**历史**：
- 2026-06-12：架构讨论中记录了 ×2 的四个来源（`add_user_feedback` 双加、`USER_INPUT_REQUESTED` + ACK 双通道、`ToolExchangeTurn` pre_text 重复、React StrictMode）
- 2026-06-21：`respond()` 外层写 + handler 内部写 → ×2，修复为写入单点化
- 2026-06-22：用户反馈 ×2 再次出现，dump 显示 LLM messages 中只出现一次（前端问题），原因待定
