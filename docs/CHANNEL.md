# 反模式经验录

记录本项目中反复出现的错误模式，每一条都是至少踩过两次的坑。

> 🔄 **重构后现状**（2026-07-24）：本文档中的反模式示例引用了一些已删除的函数名（`_scout_text`、`scout_field_review_pause_payload` 等），但**每一条的教训仍然有效**——反模式本身不因函数名消失而消失。新架构中仍可能出现同类问题（如 ``_save_review_cards` 代替了旧 payload 函数、workflow 卡片代替了旧 review 通道），阅读时请关注教训本身而非代码名。

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

**触发**：LLM 没调 `route_to`，代码检测 `submit_assessment`/`submit_findings` 然后自动切阶段；或者代码往 prompt 里注入阶段提示告诉 LLM "你当前在 XX 阶段"。

**为什么错**：LLM 有 `route_to` 工具，且能从完整对话历史中自己判断所在阶段。代码不应该假设"LLM 调了 X 工具就等于想切到 Y 阶段"或"LLM 需要我告诉他在哪"。阶段判断是 LLM 的决策，代码只负责把对话历史完整送达。

**正确做法**：代码只检测 `route_to`。不猜阶段，不贴便条。如果 LLM 表现异常 → 查通道（prompt、工具描述、信息完整性），不加固化规则。

**历史**：
- 2026-06-22 上午：给 scout/cleaner/analyst handler 加了 submit_assessment/findings 检测作为"兜底"
- 2026-06-22 下午：全部删除，回归纯 `route_to` 检测

### 案例：阶段提示注入 — "治标的修复炸了自己"（2026-06-25）

**怎么发生的**：
1. 2026-06-24 15:12（`75ac54d`）：LLM 收到字段反馈后跳到清洗、跳过确认。代码-AI 判断"LLM 不知道当前阶段"，在 prompt 里注入 `【当前关注点：理解字段】` 作为"修复"。
2. 为了动态生成这个提示，加了 `infer_current_focus()` — 扫描 LLM 的历史 tool_calls，用硬编码映射表（`set_columns → 评估清洗`、`submit_assessment → 统计分析` 等）猜 LLM 当前在哪个阶段。
3. 2026-06-24 20:24（`a95d58e`）：升级为"让 Session 成为阶段真相源"，把映射表正式化为 `KEY_TOOL_TO_FOCUS`。
4. **2026-06-25 09:37**：用户纠正字段名 → 代码扫描对话历史，发现 LLM 调过 `set_columns` → 映射表说"set_columns = 评估清洗" → 注入 `【当前关注点：评估清洗】` → **LLM 认为自己在清洗阶段，跳过字段确认，直接做数据质量评估。** 跟 75ac54d 想修的 bug 一模一样，只是换了方向。

**教训**：
- 75ac54d 的"诊断"是错的 — LLM 跳阶段的原因不是"不知道当前阶段"，原始设计里 LLM 从对话历史就能判断。真正的根因是别的通道问题（prompt 歧义、工具描述误导等），至今未查。
- 用"代码猜+提示 LLM"来治标，埋下的硬编码映射表在一天后炸了回来。
- **代码替 LLM 做判断的任何"修复"，最终都会变成 bug。因为代码的判断可能对一时，但一定会在某个场景下错。**

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

---

## 反模式 6：不看根因就写代码 — 2026-06-25 全天教训

### 经验 1：补丁链的机制

**行为**：看到 LLM 不出表 → 把循环上限从 5 改到 99 → LLM 一路到底 → 拆循环 → LLM 卡住 → 加 had_tools → LLM 还在卡 → 撤回。

**后果**：一天 9 个 commit，2 个撤回。每个补丁"修复"都创造了下一个 bug，因为没人停下来问"LLM 为什么不出表？"

**提炼**：**修 bug 前先找根因。** 症状是"不出表"，根因可能是 prompt 没说要出表、工具没注册、或者 LLM 在探索数据。不知道根因就动手 = 补丁链。补丁链的特点：每个补丁单独看都对，链起来就是死循环。

### 经验 2：代码替 LLM 做判断的识别

**行为**：代码扫描 LLM 调了什么工具 → 查映射表 → 往 prompt 里塞"你当前在 XX 阶段"；代码看 LLM 有没有文本 + 有没有调工具 → 判断"LLM 是不是在说话"。

**后果**：映射表写错了 → LLM 跳过确认。判断条件太粗糙 → 干活宣言被当最终回复。每个"代码替 LLM 判断"的改动，都在某个场景下猜错了。

**提炼**：**问自己：这个判断 LLM 自己不能做吗？** 能 → 不写代码，改 prompt。不能（纯 IO/运算）→ 写代码。今天的教训：ask_user break（执行 LLM 的决策）是对的；infer_current_focus（代码猜 LLM 阶段）是错的；had_tools（代码猜 LLM 是不是在对话）也是错的。判断标准不是"改动大不大"，是"LLM 能不能自己做"。

### 经验 3：不看 dump 就改代码的代价

**行为**：用户说"卡住了" → 马上看代码找可能原因 → 提出方案 → 改 → 测试 → 又卡住 → 循环。

**后果**：猜了 5 次才找到真正原因（respond 同步阻塞事件循环）。前面 4 次改动都是浪费。

**提炼**：**dump 是事实，用户描述是线索。** 任何时候 LLM 行为异常，第一反应不是看代码，是看 dump——LLM 收到了什么消息、输出了什么、调了什么工具。dump 看完，80% 的问题不用改代码。

### 经验 4：改 prompt 和改代码混在一起

**行为**：LLM 不调 ask_user → 同时改了 prompt（加"调用 ask_user 确认"）和代码（加 ask_user break 和对话循环）。

**后果**：测试时不知道是 prompt 生效了还是代码生效了。如果 prompt 就够了，代码白写了。

**提炼**：**一次只改一样。** prompt 问题改 prompt，代码问题改代码。改了 prompt 先测，效果不够再加代码。两者一起改 = 不知道自己修了什么。

### 经验 5：改动不评估波及面

**行为**：加一行 `context["_run_dir"] = str(run_dir)`，没检查上下文里 `context` 是空字典、后面有 `if not context:` 依赖它为空。

**后果**：一个测试挂掉，排查了 15 分钟才发现是这行引起的链式反应。

**提炼**：**改之前 grep 所有引用。** 改一个变量 → 搜它在哪里被读取。改一个条件 → 搜它依赖什么假设。2 分钟的搜索省 15 分钟的排查。

---

## 反模式 7：补丁思维 — 同一问题反复出现不加代码

**触发**：用户报告断连/吞没 → 加 persist 同步写 → 加 snapshot 合并 → 加 HTTP 落盘 → 连续 6 小时、30+ commits 全在堵同一个症状的不同出口。

**为什么错**：问题根源不是"消息没存到 localStorage"，而是"前端有三个存储各存各的，没有单一真相源"。补丁加在症状出口上，永远堵不完。

**正确做法**：同一问题反复出现 → 先问架构。数据有几个存储？哪个是唯一真相？改结构（session 为唯一真相、前端不做独立存储）比加代码（persist 同步写、snapshot 合并匹配）有效。

**历史**：
- 2026-07-16：断连/吞没问题，persist 同步写 → HMR 怀疑 → 清缓存 → 手动读 localStorage → HTTP 落盘 → snapshot 匹配合并 → 最后才意识到架构问题
- 根源：前端 messages state、localStorage、后端 session 三处各存各的。重构为 session 唯一真相 + snapshot 全量覆盖，补丁全部不需要。

**守门**：CLAUDE.md 刹车 H

## 通道实现参考（2026-06-25 v0.9 验证的正确模式）

以下模式经过全天 9 轮调试验证，架构调整时不应破坏。

### 信息通道

```
用户输入 → respond() → session.add("user", text) → _handle_reply()
→ run_step() → build_messages(query, user_input, history=session.messages)
→ LLM 调用 → stream deltas → EventBus → WSBridge → WebSocket → 前端渲染
```

**规则**：
- `build_messages()` 是 LLM 消息构造的唯一入口（`hagoku/channel.py`）
- 用户原话通过 `session.add("user")` 写入，不在别处重复写入
- LLM 文本通过流式直达前端，代码不搬运 LLM 输出的文本

### 控制通道

```
LLM 调 ask_user → _pending_ask_user 写入 context → run_step 内循环 break
→ _handle_reply 检测 → emit USER_INPUT_REQUESTED → 前端显示问题
→ 用户回复 → respond() → _handle_reply → run_step → 循环
```

**规则**：
- `ask_user` 是 LLM 唯一的暂停机制，代码只执行不判断
- `_pending_ask_user` 在 `respond()` 空文本分支和 `_handle_reply` 末尾各 pop 一次
- `infer_field_semantics` 内 `_pending_ask_user` 需传到 `self._context`

### 停止信号

```
用户点停止 → 前端 send("cancel_respond") → ws_handler → orch.request_cancel_respond()
→ _respond_cancelled = True → run_step 内循环检查 → break
→ _handle_reply 正常返回 → emit USER_INPUT_REQUESTED → 对话从断点继续
```

**规则**：
- 停止不抛异常，不走 error 路径
- session 已写入的内容保留，LLM 下次看到截断历史自己接上
- `respond()` 开头清除 `_respond_cancelled` 标记

### 状态持久化

```
运行中：save_state() → orch_state.json + session.json + df_*.parquet
重连：_try_restore_session() → 磁盘优先 → restore_session() → 恢复完整状态
前端：state_snapshot → 恢复 project/data_path/messages/ask_user
```

**规则**：
- `restore_session()` 是完整恢复的单一路径：context + DataFrames + Session + Agent + OutputManager
- `_try_restore_session()` 搜索所有项目目录，找最新的 orch_state.json
- 快照包含 messages（最近 50 条）、project_name、data_path、phase、gate_open

### 工具循环

```
run_step() 内循环：for _round in range(99):
    if not tc_list: break          # LLM 不再调工具
    dispatch(tools)                # 执行所有工具调用
    session.add_tool_call(...)     # 写入对话历史
    if _pending_ask_user: break    # LLM 要暂停
    if _respond_cancelled: break   # 用户要停止
    call_llm_again(...)            # 让 LLM 看到工具结果继续
```

**规则**：
- 循环不设上限（99 足够），LLM 自己决定何时停
- 每轮 LLM 输出都走流式
- 工具 dispatch 失败不中断循环（记录 error 后 continue）

### 前端渲染

```
输入框：永远可见，不受 gateOpen/replyPending 控制
停止按钮：replyPending 时显示，点它取消当前 respond
AskUserPrompt：yes_no/choice 变体底部永远有文本输入框（全局 InputBar）
状态标签：不显示"当前：XX 阶段"（代码不猜阶段）

---

## 日志系统（v0.9 统一）

### 架构

```
前端 log() → WS __log → ~/.hagoku/hagoku.log
后端 logger → FileHandler → ~/.hagoku/hagoku.log
分析事件 → run.log（每 run 独立）
对话历史 → session.json
LLM 调用 → llm_dumps/
```

### 统一日志（~/.hagoku/hagoku.log）

所有运行时日志写入同一个文件，格式 `时间 模块 级别 内容`。一个 `grep` 串起完整事件链。

| 模块名 | 记录内容 |
|--------|---------|
| `hagoku.ws.recv` | 前端发来的每条 WS 命令（ping/respond/analyze/select_project...）|
| `hagoku.ws.send` | 发给前端的每条广播（事件类型 + 摘要）|
| `hagoku.ws` | WSBridge on_event 入站、loop 检查、广播状态 |
| `hagoku.observability.event_bus` | 每次 emit（含 subscribers 数量）|
| `hagoku.api` | REST 操作（项目 CRUD、文件上传）|
| `[frontend]` | 前端关键节点（gateOpen、守卫拦截、send 结果、事件接收）|

### 追踪排查

```
# 完整用户输入链路
grep "respond\|user_input\|gateOpen\|submitUserReply" ~/.hagoku/hagoku.log

# 事件是否发射到前端
grep "emit\|on_event\|broadcast" ~/.hagoku/hagoku.log

# 前端状态变化
grep "frontend" ~/.hagoku/hagoku.log
```

### 前端日志写入

`useWebSocket.log(msg)` 通过 WS `__log` 命令发送到后端，写入 `~/.hagoku/hagoku.log`。不依赖浏览器 console。

### 不在统一日志中的

| 数据 | 原因 |
|------|------|
| run.log | 按 run 独立存储，每条分析一个文件 |
| session.json | 对话历史，结构完整，不是事件流 |
| llm_dumps/ | LLM 完整交互，体积大，独立管理 |
| df_*.parquet | 数据快照，非日志 |
```
