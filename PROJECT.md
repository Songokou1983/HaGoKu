# HaGoKu Studio — 项目规范（The Single Source of Truth）

## 灵魂

> **让每个小模型，都能做专业级商业分析。**

HaGoKu Studio 追求统计分析深度：自动检验假设、报告效应量、做模型诊断，区分因果和相关。同时不牺牲信息设计的吸引力——门面吸引用户走进来，地基让用户留下来。

---

## 设计哲学

| 维度 | 含义 |
|------|------|
| **精** | 报告结论精炼：不超过 5 条核心发现 |
| **准** | 每条结论有统计检验支撑（p值 + 效应量 + 置信区间） |
| **狠** | 直接回答用户问题，不回避不确定性 |
| **轻量** | 本地 LLM 优先，最小依赖，数据不出本机 |
| **专业** | 严肃对待不确定性，不假装 100% 确定 |

---

## 壳子、架构、通道

HaGoKu Studio 由三个要素构成。代码只负责壳子（运行环境）、架构（编排规则）、通道（信息路由）。所有语义理解由 LLM 完成。

| 要素 | 含义 | 代码做什么 |
|------|------|-----------|
| **壳子** | Web UI + CLI + 事件系统 + 存储 | 给用户操作界面，给 Agent 运行环境 |
| **架构** | Agent 分工 + 协作顺序 + 护栏 + 看板 | 谁在什么时候做什么，产出如何传递 |
| **通道** | 上下文整理 + 信息路由 + LLM 调用 | 完整信息到达 LLM，LLM 返回机械应用 |

**通道的检验标准**：当 LLM 看到上下文后，能否仅凭上下文做出正确决定？如果不能，说明信息有遗漏——需要补的是通道（多传信息），不是补代码规则。

**通道的首选机制**：function calling（tools）。代码定义工具签名（`update_field_understanding`），LLM 主动调用工具来理解、更新字段。代码仅机械执行 `msg.tool_calls` 的结果。function calling 是代码只管"怎么做"的最高级形态——LLM 在丰富的上下文里自主决定调用哪个工具、传什么参数。

任何需要"判断"的环节——用户想干什么、字段是什么意思、失败后该换什么策略——信息必须完整到达 LLM。

---

## 代码边界

### LLM 负责（语义决策）

- 理解用户自然语言输入
- 推断字段含义和角色
- 选择分析方法
- 生成报告叙述
- 决定降级策略

### 代码负责（机械执行）

- LLM 健康检查、事件路由、状态写入、格式校验
- 统计计算（Pingouin/Statsmodels）
- 可视化渲染（Plotly）
- 数据 I/O（Pandas/DuckDB）
- 护栏校验（p 值/效应量/置信区间存在性检查）
- 看板状态机（确定性状态转换）

**区分线**：LLM 管"做什么"，代码管"怎么做"。

### 工具与流程：给 Agent 用，不给代码用

代码提供工具和流程，**Agent 决定用不用、怎么用**。

HaGoKu Studio 的核心隐喻：**每个 Agent 是工作室的资深合伙人，代码提供的是工位、工具、电话线。用户走进工作室，跟合伙人们直接沟通需求。没有人在用户和合伙人之间自作主张。**

**示例对比**：

| 场景 | ✅ 工具与流程（代码该做） | ❌ 硬写（代码不该做） |
|------|--------------------------|---------------------|
| 字段理解 | 代码提供 3 列表格模板（display_name/description/状态），LLM 填写内容 | 代码用正则解析用户输入，自己判断哪个列该更新什么 |
| 分析方法 | 代码注册 50+ 分析方法（工具库），LLM 选择调用哪个 | 代码用 if-else 根据关键词选择分析方法 |
| 用户反馈处理 | 代码提供 `update_field_understanding` function calling 工具，LLM 通过 tool_calls 主动选择更新哪些字段，代码机械写入 context | 代码用正则 `col=desc` 格式解析用户输入并自行更新字段 |
| 保底/降级 | LLM 失败时保留原 context 不变，通知用户"AI 暂时无法处理" | LLM 失败时代码用正则/默认值自己填表 |

**检验标准**：如果一段代码的语义产出（字段含义、方法选择、报告叙述）可以被删除且不影响最终结果（因为 LLM 会产生同样的产出），那这段代码就是硬写——应删除。

**保底的正确姿势**：保底不是"代码替 LLM 完成任务"，而是"代码提供备选通道让 LLM 重试"。例如：快速 LLM 失败 → 切换深度 LLM 重试 → 仍失败 → 保留原样，通知用户。

**关于模板**：表格列结构、报告章节、分析方法签名——这些都是"办公用品"，由代码定义供 Agent 使用。代码定义**形状**，Agent 填写**内容**。

---

## 防退化机制

代码接管语义理解往往不是初始设计，而是在测试/迭代中为快速解决问题逐步渗入的。以下三重刹车防止这一退化：

### 刹车 1：禁止正则覆盖区（代码级）

涉及用户输入处理、字段语义更新的代码区域顶部，有明确的分隔注释标记 `# ==== CHANNEL ZONE: 禁止正则/if-else 语义分支 ====`。该区域内禁止出现：
- 中文字符串匹配（`"是"` `"代表"` `"表示"` `"意为"` 等自然语言动词）
- `if/elif` 链枚举语义模式

出现即违规。

> **当前通道区域**：
> - **意图解析**（`query_parser.py`）：已彻底 LLM 化。`QueryParser.parse()` 通过 LLM structured output（`PlanRequestFields` schema）输出 `{intent, analysis_type, research_question}`，代码仅做 schema 校验和传输。无正则、无关键词枚举。
> - **字段理解**（`orchestrator.py`）：`_apply_scout_reply_with_llm`（function calling 模式，LLM 通过 `update_field_understanding` 工具自主决定更新内容）与 `apply_scout_user_field_reply_to_context`（机械执行层，将 tool_calls 结果写入 context）。
> - **分布判断**（Scout Agent）：Shape analysis 已由 LLM 完成，不再有硬编码的倍数阈值（`maxv > q75v * 10` 等）。
> - **工具 description**：`_SCOUT_FIELD_UPDATE_TOOLS` 内的中文字符串是 function calling 工具的 `description`（供 LLM 理解工具用途），不属于代码硬匹配。

### 刹车 2：回归契约（测试级）

测试验证 LLM 确实收到了包含用户原话的请求。若代码绕过 LLM 调用，mock 收不到请求，测试失败。不关心代码怎么实现，只验证通道是否完整。

```bash
# 核心契约：用户输入 → LLM 收到完整上下文 → 返回更新 JSON → 代码机械应用
pytest tests/test_product/test_agent_interaction_contract.py -q
```

### 刹车 3：审查清单（流程级）

审查时扫中文字面量：涉及用户输入解析/字段语义更新的代码区域若新增中文字符串匹配或 if-else 语义分支 → 拒绝合并，改为补通道。

```bash
# 审查命令：在通道区域内检查中文硬匹配
grep -nE '(代表|表示|意为|是|当成|看作)' hagoku/agents/scout/agent.py
grep -nE '(代表|表示|意为|是|当成|看作)' hagoku/manager/orchestrator.py
```

---

## Agent 角色设计

| Agent | 职责 | LLM 参与 |
|-------|------|---------|
| 🔍 **Scout** | 数据画像 + 字段语义推断 | LLM 做语义分析 |
| 🧹 **Cleaner** | 数据清洗 + 缺失机制检验 | LLM 决策清洗策略 |
| 📊 **Analyst** | 假设检验 + 回归分析 + 模型诊断 | LLM 选方法，代码做计算 |
| 📝 **Reporter** | 双轨 HTML 报告渲染 | LLM 生成叙述 |
| 📋 **Scribe** | 记录 + 知识调度 + 看板维护 | 确定性引擎；仅字段描述不完整时用 LLM 补全遗漏列 |

---

## 人机互动

- **流程内暂停**：流水线在关键阶段结束后暂停（`USER_INPUT_REQUESTED`），Agent 主动引导
- **结构化卡片优先**：暂停时先交付结构化数据（字段表/清洗表/护栏摘要），若附带短消息由 LLM 依结果生成
- **自然语言回复**：用户用自然语言回复（`respond`），后端 `unblock` 继续
- **多轮对齐**：阶段内可多轮对话直到对齐（`interaction_revision` 递增）

> 可执行契约：`docs/AGENT_INTERACTION_CONTRACT.md`  
> 多轮分期方案：`docs/INTERACTION_MULTITURN_PLAN.md`

---

## 报告设计 — 双轨输出

| 层 | 面向 | 内容 |
|----|------|------|
| **吸引力层** | 所有人 | 核心结论（≤5条）、关键图表、通俗解读 |
| **核心价值层** | 专业人士 | 完整统计结果、检验假设、方法细节、诊断数据 |

---

## 知识系统

```
Layer 1: kb/  领域知识（手写，低频更新）
Layer 2: agent/knowledge.yaml  方法经验（手动维护，V2 计划自动积累）
Layer 3: LLM 自由发挥（前两层无匹配时兜底）
```

Scribe 在 Agent 启动前检索知识库并注入 prompt。Agent 不主动查知识库。

---

## 看板协作

Agent 间不直接对话，通过看板交换信息：

```
~/.hagoku/projects/{project}/
├── kanban.db       ← SQLite 看板
├── context.md      ← 项目上下文（所有 Agent 共享读取）
├── data/           ← 数据制品 (Parquet)
├── runs/           ← 分析运行记录
└── progress.yaml   ← 项目记忆
```

---

## 统计护栏 — 三级安全网

### 强制级（Violation = 阻止正式报告输出）

| 规则 | 说明 |
|------|------|
| `no_conclusion_without_test` | 无统计检验不下结论 |
| `must_report_effect_size` | 显著必须配效应量 |
| `must_report_ci` | 点估计必须配置信区间 |
| `no_causal_claim_without_method` | 声称因果须有因果推断方法 |
| `must_diagnose_model` | 建模后须做残差诊断 |

### 警告级（Violation = 标注但允许输出）

| 规则 | 说明 |
|------|------|
| `assumptions_violated` | 假设不满足，建议替代方法 |
| `small_sample_size` | 样本量不足警告 |
| `high_vif` | 多重共线性超标警告 |

### 提示级（Violation = 建议不阻断）

| 规则 | 说明 |
|------|------|
| `suggest_nonlinear` | 残差暗示非线性，建议检查 |
| `missing_not_random` | 缺失非随机，建议谨慎 |

---

## 降级策略

| Agent | 失败场景 | 方案 |
|-------|---------|------|
| Scout | 语义推断失败 | 标记 UNKNOWN，等待用户确认 |
| Analyst | 回归失败 | LLM 依据失败上下文决定替代方法；代码执行计算 |
| Cleaner | 填补失败 | 保留缺失值，标注未处理 |
| Reporter | 模板渲染失败 | 降级到 Markdown 纯文本 |

> **LLM 不可用前置拦截**：pipeline 启动前 `health.check_llm_health()` 验证 LLM 可达性；失败则返回错误，不进 pipeline。

---

## 数据流

```
原始数据
  ▼ Scout → DataContext + raw.parquet
  ▼ Cleaner → CleaningReport + cleaned.parquet
  ▼ Analyst → list[AnalysisResult] + diagnostics/
  ▼ Reporter → 双轨 HTML
  ▼ 用户
```

数据传递格式：Parquet + 元数据 JSON。

---

## 存储架构

```
~/.hagoku/
├── config.yaml
├── hagoku.db                     # SQLite 元数据库
└── projects/{name}/
    ├── progress.yaml / context.md / kanban.db
    ├── data/                     # raw/cleaned .parquet
    ├── runs/{run_id}/
    │   ├── run_meta.json / plan.json / events.jsonl
    │   ├── results/ / diagnostics/ / output/
    └── reports/                  # latest.html → runs 的符号链接
```

---

## 可观测性

HaGoKu Studio 全程透明，用户坐副驾驶位：

```
🔍 Scout ──── ✅ 完成 (12s)
🧹 Cleaner ── ✅ 完成 (8s)
📊 Analyst ── 🔄 执行中...
📝 Reporter ── ⏳ 等待中
> Scribe（📋 看板仲裁）在后台运行，不显示终端进度。
```

---

## 项目结构

```
hagoku/
├── llm/              # LLM 客户端 (OpenAI-compatible)
├── manager/          # 编排器（计划生成 + 调度 + 降级）
├── agents/           # 5 个 Agent（scout/cleaner/analyst/reporter/_scribe）
├── kb/               # 领域知识库（Layer 1）
├── tools/            # 分析工具集（插件架构）
├── guardrails/       # 统计护栏 + 输出解析
├── storage/          # 持久化（kanban/project/artifact/database/memory）
├── observability/    # 事件总线 + 终端显示
├── api/              # FastAPI + WebSocket
└── devtools/         # 交互场景模拟
```

> 前端：`hagoku_web/`（Vite + React + Zustand，固定侧栏/顶栏视图切换）

---

## 技术选型

| 部位 | 选型 | 核心价值 |
|------|------|---------|
| 🧠 大脑 | **Pingouin** + **Statsmodels** | 自动效应量 + 深度诊断 |
| 🧹 手 | **sklearn** + **PyOD** | MICE 填补 + 异常检测（IsolationForest） |
| 📝 嘴 | **Jinja2** + Plotly | 模板渲染 + 交互式图表 |
| 🦿 腿 | **Orchestrator（手动编排）** + **langchain-openai** | Agent 调度 + LLM 适配；CrewAI 为可选适配器（按需创建，非管道路径） |
| 🫀 心脏 | **Instructor** + **Pydantic** | 结构化输出保证 |
| 📊 数据 | **Pandas** + **DuckDB** + **PyArrow** | 数据处理 + SQL + Parquet |
| 🖥 界面 | **Click** + **FastAPI** + **React** | CLI + Web UI |

---

## 版本愿景

- **MVP**：统计分析闭环 — Scout → Cleaner → Analyst → Reporter 全流程可跑
- **V2**：Web UI + 持续性分析 + 人工介入决策点 + 更多报告模板
- **V3**：因果推断 + 时间序列深度分析 + Agent 扩展接口 + 辩论协作

> 交付物详细勾选见 `DEVELOPMENT_PROMPT.md`

---

## 环境变量

唯一读取 `~/.hagoku/.env`（由 `config.py` 加载）。仓库内只维护 `.env.example` 作模板。

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `HAGOKYU_LLM_BASE_URL` | LLM 服务地址 | `http://localhost:8080/v1` |
| `HAGOKYU_LLM_API_KEY` | API 密钥 | `none` |
| `HAGOKYU_LLM_MODEL` | 默认模型名 | `Qwen3.6-35B-A3B` |
| `HAGOKYU_LLM_MODEL_DEEP` | 深度推理（Analyst/仲裁器） | 同 `MODEL` |
| `HAGOKYU_LLM_MODEL_QUICK` | 快速模型（Scout/Reporter/Scribe） | 同 `MODEL` |
| `HAGOKYU_EMBEDDING_BASE_URL` | Embedding 服务地址 | 空（须自行填写） |
| `HAGOKYU_EMBEDDING_API_KEY` | Embedding API 密钥 | `none` |
| `HAGOKYU_EMBEDDING_MODEL` | Embedding 模型名 | `text-embedding-3-small` |
| `HAGOKYU_WORK_DIR` | 工作目录 | `~/.hagoku` |
| `HAGOKYU_PROJECT_DIR` | 项目根目录覆盖 | 同 `WORK_DIR/projects` |

---

## 文档索引

| 文档 | 用途 | 受众 |
|------|------|------|
| **PROJECT.md**（本文件） | 项目灵魂、架构原则、唯一真相源 | 所有人 |
| `README.md` | 用户手册（安装、命令、快速开始） | 用户 |
| `DEV.md` | 开发快速上手 | 新贡献者 |
| `docs/DEVELOPMENT.md` | 设计手册（看板/向量/防护/审查） | 开发者 |
| `docs/EXTERNAL_REFERENCES.md` | 外部项目思想参考 | 开发者 |
| `docs/TROUBLESHOOTING.md` | 常见问题排查 | 开发者 |
| `docs/AGENT_INTERACTION_CONTRACT.md` | Agent 交互可执行契约 | 开发者 |
| `docs/INTERACTION_MULTITURN_PLAN.md` | 多轮对齐分期方案 | 开发者 |
| `DEVELOPMENT_PROMPT.md` | 路线图跟踪 + 任务传递 + 审查约定 | 协作者 |
| `CLAUDE.md` | AI 编码助手上下文 | AI 助手 |

---

## 项目信息

- **名称**: HaGoKu Studio
- **灵魂**: 让每个小模型都能做专业级商业分析
- **原则**: 精、准、狠
- **许可**: MIT