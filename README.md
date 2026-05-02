# HaGoKu

**用数学的力量，挖出数据背后真正的信息**

HaGoKu 是一个多 Agent 协作的数据分析平台。它将数据分析全流程拆分为专业角色——侦察、清洗、分析、报告——由 AI 驱动自动完成，同时确保统计严谨性：没有检验不许下结论，显著性必须配效应量。

## 核心理念

- **角色分工** — 每个 Agent 专注一个领域，做得少但做得精
- **统计护栏** — 强制级规则阻止无检验结论，警告级规则标注常见问题
- **全程透明** — 事件总线记录每一步，可回放整个分析过程
- **数据不出本机** — 本地 LLM 驱动，机密数据零外泄

## 安装

```bash
git clone https://github.com/yourname/hagokyu.git
cd hagokyu

python -m venv .venv
source .venv/bin/activate

pip install -e .
```

如需开发依赖（pytest、ruff、mypy）：

```bash
pip install -e ".[dev]"
```

## 快速开始

### 1. 数据画像 — 30 秒了解数据全貌

```bash
hagokyu profile examples/ad_campaign.csv
```

输出每列的类型推断、缺失率、唯一值数、数据质量评分。

### 2. 完整分析 — 提问，拿报告

```bash
hagokyu run examples/ad_campaign.csv -q "哪个广告渠道效果最好"
```

自动走完 Scout → Cleaner → Analyst → Reporter 流水线，输出 HTML 报告。

### 3. 快速模式 — 零交互，直接出结果

```bash
hagokyu quick examples/ad_campaign.csv -q "分析转化率趋势"
```

静默执行，只输出报告路径。

## 主要命令

| 命令 | 用途 |
|------|------|
| `hagokyu profile <file>` | 生成数据画像 |
| `hagokyu run <file> -q "问题"` | 完整分析流程 |
| `hagokyu quick <file> -q "问题"` | 快速模式（零交互） |
| `hagokyu projects` | 列出所有项目 |
| `hagokyu history <project>` | 查看运行历史 |
| `hagokyu replay <run_id>` | 回放分析过程 |
| `hagokyu config` | 查看/管理配置 |
| `hagokyu guardrails` | 查看统计护栏规则 |

### 常用选项

```bash
# 输出格式（可组合）
hagokyu run data.csv -q "分析" -f html -f md -f json

# 报告模板
hagokyu run data.csv -q "分析" --template academic         # 学术报告
hagokyu run data.csv -q "分析" --template business_analysis # 商业分析
hagokyu run data.csv -q "分析" --template executive_brief   # 高管简报

# Manager 模式
hagokyu run data.csv -q "分析" --manager-mode pure_rule   # 纯规则，零AI
hagokyu run data.csv -q "分析" --manager-mode cloud        # 云端强模型

# 输出详细度
hagokyu run data.csv -q "分析" -v verbose
hagokyu run data.csv -q "分析" -v quiet
```

## 四个专业 Agent

| Agent | 角色 | 职责 |
|-------|------|------|
| **Scout** | 侦察员 | 加载数据、推断字段语义、评估质量 |
| **Cleaner** | 清洁工 | 缺失值处理、异常值检测、影响评估 |
| **Analyst** | 分析师 | 回归分析、假设检验、相关性、趋势分析 |
| **Reporter** | 报告员 | 模板驱动报告生成、护栏检查报告 |

## 统计护栏

HaGoKu 内置三级统计护栏，防止常见统计错误：

- **强制级** — 没有统计检验不许下结论；观测数据不能声称因果
- **警告级** — 样本量过小；假设检验前提未满足
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

## 配置

首次运行自动创建 `~/.hagokyu/config.yaml`，也可通过环境变量覆盖：

```yaml
llm:
  base_url: "http://localhost:8000/v1"
  model: "Qwen3.6-35B-A3B"
  temperature: 0.6
manager:
  mode: "local_weak"  # local_weak / local_strong / cloud / pure_rule
output:
  formats: ["html"]
  base_dir: "~/.hagokyu/projects"
```

环境变量：`HAGOKYU_LLM_BASE_URL`、`HAGOKYU_LLM_MODEL`、`HAGOKYU_MANAGER_MODE`

## 技术栈

- **统计**: Pingouin, Statsmodels, SciPy
- **机器学习**: scikit-learn, FLAML
- **数据**: Pandas, DuckDB, PyArrow
- **清洗**: PyOD, cleanlab, Great Expectations
- **报告**: Jinja2, Plotly, Matplotlib
- **Agent**: CrewAI, Instructor, Pydantic
- **CLI**: Click

## License

MIT
