<!-- TODO: 以 PROJECT.md 为基准全面对齐，产品完成后最终更新 -->

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
┌──────────────────────────────────────────────────────┐
│  CLI (Click) / Web UI (Streamlit V2)                 │
├──────────────────────────────────────────────────────┤
│  Orchestrator                                        │
│  ┌────────────┐  ┌──────────┐  ┌─────────────────┐  │
│  │  仲裁器     │  │  看板    │  │  QueryParser    │  │
│  │ (规则+LLM) │  │ (Kanban) │  │ (意图解析)      │  │
│  └─────┬──────┘  └────┬─────┘  └────────┬────────┘  │
│        │              │                  │           │
│        ▼              ▼                  ▼           │
│  ┌──────────────────────────────────────────────┐   │
│  │  Scribe (后台隐形引擎，零 LLM 开销)           │   │
│  │  看板状态 | 知识调度 | 经验记录 | 经验提炼     │   │
│  └──────────────────────────────────────────────┘   │
│        │              │                  │           │
│        ▼              ▼                  ▼           │
│  ┌──────────┐  ┌──────────┐  ┌──────────────────┐  │
│  │  Scout   │  │ Cleaner  │  │ Analyst │ Reporter│  │
│  └──────────┘  └──────────┘  └──────────────────┘  │
│  Agent 四件套: prompt.md + memory.md + knowledge.yaml + LLM自由通道  │
├──────────────────────────────────────────────────────┤
│  Tools Layer (12 组借力组件)                           │
│  Pingouin | Statsmodels | PyOD | ydata-profiling     │
│  sklearn | FLAML | Jinja2 | Great Expectations       │
├──────────────────────────────────────────────────────┤
│  Infrastructure                                      │
│  EventBus | DataStore | Guardrails | LLM Adapter     │
│  SQLite DB | Kanban | Output | Lineage | Knowledge   │
└──────────────────────────────────────────────────────┘
```

> **设计变更**：原"Manager 总管"已拆解。意图解析归 QueryParser+Scout，计划制定归规则引擎+LLM 微调，调度归 Scribe+看板，质量把关归 Guardrails，跨 Agent 仲裁归 Orchestrator 内仲裁逻辑。

---