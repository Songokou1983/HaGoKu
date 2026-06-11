# Memory 三层体系 mini-brief（2026-06-11）

> **文档定位**：架构审核方出具，交付实施 AI 执行。
>
> **本 brief 是 [`2026-06-11-collapse-to-single-agent-brief.md`](2026-06-11-collapse-to-single-agent-brief.md) 的子 brief**——专门规划 4 agent 合 1 后"知识与记忆"体系的重组。
>
> **前置依赖**：collapse brief 的 Phase B 完成（ProjectContext 升级为唯一 chat 持有者）。
>
> **实施时机**：collapse brief 的 Phase D（4 agent 合 1）+ Phase E（工具箱深化）。

---

## §0 来龙去脉

### 0.1 触发场景

2026-06-11 与用户讨论 collapse 改造时，用户重新整理了知识/记忆体系——从当前"4 份 knowledge.py + hagoku/kb + storage/knowledge_vector + MemoryManager 混合"简化为**清晰的三层**：

> 1. 关于分析方法（学术）的知识库
> 2. 关于 Agent 本身能力成长的记忆系统
> 3. 关于单个项目信息的记忆系统

这三层的清晰度对当前实现是**降维打击**。

### 0.2 现状混乱

```
hagoku/kb/                          ← 业务/金融/统计 三库（杂糅业务 + 学术）
├── business/  financial/  stats/   
├── knowledge_base.py
└── _registry.yaml

hagoku/storage/knowledge_vector.py  ← 向量库引擎

hagoku/agents/scout/knowledge.py    ← 4 份各 agent 的接口
hagoku/agents/cleaner/knowledge.py
hagoku/agents/analyst/knowledge.py
hagoku/agents/reporter/knowledge.py

hagoku/storage/memory.py            ← 项目记忆 MemoryManager
```

**问题**：
- 业务/金融/学术混在 `hagoku/kb/` 同一层级
- 4 份 knowledge.py 是 4 agent 时代的产物，Phase D 后无意义
- **"Agent 能力成长记忆"完全缺失**——每次新 run 都是白纸
- 学术方法、项目记忆、向量索引三件事职责不清

### 0.3 新设计的核心洞察

| 层 | 性质 | 写入者 | 读取者 | 生命周期 |
|---|------|--------|--------|---------|
| ① 学术方法知识库 | 静态、几乎不更新 | 项目维护者（人）| LLM 主动查询 | 跨项目永久 |
| ② Agent 能力成长记忆 | 动态、追加式 | **LLM 自己**写入 | LLM 自己查询 | 跨项目永久 |
| ③ 单项目信息记忆 | 动态、可清空 | LLM + 用户纠正 | LLM 本项目内 | 项目级，clear-history 时清 |

**关键判别原则**：
- 字段名级别的具体信息 → ③ 项目记忆
- 方法/模式级别的抽象经验 → ② Agent 成长记忆
- 学科共识的稳定知识 → ① 学术方法库

举例：
- `Code = 店铺编号` → ③（项目特定，下次同项目可复用，跨项目无意义）
- `n<10 的均值比较优先非参检验，因为方差估计不稳` → ②（跨项目通用，从 LLM 实战经验沉淀）
- `Mann-Whitney U 检验的假设：独立观测 + 分布形状相似` → ①（教科书知识，不变）

---

## §1 三层详细设计

### ① 学术方法知识库

**目录结构**：
```
hagoku/memory/methods/
├── statistics/          ← t 检验 / ANOVA / 回归 / 非参检验 / 多重比较
│   ├── t_test.md
│   ├── anova.md
│   ├── mann_whitney.md
│   └── ...
├── ml/                  ← 监督 / 非监督 / 模型诊断
├── causal/              ← DiD / IV / PSM / RDD
└── bayesian/            ← Bayes 因子 / MCMC / 先验选择
```

**内容形态**：每个方法一份 markdown，结构：
```
# <方法名>

## 适用场景
## 假设条件
## 实施步骤（参考——LLM 自己决定具体执行）
## 常见误用
## 反例（什么时候不该用）
## 配套护栏（共线性 / 多重比较 / 效应量等）
```

**暴露给 LLM 的工具**：
```python
query_method(
    question: str,           # "小样本均值比较怎么选检验"
    scope: list[str] | None  # ["statistics", "ml"]，None = 全部
) -> list[MethodMatch]
  # 返回相关方法的摘要 + 路径，LLM 决定是否再细读

read_method(path: str) -> str
  # 读取完整 markdown
```

**实施动作**（Phase D 内）：
- 把 `hagoku/kb/stats/` 整体迁移到 `hagoku/memory/methods/statistics/`
- 删除 `hagoku/kb/business/` 和 `hagoku/kb/financial/`——业务专有知识属于 ② / ③，不属于 ①
- 删除 `hagoku/kb/knowledge_base.py`（功能由 query_method tool 替代）
- 保留 `hagoku/storage/knowledge_vector.py` 作为底层引擎（被 ① / ② 共用）

### ② Agent 能力成长记忆（**全新**）

**目录结构**：
```
hagoku/memory/lessons.jsonl              ← append-only，每行一条 Lesson
hagoku/memory/lessons_index/             ← 向量索引（reuse knowledge_vector）
```

**Lesson schema**：
```python
@dataclass
class Lesson:
    id: str                              # UUID
    timestamp: str                       # ISO datetime
    project_id: str                      # 来源项目（仅追溯用，跨项目可见）
    
    scenario: str                        # "小样本 ROI 比较"
    what_worked: str                     # "Mann-Whitney + Cliff's delta"
    what_failed: str                     # "t 检验在 n<10 时方差不稳"——强制非空或显式 "none"
    lesson: str                          # "n<10 的均值比较优先非参 + 报告效应量"
    
    conditions_to_recheck: list[str]     # 适用前提，LLM 召回时必须验证
                                          # 例：["样本量 n<10", "目标是均值差异"]
    confidence: str                      # "high" | "medium" | "low"
    
    user_validated: bool                 # 用户是否在事后认可此 lesson
    superseded_by: str | None            # 被 LessonAuditor 标记为过时时填后续 lesson id
```

**暴露给 LLM 的工具**：
```python
save_lesson(
    scenario: str,
    what_worked: str,
    what_failed: str,                    # 强制非空（不写就传 "none"）
    lesson: str,
    conditions_to_recheck: list[str],
    confidence: str
) -> str  # 返回 lesson id

recall_lessons(
    context_query: str,                  # 当前场景描述
    top_k: int = 3
) -> list[Lesson]
  # 返回时显式标注"参考用，不是结论；请验证 conditions_to_recheck"

correct_lesson(
    lesson_id: str,
    new_lesson: str | None,              # None = 标记为废弃
    reason: str
) -> None
```

**反"经验绑架"设计（防御铁律 6）**：

| 风险 | 防御机制 |
|------|---------|
| LLM 看到 lesson 直接复制方法，不再独立判断 | `recall_lessons` 返回必须包含字符串 `"这些是历史参考，请用 conditions_to_recheck 验证适用性"` |
| 错误经验累积污染 | `confidence` + `user_validated` 双字段；`LessonAuditor` Agent 周期审核（见 [Meta v2 brief](2026-06-11-meta-layer-v2-brief.md)） |
| 全是成功叙事缺反思 | `what_failed` **强制非空**——schema 验证拒绝空值 |
| 同类 lesson 重复 | `LessonAuditor` 周期去重，写入时 `save_lesson` 提示"已有相似 lesson X，是否补充而非新增" |

### ③ 单项目信息记忆

**目录结构**：
```
hagoku/memory/projects/<project_id>/
├── fields.yaml          ← 用户确认过的字段语义
├── analysis_goal.txt    ← 当前分析目标（最新版本）
├── chat_history.jsonl   ← 本项目历次 run 的 chat 归档（append-only）
└── corrections.jsonl    ← 用户在本项目里所有显式纠正
```

**暴露给 LLM 的工具**：
```python
remember_field(
    column: str,
    display_name: str | None,
    semantics: str | None,
    role: str | None,                    # target / feature / identifier / ignore
    confirmed_by_user: bool
) -> None

query_project_memory(
    project_id: str | None,              # None = 当前项目
    aspect: str                          # "fields" | "history" | "corrections"
) -> dict

forget_project(project_id: str) -> None  # clear-history 实现
```

**与 ProjectContext 的关系**：
- `ProjectContext`（collapse brief Phase B 升级版）= **当前 run 内**的 append-only chat
- `③ 项目记忆` = **跨 run** 的项目级持久化
- 关系：run 结束时，`ProjectContext` 的关键事件（字段确认 / 用户纠正 / 分析结论）落库到 ③

---

## §2 文件层级重组

### 重组前
```
hagoku/kb/                     ← 删
├── business/                  ← 删
├── financial/                 ← 删
├── stats/                     ← 迁移到 hagoku/memory/methods/statistics/
├── knowledge_base.py          ← 删
└── _registry.yaml             ← 删

hagoku/storage/knowledge_vector.py  ← 保留，移到 memory/_vector.py
hagoku/storage/memory.py            ← 重构为 memory/projects/_manager.py

hagoku/agents/scout/knowledge.py    ← 删（4 份）
hagoku/agents/cleaner/knowledge.py
hagoku/agents/analyst/knowledge.py
hagoku/agents/reporter/knowledge.py
```

### 重组后
```
hagoku/memory/
├── methods/                   ← ① 学术方法（从 kb/stats 迁入）
│   ├── statistics/
│   ├── ml/
│   ├── causal/
│   └── bayesian/
├── lessons.jsonl              ← ② Agent 成长（新建）
├── lessons_index/             ← ② 向量索引（新建）
├── projects/                  ← ③ 单项目记忆（从 storage/memory.py 重构）
│   └── <project_id>/
├── _vector.py                 ← 底层向量引擎（从 storage/knowledge_vector.py 迁入）
└── __init__.py

hagoku/tools/memory_tools.py   ← 暴露所有 memory 工具（query_method / save_lesson / 
                                  recall_lessons / correct_lesson / remember_field / 
                                  query_project_memory / forget_project / read_method）
```

**删除**：
- `hagoku/kb/` 整目录
- `hagoku/storage/knowledge_vector.py`（迁移到 `memory/_vector.py`）
- `hagoku/storage/memory.py`（重构到 `memory/projects/_manager.py`）
- 4 份 `hagoku/agents/*/knowledge.py`

---

## §3 实施分解

### Phase D 内（与 4 agent 合 1 同步）

| # | 任务 | 涉及文件 |
|---|------|---------|
| CO-D6.1 | 创建 `hagoku/memory/` 目录骨架 | 新建 |
| CO-D6.2 | 迁移 `hagoku/kb/stats/` → `memory/methods/statistics/`；删 business / financial | 文件移动 |
| CO-D6.3 | 迁移 `storage/knowledge_vector.py` → `memory/_vector.py`；改所有 import | rename + 全仓 import 改 |
| CO-D6.4 | 重构 `storage/memory.py` → `memory/projects/_manager.py`；改所有 import | rename + 全仓 import 改 |
| CO-D6.5 | 删 4 份 `agents/*/knowledge.py` | 删 4 文件 |
| CO-D6.6 | 创建 `memory/lessons.jsonl` 空文件 + Lesson schema 定义 | 新建 |

### Phase E 内（工具箱深化）

| # | 任务 | 涉及文件 |
|---|------|---------|
| CO-E4.1 | 创建 `hagoku/tools/memory_tools.py` 暴露 8 个工具 | 新建 ~200 行 |
| CO-E4.2 | 注册到 `tools/agent_tool_defs.py` registry | +30 行 |
| CO-E4.3 | 在「数据分析师」prompt.md 加章节："你可以查 ① 方法库 / ② 成长记忆 / ③ 项目记忆"；明确"② 是参考不是结论" | prompt.md +30 行 |
| CO-E4.4 | 给 `recall_lessons` 加 "参考用不是结论" 字符串硬塞返回（防绕过）| memory_tools.py 实现 |
| CO-E4.5 | 加测试：lessons.jsonl append-only / what_failed 强制非空 / recall 返回必含警示语 | tests/test_memory/ ~80 行 |

---

## §4 审核标准

| 层 | 验收 |
|---|------|
| ① 方法库 | `grep -rn "from hagoku.kb" hagoku/` 返回 0；`query_method` 真 LLM 冒烟能正确返回 ≥1 条相关方法 |
| ② 成长记忆 | `save_lesson` 拒绝空 `what_failed`；`recall_lessons` 返回必含警示语；测试覆盖 |
| ③ 项目记忆 | `MemoryManager` 旧测试全迁移并保持绿；`forget_project` 实现 clear-history 语义 |
| 整体 | 4 份 `knowledge.py` 全删；`hagoku/kb/` 目录消失；`grep -rn "knowledge_vector\b" hagoku/` 只剩 `memory/_vector.py` 自身 |

---

## §5 与 collapse brief 的边界

| 由 collapse brief 负责 | 由本 brief 负责 |
|---------------------|--------------|
| Phase D 合并 4 agent.py 为 1 个 | Phase D 同步重组 memory 目录 |
| Phase B ProjectContext 升级 | 本 brief 不动 ProjectContext（它管 run 内 chat，与 ③ 项目级持久化分工） |
| Phase E 工具注册表扩张 | 本 brief 加 8 个 memory 工具 |
| Phase F 律的减法 | 本 brief 不产生律 |

---

## §6 风险

| 风险 | 缓解 |
|------|------|
| 用户已有项目数据（`~/.hagoku/projects/<name>/memory.db`）迁移失败 | CO-D6.4 必须包含迁移脚本 + 旧版本回退路径 |
| 4 份 `knowledge.py` 删后某个 agent 调用方还在引用 | Phase D 合并 agent 时同步删调用方；`grep -rn "from .knowledge"` 守门 |
| ② 层 lesson 污染失控 | `LessonAuditor` Agent 周期审核（见 Meta v2 brief） |
| LLM 在 ③ 层污染（误存了不应跨 run 持久化的瞬时状态）| Phase E 测试覆盖 + LessonAuditor 顺带监控（v2 brief 设计） |

---

## §7 不做什么

- 不做向量库切换（继续用 chroma / faiss / 现有实现，看 `knowledge_vector.py` 现实）
- 不做 RAG 链路重构（① 层就是简单检索 + 让 LLM 决定要不要细读）
- 不做 lesson 自动生成（LLM 自己决定何时 save_lesson；不靠 code 自动归纳）
- 不做"业务/金融/学术"原三层结构的保留——业务知识属 ② / ③，学术 ① 不掺杂业务
