# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository Context

This repository contains **one primary project**: `hagoku/`（主项目）。其他同名目录下的项目不在此仓库管理范围内。

## 铁律（PR 级硬约束 — 违反任何一条 PR 直接拒）

开始任何代码动作前，请先做这两件事：

1. 读完仓库根目录的 [AGENTS.md](AGENTS.md)
2. 读完 [PROJECT.md](PROJECT.md) 的三个章节：
   - §「代码边界」（哪些事 LLM 干、哪些事代码干）
   - §「通道完备性十律」（10 条正向契约）
   - §「失败处理」§「代码层合法动作清单」（LLM 失败时唯一允许的代码动作）

### 铁律 1（零硬编码）

任何"业务概念分类 / 自然语言意图判断 / 中文同义识别"必须由 LLM 完成。代码不准做。如果你想写：

- `["收入", "营收", "销售额", ...]` 这样的关键词列表
- `re.search(r"收入|营收|销售", text)` 这样的中文语义正则
- `if intent == "预测" elif intent == "对比"` 这样的中文 if-elif 链
- 函数名带 `_infer_`/`_detect_`/`_classify_` 但内部没调 LLM

→ 全部禁止。停下来想：这个判断能不能写到 system prompt 里让 LLM 做？
能 → 写到 prompt 里，删掉代码。
不能（纯运算/IO/序列化）→ 才允许写代码。

### 铁律 2（LLM 失败的唯一合法路径）

当 LLM 调用失败时，你只能做四件事：

- **A.** `raise RuntimeError(...)` — LLM 不可达 / 通道异常时
- **B.** 写 `ctx["_last_understanding_failure"] = {raw_text, ...}` 然后 `return []` — LLM 调用成功但没产生有效工具调用时
- **C.** 落地能落的工具调用，未落的留空 — LLM 给出部分输出时
- **D.** 拒绝写入权威结构（同 B） — LLM 输出与原话明显矛盾时

禁止写：`except: return []` / `except: return None` / 默认值兜底 / 缓存+规则降级。

### 铁律 3（提交前自检）

完成任何代码改动后，必须跑过这三组测试。任一变红 = 改坏了：

```bash
.venv/bin/python -m pytest tests/test_doctrine_compliance.py -q
.venv/bin/python -m pytest tests/test_product/test_information_arrival.py -q
.venv/bin/python -m pytest --tb=short -q
```

### 常见错误模式（每次都会犯，请警惕）

| 你的本能 | 正确做法 |
|---------|---------|
| 测试不绿 → 加规则让它绿 | 检查是不是 prompt 写错了 / 工具 schema 不全 |
| LLM 调用失败 → 加 except 兜底 | `raise RuntimeError` 让用户看见 |
| 看到字段名（"收入"/"销售额"）→ 加 dict 映射 | 让 LLM 用 `_resolve_to_column_names` 之类的工具映射 |
| 防御性编程 "万一 LLM 返回空"→ 加默认值 | 写 `_last_understanding_failure` 让用户看到没理解 |

### 拿不准时问自己唯一一个问题

> "这段代码做的判断，能不能用一句中文写成 prompt 让 LLM 做？"

| 答案 | 行动 |
|------|------|
| 能 → 这是 LLM 的活 | 删掉代码，写到 prompt 里 |
| 不能（纯运算/IO/序列化）→ 代码的活 | 写代码，但确保不夹带业务判断 |
| 拿不准 | 默认是 LLM 的活（LLM 主导是项目第一原则） |

## hagoku/ — HaGoKu Studio 多 Agent 数据分析平台

> 项目灵魂、Agent 表、架构原则、命令参考、技术栈 → 见 **[PROJECT.md](PROJECT.md)**（唯一真相源）。
> 文档索引、环境变量 → 见 **[DEV.md](DEV.md)**。

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
| P0-3 | 删除 `_parse_llm_field_desc_line()` | `hagoku/agents/scout/agent.py` | 死代码已清除（无调用方），列语义由 LLM structured output 接管 |
| P0-4 | 保留 `_format_sample_preview()` | `hagoku/agents/scout/agent.py` | 纯数据工具函数（列值取样 → 字符串），不含业务语义决策；LLM 需要看到具体样本值才能做语义推理 |
| P0-5 | Plan 构建 LLM 化 | `hagoku/manager/orchestrator.py` | 移除关键词映射表，改为 `_call_llm_for_plan()` |
| P0-6 | 阶段消息 LLM 化 | `hagoku/manager/orchestrator.py` | 移除 `llm_lines` 硬编码消息，改为 `_generate_phase_message()` LLM 生成 |

> 删除的硬编码常量（`DISTRIBUTION_CATEGORICAL_THRESHOLD` 等）位于 `hagoku/agents/constants.py`。完整审查 → `docs/AGENT_HARDCODED_REVIEW.md`。

**代码层角色限定**：serialize → validate → transport。判断的事 LLM 做——详见 [AGENTS.md](AGENTS.md)。

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