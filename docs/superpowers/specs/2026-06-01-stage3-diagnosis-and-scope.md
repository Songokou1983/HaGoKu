# 阶段 3 诊断与范围 spec

**日期**：2026-06-01
**状态**：待诊断 → 待评审 → 待实施
**作者**：审查方（Cascade）
**实施方**：开发

---

## 0. Onboarding（实施方必读）

### 0.1 阅读顺序（约 15 分钟）

1. **`CLAUDE.md`** — AI 实现者铁律（律 1-7、通道规则、自检流程）。每次 commit message 必须有「【自检】」段
2. **本 spec 全文** — 重点看 §1 现状、§3 实施清单、§7 实施步骤
3. **`docs/decisions/ADR-005-project-context-memory-system.md`** — ProjectContext 为什么存在、设计意图
4. **`docs/superpowers/specs/2026-05-30-project-context-memory-design.md` §3.5「集成点」** — 三层注入分工，理解为什么诊断要看「通道污染」

### 0.2 选读（遇到具体问题再翻）

- `docs/cases/2026-05-26-restrict-analysis-to-failure.md` — 现行犯档案模板，本次 case 按此格式
- `tests/README.md` — 5 层测试金字塔（dump 加了不能挂现有测试）
- `DEVELOPMENT_PROMPT.md` — 提交流程

### 0.3 当前任务（仅一件）

**第 0 步：诊断 dump**（详见 §4）

按 §4.2 加 dump 代码 → 跑一次 test0526 类场景 → 把 `.hagoku/llm_dumps/<run_id>/` 整个目录交给审查方。

**严格只做这一件事**——不要顺手改 prompt、不要改通道、不要动 Cleaner。dump 完才决定阶段 3 真实范围。

### 0.4 完成标志

```bash
HAGOKU_DUMP_LLM=1 <你的启动方式>
# 跑一遍：上传数据 → Scout 字段评审 1-2 轮 → 进 Cleaner 看到清洗策略
ls .hagoku/llm_dumps/<run_id>/
# 期望看到 4-6 份 JSON：
#   001_scout_infer_all_semantics_*.json
#   002_scout_reply_review_*.json   （字段评审每轮一份）
#   003_cleaner_dialogue_*.json
#   004_cleaner_planning_*.json
```

### 0.5 Commit message 模板

```
chore: 加 LLM messages 诊断 dump（HAGOKU_DUMP_LLM=1 开关）

Issue：阶段 3 前置诊断（本 spec §4）
范围：仅加观测，不改业务逻辑。诊断完成后整体删除。

【自检】判断：LLM 拿到分析目标和数据后能自己判断 [X] 吗？
答案：N/A — 本次只加观测，不改决策路径
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

## 5. 第 1 步：阶段 3 范围（候选：A + D + F）

> ⚠️ 确认范围前必须先完成 §4 诊断。本节仅是当前最可能的方向，dump 结果可能调整任务取舍。

### 5.1 任务 A：Cleaner 接入 ProjectContext.build_prompt

**目标**：Cleaner 启动时看到 Scout 阶段用户与 LLM 的全部对话记忆。

**改动**：

- `hagoku/agents/cleaner/agent.py`
  - `cleaner_dialogue` 入口：注入 `_project_context`（从 context dict 取）
  - 调 `project_ctx.build_prompt("cleaner", context)` 得到 `{system_prefix, upstream_summary, messages_history}`
  - 用 system_msg + system_prefix + upstream_summary 拼 system role；展开 messages_history
  - 兼容旧路径：`if project_ctx is None` 走最小降级 + warning（参考 Scout 现写法）

- `hagoku/manager/orchestrator.py`
  - 调 cleaner 前确保 `context["_project_context"]` 已注入（Scout 路径已有，Cleaner 路径需补）

### 5.2 任务 D：upstream_summary 真正被消费

**目标**：build_prompt 输出的 upstream_summary 字段不再是死代码。

**已具备**：`@/home/son_goku/HaGoKu/hagoku/context/project_context.py:155-169` 已计算

**待办**：在 A 落地的同时，确保 Cleaner 的 system role 拼接 upstream_summary。Scout 阶段不需要（无上游）。

### 5.3 任务 F：退役 `_conversation_history`

**目标**：消除并行通道，ProjectContext 单一权威。

**改动**：

- 移除 `hagoku/agents/cleaner/agent.py:574, 608, 624` 处对 `_conversation_history` 的读写
- 移除 `hagoku/manager/orchestrator.py:961` 的同名引用
- doctrine 守门测试 `tests/test_doctrine_compliance.py` 加新条目：`_conversation_history` 字面量不得残留（如 `_session_messages` 已守门）

### 5.4 暂不做（推迟阶段 4+）

- Analyst 接入：模式可能不同，等 Cleaner 验证后再判断
- Reporter 接入：低优先
- 崩溃恢复持久化：与本次困惑无关

---

## 6. 第 2 步：跨阶段衔接守门测试

新增 `tests/test_product/test_stage_handoff.py`，至少包含：

```python
def test_律3跨阶段_cleaner看到scout用户原话():
    """Cleaner 启动时 LLM 调用的 messages 中应包含 Scout 阶段的关键用户反馈。

    场景：用户在 Scout 阶段说「Code 是店铺编号，不参与分析」
    断言：进入 Cleaner 后，第一次 LLM 调用 messages_history 或 upstream_summary
          中存在该原话或其结构化摘要。
    """
    # 用 LLMSpy 拦截 Cleaner 的 client.chat.completions.create
    # 跑通 Scout 字段评审 → emit AGENT_COMPLETED → 进 Cleaner
    # 断言 LLMSpy.last_messages 含目标信息


def test_律5_cleaner不读_conversation_history():
    """守门：F 任务完成后，Cleaner 路径不再依赖 _conversation_history。"""
    # 启动 cleaner_dialogue 但 context 中无 _conversation_history 键
    # 期望不报错、能正常运行（数据来自 ProjectContext）


def test_upstream_summary有内容_当下游agent调用buildprompt():
    """A + D 联合守门：Cleaner 调 build_prompt 时 upstream_summary 非空。"""
    # 构造 ProjectContext，scout 阶段已 add_agent_response
    # ctx.build_prompt("cleaner", context)["upstream_summary"] 应含 scout 摘要
```

**这三条是阶段 3 验收硬指标**——任一未过不能合并。

---

## 7. 不做什么（边界）

- 不重构 system_msg 文本本身（属 prompt 工程，与通道无关）
- 不改 ProjectContext 数据模型（律 5 已稳定）
- 不动 EventBus 订阅机制
- 不引入持久化（阶段 4+ 工作）
- 不改 Analyst / Reporter（待 Cleaner 验证后决策）

---

## 8. 实施步骤总览

```
[ ] 1. 开发实施 §4：加 llm_dump.py + 4 处 hook（HAGOKU_DUMP_LLM=1 开关）
[ ] 2. 开发跑一次真实场景（test0526 类型）→ 把 dump 文件交给审查方
[ ] 3. 审查方填写 docs/cases/2026-06-01-stage3-channel-pollution.md
[ ] 4. 审查方根据 case 调整 §5 任务取舍（确认 A/D/F 是否仍合理）
[ ] 5. 开发实施 A + D + F
[ ] 6. 开发实施 §6 三条守门测试
[ ] 7. 审查方做最终审查 → 合并
```

每一步完成后由审查方批准才进入下一步。

---

## 9. 提交格式

按 CLAUDE.md 要求：

```
fix/refactor/feat: <精简标题>

Issue / 动机：[一句话说明本次修法对应哪个困惑或哪个 case]

【自检】判断：LLM 拿到分析目标和数据后能自己判断 [X] 吗？
答案：能 → 不写规则，只送数据 / 不能 → 代码的活
```
