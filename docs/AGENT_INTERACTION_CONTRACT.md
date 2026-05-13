# Agent 互动与成长 — 可执行契约（Executable Contract）

> 与 `PROJECT.md`「人机互动理念」「互动与成长：原则优先级与验收」配套：**本文件写「测什么」**，代码与测试写「怎么保证」。

## 1. 禁止项（回归必须守住）

| ID | 规则 | 典型反例（不得再现） |
|----|------|----------------------|
| C1 | **Cleaner 暂停**不得再走「冒充 Agent 长谈」的写死客服话术路径 | 旧版 `_fallback_pause_message("cleaner")` 中「数据质量检测完成…特别想保留/排除…」整段 |
| C2 | **Scout / Cleaner / Analyst 暂停**：`user_input_requested` 主载荷须为结构化 `field_review` / `cleaning_review` / `analyst_review`，`message` 可为空；**不得**把整表 Markdown 或「冒充 Agent」长段塞进单一 `message` | 旧 Markdown 三列表串；Analyst 仅用 LLM 生成整段暂停台词 |
| C3 | **用户纠错须写进状态**：Scout 暂停后用户自然语言/结构化纠错须进入 `context`（如 `column_descriptions`），**不得**仅追加 `[用户补充]` 到 `query` 而无上下文更新 | 「code means …」被忽略 |
| C4 | **Scout 多轮对齐 + 闸门**：在仍有 `needs_user_input=True` 或用户未发「纯确认」前，编排**须**保持 Scout 子循环；每次 `user_input_requested` 的 Scout 载荷**须**含递增的 **`interaction_revision`**；Scout 对齐后**不得**跳过闸门直接调用 `cleaner.run()`；闸门拒绝（回复含「补充/还有/改」）须回 FieldReviewLoop | 单次 `respond` 后无条件进清洗；无 `interaction_revision`；对齐后不经闸门直接进 Cleaner |

## 2. 当前实现锚点（便于审查 PR）

| 能力 | 主要代码 |
|------|----------|
| Scout 结构化暂停 | `hagoku/manager/orchestrator.py` → `scout_field_review_pause_payload` |
| Scout 多轮 + 对齐判定 | 同上 → `_is_scout_aligned`、Scout 段 `while` 循环、`interaction_revision` |
| 用户纠错写入 context | `apply_scout_user_field_reply_to_context` |
| Cleaner 结构化暂停 | `cleaning_review_pause_payload`、`_normalize_cleaning_operation` |
| Analyst 结构化暂停 | `analyst_review_pause_payload` |
| Web 工作流表 | `hagoku_web/src/panels/AnalyzePanel.tsx`（`field_review` / `cleaning_review` / `analyst_review`） |

## 3. 自动化验收

```bash
pytest tests/test_product/test_agent_interaction_contract.py -q
```

**C4 相关用例**：`test_is_scout_aligned_*`、`test_interaction_revision_in_scout_payload`（及 Scout 多轮行为与 `_pause_and_wait` 编排变更的回归，变更时必跑）。

新增禁止类规则时：**先在本表增加一行，再写/改测试**，避免「只改 PROJECT」。

## 4. 已知缺口（非本契约能单独解决）

- **除 Scout 字段表外的「全自由多轮」**：Scout 已具备**确定性**多轮对齐子循环；**跨阶段闸门、Cleaner/Analyst 同构多轮**仍见 [INTERACTION_MULTITURN_PLAN.md](INTERACTION_MULTITURN_PLAN.md) §2.2 / §4-B/C。更宽的状态图（对比 `PROJECT.md` LangGraph 对照）**不**由本契约假装已完备。
- **「成长」的可视叙事**：当前以记忆/知识/看板为主；若需 UI 级「履历时间线」，另立规格与测试。

**实施计划（多轮对齐）**：[INTERACTION_MULTITURN_PLAN.md](INTERACTION_MULTITURN_PLAN.md)。**C4（Scout）**已写入 §1 表；跨阶段闸门、Cleaner/Analyst 同构等 **C4 扩展** 随方案 §4-B/C 与 `DEVELOPMENT_PROMPT` **2.8.3** 继续补测试与条文。

## 5. 互动场景夹具（可执行剧本）

> 把「用户在分析页会看到什么」写成**版本化 JSON**，才能对照实现、迭代 LLM 短引导，而不是只靠口头描述。

| 资产 | 用途 |
|------|------|
| `tests/fixtures/interaction_scenarios/*.json` | 每条 `steps[]` 含 `note`（给人看）与可选 `ws`（给前端 / 回放器看的 WebSocket `event` 载荷）；`gap` 标注与「话术动态」之间的差距 |
| `hagoku/devtools/interaction_scenarios.py` | `validate_scenario_document` / `format_scenario_script` |
| `scripts/simulate_interaction_scenario.py` | `--validate-all` 校验全部夹具；`--script <id>` 打印一页纸剧本 |

```bash
python3 scripts/simulate_interaction_scenario.py --validate-all
python3 scripts/simulate_interaction_scenario.py --script full_web_pause_flow
pytest tests/test_product/test_interaction_scenarios.py -q
```

新增场景：**先加 JSON + 跑通校验**，再改前后端；避免「永远写不出来」却无对照物。
