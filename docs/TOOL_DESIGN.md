# 工具设计审计与演进

> **核心判准**：工具 = LLM 物理上做不到的事。分析方法 ≠ 工具（训练数据里有）。

---

## 工具三问（每个工具必须过）

1. **LLM 不调这个工具，能靠自己的知识完成吗？** — 能 → 不是工具，删
2. **工具描述里有没有"什么时候该用"的规则？** — 有 → 规则该在 prompt，不在描述里
3. **同一件事有几个工具入口？** — 超过 1 个 → LLM 会犹豫，合并

---

## 审计发现（2026-06-21，基于 agent_tool_defs.py + stat_tools.py + cleaning_tools.py + memory_tools.py + viz_tools.py）

### 问题 A：判断被包成了工具

| 工具 | 问题 | 建议 |
|------|------|------|
| `suggest_cleaning` | 根据规则推荐清洗策略。分析方法是 LLM 知识库里的知识，不需要做成工具 | 删除 |
| `interpret_nonsignificant` | "p>0.05 时怎么解读"——纯粹是 LLM 训练数据里的统计学知识 | 删除 |
| `update_field_role` | handler 只做 `return args`，无任何副作用——LLM 调了等于没调 | 删除或合并进 `set_columns` |
| `restrict_analysis_to` | handler 只做 `return args`——无状态写入 | 删除或合并进 `set_columns` |

### 问题 B：同一件事暴露多个入口

修改字段状态的工具有 **5 个**：

```
set_columns          ← 写字段理解（主力）
update_field_table   ← 又一种写字段的方式
update_field_role    ← 只改角色（handler 无副作用）
restrict_analysis_to ← 缩小范围（handler 无副作用）
update_analysis_scope ← 扩大/缩小范围
```

LLM 面对 5 个相似工具，等于面对 5 把形状差不多的扳手——不知道该用哪把。

**建议**：统一为 `set_columns`（已支持批量），其他 4 个删除或做成 `set_columns` 的字段别名。

### 问题 C：工具描述里塞了 prompt

对比 IDE 里的工具描述：

```
# IDE 风格（只说"我能做什么"）
read_file(path) → "读取指定路径的文件内容"
```

当前 HaGoKu 工具描述：

```
# HaGoKu 风格（塞满"你什么时候该用我"）
route_to → 14 行规则（"用户说确认 → 你必须调"、"每个阶段只能向前"）
ask_user → 12 行典型用法（"scout: 展示完字段理解表后 → ask_user(...)"）
submit_first_pass → "仅在 Analyst 阶段首次进入时使用；后续用 submit_analysis"
```

**结果**：工具描述变成了隐形 prompt，和 prompt.md 信号冲突 → LLM 犹豫、反复。

**建议**：工具描述只写"我做什么 + 参数含义"，"何时调"的逻辑放在 prompt.md 的阶段描述里。

### 问题 D：submit 工具分裂

`submit_first_pass` 和 `submit_analysis` 结构完全相同（findings + method_used + summary），只是"首波"和"后续"的区别。LLM 需要判断"我是第几次被调用"才能选对工具——**这是让 LLM 做状态跟踪，而状态跟踪是代码该做的事**。

**建议**：合并为一个 `submit_findings`，由代码（run_step 上下文）判断是首波还是后续。

---

## 为什么 LLM 不如在 IDE 里流畅

| 维度 | IDE 模式 | HaGoKu 当前 |
|------|----------|------------|
| 工具数量 | ~10 个通用工具 | 24 个专用工具 |
| 工具描述 | 1-2 行，只说能力 | 5-15 行，嵌满规则 |
| 决策负担 | LLM 从上下文自由决策 | LLM 要同时满足 prompt + 工具描述规则 + 上下文 |
| 重叠 | 无（每个工具功能唯一） | 5 个工具改字段、2 个工具提交分析 |
| 状态感知 | 不需要（工具无状态） | 需要知道"我在哪个阶段""这是第几次" |

**核心差异**：IDE 给 LLM 少量万能工具 + 完全的决策自由。HaGoKu 给 LLM 大量专用工具 + 描述里嵌满规则。规则越多，LLM 越犹豫。

---

## 修改思路

### 方向 1：精简（最小侵入，当前可做）

1. **删除判断类工具**：`suggest_cleaning`、`interpret_nonsignificant`
2. **合并字段工具**：保留 `set_columns` + `update_analysis_scope`，删除 `update_field_table`、`update_field_role`、`restrict_analysis_to`
3. **合并 submit**：`submit_first_pass` + `submit_analysis` → `submit_findings`
4. **精简描述**：每个工具描述控制在 2 行以内，删除所有"何时使用"规则

预期效果：24 → ~18 工具，描述总 token 减半。

### 方向 2：重构（更激进，效果更好）

将"读数据"和"跑统计"两类工具各合并为一个万能入口：

| 新工具 | 替代 | 说明 |
|--------|------|------|
| `query_data(expression)` | get_column_stats, get_sample_rows, list_columns, group_stats | LLM 传 pandas 表达式，系统执行后返回结果 |
| `run_stats(code)` | run_statistical_test, check_test_assumptions, detect_outliers, detect_missing_pattern, assess_statistical_power, required_sample_size, correct_multiple_comparisons, diagnose_regression | LLM 传 Python 代码片段，在沙箱执行 |
| `set_columns(columns)` | 所有字段写入工具 | 唯一状态写入 |
| `submit(data)` | submit_assessment, submit_analysis, submit_first_pass | 唯一提交入口 |
| `create_plot(...)` | 不变 | |
| `route_to(stage)` | 不变 | 描述精简到 1 行 |
| `ask_user(question)` | 不变 | 描述精简到 1 行 |
| `remember(...)` / `recall(...)` | 7 个记忆工具 | 合并记忆读写 |

预期效果：24 → ~8 工具。接近 IDE 工具数量级。

### 方向 3：终极形态

只要 LLM 能写代码，理论上只需要：

```
read_data(expression)   — 读
run_code(code)          — 算+画
set_state(key, value)   — 写
signal(action, payload) — 控制（route_to / submit / ask_user 统一）
```

4 个工具。但这依赖 LLM 的代码生成质量，小模型可能不够稳定。

---

## 工具描述精简模板

**当前（反面教材）**：

```
route_to: "切换分析阶段。你必须在当前阶段的工作全部完成后才调用此工具。
           标准流程（必须按顺序）：scout → cleaner → analyst → reporter
           规则：用户说「确认」→ 你必须调 route_to...
           每个阶段只能向前..." (14行)
```

**精简后**：

```
route_to: "切换到指定分析阶段。" (1行)
```

"何时切换"的判断由 LLM 从对话上下文自己推导——这是语义判断，是 LLM 的强项，不该写在工具描述里。prompt.md 里已经写了"确认后 route_to("cleaner")"，不需要工具描述再重复一遍。

---

## 当前工具清单（12 个，2026-08-18 核对）

> **运行时验证**：`python3 -c "from hagoku.tools import agent_tools; print(sorted(agent_tools._tools.keys()))"`
> 列出全部 12 个，与本表一一对应。

| # | 工具 | 描述 | 类别 |
|---|------|------|------|
| 1 | `get_column_names` | 列出数据集中所有列名 + 行数。 | 数据探查 |
| 2 | `get_column_stats` | 获取某列的统计信息：min/q25/median/q75/max/mean/std/null_count。 | 数据探查 |
| 3 | `get_group_stats` | 按某列分组聚合 count/mean/std/min/max。 | 数据探查 |
| 4 | `set_columns` | 写入你对字段的理解（中文名 + 业务含义 + role + evidence）。批量推荐。 | 字段管理 |
| 5 | `run_statistical_test` | 调度 ttest/anova/chi2/pearson/spearman/回归/趋势分解，返回 p/effect_size/CI。 | 统计与清洗 |
| 6 | `detect_outliers` | 检测异常值（IQR 或 Z-score）。 | 统计与清洗 |
| 7 | `detect_missing_pattern` | 检测缺失机制（MCAR/MAR/MNAR）并给填充建议。 | 统计与清洗 |
| 8 | `create_plot` | 生成交互式图表（Plotly，散点/折线/柱/直方/箱/小提琴/热力）。 | 可视化·报告·记忆 |
| 9 | `generate_report` | 渲染 HTML 报告（Jinja 模板，自动注入 create_plot 图表）。 | 可视化·报告·记忆 |
| 10 | `recall_lessons` | 跨对话经验库检索。 | 可视化·报告·记忆 |
| 11 | `save_lesson` | 持久化一条新经验。 | 可视化·报告·记忆 |
| 12 | `query_project_memory` | 读项目记忆（fields/history/corrections 三 aspect）。 | 可视化·报告·记忆 |

**所有工具均为纯 I/O**——不携带流程信号（无 submit/ask/route/pause/confirm 语义）。LLM 调完工具后自然回话推进，代码不替 LLM 管阶段。

### 已删除

| 工具 | 原因 |
|------|------|
| `ask_user` | 违反铁律 14（工具即 I/O）。LLM 直接输出文字提问即可 |
| `route_to` | 单 Agent 自驱动后不再需要。阶段切换由 LLM 读历史决定（2026-06-11 Phase D） |
| `submit_findings` / `submit_assessment` / `submit_first_pass` / `submit_analysis` / `submit_report` | 违反铁律 14。LLM 直接输出文字即可，代码不再有"发现卡片"概念 |
| `set_columns` 之外的所有 `update_field_*` / `restrict_analysis_to` | handler 只 return args 无副作用，纯 LLM 知识（已合并/删除） |
| `get_sample_rows` | LLM 通过 `get_column_stats` 即可获得样本信息 |
| `list_columns` | 重命名为 `get_column_names`（同时返回行数） |
| `group_stats` | 重命名为 `get_group_stats` |
| `check_test_assumptions` | 检验方法选择是 LLM 任务，不是工具 |
| `correct_multiple_comparisons` | 多重比较校正可通过 `run_statistical_test` 后续扩展 |
| 7 个 biz_tools（ROI/ROAS/LTV 等） | 公式是 LLM 训练数据自带的知识 |

---

## 检验标准

工具改完后，用这两个问题验证：

1. **描述测试**：把工具描述给一个不懂项目的人看——他只应该知道"这个工具做什么"，不应该知道"什么业务场景该用它"
2. **删除测试**：如果删掉一个工具，LLM 的输出质量是否下降？不下降 → 这个工具不该存在

---

## 变更记录

| 日期 | 版本 | 内容 |
|------|------|------|
| 2026-06-21 | v1 | 初稿：审计发现 4 类问题 + 3 个优化方向 |
| 2026-06-21 | v2 | 精简完成：24→15 工具，审查通过 |
| 2026-08-18 | v3 | 与 runtime 对齐：12 工具；删 ask_user/route_to/submit_* 等所有流程控制工具；4 个 memory_tools 已重新注册 |
