# 开发任务传递（DEVELOPMENT_PROMPT）

> **用途**：① **路线图跟踪**（四阶段 backlog，可勾选、可转发）；② **单轮任务骨架**（复制给 AI/协作者的一轮规格）。  
> **真相源**：[PROJECT.md](PROJECT.md)（含「交付物规划」「迭代执行顺序」）。本文件任务状态**由执行人合并后更新**；**审查**见下文「审查约定」。

---

## 修改代码前必读（口径）

| 文档 | 用途 |
|------|------|
| [PROJECT.md](PROJECT.md) | 灵魂、Agent、人机互动、双轨报告、交付物、**迭代执行顺序** |
| [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) | 设计手册、测试与 Playwright/React 说明 |
| [DEV.md](DEV.md) | 环境、日常命令 |
| [README.md](README.md) | 用户安装与快速开始 |
| [UI_CHANGELOG.md](UI_CHANGELOG.md) | 前端有界面改动时按 `CLAUDE.md` 记录 |
| [CLAUDE.md](CLAUDE.md) | UI 原则、备份与变更日志规则 |

**环境变量**：只认 `~/.hagoku/.env`；模板见仓库 `.env.example`。LLM 默认端口口径与 **HaGoKu API（8000）** 区分见 `PROJECT.md`。

---

路线图跟踪（与 PROJECT.md「迭代执行顺序」一致）

### 审查结论（2026-05-12，只读代码审查 — 可转发）

> **严重程度：高 — 曾存在「未达标却标 `[x]`」**  
> 提交 **`710cf9a` 仅修改本 Markdown**，**未包含**实现证据。后续必须以 **PR + 测试或书面备案** 支撑勾选。

#### 第一次审查（文档 / 参数面对照）

| 原勾选 | 审查认定 | 说明 |
|--------|----------|------|
| 1.1 `[x]` | **曾不成立 → 已书面备案** | CLI `Orchestrator.run()` 与 WS `analyze` 参数面不同。现于**下方阶段 1 表**备案为 **「Web 子集」故意设计**；若产品反悔须在 PR 中撤回该备案。 |
| 1.2 `[x]` | **仅部分成立** | `respond` → `unblock` 存在；重叠 `run` / 重连等仍缺专项测试。 |
| 1.3 `[x]` | **仅部分成立** | `memory` 有单测；`Orchestrator.resume=True` 集成测试仍缺。 |
| 1.4 `[x]` | **未逐项核验** | `history` vs DB 字段稳定性仍待点验。 |
| 1.5 `[x]` | **曾不成立** | 见下方 **「走读记录」**；走读后状态为 **`[/]`**（现状已建档 + 测试锁定，**不等于**已实现产品级「降级 / `can_output` 阻断 Reporter」）。 |
| 1.6 `[x]` | **仍部分成立** | 已增加 `tests/test_pipeline/test_failure_path.py`（**11** 项）固化 1.5 相关行为；**不**覆盖 1.1–1.4 全风险面。 |

#### 走读记录（2026-05-12）— 失败路径与统计护栏（对照 `hagoku/manager/orchestrator.py`）

以下已由人工走读 + **本仓库测试文件**交叉验证（`pytest tests/test_pipeline/test_failure_path.py` → **11 passed**）。

| 观测 | 位置 / 说明 |
|------|-------------|
| **Agent 异常 → 硬终止（无降级）** | `Orchestrator.run` 顶层 `except Exception`：`fail_run` → 发射 `RUN_FAILED` → **`raise`**（约 **L713–L717**）。无 fallback / retry / 跳 Reporter 等分支。 |
| **`orchestrator.guardrails` 未使用** | 仅在 `__init__` 中 `StatisticalGuardrails()`；`run()` 内无 `guardrails.check` / `can_output`。 |
| **`can_output()` 未阻断 Reporter** | 全仓库 `can_output` 仅在 `guardrails/statistical.py` 定义；**未**出现在 `Orchestrator.run` → `ReporterAgent.run` 决策路径中。 |
| **Analyst 侧护栏** | `AnalystAgent` 内对每条结果 `guardrails.check`，写入 `result["guardrail_results"]`，并对违规发 `QUALITY_CHECK`；**不** `return` / 抛错阻断，**Reporter 仍会运行**。 |
| **≠ `validate_analysis_output`** | Reporter 使用文本解析器做结构检查；与护栏引擎 `can_output` **不是同一套逻辑**（见测试文件内说明）。 |

**结论（1.5 工作项怎么算）**：  
- **「路径可说明、可测试、可复现」** → ✅ 已满足（本走读 + `test_failure_path.py`）。  
- **「按产品设计：失败时降级 + 编排层护栏阻止输出」** → ❌ **当前未实现**；若 `PROJECT.md` 将此类行为定为硬性要求，应作为 **阶段 3.3 / 后续 PR** 收敛，**不得**把 1.5 标为 `[x]`。

**阶段闸门（执行，修订）**：  
- **1.1**：若以「Web 子集」备案为准，可视为文档闭环。  
- **1.5**：保持 **`[/]`**，直至产品明确「硬终止即可」**或** 实现降级 / `can_output` 门禁后再标 `[x]`。  
- **1.3、1.4、1.6**：仍建议补齐后再大举投入阶段 2 P0；破例须书面备案。

---

> **阶段闸门**（表格）：未完成阶段 **1** 中标记为 P0 的项前，不启动阶段 **2** 的 P0；以此类推。若需破例，须在 PR 中写明原因并由审查人认可。  
> **状态用语**：`[ ]` 未开始 · `[/]` 进行中 / 部分完成 · `[x]` 已完成（须代码/测试/或已备案差异）· `[!]` 阻塞（在备注写阻塞原因）  
> **最后更新**：2026-05-12 — **作者备注**：1.1 Web 子集已备案；1.5 失败路径 / 护栏走读完成 + `tests/test_pipeline/test_failure_path.py`（11 passed）；**1.5 状态 = `[/]`（非完成）**

### 阶段 1 — 功能代码闭环（后端 / 编排 / 存储 / CLI）

**目标**：同一业务能力从入口到落盘**可测、可复现**；HTTP/API 与 `Orchestrator` **语义一致**；失败、恢复边界清晰。

| ID | 工作项 | 状态 | 备注 / 涉及路径（可填） |
|----|--------|------|-------------------------|
| 1.1 | **API ↔ Orchestrator 对齐审计**：`hagoku run` / `project run` 与 `hagoku-api` 分析入口在参数（template、formats、resume）、错误码、最终 `output_path` / artifacts 上一致或可文档化差异 | [x] | **已备案差异（Web 子集）**：WS `cmd=analyze` 仅接受 `data_path`/`query`/`project_name`/`phase`，CLI 额外支持 `template`/`formats`/`resume`/`output_dir`/`progress_path`/`verbosity`/`interactive`。这是**故意设计**，Web UI 为 CLI 子集，阶段 2 不要求补齐所有参数面。详见 `hagoku/api/ws_handler.py` L161-196。 |
| 1.2 | **WebSocket 会话全路径**：`respond` / `unblock`、断开重连、并发单项目、异常时客户端可理解的错误事件 | [/] | **已有**：`respond`/`unblock`。**待证**：同 Orch 重叠 `run`、重连、错误 JSON。`hagoku/api/ws_handler.py`、`hagoku_web` |
| 1.3 | **Resume / 断点**：`memory.save_resume_state` / `get_resume_state` 与 Orchestrator 阶段机一致；补充或补齐边界用例测试 | [/] | **已有**：存储单测。**待补**：编排 `resume=True` 集成测试。`orchestrator.py`、`memory.py` |
| 1.4 | **Runs / SQLite 一致性**：`create_run`、`complete_run`、`fail_run` 与看板事件；`diff_runs` 与 CLI `history` 输出字段稳定 | [/] | **待点验**：`history` vs DB 字段；审查未逐项执行。`database.py`、`cli.py` |
| 1.5 | **失败与降级**：Agent 失败时 Orchestrator 是否按产品设计降级或终止；护栏 `can_output` 与 Reporter 收紧路径可追踪 | [/] | **走读结论（2026-05-12）**：当前为 **硬终止**（`hagoku/manager/orchestrator.py` 顶层 `except` 约 **L713–L717**：`fail_run` + `RUN_FAILED` + `raise`），**无**降级；`orchestrator.guardrails` **未调用**；`can_output` **未**介入 Reporter；Analyst 对结果做护栏检查并写入 `guardrail_results`、发事件但**不阻塞**下游。行为已由 `tests/test_pipeline/test_failure_path.py`（**11** 项）锁定。**未**实现任务原文若要求的「产品级降级 / 编排层阻断输出」— 待决策后归入阶段 **3.3** 或本产品接受「现状」后改标 `[x]` 并更新 `PROJECT.md`。 |
| 1.6 | **回归测试**：与本阶段改动相关的 `pytest` 全绿；新增用例覆盖上述风险点 | [/] | **已增加**：`tests/test_pipeline/test_failure_path.py`（覆盖 1.5 行为与 `can_output` 语义）。仍须：**WS / resume / history** 等向用例。`pytest tests/ -q`。 |

### 阶段 2 — Web UI 功能适配（对齐 CLI / API 已有能力）

**目标**：还清「CLI 或 API 已有、**Web 无上位替代**」的债务；不预先扩张阶段 3/4 的分析或报表 scope。

| ID | 工作项 | 状态 | 备注 / 涉及路径 |
|----|--------|------|-----------------|
| 2.1 | **跑次 / 历史**：展示当前项目运行列表、状态、时间；可链接到报告或事件（对标 `hagoku history`） | [ ] | `hagoku_web`、需时补 REST `hagoku/api` |
| 2.2 | **回放 / 复盘**：CLI 已有 `hagoku replay` — Web 提供「按 run 查看事件时间线」或等同能力（可重用事件面板增强） | [ ] | `EventPanel`、API/WS |
| 2.3 | **Run diff**：可选展示两次运行关键字段差异（后端已有 `diff_runs` 时优先用 API） | [ ] | `database.diff_runs`、新端点或扩展现有 |
| 2.4 | **导出**：若后端支持 `md`/`json`，Web 提供下载或与报告页一致入口（**PDF 归入阶段 4**） | [ ] | 对齐 `cli` `--format` |
| 2.5 | **项目与数据**：Web 侧「添加数据文件」等与 `hagoku project add` 能力对齐（错误提示、刷新状态） | [ ] | `ProjectPanel`、API |
| 2.6 | **验收**：主要产品路径在 **仅 Web** 下可完成「选项目 → 分析 → 看报告 → 查跑次」不断链 | [ ] | 手动 + 可自动化 E2E 再定 |

### 阶段 3 — 强化分析能力

**目标**：在阶段 1、2 稳定后，加深 Scout / Cleaner / Analyst / 护栏；**不**以牺牲可观测性与可中断性为代价。

| ID | 工作项 | 状态 | 备注 |
|----|--------|------|------|
| 3.1 | **「每检验配诊断图」规范**：定义最小图表集（残差、QQ、杠杆等）与落盘位置；与 `runs/.../diagnostics` 对齐 | [ ] | `hagoku/tools/diagnostics.py`、Analyst |
| 3.2 | **方法库与路由**：`hagoku methods` 与 Orchestrator/Analyst 实际调用路径一致；缺失标签或文档的补齐 | [ ] | `hagoku/tools/analysis.py` |
| 3.3 | **护栏与结构化输出**：强制级违规是否在所有出口阻断；Reporter `validate_analysis_output` 失败时的产品行为（重试/标注） | [ ] | **已知基线（2026-05-12）**：见上文 **走读记录** — Orchestrator **未**用 `can_output`；Analyst 护栏**不**阻 Reporter；`validate_analysis_output` ≠ 护栏引擎。本项为收敛点。 |
| 3.4 | **V3 预备（可选本阶段内 POC）**：因果/时序中单点能力试做须有 feature flag 或明确「非默认路径」 | [ ] | 见 PROJECT.md V3 |

### 阶段 4 — 强化报表功能

**目标**：`default` 双轨体验稳定；多模板、导出与叙事一致；与 `PROJECT.md` 报告章节不冲突。

| ID | 工作项 | 状态 | 备注 |
|----|--------|------|------|
| 4.1 | **PDF（或等价印刷流）**：CLI `--format` 与 `OutputManager`、Reporter 输出链路打通；依赖与可选 extra 在 README 说明 | [ ] | 见 `pyproject.toml` `pdf` extra |
| 4.2 | **非 `default` 模板**：明确与双轨叙述关系（仅文档 vs 模板渐近统一），按产品决策执行 | [ ] | `hagoku/tools/reporting.py` |
| 4.3 | **图表与内联 HTML**：模板中 Plotly/静态图在暗色主题、打印样式下可读性 | [ ] | 模板 CSS、`ReportData` |
| 4.4 | **Web 报告页**：打开最新 HTML、切换 run、下载（与阶段 2 协同） | [ ] | `ReportPanel` |

---

## 审查约定（交 PR / 合并前）

**审查人**：默认由**指派审查者**（或主仓维护者）执行；可要求**本会话 AI** 只做只读审查（对照本文件 + `PROJECT.md`，不改业务口径）。

执行人须在 PR 描述中写明：

1. 对应 **路线图 ID**（如 1.2、2.1）或声明「单轮任务区，非路线图」；
2. **是否更新**上表「状态」列（建议合并后由作者跟进一次 commit 更新 `[ ]` → `[x]`）；**`[x]` 须附**：代码/测试变更或经审查人认可的「已备案差异」文档链接，**禁止仅改 Markdown 勾选**；
3. **对用户可见行为**的截图或简短步骤（Web）/ 命令复现（CLI）。

**审查清单（最低限度）**

- [ ] 行为与 [PROJECT.md](PROJECT.md) 人机互动、双轨报告、环境变量约定无冲突  
- [ ] 未引入重复功能入口（同一操作只在一处主路径）  
- [ ] 相关测试已跑通；API/WebSocket 变更含或可补集成测试  
- [ ] UI 改动符合 `CLAUDE.md`（含表头居中规则、`UI_CHANGELOG.md` 等）  
- [ ] 不擅自扩展阶段 scope（参阅上文阶段闸门）  
- [ ] 路线图状态与实现一致；若此前有误标 `[x]`，已在 `DEVELOPMENT_PROMPT` 中纠正并说明

---

## 单轮任务区（非路线图的一轮需求，可整段替换）

### 背景

（为什么要做：问题 / 用户反馈 / 技术债）

### 目标与范围

- **要做**：

- **明确不做**（缩小边界）：

### 涉及模块（预估）

（例：`hagoku/...`、`hagoku_web/...`、仅文档等）

### 验收标准

- [ ]

### 风险 / 约束

（兼容性、勿改动的文件、与 `PROJECT.md` 冲突时需先对齐文档等）

### 附：转发用一句话（可选）

（可复制到 IM / Issue）

---

_说明：单轮任务完成后可清空本节；**路线图跟踪表**应长期保留并逐步勾选，避免与 `PROJECT.md` 交付物脱节。_
