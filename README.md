# HaGoKu

**用数学的力量，挖出数据背后真正的信息**

HaGoKu 是一个多 Agent 协作的数据分析平台。CLI + Web UI 双入口，将数据分析全流程拆分为专业角色——侦察、清洗、分析、报告——由 AI 驱动自动完成，同时确保统计严谨性：每个结论都附带 p 值 + 效应量 + 置信区间。

## 核心能力

| 能力 | 说明 |
|------|------|
| 📈 统计检验 | t 检验、ANOVA、回归、相关，强制效应量+CI |
| 💰 商业分析 | ROI、ROAS、LTV、CAC、归因、漏斗 |
| ⚡ 功效分析 | 样本量评估、效应量解读 |
| 🛡️ 统计护栏 | 三级规则（强制/警告/提示），每个结论都有保障 |
| 🔌 插件架构 | 新增分析方法无需改核心代码 |

## 安装

```bash
pip install -e .
```

开发依赖：

```bash
pip install -e ".[dev]"
```

## 快速开始

### Web UI（推荐）

```bash
hagokyu-ui
# 浏览器打开 http://localhost:8501
```

**UI 功能：** 项目管理 → 数据上传 → 快捷分析 → 实时事件流 → 报告查看 → Refinement 对话

### CLI

```bash
# 数据画像
hagokyu profile examples/ad_campaign.csv

# 完整分析
hagokyu run examples/ad_campaign.csv -q "哪个广告渠道效果最好"

# 零交互快速模式
hagokyu quick examples/ad_campaign.csv -q "分析转化率趋势"

# 项目管理
hagokyu project create "Q1销售分析" -d "分析Q1各渠道ROI"
hagokyu project add "Q1销售分析" ~/data/sales.csv
hagokyu project run "Q1销售分析" -q "哪个渠道roi最高"
```

## 主要命令

| 命令 | 用途 |
|------|------|
| `hagokyu profile <file>` | 生成数据画像 |
| `hagokyu run <file> -q "问题"` | 完整分析流程 |
| `hagokyu quick <file> -q "问题"` | 快速模式（零交互） |
| `hagokyu project create <名称>` | 立项（创建项目） |
| `hagokyu project add <项目> <文件>` | 添加数据文件到项目 |
| `hagokyu project run <项目> -q "问题"` | 在项目中运行分析 |
| `hagokyu project list` | 列出所有项目 |
| `hagokyu project info <项目>` | 查看项目详情 |
| `hagokyu memory --export schema.yaml` | 导出记忆/列语义 |
| `hagokyu replay <run_id>` | 回放分析过程 |
| `hagokyu-ui` | 启动 Web UI |

## 项目管理

每个项目是独立的工作区：

```
~/.hagokyu/projects/<项目名>/
├── project.yaml      # 元数据
├── input/           # 原始数据文件
├── process/         # 清洗后数据
└── output/          # 报告、可视化
```

## 四个专业 Agent

| Agent | 角色 | 职责 |
|-------|------|------|
| **Scout** | 侦察员 | 加载数据、推断字段语义（SemanticType）、评估质量 |
| **Cleaner** | 清洁工 | MCAR/MNAR 检验、异常值 Winsorize、MICE 填补、影响率评估 |
| **Analyst** | 分析师 | 回归/假设检验/ANOVA/相关，强制效应量+CI，自动非参数切换 |
| **Reporter** | 报告员 | 双轨输出（吸引力层+核心价值层），3 种用户模式，图表生成 |

**Manager 编排**：规则引擎覆盖 80% 常见场景，LLM 处理复杂决策。

## 统计护栏

HaGoKu 内置三级统计护栏，防止常见统计错误：

- **强制级** — 没有统计检验不许下结论；观测数据不能声称因果；必须报告效应量
- **警告级** — 样本量过小；假设检验前提未满足；多重比较未校正
- **提示级** — 效应量小但显著；建议补充分析

## 报告模板

| 模板 | 风格 | 适用场景 |
|------|------|----------|
| `default` | 彩色现代风 | 日常分析（默认） |
| `academic` | APA 风格、表格化 | 学术论文 / 正式报告 |
| `brief` | 单页精简 | 快速汇报 / 邮件摘要 |
| `business_analysis` | 商业分析 | 含建议行动区 |
| `ab_test` | A/B 测试 | 含 verdict 判定 |
| `executive_brief` | 高管简报 | 极简关键信息 |
| `data_audit` | 数据审计 | 详细清洗操作表 |

## 用户模式

Reporter 支持三种输出详细度：

| 模式 | 输出 | 适用人群 |
|------|------|----------|
| `quick` | 纯人话摘要 | 快速浏览 |
| `standard` | 人话 + 数学细节 | 大多数用户 |
| `expert` | 完整统计证据链 | 数据分析师 |

## 配置

首次运行自动创建 `~/.hagokyu/config.yaml`，也支持环境变量覆盖：

```yaml
llm:
  base_url: "http://localhost:8000/v1"
  model: "Qwen3.6-35B-A3B"
  temperature: 0.6
manager:
  mode: "balanced"   # balanced(规则+AI) / rule(纯规则) / ai(AI优先)
```

环境变量：`HAGOKYU_LLM_BASE_URL`、`HAGOKYU_LLM_API_KEY`、`HAGOKYU_LLM_MODEL`、`HAGOKYU_MANAGER_MODE`

## 技术栈

- **统计**: Pingouin, Statsmodels, SciPy
- **机器学习**: scikit-learn, FLAML
- **数据**: Pandas, DuckDB, PyArrow, openpyxl
- **清洗**: PyOD, cleanlab, Great Expectations, ydata-profiling
- **报告**: Jinja2, Plotly, Matplotlib
- **Agent**: CrewAI, Instructor, Pydantic
- **CLI**: Click
- **UI**: Streamlit

## 测试

```bash
pytest tests/ -q          # 223 测试
python /tmp/test_ui_logic.py   # 153 UI 逻辑测试
```

## License

MIT
