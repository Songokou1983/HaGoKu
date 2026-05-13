# 开发任务传递（DEVELOPMENT_PROMPT）

> **用途**：① **路线图跟踪**（四阶段 backlog，可勾选、可转发）；② **单轮任务骨架**（复制给 AI/协作者的一轮规格）。  
> **真相源**：[PROJECT.md](PROJECT.md)（含「交付物规划」「迭代执行顺序」）。本文件任务状态**由执行人合并后更新**；**审查**见下文「审查约定」。

---

## 修改代码前必读（口径）

| 文档 | 用途 |
|------|------|
| [PROJECT.md](PROJECT.md) | 灵魂、Agent、人机互动、双轨报告、交付物、**迭代执行顺序** |
| [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) | 设计手册、测试与 Playwright/React 说明 |
| [docs/INTERACTION_MULTITURN_PLAN.md](docs/INTERACTION_MULTITURN_PLAN.md) | **多轮对齐互动**：目标态、现状差距、分期实施与验收 |
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
| 1.5 `[x]` | **部分曾不成立 → 已收敛一栏** | 见 **「走读记录」**：**编排层**在 Reporter 前已对**强制级统计护栏**做 `can_output` 门禁（不通过则跳过正式报告）；**Agent 级失败**仍为硬终止、**无**产品级降级 — 故工作项整体仍为 **`[/]`**。 |
| 1.6 `[x]` | **仍部分成立** | 已增加 `tests/test_pipeline/test_failure_path.py`（**12** 项）固化 1.5 相关行为；**不**覆盖 1.1–1.4 全风险面。 |

#### 走读记录（2026-05-12）— 失败路径与统计护栏（对照 `hagoku/manager/orchestrator.py`）

以下已由人工走读 + **本仓库测试文件**交叉验证（`pytest tests/test_pipeline/test_failure_path.py` → **12 passed**）。

| 观测 | 位置 / 说明 |
|------|-------------|
| **Agent 异常 → 硬终止（无降级）** | `Orchestrator.run` 顶层 `except Exception`：`fail_run` → 发射 `RUN_FAILED` → **`raise`**（约 **L818–L822**）。无 fallback / retry 等分支。 |
| **编排层强制级护栏 → 阻断正式报告** | `_mandatory_guardrails_block_report`（`orchestrator.py` 约 **L243**）对 Analyst 结构化结果逐条 `guardrails.check`；任一条 **`not can_output`** 则在 **Reporter 之前**返回阻断：写入 `run_dir/output/GUARDRAILS_BLOCKED.md`，`QUALITY_CHECK` 失败类事件，**不调用** `ReporterAgent.run`，`complete_run` 仍执行，`save_resume_state` 阶段为 **`analyzed`**，返回 **`status: "guardrails_blocked"`**（`run()` 内约 **L646–L717** 一带，以当前文件为准）。 |
| **`can_output` 与 Reporter** | **已**介入编排层门禁（见上）；CLI `hagoku run` / `project run` / `demo` 对 `guardrails_blocked` **exit 0** 并提示说明文件路径。 |
| **Analyst 侧护栏** | `AnalystAgent` 内对每条结果 `guardrails.check`，写入 `result["guardrail_results"]`，并对违规发 `QUALITY_CHECK`；**仍不**在 Analyst 内 `return` / 抛错阻断下游 — **是否出正式报告由编排层门禁决定**。 |
| **≠ `validate_analysis_output`** | Reporter 使用文本解析器做结构检查；与护栏引擎 **`check` / `can_output`** **不是同一套逻辑**（见测试文件内说明）。 |

**结论（1.5 工作项怎么算）**：  
- **「路径可说明、可测试、可复现」** → ✅ 已满足（本走读 + `test_failure_path.py`）。  
- **「编排层：强制级护栏未通过则不出正式 HTML 报告」** → ✅ **已实现**（见上表与单测）。  
- **「Agent 失败时产品级降级（非硬终止）」** → ❌ **当前未实现**；若 `PROJECT.md` 定为硬性要求，应作为后续 PR / **3.3** 等收敛。  
- **1.5 整体状态**：工作项标题含 **「失败与降级」**，护栏子项已落地，**降级子项仍未** — 表格中保持 **`[/]`**，**不得**因仅完成护栏而整条标 `[x]`。

**阶段闸门（执行，修订）**：  
- **1.1**：若以「Web 子集」备案为准，可视为文档闭环。  
- **1.5**：保持 **`[/]`**，直至「Agent 失败降级」有明确产品结论（接受硬终止并改 `PROJECT.md` **或** 实现降级路径）后再标 `[x]`。  
- **1.3、1.4、1.6**：仍建议补齐后再大举投入阶段 2 P0；破例须书面备案。

---

> **阶段闸门**（表格）：未完成阶段 **1** 中标记为 P0 的项前，不启动阶段 **2** 的 P0；以此类推。若需破例，须在 PR 中写明原因并由审查人认可。  
> **状态用语**：`[ ]` 未开始 · `[/]` 进行中 / 部分完成 · `[x]` 已完成（须代码/测试/或已备案差异）· `[!]` 阻塞（在备注写阻塞原因）  
> **最后更新**：2026-05-14 — **作者备注**：**护栏 × 沟通**清单 **P0–P2 全勾**（含 `wsGuardrails` 与 **`tests/test_web/test_ws_guardrails_parity.py`** Python 镜像契约）。**2.7 → `[x]`**。**1.5** 仍为 **`[/]`**（Agent 失败无降级）。**2.8.1 / 2.8.2** Scout 多轮与前端卡片已落地；**2.8.0** 书面词表与场景剧本仍建议补；**2.8.4** 契约与回归测已闭；**2.8.3** 仍为 **`[/]`**（Cleaner/Analyst 同构待拆）。**路线图其余 2.1–2.6 / 3.x / 4.x** 仍为各表原状态，非本轮闭合并入范围。  
> **设计手册对齐**：`docs/DEVELOPMENT.md`「测试方法」已补 **pytest 子集**（`tests/test_api/`、`test_ws_guardrails_parity`）、**UI 手动步骤** 5–7（报告按 run / 护栏拦截 / 事件与 API 一致）；`PROJECT.md`「Web UI 当前形态」已补护栏 run 与说明；`docs/TROUBLESHOOTING.md` §8 汇总复现与验证命令。  
> **多轮对齐互动（方案 / 分期）** → [docs/INTERACTION_MULTITURN_PLAN.md](docs/INTERACTION_MULTITURN_PLAN.md)（编排 + 分析页后续 PR 以此为准；进度在下方 **阶段 2.8** 勾选）。

### 阶段 2.8 — 多轮对齐式互动（编排 + Web）

| ID | 工作项 | 状态 | 备注 |
|----|--------|------|------|
| 2.8.0 | **Phase 0**：对齐判定规则 + 3 条场景剧本评审 | [/] | **代码侧**已有 `_scout_reply_is_pure_confirm` / `_is_scout_aligned`；**书面**词表（如「可以了」）与 3 条剧本仍建议产品补全，见 `INTERACTION_MULTITURN_PLAN.md` §2.2 |
| 2.8.1 | **Phase 1**：Scout 字段理解子状态机 + `interaction_revision` + pytest | [x] | `hagoku/manager/orchestrator.py`（Scout 段 `while`；`_is_scout_aligned`；合约测于 `test_agent_interaction_contract.py`） |
| 2.8.2 | **Phase 2**：`AnalyzePanel` 多轮同阶段暂停 UI | [x] | `activeFieldReviewRevision`；revision 递增时原地更新卡片 |
| 2.8.3 | **Phase 3**：跨阶段闸门 + Cleaner/Analyst 同构 | [/] | **Scout→Cleaner 闸门**已落地（`_is_gate_confirm`；`gate_cleaning_pause_payload`；AnalyzePanel gate UI）；**Cleaner/Analyst 同构**仍待（可拆 PR） |
| 2.8.4 | **契约**：`AGENT_INTERACTION_CONTRACT.md` C4 扩展 + 回归测 | [x] | C4 已含闸门行为（禁止未对齐进清洗）；`test_agent_interaction_contract.py` 新增闸门测（`_is_gate_confirm` 等 3 条） |

---

### 护栏 × 沟通 — 实现清单（`PROJECT.md` 原则落地）

> **产品锚点**：[PROJECT.md](PROJECT.md) →「统计护栏 — 三级安全网」→ **产品原则（护栏 × 报告 × 沟通）**。  
> **技术锚点（已实现，供对照）**：`Orchestrator.run` 在强制级未通过时发射 `QUALITY_CHECK`（`verdict: fail`）、`AGENT_COMPLETED` / `reporter`（`skipped: true`）、`RUN_COMPLETED` / `manager`（`guardrails_blocked: true`，**且含 `run_id`、`project`**），落盘 `runs/{run_id}/output/GUARDRAILS_BLOCKED.md`；WS 经 `Event.to_dict()` 原样转发 `data`。  
> **落地进度（2026-05-14）**：**P0–P2** 已合入。其中 **P2 前端解析**：`hagoku_web/src/utils/wsGuardrails.ts`（`AnalyzePanel` / `EventPanel` 引用）+ **`tests/test_web/test_ws_guardrails_parity.py`**（逻辑镜像、**`pytest` 常驻绿**）；**P2 API 契约**：`tests/test_api/`。  
> 下列项按 **P0 → P1 → P2** 排期；执行人改完自勾选，并在 PR 中写明对应编号。

#### P0 — 分析页：拦截态 ≠ 成功出报告

- [x] **`AnalyzePanel`（或等价分析主面板）**：处理 `event_type === "run_completed"` 且 `data.guardrails_blocked === true` 时，进入 **`guardrails_blocked` 终态**（文案、配色与「分析成功 / 报告已就绪」区分，避免误导）。
- [x] **冗余校验**：`agent === "reporter"` 且 `event_type === "agent_completed"` 且 `data.skipped === true` 时，与同终态一致，避免只订阅半程事件时状态错误。
- [x] **禁止假成功**：上述终态下 **不**设置「打开双轨 HTML」的成功 URL（例如当前依赖的 `/api/reports/{project}` 默认最新 HTML 的路径在拦截 run 上可能不适用）。
- [x] **对话区（互动性）**：插入一条 **Agent 或 system 气泡**，说明「强制级统计护栏未通过、未生成正式 HTML 报告」，并引用简短原因或引导查看全文（文案可与 CLI `guardrails_blocked` 提示一致）。
- [x] **可操作 CTA**：至少一个入口 **「查看护栏说明」**（或同级措辞）：**图标 + 文字**（`CLAUDE.md` 按钮规范）。链接到 P0 API 可读到的 `GUARDRAILS_BLOCKED.md` 全文（新标签或侧栏/模态均可，产品自定）。
- [x] **流水线进度 UI**：Reporter 步骤显示 **已跳过 / 未产出正式报告**（不得与绿色「已完成」混淆）。

#### P0 — API：Web 不依赖本机路径读说明

- [x] **HTTP GET** 能拉取当次说明正文：优先复用现有 `GET /api/reports/{project_name}/{run_id}/{filename}`（文件名 `GUARDRAILS_BLOCKED.md`）；若列表/发现入口不展示该文件，则 **补路由或补 `list_reports`/`runs` 元数据**，使前端可拼出稳定 URL。
- [x] **`GET /api/projects/{project}/detail` 或 `.../runs`**：在「最近一次 run」或列表项中带 **`guardrails_blocked: boolean`**（或 `status: "guardrails_blocked"`），避免前端仅靠事件丢失状态（重连、刷新后仍可恢复）。
- [x] **验收**：仅开浏览器、不打开本地 `~/.hagoku` 目录，即可完成「触发拦截 → 读说明 → 理解未出 HTML」。

#### P1 — 报告页与跑次呈现

- [x] **`ReportPanel`**：若当前/所选 run 为护栏拦截（依据 run 元数据或报告列表含 `GUARDRAILS_BLOCKED.md`），**不**展示「双轨 HTML 成功预览」为默认态；改为说明 + 链接/内嵌 Markdown（与 `PROJECT.md`「真诚、可穿透」一致）。
- [x] **`EventTable` / 跑次列表**：`run_completed` + 护栏拦截有**独立**展示（标签或文案），不与「成功完成」混用。
- [x] **`useAgentStatusSync` / 项目状态**：若全局状态仅有 `completed`/`running`，扩展 **`guardrails_blocked`**（或映射到「已完成但拦截」），避免项目卡片误显示「已完成」而实际无 HTML。（**已做**：`AgentStatus` 含 `skipped`；`ProjectPanel` 识别 `last_status: guardrails_blocked`。）

#### P2 — 测试、回归与文档

- [x] **契约**：断言经 WS 广播的 `run_completed` / `reporter` `agent_completed` payload 含 `guardrails_blocked` / `skipped` / `run_id`（`tests/test_api/test_ws_handler.py`：`TestGuardrailsWSPayloadContract`）；REST `runs`/`detail` 护栏语义见 `tests/test_api/test_server.py`。`test_api` 已改为 **`asyncio.run`** 包装原 async 用例，**不依赖**测试运行器安装 **`pytest-asyncio`**。
- [x] **前端**：对解析 WS `data` 的分支：**`hagoku_web/src/utils/wsGuardrails.ts`** + **`tests/test_web/test_ws_guardrails_parity.py`**（与 TS 同步；修改任一方须对齐）。
- [x] **`README.md` 或用户可见帮助**（一两句）：说明「护栏未通过时不会生成正式 HTML，但会留说明文件」。
- [x] **UI 改动**：按 `CLAUDE.md` 备份 + `UI_CHANGELOG.md` 记录涉及文件。

**路线图交叉引用**：阶段 2 表 **2.7**（**`[x]`** 护栏 Web 已闭环）；阶段 3 **3.3**（见表内 **2026-05-14** 点验：生产路径 **Reporter 仅 `orchestrator.py`**；`validate_analysis_output` 仍待产品定）。

### 阶段 1 — 功能代码闭环（后端 / 编排 / 存储 / CLI）

**目标**：同一业务能力从入口到落盘**可测、可复现**；HTTP/API 与 `Orchestrator` **语义一致**；失败、恢复边界清晰。

| ID | 工作项 | 状态 | 备注 / 涉及路径（可填） |
|----|--------|------|-------------------------|
| 1.1 | **API ↔ Orchestrator 对齐审计**：`hagoku run` / `project run` 与 `hagoku-api` 分析入口在参数（template、formats、resume）、错误码、最终 `output_path` / artifacts 上一致或可文档化差异 | [x] | **已备案差异（Web 子集）**：WS `cmd=analyze` 仅接受 `data_path`/`query`/`project_name`/`phase`，CLI 额外支持 `template`/`formats`/`resume`/`output_dir`/`progress_path`/`verbosity`/`interactive`。这是**故意设计**，Web UI 为 CLI 子集，阶段 2 不要求补齐所有参数面。详见 `hagoku/api/ws_handler.py` L161-196。 |
| 1.2 | **WebSocket 会话全路径**：`respond` / `unblock`、断开重连、并发单项目、异常时客户端可理解的错误事件 | [/] | **已有**：`respond`/`unblock`。**待证**：同 Orch 重叠 `run`、重连、错误 JSON。`hagoku/api/ws_handler.py`、`hagoku_web` |
| 1.3 | **Resume / 断点**：`memory.save_resume_state` / `get_resume_state` 与 Orchestrator 阶段机一致；补充或补齐边界用例测试 | [/] | **已有**：存储单测。**待补**：编排 `resume=True` 集成测试。`orchestrator.py`、`memory.py` |
| 1.4 | **Runs / SQLite 一致性**：`create_run`、`complete_run`、`fail_run` 与看板事件；`diff_runs` 与 CLI `history` 输出字段稳定 | [/] | **待点验**：`history` vs DB 字段；审查未逐项执行。`database.py`、`cli.py` |
| 1.5 | **失败与降级**：Agent 失败时 Orchestrator 是否按产品设计降级或终止；护栏 `can_output` 与 Reporter 收紧路径可追踪 | [/] | **走读结论（2026-05-12，修订）**：**Agent 异常**仍为 **硬终止**（`orchestrator.py` 顶层 `except` 约 **L818–L822**：`fail_run` + `RUN_FAILED` + `raise`），**无**降级。**编排层**：`_mandatory_guardrails_block_report` 在 Reporter 前对结果调用 `guardrails.check`；强制级 **`not can_output`** 时跳过 Reporter，写 **`GUARDRAILS_BLOCKED.md`**，返回 **`guardrails_blocked`**，resume 阶段 **`analyzed`**。Analyst 仍只写入 `guardrail_results` / 事件，**由编排层**决定是否出正式报告。`tests/test_pipeline/test_failure_path.py`（**12** 项）。**仍缺**：产品级「失败降级」若需要则另 PR；本条 **`[/]`** 直至降级口径闭合。 |
| 1.6 | **回归测试**：与本阶段改动相关的 `pytest` 全绿；新增用例覆盖上述风险点 | [/] | **已增加**：`tests/test_pipeline/test_failure_path.py`；**护栏 Web**：`tests/test_api/`、`tests/test_web/test_ws_guardrails_parity.py`。仍须：resume / history 等。`pytest tests/ -q`。 |

### 阶段 2 — Web UI 功能适配（对齐 CLI / API 已有能力）

**目标**：还清「CLI 或 API 已有、**Web 无上位替代**」的债务；不预先扩张阶段 3/4 的分析或报表 scope。

| ID | 工作项 | 状态 | 备注 / 涉及路径 |
|----|--------|------|-----------------|
| 2.1 | **跑次 / 历史**：展示当前项目运行列表、状态、时间；可链接到报告或事件（对标 `hagoku history`） | [/] | **子集已达**：`ReportPanel` 经 `GET /api/projects/{name}/runs` **按运行**列护栏/HTML（见 2.7）。**仍缺**：对标 CLI `history` 的全局列表、更丰富元数据等。 |
| 2.2 | **回放 / 复盘**：CLI 已有 `hagoku replay` — Web 提供「按 run 查看事件时间线」或等同能力（可重用事件面板增强） | [ ] | `EventPanel`、API/WS |
| 2.3 | **Run diff**：可选展示两次运行关键字段差异（后端已有 `diff_runs` 时优先用 API） | [ ] | `database.diff_runs`、新端点或扩展现有 |
| 2.4 | **导出**：若后端支持 `md`/`json`，Web 提供下载或与报告页一致入口（**PDF 归入阶段 4**） | [ ] | 对齐 `cli` `--format` |
| 2.5 | **项目与数据**：Web 侧「添加数据文件」等与 `hagoku project add` 能力对齐（错误提示、刷新状态） | [ ] | `ProjectPanel`、API |
| 2.6 | **验收**：主要产品路径在 **仅 Web** 下可完成「选项目 → 分析 → 看报告 → 查跑次」不断链 | [ ] | 手动 + 可自动化 E2E 再定 |
| 2.7 | **护栏拦截（Web）**：`guardrails_blocked` 终态、说明可读、对话引导；与 CLI / `PROJECT.md` 产品原则一致 | [x] | **护栏 Web 闭环**（清单 P0–P2）。含 `wsGuardrails.ts`、`tests/test_web/test_ws_guardrails_parity.py`、`tests/test_api/` 等；见 **「护栏 × 沟通 — 实现清单」**。 |

### 阶段 3 — 强化分析能力

**目标**：在阶段 1、2 稳定后，加深 Scout / Cleaner / Analyst / 护栏；**不**以牺牲可观测性与可中断性为代价。

| ID | 工作项 | 状态 | 备注 |
|----|--------|------|------|
| 3.1 | **「每检验配诊断图」规范**：定义最小图表集（残差、QQ、杠杆等）与落盘位置；与 `runs/.../diagnostics` 对齐 | [ ] | `hagoku/tools/diagnostics.py`、Analyst |
| 3.2 | **方法库与路由**：`hagoku methods` 与 Orchestrator/Analyst 实际调用路径一致；缺失标签或文档的补齐 | [ ] | `hagoku/tools/analysis.py` |
| 3.3 | **护栏与结构化输出**：强制级违规是否在所有出口阻断；Reporter `validate_analysis_output` 失败时的产品行为（重试/标注） | [/] | **基线（2026-05-14）**：仓库检索 **`ReporterAgent.run`** 仅 **`hagoku/manager/orchestrator.py`** 主路径；**WebSocket** `_run_analysis` 同该编排。**强制级护栏**与 CLI 一致。*仍待产品定*：`validate_analysis_output` 失败策略；若未来新增「绕过编排直调 Reporter」入口须复用 `_mandatory_guardrails_block_report`。 |
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
