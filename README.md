# HaGoKu Studio

> **让每个小模型，都能做专业级商业分析。**

HaGoKu Studio 是一个 LLM 驱动的本地数据分析平台。**一个 Agent + 15 个工具 + 可切换提示词 = 多维度分析能力。**

---

## 核心竞争力：不改代码，切换分析领域

传统方案需要为每个领域（股市、电商、医疗）开发独立的 Agent 和工具集。HaGoKu 的通道架构让它完全不同：

```
        ┌──────────┐
        │   通道    │  ← 代码：纯透传 + 工具执行，零领域知识
        └─────┬────┘
              │
 ┌────────────┼────────────┐
 │            │            │
┌┴────────┐ ┌┴────────┐ ┌┴────────┐
│通用商业  │ │股市技术  │ │电商运营  │  ← 提示词预设：领域术语 + 分析框架
└─────────┘ └─────────┘ └─────────┘
```

**同一个 DataAnalystAgent + 同一套工具 + 不同的 prompt.md = 不同领域的专业分析。** 用户在「分析能力」面板一键切换，无需写代码、无需懂 LLM。

详见 [`PROJECT.md`](PROJECT.md) 和 [`docs/PRESETS.md`](docs/PRESETS.md)。

---

## 快速上手

### 前置

- Python ≥ 3.10
- OpenAI 兼容协议的 LLM 服务（本地或云端）
- Node ≥ 18（仅前端开发用）

### 安装

```bash
git clone <repo-url> && cd HaGoKu

python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# 配置 LLM
mkdir -p ~/.hagoku && cp .env.example ~/.hagoku/.env
# 编辑 ~/.hagoku/.env 填入 LLM base_url 和 API key
```

### 运行

```bash
# 终端 1：启动后端 API
hagoku-api                 # http://localhost:8000

# 终端 2：启动前端
cd hagoku_web && npm install && npm run dev   # http://localhost:5173
```

浏览器打开前端，创建项目 → 上传数据 → 提问，LLM 自动完成分析。

---

## 设计哲学

| 维度 | 含义 |
|------|------|
| **通道优先** | 代码只透传 + 执行工具，LLM 做所有语义判断 |
| **精** | 报告结论精炼，不超过 5 条核心发现 |
| **准** | 每条结论有统计检验支撑（p 值 + 效应量 + 置信区间） |
| **狠** | 直接回答用户问题，不回避不确定性 |
| **保密** | 本地模型优先，数据不出本机 |
| **专业** | 严肃对待不确定性，不假装 100% 确定 |

---

## 分析流程

用户与单一 `DataAnalystAgent` 对话，LLM 自主推进五阶段：

| 阶段 | 内容 |
|------|------|
| 理解字段 | 逐列推断含义和角色，展示表格请用户确认 |
| 评估清洗 | 检查数据质量，给出处理建议 |
| 统计分析 | 选择方法、跑检验、产出有统计支撑的发现 |
| 撰写报告 | 整理发现为 HTML 报告，可包含 Plotly 图表 |
| 持续交互 | 报告生成后继续对话，补充分析或深挖细节 |

每个阶段 LLM 通过 `ask_user` 工具暂停等待用户确认，用户可随时纠正、跳过或深入。

---

## 架构亮点

### 通道 = 代码的边界

- **信息通道**：用户输入 → LLM 完整到达，不截断不摘要不代劳
- **控制通道**：LLM 通过 tool_calls 表达意图，代码机械执行不判断
- **铁律**：不在代码中硬编码业务语义，LLM 失败必须可见（不静默兜底）

### 工具系统

15 个工具覆盖全流程：数据探查、字段管理、统计检验（t-test/ANOVA/回归/趋势分解）、清洗检测、Plotly 可视化、HTML 报告生成。新增工具只需注册，Agent 自动可见。

### 统计护栏

14 条规则三级严重度（MANDATORY/WARNING/SUGGESTION）——无检验的结论、缺效应量、高 VIF、小样本等问题自动拦截或标注。

### 可观察性

- LLM Dump：每次调用完整记录到 `runs/{id}/llm_dumps/`
- 事件总线：全链路事件实时推送到前端
- Session 持久化：崩溃后可恢复对话

---

## 项目结构

```
hagoku/                    # Python 后端
├── agents/               # DataAnalystAgent + 提示词预设
│   └── presets/          # 可切换的分析场景预设
├── manager/              # Orchestrator + 事件驱动编排
├── tools/                # 15 个 LLM 工具（统计/清洗/可视化/报告）
├── guardrails/           # 统计护栏
├── observability/        # EventBus / LLM dump / 通道日志
├── api/                  # FastAPI + WebSocket
└── cli.py                # CLI 入口

hagoku_web/               # React 前端（Vite + Tailwind + Zustand）
docs/                     # 设计文档 / ADR / 计划
tests/                    # 5 层测试金字塔
```

---

## 文档导航

| 文件 | 看什么 |
|------|--------|
| [`PROJECT.md`](PROJECT.md) | 项目规范——设计哲学、通道律、铁律（**唯一真相源**） |
| [`CLAUDE.md`](CLAUDE.md) | AI 实现者操作手册 |
| [`docs/PRESETS.md`](docs/PRESETS.md) | 预设系统——如何切换/新建分析场景 |
| [`docs/TOOL_DESIGN.md`](docs/TOOL_DESIGN.md) | 工具设计原则 |
| [`docs/CHANNEL.md`](docs/CHANNEL.md) | 通道反模式经验录 |
| [`docs/decisions/`](docs/decisions/) | 架构决策日志（ADR） |

---

## License

MIT
