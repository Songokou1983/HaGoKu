# HaGoKu

> **让每个小模型，都能做专业级商业分析。**

用数学的力量，挖出数据背后真正的信息。

HaGoKu 是一个多 Agent 协作的数据分析平台，由 4 个专业 Agent（Scout、Cleaner、Analyst、Reporter）和 Scribe 确定性引擎构成。每个结论必须附带 p 值 + 效应量 + 置信区间，受三级 Statistical Guardrails 规则兜底，由仲裁器（Arbitrator）统一编排调度。

---

## 核心能力

| 能力 | 说明 |
|------|------|
| 📈 统计检验 | t 检验、ANOVA、回归、相关，强制效应量+CI |
| 💰 商业分析 | ROI、ROAS、LTV、CAC、归因、漏斗 |
| ⚡ 功效分析 | 样本量评估、效应量解读 |
| 🛡️ 统计护栏 | 三级规则（强制/警告/提示），每个结论都有保障 |
| 🔌 插件架构 | 新增分析方法无需改核心代码 |
| 🧠 三层知识 | kb/领域知识 → 方法经验 → LLM 自由发挥，Agent 启动前自动注入 |

---

## 安装要求

- **Python**: 3.10+
- **后端 API**：`hagoku-api` 默认监听 **http://localhost:8000**（HaGoKu 的 HTTP/WebSocket，**不是** LLM 地址）。
- **LLM**：需要单独的 **OpenAI-compatible 推理服务**（如本地 vLLM / llama.cpp 代理等）。`~/.hagoku/.env` 中 `HAGOKYU_LLM_BASE_URL` 默认示例如 [`hagoku/config.py`](hagoku/config.py)、[`.env.example`](.env.example)（常见本机约定 `http://localhost:8080/v1`，**避免占用 8000** 以免与 `hagoku-api` 冲突）。

## 安装步骤

```bash
# 1. 克隆项目（以下 <repo-root> 为克隆后的仓库根目录，与 pyproject.toml、hagoku/、hagoku_web/ 同级）
git clone <repo-url>
cd <repo-root>

# 2. 创建虚拟环境（推荐）
python3 -m venv .venv
source .venv/bin/activate  # Linux/Mac
# .venv\Scripts\activate   # Windows

# 3. 安装
pip install -e .

# 4. 启动 LLM 服务（如本地部署 Qwen 等模型）

# 5. 启动后端 API
hagoku-api       # FastAPI 服务：http://localhost:8000

# 6. 启动前端（新终端）
cd hagoku_web && npm run dev   # React 开发服务器：http://localhost:5173
```

> ⚠️ **代码更新后**：执行 `pip install -e . --force-reinstall` 强制重装，使最新代码生效。

---

## 快速开始

### Web UI（推荐）

```bash
# 终端 1：启动后端
hagoku-api
# FastAPI 服务运行在 http://localhost:8000

# 终端 2：启动前端
cd hagoku_web && npm run dev
# React 开发服务器运行在 http://localhost:5173
```

**UI 功能：** 固定导航切换视图 → **项目**（卡片式项目库、描述与数据文件）→ **分析**（「开始分析」、流水线进度、Agent 对话气泡与暂停回复、WebSocket 实时事件）→ **报告**（按项目列出 HTML 等）→ **知识**（方法类知识库）→ **事件**（原始事件流）

### CLI

```bash
hagoku run data.csv --query "哪个广告渠道效果最好"


# 项目管理
hagoku project create "Q1销售分析" -d "分析Q1各渠道ROI"
hagoku project add "Q1销售分析" ~/data/sales.csv
hagoku project run "Q1销售分析" -q "哪个渠道roi最高"
```

---

## 主要命令

### 核心命令

| 命令 | 用途 |
|------|------|
| `hagoku run <file> -q "问题"` | 完整分析流程 |
| `hagoku demo` | 列出所有内置演示数据集 |
| `hagoku demo ad_campaign -q "问题"` | 用演示数据直接运行分析 |
| `hagoku profile <file>` | 生成数据画像 |

### 项目管理 (`hagoku project`)

| 命令 | 用途 |
|------|------|
| `hagoku project create <名称> -d "描述"` | 创建新项目 |
| `hagoku project add <项目> <文件>` | 添加数据文件到项目 |
| `hagoku project run <项目> -q "问题"` | 在项目上下文中运行分析 |
| `hagoku project list` | 列出所有项目 |
| `hagoku project info <项目>` | 查看项目详情 |
| `hagoku project delete <项目>` | 删除项目（需确认） |

### 诊断与工具

| 命令 | 用途 |
|------|------|
| `hagoku doctor` | 检查系统健康状态（LLM 连接、依赖库） |
| `hagoku methods` | 查看所有可用的分析方法 |
| `hagoku methods --tag statistical` | 按标签过滤分析方法 |
| `hagoku guardrails` | 查看统计护栏规则 |
| `hagoku config` | 查看当前配置 |
| `hagoku config --reset` | 重置配置为默认值 |

### 记忆与历史

| 命令 | 用途 |
|------|------|
| `hagoku memory` | 查看所有项目记忆概览 |
| `hagoku memory <项目>` | 查看指定项目的记忆 |
| `hagoku memory --export schema.yaml` | 导出记忆/列语义 |
| `hagoku memory --import schema.yaml` | 从 schema.yaml 导入记忆 |
| `hagoku history <项目>` | 查看项目运行历史 |
| `hagoku replay <run_id>` | 回放分析过程 |

### 高级选项 (`hagoku run`)

| 选项 | 说明 |
|------|------|
| `--demo ad_campaign` | 使用内置演示数据集 |
| `--format html --format md` | 输出格式（可多选） |
| `--template academic` | 报告模板（`default` 为双轨 HTML 默认；另有 business_analysis / academic / …） |
| `--interactive` | 交互模式：分析完后继续调整 |
| `--resume` | 从上次断点继续分析 |
| `--schema schema.yaml` | 外部 schema 文件路径 |
| `--verbosity verbose` | 详细终端输出 |

### Web UI

| 命令 | 用途 |
|------|------|
| `hagoku-api` | 启动后端 API（http://localhost:8000） |
| `cd hagoku_web && npm run dev` | 启动前端开发服务器（http://localhost:5173） |

---

## 系统架构

### 4 个 Agent + 1 个确定性引擎

| 角色 | 类型 | 职责 |
|------|------|------|
| 🔍 **Scout** | Agent | 加载数据、推断字段语义（SemanticType）、评估质量 |
| 🧹 **Cleaner** | Agent | MCAR/MNAR 检验、异常值区分、清洗影响评估 |
| 📊 **Analyst** | Agent | 回归/假设检验/ANOVA/相关，强制效应量+CI，自动非参数切换 |
| 📝 **Reporter** | Agent | 双轨输出（吸引力层+核心价值层），图表生成 |
| 📋 **Scribe** | 确定性引擎 | 零 LLM 调用。看板管理、记忆维护、知识注入、字段仲裁、经验更新 |
| ⚖️ **仲裁器** | 编排 | 规则引擎（80%场景）+ LLM 决策（新场景），计划生成、调度、降级 |

> **Scribe 不是 Agent**，它是确定性逻辑引擎，作为 Agent 的"外骨骼"——Agent 负责分析决策，Scribe 负责装备知识、记录决策、仲裁分歧。Agent 不主动查知识库，Scribe 在启动前完成检索和注入。

### 三层知识架构

```
kb/ 领域知识（手写）→ knowledge.yaml 方法经验（自动积累）→ LLM 自由发挥（兜底）
```

Scribe 在 Agent 启动前检索匹配 kb/ 和 knowledge.yaml，将相关知识注入 Agent 的 system prompt。无匹配时 LLM 自行判断。

### 看板协作

Agent 之间不直接对话，通过看板交换信息。每个项目有 `kanban.db`（消息队列）和 `context.md`（共享上下文）。

---

## 统计护栏 — 三级安全网

| 级别 | 规则示例 | 后果 |
|------|---------|------|
| **强制级** | 无检验不下结论、必须报告效应量+CI、观测数据不得声称因果、必须做模型诊断 | 阻止输出 |
| **警告级** | 假设不满足、样本量不足、共线性超标、清洗影响>10% | 标注但允许输出 |
| **提示级** | 建议非线性模型、建议交互效应、建议功效分析 | 不阻断 |

**Web UI**：强制级未通过时**不会**生成正式双轨 HTML，但会在当次 run 的 `output/GUARDRAILS_BLOCKED.md` 留下说明；分析页可链接阅读（与 CLI 语义一致）。

---

---

## 报告模板

版式上以 **`default`** 为双轨 HTML（要点速览 / 数据与完整证据）；其余内置模板为 **风格化** 单栏或专用结构，数据仍可走同一套 Reporter 字段，但页面导航不一定与 `default` 相同。详见 [PROJECT.md](PROJECT.md)「报告设计」。

| 模板 | 风格 | 适用场景 |
|------|------|----------|
| `default` | 通用双轨 HTML | **未指定 `--template` 时使用**；「要点速览」+「数据与完整证据」 |
| `business_analysis` | 商业分析 | 含建议行动区等（单页纵向结构，非 `default` 同款双轨导航） |
| `academic` | APA 风格、表格化 | 学术论文 / 正式报告 |
| `ab_test` | A/B 测试 | 含 verdict 判定 |
| `executive_brief` | 高管简报 | 极简关键信息 |
| `data_audit` | 数据审计 | 详细清洗操作表 |
| `brief` | 极简摘要 | 快速浏览 |

---

## 项目结构

```
~/.hagoku/projects/<项目名>/
├── progress.yaml       # 项目记忆（字段决策、用户偏好、分析历史）
├── context.md          # 看板上下文（所有 Agent 共享）
├── kanban.db           # Agent 看板（SQLite 消息队列）
├── data/               # 数据制品（raw/cleaned .parquet）
├── runs/               # 分析运行记录
└── reports/            # 最终报告
```

---

## 配置

首次运行自动创建 `~/.hagoku/config.yaml`，也支持环境变量覆盖。

**环境变量文件（与仓库根目录无关）**：后端 `hagoku/config.py` **只读取** `~/.hagoku/.env`（若存在）。可从仓库内 `.env.example` 生成：

```bash
mkdir -p ~/.hagoku && cp .env.example ~/.hagoku/.env
# 再编辑 ~/.hagoku/.env
```

`config.yaml` 示例（`base_url` 为 **LLM** OpenAI 兼容端点，勿填成 `hagoku-api` 的根 URL）：

  base_url: "http://localhost:8080/v1"
  model: "Qwen3.6-35B-A3B"
  temperature: 0.6
manager:
  cleaning_impact_warning: 0.3   # 清洗影响率超过该比例时在护栏中重点提示（与「编排模式」无关）
```

环境变量：`HAGOKYU_LLM_BASE_URL`、`HAGOKYU_LLM_API_KEY`、`HAGOKYU_LLM_MODEL`、`HAGOKYU_LLM_MODEL_DEEP`、`HAGOKYU_LLM_MODEL_QUICK`、`HAGOKYU_EMBEDDING_BASE_URL`、`HAGOKYU_EMBEDDING_API_KEY`、`HAGOKYU_EMBEDDING_MODEL`、`HAGOKYU_WORK_DIR`、`HAGOKYU_PROJECT_DIR`（可选）

---

## 技术栈

- **统计**: Pingouin, Statsmodels, SciPy
- **机器学习**: scikit-learn, FLAML
- **数据**: Pandas, DuckDB, PyArrow, openpyxl
- **清洗**: PyOD, cleanlab, Great Expectations, ydata-profiling
- **报告**: Jinja2, Plotly, Matplotlib
- **Agent**: CrewAI, Instructor, Pydantic
- **编排与界面**: Click（CLI）+ FastAPI + React + Vite（固定导航多视图 SPA，非 dockview）

---

## 测试

```bash
pytest tests/ -q
```

---

## 常见问题

**Q: API 启动报错 `AttributeError` 或显示异常功能？**
A: 代码已更新，执行 `pip install -e . --force-reinstall` 强制重装，并重启 `hagoku-api`。

**Q: LLM 连接失败？**
A: 确认 LLM 推理服务已启动，且 `~/.hagoku/.env` 或 `config.yaml` 中的 `base_url`（如 `http://localhost:8080/v1`）与 `model` 指向该服务，**不要**误填 `hagoku-api` 的 `http://localhost:8000`。

**Q: 项目文件存放在哪里？**
A: 默认 `~/.hagoku/projects/`，可在 Settings 面板修改「项目文件夹」路径。

---

## 项目文档

| 文档 | 用途 | 受众 |
|------|------|------|
| [PROJECT.md](PROJECT.md) | 项目灵魂、架构原则、唯一真相源 | 所有人 |
| [DEV.md](DEV.md) | 开发快速上手 | 新贡献者 |
| [CLAUDE.md](CLAUDE.md) | AI 编码助手上下文 | Claude Code |
| [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) | 详细设计手册（架构/看板/向量/审查） | 开发者 |
| [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) | 常见问题排查 | 开发者 |

## License

MIT
