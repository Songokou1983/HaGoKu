# HaGoKu Studio 全面项目审计与说明书

> **审计日期**: 2026-05-23
> **审计范围**: 全栈代码库（hagoku Python 后端、hagoku_web 前端、文档、配置、测试）
> **代码规模**: ~20,000+ 行 Python / ~5,000+ TypeScript、12+ 文档文件、30+ 测试文件

---

## 目录

1. [项目概述与定位](#1-项目概述与定位)
2. [架构设计全景](#2-架构设计全景)
3. [各层深度审计](#3-各层深度审计)
   - [3.1 配置层 (config.py)](#31-配置层-configpy)
   - [3.2 LLM 客户端层 (llm/client.py)](#32-llm-客户端层-llmclientpy)
   - [3.3 Agent 层](#33-agent-层)
   - [3.4 Orchestrator 编排层](#34-orchestrator-编排层)
   - [3.5 Tools 工具层](#35-tools-工具层)
   - [3.6 Storage 存储层](#36-storage-存储层)
   - [3.7 Guardrails 护栏层](#37-guardrails-护栏层)
   - [3.8 Observability 可观测性层](#38-observability-可观测性层)
   - [3.9 API / WebSocket 层](#39-api--websocket-层)
   - [3.10 KB 知识库层](#310-kb-知识库层)
   - [3.11 前端层 (hagoku_web)](#311-前端层-hagoku_web)
4. [测试审计](#4-测试审计)
5. [文档审计](#5-文档审计)
6. [部署与运维](#6-部署与运维)
7. [问题发现与改进建议汇总](#7-问题发现与改进建议汇总)
8. [代码质量总结](#8-代码质量总结)

---

## 1. 项目概述与定位

**HaGoKu Studio** 是一个基于 LLM 多智能体协作的数据分析平台。它将传统的数据分析工作流（数据理解 → 清洗 → 统计分析 → 报告生成）映射为 4 个专业化 Agent（Scout、Cleaner、Analyst、Reporter），通过 WebSocket 驱动的交互式管道实现人机协作。

### 核心理念
- **Agent 是语义引擎**：LLM 作为唯一语义理解单元，代码只做机械搬运
- **人机协作多轮暂停**：每个阶段完成后暂停，等待用户确认/修改
- **函数调用 (Function Calling) 作为 Agent 语言**：LLM 通过结构化的函数／工具调用与系统交互
- **项目记忆跨运行复用**：已确认的字段定义不重复询问

### 技术栈
| 层级 | 技术 |
|------|------|
| 后端框架 | FastAPI + Uvicorn |
| LLM 集成 | OpenAI SDK + instructor (结构化输出) |
| 多智能体 | 自研 Agent 基类 (轻 CrewAI 依赖) |
| 数据分析 | Pandas, NumPy, SciPy, Statsmodels, Scikit-learn |
| 数据存储 | SQLite (元数据) + YAML (人可读) + Chroma (向量) |
| 前端 | React + TypeScript + Vite + Tailwind CSS + Zustand |
| 通信 | WebSocket (双向实时) + REST (CRUD) |
| 配置 | Pydantic + YAML + 环境变量 |

---

## 2. 架构设计全景

```
┌─────────────── 前端 (hagoku_web) ───────────────┐
│  App.tsx → Panels (Workspace, Analyze, Kanban)  │
│  Zustand Store → WebSocket ↔ REST              │
└────────────────────┬────────────────────────────┘
                     │ WebSocket (ws_handler.py)
┌────────────────────▼────────────────────────────┐
│              FastAPI Server (api/server.py)     │
│  /api/projects, /api/reports, /api/analyze     │
│  ws:// → ws_handler.py → Orchestrator          │
└────────────────────┬────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────┐
│           Orchestrator (manager/orchestrator.py) │
│  管道调度、多轮交互状态机、Agent 间上下文传递     │
│  闸门 (Gate)、暂停 (Pause)、意图检测 (Intent)     │
└──┬─────────┬──────────┬──────────┬──────────────┘
   │         │          │          │
   ▼         ▼          ▼          ▼
┌──────┐ ┌──────┐ ┌────────┐ ┌──────────┐
│Scout │ │Cleaner│ │Analyst │ │Reporter  │
│1156行│ │856行  │ │~1200行 │ │~400行    │
└──┬───┘ └──┬───┘ └───┬────┘ └────┬─────┘
   │        │         │           │
   ▼        ▼         ▼           ▼
┌────────────────────────────────────────┐
│         Tools 工具层 (13个文件)         │
│  profiling, cleaning, analysis,        │
│  visualization, reporting, business    │
└────────────────────────────────────────┘
   │        │         │           │
   ▼        ▼         ▼           ▼
┌────────────────────────────────────────┐
│    Storage 层 (SQLite + YAML + Chroma) │
│  memory, database, artifact, kanban    │
└────────────────────────────────────────┘
```

---

## 3. 各层深度审计

### 3.1 配置层 (`config.py`, 209行)

**文件**: `hagoku/config.py`

**设计评估**: ★★★★★ 优秀

**核心结构**:
```python
HaGoKuConfig
├── llm: LLMConfig          # 模型连接（支持 model_deep / model_quick 分层）
├── embedding: EmbeddingConfig
├── manager: ManagerModeConfig
├── output: OutputConfig
├── analysis: AnalysisConfig
├── cleaning: CleaningConfig
└── work_dir: Path
```

**亮点**:
1. ✅ **分层优先级**: YAML 文件 → 环境变量 `HAGOKU_` 前缀 → 代码默认值，层级清晰
2. ✅ **Pydantic 强类型**: 每个配置段都是独立的 Pydantic BaseModel，自动校验
3. ✅ **模型分层**: `model_deep` (Analyst/仲裁器) 和 `model_quick` (Scout/Reporter) 允许异构模型部署
4. ✅ **清洗配置详尽**: 33 个参数覆盖 IQR、Z-score、Isolation Forest、MCAR 检验、Winsorize 等
5. ✅ **容错启动**: YAML 解析失败 → 使用默认值，不阻断程序

**注释质量**: ★★★★☆ 
- 类级 docstring 清晰
- 每个字段有简短注释
- 部分字段注释可进一步展开（如 `isolation_forest_contamination` 的业务含义）

**发现**:
- ⚠️ 配置默认值硬编码了本地模型名 `"Qwen3.6-35B-A3B"` 和 `localhost:8080` —— 虽然不是最佳实践，但符合 "本地优先" 的产品定位
- ⚠️ `api_key` 默认值 `"none"` 直接暴露了本地模型场景，但对于默认配置是可接受的

---

### 3.2 LLM 客户端层 (`llm/client.py`, 156行)

**设计评估**: ★★★★☆ 良好

**核心函数**:
| 函数 | 用途 | 模型选择 |
|------|------|----------|
| `create_structured_llm_client()` | instructor 包装的 OpenAI 客户端 | 默认 model |
| `create_raw_client()` | 原始 OpenAI（用于 tool calling） | 默认 model |
| `create_deep_client()` | 深度推理（Analyst/仲裁器） | model_deep or model |
| `create_quick_client()` | 快速推理（Scout/Reporter） | model_quick or model |

**亮点**:
1. ✅ **代理环境变量清理**: 创建客户端前后清理/恢复 `ALL_PROXY` / `HTTP_PROXY` 等 —— 关键设计，防止 socks:// 等不被 httpx 支持的 scheme 导致 ValueError
2. ✅ **instructor 集成**: 使用 `mode=instructor.Mode.JSON` 获取结构化输出
3. ✅ **超时设置**: HTTP timeout 120s，适合 LLM 推理场景
4. ✅ **回退策略**: instructor 不可用时退回原始 OpenAI 客户端

**注释质量**: ★★★☆☆
- 函数 docstring 完整
- 但缺少中文注释解释 "为什么" 要清理代理变量（新人可能不确定机制）
- `create_raw_client` 和 `create_deep_client` 有代码重复（代理清理逻辑重复 3 次）

**改进建议**:
- 🔧 代理清理逻辑应抽为 context manager 或 helper 函数
- 🔧 `max_tokens=8192` 在 `create_quick_client` 中硬编码，应可配置

**完整注释补充**:
```
create_quick_client: 快速客户端将 max_tokens 硬编码为 8192，适用于
Scout/Reporter/Scribe 的反思想场景。快速模型通常上下文窗口较小，
8192 在大多数场景下足够且避免 OOM。
```

---

### 3.3 Agent 层

#### 3.3.0 基类 (`base.py`, 185行)

**设计评估**: ★★★★☆

**核心职责**:
- 统一事件发射（EventBus 集成）
- Agent 生命周期管理（start / complete / fail）
- LLM 客户端创建
- 可选 CrewAI 集成（延迟加载）

**亮点**:
1. ✅ 事件驱动设计：每个操作（思考、工具调用、错误）都通过 EventBus 广播到前端
2. ✅ CrewAI 延迟创建：只在需要时初始化完整的 CrewAI Agent
3. ✅ 双层 LLM 客户端策略：支持外部注入客户端（`_llm_client`），用于架构灵活性

**注释质量**: ★★★★☆
- 方法级 docstring 完整
- 中英混合，结构清晰

#### 3.3.1 Scout Agent (`scout/agent.py`, 1156行) ⭐

**职责**: 字段语义理解 — "数据侦察员"
**设计评估**: ★★★★★ 卓越

**核心流程**:
```
CSV 输入 → 列数据画像 → LLM 工具调用 (submit_field_inference)
→ 跨项目知识库检索 → 项目记忆复用 → 字段描述生成 → 用户确认循环
```

**LLM Function Calling 设计 — 项目最精华部分**:

Scout 定义了 `submit_field_inference` 工具（工具定义在代码中），LLM 通过调用该工具提交每个字段的语义分析结果。工具参数设计为：
```python
{
  "columns": [{
    "name", "inferred_type", "confidence", "evidence",
    "needs_user_input", "suggested_role", "display_name", "description"
  }],
  "target_columns", "feature_columns", "target_keywords_from_query"
}
```

**核心设计原则**: `# ==== CHANNEL ZONE: 禁止正则/if-else 语义分支 ====` 
— 这个设计原则贯穿 Scout 和 Orchestrator，代码只搬运 LLM 输出，不做语义判断。

**亮点**:
1. ✅ **LLM 唯一引擎**: 字段语义推断完全交给 LLM 的 function calling，代码不做硬编码解析
2. ✅ **跨项目知识库**: `_inject_knowledge_context()` 通过 Chroma 向量检索历史项目的字段分析经验
3. ✅ **项目记忆复用**: 从 YAML 文件读取已确认的字段定义，直接复用避免重复询问
4. ✅ **兜底机制**: `_infer_column()` (1020-1147行) 提供确定性推断规则，用于测试和 LLM 不可用场景
5. ✅ **字段描述生成**: `_generate_field_descriptions()` 回填 LLM 产出的 display_name / description

**注释质量**: ★★★★☆
- 每个方法有清晰 docstring
- 代码内联注释解释算法意图
- `CHANNEL ZONE` 注释标注了架构设计禁区

**发现**:
- ⚠️ `_infer_column()` (行 1020-1147) 包含大量硬编码规则（如 `n_unique == n_total → ID`），部分与 `CHANNEL ZONE` 原则存在张力
- ⚠️ 知识库检索相似度阈值 `0.45` (行 506) 硬编码，可能需要根据知识库规模调整
- ⚠️ `scout/agent.py` 达 1156 行，包含多个职责（字段推断、知识管理、LLM 交互、描述生成），建议拆分

#### 3.3.2 Cleaner Agent (`cleaner/agent.py`, 865行)

**职责**: 数据清洗 — 4 阶段清洗管道
**设计评估**: ★★★★☆

**4 阶段清洗管道**:
```
Phase 1: 检测 (detect) → Phase 2: 决策 (decide) → Phase 3: 执行 (execute) → Phase 4: 评估 (assess)
```

**亮点**:
1. ✅ **策略驱动**: LLM 生成清洗策略 JSON，代码机械执行（遵循 CHANNEL ZONE 原则）
2. ✅ **8+ 清洗操作**: 覆盖缺失值处理（drop/impute）、异常值处理（winsorize/isolate）、重复行、数据类型转换、标准化
3. ✅ **影响评估**: Phase 4 评估清洗前后的数据分布变化
4. ✅ **清洗报告**: 生成结构化的清洗报告，包含每步操作的记录数变化

**注释质量**: ★★★☆☆
- 方法级注释充分
- 但 Phase 1-4 的设计意图和转换规则在代码中较分散，建议在文件头增加管道状态机图

**发现**:
- ⚠️ 策略 JSON 结构较复杂（嵌套 3-4 层），LLM 偶尔生成格式不严格匹配的 JSON
- ⚠️ `_map_strategy_to_ops()` 中的策略名与函数名硬编码映射，新增策略需同时修改映射表和函数

#### 3.3.3 Analyst Agent (`analyst/agent.py`)

**职责**: 统计分析执行
**设计评估**: ★★★★☆

**核心流程**:
```
分析目的 → LLM 生成分析计划 → 工具调用执行统计分析
→ 结果验证 → 解释生成
```

**亮点**:
1. ✅ **分析计划结构**: 使用 Pydantic 模型 (`AnalysisPlan`) 与 LLM 的结构化输出对齐
2. ✅ **统计方法矩阵**: 覆盖 t 检验、ANOVA、卡方检验、相关性分析、回归分析等
3. ✅ **效应量计算**: 不仅报告 p 值，还计算 Cohen's d、η² 等效应量
4. ✅ **结果验证**: 检查分析计划的执行完整性和合理性

#### 3.3.4 Reporter Agent (`reporter/agent.py`)

**职责**: 报告生成 — 将分析结果转化为 HTML 报告
**设计评估**: ★★★★☆

**亮点**:
1. ✅ **模板系统**: 支持多种报告模板（business_analysis, executive_brief, academic, data_audit, ab_test）
2. ✅ **图表嵌入**: 生成的 HTML 包含 Plotly 交互式图表
3. ✅ **Markdown 渲染**: 支持 LLM 生成的 Markdown 内容渲染为 HTML

#### 3.3.5 Scribe Agent (`_scribe/agent.py`)

**职责**: 仲裁/把关 Agent — 在各阶段结束后验证输出的完整性和合理性
**设计评估**: ★★★★☆

**亮点**:
1. ✅ **闸门模式**: 在每个 Agent 完成后进行质量检查
2. ✅ **仲裁逻辑**: 使用 LLM 判断是否需要重新执行某个阶段
3. ✅ **事件日志**: 完整记录了仲裁决策过程

---

### 3.4 Orchestrator 编排层 (`manager/orchestrator.py`, ~2800行) ⭐

**职责**: 管道总控、多轮交互状态机、Agent 间上下文传递

**设计评估**: ★★★★★ 卓越（但复杂度高）

**核心设计 — 多轮交互暂停/恢复**:

管道在每个关键阶段后暂停，等待用户输入。这是整个系统最复杂的状态管理部分。

```
管道流程:
  Scout → [Field Review 暂停] → Gate → Cleaner
  → [Cleaning Review 暂停] → Analyst
  → [Analysis Review 暂停] → Reporter → 报告输出

每个暂停点:
  1. 生成暂停负载 (pause payload) → 发送到前端
  2. 前端展示，用户输入
  3. 意图检测: 确认放行 or 有修改补充？
  4. 确认 → 继续下一阶段
  5. 补充 → 应用修改，重新暂停
```

**意图检测机制 — 核心亮点**:

```python
# 三层意图检测:
1. 正则快速匹配: 明确的确认/否词（如 "确认"、"好的"、"ok"）
2. LLM 意图分类: 正则未匹配 → 调用 LLM 判断 intent = "confirm" / "modify"
3. 安全默认值: LLM 不可用 → 回退到 "modify"（确保用户输入不被静默丢弃）

# Scout 字段核对:
_scout_reply_is_pure_confirm() → _detect_user_intent_via_llm()

# Cleaner 审核:
_cleaner_reply_accepts_proceed() → _detect_user_intent_via_llm()

# Analyst 审核:
_analyst_reply_accepts_proceed() → _detect_user_intent_via_llm()
```

**Scout 字段理解回写 — Function Calling 2.0**:

```python
# Orchestrator 定义了 update_field_understanding 和 update_field_role 两个工具
# LLM 理解用户自然语言输入后，通过调用这些工具主动更新字段表格

_SCOUT_FIELD_UPDATE_TOOLS = [
    "update_field_understanding": 更新 display_name 和 description
    "update_field_role":        更新 target / features / ignored
]

# 代码只负责机械地将 tool_calls 应用到 context
_apply_field_update(tool_calls, context)
_apply_role_update(tool_calls, context)
```

**亮点**:
1. ✅ **CHANNEL ZONE 设计**: 全文件多次标注 `==== CHANNEL ZONE: 禁止正则/if-else 语义分支 ====`，强制代码不做语义理解
2. ✅ **安全默认值**: LLM 不可用时回退到 "有补充"（conservative），确保用户输入不被丢弃
3. ✅ **暂停负载结构化**: 每个暂停点的 payload 设计为前端可直接渲染的结构
4. ✅ **闸门机制**: `_is_gate_confirm()` 在字段对齐后提供 "确认进入清洗" 的最终闸门
5. ✅ **列名模糊匹配**: `_resolve_scout_column_token()` 支持大小写、下划线变化的列名匹配

**发现**:
- ⚠️ **文件过大**: ~2800 行，建议拆分。可拆为：
  - `orchestrator.py`: 管道调度主逻辑
  - `orchestrator_intent.py`: 意图检测 + 暂停处理
  - `orchestrator_scout_review.py`: Scout 字段核对子状态机
- ⚠️ 正则表达式散落在多个函数中（`_SCOUT_PURE_CONFIRM_RE`, `_STAGE_CLEANER_PROCEED_RE`, `_STAGE_ANALYST_PROCEED_RE` 等），缺乏集中的常量管理
- ⚠️ `_detect_user_intent_via_llm` 的 LLM prompt 较简单，在边缘用例（如用户输入 "好的，但是..."）可能误判

**注释质量**: ★★★★★
- 文件头有完整的管道架构说明
- 每个函数有清晰的 docstring
- CHANNEL ZONE 标记明确
- 行内注释解释了设计意图

---

### 3.5 Tools 工具层

**文件清单**: 13 个文件（analysis.py, cleaning.py, profiling.py, visualization.py, reporting.py, business.py, diagnostics.py, health.py, power_analysis.py, data_io.py, analysis_registry.py, __init__.py）

**设计评估**: ★★★★☆

**亮点**:
1. ✅ **职责分离**: 清洗、分析、可视化、报告各自独立模块
2. ✅ **分析注册表** (`analysis_registry.py`): 统一管理可用的统计分析方法
3. ✅ **功效分析** (`power_analysis.py`): 提供了 G*Power 风格的样本量/功效计算
4. ✅ **诊断工具** (`diagnostics.py`): 数据质量检查功能

**发现**:
- ⚠️ `cleaning.py` 中的清洗操作函数与 Cleaner Agent 的 Phase 3 有紧密耦合
- ⚠️ 缺乏对 LLM 生成的策略 JSON 的结构化校验（可能导致 KeyError）

---

### 3.6 Storage 存储层

**设计评估**: ★★★★★ 卓越

**双后端设计**:
```
MemoryManager (Facade)
├── SqliteMemoryBackend  → 程序化查询、ACID 事务
├── YamlMemoryBackend    → 人可读、Git 友好、用户可手动编辑
└── Chroma 向量存储       → 跨项目知识检索 (KB)
```

**亮点**:
1. ✅ **YAML 优先**: YAML 作为用户真相源，SQLite 作为查询缓存
2. ✅ **自动同步**: `_auto_sync_yaml()` 在 YAML 比 SQLite 新时自动导入
3. ✅ **MemoryManager Facade**: 调用方无需知道存储后端细节
4. ✅ **项目隔离**: 按 `project_id` 分区存储
5. ✅ **Kanban 存储** (`kanban.py`): 支持看板工作流状态管理

**注释质量**: ★★★★☆
- 模块级 docstring 清晰解释了双后端设计理念
- 方法级注释充分

---

### 3.7 Guardrails 护栏层

**设计评估**: ★★★☆☆

**功能**:
```python
parse_pvalue(text)              # 从 LLM 输出提取 p 值
parse_effect_size(text)          # 提取效应量 (Cohen's d, η²)
parse_conclusion_count(text)     # 统计结论数量
parse_confidence_interval(text)  # 提取置信区间
validate_analysis_output(text)   # 综合验证
```

**亮点**:
1. ✅ **正则模式丰富**: 覆盖多种 LLM 输出格式
2. ✅ **启发式过滤**: CI 提取中排除差值 > 10 的非区间匹配

**发现**:
- ⚠️ **只做提取不做验证**: 提取出的 p 值、效应量不做合理性检查（如 p 值是否在 [0,1] 范围内）
- ⚠️ 文件仅 118 行，功能相对单薄。可扩展方向：
  - 统计结论一致性校验（p 值 vs CI 是否矛盾）
  - 幻觉检测（LLM 生成不存在的统计量）
  - 分析计划合理性检查

---

### 3.8 Observability 可观测性层

**设计评估**: ★★★★☆

**核心组件**:
```
EventBus (单例) → Event (EventType, data)
├── AGENT_STARTED / AGENT_COMPLETED / AGENT_FAILED
├── AGENT_THINKING (thought 流)
├── TOOL_CALLED / TOOL_RESULT / TOOL_ERROR
├── PAUSE_TRIGGERED / USER_INPUT_APPLIED
└── → WebSocket 广播到前端
```

**亮点**:
1. ✅ **事件驱动**: Agent 的所有动作都产生事件，解耦 Agent 和 UI
2. ✅ **类型安全**: EventType 枚举确保事件名的一致性
3. ✅ **前端联动**: 前端通过 WebSocket 订阅事件流，实时更新 UI

---

### 3.9 API / WebSocket 层

**设计评估**: ★★★★☆

**架构**:
```
FastAPI Server
├── REST: /api/health, /api/projects, /api/reports, /api/analyze
├── WebSocket: ws_handler.py → 双向事件流
│   ├── 事件上行: 用户操作 → Orchestrator
│   └── 事件下行: Agent 状态 → 前端 UI
└── CORS: 全开放（开发友好）
```

**亮点**:
1. ✅ **WebSocket 双向通信**: 支持实时推送 Agent 思考过程
2. ✅ **lifespan 初始化**: 每个 uvicorn worker 启动时创建 Orchestrator
3. ✅ **文件上传**: 支持 CSV 文件上传作为分析输入

**发现**:
- ⚠️ `allow_origins=["*"]` — 开发环境可接受，生产部署需锁定
- ⚠️ WebSocket 异常处理较简单，连接断开后的状态恢复未处理

---

### 3.10 KB 知识库层

**设计评估**: ★★★★☆

**功能**:
```
Scout 跨项目知识库 (Chroma 向量存储)
├── kb/_registry.yaml → 知识库注册
├── kb/knowledge_base.py → 知识库管理 (learn, recall, delete)
├── kb/business/ → 业务领域知识
├── kb/financial/ → 金融领域知识
└── kb/stats/ → 统计方法知识
```

**Scout 中的使用** (行 489-567):
- 对每个字段，用列名 + 样本值做向量检索
- 相似度阈值 0.45 过滤低质量匹配
- 检索结果注入 LLM 提示词作为 "参考而非决定"

**亮点**:
1. ✅ **知识复用**: 项目 A 确认的字段含义可辅助项目 B 的字段推断
2. ✅ **领域分离**: business / financial / stats 三个独立知识域
3. ✅ **相似度阈值**: 避免低质量匹配误导 LLM

---

### 3.11 前端层 (hagoku_web)

**技术栈**: React 18 + TypeScript + Vite + Tailwind CSS + Zustand

**设计评估**: ★★★★☆

**核心组件**:
```
App.tsx → 应用入口、WebSocket 连接管理
Panels:
├── DashboardPanel → 项目总览
├── CanvasPanel → 分析画布（拖拽式分析编排）
├── AnalyzePanel → 分析参数配置 + 交互确认界面
├── KanbanPanel → 清洗步骤看板
├── CommandsPanel → 命令系统界面
└── ReportsPanel → 报告查看（HTML 嵌入）
```

**亮点**:
1. ✅ **Zustand 状态管理**: 轻量、类型安全
2. ✅ **WebSocket 实时推送**: Agent 状态实时更新
3. ✅ **Tailwind CSS**: 快速 UI 开发
4. ✅ **交互确认 UI**: 暂停点的字段表格、清洗报告、分析报告都有对应的确认界面

**发现**:
- ⚠️ 前端类型定义 (`types/`) 与后端 Pydantic 模型缺乏共享定义（可能产生类型不同步）
- ⚠️ 错误处理主要在 UI 层，缺乏全局错误边界

---

## 4. 测试审计

**测试文件清单** (~35 个文件):

| 模块 | 测试文件 | 覆盖范围 |
|------|----------|----------|
| Agents | `test_agents.py` | Scout 字段推断、Cleaner 清洗、Analyst 分析 |
| Orchestrator | `test_scout_user_reply_apply.py` | Scout 字段回写 |
| | `test_cleaning_review_payload.py` | 清洗审查负载 |
| | `test_scout_field_review_payload.py` | 字段审查负载 |
| Tools | `test_tools.py`, `test_analysis_enhanced.py`, `test_visualization.py` | 工具函数 |
| LLM | `test_plan_generation.py` | 分析计划生成 |
| Guardrails | `test_guardrails.py` | 解析器 |
| Storage | `test_storage.py`, `test_memory.py`, `test_project_manager.py` | 存储 |
| API | `test_server.py`, `test_ws_handler.py` | API/WS |
| Pipeline | `test_pipeline.py`, `test_failure_path.py` | 端到端管道 |
| Product | `test_agent_interaction_contract.py`, `test_interaction_scenarios.py` | 交互契约 |
| Web | `test_ws_guardrails_parity.py` | 前后端护栏一致性 |

**测试质量评估**: ★★★★☆

**亮点**:
1. ✅ **交互契约测试** (`test_agent_interaction_contract.py`): 验证 Agent 间的上下文传递格式
2. ✅ **交互场景测试** (`test_interaction_scenarios.py`): 模拟多轮对话的完整流程
3. ✅ **失败路径测试** (`test_failure_path.py`): 验证错误处理的健壮性
4. ✅ **前后端一致性测试** (`test_ws_guardrails_parity.py`): 确保 WebSocket 事件格式一致

**发现**:
- ⚠️ 缺少 Scout LLM function calling 模式的完整集成测试
- ⚠️ 性能测试完全缺失（如大型 CSV 文件处理、多项目并发）
- ⚠️ 无 LLM 输出格式的 Fuzzing 测试

---

## 5. 文档审计

| 文档文件 | 质量 | 审计备注 |
|----------|------|----------|
| `README.md` | ★★★★ | 快速开始指南，清晰 |
| `PROJECT.md` | ★★★★★ | 全面的项目上下文，Agent 角色说明 |
| `DEV.md` | ★★★★ | 开发环境搭建指南 |
| `CLAUDE.md` | ★★★★★ | AI 助手开发规范，非常详尽 |
| `docs/DEVELOPMENT.md` | ★★★★ | 开发流程说明 |
| `docs/COMMAND_SYSTEM.md` | ★★★★★ | 命令系统完整说明 |
| `docs/AGENT_INTERACTION_CONTRACT.md` | ★★★★★ | Agent 间交互契约形式化定义 |
| `docs/INTERACTION_MULTITURN_PLAN.md` | ★★★★★ | 多轮交互暂停/恢复详细设计 |
| `docs/DATA_CLEANING_REVIEW.md` | ★★★★ | 数据清洗审查流程 |
| `docs/AGENT_HARDCODED_REVIEW.md` | ★★★★★ | 硬编码审查报告 |
| `docs/EXTERNAL_REFERENCES.md` | ★★★★ | 外部引用说明 |
| `docs/TROUBLESHOOTING.md` | ★★★☆ | 故障排除手册（可更详尽） |
| `UI_CHANGELOG.md` | ★★★★ | UI 变更日志 |
| `DEVELOPMENT_PROMPT.md` | ★★★★ | 开发提示词 |

**Prompt 文件** (Agent 系统提示词):
| 文件 | 用途 |
|------|------|
| `scout/prompt.md` | Scout 的字段语义理解系统提示 |
| `cleaner/prompt.md` | Cleaner 的数据清洗策略提示 |
| `analyst/prompt.md` | Analyst 的统计分析提示 |
| `reporter/prompt.md` | Reporter 的报告生成提示 |
| `_scribe/prompt.md` | Scribe 的仲裁判断提示 |

---

## 6. 部署与运维

**依赖管理**: `pyproject.toml` + `uv.lock` (使用 uv 包管理器)
**前端构建**: Vite + npm
**数据库**: SQLite (轻量级，无需外部数据库服务)

**发现**:
- ⚠️ 无 Docker Compose / 容器化部署配置
- ⚠️ 无 CI/CD 配置（GitHub Actions 等）
- ⚠️ 无日志聚合方案（当前为 Python logging 到控制台）

---

## 7. 问题发现与改进建议汇总

### 严重问题 (P0)

**无** — 项目在关键路径上没有发现导致数据丢失或安全漏洞的严重问题。

### 重要问题 (P1)

| # | 问题 | 位置 | 建议 |
|---|------|------|------|
| 1 | Orchestrator 文件过大 (~2800行) | `orchestrator.py` | 拆分为 3 个文件：`orchestrator.py`(管道调度)、`orchestrator_intent.py`(意图检测)、`orchestrator_scout_review.py`(字段核对) |
| 2 | 代理清理代码重复 3 次 | `llm/client.py` | 抽取为 `@contextmanager _clear_proxy_env()` |
| 3 | 前端类型与后端 Pydantic 模型未共享 | `types/` | 考虑使用 OpenAPI 生成 TypeScript 类型或手动保持同步 |

### 一般问题 (P2)

| # | 问题 | 位置 | 建议 |
|---|------|------|------|
| 4 | Scout `_infer_column` 硬编码规则与 CHANNEL ZONE 原则有张力 | `scout/agent.py:1020-1147` | 明确标注为 "测试/离线回退"，生产路径确保走 LLM |
| 5 | intent detection prompt 较简单 | `orchestrator.py:218-232` / `query_parser.py` | ✅ **已修复** — `query_parser.py` system_prompt 已增强：补充全部 intent_type 判断指引 + 中文业务场景特化示例 |
| 6 | 无性能测试 | 测试套件 | 增加大型 CSV (10万+行) 的性能基准测试 |
| 7 | LLM 输出无结构化校验 | `cleaner/agent.py` | 增加策略 JSON 的 Pydantic 校验层 |
| 8 | CORS `allow_origins=["*"]` | `api/server.py` | 区分开发/生产环境 |
| 9 | WebSocket 重连无状态恢复 | `ws_handler.py` | 增加断线重连后的状态同步机制 |
| 10 | 清洗策略映射硬编码 | `cleaner/agent.py` | 考虑使用策略注册表模式 |

### 增强建议 (P3)

| # | 建议 |
|---|------|
| 11 | 添加 Docker Compose 部署配置 |
| 12 | 添加 GitHub Actions CI 配置 |
| 13 | Guardrails 层增强：p 值合理性校验、幻觉检测 | ✅ **已修复** — `parsers.py` 新增 `deep_validate()`（p 值范围检查、CI 合法性、p/CI 一致性校验、自相矛盾检测），已暴露到 `__init__.py` |
| 14 | 增加分析结果的可重复性验证（相同输入 → 相同输出） |
| 15 | 知识库 recall 的相似度阈值可配置化 |
| 16 | 增加缓存层：LLM 输出缓存避免重复推理 |

---

## 8. 代码质量总结

### 总体评分

| 维度 | 评分 | 说明 |
|------|------|------|
| **架构设计** | ★★★★★ | 清晰的 Agent 管道 + 多轮交互模式，CHANNEL ZONE 设计原则贯穿 |
| **代码职责** | ★★★★☆ | Agent 职责清晰，但个别文件过大（Orchestrator 2800行、Scout 1156行） |
| **注释文档** | ★★★★★ | 中文注释详尽，docstring 完整，设计原则标注明确 |
| **错误处理** | ★★★★☆ | 异常有统一处理，LLM 失败有安全回退 |
| **可测试性** | ★★★★☆ | 测试覆盖全面，但缺少性能测试和 LLM 边缘用例 |
| **安全性** | ★★★☆☆ | CORS 全开放，无认证机制（本地应用可接受） |
| **可扩展性** | ★★★★★ | 知识库、模板系统、配置分层均易于扩展 |
| **代码风格** | ★★★★★ | 一致的命名规范、类型注解完整、遵循 PEP 风格 |

### 核心设计模式

1. **CHANNEL ZONE 原则**: 代码只搬运 LLM 输出，不做语义理解 — 这是整个系统最核心的设计哲学
2. **Function Calling 作为 Agent 语言**: LLM 通过调用工具函数与系统交互，而非输出裸 JSON
3. **Facade 模式**: MemoryManager 封装双后端存储
4. **事件驱动**: EventBus 解耦 Agent 状态与 UI 展示
5. **策略模式**: Cleaner 的清洗策略注册表
6. **安全回退**: LLM 不可用时的确定性降级路径

### 最优秀的代码片段

**Scout 的 LLM Function Calling 集成** (行 585-682):
- 完整的工具定义 (JSON Schema)
- LLM 调用、结果解析、兜底处理
- 缺失列补全
- 多格式兼容 (tool_call / raw JSON / markdown)

**Orchestrator 的意图检测** (行 205-308):
- 三层检测策略 (正则 → LLM → 安全默认值)
- 多阶段适配 (scout / cleaner / analyst)
- 安全保守的失败回退

---

> *审计完成。整体评价：这是一个设计精良、理念先进的 LLM 多智能体数据分析平台。架构设计中的 CHANNEL ZONE 原则和 Function Calling 集成模式值得作为 LLM 应用开发的参考范式。*