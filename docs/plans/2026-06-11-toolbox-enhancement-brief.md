# 工具箱增强 brief — 知识驱动 · 一次性交付（2026-06-11）

> **交付模式**：**一个 PR、一次做完**。与 Web UI brief（`2026-06-11-web-ui-ab-brief.md`）可并行，互不阻塞。
>
> **读者**：实施开发。按 **CO-T01～CO-T32** 勾选，全部完成后再合 PR。
>
> **前置**：Phase D（1 DataAnalystAgent + 全局 `agent_tools`）已落地；Meta v2 已落地。
>
> **核心命题**：不是堆到 100 个工具，而是 **「方法文档 + 执行工具」成对生长**——知识库教 LLM *何时/为何*，工具箱让 LLM *算得出*。

---

## §0 为什么是这个方向

Phase D 坍缩后，**能力上限 = 工具箱质量 × 知识库深度**。加 agent 违背坍缩，加律违背铁律 1，只有 **工具 + 方法文档** 是纯增量。

| 层 | 职责 | 消费者 |
|----|------|--------|
| **学术方法库** `memory/methods/**/*.md` | 假设、选择逻辑、解读、局限 | LLM（`query_method`/`read_method`）+ 人（Web 知识库 `/api/kb`） |
| **执行工具** `agent_tools` | 结构化计算：p、效应量、CI、诊断 | LLM function calling |
| **成长记忆** `lessons` | 项目间经验（参考非结论） | 已有 8 个 memory 工具 |
| **项目记忆** | 字段语义、历史 | 已有 |

**目标规模**：注册工具 **~27 → ~45**（不是 100）。40–50 个 schema 全量注入 LLM 仍可接受；**暂不建** `search_tools` 发现层（≥60 再议）。

---

## §1 现状审计（开发前先读）

### 1.1 已注册工具（27）

| 来源 | 数量 | 代表 |
|------|------|------|
| `agent_tool_defs.py` | 19 | 探查、清洗、统计、流程 |
| `memory_tools.py` | 8 | `query_method`、`read_method`、lessons、项目记忆 |

### 1.2 休眠武器（库有、LLM 调不到）

| 模块 | 函数/能力 | 状态 |
|------|-----------|------|
| `analysis/diagnostics.py` | `check_test_assumptions` | prompt **承诺了**，未注册 → 调了报错 |
| `power_analysis.py` | 功效/样本量/非显著解读 | prompt **承诺了**，未注册 |
| `analysis/advanced.py` | `multiple_comparison_correction`、交互分析 | 未注册 |
| `diagnostics.py` | `diagnose_regression` | 未注册 |
| `business.py` | ROI/LTV/CAC/漏斗/归因等 ~15 个 | 未注册 |
| `cleaning.py` | 离群检测、缺失机制、清洗建议 | 未注册 |
| `visualization.py` | `create_plot` | 仅报告管道，分析对话不可用 |
| `analysis/comparison.py` 等 | 带效应量+CI 的 `ttest`/`anova`/… | **`run_statistical_test` 未委托**，自写 scipy 薄封装 |

### 1.3 知识库

- 路径：`hagoku/memory/methods/`（当前 **5** 篇：`ttest`/`anova`/`regression`/`power-analysis`/`multiple-testing`）
- LLM 检索：`query_method` 用 **question 分词 + 文件全文 token 匹配**（LLM 驱动 question，合规）
- Web：`GET /api/kb` 列目录；frontmatter 的 `title`/`summary` **尚未**被 API 解析（只读第一行 `#`）

### 1.4 应删除的死代码

- `analysis_registry.py`：关键词索引注册表，**零引用**，与铁律 1 方向相悖 → **删除** + 清理 `tools/__init__.py` export

---

## §2 设计原则

### 2.1 方法条目 = 文档 + 工具（成对规范）

每新增/接通一项能力，**必须同时**：

1. `memory/methods/<域>/<slug>.md` — 方法文档
2. `agent_tools.register(Tool(...))` — 执行工具
3. 文档 frontmatter 增 `tools: [tool_name, ...]` 互链
4. `tests/test_tools/test_<tool_name>.py` — 至少 1 个行为测试

**方法文档 frontmatter 模板**：

```yaml
---
title: t 检验选择指南
category: statistics
tags: [t检验, 假设检验]
summary: 独立/配对/单样本 t 检验的选择与假设
tools:
  - check_test_assumptions
  - run_statistical_test
kb_order: 10
---
```

### 2.2 工具注册规范

| 字段 | 要求 |
|------|------|
| `name` | snake_case，动词或 `calc_*` |
| `description` | 中文，说清**输入/输出/何时用**；不写结论 |
| `parameters` | OpenAI JSON Schema；enum 列全合法值 |
| `handler` | `(args, ctx, df) -> dict`；数据不足返回 `{"error": "..."}`  **禁止** raise 吞掉 |
| `phase_tag` | 保留，仅描述性：`['理解字段', ...]` |
| **返回** | 统计类 **必须**含 `p_value`（如适用）、`effect_size`+`effect_type`、`confidence_interval`（如适用）、`test` 字段名 |

**铁律 7**：依赖缺失（如 pingouin）可降级到 scipy，但须在返回里 `note` 说明；**禁止** except 后返回假显著。

### 2.3 `run_statistical_test` 重构原则

**禁止**在 handler 内重复 scipy 薄封装。改为委托 `hagoku.tools.analysis` 模块：

| test_type | 委托 |
|-----------|------|
| `ttest` | `analysis.comparison.ttest` |
| `anova` | `analysis.comparison` 对应函数 |
| `pearson_r` / `spearman_r` | `analysis.correlation` |
| `linear_regression` | `analysis.regression` |
| `chi2` | `analysis` chi_square |
| `trend_decomposition` | 可保留现实现或迁到 `analysis/advanced` |

这样 `submit_analysis` / AnalystReview 表的效应量、CI 有**工具背书**，对齐 PROJECT.md「准：p + 效应量 + CI」。

### 2.4 prompt.md 修改（铁律 10）

- **只改**与工具清单对齐的段落（§跑统计 工具表、工作流程「先 check 再跑」）
- **禁止**全文重写
- PR body **必须**附改前/改后 dump 对比（`HAGOKU_DUMP_LLM` 跑一轮 analyst）

---

## §3 交付清单 CO-T01～CO-T32

### A. 清理与基建

| ID | 内容 | 文件 |
|----|------|------|
| CO-T01 | 删除 `analysis_registry.py`；清 `tools/__init__.py` 引用 | `hagoku/tools/` |
| CO-T02 | 新建 `hagoku/tools/tool_handlers/` 或按域拆 `stat_tools.py` `biz_tools.py`（**禁止** `agent_tool_defs.py` 超 800 行） | 新建 |
| CO-T03 | `_kb_load_registry_entries` 解析 frontmatter `title`/`summary`/`category` | `hagoku/api/server.py` |
| CO-T04 | 方法文档 5 篇补全 `tools:` frontmatter | `memory/methods/` |

### B. 统计诊断与功效（接通休眠 + 对齐 prompt）

| ID | 工具名 | 包装函数 | phase_tag |
|----|--------|----------|-----------|
| CO-T05 | `check_test_assumptions` | `analysis.diagnostics.check_test_assumptions` | 跑统计 |
| CO-T06 | `assess_statistical_power` | 统一入口：`mode` = ttest/anova/correlation/regression + 列参数 | 跑统计 |
| CO-T07 | `required_sample_size` | 统一入口：对应 `required_n_*` | 跑统计 |
| CO-T08 | `interpret_nonsignificant` | `interpret_nonsignificant_result` | 跑统计 |
| CO-T09 | `correct_multiple_comparisons` | `multiple_comparison_correction` | 跑统计 |
| CO-T10 | `diagnose_regression` | `diagnostics.diagnose_regression` | 跑统计 |

### C. 加厚 `run_statistical_test`（CO-T11）

- 重构 handler 委托 `analysis/*`（§2.3）
- 返回字段统一：`p_value`, `effect_size`, `effect_type`, `confidence_interval`, `statistic`, `test`
- 补测试：`tests/test_tools/test_run_statistical_test.py`（ttest 至少断言 effect_size 存在）

### D. 业务指标（营销分析场景）

| ID | 工具名 | 函数 |
|----|--------|------|
| CO-T12 | `calc_roi` | `business.calc_roi` |
| CO-T13 | `calc_roas` | `business.calc_roas` |
| CO-T14 | `calc_ltv` | `business.calc_ltv` |
| CO-T15 | `calc_cac` | `business.calc_cac` |
| CO-T16 | `calc_ltv_cac_ratio` | `business.calc_ltv_cac_ratio` |
| CO-T17 | `funnel_analysis` | `business.funnel_analysis` |
| CO-T18 | `attribution_analysis` | `business.attribution_analysis` |

配套新建方法文档（可短）：

- `memory/methods/business/roi-roas.md`
- `memory/methods/business/ltv-cac.md`
- `memory/methods/business/funnel.md`
- `memory/methods/business/attribution.md`

### E. 清洗增强

| ID | 工具名 | 函数 |
|----|--------|------|
| CO-T19 | `detect_outliers` | 合并 `detect_outliers_iqr` + `zscore`，参数 `method` |
| CO-T20 | `detect_missing_pattern` | `detect_missing_mechanism` |
| CO-T21 | `suggest_cleaning` | `suggest_cleaning_strategy` |

配套：`memory/methods/cleaning/outliers.md`、`missing-data.md`

### F. 可视化（分析对话）

| ID | 内容 |
|----|------|
| CO-T22 | 注册 `create_plot`：参数 `chart_type` + `columns` + `title`；返回 plotly JSON 或 base64 + `artifact_path` 写入 context 供报告复用 |
| CO-T23 | `memory/methods/visualization/chart-selection.md` |

**边界**：图表进 **tool_exchange** 展示摘要；大图不塞进 LLM context，只返路径/缩略信息。

### G. 知识库检索增强（不加新律）

| ID | 内容 |
|----|------|
| CO-T24 | `query_method`：除 token 匹配外，读 frontmatter `tags`/`summary`；可选复用 `LessonStore` 同款向量索引（**若已有 embedding 基础设施**），否则保持 token 匹配并写测试 |
| CO-T25 | `read_method` 返回增加 `tools` 列表（来自 frontmatter），方便 LLM 读完后直接调工具 |

### H. prompt.md 对齐（CO-T26）

- 工具表与 §3 B～F **完全一致**
- 工作流程保留「先 `check_test_assumptions` 再跑检验」
- 新增一句：**「遇到陌生方法先 `query_method`，再 `read_method`，再调对应 tools 列表中的工具」**
- dump 对比进 PR body

### I. 测试

| ID | 内容 |
|----|------|
| CO-T27 | `tests/test_tools/test_check_test_assumptions.py` |
| CO-T28 | `tests/test_tools/test_power_tools.py` |
| CO-T29 | `tests/test_tools/test_business_tools.py`（ROI  smoke） |
| CO-T30 | `tests/test_tools/test_query_method.py`（frontmatter tags 命中） |
| CO-T31 | `tests/test_context/test_tool_exchange.py` 补 emit `EventType.TOOL_EXCHANGE`（若 Web brief WC.0 未合，本 PR 一并做） |
| CO-T32 | 全量 `pytest` 绿；`ruff`/`mypy` 若项目已启用则不过线 |

---

## §4 目标工具全景（完成后 ~45）

```
探查(4)     get_column_stats, get_sample_rows, list_columns, group_stats
字段(3)     update_field_table, update_field_understanding, update_field_role
清洗(6)     submit/update_assessment, propose_cleaning_rule, compare_before_after,
            detect_outliers, detect_missing_pattern, suggest_cleaning
统计(10)    run_statistical_test*, check_test_assumptions, assess_statistical_power,
            required_sample_size, interpret_nonsignificant, correct_multiple_comparisons,
            diagnose_regression, propose_method, update_analysis_scope, restrict_analysis_to
分析提交(2) submit_analysis, submit_first_pass
业务(7)     calc_roi, calc_roas, calc_ltv, calc_cac, calc_ltv_cac_ratio,
            funnel_analysis, attribution_analysis
可视化(1)   create_plot
流程(2)     ask_user, route_to
记忆(8)     query_method, read_method, save/recall/correct_lesson, remember_field,
            query_project_memory, forget_project
---
合计 ~43（含 run_statistical_test 计 1）
```

`*` `run_statistical_test` 为聚合入口，内部委托 analysis 模块。

---

## §5 知识库 ↔ 工具映射表（CO-T04 验收）

| 方法文档 | 关联工具 |
|----------|----------|
| `statistics/ttest.md` | `check_test_assumptions`, `run_statistical_test` |
| `statistics/anova.md` | 同上 |
| `statistics/regression.md` | `run_statistical_test`, `diagnose_regression` |
| `statistics/power-analysis.md` | `assess_statistical_power`, `required_sample_size`, `interpret_nonsignificant` |
| `statistics/multiple-testing.md` | `correct_multiple_comparisons` |
| `business/*.md` | 各 `calc_*` / `funnel_*` / `attribution_*` |
| `cleaning/*.md` | CO-T19～21 |
| `visualization/chart-selection.md` | `create_plot` |

Web 知识库详情页（可选增强，不阻塞）：文末展示「相关工具」chip，读 frontmatter `tools`。

---

## §6 明确不做

| 项 | 原因 |
|----|------|
| 硬凑 100 工具 | 非目标；质量优先 |
| `search_tools` / 关键词路由子集 | ＜60 工具不需要；≥60 另 brief |
| 新 Agent / 新护栏维度 | 违背坍缩方向 |
| lessons CRUD 页 | Web 另 brief |
| 改 `agent_tools.to_openai()` 过滤逻辑 | Phase D 已定论全量注入 |
| 全文重写 `prompt.md` | 铁律 10 |

---

## §7 一次性验收

### 7.1 自动化

- [ ] `pytest` 全绿（基线 538+）
- [ ] 新增 CO-T27～31 测试全绿

### 7.2 行为

- [ ] LLM 可调 `check_test_assumptions`、`assess_statistical_power`（不再 `未知工具`）
- [ ] `run_statistical_test` ttest 返回含 `effect_size` + `confidence_interval`
- [ ] `query_method("功效分析")` 命中 `power-analysis.md`
- [ ] `read_method` 返回含 `tools` 列表
- [ ] `calc_roi` 等 7 个业务工具可 dispatch
- [ ] `create_plot` 返回可展示产物（路径或 JSON）
- [ ] `analysis_registry` 已删除，无残留 import

### 7.3 prompt

- [ ] 工具表与注册表一致
- [ ] PR 含 dump 对比

### 7.4 Smoke（手工 10 分钟）

1. 启动分析 → analyst 阶段：`query_method` → `read_method` → `check_test_assumptions` → `run_statistical_test`（ConvoFeed 可见 tool 块，若 Web 已合）
2. 跑 ttest → 核对返回有效应量
3. `assess_statistical_power` 对小样本给功效不足提示
4. Web 知识库打开 `ttest.md`，frontmatter title 显示正确
5. `calc_roi` 传入 cost/revenue 列得 ROI

---

## §8 文件清单

```
hagoku/tools/
├── agent_tool_defs.py          # 瘦身：迁出 stat/biz/cleaning handlers
├── stat_tools.py               # 新建 CO-T05～11
├── biz_tools.py                # 新建 CO-T12～18
├── cleaning_tools.py           # 新建 CO-T19～21
├── viz_tools.py                # 新建 CO-T22
├── memory_tools.py             # CO-T24～25
├── analysis_registry.py        # 删除 CO-T01
└── __init__.py                 # 清 export

hagoku/memory/methods/
├── statistics/*.md             # CO-T04 frontmatter
├── business/*.md               # 新建 4
├── cleaning/*.md               # 新建 2
└── visualization/chart-selection.md

hagoku/agents/prompt.md         # CO-T26 最小改

hagoku/api/server.py            # CO-T03 kb frontmatter

hagoku/observability/events.py  # TOOL_EXCHANGE（若未合 Web WC.0）

tests/test_tools/               # CO-T27～30 新建
```

---

## §9 PR 模板

```markdown
## Summary
工具箱增强：方法文档与执行工具成对接通，27→~45 工具；run_statistical_test 委托 analysis 模块返回效应量+CI；删除 analysis_registry。

## 知识库
- [ ] 方法文档 frontmatter tools 互链
- [ ] /api/kb 解析 title/summary

## Prompt
- [ ] 工具表对齐（附 dump 对比）

## Test plan
- [ ] pytest
- [ ] §7.4 smoke 1–5
```

**建议 commit message**：

```
feat(tools): 知识驱动工具箱增强 — 接通诊断/功效/业务/清洗/绘图

- 注册 ~16 个新工具；run_statistical_test 委托 analysis 模块
- 方法库 frontmatter tools 互链；KB API 解析 frontmatter
- 删除 analysis_registry；prompt 工具表对齐
```

---

## §10 与 Web UI brief 的衔接

| 工具箱交付 | Web UI 展示 |
|------------|-------------|
| `tool_exchange` emit 修复 | `ToolExchangeTurn` 折叠块 |
| 加厚统计返回 | `AnalystReviewTable` 效应量/CI 有数据来源 |
| `create_plot` artifact | 报告/HTML 可引用 |
| `/api/kb` frontmatter | `KnowledgePanel` 标题/摘要更准确 |

两 PR 可并行；**tool_exchange EventType** 只应修一次（先合者优先）。

---

## §11 预估工作量

**5–7 人天**（含测试 + prompt dump 对比），**一个 PR**。若同时做 §12 Doctor 维护闭环，增量 **+2–3 人天**，建议仍放同一个「工具箱增强」PR，便于把方法文档 / 工具注册 / 维护 gate 一次对齐。

建议编码顺序（非里程碑）：删 registry → 拆文件 → 接通 stat/power → 重构 run_statistical_test → biz/cleaning/viz → KB frontmatter → prompt → 测试。

---

## §12 HaGoKu Doctor 维护扩展评估与规格

> **结论**：Doctor 可以负责知识库和工具箱的**后期维护闭环**，但角色必须是 **审稿人 + 脚手架 + gate**，不是第二个会自动修改生产代码的 agent。
>
> **核心边界**：Doctor 可以自动生成报告、草稿、缺口清单；写入 `memory/methods/` 和 `hagoku/tools/` 必须走 PR / 用户确认 / CI。

### 12.1 为什么要把这件事放进 Doctor

Phase D 后只剩一个 `DataAnalystAgent`，它的能力来自两类资产：

| 资产 | 风险 |
|------|------|
| `memory/methods/**/*.md` | 方法文档过期、frontmatter 缺 `tools`、知识库里有方法但无执行工具 |
| `agent_tools` | 工具已注册但无方法说明、prompt 写了不存在的工具、返回结构不满足 p/效应量/CI |

这类风险不是单次分析 bug，而是**系统资产腐化**。它和 LessonAuditor 审 lessons 属于同一类「维护问题」，所以应挂到 HaGoKu Doctor，而不是塞回 DataAnalystAgent。

但 Meta v2 已明确 `LessonAuditor` 只审 ② 成长记忆：

```text
只审 ② 层（成长记忆），不审 ① 学术方法库 / ③ 项目记忆
```

因此不要扩写 LessonAuditor 的职责。新增独立组件：

```
HaGoKu Doctor
├── Prompt Lab          # 已有：prompt 模拟 / 应用
├── LessonAuditor       # 已有：② 成长记忆审计
├── MethodCurator       # 新增：① 学术方法库维护
└── ToolCurator / gate  # 新增：③ 工具箱一致性审计
```

### 12.2 分工边界

| 组件 | 可自动做 | 不可自动做 |
|------|----------|------------|
| **MethodCurator** | 扫 `methods/*.md`；检查 frontmatter；生成缺口报告；起草新方法文档到 staging 目录 | 直接覆盖正式方法文档 |
| **ToolCurator** | 扫 `agent_tools`；检查工具是否有文档、测试、返回结构；生成 schema 草稿 | 直接注册新工具、修改 Python handler |
| **tool_gate** | CI / 本地脚本校验一致性 | 自动修复生产代码 |
| **DataAnalystAgent** | 分析时查知识库、调工具 | 自己维护工具箱 |

**原则**：运行时分析和系统维护彻底分离。Doctor 看资产，DataAnalystAgent 看数据。

### 12.3 新增文件结构（建议）

```
hagoku/agents/method_curator/
├── agent.py                 # 只读扫描 + LLM 评审 + 报告/草稿
├── prompt.md                # 方法库审计职责
└── __init__.py

hagoku/agents/tool_curator/
├── agent.py                 # 工具注册表审计 + schema 草稿
├── prompt.md
└── __init__.py

scripts/ci/tool_gate.py      # 确定性 gate，不依赖 LLM

~/.hagoku/audits/
├── method_audit_<ts>.md
├── tool_audit_<ts>.md
└── drafts/
    ├── methods/<domain>/<slug>.md
    └── tools/<tool_name>_schema.md
```

### 12.4 MethodCurator 规格

**触发**：

- 手动：Prompt Lab / Doctor 面板按钮「审知识库」
- CLI：`hagoku doctor audit-methods`
- 可选月度：每月一次，只产报告

**输入**：

- `hagoku/memory/methods/**/*.md`
- `agent_tools` 已注册工具名
- `hagoku/agents/prompt.md` 中的工具表（只读）

**检查项**：

| ID | 检查 | 失败示例 |
|----|------|----------|
| MC-01 | frontmatter 必含 `title/category/summary/tags/tools` | `ttest.md` 无 `tools` |
| MC-02 | `tools` 中每个工具必须存在于 `agent_tools` | `power_analysis` 写了但未注册 |
| MC-03 | 每个统计工具至少有一篇方法文档引用 | `diagnose_regression` 无文档 |
| MC-04 | 方法文档正文必须含「适用场景 / 假设 / 局限 / 报告格式」 | 只有概念介绍 |
| MC-05 | 文档不得声称因果，除非关联因果推断工具 | ROI 文档写「导致增长」 |

**输出**：`~/.hagoku/audits/method_audit_<ts>.md`

报告结构：

```markdown
# Method Audit

## Summary
- methods: 12
- tools referenced: 18
- missing frontmatter: 2
- missing tool docs: 4

## Blocking
- `statistics/power-analysis.md` references `power_analysis`, but registered tool is `assess_statistical_power`.

## Draft Suggestions
- Create `business/roi-roas.md`
- Add `tools: [calc_roi, calc_roas]`
```

**草稿模式**：可写到 `~/.hagoku/audits/drafts/methods/...`，不写入仓库。用户/开发确认后复制到正式路径。

### 12.5 ToolCurator / tool_gate 规格

ToolCurator 是 LLM 审稿人，`tool_gate.py` 是确定性守门脚本。两者不要混。

#### ToolCurator（LLM，建议）

**检查项**：

| ID | 检查 | 说明 |
|----|------|------|
| TC-01 | 工具 description 是否说明输入/输出/何时用 | 给 LLM 看的工具描述必须足够具体 |
| TC-02 | JSON Schema 是否含 required / enum | 防止 LLM 乱传 |
| TC-03 | 统计工具返回是否含 p/效应量/CI | 对齐 PROJECT「准」 |
| TC-04 | 工具是否有测试 | 至少 smoke |
| TC-05 | 是否有方法文档引用 | 与知识库成对 |
| TC-06 | prompt.md 是否提到不存在的工具 | 当前已有问题 |

**输出**：`~/.hagoku/audits/tool_audit_<ts>.md`

ToolCurator 可以起草 schema 文档，但不写 Python：

```markdown
## Proposed Tool: assess_statistical_power

Description:
评估当前数据在指定检验下的统计功效...

Parameters:
...

Expected return:
...

Required tests:
- small n returns warning
- adequate n returns power
```

#### tool_gate.py（确定性，必做）

**路径**：`scripts/ci/tool_gate.py`

**触发**：

- CI：PR 触及 `hagoku/tools/` 或 `hagoku/memory/methods/`
- 本地：`python scripts/ci/tool_gate.py`
- Prompt Lab / Doctor 面板：只读运行，显示结果

**确定性规则**：

| Gate | 规则 |
|------|------|
| G1 | 所有 `methods/*.md` frontmatter 可解析 |
| G2 | `tools:` 引用的工具必须存在于 `agent_tools._tools` |
| G3 | 每个新增 `agent_tools.register(Tool(name=...))` 必须被至少一篇 method 文档引用，除流程/记忆类工具外 |
| G4 | prompt.md 反引号工具名必须存在于注册表或在 allowlist（如 `submit_field_inference` 私有 tool） |
| G5 | 统计类工具名匹配 `run_|check_|assess_|diagnose_|correct_` 时，测试文件必须存在 |
| G6 | 禁止恢复 `analysis_registry.py` import |

**输出 JSON**：

```json
{
  "ok": false,
  "errors": [
    {
      "code": "METHOD_TOOL_MISSING",
      "file": "hagoku/memory/methods/statistics/power-analysis.md",
      "tool": "power_analysis"
    }
  ],
  "warnings": []
}
```

**失败策略**：CI hard fail。Doctor 面板显示错误，不自动修。

### 12.6 与现有 Meta v2 的关系

这不是推翻 Meta v2，而是补齐它当时刻意不做的范围：

| Meta v2 | 本节新增 |
|---------|----------|
| Prompt Lab 管 prompt | 保持 |
| LessonAuditor 管 lessons | 保持 |
| prompt_gate 管 prompt 退化 | 保持 |
| 不审学术方法库 | **新增 MethodCurator** |
| 不审工具箱 | **新增 ToolCurator + tool_gate** |

Meta v2 砍掉“大 Doctor agent 什么都干”是正确的。本节采用**多组件 Doctor**，每个组件单一职责、只读优先、写入走 gate。

### 12.7 实施清单 CO-D01～CO-D14

| ID | 内容 | 文件 |
|----|------|------|
| CO-D01 | 新建 `method_curator` 包和 prompt | `hagoku/agents/method_curator/` |
| CO-D02 | MethodCurator 扫描 methods + agent_tools + prompt 工具表 | `agent.py` |
| CO-D03 | MethodCurator 输出 `method_audit_<ts>.md` | `~/.hagoku/audits/` |
| CO-D04 | 可选草稿写入 `~/.hagoku/audits/drafts/methods/` | `agent.py` |
| CO-D05 | 新建 `tool_curator` 包和 prompt | `hagoku/agents/tool_curator/` |
| CO-D06 | ToolCurator 输出 `tool_audit_<ts>.md` | `agent.py` |
| CO-D07 | 新建 `scripts/ci/tool_gate.py` | `scripts/ci/` |
| CO-D08 | `tool_gate.py` 实现 G1～G6 | `scripts/ci/tool_gate.py` |
| CO-D09 | API 增加 Doctor 审计端点 | `hagoku/api/server.py` 或新 router |
| CO-D10 | Settings / Prompt Lab 增「Doctor 维护」按钮（可在 Web UI brief 后做） | `hagoku_web/src/panels/SettingsPanel.tsx` |
| CO-D11 | CLI 命令：`hagoku doctor audit-methods` / `audit-tools` / `tool-gate` | `hagoku/cli.py` |
| CO-D12 | 单测：frontmatter 解析、缺失工具、prompt 虚假工具 | `tests/test_ci/test_tool_gate.py` |
| CO-D13 | 单测：MethodCurator 报告生成（mock meta LLM 或纯规则部分） | `tests/test_agents/test_method_curator.py` |
| CO-D14 | 文档：PR body 写清「Doctor 只审不自动改生产」 | 本 brief |

### 12.8 不做什么

| 不做 | 原因 |
|------|------|
| Doctor 自动写 `hagoku/tools/*.py` | 可执行代码必须人审 |
| Doctor 运行时给 DataAnalystAgent 动态注册工具 | 会让生产不可追踪 |
| 用关键词规则决定工具选择 | 铁律 1 |
| 合并 LessonAuditor / MethodCurator / ToolCurator 成一个大 agent | 回到 v5 复杂度 |
| 自动修改 prompt.md | 仍由 Prompt Lab + prompt_gate |

### 12.9 验收

- [ ] `tool_gate.py` 能发现：method 文档引用不存在工具
- [ ] `tool_gate.py` 能发现：prompt.md 反引号里写了未注册工具（私有 allowlist 除外）
- [ ] `MethodCurator` 能输出方法库缺口报告
- [ ] `ToolCurator` 能输出工具 schema/测试缺口报告
- [ ] Doctor 不直接修改仓库文件，只写 `~/.hagoku/audits/`
- [ ] `pytest tests/test_ci/test_tool_gate.py -v` 绿
- [ ] `pytest tests/test_agents/test_method_curator.py -v` 绿

### 12.10 最终定位

HaGoKu Doctor 的后期职责应是：

> **维护系统资产的一致性**：prompt 说的、知识库写的、工具箱注册的、测试覆盖的，四者必须互相对得上。

DataAnalystAgent 负责分析；Doctor 负责防止分析能力的地基腐烂。
