# 阶段 3 诊断与范围 spec

**日期**：2026-06-01
**状态**：诊断完成（2026-06-01 17:35）→ 范围已重写 → 待开发实施
**诊断产出**：`docs/cases/2026-06-01-stage3-channel-pollution.md`（7 项问题已定位）
**作者**：审查方（Cascade）
**实施方**：开发

---

## 0. Onboarding（实施方必读）

### 0.1 阅读顺序（约 15 分钟）

1. **`CLAUDE.md`** — AI 实现者铁律（律 1-7、通道规则、自检流程）。每次 commit message 必须有「【自检】」段
2. **`docs/cases/2026-06-01-stage3-channel-pollution.md`** — 诊断 case。所有 P1-P7 问题现场 + 根因都在这里。实现任何任务前必读该任务对应的 P 项
3. **本 spec §5 / §6** — 任务定义 + 验收守门测试
4. **`docs/decisions/ADR-005-project-context-memory-system.md`** — ProjectContext 设计意图（设计背景）

### 0.2 选读（遇到具体问题再翻）

- `docs/cases/2026-05-26-restrict-analysis-to-failure.md` — 现行犯档案模板，本次 case 按此格式
- `tests/README.md` — 5 层测试金字塔（dump 加了不能挂现有测试）
- `DEVELOPMENT_PROMPT.md` — 提交流程

### 0.3 当前任务

**阶段【Tier 1 修复】**（详见 §5.1）—— G → H → I 顺序独立完成。

**每一个任务一次 commit，提交后暂停等审查方 review**，过了再推下一个。不要一口气拼完 3 个。

**只动 spec 中明确点名的代码**——不要顺手重构、不要改 prompt 文本、不要动 Analyst / Reporter。

### 0.4 当前任务验收

Tier 1 三个任务都完成后：

```bash
HAGOKU_DUMP_LLM=1 <你的启动方式>
# 跑同样场景
ls ~/.hagoku/llm_dumps/  # 看新 dump
```

对比旧 dump（在 `docs/cases/2026-06-01-stage3-channel-pollution.md` 里）验证：

- P1 修了：messages 顺序严格 user/assistant 交替
- P3 修了：Cleaner messages 中能看到 Scout 阶段用户原话
- P4 修了：Cleaner messages 中 tool_calls 是结构化字段，不是 content 字符串

### 0.5 Commit message 模板

```
fix: 任务 G（或 H / I）— <精简标题>

Issue：阶段 3 Tier 1（本 spec §5.1）修 P1 / P3 / P4 之一
范围：只动 spec 点名的文件，不越茂

【自检】判断：LLM 拿到分析目标和数据后能自己判断 [X] 吗？
答案：<能 → 不写规则 / 不能 → 代码的活>
```

---

## 1. 背景

阶段 1 / 2 已完成 ProjectContext 接入，但仅 Scout 走通。用户报告两个困惑：

1. **「LLM 进入项目变白痴」** — 怀疑通道 / 提示词污染。开发一度加了一个旁路（已要求去除），属症状信号。
2. **「阶段衔接（Scout → Cleaner）问题很大」** — 字段理解到字段清洗的语义衔接断裂。

审查方已基于代码现状做出**根因假设**（见 §2），但**必须先诊断现行犯再决定方案**。本 spec 提供：

- §2 现状审计（已知事实）
- §3 根因假设
- §4 第 0 步：诊断 dump（开发实施）
- §5 第 1 步：基于 dump 输出的阶段 3 范围（候选 A+D+F）
- §6 第 2 步：跨阶段衔接守门测试

---

## 2. 现状审计（已知事实）

### 2.1 ProjectContext 接入覆盖

| Agent | 接入 ProjectContext.build_prompt | 旧通道残留 |
|-------|----------------------------------|------------|
| Scout `_apply_scout_reply_with_llm`（字段评审） | ✅ | 已退役 |
| Scout `_infer_all_semantics`（初始字段推断） | ❌ 仍走 bare prompt + payload JSON 兜底 | — |
| Cleaner `cleaner_dialogue` | ❌ | `_conversation_history` 仍在 |
| Cleaner 一次性清洗规划 | ❌ | system_prompt 来自 prompt.md，无上游摘要 |
| Analyst | ❌ | `_conversation_history` |
| Reporter | ❌ | 独立 |

### 2.2 LLM 调用通道（多源）

Scout 字段评审一次调用塞入：

```
system_role:
  [静态角色 system_msg_for_llm]
  + [system_prefix（含 analysis_goal + 字段表 + features + pending + _pending_command_text）]
  + [upstream_summary（Scout 阶段为空）]
messages_history: [前 N 轮 user/assistant 实际反馈]
user: [本轮原话]
```

Scout `_infer_all_semantics`（初始）走另一通道：

```
system: [analysis_goal_section（兜底）] + [submit_field_inference 工具指示] + [knowledge_section] + [memory_notes]
user: [payload JSON（含 user_query / 字段元数据）]
```

Cleaner `cleaner_dialogue` 走第三通道：

```
system: [prompt.md 静态规则]
messages: [conv_history 自维护数组]
user: [本轮]
```

**三个通道并行**，没有统一权威，正是「白痴」嫌疑的最大根因。

### 2.3 阶段衔接现状

`@/home/son_goku/HaGoKu/hagoku/context/project_context.py:155-169` 已经计算 `upstream_summary`，**但只有 Scout `_apply_scout_reply_with_llm` 调 build_prompt，Cleaner 不调用**。所以：

- Cleaner 启动时 → 读 `context` dict（结构化 column_semantics），看不到 Scout 与用户的对话历史
- Cleaner 不读 ProjectContext.entries，更不读 upstream_summary
- 律 3「跨阶段记忆」**仅在 Scout 内部生效**，跨阶段失效

---

## 3. 根因假设

两个困惑大概率**同源**：

> **ProjectContext 设计是「全 Agent 唯一通道」，但只装到了 Scout。**

具体推导：

1. **「LLM 白痴」根因 = 通道污染 + 信号过载**
   - Scout 调用塞 5 类信息（system_msg + system_prefix + upstream_summary + messages_history + user），其中 system_prefix 已含字段表全量，可能与 messages_history 中 assistant 状态摘要重复
   - `_infer_all_semantics` 走 bare prompt 通道，与字段评审通道不一致——LLM 在两次调用间「人格切换」
   - knowledge_section / memory_notes 累加 → 信号噪声比恶化

2. **「阶段衔接差」根因 = upstream_summary 没人消费 + 多通道平行**
   - upstream_summary 算了不发送 = 死代码
   - Cleaner 用 `_conversation_history`，与 ProjectContext 完全隔离
   - 没有跨阶段「信息抵达」守门测试，问题永远不可见

**但假设≠定论**——必须看真实 dump 才能确认到底是哪一段污染最重。

---

## 4. 第 0 步：诊断 dump（开发实施，预计 0.5 天）

### 4.1 目标

落盘所有 LLM 调用的完整 messages，量化通道污染与衔接断点。

### 4.2 实施清单

**新建文件**：`hagoku/observability/llm_dump.py`

- 提供 `dump_messages(stage, messages, model, run_id=None, extra=None)` 函数
- 由 env 开关控制：`HAGOKU_DUMP_LLM=1` 才生效，默认 OFF
- 输出路径：`.hagoku/llm_dumps/<run_id>/<seq>_<stage>_<ts>.json`
- 失败不影响主流程（捕获异常 + warning 日志）

**Hook 4 个调用点**：

| 调用点 | 文件 | 行号附近 | stage 标识 |
|--------|------|---------|-----------|
| Scout 初始字段推断 | `hagoku/agents/scout/agent.py` | 640 | `scout_infer_all_semantics` |
| Scout 字段评审 | `hagoku/manager/orchestrator.py` | 944 | `scout_reply_review` |
| Cleaner 多轮对话 | `hagoku/agents/cleaner/agent.py` | 597 | `cleaner_dialogue` |
| Cleaner 一次性清洗规划 | `hagoku/agents/cleaner/agent.py` | 809 | `cleaner_planning` |

每处在 `client.chat.completions.create(...)` 调用**之前**插入 `dump_messages(stage, messages, model, run_id=..., extra=...)`，extra 至少包含：当前 query / via_project_ctx / tools 名。

### 4.3 验证

```bash
HAGOKU_DUMP_LLM=1 .venv/bin/python -m hagoku.api.server  # 或常规启动方式
# 完成一次 test0526 类型场景：上传数据 → Scout 字段评审 1-2 轮 → 进 Cleaner
ls .hagoku/llm_dumps/<run_id>/  # 期望看到 4-6 份 JSON
```

### 4.4 现行犯档案产出

跑完后，**审查方填写**：

新建 `docs/cases/2026-06-01-stage3-channel-pollution.md`，包含：

- 每个 stage 的 messages 长度统计（system 段 / messages_history / user）
- 列出 system 段中**重复信息**位置（例：字段表在 system_prefix 出现一次，又在 messages_history 的 assistant 内容中重复）
- 标注「可删」「应迁移」「保留」三类
- Scout vs Cleaner 通道差异截图（对比 system 块）
- 列出 Cleaner 启动时**没看到**但应该看到的 Scout 阶段信息（衔接断点）

完成后**才**进入第 1 步。

---

## 5. 第 1 步：阶段 3 范围（已重写）

> **重要**：本节于 2026-06-01 根据诊断 case 重写。原候选范围 A+D+F 使命宣告废弃。诊断 case 中 Cleaner 被发现已接入 ProjectContext，但 build_prompt 本身有 3 处设计缺陷 + Cleaner 拼装有 1 处遗漏。本阶段范围重定向为「修 build_prompt + Cleaner tool_calls 协议」。

### 5.1 Tier 1：直接解决用户两个困惑的修复

#### 任务 G：修复 messages_history 顺序错乱（P1）

**现状**：`add_agent_response` 在 `_apply_scout_reply_with_llm` 函数内写入（L1077），早于函数返回后 emit 的 `USER_INPUT_RECEIVED`（约 L2290）。entries 中 agent_response 永远在 user_feedback 之前 → build_prompt 输出 `assistant×2 → user×2` 序列。

**修法二选一**：

- **G1（推荐，改时序）**：将 `_apply_scout_reply_with_llm` 内部 `add_agent_response` 从函数内移出。改为：orchestrator 主环以 `USER_INPUT_RECEIVED → 函数调用 → AGENT_COMPLETED` 顺序控制。让 EventBus 事件顺序反映真实对话顺序。
- **G2（保守，不改时序，改 build_prompt）**：在 `ProjectContext.build_prompt` 中对 entries 做 `user/assistant` 配对重排（同 revision 内 user 在前 assistant 在后）。

**选择**：G1。G2 是掌责补丁，变量同步不严谨的设计愿望在远期会复响。

#### 任务 H：修复 Cleaner tool_calls 协议违反（P4 —— 「白痴」的真现行犯）

**现状**：`@/home/son_goku/HaGoKu/hagoku/agents/cleaner/agent.py:616` 把 tool_calls 序列化为字符串 `"[调用] {fn.name}({fn.arguments})"` 塑进 conv_history。下一轮 LLM 看到中文串但看不到 tool_call 结果。LLM 认为「以前调过 submit_assessment 但没看到返回」→ 反复调用、反复探索、表现「白痴」。

**改动**：

- `cleaner_dialogue` 内部重写 messages 累积逻辑：
  - 保留 LLM 返回的原始 assistant message（含 `tool_calls` 字段，不要序列化）
  - 工具返回值以 `{"role": "tool", "tool_call_id": tc.id, "content": result_json}` 形式追加
  - 下一轮调用时完整透传给 OpenAI
- 删除二次处理逻辑 `"[调用] xxx({json})"` 字符串拼接

**验收指标**：同一任务不再出现 LLM 重复调用 `submit_assessment` ；工具返回值出现在 dump messages 中。

**Follow-up H'（低优，不阻塞 Tier 1）**：当前实现（`@/home/son_goku/HaGoKu/hagoku/agents/cleaner/agent.py:617-630`）在循环中按每个 `tool_call` 各 append 一个 `assistant` message + 一个 `tool` message，导致：

- 同一次 LLM response 被拆成 N 个 assistant turn（应为 1 个含 N tool_calls 的 turn）
- `txt` 内容被复制 N 次，浪费上下文 token

OpenAI 协议接受这种结构（每对 assistant/tool 自洽），所以 H 主验收指标不受影响。但与「一次 LLM response = 一个 assistant turn」的最佳实践有距离。Tier 1 全部完成后跑新 dump，如果 dump 仍显示 `txt` 重复或上下文压力，再修为：1 个 assistant message 含全部 tool_calls + 紧跟 N 个 tool messages。修法约 5 行。

#### 任务 I：build_prompt upstream_summary 增加上游用户原话（P3 设计层修复）

**现状**：`@/home/son_goku/HaGoKu/hagoku/context/project_context.py:179-190` 的 upstream_summary 只取 `agent_response.snapshot` 结构化字段（target / features / pending），**不传上游 user_feedback 原话**。下游 Agent 一个字都看不到用户说过什么。

**改动**：`build_prompt` 拼装 upstream_summary 时，除 agent_response 结构化摘要外，加入上游阶段的关键 user_feedback 原话（以 raw_user_text 取原始，不刪减）。建议格式：

```
【上游阶段摘要】
scout 阶段完成: target=Inc1, features=['BU','Code','Period']

【上游用户原话】
(scout) BU 代表的是公司，Code 才是店铺的编码，…
(scout) 本次参与分析的应该是店铺、周期、收入3个字段…
```

**限制**：上游原话只取关键轮（含重点关键词的 user_feedback，可以先全部传，估评体量后再决定是否限后 N 条）。

### 5.2 Tier 2：设计层修复

#### 任务 J：upstream_summary 去重（P2）

**现状**：upstream_summary 重复 5 次「scout 阶段完成: target=Inc1, features=[...]」。每轮 Scout reply 都生一条 agent_response → 全部展开。

**改动**：`@/home/son_goku/HaGoKu/hagoku/context/project_context.py:179-190` 使用 OrderedDict + key（stage + snapshot 摘要哈希）去重；**或者**按 stage 分组仅取最后一条 snapshot 生成摘要。

**选择**：后者（每 stage 取最后一条）——状态是递进的，只需最新快照。

#### 任务 K：agent_response.content 记录 LLM 实际输出（P6）

**现状**：`@/home/son_goku/HaGoKu/hagoku/manager/orchestrator.py:1083` 只记 `applied_summary`（「无字段更新」/「BU←公司」这种摘要）。LLM 实际调的 tool_calls / 思考全部丢。

**改动**：agent_response.content 同时保留 LLM 原始 assistant turn（含 raw_text + tool_calls）。拆为两个字段或考虑为 entry 加 `tool_calls` 结构化字段。

**依赖**：H 在 Cleaner 侧已设计不序列化 tool_calls，本任务是在 ProjectContext 侧同步设计。

### 5.3 Tier 3：清理

#### 任务 F（原 spec）：退役 `_conversation_history`

**现状**：Cleaner system 已走 build_prompt，但 messages 拼装仍循环 `conv_history[-6:]`。H 完成后顺手退役。

**改动**：

- `cleaner_dialogue` 拼装改为用 `ctx_block["messages_history"]` 展开，删除 `conv_history` 逻辑
- 同步删 `hagoku/manager/orchestrator.py:961` 引用
- `tests/test_doctrine_compliance.py` 加守门：`_conversation_history` 字面量不得出现于 `hagoku/agents/` 和 `hagoku/manager/`

#### 任务 L（低优）：system 字段信息三段重叠（P7）

**现状**：system 中 target / features 出现 7 次（字段表 + 显式标注 + upstream_summary×5）。

**改动**：J 完成后重复度会从 7 降到 3；如需进一步裁减，删「目标变量 / 特征变量」两行（信息在字段表中已含）。可选。

### 5.4 暂不做（推迟阶段 4+）

- Analyst / Reporter 接入：等 Cleaner 验证 G/H/I 修法实际效果后再判断
- 崩溃恢复持久化：与本次困惑无关
- Scout `_infer_all_semantics` 接入 build_prompt：已 analysis_goal_section 兜底，当前可接受

---

## 6. 第 2 步：跨阶段衔接守门测试（验收硬指标）

新增 `tests/test_product/test_stage_handoff.py`，包含以下 5 条：

```python
# ===== Tier 1 验收（3 条必备）=====

def test_messages_history_顺序_user_assistant_交替():
    """任务 G 验收：scout 用户连续 2 轮反馈后，第 3 轮 build_prompt 输出的 messages_history
    严格按 user → assistant → user → assistant 交替顺序。不能出现 assistant×2 → user×2。"""
    # 构造 ProjectContext，按真实时序 emit USER_INPUT_RECEIVED + AGENT_COMPLETED
    # 断言 build_prompt("scout", context)["messages_history"] 顺序严格交替


def test_cleaner_看到_scout_用户原话():
    """任务 I 验收：scout 阶段用户说「只用店铺、周期、收入 3 个字段」，进入 Cleaner 后
    LLM 首次调用 messages 中含该原话（或 ±8 个字的子串）。"""
    # LLMSpy 拦截 Cleaner client
    # 断言 system 或 messages_history 中出现该原话子串


def test_cleaner_tool_calls_协议合法():
    """任务 H 验收：Cleaner 多轮 dialogue 后，messages 中任何 assistant turn 含 tool_calls 的：
      1) 使用 OpenAI tool_calls 结构字段，不是 content 字符串中存 '[调用] xxx({...})'。
      2) 紧跟一条 role=tool message，携带 tool_call_id。
    同任务下 LLM 不重复调用 submit_assessment 超过 1 次。"""
    # 构造 Cleaner 多轮调用，检查 messages 结构


# ===== Tier 2 验收（2 条）=====

def test_upstream_summary_不重复():
    """任务 J 验收：scout 阶段 add_agent_response 5 次后，Cleaner 调 build_prompt 输出的
    upstream_summary 中 'scout 阶段完成' 只出现 1 次。"""
    # 构造 5 次 add_agent_response
    # 断言 upstream_summary.count('scout 阶段完成') == 1


def test_agent_response_含_LLM_原始输出():
    """任务 K 验收：_apply_scout_reply_with_llm 调用后，entries 中最新一条 agent_response
    的字段含 LLM 原始 tool_calls 信息，不是仅「无字段更新」这种摘要。"""
    # Spy 返回 tool_calls，验证 entry.content 或新增字段保留原始信息
```

**Tier 1 三条必过才能合并。Tier 2 两条验收设计层修复**。

另需修复 1 个独立问题：

- **孤儿测试**：`tests/test_product/test_information_arrival.py:149` 仍 import `_detect_user_intent_via_llm`（已在 commit 1d30f5a 被删）——修复或删除该测试

---

## 7. 不做什么（边界）

- 不重构 system_msg 文本本身（属 prompt 工程，与通道无关）
- 不动 EventBus 订阅机制（G 任务仅调整 emit 顺序，不改 subscribe 逻辑）
- 不引入持久化（阶段 4+ 工作）
- 不改 Analyst / Reporter（待 Cleaner 验证后决策）
- 不补丁 Scout `_infer_all_semantics`（analysis_goal_section 兜底已够用）
- 任务 K 可能需调整 ProjectContextEntry 数据模型（增加 `tool_calls` 字段），是本阶段唯一允许的模型变动

---

## 8. 实施步骤总览

```
[✅] 1. 开发实施 §4：加 llm_dump.py + 4 处 hook
[✅] 2. 开发跑一次真实场景 → 交付 7 份 dump
[✅] 3. 审查方填写 docs/cases/2026-06-01-stage3-channel-pollution.md
[✅] 4. 审查方重写阶段 3 范围（本 spec §5 / §6）
[ ] 5. 开发实施 Tier 1：G → H → I（3 个任务顺序独立完成，每个任务一次 commit + 审查方 review）
[ ] 6. 开发实施 Tier 2：J + K
[ ] 7. 开发实施 Tier 3：F（退役 conv_history）+ L（如需）
[ ] 8. 开发实施 §6 五条守门测试
[ ] 9. 开发补丢失测试：修/删 test_information_arrival.py:149 孤儿 import
[ ] 10. 再跑一次 HAGOKU_DUMP_LLM=1 场景 → 交新 dump
[ ] 11. 审查方对比新旧 dump 证明 7 项问题都修了 → 合并、删除 llm_dump 环境开关代码
```

每个 Tier 完成后由审查方批准才进入下一个。不要一口气做完所有任务。

---

## 9. 提交格式

按 CLAUDE.md 要求：

```
fix/refactor/feat: <精简标题>

Issue / 动机：[一句话说明本次修法对应哪个困惑或哪个 case]

【自检】判断：LLM 拿到分析目标和数据后能自己判断 [X] 吗？
答案：能 → 不写规则，只送数据 / 不能 → 代码的活
```
