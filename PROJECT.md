# HaGoKu Studio — 项目规范（The Single Source of Truth）

> **核心信条**：LLM 在语义判断上比代码更可靠。Code 的活是构建通道让 LLM 自由发挥，不是替 LLM 干活。

## 灵魂

> **让每个小模型，都能做专业级商业分析。**

HaGoKu Studio 追求统计分析深度：自动检验假设、报告效应量、做模型诊断，区分因果和相关。同时不牺牲信息设计的吸引力——门面吸引用户走进来，地基让用户留下来。

---

## 演进方向（2026-06-11 起）

> 📍 项目正在从「4 Agent 协作 pipeline」收缩为「**1 个数据分析师 LLM + 专业工具箱**」。
>
> **触发**：2026-06-11 用户与架构审核方讨论发现当前架构嘴上信条对（LLM 主导）、手上没完全对（重拼 prompt = 代码替 LLM 决定它看到什么）。**复杂度的根因是"每次 LLM 调用从碎片重拼 messages"这个动作存在本身**——律 / 刹车 / HaGoKu Doctor 都是为维持这套架构长出来的免疫系统。
>
> **新重心**：本地优先的严肃数据分析师，基于大模型能力，配备深度统计工具箱。**核心信条一字未动**，变的是"架构如何落实信条"。
>
> **新叙事差异**：
> - 是什么：1 个数据分析师 LLM + 专业工具箱（旧：4 Agent 协作 pipeline）
> - 稀缺点：严肃统计 + 本地优先 + 小模型也能跑（旧：多 Agent 编排）
> - 成长方式：加工具 / 加护栏维度（旧：加 Agent / 加律 / 加守门）
>
> **不变**：铁律 1 / 7 / 10 / 工作流刹车 / 统计护栏 / dump 通道 / 工具注册表 / 数据不出本机 —— 全部保留。
>
> **6 Phase 改造路径与审核标准**：详见 [`docs/plans/2026-06-11-collapse-to-single-agent-brief.md`](docs/plans/2026-06-11-collapse-to-single-agent-brief.md)。本文档以下章节描述**当前实现**，会随 Phase D 完成而重写。在此之前，"4 个 Agent"的描述仍是物理事实。

> 💡 当前通道设计在 ~30B+ 模型上验证稳定。随着技术进步，7B 级已退化为玩具级别——幻觉率高、指令遵循弱，不是 HaGoKu 的目标运行环境。如果你在用小模型遇到「字段全选」「角色乱判」等问题，换个稍大的模型通常就解决了。
>
> **Phase A-D 已完成（2026-06-11）**：4 agent 合 1，prompt 单点化，阶段切换 LLM 化，Meta v2 四组件。[详见](docs/plans/2026-06-11-collapse-to-single-agent-brief.md)

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

HaGoKu Studio 由三个要素构成。代码只负责壳子（运行环境）、架构（编排规则）、通道（信息流 + 控制权双向路由）。所有语义理解和流程决策由 LLM 完成。

| 要素 | 含义 | 代码做什么 |
|------|------|-----------|
| **壳子** | Web UI + CLI + 事件系统 + 存储 | 给用户操作界面，给 Agent 运行环境 |
| **架构** | Agent 分工 + 协作顺序 + 护栏 + 看板 | 谁在什么时候做什么，产出如何传递 |
| **通道** | 信息通道（上下文 ↔ LLM）+ 控制通道（LLM 流程决策） | 完整信息到达 LLM，LLM 的语义产出 / 流程决策机械应用 |

**通道有两类，缺一不可**：

- **信息通道**：用户输入 / 数据画像 / 上游摘要 → LLM；LLM 的结构化产出 → 状态。
- **控制通道**：LLM 主动表达"本阶段完成 / 留在本阶段 / 跳回上一阶段 / 再问用户一次"作为 tool_calls，由代码机械执行。**控制权也是信息的一种**——不通控制权的设计，LLM 永远只能在工位上发言，工厂总图归代码所有。

**通道的检验标准**：当 LLM 看到上下文后，能否仅凭上下文做出正确决定，并能把决定传递回系统？如果不能，说明通道残缺——需要补的是通道（多传信息或多开出口），不是补代码规则。

**通道的首选机制**：function calling（tools）。代码定义工具签名（语义工具 `update_field_understanding`、控制工具 `done_with_stage` / `route_to` 等），LLM 主动调用。代码仅机械执行 `msg.tool_calls` 的结果。

任何需要"判断"的环节——用户想干什么、字段是什么意思、下一步去哪、失败后该换什么策略——信息必须完整到达 LLM，LLM 的决定必须能完整回到系统。**详见下文「通道完备性十律」**。

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

### 字段理解的归属（2026-06-03 确立）

字段语义是**项目级信息**，不属于跨项目知识库。

| 存储 | 归属 | 生命周期 |
|------|------|---------|
| **项目记忆**（SQLite memory 表） | 用户确认过的字段名/描述 | clear-history 时清除 |
| **跨项目知识库**（knowledge.yaml/db） | 分析策略模式，**不存字段名** | 跨项目持久 |

**设计原则**：
- LLM 看列名 + 样本值 + 数据类型就够推断字段含义，不需要历史知识库
- 知识库存字段名会污染新项目（BU 在 A 项目=公司，B 项目=业务单元）
- 只有用户显式纠正过的字段（`confirmed_by_user=True`）才持久化到项目记忆
- `clear-history` 清除数据库和项目文件，**不清除知识库**（知识库是分析经验，不是字段名）

### Scope 引导式分析（2026-06-03 设计阶段）

字段理解阶段产出 scope（分析范围：target + features + excluded），注入下游所有 Agent 的 system prompt。Scope 是**引导性的**——全表始终对 LLM 可见，scope 告诉 LLM "优先关注这些"，用户随时可解锁新维度。

详见 `docs/superpowers/specs/2026-06-03-scope-guided-analysis-design.md`。

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

### 全局工具注册表

HaGoKu 有一个**项目级工具注册表**（`hagoku/tools/registry.py`），所有 Agent 共享。代码只做三件事：注册工具签名、执行工具调用、返回结果。LLM 决定调哪个、什么时候调。

```
hagoku/tools/
├── registry.py          # AgentTools 注册表（单例）：register / to_openai / dispatch
├── agent_tool_defs.py   # 工具定义：每个 Tool = name + description + parameters + handler + agents
└── ...
```

**新增工具只需在 `agent_tool_defs.py` 加一个 `Tool(...)` 注册**，指定 `agents=["scout","cleaner"]` 控制哪些 Agent 可用。代码不做任何 if-else 语义路由——LLM 通过 function calling 主动选择工具，代码机械执行 `dispatch()`。

**已注册工具**（7 个）：

| 工具 | 可用 Agent | 用途 |
|------|----------|------|
| `get_column_stats` | 全部 | 获取某列统计量（min/q25/median/q75/max/mean） |
| `get_sample_rows` | 全部 | 获取某列抽样值 |
| `list_columns` | 全部 | 列出所有列名和类型 |
| `group_stats` | cleaner, analyst | 按某列分组查看另一列统计 |
| `update_field_understanding` | scout | 更新字段中文名/含义 |
| `update_field_role` | scout | 设置 target/features/ignored |
| `restrict_analysis_to` | scout | 限定参与分析的字段 |

**检验标准**（律 4 延伸）：新增 Agent 能力时，若要在 prompt 里手写 JSON 格式让 LLM 输出 → 说明缺工具，应在注册表补。

---

### 全局联动原则

字段理解、角色分配、参与分析、清洗建议——这些不是孤立决策。LLM 更新任何一项后，必须同步检查其他项是否需要调整。代码通过 channel 传递完整上下文（字段表、分析目标、对话历史），LLM 基于全局做联动判断。

> 这不是规则，是能力。通道的任务是让 LLM 看到全局。LLM 看到了，自己会联动。

---

## 通道完备性十律

> **Phase D 后**：单 agent + 单 chat（ProjectContext）+ `to_messages_for_llm()` 统一入口已物理保证律 1-6/8-10 自动满足。律 11（配置中性）保留为文档规范。契约测试（`tests/test_product/test_information_arrival.py`）持续守门。

> 项目文档（`CLAUDE.md` / `PROJECT.md` / `.env.example` / commit message / memory / AI 输出）**不绑具体部署配置**——LLM 模型名、API 端点 URL、端口等都是用户运行时通过 `hagoku-ui` 设置功能选择的，不是项目真理。

**反例**：
- `PROJECT.md` 写 `HAGOKYU_LLM_MODEL=Qwen3.6-35B-A3B` 当默认值——一旦换模型就过时
- `.env.example` 写 `HAGOKYU_LLM_BASE_URL=http://localhost:8080/v1` 当模板值——云端模型不是这个地址
- AI 输出 "因为当前用 35B 模型 context 是 128K"——把 runtime config 当 design constraint
- memory 写 "项目当前用某个云端模型 1M context"——memory 跨 session 持久，runtime 变了就误导

**合法写法**：
- 文档/示例里出现模型名时 → `<用户配置>` 占位
- BASE_URL / port 等部署值 → 留空 + `# 用户配置` 注释
- 描述列加 "（用户运行时通过设置功能选择）" 说明
- 涉及 LLM 能力时 → 按"配置范围"评估（如"假设 context 在 128K-1M 之间"），不绑具体模型
- `config.py` 数据类默认值可保留（Python 类行为），但 docs 描述不许指向具体值

**检验**：
```bash
grep -rn "Qwen\|A3B\|localhost:8\|text-embedding" CLAUDE.md PROJECT.md .env.example  # 应空
grep -rn "minimax\|claude\|gpt-\|gemini" hagoku/ docs/  # AI 内部输出不留具体模型名
```

> 起源：2026-06-06 scribe redesign 讨论中，AI 反复在项目文档/AI 输出/记忆里写具体模型名（先 Qwen 后又写另一个云端模型名），被用户两次纠正。

---

## 防退化机制

> **Phase D 后**：单 agent + `to_messages_for_llm()` + pre-commit hook 已物理拦截所有 4 类退化。信息抵达契约（`tests/test_product/test_information_arrival.py`）持续守门。

---

## Agent

**Phase D 后：唯一 DataAnalystAgent**（`hagoku/agents/agent.py`）。按 4 关注点工作（理解字段/评估清洗/跑统计/写报告），通过 `route_to` 自主切换。统一 prompt（`hagoku/agents/prompt.md`，256 行）。27 工具全集可见。

ProjectContext 持有唯一 chat；`to_messages_for_llm()` 统一 LLM 调用入口。

### 分析计划生成

用户查询到达后，系统通过 LLM 两阶段生成分析计划（pipeline 编排的决策依据）：

| 阶段 | 组件 | 作用 |
|------|------|------|
| **意图解析** | `QueryParser.parse()` → LLM Structured Output | 从自然语言提取意图、目标变量、分组维度、过滤条件等 |
| **计划生成** | `plan_schema.LLMPlanResponse` + `llm/prompts.py` | LLM 依据意图和上下文，决定 Agent 编队、分析焦点（regression/causal/hypothesis_test 等 7 种）、计划名、目标变量 |

**Schema 定义**（`llm/plan_schema.py`）：
- `LLMPlanResponse`（Pydantic）：`plan_name`、`agents`、`analyst_focus`（7 种可选）、`target`、`query`、`reasoning`
- 默认探索焦点：`["regression", "hypothesis_test", "correlation"]`
- LLM 失败兜底：`QueryIntent(intent_type="exploration")`  
  ⚠️ **已知违规**：此 fallback 违反铁律 2（LLM 失败不准默认值兜底），见 `docs/plans/doctrine-violations-cleanup.md`。当前实现在 `query_parser.py:61-63`，待修复后移除此文档描述。

**Prompt 模板**（`llm/prompts.py`）：
- 系统 prompt：定义分析规划师角色、决策依据、6 种分析类型描述、决策规则
- 调整模式：在规则计划基础上由 LLM 判断是否需调整

**代码职责**：仅定义 schema 形状和 prompt 模板，不参与决策。LLM 选方法、定焦点；代码机械校验 schema 并调度 Agent。

> 实现：`hagoku/llm/plan_schema.py`、`hagoku/llm/prompts.py`、`hagoku/manager/query_parser.py`

---

## 人机互动

- **流程内暂停**：流水线在关键阶段结束后暂停（`USER_INPUT_REQUESTED`），Agent 主动引导
- **结构化卡片优先**：暂停时先交付结构化数据（字段表/清洗表/护栏摘要），若附带短消息由 LLM 依结果生成
- **自然语言回复**：用户用自然语言回复（`respond`），后端 `unblock` 继续
- **多轮对齐**：阶段内可多轮对话直到对齐（`interaction_revision` 递增）。Scout（C4）含字段纠错→再展示→闸门确认；Cleaner/Analyst（C5）含多轮暂停+显式放行短语
- **字段理解持久化**：Scout 对齐后，用户确认的字段描述（`column_descriptions` / `column_display_names`）通过 `MemoryManager.persist_field_descriptions()` 写入 SQLite + YAML。下次同一项目分析时自动复用，避免重复询问

> 可执行契约：`docs/AGENT_INTERACTION_CONTRACT.md`  
> 多轮分期方案：`docs/INTERACTION_MULTITURN_PLAN.md`

---

## 命令系统

命令是用户对 **LLM 的定向沟通通道**。用户输入 `/` 开头的命令，系统剥离前缀后原样转发给当前阶段 LLM，绕过流程控制拦截。

### 设计原则

- 流程控制（确认/跳过/取消）→ **UI 按钮**，不占用命令
- 命令 = `/<命令> <固定结构参数>`，结构由代码定义，内容由 LLM 理解
- 阶段命令自动路由到当前停留阶段 LLM（Scout / Cleaner / Analyst / Reporter）
- 全局命令（`/goal`）补充分析目标，所有阶段通用
- 后续阶段按需扩充，全部命令遵循统一格式规范

### Scout 阶段 · 字段理解

Scout 向用户展示字段核对表（三列：`field_name` | `chinese_name` | `meaning`）。

| 命令 | 格式 | 作用 |
|------|------|------|
| `/goal` | `/goal <分析目的>` | 补充/修正分析目标 |
| `/rename` | `/rename <原始列名>=<中文名称> [, ...]` | 纠正 LLM 猜错的中文显示名（第二列），更新 `column_display_names` |
| `/use` | `/use <列名1>, <列名2>, ...` | 指定本次分析参与字段，超出范围的标记 `used_in_analysis=False` |

### 实现

- **命令解析器**：`hagoku/manager/command_parser.py`，将 `/command args` 解析为 `{command, args}`
- **路由**：`orchestrator.py` 在暂停点入口判定：命令 → 转发 LLM；自然语言 → 现有流程
- **前端指引**：`CommandsPanel.tsx` 按阶段展示命令速查表

> 完整设计：`docs/COMMAND_SYSTEM.md`

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

### 知识向量存储

每个 Agent 配备双层知识系统，实现语义检索和人工维护的有机结合：

| 层 | 文件 | 内容 | 操作方式 |
|---|------|------|---------|
| **YAML** | `{agent}/knowledge.yaml` | 人可读的知识条目（字段经验 / 清洗策略 / 分析经验 / 报告模板） | 人工编辑、代码同步 |
| **向量 DB** | `{agent}/knowledge.db` | sqlite_vec 向量索引，语义检索 | 自动同步、余弦相似度排序 |

**核心能力**（`storage/knowledge_vector.py`）：
- **入库**：`add_entry(content, metadata)` → 调用 embedding API 生成向量 → 写入 YAML + 向量 DB
- **检索**：`recall(query, top_k)` → embedding query → 余弦相似度 → 返回 top-k 条目
- **同步**：`sync_missing_vectors()` → YAML 有条目但 DB 无向量时自动补全
- **语义退化**：embedding API 不可达时返回空列表，不影响主流程（Agent 仍可用 fallback 知识）

**各 Agent 的 knowledge.py 包装**：
- **Scout**：字段理解经验（`recall_field_experience()`、`add_field_experience()`）
- **Cleaner**：清洗策略经验（`recall_cleaning_experience()`、`add_cleaning_experience()`）
- **Analyst**：分析方法选择经验（`recall_analysis_experience()`、`add_analysis_experience()`）
- **Reporter**：报表模板经验（`recall_report_experience()`、`add_report_experience()`）

各 Agent 通过自己的 `knowledge.py` 检索知识库并注入 prompt（Step 4 前由 Scribe 统一检索，Step 4 后 Scribe 已删，knowledge 系统归属到各 agent 自身）。embedding API 需要配置 `HAGOKYU_EMBEDDING_*` 环境变量；未配置时知识库仅做 YAML 索引（无向量检索）。

> 实现：`hagoku/storage/knowledge_vector.py`、`hagoku/agents/{agent}/knowledge.py`、`hagoku/agents/{agent}/knowledge.yaml`


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

## 失败处理

HaGoKu 中失败只有三条路径，不做任何「降级到次优路径」的设计。三类失败各有应对策略，但**共同点是：不许代码替 LLM 做语义判断来"装作成功"**。

### 路径 1：LLM 异常

| 场景 | 处理 |
|------|------|
| LLM 超时 / 不可达 / 返回格式异常 | 终止当前 run，通知用户修复 LLM 配置（API key、网络、模型名）后重试 |

> **前置拦截**：pipeline 启动前 `health.check_llm_health()` 验证 LLM 可达性；失败则返回错误，不进 pipeline。

### 路径 2：通道失败 = 项目失败

通道（Agent 输入输出 serialize → transport → validate 链路）是 HaGoKu 的脊梁，**通道失败即项目失败**。

| 场景 | 处理 |
|------|------|
| 任一通道环节（序列化、传输、解析）抛异常 | **项目失败，必须修复通道后重跑**，不允许降级、不允许绕过、不允许兜底 |

> 通道范畴：
> - `orchestrator.py` 对 Agent 的上下文组装与结果写入
> - `storage/` 读写（parquet / yaml / sqlite / JSON）
> - `guardrails/parsers.py` 结构化输出校验
> - `api/ws_handler.py` WebSocket 消息序列化
> - `tools/` 工具函数签名与返回值约定
> - 任一环节抛非 LLM 类异常（`ValueError` / `TypeError` / `FileNotFoundError` 等）均属通道异常

### 路径 3：语义未理解（律 7）

LLM 收到了用户输入但未产生任何有效工具调用（tool_calls 为空、或参数全空、或工具调度结果与用户原话明显无关）——属于第三类失败，**必须显式反馈给用户**，不得静默继续。

| 场景 | 处理 |
|------|------|
| LLM 对用户暂停回复未调用任何工具 | UI 显式提示"系统未理解你的输入，请换一种说法"，保留原 context，本轮暂停继续等待 |
| LLM 调用了工具但参数全为空 / 与原话无关 | 同上，并在 `process_log.md` 记录 raw_text + 工具调用结果供审计 |

> **禁忌**：`logging.warning(...)` 然后默默推进 — 用户感觉"我说了好几遍系统都没反应"，是 B 类语义漏水的高发症状。

### 设计原则

> **不做降级，只做三种响应：提醒用户修 LLM、修代码修通道、提醒用户换说法。**

### 代码层合法动作清单（给实现者）

当代码遇到 LLM 调用失败、解析失败、工具未调、参数无效等异常情况时，**唯一合法的代码动作只有以下四种**。任何其它"防御性兜底"都是违规：

| 合法动作 | 适用情况 | 写法 |
|---------|---------|------|
| **A. 抛 RuntimeError** | LLM 不可达 / 模型返回完全无法解析（非语义失败） | `raise RuntimeError("LLM 不可达，请检查配置")` → 走路径 1 |
| **B. 写未理解信号** | LLM 调用成功但未产生有效工具调用 | `ctx["_last_understanding_failure"] = {raw_text, model_reply, ...}` 然后 `return []` → 走路径 3 |
| **C. 透传给下游** | LLM 给出部分工具调用但语义不完整 | 已落地的部分写权威结构，未落地的留空，由下游 Agent 或下一轮交互补 |
| **D. 拒绝写入** | LLM 给出的参数与用户原话明显矛盾 | 不写权威结构，等同情况 B（写未理解信号） |

**禁止动作**（违反零硬编码原则的常见伪装）：

- ❌ `except: return None` / `except: return []` — 静默吞掉失败
- ❌ `if not result: result = default_value` — 默认值兜底
- ❌ `if user_input in ["收入", "营收", "销售额"]: ...` — 关键词列表
- ❌ `re.search(r"收入|营收|销售", text)` — 中文语义正则
- ❌ 函数名含 `_infer_` / `_detect_` / `_classify_` 但内部无 LLM 调用 — 假装 LLM 实则规则
- ❌ 用 LLM 调用包一层缓存，缓存 miss 时走规则路径 — 隐性降级

**铁律**：当你（实现者）拿不准要不要加一段判断逻辑时，问自己一句——
> *"这段代码做的判断，能不能用一句中文写成 prompt 让 LLM 做？"*
>
> 如果能，就是 LLM 的活——LLM 拿到分析目标和数据后自己会判断。代码只负责把分析目标和数据送到 prompt 里，不替它写结论。

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
> Orchestrator（📋 看板驱动 + 阶段消息生成）在后台运行，不显示终端进度。
```

---

## 项目结构

```
hagoku/
├── llm/              # LLM 客户端 (OpenAI-compatible)
├── manager/          # 编排器（计划生成 + 调度 + 降级）
├── agents/           # 4 个 Agent（scout/cleaner/analyst/reporter）+ base/types/constants
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
| `HAGOKYU_LLM_BASE_URL` | LLM 服务地址（OpenAI 兼容协议，用户运行时配置） | `<用户配置>` |
| `HAGOKYU_LLM_API_KEY` | API 密钥 | `none` |
| `HAGOKYU_LLM_MODEL` | 默认模型名（用户运行时通过设置功能选择） | `<用户配置>` |
| `HAGOKYU_EMBEDDING_BASE_URL` | Embedding 服务地址 | 空（须自行填写） |
| `HAGOKYU_EMBEDDING_API_KEY` | Embedding API 密钥 | `none` |
| `HAGOKYU_EMBEDDING_MODEL` | Embedding 模型名（用户运行时通过设置功能选择） | `<用户配置>` |
| `HAGOKYU_WORK_DIR` | 工作目录 | `~/.hagoku` |
| `HAGOKYU_PROJECT_DIR` | 项目根目录覆盖 | 同 `WORK_DIR/projects` |

---

## 文档索引

| 文档 | 用途 | 受众 |
|------|------|------|
| **PROJECT.md**（本文件） | 项目灵魂、架构原则、通道完备性十律、唯一真相源 | 所有人 |
| `README.md` | 用户手册（安装、命令、快速开始） | 用户 |
| `DEV.md` | 开发快速上手 | 新贡献者 |
| `docs/DEVELOPMENT.md` | 设计手册（看板/向量/防护/审查） | 开发者 |
| `docs/EXTERNAL_REFERENCES.md` | 外部项目思想参考 | 开发者 |
| `docs/TROUBLESHOOTING.md` | 常见问题排查 | 开发者 |
| `docs/AGENT_INTERACTION_CONTRACT.md` | Agent 交互可执行契约 | 开发者 |
| `docs/INTERACTION_MULTITURN_PLAN.md` | 多轮对齐分期方案 | 开发者 |
| `DEVELOPMENT_PROMPT.md` | 路线图跟踪 + 任务传递 + 审查约定 | 协作者 |
| `docs/COMMAND_SYSTEM.md` | 命令系统完整设计 | 开发者 |
| `CLAUDE.md` | AI 编码助手上下文 | AI 助手 |
| `docs/superpowers/specs/2026-06-09-meta-layer-design.md` | HaGoKu Doctor 设计（系统医生 + Prompt Lab 模拟器 + 通道守门） | 开发者 |

---

## 项目信息

- **名称**: HaGoKu Studio
- **灵魂**: 让每个小模型都能做专业级商业分析
- **原则**: 精、准、狠
- **许可**: MIT