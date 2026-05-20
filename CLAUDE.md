# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository Context

This repository contains **one primary project**: `hagoku/`（主项目）。其他同名目录下的项目不在此仓库管理范围内。

## hagoku/ — HaGoKu Studio 多 Agent 数据分析平台

> 项目灵魂、Agent 表、架构原则、命令参考、技术栈 → 见 **[PROJECT.md](PROJECT.md)**（唯一真相源）。
> 文档索引、环境变量、测试命令 → 见 **[DEV.md](DEV.md)**。

### 当前架构关键点（已实施的 P0 项）

**双层 LLM（P0.3）**：通过 `HAGOKYU_LLM_MODEL_DEEP` / `HAGOKYU_LLM_MODEL_QUICK` 环境变量区分。
- `llm_deep`：Analyst（假设检验/回归推理）、仲裁器（计划决策）
- `llm_quick`：Scout（类型推断）、Cleaner（清洗决策）、Reporter（格式化渲染）
- 工厂函数在 `hagoku/llm/client.py`：`create_deep_client()` / `create_quick_client()`
- 回退逻辑：未设置 deep/quick 时复用 `HAGOKYU_LLM_MODEL`

**结构化输出解析器（P1.2）**：`hagoku/guardrails/parsers.py`
- `parse_pvalue()`、`parse_effect_size()`、`parse_conclusion_count()`、`parse_confidence_interval()`
- `validate_analysis_output()` 综合 4 项检查
- Reporter 需调用解析器验证 Analyst 输出结构完整性

**Scribe**：确定性 Agent，仅字段描述不完整时用 LLM 补全。负责：看板管理、记忆维护、知识库检索与注入、字段仲裁。详见 PROJECT.md Agent 表。

**P0 架构净化（2026-05-20）**：移除 6 处代码级硬编码语义，彻底贯彻 `LLM 输出 → 代码搬运 → 用户` 通道原则：

| # | 变更 | 文件 | 说明 |
|---|------|------|------|
| P0-1 | 意图解析 LLM 化 | `hagoku/manager/query_parser.py` | 移除关键词硬匹配，改为 LLM structured output（`PlanRequestFields` schema）|
| P0-2 | Scout 分布判断 LLM 化 | `hagoku/agents/scout/agent.py` | 移除硬编码倍数阈值（`maxv > q75v * 10` 等），shape analysis 由 LLM 完成 |
| P0-3 | 删除 `_parse_llm_field_desc_line()` | `hagoku/manager/orchestrator.py` | 移除正则字段描述解析器 |
| P0-4 | 删除 `_format_sample_preview()` | `hagoku/agents/scout/agent.py` | Scout 只传原始 top-10 值，格式化由 LLM 决定 |
| P0-5 | Plan 构建 LLM 化 | `hagoku/manager/orchestrator.py` | 移除关键词映射表，改为 `_call_llm_for_plan()` |
| P0-6 | 阶段消息 LLM 化 | `hagoku/manager/orchestrator.py` | 移除 `llm_lines` 硬编码消息，改为 `_generate_phase_message()` LLM 生成 |

> 删除的硬编码常量（`DISTRIBUTION_CATEGORICAL_THRESHOLD` 等）位于 `hagoku/agents/constants.py`。完整审查 → `docs/AGENT_HARDCODED_REVIEW.md`。

**代码层角色限定**：serialize → validate → transport。任何涉及"判断"（意图、字段语义、分布形状、分析策略、用户消息）的环节，信息必须完整到达 LLM。

---

## HaGoKu Studio UI 设计原则（每一条改动都必须遵守）

1. **考虑用户体验**：每次改动想清楚用户看到什么、怎么用
2. **差异化**：和市面上产品有明显区别，不是功能堆砌
3. **互动性**：Agent 主动引导用户，不是等着用户输入
4. **不要出现重复功能**：一个功能只在一个地方
5. **不要重复犯错**：同一错误不犯第二次
6. **理解确认清楚需求再改动**：不确定就问用户，不要乱猜
7. **表格规则（HTML table via st.markdown() 实现时）**：
   - 表头 **必须居中**（`text-align:center`）— 这是死规定，**绝对不允许违反**
   - 数据列内容 **不要居中**，保持默认左对齐
   - 绝不添加未经用户明确要求的功能（如"文件数列"、"总项目数"等汇总栏）
8. **新建项目表单**：始终固定在页面底部，不可在顶部
9. **操作按钮**：图标 + 文字双重要素，缺一不可
10. **最小改动原则**：每次只改用户要求的那一个地方，不做额外的改动，不改变未要求的元素
11. **每次改动前必须备份（二选一即可）**：**优先**用 Git（`git stash` / 小步 `commit`）保留可回滚点；若仍习惯 `cp` 本地快照，文件名须为 `UI_CHANGELOG_backup_YYYYMMDDHHMMSS_原文件名`（该模式已 `.gitignore`，**勿** `git add`）。堆积后可运行 `python3 scripts/clean_ui_changelog_backups.py` 查看列表，`--older-than N --apply` 按修改时间清理（见 [DEV.md](DEV.md)）。每一步 UI/编排相关改动仍须记录到 `UI_CHANGELOG.md`。

---

## Karpathy 编码原则（自动应用）

### 1. Think Before Coding
**不猜、不藏疑点，先说假设。**
- 不确定 → 先问，不要猜
- 有多种解释 → 说出来，不要自己选
- 有更简单方案 → 提出来，不要闷头实现
- 不清楚 → 停下来，说清楚，问用户

### 2. Simplicity First
**最少代码解决问题，不 speculative。**
- 不做没要求的功能
- 单次使用的代码不抽象
- 不做没被要求的"灵活性"
- 200 行能解决就不要写 2000 行

### 3. Surgical Changes
**只改需要改的，不顺手优化。**
- 不改旁边没问题的代码
- 不顺手格式化
- 不删除没被要求删除的代码
- 只清理自己改动产生的孤儿代码

### 4. Goal-Driven Execution
**给可验证的成功标准。**
- "修 bug" → 先写测试复现，再修
- "加功能" → 先说清楚怎么算完成
- 多步任务 → 先列计划，每步有验证点