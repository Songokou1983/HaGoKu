# Agents 代码完整审计报告

> 审计时间: 2026-05-23
> 审计范围: `hagoku/agents/` 下全部 Agent 实现及其交叉引用链路
> 审计方法: 全项目 `import` 扫描 + 逐文件对比

## 一、文件清单

### 扁平 `.py` 文件（顶层）

| 文件 | 行数 | 包含的类/定义 |
|------|------|-------------|
| `scout.py` | 649 | `ScoutAgent(DataAgentBase)`, `COMMON_COLUMN_ALIASES`, `SemanticType`, `DataContext` |
| `analyst.py` | 1373 | `AnalystAgent(DataAgentBase)`, `AnalysisResult` |
| `cleaner.py` | 326 | `CleanerAgent(DataAgentBase)` |
| `reporter.py` | 10 | 桥接文件：`from .reporter.agent import ReporterAgent` |
| `base.py` | — | `DataAgentBase` |
| `types.py` | — | `ColumnSemantic`, `DataContext`, `SemanticType`, `InteractionResult` |
| `_interactive.py` | 71 | `InteractionMixin` |
| `constants.py` | — | 常量定义 |

### 目录结构

| 目录 | 包含文件 |
|------|---------|
| `_scribe/` | `agent.py`, `prompt.md`, `process_log.md`, `__init__.py` |
| `reporter/` | `agent.py`, `prompt.md`, `memory.md`, `knowledge.py`, `knowledge.yaml`, `__init__.py` |
| `scout/` | `agent.py`, `prompt.md`, `memory.md`, `knowledge.py`, `knowledge.yaml`, `knowledge.db`, `__init__.py` |
| `analyst/` | `agent.py`, `prompt.md`, `memory.md`, `knowledge.py`, `knowledge.yaml`, `knowledge.db`, `__init__.py` |
| `cleaner/` | `agent.py`, `prompt.md`, `memory.md`, `knowledge.py`, `knowledge.yaml`, `knowledge.db`, `__init__.py` |

## 二、运行时引用链路（精确到行号）

### 2.1 orchestrator.py（主编排器）

```
orchestrator.py:12  →  from ..agents.analyst import AnalystAgent    →  hagoku/agents/analyst.py（扁平文件）
orchestrator.py:13  →  from ..agents.cleaner import CleanerAgent    →  hagoku/agents/cleaner.py（扁平文件）
orchestrator.py:14  →  from ..agents.reporter import ReporterAgent  →  hagoku/agents/reporter.py → reporter/agent.py（桥接）
orchestrator.py:15  →  from ..agents.scout import ScoutAgent        →  hagoku/agents/scout.py（扁平文件）
orchestrator.py:98  →  from ..agents.scout.agent import _description_is_user_facing_meaningful  →  hagoku/agents/scout/agent.py（包版本）
```

### 2.2 agents/__init__.py（包重导出）

```
__init__.py:4   →  from .analyst import AnalysisResult, AnalystAgent   →  analyst.py
__init__.py:8   →  from .cleaner import CleanerAgent                    →  cleaner.py
__init__.py:9   →  from .reporter import ReporterAgent                  →  reporter.py
__init__.py:12  →  from .scout import ScoutAgent                        →  scout.py
```

### 2.3 Agents 模块外部对 agents 的 import（非 orchestrator、非 __init__）

```
analyst.py:9           →  from ._scribe.agent import ScribeAgent (TYPE_CHECKING)  →  _scribe/agent.py
analyst.py:35          →  from ._interactive import InteractionMixin              →  _interactive.py
analyst.py:37          →  from .scout import DataContext, SemanticType             →  scout.py
analyst.py:38          →  from .types import InteractionResult                     →  types.py
cleaner.py:23          →  from .scout import DataContext                           →  scout.py
storage/memory.py:484  →  from ..agents.scout import SemanticType                 →  scout.py
```

### 2.4 目录下 agent.py 的 import

```
scout/agent.py:19   →  from . import knowledge as scout_knowledge           →  scout/knowledge.py
scout/agent.py:26   →  from .._interactive import InteractionMixin           →  _interactive.py
scout/agent.py:27   →  from ..types import InteractionResult                →  types.py
analyst/agent.py:39 →  from . import knowledge as analyst_knowledge         →  analyst/knowledge.py
analyst/agent.py:37 →  from .._interactive import InteractionMixin           →  _interactive.py
analyst/agent.py:38 →  from ..types import InteractionResult                →  types.py
cleaner/agent.py:36 →  from . import knowledge as cleaner_knowledge         →  cleaner/knowledge.py
cleaner/agent.py:35 →  from .._interactive import InteractionMixin           →  _interactive.py
```

目录下的 `agent.py` 均引用扁平的 `_interactive.py`（`InteractionMixin`）和 `types.py`（`InteractionResult`），但不引用扁平 Agent 文件（`scout.py`、`analyst.py`、`cleaner.py`）。

## 三、各 Agent 类的差异

### Scout

| 属性 | `scout.py` | `scout/agent.py` |
|------|-----------|-----------------|
| 继承 | `DataAgentBase` | `InteractionMixin` |
| prompt 来源 | 硬编码在 `__init__` 中 | 从文件 `prompt.md` 加载 |
| memory 来源 | 通过 `DataAgentBase` | 从文件 `memory.md` YAML 加载 |
| 入口方法 | `classify_query()` | `begin()` / `respond()` / `run()` |
| 提供给 orchestrator | `ScoutAgent` 类 | `_description_is_user_facing_meaningful` 函数 |

### Analyst

| 属性 | `analyst.py` | `analyst/agent.py` |
|------|-------------|-------------------|
| 继承 | `DataAgentBase` | `InteractionMixin` |
| prompt 来源 | 硬编码在 `__init__` 中 | 从文件 `prompt.md` 加载 |
| 入口方法 | LLM 调用 | `begin()` / `respond()` |
| 知识库 | 无 | `knowledge.py` + `knowledge.yaml` |

### Cleaner

| 属性 | `cleaner.py` | `cleaner/agent.py` |
|------|-------------|-------------------|
| 继承 | `DataAgentBase` | `InteractionMixin` |
| prompt 来源 | 硬编码在 `__init__` 中 | 从文件 `prompt.md` 加载 |
| 入口方法 | LLM 调用 | `begin()` / `respond()` |
| 知识库 | 无 | `knowledge.py` + `knowledge.yaml` |

## 四、结论

1. **运行时使用 5 个 Agent**：Scout、Analyst、Cleaner、Reporter、Scribe
2. **Scout**：`scout.py` 提供 `ScoutAgent` 类，`scout/agent.py` 提供工具函数 `_description_is_user_facing_meaningful`，两个文件同时被引用，互补使用
3. **Analyst**：运行时仅使用 `analyst.py`
4. **Cleaner**：运行时仅使用 `cleaner.py`
5. **Reporter**：通过 `reporter.py` 桥接到 `reporter/agent.py`
6. **Scribe**：直接使用 `_scribe/agent.py`
7. **`analyst/agent.py` 和 `cleaner/agent.py`**：存在于目录中但当前未被任何运行时代码 import。它们各自是 `InteractionMixin` 子类，引入了一套 `begin()/respond()` 交互接口和 `prompt.md`/`memory.md`/`knowledge.yaml` 文件驱动机制
8. **所有文件均不应对其进行删除操作**——每个文件都有其存在的理由（运行中 / 辅助功能 / 可能的后续迁移用途）