# HaGoKu — 项目规范（The Single Source of Truth）

## 灵魂

> **让每个小模型，都能做专业级商业分析。**

HaGoKu 不是另一个数据可视化工具。绝大多数"AI 数据分析"只做图+描述性统计——那是表面功夫。HaGoKu 追求的是**统计分析深度**：自动检验假设、报告效应量、做模型诊断、区分因果和相关。同时不牺牲信息设计的吸引力——**门面吸引用户走进来，地基让用户留下来**。

---

## 设计哲学

| 维度 | 含义 |
|------|------|
| **精** | 报告结论精炼：不超过 5 条核心发现 |
| **准** | 每条结论有统计检验支撑（p值 + 效应量 + 置信区间） |
| **狠** | 直接回答用户问题，不回避不确定性的本质 |
| **轻量** | 本地 LLM 优先，最小依赖，本地数据不出本机 |
| **连续性** | 分析结果持久化，可追溯，可积累，可对比 |
| **专业** | 严肃对待不确定性，不假装100%确定 |

---

## Agent 角色设计

HaGoKu 不是 chatbot，是**多 Agent 协作分析引擎**。核心角色：

| Agent | 一句话职责 | 关键能力 |
|-------|-----------|---------|
| 🔍 **Scout** | 理解数据里有什么 | 类型推断、语义分析、缺失/分布报告、生成 DataContext |
| 🧹 **Cleaner** | 数据清洗但不破坏信息 | 缺失机制检验（MCAR/MAR/MNAR）、异常区分（测量误差 vs 真实极端值）、清洗影响评估 |
| 📊 **Analyst** | 回答用户问题的统计分析核心 | 假设检验、回归分析、效应量报告、模型诊断、因果推断（V3） |
| 📝 **Reporter** | 把分析结果变成人话报告 | 双轨输出（吸引力层 + 核心价值层）、模板渲染、结论措辞 |
| 📋 **Scribe** | 后台记录 + 仲裁 + 知识调度 | 确定性逻辑引擎，零 LLM 调用。看板管理、记忆维护、知识库检索与注入、字段决策仲裁、Agent 经验更新 |

> **Scribe 不是 Agent。** 它是确定性逻辑引擎，不调用 LLM，不做分析决策。它负责后台基础设施：记录所有 Agent 的输入输出、管理项目看板、维护双记忆系统、从知识库中检索相关内容注入 Agent prompt、在 Scout/Analyst 对字段角色有分歧时仲裁。

**协作机制**：Scribe 是 Agent 的"外骨骼"——Agent 负责分析决策，Scribe 负责给 Agent 装备知识（注入 prompt）、记录决策（写入 memory）、仲裁分歧（字段角色）。Agent 不用主动查知识库，Scribe 在启动前注入。

### 仲裁器（Arbitrator）— 规则引擎 + LLM 决策

仲裁器取代了传统的独立 Manager Agent。它位于 `manager/orchestrator.py`，负责：

- **计划生成**：接收用户 query → 产出分析计划（调用 LLM 生成 plan JSON）
- **调度执行**：按计划顺序调度 Agent，传递数据制品
- **进度监控**：跟踪每个 Agent 的状态，检测失败并降级
- **规则兜底**：80% 的常见场景有预定义规则覆盖，LLM 仅处理新场景

### 人机互动理念（Web / 全流程）

- **不是「静态聊天框」**：产品形态接近**有流程的协作**——流水线顺序固定（Scout → Cleaner → Analyst → Reporter），但在**规定暂停点**由 Agent **主动打断、说明当前发现、并向用户提问**；用户用自然语言回复后继续执行。
- **话术动态、流程静态**：各暂停点展示给用户的文字由 **LLM 根据当次运行结果生成**；**不**用固定模板冒充「对话」。系统只锁定「何时暂停」，**不**锁定「暂停时说什么」。
- **无用户模式分级**：不提供「快速 / 普通 / 资深」等自主度档位；互动深度由**流程中的暂停与回复**体现，与「始终可对话、Agent 主动引导」一致。
- **Web UI 当前形态**（`hagoku_web/`）：**固定侧栏/顶栏视图切换**（项目、分析、报告、知识、事件等），**不再使用 dockview 可拖拽多 Tab**。分析页：**「开始分析」**进入流程；**流水线状态** + **对话气泡**承载 Agent 消息；用户通过 **WebSocket `respond`** 提交回复。报告页：默认 HTML **双轨**（要点速览 / 数据与完整证据）。

---

## 报告设计 — 双轨输出

### 原则

报告是门面，但用户应该能穿透门面看地基。每个分析报告有两层：

| 层 | 面向 | 内容 | 格式 |
|----|------|------|------|
| **吸引力层**（门面） | 所有人 | 核心结论（≤5条）、关键图表、通俗解读 | HTML 优先，交互式图表 |
| **核心价值层**（地基） | 懂行的人 | 完整统计结果、检验假设、方法细节、诊断数据 | 可折叠/链接到详细说明 |

### 模板

```
{项目名}/report_{日期}.html
```

内置模板名（`ReportGenerator` / `hagoku run --template`）：**`default`** 为当前默认，即 **双轨 HTML**（要点速览 + 数据与完整证据）；另有 `business_analysis`、`academic`、`ab_test`、`executive_brief`、`data_audit`、`brief` 等，版式可能仍为单栏，与 `default` 不同。未指定 `--template` 时使用 `default`。模板管呈现风格，AI 管内容生成。

---

## 知识系统 — 三层架构

```
Layer 1: kb/  领域知识（手写，稳定）         stats/ + financial/ + business/
Layer 2: agent/knowledge.yaml  方法经验（自动积累）   场景签名 → 方法映射
Layer 3: LLM 自由发挥（兜底）               无匹配时自行判断
```

| 层 | 更新频率 | 维护者 | 注入方式 |
|----|---------|--------|---------|
| kb/（领域知识） | 低频，人工 | 开发者 | Scribe 检索匹配后注入 prompt |
| knowledge.yaml（方法经验） | 每次分析后 | Scribe 自动 | Scribe 匹配场景签名后注入 prompt |
| LLM 自由发挥 | N/A | 无 | 前两层无匹配时的兜底 |

### 注入机制

**Agent 不主动查知识库。** Scribe 在 Agent 启动前完成检索和注入：

1. Scribe 收到仲裁器的 Agent 调用请求
2. 根据 query 和数据上下文的关键词匹配 kb/ 中的知识条目
3. 匹配 knowledge.yaml 中的场景签名
4. 将匹配到的知识内容 + 方法经验注入 Agent 的 system prompt
5. Agent 启动时已携带相关知识

### 双记忆系统

**项目记忆** (progress.yaml)：字段决策、用户偏好、分析历史。跟随项目生命周期，Scribe 维护。

```yaml
# ~/.hagoku/projects/{name}/progress.yaml
project: sales_analysis
created_at: 2026-05-01
milestones:
  - date: 2026-05-01
    event: "首次分析"
    query: "广告投入对销售有没有影响"
    result: "3个显著发现，R²=0.87"
user_preferences:
  - key: "preferred_regression_method"
    value: "robust"
field_decisions:
  - column: "revenue"
    semantic: "target"
    confirmed_by: "user"
```

**Agent 记忆** (memory.md)：方法运用经验。跨项目积累，Scribe 维护。

```
# Analyst 方法运用经验

## 已验证的方法选择
- 分组对比 + 非正态 + 小样本 → Mann-Whitney U（成功7次）
- 回归 + 非正态 → 稳健回归（成功4次）

## 失败教训
- 小样本(n<15)不要做多元回归（自由度不够）

## 用户偏好
- 偏好稳健回归，喜欢效应量实际意义解读
```

**记忆调用三层保障**：① Scribe 主动注入（最可靠） ② Agent prompt 内置回顾提醒 ③ 分析后结果校验。

**记忆写入规则**：✅ 用户偏好、纠正的字段含义、输出风格选择；❌ 数据特征、统计结果（在 SQLite 里）、临时状态。

---

## 看板协作 — Agent 间通道

HaGoKu 的 Agent 之间不直接对话，通过**看板**交换信息：

```
~/.hagoku/projects/{project}/
├── kanban.db       ← SQLite 看板数据库（Agent 间消息队列）
├── context.md      ← 项目上下文摘要（所有 Agent 共享）
├── data/           ← 数据制品
├── runs/           ← 分析运行记录
└── progress.yaml   ← 项目记忆
```

**context.md** 结构：
```
# 项目：sales_analysis

## 已确认的字段角色
| 字段 | 角色 | 确认方式 | 时间 |
...

## 用户已确认的偏好
- 分析方法：稳健回归（2026-05-01 确认）

## 数据质量概要
- 最终数据源：@data/cleaned_20260501.parquet
```

**读上下文规则**：Agent 启动时先读 context.md。如果关键字段角色都已确认（`confirmed_by: user`），直接使用；否则标注需确认项。

---

## 统计护栏 — 三级安全网

保证分析不犯低级错误。

### 强制级（Violation = 阻止输出）

| 规则 | 说明 |
|------|------|
| `no_conclusion_without_test` | 没有统计检验不许下结论 |
| `must_report_effect_size` | 报告显著性必须配效应量 |
| `must_report_ci` | 点估计必须配置信区间 |
| `no_causal_claim_without_method` | 观测数据必须用因果推断才能声称因果 |
| `must_diagnose_model` | 建模后必须做残差诊断、VIF |

### 警告级（Violation = 标注但允许输出）

| 规则 | 说明 |
|------|------|
| `assumptions_violated` | 假设不满足时标注，建议替代方法 |
| `small_sample_size` | 样本量不足时警告 |
| `high_vif` | 多重共线性超标时警告 |
| `potential_overfitting` | 训练测试差异过大时警告 |
| `cleaning_high_impact` | 清洗影响 >10% 数据时警告 |

### 提示级（Violation = 建议不阻断）

| 规则 | 说明 |
|------|------|
| `suggest_nonlinear` | 残差暗示非线性时建议 |
| `suggest_interaction` | 可能交互效应时建议 |
| `missing_not_random` | 缺失非随机时建议谨慎 |
| `consider_power_analysis` | 建议功效分析确认样本量 |

---

## 降级策略

| Agent | 失败场景 | 降级方案 | 用户感知 |
|-------|---------|---------|---------|
| Analyst | 回归失败 | 只做描述性统计 + 效应量估计 | 报告中说明 |
| Analyst | 假设检验失败 | 报告原始统计量，标注"结论需谨慎" | 报告中标注 ⚠️ |
| Analyst | LLM 自由发挥失败 | 降级到工具集保守方法 | 无感知 |
| Cleaner | 填补失败 | 保留缺失值，标注"未处理" | 报告中说明 |
| Cleaner | 异常检测失败 | 不处理异常，标注"未做异常检测" | 报告中说明 |
| Scout | 语义推断失败 | 标记 UNKNOWN | 等待用户确认 |
| 仲裁器 | LLM 超时 | 规则引擎兜底计划 | 无感知 |
| Reporter | 模板渲染失败 | 降级到 Markdown 纯文本 | 格式简化 |

---

## 数据流与持久化

### 一次分析的数据流

```
原始数据
  │
  ▼ Scout → DataContext + raw.parquet
  ▼ Cleaner → CleaningReport + cleaned.parquet
  ▼ Analyst → list[AnalysisResult] + diagnostics/
  ▼ Reporter → Report (HTML/PDF)
  ▼ 用户
```

**数据传递格式**：Parquet 文件 + 元数据 JSON（DataArtifact：artifact_id, file_path, schema, lineage, cleaning_impact）。

### 存储架构

```
~/.hagoku/
├── config.yaml
├── hagoku.db                      # SQLite 元数据库
└── projects/{name}/
    ├── progress.yaml               # 项目记忆
    ├── context.md                  # 看板上下文
    ├── kanban.db                   # Agent 看板
    ├── data/                       # 数据制品 (raw/cleaned .parquet)
    ├── runs/{run_id}/              # 分析运行
    │   ├── run_meta.json
    │   ├── plan.json
    │   ├── events.jsonl
    │   ├── context.json
    │   ├── cleaning.json
    │   ├── results/               # 结构化分析结果
    │   ├── diagnostics/           # 诊断图
    │   └── output/                # 报告
    └── reports/
        ├── latest.html → runs/{latest}/output/report.html
        └── latest.pdf  → runs/{latest}/output/report.pdf
```

### SQLite 元数据库

核心表：`projects`（项目注册）、`runs`（运行记录，含 query/status/token_count）、`findings`（结构化发现，p值/效应量/置信区间）、`artifacts`（数据制品追踪+数据血缘）。

**持续性分析能力**：

```bash
hagoku history --project sales_analysis    # 查看历史分析
hagoku run --project X --resume --query "..."  # 复用已清洗数据（V2）
hagoku query "所有 p<0.01 的发现"          # 查询历史发现（V2）
```

> **V2** 计划支持 `diff` 对比两次分析结果、外部数据库直连（PostgreSQL/MySQL）。MVP 阶段聚焦本地文件。

---

## 用户场景

**广告投入对销售有没有因果影响？**

```
❌ 表面功夫：广告支出和销售额正相关，相关系数 0.89

✅ HaGoKu 方向：
   - 控制混淆变量后的因果效应估计（β、CI、p值）
   - 效应量的实际意义（每增加1万广告预算，销售额增加多少）
   - 效应的边界条件（季节/条件下如何变化）
   - 残差诊断结果（排除其他解释）
   - 具体措辞由 Analyst + Reporter 自主生成
```

---

## 可观测性

HaGoKu 全程透明，用户坐副驾驶位，可视化工作流进度：

```
🔍 Scout ──── ✅ 完成 (12s)
🧹 Cleaner ── ✅ 完成 (8s)
📊 Analyst ── 🔄 执行中...
📝 Reporter ── ⏳ 等待中
⚖️ 仲裁器 ── 监控中
```

---

## 项目结构

使用 flat 布局（`hagoku/` 在项目根，不是 `src/` 布局）。

```
hagoku/
├── pyproject.toml
├── README.md
├── PROJECT.md                    # 本文件 — 唯一真相源
├── DEV.md                        # 开发指南
├── CLAUDE.md                     # AI 编码助手上下文
├── .env.example
│
├── hagoku/                      # flat 布局，全部代码
│   ├── cli.py                    # CLI 入口 (Click)
│   ├── config.py                 # 全局配置
│   ├── log.py                    # 结构化日志
│   │
│   ├── llm/                      # LLM 客户端
│   │   ├── client.py             # OpenAI-compatible API
│   │   ├── plan_schema.py        # Pydantic 计划 Schema
│   │   └── prompts.py            # 提示词模板
│   │
│   ├── manager/                  # 仲裁器（规则引擎 + LLM 决策）
│   │   ├── orchestrator.py       # 计划生成 + 调度 + 降级
│   │   ├── query_parser.py       # 自然语言解析
│   │   └── refinement.py         # 追问/交互式分析
│   │
│   ├── agents/                   # 4 个专业 Agent + Scribe 后台
│   │   ├── base.py               # Agent 基类
│   │   ├── types.py              # 公共类型
│   │   ├── _interactive.py       # CLI 交互处理
│   │   ├── scout.py / cleaner.py / analyst.py / reporter.py  # 委托入口
│   │   ├── scout/                # Scout Agent
│   │   │   ├── agent.py, prompt.md, memory.md, knowledge.yaml, knowledge.py
│   │   ├── cleaner/              # Cleaner Agent（同上结构）
│   │   ├── analyst/              # Analyst Agent（同上结构）
│   │   ├── reporter/             # Reporter Agent（同上结构）
│   │   └── _scribe/              # Scribe（确定性引擎，非 Agent）
│   │       ├── agent.py, prompt.md, process_log.md
│   │
│   ├── kb/                       # 领域知识库（Layer 1）
│   │   ├── knowledge_base.py     # 检索 + 注入引擎
│   │   ├── _registry.yaml        # 条目索引
│   │   ├── stats/                # ttest, anova, regression, power-analysis, multiple-testing
│   │   ├── financial/            # roi, ltv-cac, attribution
│   │   └── business/             # ab-test, funnel, cohort-analysis
│   │
│   ├── tools/                    # 分析工具集（插件架构）
│   │   ├── analysis_registry.py  # 方法注册中心
│   │   ├── data_io.py            # 数据加载 (Pandas, DuckDB)
│   │   ├── profiling.py          # 数据画像 (ydata-profiling)
│   │   ├── cleaning.py           # 清洗 (sklearn, PyOD, cleanlab)
│   │   ├── analysis.py           # 统计入口 (Pingouin, Statsmodels)
│   │   ├── business.py           # 商业分析 (ROI/ROAS/LTV/CAC)
│   │   ├── diagnostics.py        # 模型诊断
│   │   ├── health.py             # 系统健康检查
│   │   ├── power_analysis.py     # 功效分析
│   │   ├── visualization.py      # 可视化 (Plotly, Matplotlib)
│   │   └── reporting.py          # 报告渲染 (Jinja2)
│   │
│   ├── guardrails/               # 三级统计护栏 + 结构化输出解析
│   │   ├── statistical.py
│   │   └── parsers.py
│   │
│   ├── storage/                  # 持久化
│   │   ├── kanban.py             # 项目看板 (SQLite)
│   │   ├── project_manager.py    # 项目管理
│   │   ├── artifact.py           # DataArtifact + Parquet
│   │   ├── database.py           # 元数据库
│   │   ├── memory.py / memory_backends.py  # 记忆管理
│   │   ├── knowledge_vector.py   # 向量知识库
│   │   └── output.py             # 输出管理
│   │
│   ├── observability/            # 终端实时显示
│   │   ├── event_bus.py, events.py, display.py
│   │
│   ├── api/                      # FastAPI + WebSocket 后端
│   │   ├── server.py             # FastAPI app + 静态文件挂载
│   │   ├── ws_handler.py         # WebSocket 事件广播 + 心跳
│   │   └── __init__.py
│   │
│   └── ui/                       # (已废弃，替换为 hagoku_web/)
│
├── docs/
│   ├── DEVELOPMENT.md
│   └── TROUBLESHOOTING.md
│
├── tests/                        # test_guardrails, test_tools, test_agents, test_storage, test_pipeline, test_llm
│
└── examples/                     # 示例数据集 + 分析脚本
```

---

## 技术选型总览

HaGoKu 自己只写 Agent 逻辑 + 统计护栏 + 编排策略 + 报告模板，其余借力现成最强组件。

| 部位 | 选型 | 核心价值 | 对应 Agent |
|------|------|----------|-----------|
| 🧠 大脑 | **Pingouin** + **Statsmodels** | 自动效应量 + 深度模型诊断 | Analyst |
| 🦴 骨骼 | **DoWhy**（V3 计划） | 因果推断四步框架 | Analyst |
| 👁 眼睛 | **ydata-profiling** + **missingno** | 数据画像 + 缺失可视化 | Scout, Cleaner |
| 🧹 手 | **sklearn** + **PyOD** + **Cleanlab** | MICE 填补 + 异常区分 + 质量评分 | Cleaner |
| 🦾 臂 | **FLAML** (Microsoft) | 轻量 AutoML | Analyst |
| 📝 嘴 | **Jinja2** + **Quarto**（V2 计划） | 模板填充 + 学术级报告 | Reporter |
| 🦿 腿 | **CrewAI** + **langchain-openai** | Agent 角色分配式编排 + LLM 后端适配 | 全体 |
| 🫀 心脏 | **Instructor** + **Pydantic** | LLM 结构化输出保证 | 全体 |
| 🛡 免疫 | **Great Expectations** | 数据验证 | Cleaner |
| 🏃 脚 | **subprocess + 白名单** | 安全代码执行 | Analyst |
| 📊 数据 | **Pandas** + **DuckDB** + **PyArrow** | 数据处理 + SQL 查询 + Parquet | 全体 |
| 🖥 界面 | **Click** + **FastAPI** + **React** | CLI + Web UI（Vite SPA：固定导航 + 多视图面板） | 用户交互 |

**12 组选型，HaGoKu 自己只写编排逻辑。**

---

## 交付物规划

> **Checklist 审计（2026-05-12）**：勾选以当前仓库**可运行能力**为准。备注中的「增强」表示主干已有、体验或覆盖仍可持续迭代，不等同于未动工。

### MVP — 让灵魂先跑起来

- [x] 项目立项
- [x] 统计护栏框架（强制级 + 警告级 + 提示级；`hagoku/guardrails/statistical.py`）
- [x] Analyst：回归 + 假设检验 + 效应量 + 模型诊断（`hagoku/tools/analysis.py`、`hagoku/agents/analyst/`；方法覆盖随场景扩展）
- [x] Cleaner：缺失机制检验 + 清洗影响评估（含 Little's MCAR 等；`hagoku/agents/cleaner/`）
- [x] Scout：语义推断 + 用户确认交互（推断在 Scout Agent；**Web** 为流程内暂停与自然语言回复；CLI 支持分阶段调试）
- [x] Reporter：双轨输出（默认 HTML：`default` 模板，要点速览 + 完整证据）
- [x] 仲裁器：规则引擎 + 基础调度（`KEYWORD_MAP` / `PLAN_TEMPLATES` + LLM 计划，`hagoku/manager/orchestrator.py`）
- [x] 项目管理 + SQLite 元数据库 + 输出管理（`hagoku/storage/database.py`、`OutputManager`、`hagoku project` / `history` 等）
- [x] CLI + 终端实时输出（`hagoku/cli.py`、`TerminalDisplay`）
- [x] 本地 LLM 适配（OpenAI-compatible；配置见 `~/.hagoku/.env` 与 `hagoku/config.py`）
- [x] 端到端示例（`examples/` 脚本与数据；`hagoku demo` / `hagoku run --demo`）

### V2 — 洞察可见，分析可持续

- [x] FastAPI + WebSocket API（`hagoku/api/`）
- [x] React Web UI（`hagoku_web/`，Vite + Zustand + 固定视图导航，非 dockview）
- [ ] 每个检验配诊断图（报告与 Analyst 已产出部分图表；**尚未**做到「每一检验一键固定诊断图」全覆盖）
- [x] 执行回放（**CLI**：`hagoku replay`；**Web**：无独立回放页，**事件**视图可辅助复盘）
- [x] 报告导出 HTML（主路径）
- [ ] 报告导出 PDF（CLI 当前 `html` / `md` / `json`；印刷级 PDF 未接主路径）
- [x] 人工介入决策点（Web：流水线暂停点 + WebSocket `respond` / `unblock`；CLI：`--interactive` 等）
- [x] 更多报告模板（内置如 `business_analysis`、`academic`、`ab_test` 等 **7** 种 + `default` 双轨）
- [ ] 外部数据库直连（**产品级**：连接管理、向导、与项目绑定；代码层有 `load_sql(..., engine=postgres|mysql)` 工具能力）
- [x] 持续性分析：resume、`diff_runs`、历史查询（`Orchestrator` + `HaGoKuDB` + `hagoku history`；**Web 展示可增强**）
- [x] 数据源管理 — 项目级多文件（`hagoku project add` 等）
- [ ] 多源注册 + 跨源统一画像（企业式数据目录）
- [ ] Scribe 知识自动提炼（LLM 辅助语义匹配）（`knowledge.yaml` 仍以规则与人工维护为主）

### V3 — 分析可扩展

- [ ] 因果推断：工具变量、DID、断点回归
- [ ] 时间序列深度分析
- [ ] 自定义 Agent 扩展接口
- [x] REST API（FastAPI，已完成）
- [ ] 多用户支持
- [ ] Analyst 辩论模式：同问题 2 方法并行分析 → Scribe 仲裁
- [ ] 辩论式协作（从 TradingAgents 借鉴）—— 多方视角降低偏差

### 迭代执行顺序（产品决策，2026-05）

> 排期默认遵循以下顺序；除非出现明确 **P0 线上/数据事故**，否则不擅自跳步扩大 scope。

| 顺序 | 阶段 | 说明 |
|------|------|------|
| **1** | 功能代码闭环 | **后端** / 编排 / 存储 / CLI：同一能力从入口到落盘、可测、可复现；API 与 `Orchestrator` 行为一致；失败与 resume 边界清晰。优先于把半成品铺到全端。 |
| **2** | Web UI 功能适配 | 在（1）稳定前提下，将已有能力**对齐暴露**到 `hagoku_web`（回放、跑次 / history / diff、导出、项目与数据操作等，按 V2 缺口逐项收口）。优先偿还「CLI 有、Web 无」。 |
| **3** | 强化分析能力 | 方法覆盖、护栏与诊断深度、Scout / Cleaner / Analyst 质量；因果 / 时序等 **V3** 能力在交互与闭环可靠后再加厚。 |
| **4** | 强化报表功能 | 模板体系、`default` 双轨与其余模板体验、PDF / 多格式导出、图表与叙事一致性；让结果「写得出去、读得懂」。 |

---

## 业界参考与架构演进

> 2026-05 对 [TradingAgents](https://github.com/TauricResearch/TradingAgents)（v0.2.4）进行了架构审计，提取了可借鉴的设计模式。以下为对比分析和优化路线图。

### 与 TradingAgents 架构对比

| 维度 | TradingAgents | HaGoKu |
|------|-------------|--------|
| 领域 | 金融交易决策 | 商业数据分析 |
| Agent 模式 | 7 类角色 × 多实例（4 分析师 + 2 研究员 + 1 交易员 + 3 风控 + 2 管理器） | 4 Agent + 1 确定性引擎（Scribe） |
| 编排引擎 | LangGraph StateGraph（有状态图 + 条件路由） | 手写 Orchestrator（顺序调用 + 规则引擎） |
| LLM 策略 | 双层（deep_think + quick_think） | 双层（deep + quick）✅ P0.3 已实施 |
| Agent 间通信 | AgentState TypedDict（22+ 类型化字段） | Parquet + context.md + progress.yaml |
| 协作机制 | 辩论式（Bulls vs Bears + 三方风控辩论） | 线性传递（Scout → Cleaner → Analyst → Reporter） |
| 事后反思 | Reflector 反思循环 + 经验注入 | Scribe knowledge.yaml 手动更新 |
| 输出解析 | 确定性解析器（parse_rating 等） | LLM 自由输出 + Guardrails 校验 |

### HaGoKu 的独特优势

以下设计是 HaGoKu 的**不可放弃资产**，TradingAgents 不具备：

- **三级统计护栏**（强制/警告/提示）—— TA 无统计分析需求
- **知识系统三层架构**（kb/ → knowledge.yaml → LLM 兜底）—— TA 无领域知识注入
- **双轨报告输出**（吸引力层 + 核心价值层 HTML）—— TA 输出文本决策
- **流程内人机暂停 + 动态话术**（非三档位用户模式）—— TA 全自动批量跑、无同类「可解释暂停」产品化体验
- **规则引擎 80% 覆盖**（KEYWORD_MAP + PLAN_TEMPLATES）—— TA 无规则引擎
- **数据血缘追踪**（Parquet → Artifact → lineage）—— TA 无数据链路

### 借鉴清单（按优先级）

#### P0：立即实施（低风险高回报）

1. **双层 LLM**（从备选路线 2）— **✅ 已实施**：
   - 增加 `HAGOKYU_LLM_MODEL_DEEP` / `HAGOKYU_LLM_MODEL_QUICK` 环境变量
   - Scout（类型推断/语义分析）→ 快速模型；Analyst（假设检验/回归推理）→ 深度模型
   - Reporter（格式化渲染）→ 快速模型；仲裁器（计划决策）→ 深度模型
   - 预期收益：降低 ~40% token 消耗 + 响应延迟

2. **结构化输出解析器**（从备选路线 3）— **✅ 已实施**：
   - 新增 `hagoku/guardrails/parsers.py`：`parse_pvalue()`、`parse_effect_size()`、`parse_conclusion_count()`
   - 护栏从"检查 LLM 是否输出"升级为"解析 + 校验"
   - Reporter 用解析器验证 Analyst 输出的结构完整性

#### P1：下个迭代

3. **LangGraph 工作流**（从备选路线 1）：
   - 引入 `langgraph` 依赖，用 `StateGraph` 替代手写 Agent 循环
   - 条件边实现：降级路由（Analyst 失败 → 简化分析）
   - 获得 LangGraph 内置 checkpoint/resume 能力

4. **AgentState TypedDict**（从备选路线 5）：
   - 创建 `AnalysisPipelineState(TypedDict)`，定义所有 Agent 的输出槽位
   - 每个 Agent 输出写入指定字段，获得类型安全 + 可维护性

#### P2：V2 配套升级

5. **Scribe 反思循环升级**（从备选路线 6）：
   - 每次分析后，Scribe 用快速 LLM 回顾结果 → 自动写入 memory.md 的"失败教训"区域
   - 使 knowledge.yaml 自动积累从"人工格式"升级为"LLM 驱动"

| 优先级 | 演进项 | 实施成本 | 收益 | 风险 |
|--------|---------|---------|------|------|
| 🔴 P0 | 双层 LLM（✅） | 🟢 低 | 🟢 高（降本 40%） | 无 |
| 🔴 P0 | 结构化解析器（✅） | 🟢 低 | 🟢 高（护栏更可靠） | 无 |
| 🟡 P1 | LangGraph 工作流 | 🟡 中 | 🟢 高（可视化+条件路由） | 🟡 中（迁移风险） |
| 🟡 P1 | AgentState TypedDict | 🟡 中 | 🟡 中（类型安全） | 低 |
| 🟢 P2 | 反思循环升级 | 🟢 低 | 🟡 中（经验自动化） | 低 |
| ⚪ V3 | 辩论式协作 | 🔴 高 | 🔴 高（分析质量飞跃） | 🔴 高（复杂度 + token 消耗） |

---

## 环境变量配置

### 硬性约定（重新规定）

1. **唯一读取的 dotenv 文件**：`~/.hagoku/.env`（由 `hagoku/config.py` 在导入时加载；文件不存在则跳过）。
2. **仓库内**：只维护 **`.env.example`** 作模板；**不在仓库根目录**放置或依赖 `.env`（且 `.gitignore` 已忽略根目录 `.env`，避免误提交）。
3. **首次配置**：`mkdir -p ~/.hagoku && cp .env.example ~/.hagoku/.env`，再编辑 `~/.hagoku/.env`。环境变量覆盖 `~/.hagoku/config.yaml` 中的同名逻辑（以 `config.py` 的 `_merge_env` 为准）。

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `HAGOKYU_LLM_BASE_URL` | LLM（OpenAI 兼容）服务地址；**勿与** `hagoku-api` 的 HTTP 端口混淆 | `http://localhost:8080/v1` |
| `HAGOKYU_LLM_API_KEY` | LLM API 密钥 | `none` |
| `HAGOKYU_LLM_MODEL` | LLM 模型名（默认，所有 Agent 共用） | `Qwen3.6-35B-A3B` |
| `HAGOKYU_LLM_MODEL_DEEP` | 深度推理模型（Analyst、仲裁器） | 同 `HAGOKYU_LLM_MODEL` |
| `HAGOKYU_LLM_MODEL_QUICK` | 快速模型（Scout、Reporter、反思） | 同 `HAGOKYU_LLM_MODEL` |
| `HAGOKYU_EMBEDDING_BASE_URL` | Embedding 服务地址 | 同 `HAGOKYU_LLM_BASE_URL` |
| `HAGOKYU_EMBEDDING_API_KEY` | Embedding API 密钥 | 同 `HAGOKYU_LLM_API_KEY` |
| `HAGOKYU_EMBEDDING_MODEL` | Embedding 模型名 | `text-embedding-3-small` |
| `HAGOKYU_WORK_DIR` | 工作目录 | `~/.hagoku` |

---

## 项目文档索引

| 文档 | 用途 | 受众 |
|------|------|------|
| **PROJECT.md**（本文件） | 项目灵魂、架构原则、唯一真相源 | 所有人 |
| [README.md](README.md) | 用户手册（安装、命令、快速开始） | 用户 |
| [DEV.md](DEV.md) | 开发快速上手 | 新贡献者 |
| [CLAUDE.md](CLAUDE.md) | AI 编码助手上下文 | Claude Code |
| [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) | 详细设计手册（架构/看板/向量/审查） | 开发者 |
| [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) | 常见问题排查 | 开发者 |
| [DEVELOPMENT_PROMPT.md](DEVELOPMENT_PROMPT.md) | 单轮开发任务传递模板（填写后转发给 AI/协作者；真相同步以本表为准） | 派活人、协作者 |

---

## CLI 命令快速参考

### 核心分析

| 命令 | 用途 |
|------|------|
| `hagoku run <file> -q "问题"` | 端到端分析流程（无 `--mode` / 无用户模式档位） |
| `hagoku demo` | 列出内置演示数据集 |
| `hagoku profile <file>` | 数据画像 |

### 项目管理

| 命令 | 用途 |
|------|------|
| `hagoku project create <名> -d "描述"` | 创建项目 |
| `hagoku project add <项目> <文件>` | 添加数据 |
| `hagoku project run <项目> -q "问题"` | 项目分析 |
| `hagoku project list` | 列出项目 |
| `hagoku project info <项目>` | 项目详情 |
| `hagoku project delete <项目>` | 删除项目 |

### 诊断 & 工具

| 命令 | 用途 |
|------|------|
| `hagoku doctor` | 系统健康检查 |
| `hagoku methods` | 可用分析方法 |
| `hagoku guardrails` | 护栏规则 |
| `hagoku config` | 查看/重置配置 |

### 记忆 & 历史

| 命令 | 用途 |
|------|------|
| `hagoku memory <项目>` | 查看项目记忆 |
| `hagoku history <项目>` | 运行历史 |
| `hagoku replay <run_id>` | 回放分析 |

---

## 项目信息

- **名称**: HaGoKu
- **灵魂**: 让每个小模型都能做专业级商业分析
- **原则**: 精、准、狠
- **价值**: 门面吸引用户走进来，地基让用户留下来
- **许可**: MIT
- **状态**: 立项阶段，MVP 开发中
