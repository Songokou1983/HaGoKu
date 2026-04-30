# HaGoKu

**专注数据分析的多 Agent 协作软件**

HaGoKu 是一个基于多 Agent 协作的数据分析平台，将数据分析全流程拆分为专业角色，由 AI 驱动自动完成——从数据查询、清洗、分析到专业报告生成。

## 核心理念

- **角色分工**：每个 Agent 专注一个领域，做得少但做得精
- **总管调度**：Manager 统一规划、分配、质检，权重可调
- **模板驱动呈现**：AI 管内容，模板管呈现，报告专业美观
- **全程透明**：用户坐在副驾驶位，实时看到每一步执行过程
- **数据不出本机**：纯本地 LLM 驱动，机密数据零外泄

## 四个专业 Agent

| Agent | 角色 | 职责 |
|-------|------|------|
| **Scout** (侦察员) | 查询数据与知识 | 加载文件、SQL查询、文档解析、知识检索 |
| **Cleaner** (清洁工) | 数据清洗 | 缺失值处理、异常值检测、标准化、数据画像 |
| **Analyst** (分析师) | 数理分析 | 回归分析、假设检验、相关性、时序分析、ML建模 |
| **Reporter** (报告员) | 专业汇报 | 图表生成、格式化表格、报告渲染与导出 |

## Manager（总管）

统一调度 4 个 Agent，权重可调节：

| 模式 | 规则权重 | AI权重 | 适用场景 |
|------|----------|--------|----------|
| `local_weak` | 90% | 10% | 本地轻量模型（默认） |
| `local_strong` | 50% | 50% | 本地强模型 |
| `cloud` | 10% | 90% | 云端强模型 |
| `pure_rule` | 100% | 0% | 纯规则，零AI开销 |

## 架构

```
用户查询 (CLI / Web UI)
    │
    ▼
┌─────────────────────────────────────────┐
│  Manager（总管）                         │
│  规则引擎 + AI · 权重可调                 │
├─────────────────────────────────────────┤
│  Scout → Cleaner → Analyst → Reporter   │
│  (查询)    (清洗)    (分析)    (报告)     │
├─────────────────────────────────────────┤
│  EventBus（可观测性）                     │
│  工作流 / 协作流 / 工具流 / 数据流        │
├─────────────────────────────────────────┤
│  Template Engine（呈现层）               │
│  报告模板 + 图表主题 + 格式导出           │
├─────────────────────────────────────────┤
│  DataStore（数据层）                     │
│  Parquet 制品 + 元数据 + 血缘追踪        │
└─────────────────────────────────────────┘
```

## 快速开始

```bash
# 安装
pip install -e .

# 基本用法
hagokyu run --data sales.csv --query "分析季度销售趋势"

# 指定输出格式
hagokyu run --data data.xlsx --output html --query "各区域销售对比"

# 跳过清洗
hagokyu run --data clean.parquet --skip-clean --query "回归分析"

# 切换 Manager 模式
hagokyu run --data sales.csv --query "分析趋势" --manager-mode cloud

# 数据画像
hagokyu profile --data raw.csv

# 回看执行过程
hagokyu replay --agent analyst
```

## 可观测性

HaGoKu 让用户坐在副驾驶位，全程透明：

- **工作流**：全局进度、各 Agent 状态、耗时
- **协作流**：Agent 间交互、Manager 调度决策
- **工具流**：每个工具的调用参数和返回结果
- **数据流**：数据在 Agent 间如何传递变换
- **执行报告**：每次运行的完整复盘

## 技术栈

- **Agent 框架**: CrewAI
- **本地 LLM**: Qwen3.6-35B-A3B (llama.cpp)
- **数据处理**: Pandas, DuckDB, PyArrow
- **统计分析**: Statsmodels, SciPy, Scikit-learn
- **可视化**: Plotly, Matplotlib
- **报告**: Jinja2, WeasyPrint
- **CLI**: Click
- **UI**: Streamlit
- **结构化输出**: Pydantic

## 项目状态

🚧 **立项阶段** — 架构设计中

## License

MIT
