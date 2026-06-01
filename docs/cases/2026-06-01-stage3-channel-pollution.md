# 现行犯档案：阶段 3 诊断 dump 分析

**日期**：2026-06-01
**触发**：用户报告「LLM 进项目变白痴」+「阶段衔接差」
**Dump 路径**：`~/.hagoku/llm_dumps/`（7 份 JSON）
**场景**：分析每个店铺的收入变动趋势（test0526 类型数据）

---

## 0. 一句话结论

**通道污染 + 阶段衔接断裂两个困惑同源**，但根因比 spec §3 假设更复杂：

1. ProjectContext 已接入 Cleaner（spec 假设错）
2. **但 build_prompt 内部有 3 处设计缺陷 + Cleaner 拼装有 1 处遗漏**，导致下游 Agent 看到的是「重复噪声 + 失序对话 + 用户原话蒸发」

阶段 3 真实任务**不是「让 Cleaner 接入 ProjectContext」**（已经接了），而是修 build_prompt 的 3 个设计缺陷 + Cleaner 改用 build_prompt 返回值。

---

## 1. Dump 文件清单

| seq | stage | 触发场景 |
|-----|-------|---------|
| 001 | scout_infer_all_semantics | Scout 初始字段推断（兜底 analysis_goal_section 生效 ✅） |
| 002 | scout_reply_review | 字段评审第 1 轮（用户：「BU 代表公司，Code 才是店铺编码…」） |
| 003 | scout_reply_review | 字段评审第 2 轮（用户：「本次参与分析的应该是店铺、周期、收入 3 个字段」） |
| 004 | scout_reply_review | 字段评审第 3 轮（用户：「可以进入下一阶段了」） |
| 005 | cleaner_dialogue | Cleaner 首次启动 |
| 006 | cleaner_dialogue | Cleaner 第 2 次（重复调用 submit_assessment？） |
| 007 | cleaner_dialogue | Cleaner 第 3 次（多次重复探索） |

---

## 2. 关键发现矩阵

### P1 🔴 messages_history 顺序错乱（律 3 破坏）

**现场**：dump 003 / 004

dump 003 messages（按出现顺序）：

```
1. system
2. assistant: 字段推断完成：理解 8 个字段       ← Scout 初始补录
3. assistant: 无字段更新                       ← 第 1 轮 _apply_scout_reply_with_llm 内写入
4. user: BU 代表的是公司...                    ← 第 1 轮 USER_INPUT_RECEIVED 写入
5. user: 本次参与分析的应该是店铺...           ← 本轮（当前）
```

**期望对话顺序**：`user1 → assistant1 → user2 → assistant2 → ...`
**实际顺序**：`assistant1 → assistant2 → user1 → user2`

LLM 看到的不是"用户问 → 我答 → 用户问 → 我答"，而是"我连说两句空话 → 用户接连提了两件事"。**对话语义完全错位**。

**根因**：

```@/home/son_goku/HaGoKu/hagoku/manager/orchestrator.py:1077
            project_ctx.add_agent_response(
                stage="scout",
                ...
            )
```

每轮 `_apply_scout_reply_with_llm` **在 LLM 调用后立即** add_agent_response，但 `USER_INPUT_RECEIVED` 事件是在函数**返回之后**才 emit（`@/home/son_goku/HaGoKu/hagoku/manager/orchestrator.py:2290` 附近）。

时序：

```
T1: 用户发反馈
T2: 调 _apply_scout_reply_with_llm(raw=反馈)
T3:   ↳ build_prompt 拼装 messages（此时 entries 中无本轮 user_feedback）
T4:   ↳ LLM 调用
T5:   ↳ add_agent_response  ← entries 加入 agent_response (在 user_feedback 之前)
T6: 函数返回
T7: emit USER_INPUT_RECEIVED → add_user_feedback (晚于 agent_response 进入 entries)
T8: 下一轮 build_prompt 按 entries 顺序输出 → assistant 永远先于 user
```

---

### P2 🔴 upstream_summary 严重重复

**现场**：dump 005 / 006 / 007 — system 段末尾：

```
【上游阶段摘要】
scout 阶段完成: target=Inc1, features=['BU', 'Code', 'Period'], 待确认=['Bos1', 'Bos2', 'Bos3']
scout 阶段完成: target=Inc1, features=['BU', 'Code', 'Period'], 待确认=['Bos1', 'Bos2', 'Bos3']
scout 阶段完成: target=Inc1, features=['BU', 'Code', 'Period']
scout 阶段完成: target=Inc1, features=['BU', 'Code', 'Period']
scout 阶段完成: target=Inc1, features=['BU', 'Code', 'Period']
```

**5 条几乎相同**的 summary。前 2 条因为 `pending` 还没清空附带「待确认」字段，后 3 条 pending 已清空。

**根因**：

```@/home/son_goku/HaGoKu/hagoku/context/project_context.py:179-190
        upstream_entries = [e for e in self.entries if e.stage != agent]
        upstream_parts: list[str] = []
        for e in upstream_entries:
            if e.type == "agent_response" and e.snapshot:
                ...
                upstream_parts.append(summary)
        upstream_summary = "【上游阶段摘要】\n" + "\n".join(upstream_parts) if upstream_parts else ""
```

Scout 阶段每轮 add_agent_response 都生成一条 agent_response entry。Cleaner 启动时拿到上游 entries 共 5 条（1 初始 + 3 评审 + 1 内部补录或类似），**未去重、未取最后一条**——直接全部展开。

---

### P3 🔴 Cleaner 看不到 Scout 用户原话（阶段衔接断裂的核心）

**现场**：dump 005 完整 messages_history = **空**

```json
"messages": [
  {"role": "system", "content": "...【上游阶段摘要】..."},
  {"role": "user", "content": "【核心任务】..."}
]
```

用户在 Scout 阶段说过的关键意图：
- 「BU 代表公司，Code 才是店铺编码，Inc1 是店铺收入，Inc2 是店铺积分，Bos1-3 是费用」
- 「**只用店铺、周期、收入 3 个字段，其他都不用**」

**Cleaner 一个字都看不到**。它只通过结构化 `column_semantics`（target/features 列表）知道哪些列参与，但**用户为什么这样判断的语义信息全部蒸发**。这就是用户报告「阶段衔接差」的现行犯。

**根因（2 处叠加）**：

1. **build_prompt 设计层缺陷**：

```@/home/son_goku/HaGoKu/hagoku/context/project_context.py:194-200
        current_stage_entries = [e for e in self.entries if e.stage == agent]
        messages_history: list[dict[str, str]] = []
        for e in current_stage_entries:
            if e.type == "user_feedback":
                messages_history.append({"role": "user", "content": e.raw_user_text or e.content})
            elif e.type == "agent_response":
                messages_history.append({"role": "assistant", "content": e.content})
```

`messages_history` 只取 **`stage == agent`** 的 entries。Cleaner 启动时它自己的 stage 还没有 entries，所以 messages_history 必为空。

`upstream_summary` 只取 **agent_response.snapshot**（结构化字段），**完全不传 Scout 阶段的 user_feedback 原话**。

2. **Cleaner 拼装层遗漏**：

```@/home/son_goku/HaGoKu/hagoku/agents/cleaner/agent.py:578-583
        project_ctx = context.get("_project_context")
        if project_ctx:
            ctx_block = project_ctx.build_prompt("cleaner", context)
            messages[0]["content"] += "\n\n" + ctx_block["system_prefix"] + "\n\n" + ctx_block["upstream_summary"]
        for turn in conv_history[-6:]:
            messages.append({"role": turn.get("role", "user"), "content": turn.get("content", "")})
```

只用了 `system_prefix` 和 `upstream_summary`，**`messages_history` 字段直接丢弃**，转而循环旧通道 `conv_history[-6:]`——而 Cleaner 启动时 conv_history 为空。

---

### P4 🔴 Cleaner LLM 行为退化（用户报「白痴」的现行犯）

**现场**：dump 007（第 3 次 cleaner_dialogue）— **5 个连续 assistant turn**：

```
turn 1 (assistant): [调用] submit_assessment({"summary": "数据质量整体较好...", "columns": [...]})
turn 2 (assistant): <think>I need to evaluate the 4 columns...</think>
                    [调用] list_columns()
                    [调用] get_sample_rows({"column": "Code", "n": 10})
                    [调用] get_sample_rows({"column": "Period", "n": 10})
                    [调用] get_column_stats({"column": "Inc1"})
turn 3 (assistant): [调用] group_stats(...)  [调用] group_stats(...)
turn 4 (assistant): [调用] submit_assessment({...几乎相同的 summary...})
turn 5 (assistant): <think>All columns look clean...</think>
                    [调用] submit_assessment({...第 3 次几乎相同的 summary...})
```

**症状**：
- LLM **连续 3 次调用 `submit_assessment`**，每次内容几乎一样
- 在已有完整评估后还在执行 `list_columns` / `get_sample_rows` / `group_stats` 重新探索
- 多个 `[调用] xxx` 被串接到**单条 assistant content 字符串里**——不是合法的 OpenAI tool_calls 协议

**根因**：

```@/home/son_goku/HaGoKu/hagoku/agents/cleaner/agent.py:616
                    conv_history.append({"role": "assistant", "content": f"[调用] {fn.name}({fn.arguments})"})
```

Cleaner 把每次 tool_call **序列化成字符串** `"[调用] xxx({json})"` 塞进 conv_history.content。下一轮 LLM 调用时这些字符串被当作普通 assistant 消息回灌——**丢失了 OpenAI 协议中 tool_calls / tool_results 的语义关联**：

- 正确做法：assistant message 应含 `tool_calls` 字段（结构化），紧接着是 `role: "tool"` message 携带 `tool_call_id` + 工具返回值
- 实际做法：把工具调用降级为字符串，工具返回值压根不入 history

LLM 看到的是「我之前调过 `submit_assessment`，但没看到返回结果，再调一次吧」→ 反复调用、反复探索、**变白痴**。

**这才是用户说「白痴」的真正现行犯**——通道污染只是 P1/P2/P3 的间接症状，P4 才是 LLM 行为退化的直接原因。

---

### P5 🟡 conv_history 残留是阶段 2 任务 F 未完成

Cleaner system 已经接入 ProjectContext.build_prompt，但拼装仍用旧的 `_conversation_history`（cleaner/agent.py:582, 608, 624）。这是 spec §5.3 任务 F 要做的事，但当时审查方误判 Cleaner 没接入。

---

### P6 🟡 assistant content 信息空洞

dump 003 中 assistant 消息是「字段推断完成：理解 8 个字段」「无字段更新」——**LLM 实际调的 tool_calls 全部丢失**，下一轮 LLM 看到的是空话。

```@/home/son_goku/HaGoKu/hagoku/manager/orchestrator.py:1083-1089
            applied_summary = ", ".join(applied) if applied else "无字段更新"
            project_ctx.add_agent_response(
                stage="scout",
                revision=context.get("interaction_revision", 0),
                content=applied_summary,
                snapshot=project_ctx._derive_snapshot(context),
            )
```

只记录 applied 字段列表，**未记录 LLM 实际说了什么或调了什么工具**。

同 P4 根因——agent_response 设计上就是「字段更新摘要」而非「assistant 完整 turn」，所以 messages_history 中 assistant 内容必然空洞。

---

### P7 🟡 Cleaner system 字段信息三段重叠

dump 005 system 段：

```
当前字段状态:
  BU(公司): 参与  role=feature
  Code(店铺编码): 参与  role=feature
  ...
目标变量: Inc1                     ← 第 1 处
特征变量: BU, Code, Period          ← 第 2 处
【上游阶段摘要】
scout 阶段完成: target=Inc1, features=['BU','Code','Period'] × 5 ← 第 3 处
```

target 和 features 在 system 中出现 **7 次**（字段表 + 显式标注 + 5 条上游摘要）。冗余但不严重，相比 P1-P4 是小问题。

---

## 3. 重新审视阶段 3 范围

| spec §5 任务 | 原假设 | 实际情况 | 阶段 3 真实任务 |
|-------------|-------|---------|---------------|
| **A** Cleaner 接入 build_prompt | Cleaner 未接入 | Cleaner **已接入** | 修 Cleaner 拼装：丢 conv_history，改用 build_prompt 返回的 messages_history |
| **D** upstream_summary 被消费 | 死代码 | 已消费但**严重重复** | 修 build_prompt：每 stage 只保留最后一条 snapshot 摘要 + 加入用户原话摘要 |
| **F** 退役 conv_history | — | Cleaner 仍依赖 | 不变 |
| **新 G** | — | — | **修 P1**：调整 add_agent_response 与 USER_INPUT_RECEIVED 时序（或 build_prompt 内 user/assistant 配对重排） |
| **新 H** | — | — | **修 P4**：Cleaner conv_history 改为真实 OpenAI tool_calls 协议；tool_results 必须入 history |
| **新 I** | — | — | **修 P3 设计层**：build_prompt 的 upstream_summary 需含上游用户原话摘要（不只是 snapshot 结构化字段） |
| **新 J** | — | — | **修 P6**：agent_response.content 改为记录 LLM 实际输出，而非「字段更新摘要」 |

---

## 4. 优先级判断（审查方建议）

**Tier 1（必修，直接解决用户两个困惑）**：

- **P3 + 新 I**：Cleaner 看见上游用户原话——直接解决「阶段衔接差」
- **P4 + 新 H**：Cleaner tool_calls 协议合法化——直接解决「白痴」
- **P1 + 新 G**：messages_history 顺序——解决 LLM 看混乱对话历史

**Tier 2（设计层修复，提升健壮性）**：

- **P2**：upstream_summary 去重
- **P6 + 新 J**：agent_response.content 含 LLM 实际输出

**Tier 3（清理）**：

- **F**：conv_history 退役（Tier 1 修完后顺手）
- **P7**：字段信息三段重叠裁剪（低优）

---

## 5. 不在本阶段做

- Analyst / Reporter 接入（先在 Cleaner 验证修法）
- ProjectContext 持久化（与本现场无关）
- Scout `_infer_all_semantics` 改造（已 analysis_goal 兜底，足够）

---

## 6. 下一步

审查方根据本档案重写阶段 3 spec（替换原 §5 / §6 范围），提交给开发实施。

具体改动：

1. **重写 spec §5 任务清单**：从 A+D+F 改为 **G+H+I + Tier 1 修法**
2. **重写 spec §6 守门测试**：增加：
   - `test_cleaner看到scout用户原话`（P3 验收）
   - `test_messages_history顺序正确`（P1 验收）
   - `test_cleaner_tool_calls协议合法`（P4 验收）
   - `test_upstream_summary不重复`（P2 验收）

---

## 附录：完整 dump 文件位置

- `~/.hagoku/llm_dumps/001_scout_infer_all_semantics_*.json`
- `~/.hagoku/llm_dumps/002-004_scout_reply_review_*.json`
- `~/.hagoku/llm_dumps/005-007_cleaner_dialogue_*.json`


---

## Tier 1 后验收（2026-06-01）

- **新 dump 路径**：`~/.hagoku/llm_dumps/`（7 文件）
- **旧 dump 路径**：`~/.hagoku/llm_dumps_before_tier1/`（7 文件）

### 逐项对比

#### P1 — messages_history 顺序

| | 旧 dump (002-004) | 新 dump (002-004) |
|---|---|---|
| 002 顺序 | system → assistant → user | system → assistant → user |
| 003 顺序 | assistant → assistant → user → user (错乱) | **user → assistant → user ✅** |
| 004 顺序 | assistant → assistant → user → user → user | **user → assistant → user ✅** |

**结论**：✅ 通过。新 dump 中 assistant 在 user 之后出现，序列正确交替。旧 dump 中 assistant 总是堆在 user 前面。

**证据**：`003_scout_reply_review_20260601_111457.json` 显示 `user → assistant → user` 严格交替。

#### P2 — upstream_summary 去重

| | 旧 dump (005) | 新 dump (005) |
|---|---|---|
| 重复次数 | 5 条 "scout 阶段完成" | **1 条 ✅** |

**结论**：✅ 通过。去重生效，每 stage 只保留最后一条 snapshot。

#### P3 — Cleaner 看到上游用户原话

| | 旧 dump (005) | 新 dump (005) |
|---|---|---|
| 用户原话 | ❌ 无 | **✅ 3 条** |

新 dump 005 system 段末尾包含 `【上游用户原话】` 段，含 3 条 Scout 原话。

**结论**：✅ 通过。

#### P4 — Cleaner tool_calls 协议

| 检查项 | 旧 dump | 新 dump | 状态 |
|--------|---------|---------|------|
| conv_history 字符串序列化 | `"[调用] fn(args)"` | 已删除 ✅ | |
| OpenAI 标准协议 | 新旧两套并存 | 仅保留标准 ✅ | |
| 跨调用对话历史 | conv_history 保留 | **messages_history 未展开 ❌** | |

**结论**：🟡 部分通过。单次调用内协议已修复，但 `messages_history` 未在 Cleaner 拼装中展开——每次 `assess()` 调用重新起 messages，005-007 之间无对话累积。

#### H' 现象

Cleaner dump 005-007 每次都是 `system → user(intro)` 两条消息，无对话累积。**H' 需修**：Cleaner 需展开 `ctx_block["messages_history"]`。

### 验收总结

| 问题 | 结论 |
|------|------|
| P1 | ✅ 通过 |
| P2 | ✅ 通过（顺带修） |
| P3 | ✅ 通过 |
| P4 | 🟡 部分通过 |
| H' | ❌ 需修 |

**下一步**：H' 修复 + 进入 Tier 2。

---

## 命名澄清 + 任务 J 升 Tier 1（2026-06-01 review）

### 命名澄清

- **原 H'**（spec §5.1 任务 H 末尾备注）：单次 LLM response 多 tool_calls 时被拆成 N 个 assistant turn、`txt` 复制 N 次。当前 dump 在 `for _round` 循环之外只打一次，无法证伪，**暂搁置**。
- **本次 dump 验收发现**的「Cleaner 跨调用无对话累积」是**另一个独立问题**，正式命名为**任务 J**，与 H' 解耦。

### 任务 J — Cleaner / Analyst / Reporter 丢弃 `messages_history`（系统性违反律 3）

#### 现行犯

`cleaner_dialogue` 入口 dump（005/006/007）三次独立 `assess()` 调用 messages 永远是 `[system, user_intro]`，跨轮不累积。根因是 `build_prompt` 算出来的 `ctx_block["messages_history"]` 被丢弃。

#### 旁路扫描结果

| Agent | 文件位置 | 是否展开 `messages_history` |
|-------|---------|---------------------------|
| Scout | `@/home/son_goku/HaGoKu/hagoku/manager/orchestrator.py:921-927` | ✅ |
| Cleaner | `@/home/son_goku/HaGoKu/hagoku/agents/cleaner/agent.py:579-580` | ❌ |
| Analyst | `@/home/son_goku/HaGoKu/hagoku/agents/analyst/agent.py:874-875` | ❌ |
| Reporter | `@/home/son_goku/HaGoKu/hagoku/agents/reporter/agent.py:417-418` | ❌ |

四个 Agent 中三个违反律 3。这是 ProjectContext 接入时的统一遗漏，不是 Cleaner 单点 bug。

#### 影响

- 用户在 Cleaner 阶段做第 2 轮反馈时，第 2 次 `assess()` 看不到第 1 轮用户/助手对话 → 直接对应「LLM 变白痴」用户主诉。
- Analyst / Reporter 同病。

#### 修法

详见 spec §5.1 任务 J。范围：3 个 Agent 文件 + 守门测试。

---

## 任务 M 首次提交（commit 1e252f4）审查不通过 — 3 个 critical bug（2026-06-01）

### Bug 1：Analyst 根本没改

commit message 写「Analyst: _messages list 拼装后 extend」，`git show HEAD --stat` 显示**未触碰 `hagoku/agents/analyst/agent.py`**。`@/home/son_goku/HaGoKu/hagoku/agents/analyst/agent.py:872-876` 仍只拼 `system_prefix + upstream_summary`，丢弃 `messages_history`。

### Bug 2：Reporter 加了参数但 caller 没传

`@/home/son_goku/HaGoKu/hagoku/agents/reporter/agent.py:103-106` 改造 `_call_llm` 接口加 `messages_history` 参数 ✅，但唯一 caller `@/home/son_goku/HaGoKu/hagoku/agents/reporter/agent.py:425` 调用时未传该参数：

```python
response = self._call_llm(system=system, user=user_prompt)  # 缺 messages_history=
```

新参数成为死代码，Reporter 实际行为与改造前相同。

### Bug 3：守门测试错位（最严重）

`@/home/son_goku/HaGoKu/tests/test_product/test_stage_handoff.py` 的 `test_下游_agent_注入_messages_history` 测的是 **`build_prompt` 输出**，不是 **3 个 Agent 实际发给 LLM 的 messages**：

```python
block = ctx.build_prompt("cleaner", context={})
mh = block.get("messages_history", [])
assert len(mh) >= 2, ...
```

`build_prompt` 在任务 I 完成时已正确。这个 assert 即使 Cleaner / Analyst / Reporter 全部丢弃 `messages_history` 也照样过 → 不构成守门。

### 影响

测试全绿但实际只有 Cleaner 真接上 `messages_history`，Analyst / Reporter 仍违反律 3。如未及时复盘，下次 dump 验收会再次发现「LLM 跨轮无记忆」。

### 修法

补 Analyst extend、补 Reporter caller 参数、新增 spy LLM client 真守门测试。详见 spec §5.1 任务 M 重做指引。

---

## 任务 M 第二次提交（commit 7a522fb）审查 — 🟡 部分通过 + Bug 4 + 覆盖缺口（2026-06-01）

### ✅ 通过项

- Analyst 真改对：`@/home/son_goku/HaGoKu/hagoku/agents/analyst/agent.py:879-883` 用 `_analyst_messages` 拼装含 `messages_history.extend`
- Cleaner 守门测试可证伪：用「锚点_确认_A/B」字符串锚点，删 extend 必 fail
- 旧测试改名 `test_build_prompt_messages_history_分组` 归位
- 38 测试全绿

### ❌ Bug 4：Reporter `rpt_history` 未定义 — 运行时 NameError

`@/home/son_goku/HaGoKu/hagoku/agents/reporter/agent.py:417-425`：

```python
project_ctx = context.get("_project_context")
if project_ctx:
    ctx_block = project_ctx.build_prompt("reporter", context)
    system += "\n\n" + ctx_block["system_prefix"] + "\n\n" + ctx_block["upstream_summary"]
…
response = self._call_llm(system=system, user=user_prompt, messages_history=rpt_history)
```

**`rpt_history` 从未赋值**，全文件只有 L425 一处提到该名字。Reporter 每次跑都会 `NameError: name 'rpt_history' is not defined`。

测试全绿是因为**没有任何测试触发 Reporter LLM 路径**——bug 被「未覆盖」遮蔽。

### ⚠️ 覆盖缺口

守门测试 `test_下游_agent_实际注入_messages_history` 只 spy 了 Cleaner，**Analyst 与 Reporter 没有真守门**。这正是 Bug 4 没被测试抓到的根因。

### 反思与机制改进

「测试全绿」≠「代码正确」，仅意味着「测试覆盖到的路径正确」。本次重做引入了 Bug 4 + 覆盖缺口同时发生，二者互相掩护：

- 如有 Reporter 真守门 → Bug 4 必被抓到（spy 调用前就 NameError）
- 如无 Bug 4 → 覆盖缺口仅暴露为「Reporter 改动无验证」，相对低危

教训：**律 3 这种横切关注点的守门测试必须参数化覆盖所有应遵守的 Agent**，否则等于只测了 1/3。建议把「Agent 横切关注点测试必须穷举所有 Agent」上升到 CLAUDE.md 守则或 spec §6 验收规则。

### 修法

详见 spec §5.1 任务 M「第二次重做指引」。范围：Reporter rpt_history 初始化 + 守门测试参数化为 cleaner/analyst/reporter 三 Agent。



---

## M 任务完成后更新（2026-06-01 终）

| 问题 | 状态 |
|------|------|
| P1 messages_history 顺序 | ✅ G 修复 |
| P2 upstream_summary 重复 | ✅ I 顺带修复 |
| P3 Cleaner 看不到上游原话 | ✅ I 修复 |
| P4 tool_calls 协议 | ✅ H 修复 |
| P5 conv_history 残留 | ✅ F 守门测试 |
| P6 agent_response 内容空洞 | ⏸️ 任务 K 待做（需改函数签名） |
| P7 字段信息重叠 | ⏸️ 任务 L 低优 |
| M 下游 Agent messages_history | ✅ 三 Agent 全注入 + 守门测试 |

剩余工作：K（Tier 2 设计层）、L（低优裁剪）、重跑 dump 验证
