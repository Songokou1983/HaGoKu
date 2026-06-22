# 2026-06-22 架构教训

## 背景

一天之内对 HaGoKu 进行了大量修复：删代码生成、修 ×2 重复、补流式全轮、ProjectContext → Session 重构。每次修好一个 bug，暴露出另一个。根因不是修法不对——是修的对象本身就是错误的抽象。

## 核心教训：错误的抽象之上，每个修复都是新 bug

### 案例 1：ProjectContext entry 体系

```
设计：一次分析 = entries[ContextEntry]
      ContextEntry 有 5 种 type：user_feedback / agent_response / tool_exchange / stage_transition / goal
      写入时调用 add_agent_response() / add_tool_exchange()
      读取时调用 build_prompt() 按 type 逐条翻译成 LLM messages
```

**产生的 bug：**
- `agent_response` 和 `tool_exchange` 写入同一段 LLM 文本 → LLM 上下文 ×2 重复
- `_maybe_save()` 只在 `add_tool_exchange` 中调用 → user_feedback/agent_response 不持久化
- `build_prompt()` 翻译逻辑和写入逻辑不同步

**修复：** 删掉 entry 体系。Session 直接存 `messages: [{role, content}]`，OpenAI 原生格式。410 行 → 90 行兼容层。

### 案例 2：scout_field_review_pause_payload

```
设计：代码从 column_semantics 生成 field_review 结构化数据
     传给前端 FieldReviewTable 组件渲染
```

**产生的 bug：**
- 代码替 LLM 做了 display_name 翻译、角色中文映射、表结构构造
- 与 LLM 流式输出的 markdown 表双倍显示
- 自检只检查了 `_column_profiles` 一种模式 → 150 行代码生成完全漏网

**修复：** 删掉整个函数。LLM 的 markdown 表通过流式直达前端。

### 案例 3：_rewrite_as_written_summary

```
设计：LLM 输出 findings → 代码调第二个 LLM 重写为 [发现]/[统计依据]/[局限] 三要素
     硬编码 prompt，注入事件流
```

**产生的 bug：**
- 第二个 LLM 的 prompt 是代码写的 → 代码在做内容决策
- 主对话 LLM 自己有输出总结的能力，被绕过

**修复：** 删掉。run_step 的流式输出直接到前端。

## 原则

1. **抽象必须比它替代的东西更简单。** ProjectContext 的 entry 类型比 messages 数组更复杂 → 不该存在。
2. **数据格式就是通信协议。** LLM 说 OpenAI message 格式，代码就不该发明自己的格式再翻译回去。
3. **守门要守原则，不是守模式。** "不能用 `_column_profiles`" 是模式，"代码不能生成用户可见内容" 是原则。守门应从原则出发。
4. **一个事实一处存。** LLM 文本存在 messages 里就是 messages 里，不要同时存在 `agent_response.content` 和 `tool_exchange.assistant_pre_text` 两个地方。
5. **先问"为什么需要这层抽象"，再问"这层抽象有什么 bug"。** 如果第一问答不上来，直接删。
6. **相似的代码不是模式，是冗余。** 4 个 handler 各 40 行几乎相同的代码——不是因为 4 个阶段真的需要不同逻辑，而是因为没人在写完第 2 个之后停下来问"为什么不能合并"。合并后 150 行 → 55 行。
7. **每个数据只从一个通道进入系统。** 对话消息从流式进前端，就不要让快照也发一份。两条通道投递同一数据 → ID 体系不兼容 → 查重不可能 → 补丁越打越多。纯净架构不是补丁拼出来的——是删掉重复通道删出来的。
