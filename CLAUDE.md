# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository Context

This repository contains **one primary project**: `hagoku/`（主项目）。其他同名目录下的项目不在此仓库管理范围内。

## hagoku/ — HaGoKu 多 Agent 数据分析平台

> 项目灵魂、Agent 表、架构原则、命令参考、技术栈 → 见 **[PROJECT.md](PROJECT.md)**（唯一真相源）。
> UI 设计原则、全局工作原则、Karpathy 编码原则 → 见下文。

### 项目文档索引

| 文档 | 用途 | 何时读 |
|------|------|--------|
| | [PROJECT.md](PROJECT.md) | 项目灵魂、模块全景、架构原则、反模式 | 每次对话开始 |
| | [DEV.md](DEV.md) | 快速上手（环境搭建→测试→提交） | 新环境搭建 |
| | [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) | 设计手册（架构/看板/向量/审查） | 涉及架构变更时 |
| | [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) | 已知 bug 及修复 | 遇到问题时 |
| | [README.md](README.md) | 用户手册（安装、命令参考） | 回答用户问题 |
| | [DEVELOPMENT_PROMPT.md](DEVELOPMENT_PROMPT.md) | **四阶段路线图跟踪** + 单轮任务模板；审查约定见该文件 | 派活、协作开发、PR 审查 |

### Agent 角色速查

| Agent | 职责 | LLM 层级 |
|-------|------|----------|
| 🔍 **Scout** | 数据理解：类型推断、语义分析、缺失/分布报告 | `quick` |
| 🧹 **Cleaner** | 数据清洗：缺失机制检验、异常区分、清洗影响评估 | `quick` |
| 📊 **Analyst** | 统计分析核心：假设检验、回归、效应量、模型诊断 | `deep` |
| 📝 **Reporter** | 双轨报告渲染：吸引力层 + 核心价值层 | `quick` |
| 📋 **Scribe** | **确定性逻辑引擎（非 Agent，零 LLM 调用）**：看板管理、记忆维护、知识库检索与注入、字段仲裁 | 无 |

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

**Scribe 身份**：不是 Agent，是确定性逻辑引擎。不调用 LLM，不做分析决策。负责：知识注入、记忆写入、字段仲裁、看板管理。详见 PROJECT.md L36-38。

---

## HaGoKu UI 设计原则（每一条改动都必须遵守）

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

## 全局工作原则 → 见 [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md)

开发流程、测试方法、提交规范、编码约束（不重复造轮子、不重复犯错）统一维护在设计手册中。此处不再重复。

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