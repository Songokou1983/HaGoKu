# Agent 互动与成长 — 可执行契约（Executable Contract）

> 与 `PROJECT.md`「人机互动理念」「互动与成长：原则优先级与验收」配套：**本文件写「测什么」**，代码与测试写「怎么保证」。

## 1. 禁止项（回归必须守住）

| ID | 规则 | 典型反例（不得再现） |
|----|------|----------------------|
| C1 | **Cleaner 暂停**不得再走「冒充 Agent 长谈」的写死客服话术路径 | 旧版 `_fallback_pause_message("cleaner")` 中「数据质量检测完成…特别想保留/排除…」整段 |
| C2 | **Scout / Cleaner / Analyst 暂停**：`user_input_requested` 主载荷须为结构化 `field_review` / `cleaning_review` / `analyst_review`，`message` 可为空；**不得**把整表 Markdown 或「冒充 Agent」长段塞进单一 `message` | 旧 Markdown 三列表串；Analyst 仅用 LLM 生成整段暂停台词 |
| C3 | **用户纠错须写进状态**：Scout 暂停后用户自然语言/结构化纠错须进入 `context`（如 `column_descriptions`），**不得**仅追加 `[用户补充]` 到 `query` 而无上下文更新 | 「code means …」被忽略 |

## 2. 当前实现锚点（便于审查 PR）

| 能力 | 主要代码 |
|------|----------|
| Scout 结构化暂停 | `hagoku/manager/orchestrator.py` → `scout_field_review_pause_payload` |
| 用户纠错写入 context | `apply_scout_user_field_reply_to_context` |
| Cleaner 结构化暂停 | `cleaning_review_pause_payload`、`_normalize_cleaning_operation` |
| Analyst 结构化暂停 | `analyst_review_pause_payload` |
| Web 工作流表 | `hagoku_web/src/panels/AnalyzePanel.tsx`（`field_review` / `cleaning_review` / `analyst_review`） |

## 3. 自动化验收

```bash
pytest tests/test_product/test_agent_interaction_contract.py -q
```

新增禁止类规则时：**先在本表增加一行，再写/改测试**，避免「只改 PROJECT」。

## 4. 已知缺口（非本契约能单独解决）

- **同阶段多轮自由对话**：依赖编排状态图/循环（见 `PROJECT.md` 与 TradingAgents 对比）；契约测试**不**假装已具备 LangGraph 级能力。
- **「成长」的可视叙事**：当前以记忆/知识/看板为主；若需 UI 级「履历时间线」，另立规格与测试。
