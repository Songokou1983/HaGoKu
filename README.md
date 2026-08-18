# HaGoKu Studio

<!-- badges:start -->
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![CI](https://github.com/Songokou1983/HaGoKu/actions/workflows/ci.yml/badge.svg)](https://github.com/Songokou1983/HaGoKu/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/Songokou1983/HaGoKu)](https://github.com/Songokou1983/HaGoKu/releases)
[![Tools](https://img.shields.io/badge/tools-12-orange.svg)](docs/TOOL_DESIGN.md)
[![Single Agent](https://img.shields.io/badge/agents-1-purple.svg)](docs/CHANNEL.md)
[![PRs](https://img.shields.io/badge/PRs-not%20accepted-lightgrey.svg)](CONTRIBUTING.md)
[![Issues](https://img.shields.io/badge/issues-welcome-green.svg)](https://github.com/Songokou1983/HaGoKu/issues)
<!-- badges:end -->

> **单 Agent + 预设 + 12 工具 = 不写代码切换分析领域。**
> **让本地 35B 也能跑专业级商业分析。**

HaGoKu Studio 是一个 LLM 驱动的数据分析平台，**单 Agent + 12 个工具 + 可切换提示词**——
同一个引擎，靠提示词预设适配不同领域（通用商业 / 股市 / 电商），不写代码。

---

## 为什么是 HaGoKu

- **1 个 Agent 干 5 个 Agent 的活** — 其他框架（LangGraph / AutoGen / CrewAI）需要 Scout+Cleaner+Analyst+Reporter+Orchestrator 协调；HaGoKu 单 Agent 读历史自驱动，行为更可预期，bug 面更小
- **预设即领域** — 同一引擎，切 `presets/stock.md` 变股票技术分析，切 `ecommerce.md` 变电商运营，切 `general.md` 变通用商业。**0 行代码切换领域**
- **小模型友好** — 本地 35B（Qwen3.5-A3B Q4_K_M 级别）就能跑；也兼容云端大模型（DeepSeek / Claude / 任何 OpenAI 兼容端点）
- **445 测试 100% 通过** — 含铁律合规测试 + 契约测试 + 单元测试
- **三层记忆** — 跨项目方法库 + 经验库 + 项目记忆，分析越用越聪明
- **通道架构** — 代码只做 I/O，LLM 决定一切。改业务规则 = 改 prompt，不改代码
- **完整反模式经验** — 80 天开发踩过的所有坑写在 `docs/CHANNEL.md`，开源即送

---

## 是什么

HaGoKu 把"小模型做不了专业分析"这件事拆掉。三个层面的设计一起做到：

- **通道架构**：代码只做机械执行（透传/工具/日志/校验），不让 LLM 做语义判断；LLM 只决定"下一步调哪个工具 + 看结果怎么解读"。这把"改业务规则"从代码工程降级成"改一段 prompt"。
- **单 Agent 自驱动**：`run_step()` 用 `while tc_list` 自动续轮（对标 Claude Code），LLM 自己读历史决定阶段推进；代码不替 LLM 做阶段决策。12 个工具都是纯 I/O，没有"submit/ask/route/pause/confirm"这种带阶段信号的工具。
- **预设即领域**：`hagoku/agents/presets/` 下有 3 个预设文件（`general.md` / `stock.md` / `ecommerce.md`），运行时从 `~/.hagoku/active_preset` 读选择。建一个新分析场景 = 写一段 prompt。

**与"传统多 Agent 框架"的区别**：很多框架把分析师拆成 Scout/Cleaner/Analyst/Reporter 多个 Agent，再用编排器串起来。HaGoKu 在 2026-06-11 收敛为单个 `DataAnalystAgent`，因为阶段推进本质是 LLM 对历史的判断，不需要跨 Agent 通信。删掉 3 个 Agent 后代码量减半，行为更可预期。

---

## 工作流

一个数据分析任务按**四阶段**推进，LLM 按对话历史自主决定阶段切换：

| 阶段 | LLM 干什么 |
|------|------|
| **理解字段** | 逐列推断中文字段名 + 业务含义 + 角色，调用 `set_columns` 写进上下文 |
| **评估清洗** | 围绕分析目标检查数据质量（缺失/异常），给出处理建议 |
| **统计分析** | 按目标 + 数据形态选方法，跑检验（t 检验/ANOVA/相关/回归/趋势分解），产出有统计支撑的发现 |
| **撰写报告** | 整理发现为 HTML 报告，可用 Plotly 图表，自动出 `latest.html` 软链 |

报告生成后用户可继续对话（追问/深挖/补分析），不属于独立阶段。

---

## 核心竞争力

### 通道架构：代码的边界

判断代码越界与否有一个简单测试：**"删掉这段代码，用户看到的内容变了吗？"** 不变 → 通道。变了 → 越界。

通道架构的好处是**改业务规则不动代码**。比如从"通用商业"切到"股票技术分析"，改的不是 Python 代码，是 `hagoku/agents/presets/stock.md` 这一个文件——同一个引擎、同一个工具集、同一个 UI。

### 12 个工具的精挑细选

工具设计三条过滤（内部叫"工具三问"）：
1. LLM 自己能做吗？能做 → 删
2. 描述里写了"你什么时候该用我"？那是 prompt 的事，不是 tool 的事 → 改
3. 同一件事有几个入口？→ 合并

历史上从 36 个工具收到 16 再到 12。每次收都是删 LLM 自己能干的事（不是所有"知识"都得包成 tool）。

### 预设即领域

| 预设 | 适用场景 |
|------|------|
| `general` | 通用商业分析（默认）。任何运营/业务数据集。自动选统计方法 |
| `stock` | 股票/期货/加密技术分析。趋势分解、波动率（GARCH/历史）、相关性、单位根、板块轮动、量价 |
| `ecommerce` | 电商运营。RFM、转化漏斗、复购/留存、购物篮分析、A/B、LTV；内置刷单检测和归因缺口识别 |

切预设不需要改任何业务代码。

---

## 工具系统

12 个工具按职责分 4 组：

| 类别 | 工具 | 干什么 |
|------|------|------|
| **数据探查** | `get_column_names` | 列出所有列 + 行数 |
| | `get_column_stats` | 单列完整摘要（dtype/分位数/均值/众数/缺失） |
| | `get_group_stats` | group-by 聚合（count/mean/std/min/max） |
| **字段管理** | `set_columns` | 批量/单条写中文字段名 + 业务含义 + 角色 + 证据 |
| **统计与清洗** | `run_statistical_test` | 调度 ttest/anova/chi2/pearson/spearman/回归/趋势分解 |
| | `detect_outliers` | IQR 或 Z-score 异常检测 |
| | `detect_missing_pattern` | MCAR/MAR/MNAR 分类 + 填充建议 |
| **可视化/报告/记忆** | `create_plot` | Plotly 图表（散点/折线/柱/直方/箱/小提琴/热力） |
| | `generate_report` | 渲染 HTML 报告（Jinja 模板，自动注入图表） |
| | `recall_lessons` | 跨对话经验库检索 |
| | `save_lesson` | 持久化新经验 |
| | `query_project_memory` | 读项目记忆（fields/history/corrections） |

所有工具都是**纯 I/O**——不携带流程信号。LLM 调完工具后自然会回话推进，代码不替 LLM 管阶段。

---

## 架构

三层结构：

```
┌─────────────────────────────────────────────────────────────┐
│  壳子层（Shell）   Web UI / CLI / FastAPI / Electron 桌面   │
├─────────────────────────────────────────────────────────────┤
│  架构层（Arch）    Orchestrator + EventBus + WS Handler      │
├─────────────────────────────────────────────────────────────┤
│  通道层（Channel） DataAnalystAgent + 12 tools + 预设 prompt │
│                    + 三层记忆（方法库 / 经验库 / 项目记忆）  │
└─────────────────────────────────────────────────────────────┘
```

关键约束：
- 单 `DataAnalystAgent`（`hagoku/agents/agent.py`），`run_step()` 用 `while tc_list` 自续轮
- `to_messages_for_llm()` 是 LLM 消息构造的**唯一入口**
- `orchestrator.run()` 加载→画像→推断字段→分析→报告骨架（流程保障），LLM 决定每步内容
- 配置中性：不写死模型名/URL/端口，从 `~/.hagoku/.env` 读

### 项目结构

```
hagoku/                # Python 后端（核心包）
├── agents/            # DataAnalystAgent + 3 个提示词预设 + 3 个元审计器
├── tools/             # 12 个工具（registry/cleaning/stat/viz/memory）
├── manager/           # Orchestrator + LLM dispatch + Scout 载荷
├── guardrails/        # 统计护栏（强制/警告/提示 三级）
├── memory/            # 方法库（methods/） + 经验库（lessons.jsonl）
├── storage/           # SQLite + 产物 + 记忆后端
├── repository/        # 项目仓库
├── api/               # FastAPI + WebSocket + 鉴权中间件
├── llm/               # 客户端 + 清洗
├── observability/     # EventBus / 通道日志 / LLM dump
├── context/           # Session（消息列表）
├── devtools/          # 交互场景
└── cli.py             # CLI 入口（22 个子命令）

hagoku_web/            # React 19 + Vite + TypeScript + Tailwind + Zustand
desktop/               # Electron 桌面客户端（v0.9）
docs/                  # 设计文档 / ADR / 计划
tests/                 # 测试套件（unit + 契约 + 铁律合规）
```

---

## 桌面 + Web

两种入口，二选一：

**Web**（推荐开发）：
```bash
hagoku-api                              # 启动 FastAPI（默认 :8000）
cd hagoku_web && npm install && npm run dev   # 启动 Vite 开发服务器（默认 :5173）
```

**桌面**（Electron，开箱即用）：
```bash
hagoku desktop                          # 启动桌面客户端
# 或从 Linux 桌面：找到 desktop/hagoku-studio.desktop 装到 ~/.local/share/applications/
```

---

## 快速开始

```bash
# 1. 克隆与安装
git clone https://github.com/Songokou1983/HaGoKu.git
cd HaGoKu
python3 -m venv .venv && source .venv/bin/activate
pip install -e .

# 2. 配置 LLM（任何 OpenAI 兼容端点）
mkdir -p ~/.hagoku
cat > ~/.hagoku/.env <<'EOF'
HAGOKU_LLM_BASE_URL=http://localhost:8000/v1
HAGOKU_LLM_API_KEY=your-key-here
HAGOKU_LLM_MODEL=your-model-name
EOF

# 3. 健康检查（验环境、LLM 连通、统计库栈）
hagoku doctor

# 4. 一行分析
hagoku run data.csv -q "哪个渠道ROI最高"

# 5. 或启动 Web UI（两个进程，分别在两个终端）
hagoku-api                              # 后端（FastAPI，:8000）
cd hagoku_web && npm install && npm run dev   # 前端（Vite，:5173）
```

数据按"项目"组织（默认 `~/.hagoku/projects/{name}/`），每个项目有自己的输入、过程数据、报告、会话、LLM dump。

---

## 配置

所有配置走 `~/.hagoku/.env` 和 `~/.hagoku/config.yaml`，**仓库内零硬编码**：

- LLM 端点：任何 OpenAI 兼容协议（本地 llama-server / vLLM / 云端 API）
- 统计护栏：3 级严重度（强制/警告/提示），可单独开关
- 预设：写到 `~/.hagoku/active_preset` 切换默认预设
- 数据路径：项目目录可指定（默认 `~/.hagoku/projects/`）

---

## 设计文档

- [PROJECT.md](PROJECT.md) — 设计真相来源（架构 / 阶段 / 通道原则）
- [docs/decisions/](docs/decisions/) — 架构决策记录（ADR-001 ~ ADR-005）
- [docs/CHANNEL.md](docs/CHANNEL.md) — 通道反模式经验录
- [docs/TOOL_DESIGN.md](docs/TOOL_DESIGN.md) — 工具设计三问 + 实战教训
- [docs/PRESETS.md](docs/PRESETS.md) — 预设系统说明
- [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) — 开发手册
- [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) — 故障排查

---

## ⭐ Star History

如果觉得有用，⭐ 一下是对个人开发者最大的支持：

<a href="https://star-history.com/#Songokou1983/HaGoKu">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://api.star-history.com/svg?repos=Songokou1983/HaGoKu&type=Date&theme=dark" />
    <source media="(prefers-color-scheme: light)" srcset="https://api.star-history.com/svg?repos=Songokou1983/HaGoKu&type=Date" />
    <img alt="Star History Chart" src="https://api.star-history.com/svg?repos=Songokou1983/HaGoKu&type=Date" />
  </picture>
</a>

---

## 🤝 贡献 & 社区

- **Bug / 问题 / 文档不清**：开 [Issue](https://github.com/Songokou1983/HaGoKu/issues)（模板已就绪）
- **架构讨论 / 用例分享**：[Discussions](https://github.com/Songokou1983/HaGoKu/discussions)
- **怎么贡献**：[CONTRIBUTING.md](CONTRIBUTING.md)（一句话：**Issue 欢迎，PR 不接受**，单 master 不开分支）
- **变更历史**：[CHANGELOG.md](CHANGELOG.md)

⭐ 如果觉得有用，给个 star 是对个人开发者最大的支持 ❤️

---

## License

[MIT](LICENSE) — 自由使用、修改、商用、再分发。详见 [LICENSE](LICENSE)。

Copyright (c) 2026 Songokou1983