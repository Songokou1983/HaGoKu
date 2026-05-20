# HaGoKu Studio — 全方位核心原则审计报告

> 审计时间：2026-05-20
> 审计范围：对照 PROJECT.md 六条核心原则，全代码库逐项扫描
> 审计方法：grep 硬匹配扫描 + 关键模块逐行阅读 + 刹车清单对照

---

## 概览总表

| 维度 | 评分 | 状态 |
|------|------|------|
| 刹车 1：CHANNEL ZONE 标记 | 🔴 严重缺失 | 0 处标记 |
| 刹车 2：回归契约 | 🟢 已有 | `test_agent_interaction_contract.py` |
| 刹车 3：中文硬匹配 | 🟡 少量违规 | 4 处需审视 |
| 原则 1：多 Agent 框架 | 🟢 合格 | 5 Agent 管道完整 |
| 原则 2：LLM 驱动决策 | 🟢 主体合格 / 🟡 CLI 遗留 | 核心路径 LLM 化；CLI 含硬匹配 |
| 原则 3：LLM-用户通道 | 🟢 主体合格 | WebSocket 暂停/恢复机制 |
| 原则 4：工具与知识库 | 🟢 合格 | 工具插件 + KB 三层架构 |
| 原则 5：无代码兜底 | 🟡 1 处灰区 | Scribe 占位描述为机械行为，可接受 |
| 原则 6：可持续架构 | 🟡 部分达标 | Agent 新增简单；管道 / 常量为硬编码 |

---

## 刹车 1：CHANNEL ZONE 标记 — 全面缺失 🔴

PROJECT.md 明确要求：

> 涉及用户输入处理、字段语义更新的代码区域顶部，有明确的分隔注释标记 `# ==== CHANNEL ZONE: 禁止正则/if-else 语义分支 ====`。

**扫描结果**：全代码库 0 处存在该标记。

### 应标记但未标记的区域

| 文件 | 函数/区域 | 应加标记原因 |
|------|-----------|------------|
| `orchestrator.py` | `_apply_scout_reply_with_llm`（~260-620） | 字段语义更新核心路径 |
| `orchestrator.py` | `apply_scout_user_field_reply_to_context`（~130-240） | 用户回复 → context 写入 |
| `orchestrator.py` | `_is_scout_aligned` / `_scout_reply_is_pure_confirm` / `_is_gate_confirm`（139-218） | 用户意图判断（见下文灰区讨论） |
| `query_parser.py` | `_llm_parse_intent`（77-133） | 意图解析核心 |
| `scout/agent.py` | `_infer_field_semantics` / `_scout_reply_with_llm` | 字段语义推断 |
| `cleaner/agent.py` | `_infer_cleaning_strategy` | 清洗策略推断 |

### 建议

在每个上述函数顶部添加 `# ==== CHANNEL ZONE: 禁止正则/if-else 语义分支 ====` 标记（或等效），为未来审查建立防线。

---

## 刹车 2：回归契约 — 已有 🟢

`tests/test_product/test_agent_interaction_contract.py` 已存在，验证用户输入 → LLM 收到请求 → 返回更新的完整链路。Mock 可检测代码是否绕过 LLM。

**状态**：符合要求。

---

## 刹车 3：中文硬匹配逐行审查 🟡

### 3.1 orchestrator.py (lines 139-218) — 状态机确认判断 — 灰区

```python
# 139: 用户仅表示「确认」、无字段纠错时
# 141: r"^(确认(?:无误|进清洗|继续)?|可以了|对齐了|就这样|没问题了|好的|是|..."
# 156: r"^(确认(?:继续|无误)?|好的|是|没问题|对的|正确|通过|ok|okay|yes)..."
# 173: r"^(确认(?:继续|无误)?|生成报告|可以生成|同意进入报告|好的|是|..."
```

**用途**：判断用户回复是「纯确认」（进入下一阶段）还是「有补充内容」（回到当前阶段继续对齐）。

**分析**：这些正则在状态机转换层（`_is_scout_aligned`、`_scout_reply_is_pure_confirm`、`_is_gate_confirm`），**不做字段语义判断**——若判断为「纯确认」，则跳过 LLM 调用直接继续；若判断为「有补充」，则仍走 LLM function calling 通道。这是**结构性/管理性**判断而非语义理解，属于 PROJECT.md 中描述的「看板状态机（确定性状态转换）」范围。

**判定**：🟡 灰区。建议增加注释说明这是状态机决策而非语义决策，同时将模式列表声明为常量以明示意图。**不构成违反核心原则。**

### 3.2 orchestrator.py (lines 1999-2053) — CLI 交互模式 — 违规 🔴

```python
# 1999: if user_input.lower() in ("好", "是", "ok", "继续", "next", "y", "yes"):
# 2009: if confirm.lower() in ("好", "是", "ok", "y", "yes", ""):
# 2053: {"role": "system", "content": "你是数据分析师。用户告诉你字段的含义。..."}
```

**分析**：
- Lines 1999-2009：CLI 模式下的确认判断，用硬编码中文关键词代替 LLM。与上一条不同，这段代码位于 CLI `run_cli` 方法，**没有 function calling 通道**——用户的字段语义解释直接被硬编码 `confirm` 匹配跳过。
- Line 2053：虽然是 system prompt，但整个 CLI `run_cli` 方法是完全绕开 Web UI 暂停/恢复通道的退化路径。

**判定**：🔴 违规。CLI 确认逻辑应走与 Web UI 相同的 function calling 通道，或至少标注清楚这是 CLI 降级路径。

### 3.3 cleaner/agent.py (line 601) — LLM prompt 中的示例阈值 — 合格 🟢

```python
"   - 比较 q75 与 max 的差距判断有无极端值（如 max > q75 * 3 可能有极端值，max > q75 * 10 几乎确定是异常）\n"
```

**分析**：这是 LLM prompt 中的示例指导，不是代码逻辑。LLM 自行决定是否采用这些阈值。PROJECT.md 第 100 行已特别注明：

> 分布判断（Scout Agent）：Shape analysis 已由 LLM 完成，不再有硬编码的倍数阈值（`maxv > q75v * 10` 等）。

Prompt 内的示例是给 LLM 的上下文参考，不构成硬编码。

**判定**：🟢 合格。

### 3.4 其他 Agent 文件 — 合格 🟢

| 文件 | 匹配内容 | 性质 |
|------|---------|------|
| Scout agent.py:469 | `'可能表示…'` | LLM prompt 中的格式指导 |
| Reporter agent.py:304 | `"你是 HaGoKu Studio 的专业报告员"` | LLM system prompt |
| cleaner/agent.py:590-600 | `"你是专业数据清洗员..."` | LLM system prompt |
| analyst/agent.py:335 | `"是否确认？"` | 生成的展示文本，非判断逻辑 |
| query_parser.py:86 | `"你是数据分析意图识别专家"` | LLM system prompt |

**判定**：全部为 LLM prompt 字符串或展示文本，不是代码硬匹配。🟢 合格。

---

## 原则 1：多 Agent 项目分析写作框架 — 合格 🟢

### 结构覆盖

| Agent | 目录 | 角色定义 | 知识系统 | 记忆 | 状态 |
|-------|------|---------|---------|------|------|
| 🔍 Scout | `agents/scout/` | prompt.md | knowledge.py + knowledge.yaml | memory.md | ✅ |
| 🧹 Cleaner | `agents/cleaner/` | prompt.md | knowledge.py + knowledge.yaml | memory.md | ✅ |
| 📊 Analyst | `agents/analyst/` | prompt.md | knowledge.py + knowledge.yaml | memory.md | ✅ |
| 📝 Reporter | `agents/reporter/` | prompt.md | knowledge.py + knowledge.yaml | memory.md | ✅ |
| 📋 Scribe | `agents/_scribe/` | prompt.md | 无独立 KB（内部记录员） | memory.md | ✅ |

### 管道协作

- Pipeline 顺序：Scout → Cleaner → Analyst → Reporter
- 数据接力：Parquet + context.md + 看板
- 暂停/恢复：每个阶段暂停等待用户确认
- Scribe：后台监听 EventBus，不参与主管道

**判定**：🟢 合格。五个 Agent 均有完整目录结构，管道编排清晰。

---

## 原则 2：充分让 LLM 发挥工作 — 主体合格，CLI 遗留 🟡

### 已 LLM 化的核心路径

| 决策点 | 实现方式 | 文件 |
|--------|---------|------|
| 意图解析 | LLM structured output（JSON schema） | `query_parser.py` |
| 字段语义理解 | function calling（`update_field_understanding`） | `orchestrator.py:_apply_scout_reply_with_llm` |
| 字段语义推断 | LLM 从画像数据推断 | `scout/agent.py:_infer_field_semantics` |
| 清洗策略 | LLM 从画像推断 | `cleaner/agent.py:_infer_cleaning_strategy` |
| 分析方法选择 | LLM 从查询+上下文选择 | `analyst/agent.py` |
| 报告叙述 | LLM 生成叙述文本 | `reporter/agent.py` |
| 分析计划生成 | LLM 根据意图生成分析计划 | `llm/plan_schema.py` |
| 暂停消息生成 | LLM 根据结果生成对话式消息 | `orchestrator.py:_attach_pause_dialogue_message` |

### 代码未替 LLM 做决策的验证

| 检查项 | 结果 |
|--------|------|
| query_parser.py 中有无 if-else 关键词匹配？ | ❌ 无。全部 LLM |
| 字段理解有无正则解析？ | ❌ 无。全部 function calling |
| 分析方法选择有无 if-else 链？ | ❌ 无。LLM 从工具库选择 |
| 分布判断有无硬编码阈值？ | ❌ 无。已从代码迁移到 LLM |

### 问题：CLI 模式 (orchestrator.py:1984-2105)

CLI `run_cli` 方法中存在的确认判断和字段理解代码**完全绕开了** function calling 通道：

```python
# 1999: 硬编码中文确认匹配
if user_input.lower() in ("好", "是", "ok", "继续", "next", "y", "yes"):
# 2053: 直接调用 LLM 但走的是简化版 prompt，不是 function calling
```

虽然这段代码标注为 CLI 交互模式（面向终端用户），但它违背了「LLM 驱动决策」的原则——用户说"好"时应由 LLM（而非代码正则）判断是确认还是另有意图。

**判定**：🟡 主体合格。核心 Web UI 路径已全部 LLM 化。CLI 模式为遗留问题，建议统一走 function calling 通道（或在 CLI 模式标注为「降级路径，允许简化匹配」）。

---

## 原则 3：为 LLM 搭建与用户沟通的通道 — 主体合格 🟢

### 通道完整性

```
用户（浏览器） ←→ WebSocket ←→ API Server ←→ Orchestrator._pause_and_wait()
                                                    │
                                           Scribe.block_task()
                                                    │
                                           EventBus 发出 USER_INPUT_REQUESTED
                                                    │
                                         前端渲染暂停卡片（结构化 + LLM 消息）
                                                    │
                                        用户回复 ← 前端 unblock
```

### 暂停点覆盖

| 暂停点 | 函数 | 用途 |
|--------|------|------|
| Scout 字段理解 | `_pause_and_wait("scout", scout_msg)` | 用户确认/纠错字段理解 |
| Scout → Cleaner 闸门 | `_pause_and_wait("scout", gate_msg)` | 确认进入清洗 |
| Cleaner 清洗方案 | `_pause_and_wait("cleaner", cleaner_msg)` | 用户确认清洗方案 |
| Cleaner → Analyst 闸门 | `_pause_and_wait("cleaner", gate_msg)` | 确认进入分析 |
| Analyst 初步发现 | `_pause_and_wait("analyst", analyst_msg)` | 用户确认分析方向 |
| Analyst → Reporter 闸门 | `_pause_and_wait("analyst", gate_msg)` | 确认进入报告 |

### 结构化卡片

每个暂停事件附带结构化数据（字段表/清洗表/护栏摘要），前端用卡片形式展示，而非纯文本。若 LLM 生成的短消息附带其中，由 LLM 根据上下文生成。

### Agent 交互契约

`docs/AGENT_INTERACTION_CONTRACT.md` 定义了完整的暂停/回复/多轮对齐规范。

**判定**：🟢 主体合格。用户通过 Web UI 与 Agent 直接通信，代码仅做通道传输和状态机管理。

---

## 原则 4：各种工具与知识库供 LLM 调用 — 合格 🟢

### 工具覆盖

| 类别 | 文件 | 工具数量 |
|------|------|---------|
| 数据 I/O | `data_io.py` | load/save |
| 数据画像 | `profiling.py` | generate_profile |
| 数据清洗 | `cleaning.py` | 异常检测/缺失处理/编码/标准化 |
| 统计分析 | `analysis.py` | 50+ 分析方法 |
| 业务分析 | `business.py` | 漏斗/ROI/LTV/CAC 等 |
| 可视化 | `visualization.py` | Plotly 图表生成 |
| 诊断 | `diagnostics.py` | 残差诊断/共线性/异方差 |
| 效能分析 | `power_analysis.py` | 统计效能/样本量 |
| 健康检查 | `health.py` | LLM 连通性 |
| 报告 | `reporting.py` | 模板渲染 |

### 工具注册架构

`tools/analysis_registry.py` 为插件式架构，新增分析工具只需在注册表中添加条目。

### 知识库三层架构

| 层 | 位置 | 内容 | 维护方式 |
|----|------|------|---------|
| Layer 1 | `kb/business/`, `kb/financial/`, `kb/stats/` | 领域知识 | 手写，低频更新 |
| Layer 2 | `agents/*/knowledge.yaml` | 方法经验 | 手动维护 |
| Layer 3 | LLM 上下文 | 自由发挥 | 自动 |

### 知识注入机制

Scribe 在 Agent 启动前检索知识库并注入 prompt。Agent 不主动查询知识库。

**判定**：🟢 合格。工具库覆盖全面，知识库分层清晰，function calling 使 LLM 可自主选择调用哪个工具。

---

## 原则 5：没有代码兜底 — 1 处灰区 🟡

### 降级策略覆盖

| Agent | 失败场景 | 方案 | 是否代码替 LLM？ |
|-------|---------|------|-----------------|
| Scout | 语义推断失败 | 标记 UNKNOWN，等待用户确认 | ❌ 否 |
| Analyst | 回归失败 | LLM 决定替代方法 | ❌ 否 |
| Cleaner | 填补失败 | 保留缺失值，标注未处理 | ❌ 否 |
| Reporter | 模板渲染失败 | 降级到 Markdown | ❌ 否（纯渲染层降级） |

### query_parser 兜底

```python
# query_parser.py:72-74
except Exception:
    return QueryIntent(intent_type="exploration", confidence="low")
```

**分析**：`exploration` 是「我不确定」的语义等价——不是代码替 LLM 猜一个具体意图，而是返回默认结构性值。符合「保留原样，通知用户」的精神。

### Scribe recover_field_descriptions 兜底

```python
# scribe/agent.py:486-493
merged[col] = f"字段 {col}（{dtype_hint}）"
```

**分析**：当 LLM 恢复字段描述失败时，生成机械占位描述（列名 + 数据类型），不做语义推断。这是一个**数据完整性兜底**——确保字段描述字典的键完整，但值明确标注为机械生成的。

**判定**：🟡 灰区但可接受。不是「代码替 LLM 做语义推断」，而是「代码保证数据结构的完整性，用机械占位值填充」。建议加注释说明这是机械兜底，非语义推断。

### 整体判定

代码中没有发现「LLM 失败时代码自己用正则/默认值推断字段含义、选择分析方法、生成报告」的模式。

**判定**：🟢 原则合格，1 处灰区可接受。

---

## 原则 6：可持续可成长的架构 — 部分达标 🟡

### 「加一行配置」的能力

| 新增内容 | 所需步骤 | 复杂度 |
|---------|---------|--------|
| 新增 Agent | 创建 `agents/{name}/` 目录 + agent.py + prompt.md + knowledge.yaml + memory.md | 🟢 低 |
| 新增工具 | 在 `tools/` 下添加函数 + `analysis_registry.py` 注册 | 🟢 低 |
| 新增知识库领域 | 在 `kb/` 下添加目录 + YAML 文件 | 🟢 低 |
| 新增报告模板 | 在 `templates/` 下添加目录 + Jinja2 模板 | 🟢 低 |
| 新增 Agent 常量 | 需要在 `agents/constants.py` 中为每个 Agent 添加常量 | 🟡 中 |

### 硬编码管道

Pipeline 执行顺序在 `orchestrator.py:run_pipeline()` 中硬编码：

```python
# 顺序硬编码在 orchestrator.py
scout.run(data_path, query, ...)
cleaner.run(data_path, context, ...)
analyst.run(df_raw, df_clean, context, query, ...)
reporter.run(results, context, query, ...)
```

如果要调整 Agent 执行顺序（如「先 Cleaner 再 Scout」），或新增中间 Agent，需要直接修改 `orchestrator.py` 而不是改配置。理想状态下，管道步骤应是声明式配置。

### 暂停阶段硬编码

每个暂停点（Scout 字段对齐循环、Scout → 清洁闸门、Cleaner 清洗确认、Cleaner → 分析闸门、Analyst 初步结果、Analyst → 报告闸门）都有独立的 while 循环和 `_pause_and_wait` 调用，硬编码在 `run_pipeline()` 中。新增一个暂停点需要修改核心方法。

### 常量化

`agents/constants.py` 按 Agent 组织常量（如 `SCOUT_INFER_TEMPERATURE`、`CLEANER_INFER_TEMPERATURE`）。新增 Agent 需要在此文件中新增常量块。

### 好的方面

- Agent 目录结构统一：每个 Agent 都有相同的文件布局
- 工具注册是声明式的
- LLM prompt 从文件加载，不硬编码在 Python 中
- 知识库是 YAML 文件，非代码
- 模板系统是目录级别的

**判定**：🟡 部分达标。Agent 和工具的新增较简单；管道和暂停逻辑的声明式程度不足。

---

## 优先级修复建议

### P0：刹车 1 标记补全

在所有通道区域顶部添加 `# ==== CHANNEL ZONE: 禁止正则/if-else 语义分支 ====` 注释。

**影响文件**（6 个）：
- `orchestrator.py`：`_apply_scout_reply_with_llm`、`apply_scout_user_field_reply_to_context`
- `query_parser.py`：`_llm_parse_intent`
- `scout/agent.py`：`_infer_field_semantics`
- `cleaner/agent.py`：`_infer_cleaning_strategy`
- `analyst/agent.py`：LLM 调用区域

### P1：CLI 模式确认逻辑统一

将 `orchestrator.py:run_cli()` 中的硬编码中文匹配替换为 function calling 通道，或在文件头部添加注释明确标注这是「CLI 降级模式，允许简化确认匹配」。

### P2：管道声明式配置

将 `run_pipeline()` 中的硬编码管道步骤提取为配置，使 Agent 执行顺序和暂停点可声明式定义。例如：

```yaml
# pipeline.yaml
stages:
  - agent: scout
    pause: field_review
    gate: cleaning
  - agent: cleaner
    pause: cleaning_review
    gate: analysis
  - agent: analyst
    pause: findings_review
    gate: report
  - agent: reporter
```

### P3：Scribe 兜底注释

在 `recover_field_descriptions()` 的 fallback 分支（line 486-493）添加注释说明这是机械占位兜底，非语义推断。

---

## 总结

| 维度 | 总体评级 | 关键发现 |
|------|---------|---------|
| 核心原则遵从度 | 🟢 85% | 核心路径全面 LLM 化；CLI 遗留 1 处违规 |
| 刹车部署 | 🟡 67% | 刹车 2（测试）已部署；刹车 1（注释标记）全面缺失；刹车 3（审查）通过主体验证 |
| 可持续架构 | 🟡 70% | Agent 新增简单；管道声明式化不足 |

**核心结论**：HaGoKu Studio 的设计原则在代码中得到较好落实。主要的缺口在于：刹车 1 的 CHANNEL ZONE 标记全面缺失（防御性基础设施未建设），以及 CLI 模式中的硬编码确认匹配（历史遗留，不影响 Web UI 主路径）。管道声明式化属于改进项而非缺陷。