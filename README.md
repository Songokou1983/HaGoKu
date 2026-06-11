# HaGoKu Studio

> **让每个小模型，都能做专业级商业分析。**

> 📍 **项目演进方向（2026-06-11 起）**：项目正在从「4 Agent 协作 pipeline」收缩为「1 个数据分析师 LLM + 专业工具箱」。新重心：**本地优先的严肃数据分析师，基于大模型能力，配备深度统计工具箱**。改造按 6 个 Phase 推进，下方"Pipeline 四阶段"是**当前实现**，会随 Phase D 完成而演变为同一 LLM 的 4 个关注点。详见 [`docs/plans/2026-06-11-collapse-to-single-agent-brief.md`](docs/plans/2026-06-11-collapse-to-single-agent-brief.md)。

HaGoKu Studio 是一个多 Agent 数据分析平台——四个分工明确的 LLM Agent 协作，把一份原始数据带到结构化的统计结论与可视化报告。本地 LLM 优先，数据不出本机。

```
┌────────┐    ┌─────────┐    ┌─────────┐    ┌──────────┐
│ Scout  │ →  │ Cleaner │ →  │ Analyst │ →  │ Reporter │
│ 字段理解 │    │  清洗   │    │ 发现+讨论 │    │  可视化   │
└────────┘    └─────────┘    └─────────┘    └──────────┘
```

每个阶段都是「LLM 自主推理 + 用户可中途介入挑战」。代码只搭通道与编排，不替 LLM 做语义判断。

---

## 设计哲学

| 维度 | 含义 |
|------|------|
| **精** | 报告结论精炼：不超过 5 条核心发现 |
| **准** | 每条结论有统计检验支撑（p 值 + 效应量 + 置信区间） |
| **狠** | 直接回答用户问题，不回避不确定性 |
| **轻量** | 本地 LLM 优先，最小依赖，数据不出本机 |
| **专业** | 严肃对待不确定性，不假装 100% 确定 |

**核心信条**：LLM 在语义判断上比代码更可靠。Code 的活是构建通道让 LLM 自由发挥，不是替 LLM 干活。

工程层面这意味着两条铁律：
1. **不在代码中硬编码业务语义**——字段角色、清洗方案、分析意图全部交给 LLM
2. **LLM 失败必须可见**——禁止 try/except 兜底返回默认值，让用户看见错误而不是看见错误的结果

完整设计哲学与十条通道律见 [`PROJECT.md`](PROJECT.md)。

---

## 快速上手

### 前置

- Python ≥ 3.10
- OpenAI 兼容协议的 LLM 服务（自部署或云端）
- Node ≥ 18（仅前端开发用）

### 安装

```bash
git clone <repo-url> && cd HaGoKu

python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# 配置 LLM（唯一生效路径：~/.hagoku/.env）
mkdir -p ~/.hagoku && cp .env.example ~/.hagoku/.env
# 编辑 ~/.hagoku/.env 填入 LLM base_url 和 API key
```

### 运行

**模式 A — CLI 跑一次完整分析**

```bash
hagoku run --data path/to/data.csv --query "哪些渠道 ROI 最高"
```

**模式 B — Web UI（推荐）**

```bash
# 终端 1：启动后端 API（FastAPI + WebSocket）
hagoku-api                # 默认 http://localhost:8000

# 终端 2：启动前端（仅本地开发）
cd hagoku_web && npm install && npm run dev   # 默认 http://localhost:5173
```

浏览器打开前端地址，上传数据 → 提问 → 与四个 Agent 协作。

---

## Pipeline 四阶段

### Scout — 字段理解
不读字段名做正则匹配。LLM 看完样本数据后**用 tool_call 表达**每个字段的角色（target / feature / identifier）和业务含义。用户可改任意字段，Scout 用 LLM diff 应用差异。

### Cleaner — 数据清洗
LLM 评估数据质量问题（缺失、异常、重复、类型不一致），提议清洗方案并由用户确认。当前 Cleaner 是一次性评估模式（即将对话化，见 `docs/plans/`）。

### Analyst — 发现 + 讨论（两阶段）
- **阶段 1 自主**：进入后自动选统计方法、跑检验、产出书面概括化结论（含「发现 / 统计依据 / 局限或解读」三要素）
- **阶段 2 对话**：用户可自由输入挑战分析方向、追问细节、要求换方法。Analyst 用 `route_to` 工具按需跳回 Scout/Cleaner 或推进到 Reporter

### Reporter — 可视化呈现
基于 Analyst 的发现 + 上游全链路数据，生成 HTML 报告。模板可配置。

---

## 架构亮点

### 壳子 / 架构 / 通道

代码只负责三件事：

- **壳子**：Web UI + CLI + 事件系统 + 持久化
- **架构**：Agent 分工 + 协作顺序 + 统计护栏 + 看板
- **通道**：
  - **信息通道**：上下文 → LLM
  - **控制通道**：LLM 用 `tool_calls` 表达「完成 / 留下 / 跳转 / 追问」，代码机械执行

任何"代码替 LLM 做语义判断"都视为通道残缺，应该补通道而非补规则。

### 可观察性

- **统一 dump 通道**：每次 LLM 调用入参 / 出参写入 `dump/<run_id>/<n>.json`，可复跑可审计
- **事件总线**：Agent 生命周期 / 工具调用 / 用户输入 / 护栏触发全部 emit 事件，前端实时看板
- **统计护栏**：分析阶段强制级检验（多重比较、共线性、效应量），失败由 LLM 向用户解释风险，不静默继续

### 通道契约测试

`tests/test_product/test_control_channel_link_integrity.py` 验证「LLM 调工具 X → 业务效果 Y」链路完整。盲点用 `strict xfail` 锁定——未来接通时 XPASS 失败会逼迫开发者补链路测试。

---

## 项目结构

```
hagoku/                  # Python 后端
├── agents/             # Scout / Cleaner / Analyst / Reporter
├── manager/            # Orchestrator + 事件驱动状态机
│   ├── llm_dispatch/   # 用户回复路由 + 各阶段处理
│   └── payloads/       # 前端消息体构造
├── tools/              # LLM 工具注册（统计 / 清洗 / 路由 / submit）
├── guardrails/         # 统计护栏（共线性 / 多重比较 / 效应量）
├── observability/      # event_bus / llm_dump / channel_logger
├── api/                # FastAPI server + WebSocket handler
└── cli.py              # `hagoku` CLI 入口

hagoku_web/              # React 前端（Vite + Tailwind + Zustand）
docs/                    # 设计文档 / 决策日志 / 计划 / 案例
tests/                   # pytest（含 doctrine_compliance + product + agents）
```

---

## 文档导航

| 文件 | 看什么 |
|------|--------|
| [`PROJECT.md`](PROJECT.md) | 项目规范——设计哲学、通道律、铁律、代码边界（**唯一真相源**） |
| [`CLAUDE.md`](CLAUDE.md) | AI 实现者操作手册（铁律速查、违禁/合法写法） |
| [`DEV.md`](DEV.md) | 开发者快速上手 |
| [`docs/DEVELOPMENT.md`](docs/DEVELOPMENT.md) | 详细开发手册（看板 / 测试 / 调试） |
| [`docs/TROUBLESHOOTING.md`](docs/TROUBLESHOOTING.md) | 常见问题排错 |
| [`docs/decisions/`](docs/decisions/) | 架构决策日志（ADR） |
| [`docs/plans/`](docs/plans/) | 已完成 / 进行中的改造 brief |
| [`docs/cases/`](docs/cases/) | 真实失效场景案例库 |

---

## 测试

```bash
# 三组守门测试（提交前必跑，任一变红 = 改坏了）
.venv/bin/python -m pytest tests/test_doctrine_compliance.py -q          # 零硬编码守门
.venv/bin/python -m pytest tests/test_product/test_information_arrival.py -q  # 信息抵达契约
.venv/bin/python -m pytest --tb=short -q                                 # 全套回归
```

当前规模：**523 passed + 3 strict xfailed**（截至 2026-06-08）。

---

## 状态与稳定性

| 维度 | 当前 |
|------|------|
| 版本 | 0.1.0（Alpha） |
| 适配模型 | ~30B+ 参数，OpenAI 兼容协议 |
| Pipeline | Scout / Cleaner / Analyst / Reporter 四环全通 |
| Analyst 对话化 | ✅ 已上线（两阶段：自动首波 + 自由对话） |
| Cleaner 对话化 | 🚧 计划中（见 `docs/plans/2026-06-08-smoke-and-cleaner-dialog-brief.md`） |
| Reporter 互动化 | 📌 未开始 |

> 💡 通道设计在 30B+ 模型上验证稳定。7B 级因幻觉率高、指令遵循弱，不在目标运行环境。若小模型遇到"字段全选 / 角色乱判"等问题，换个稍大的模型通常就解决了。

---

## License

MIT（声明于 [`pyproject.toml`](pyproject.toml)）。
