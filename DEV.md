# HaGoKu — 开发文档

## 概述

本文档是 HaGoKu 项目的开发指南，从 PROJECT.md 的设计规格出发，拆解为可执行的开发任务、技术实现细节和开发规范。

项目愿景详见 [PROJECT.md](PROJECT.md)

---

## 开发环境

### 前置条件

- Python 3.10+
- Git
- 本地 LLM 服务（llama.cpp / Ollama / vLLM，OpenAI 兼容 API）

### 环境搭建

```bash
# 克隆项目
git clone https://github.com/yourname/hagokyu.git
cd hagokyu

# 创建虚拟环境
python -m venv .venv
source .venv/bin/activate

# 安装开发依赖
pip install -e ".[dev]"

# 复制配置模板
cp .env.example .env

# 运行测试
pytest tests/ -q
```

### 依赖分组

```toml
# pyproject.toml [project.dependencies]
# 核心
crewai >= 0.100.0
pydantic >= 2.0
click >= 8.0
instructor >= 1.0

# 数据
pandas >= 2.0
duckdb >= 1.0
pyarrow >= 14.0
openpyxl              # Excel 读取
pypdf                 # PDF 读取
python-docx           # Word 读取

# 统计
pingouin >= 0.5
statsmodels >= 0.14
scipy >= 1.12

# 机器学习
scikit-learn >= 1.4
flaml >= 2.0

# 清洗与验证
pyod >= 1.1
cleanlab >= 2.0
great-expectations >= 1.0

# 画像
ydata-profiling >= 4.0
missingno >= 0.5

# 可视化
plotly >= 5.0
matplotlib >= 3.8

# 报告
jinja2 >= 3.1

# [project.optional-dependencies.dev]
pytest >= 8.0
pytest-cov
ruff
mypy
```

---

## 架构总览

```
┌─────────────────────────────────────────────────┐
│  CLI (Click) / Web UI (Streamlit V2)            │
├─────────────────────────────────────────────────┤
│  Orchestrator                                    │
│  ┌───────────┐  调度  ┌──────────┐              │
│  │  Manager  │──────→│  Agents  │              │
│  │ (规则+AI) │←──────│  4+1个   │              │
│  └───────────┘  结果  └──────────┘              │
├─────────────────────────────────────────────────┤
│  Tools Layer (12 组借力组件)                      │
│  Pingouin | Statsmodels | PyOD | ydata-profiling │
│  sklearn | FLAML | Jinja2 | Great Expectations   │
├─────────────────────────────────────────────────┤
│  Infrastructure                                  │
│  EventBus | DataStore | Guardrails | LLM Adapter │
│  SQLite DB | Output Manager | Lineage Tracker    │
└─────────────────────────────────────────────────┘
```

---

## 模块开发指南

### 模块 1: 基础设施层（最先开发）

#### 1.1 config.py — 全局配置

```python
from pydantic import BaseModel
from pathlib import Path

class LLMConfig(BaseModel):
    base_url: str = "http://localhost:8000/v1"
    api_key: str = "none"
    model: str = "Qwen3.6-35B-A3B"
    temperature: float = 0.6
    max_tokens: int = 8192
    top_p: float = 0.95
    top_k: int = 20

class ManagerConfig(BaseModel):
    mode: str = "local_weak"  # local_weak / local_strong / cloud / pure_rule
    rule_weight: float = 0.9
    llm_weight: float = 0.1

class OutputConfig(BaseModel):
    base_dir: Path = Path.home() / ".hagokyu" / "projects"
    naming: str = "{project}/report_{date}"
    date_format: str = "%Y%m%d"
    formats: list[str] = ["html"]
    auto_archive: bool = True
    keep_latest_n: int = 10

class HaGoKuConfig(BaseModel):
    llm: LLMConfig = LLMConfig()
    manager: ManagerConfig = ManagerConfig()
    output: OutputConfig = OutputConfig()
    work_dir: Path = Path.home() / ".hagokyu"
```

**开发要点**：
- 从 `~/.hagokyu/config.yaml` 加载配置，不存在则用默认值
- 支持环境变量覆盖（`HAGOKYU_LLM_BASE_URL` 等）
- 配置变更不需重启（热加载）

#### 1.2 storage/ — 数据持久化

**开发顺序**：database.py → artifact.py → project.py → output.py → lineage.py → sources.py

**database.py** — SQLite 元数据库

```python
import sqlite3
from pathlib import Path

class HaGoKuDB:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.conn = sqlite3.connect(str(db_path))
        self._init_tables()

    def _init_tables(self):
        """建表，见 PROJECT.md 数据库表结构"""
        ...

    def create_project(self, project_id: str, description: str, data_path: str, schema_path: str): ...
    def create_run(self, run_id: str, project_id: str, query: str, plan: dict, manager_mode: str): ...
    def save_finding(self, finding: dict): ...
    def save_artifact(self, artifact: dict): ...
    def get_findings(self, project_id: str, filters: dict = None) -> list[dict]: ...
    def get_run_history(self, project_id: str) -> list[dict]: ...
    def diff_runs(self, run_id_1: str, run_id_2: str) -> dict: ...
```

**开发要点**：
- 使用 Python 内置 `sqlite3`，不引入 ORM
- 所有 SQL 语句集中管理，不散落在业务代码中
- 事务保证：一次运行的所有 findings 要么全存要么全不存
- 连接池：单例模式，全局一个连接

#### 1.3 observability/ — 事件系统

**events.py** — 事件定义

```python
from enum import Enum
from dataclasses import dataclass, field
from datetime import datetime

class EventType(Enum):
    # Manager
    PLAN_CREATED = "plan_created"
    TASK_ASSIGNED = "task_assigned"
    QUALITY_CHECK = "quality_check"
    MODE_SWITCHED = "mode_switched"

    # Agent
    AGENT_STARTED = "agent_started"
    AGENT_THINKING = "agent_thinking"
    AGENT_COMPLETED = "agent_completed"
    AGENT_FAILED = "agent_failed"

    # Tool
    TOOL_CALLED = "tool_called"
    TOOL_RESULT = "tool_result"
    TOOL_ERROR = "tool_error"

    # Data
    DATA_PASSED = "data_passed"
    DATA_ARTIFACT_CREATED = "data_artifact_created"

    # User
    USER_INPUT_REQUESTED = "user_input_requested"
    USER_INPUT_RECEIVED = "user_input_received"

@dataclass
class Event:
    event_id: str
    event_type: EventType
    timestamp: datetime
    agent: str
    data: dict = field(default_factory=dict)
    parent_id: str | None = None
```

**event_bus.py** — 事件总线

```python
class EventBus:
    def __init__(self):
        self.events: list[Event] = []
        self.subscribers: list[callable] = []

    def emit(self, event: Event): ...
    def subscribe(self, callback: callable): ...
    def get_timeline(self) -> list[Event]: ...
    def get_agent_trace(self, agent: str) -> list[Event]: ...
    def get_tool_trace(self, agent: str) -> list[Event]: ...
    def save_to_file(self, path: Path): ...   # events.jsonl
    def load_from_file(self, path: Path): ...  # 用于 replay
```

**display.py** — 终端实时显示

```python
class TerminalDisplay:
    """订阅 EventBus，实时打印到终端"""

    COLORS = {
        "manager": "\033[35m",  # 紫
        "scout":   "\033[36m",  # 青
        "cleaner": "\033[33m",  # 黄
        "analyst": "\033[34m",  # 蓝
        "reporter":"\033[32m",  # 绿
    }

    def __call__(self, event: Event):
        """EventBus 回调，格式化输出"""
        ...
```

#### 1.4 guardrails/ — 统计护栏

**开发顺序**：statistical.py → mandatory.py → warnings.py → suggestions.py

**statistical.py** — 护栏核心

```python
from enum import Enum
from pydantic import BaseModel

class Severity(Enum):
    MANDATORY = "mandatory"    # 阻止输出
    WARNING = "warning"        # 标注警告
    SUGGESTION = "suggestion"  # 建议

class GuardrailResult(BaseModel):
    rule: str
    severity: Severity
    passed: bool
    message: str
    suggestion: str | None = None

class StatisticalGuardrails:
    def __init__(self, config: dict):
        self.mandatory_rules = [...]
        self.warning_rules = [...]
        self.suggestion_rules = [...]

    def check(self, analysis_result: dict) -> list[GuardrailResult]:
        """检查分析结果，返回所有违规"""
        results = []
        for rule in self.mandatory_rules + self.warning_rules + self.suggestion_rules:
            result = rule.check(analysis_result)
            results.append(result)
        return results

    def can_output(self, results: list[GuardrailResult]) -> bool:
        """是否有强制级违规阻止输出"""
        return not any(r.severity == Severity.MANDATORY and not r.passed for r in results)
```

**mandatory.py** — 强制级规则示例

```python
class NoConclusionWithoutTest:
    """没有统计检验不许下结论"""

    def check(self, analysis_result: dict) -> GuardrailResult:
        has_conclusion = bool(analysis_result.get("conclusion_plain"))
        has_test = analysis_result.get("p_value") is not None
        return GuardrailResult(
            rule="no_conclusion_without_test",
            severity=Severity.MANDATORY,
            passed=not has_conclusion or has_test,
            message="结论缺少统计检验支撑" if has_conclusion and not has_test else "",
        )
```

---

### 模块 2: 工具层

#### 2.1 tools/data_io.py — 数据加载

```python
import pandas as pd
import duckdb

def load_data(path: str, **kwargs) -> pd.DataFrame:
    """统一入口，根据扩展名自动选择加载方式"""
    ext = Path(path).suffix.lower()
    loaders = {
        ".csv": lambda: pd.read_csv(path, **kwargs),
        ".xlsx": lambda: pd.read_excel(path, **kwargs),
        ".json": lambda: pd.read_json(path, **kwargs),
        ".parquet": lambda: pd.read_parquet(path, **kwargs),
    }
    if ext not in loaders:
        raise ValueError(f"不支持的文件格式: {ext}")
    return loaders[ext]()
```

#### 2.2 tools/profiling.py — 数据画像

```python
from ydata_profiling import ProfileReport

def generate_profile(df: pd.DataFrame, minimal: bool = True) -> dict:
    """生成数据画像，返回结构化结果（不是 HTML）"""
    profile = ProfileReport(df, minimal=minimal, explorative=False)
    # 提取关键信息为结构化 dict
    return {
        "n_rows": len(df),
        "n_cols": len(df.columns),
        "columns": {col: _extract_column_stats(df[col]) for col in df.columns},
        "missing_summary": df.isnull().sum().to_dict(),
        "duplicate_rate": df.duplicated().mean(),
        "correlations": _extract_correlations(df),
    }
```

#### 2.3 tools/analysis.py — 统计分析核心

```python
import pingouin as pg
import statsmodels.api as sm

def ttest(group1, group2, paired=False) -> dict:
    """t 检验，自动报告效应量"""
    result = pg.ttest(group1, group2, paired=paired)
    return {
        "test": "ttest",
        "statistic": result["T"].iloc[0],
        "p_value": result["p-val"].iloc[0],
        "effect_size": result["cohen-d"].iloc[0],
        "effect_type": "cohen_d",
        "ci": result["CI95%"].iloc[0],
        "assumptions_met": _check_ttest_assumptions(group1, group2),
    }

def regression(df, target, features, method="ols") -> dict:
    """回归分析，自动诊断"""
    if method == "ols":
        model = sm.OLS(df[target], sm.add_constant(df[features])).fit()
    elif method == "robust":
        model = sm.RLM(df[target], sm.add_constant(df[features])).fit()

    # 自动诊断
    diagnostics = _run_diagnostics(model, df, target, features)

    return {
        "test": "regression",
        "r_squared": model.rsquared,
        "adj_r_squared": model.rsquared_adj,
        "f_statistic": model.fvalue,
        "f_pvalue": model.f_pvalue,
        "coefficients": dict(model.params),
        "ci": dict(model.conf_int()),
        "p_values": dict(model.pvalues),
        "effect_size": _compute_f_squared(model),
        "diagnostics": diagnostics,
    }
```

**开发要点**：
- 每个工具函数返回标准化的 dict，用 Pydantic 模型校验
- 优先用 Pingouin（自带效应量），需要深度诊断时用 Statsmodels
- 所有工具函数独立可测，不依赖 Agent 框架

---

### 模块 3: Agent 层

#### 3.1 agents/base.py — DataAgent 基类

```python
from crewai import Agent
from pydantic import BaseModel

class DataAgentBase(Agent):
    """HaGoKu 的 Agent 基类，扩展 CrewAI Agent"""

    def __init__(self, role: str, goal: str, backstory: str,
                 tools: list, llm_config: dict, event_bus: EventBus, **kwargs):
        super().__init__(
            role=role, goal=goal, backstory=backstory,
            tools=tools, llm=self._create_llm(llm_config), **kwargs
        )
        self.event_bus = event_bus

    def _create_llm(self, config: dict):
        """创建 CrewAI 兼容的 LLM"""
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            base_url=config["base_url"],
            model=config["model"],
            api_key=config["api_key"],
            temperature=config["temperature"],
        )

    def emit_event(self, event_type: EventType, data: dict):
        self.event_bus.emit(Event(
            event_id=uuid4().hex[:8],
            event_type=event_type,
            timestamp=datetime.now(),
            agent=self.role,
            data=data,
        ))
```

#### 3.2 agents/scout.py — 语义推断核心

```python
class ScoutAgent(DataAgentBase):
    def __init__(self, llm_config, event_bus):
        super().__init__(
            role="Scout",
            goal="理解数据上下文，不猜，问",
            backstory="你是数据侦察员...",
            tools=[load_data, generate_profile, infer_semantics, assess_quality],
            llm_config=llm_config,
            event_bus=event_bus,
        )

def infer_semantics(df: pd.DataFrame) -> list[ColumnSemantic]:
    """推断列语义，标注置信度"""
    results = []
    for col in df.columns:
        semantic = _infer_column(df[col], col)
        results.append(semantic)
    return results

def _infer_column(series: pd.Series, name: str) -> ColumnSemantic:
    """单列语义推断"""
    n_unique = series.nunique()
    n_total = len(series)

    # 100% 唯一 → ID
    if n_unique == n_total:
        return ColumnSemantic(column_name=name, inferred_type=SemanticType.ID,
                             confidence=0.95, evidence="100%唯一值", needs_user_input=False)

    # 日期推断
    if pd.api.types.is_datetime64_any_dtype(series):
        return ColumnSemantic(column_name=name, inferred_type=SemanticType.DATETIME,
                             confidence=0.95, evidence="日期类型", needs_user_input=False)

    # 布尔
    if n_unique == 2:
        return ColumnSemantic(column_name=name, inferred_type=SemanticType.BOOLEAN,
                             confidence=0.85, evidence="2个唯一值", needs_user_input=False)

    # 数值
    if pd.api.types.is_numeric_dtype(series):
        # 名字暗示是目标变量
        if any(kw in name.lower() for kw in ["target", "y", "label", "revenue", "sales", "income"]):
            return ColumnSemantic(column_name=name, inferred_type=SemanticType.TARGET,
                                 confidence=0.50, evidence=f"列名含目标关键词", needs_user_input=True)
        return ColumnSemantic(column_name=name, inferred_type=SemanticType.NUMERIC,
                             confidence=0.90, evidence="数值类型", needs_user_input=False)

    # 类别/有序
    if n_unique < 20:
        if any(kw in name.lower() for kw in ["score", "rating", "level", "grade"]):
            return ColumnSemantic(column_name=name, inferred_type=SemanticType.ORDINAL,
                                 confidence=0.50, evidence="列名暗示有序", needs_user_input=True)
        return ColumnSemantic(column_name=name, inferred_type=SemanticType.CATEGORICAL,
                             confidence=0.70, evidence=f"{n_unique}个唯一值", needs_user_input=True)

    # 完全看不懂
    return ColumnSemantic(column_name=name, inferred_type=SemanticType.UNKNOWN,
                         confidence=0.0, evidence="无法推断", needs_user_input=True)
```

---

### 模块 4: 编排层

#### 4.1 manager/rule_engine.py — 规则引擎

```python
class RuleEngine:
    """Manager 的规则引擎，覆盖 80% 常见决策"""

    PLAN_TEMPLATES = {
        "趋势分析": {"agents": ["scout", "cleaner", "analyst", "reporter"],
                     "analyst_focus": ["time_series", "trend"]},
        "差异比较": {"agents": ["scout", "cleaner", "analyst", "reporter"],
                     "analyst_focus": ["hypothesis_test", "effect_size"]},
        "因果推断": {"agents": ["scout", "cleaner", "analyst", "reporter"],
                     "analyst_focus": ["regression", "causal"]},
        "数据画像": {"agents": ["scout", "reporter"],
                     "analyst_focus": []},
    }

    KEYWORD_MAP = {
        "趋势|变化|增长|下降|走势": "趋势分析",
        "差异|对比|比较|不同|A/B": "差异比较",
        "因果|影响|导致|因为|效果": "因果推断",
        "画像|概况|什么数据|什么样": "数据画像",
    }

    def match_plan(self, query: str) -> dict | None:
        """关键词匹配计划模板"""
        for pattern, plan_name in self.KEYWORD_MAP.items():
            if re.search(pattern, query):
                return self.PLAN_TEMPLATES[plan_name]
        return None  # 匹配不到，交给 AI
```

#### 4.2 orchestrator.py — 编排器

```python
class Orchestrator:
    def __init__(self, config: HaGoKuConfig):
        self.config = config
        self.event_bus = EventBus()
        self.db = HaGoKuDB(config.work_dir / "hagokyu.db")
        self.display = TerminalDisplay()
        self.event_bus.subscribe(self.display)

    def run(self, data_path: str, query: str, mode: str = "standard", **kwargs):
        """主入口"""
        # 1. 创建项目/运行记录
        project_id = self._resolve_project(data_path)
        run_id = self._create_run_id()

        # 2. 初始化 Manager
        manager = ManagerAgent(self.config, self.event_bus)

        # 3. 生成分析计划
        plan = manager.create_plan(query, mode=mode)

        # 4. 按计划执行 Agent 流水线
        context = None
        cleaned_data = None
        results = []

        if "scout" in plan.agents:
            scout = ScoutAgent(self.config.llm, self.event_bus)
            context = scout.execute(data_path, mode=mode)

        if "cleaner" in plan.agents:
            cleaner = CleanerAgent(self.config.llm, self.event_bus)
            cleaned_data = cleaner.execute(context, mode=mode)

        if "analyst" in plan.agents:
            analyst = AnalystAgent(self.config.llm, self.event_bus)
            results = analyst.execute(cleaned_data or context, plan, mode=mode)

        if "reporter" in plan.agents:
            reporter = ReporterAgent(self.config.llm, self.event_bus)
            report = reporter.execute(results, mode=mode, **kwargs)

        # 5. 保存结果
        self._save_run(run_id, project_id, results, report)

        return report
```

---

### 模块 5: CLI

```python
import click

@click.group()
def cli():
    """HaGoKu — 用数学挖掘数据背后的真相"""
    pass

@cli.command()
@click.argument("data_path")
@click.option("--output", "-o", default="html", type=click.Choice(["html", "pdf", "markdown"]))
def quick(data_path, output):
    """⚡ 快速模式：扔数据，拿结果"""
    orchestrator = Orchestrator(load_config())
    report = orchestrator.run(data_path, query="", mode="quick", output_format=output)
    click.echo(f"\n📄 报告: {report.path}")

@cli.command()
@click.argument("data_path")
@click.option("--query", "-q", required=True, help="分析问题")
@click.option("--mode", "-m", default="standard", type=click.Choice(["quick", "standard", "expert"]))
@click.option("--template", "-t", default="business_analysis")
@click.option("--output", "-o", default="html")
@click.option("--detail", default="standard", type=click.Choice(["brief", "standard", "full"]))
@click.option("--math", "math_level", default="mixed", type=click.Choice(["plain", "mixed", "rigorous"]))
@click.option("--output-dir", default=None)
@click.option("--output-name", default=None)
@click.option("--manager-mode", default=None, type=click.Choice(["local_weak", "local_strong", "cloud", "pure_rule"]))
@click.option("--schema", "schema_path", default=None, help="字段语义定义文件")
@click.option("--skip-clean", is_flag=True)
@click.option("--resume", is_flag=True)
def run(data_path, query, mode, template, output, detail, math_level,
        output_dir, output_name, manager_mode, schema_path, skip_clean, resume):
    """📋 运行分析"""
    ...

@cli.command()
@click.option("--project", "-p", required=True)
def history(project):
    """查看历史分析"""
    ...

@cli.command()
@click.option("--run", "run_id", required=True)
def replay(run_id):
    """回放分析过程"""
    ...
```

---

## 开发计划 — MVP 分步实施

### Phase 1: 基础设施（预计 3 天）

| 步骤 | 任务 | 产出 | 验证 |
|------|------|------|------|
| 1.1 | 项目脚手架 + pyproject.toml | 可安装的空包 | `pip install -e .` 成功 |
| 1.2 | config.py | 配置加载 | 单测通过 |
| 1.3 | events.py + event_bus.py | 事件系统 | emit/subscribe 单测 |
| 1.4 | display.py | 终端输出 | 手动验证：打印彩色事件 |
| 1.5 | database.py | SQLite 元数据库 | CRUD 单测 |
| 1.6 | artifact.py + output.py | 数据制品管理 | 读写 Parquet 单测 |

### Phase 2: 工具层（预计 5 天）

| 步骤 | 任务 | 产出 | 验证 |
|------|------|------|------|
| 2.1 | data_io.py | 数据加载 | CSV/Excel/Parquet 加载单测 |
| 2.2 | profiling.py | 数据画像 | 生成画像单测 |
| 2.3 | cleaning.py | 清洗工具 | 缺失填补 + 异常检测单测 |
| 2.4 | analysis.py | 统计分析核心 | t 检验 + 回归单测（用真实数据） |
| 2.5 | diagnostics.py | 模型诊断 | VIF + 残差诊断单测 |
| 2.6 | visualization.py | 可视化 | 生成图表单测 |
| 2.7 | reporting.py | 报告渲染 | Jinja2 模板渲染单测 |

### Phase 3: Agent 层（预计 5 天）

| 步骤 | 任务 | 产出 | 验证 |
|------|------|------|------|
| 3.1 | base.py | DataAgent 基类 | 初始化 + LLM 连接单测 |
| 3.2 | scout.py | Scout Agent | 语义推断单测 + 字段确认交互测试 |
| 3.3 | cleaner.py | Cleaner Agent | 清洗 + 影响评估集成测试 |
| 3.4 | analyst.py | Analyst Agent | 回归分析集成测试 |
| 3.5 | reporter.py | Reporter Agent | 报告生成集成测试 |
| 3.6 | manager.py | Manager Agent | 计划生成 + 调度测试 |

### Phase 4: 编排 + CLI（预计 3 天）

| 步骤 | 任务 | 产出 | 验证 |
|------|------|------|------|
| 4.1 | orchestrator.py | 编排器 | 端到端流水线测试 |
| 4.2 | cli.py | CLI 入口 | `hagokyu quick` 手动测试 |
| 4.3 | guardrails | 统计护栏 | 无检验结论被阻止 |
| 4.4 | 端到端测试 | 完整示例 | `hagokyu quick sales.csv` 出报告 |

### Phase 5: 打磨（预计 2 天）

| 步骤 | 任务 | 产出 | 验证 |
|------|------|------|------|
| 5.1 | 错误处理 + 边界情况 | 健壮性 | 异常数据不崩溃 |
| 5.2 | 报告模板 (3个) | 模板库 | 3 种模板出报告 |
| 5.3 | README 完善 | 文档 | 新人能跑起来 |
| 5.4 | examples/ | 示例 | 广告效果分析示例 |

**MVP 总计：约 18 天**

---

## 开发规范

### 代码风格

- 格式化：`ruff format`
- 检查：`ruff check`
- 类型：`mypy src/`（逐步加类型标注）
- 命名：函数/变量 snake_case，类 PascalCase，常量 UPPER_SNAKE

### 提交规范

```
feat: 新功能
fix: 修 bug
refactor: 重构
docs: 文档
test: 测试
chore: 杂项
```

### 测试规范

- 每个工具函数必须有单元测试
- Agent 测试用 mock LLM，不依赖真实模型
- 端到端测试用小数据集（<100行）
- 统计分析测试用固定 seed，确保可复现
- `pytest tests/ -q` 全绿才能合并

### 目录规范

- 工具层代码不依赖 Agent 框架（可独立使用）
- Agent 层通过工具层操作数据，不直接 import pandas/scipy
- 配置通过 config.py 统一管理，不散落硬编码
- 事件总线贯穿全局，所有可观测行为必须发事件

---

## 关键技术决策记录

| 决策 | 选择 | 替代方案 | 理由 |
|------|------|----------|------|
| Agent 框架 | CrewAI | LangGraph, AutoGen | 角色分配模型最匹配 |
| 结构化输出 | Instructor + Pydantic | outlines, guidance | Pydantic 生态最成熟 |
| 统计核心 | Pingouin 优先 | 纯 Statsmodels | 自带效应量，API 简洁 |
| 元数据库 | SQLite | PostgreSQL, 纯文件 | 零配置，本地优先 |
| 数据传递 | Parquet | 内存 DataFrame, JSON | 压缩 + 类型 + 大数据集友好 |
| 代码执行 | subprocess + 白名单 | E2B, Docker | 本地优先，无外部依赖 |
| 报告模板 | Jinja2 | 纯代码生成 | 用户可自定义模板 |
| CLI 框架 | Click | Typer, argparse | 生态成熟，装饰器风格清晰 |

---

## 风险与缓解

| 风险 | 影响 | 缓解 |
|------|------|------|
| 本地 LLM 工具调用不稳定 | Agent 执行失败 | Pydantic 校验 + 重试 + 退化为文本解析 |
| CrewAI API 变更 | 编排层不兼容 | 锁版本，关键逻辑不依赖内部 API |
| 统计分析结果不准确 | 核心价值受损 | Guardrails 强制校验 + 人工抽检 |
| 本地模型速度慢 | 用户体验差 | 限制 max_iter=5，控制输出长度 |
| Parquet 文件过大 | 磁盘占满 | 自动压缩 + 清理策略 + 保留 N 份 |

---

## 参考

- [PROJECT.md](PROJECT.md) — 完整项目设计规格
- [CrewAI 文档](https://docs.crewai.com/)
- [Pingouin 文档](https://pingouin-stats.org/)
- [Instructor 文档](https://python.useinstructor.com/)
- [Statsmodels 文档](https://www.statsmodels.org/)
