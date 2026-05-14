# UI 改动日志

> 带日期的章节为**当时**的改动实录，可能仍出现已弃用的技术或布局描述（例如旧版 dockview / Streamlit）。**当前**产品形态、环境约定与互动流程以 [PROJECT.md](PROJECT.md)、[README.md](README.md) 为准。

## 2026-05-14 — 分析页：去掉「插入纠错」与表格行点选

### 变更概要

- **`AnalyzePanel.tsx`**：字段核对表改为只读展示；删除「插入纠错」「取消点选」及 `Col=` 快捷插入；补充与异议一律在输入框用自然语言说明，由后端写入上下文并进入后续 Agent 步骤。修复误删的 `submitUserReply` `useCallback` 声明。

## 2026-05-14 — 分析暂停点：强确认按钮分步露出

### 变更概要

- **`AnalyzePanel.tsx`**：字段核对 / 清洗确认 / 分析确认 / 进清洗闸门处，默认只显示「我已核对，显示确认选项」；用户点过后再显示「确认无误」「确认继续」「确认进清洗」等按钮。`插入纠错` 仍始终可用。每次 `user_input_requested`、重置、取消分析时收起该条。

## 2026-05-14 — 分析暂停点：禁止空回复/回车当作「已确认」

### 变更概要

- **前端 `AnalyzePanel.tsx`**：去掉「留空 + Enter = 确认」；`canSendReply` 仅在有非空输入时为真；「确认无误 / 确认继续」按钮改为发送明确文案（不再 `submitUserReply("")`）。闸门仍用「确认进清洗」「还有补充」按钮或手输同义句。
- **后端 `orchestrator.py`**：`_scout_reply_is_pure_confirm` 对**空串**不再视为确认；扩展短语含 `确认无误` / `确认进清洗` / `确认继续`；`_is_gate_confirm` 对**空串**不再进清洗。
- **单测**：契约与 Scout 回复用例对齐新语义。

## 2026-05-14 — 中文输入法：对话区 Enter 不打断组字

### 变更概要

- **`AnalyzePanel.tsx`**：底部回复框 `Enter` 发送前检测 `nativeEvent.isComposing` / `keyCode === 229`，IME 选词确认时不 `preventDefault`。
- **`InputBar.tsx`**、**`ProjectPanel.tsx`**：同类 `Enter` 逻辑同样避开组字阶段。

## 2026-05-13 — 分析页：WebSocket 进度文案不再成对重复

### 变更概要

- **`hagoku/api/ws_handler.py`**：去掉每个 WS 连接上对 `bridge.on_event` 的 `subscribe`/`unsubscribe`。共享 Orchestrator 创建时已订阅一次；重复订阅会导致一次 `emit` 多次 `broadcast`，分析页「理解你的问题」「正在加载数据」等每条出现两遍。
- **回归修复**：`lifespan` / `main` 会先 `set_orchestrator` 再接受分析请求，此时 `_run_analysis` 不再走「新建实例」分支，原先仅靠该分支 `subscribe`，去掉按连接订阅后事件总线未接 WSBridge，表现为点了「开始分析」无推送。现改为在 **`set_orchestrator` 与每次 `_run_analysis`** 中幂等 `subscribe`；**`EventBus.subscribe`** 对同一 callback 只注册一次。

## 2026-05-13 — 知识库：条目点进查看正文

### 变更概要

- **`hagoku/api/server.py`**：新增 **`GET /api/kb/content?filename=`**，仅允许 `_registry.yaml` 已登记路径；返回 Markdown 正文转 HTML（依赖 `markdown`）；与 `GET /api/kb` 共用注册表加载逻辑。
- **`hagoku_web/src/panels/KnowledgePanel.tsx`**：列表卡片可点进详情；详情顶栏 **返回列表**（图标+文字）；正文 `dangerouslySetInnerHTML` 展示服务端 HTML。
- **`hagoku_web/src/index.css`**：`.kb-detail-html` 下表格表头居中、正文单元格左对齐等排版。
- **`pyproject.toml`**：增加运行时依赖 `markdown>=3.5`。
- **`tests/test_api/test_server.py`**：`TestKbContent` 契约测。
- **`README.md`**：UI 功能一句中带知识库详情。

## 2026-05-13 — 设置页：「高级设置」折叠（MODEL_QUICK）

### 变更概要

- **`hagoku_web/src/panels/SettingsPanel.tsx`**：在「模型名称」下增加 **高级设置** 折叠区（图标 + 文案）；展开后说明 `HAGOKYU_LLM_MODEL` / `MODEL_DEEP` / `MODEL_QUICK` 分工，并可填 `MODEL_QUICK`；默认收起；若本机已配置 QUICK≠主则自动展开并带出值；展开状态可写入 `localStorage` 键 `hagoku_settings_advanced_llm_open`。

### 涉及文件

- `hagoku_web/src/panels/SettingsPanel.tsx`
- `PROJECT.md`

## 2026-05-13 — 设置页移除项目路径；报告页说明另存为

### 变更概要

- **`hagoku_web/src/panels/SettingsPanel.tsx`**：去掉「项目数据放在哪（只读）」；`GET /api/config` 不再依赖 `projects_root`。
- **`hagoku_web/src/panels/ReportPanel.tsx`**：顶部增加说明——打开报告后用浏览器 **另存为** / **打印为 PDF** 保存到自选位置。
- **`hagoku/api/server.py`**：`GET /api/config` 不再返回 `projects_root`；`_projects_root()` 与 `HaGoKuConfig.output.project_dir`（含 `HAGOKYU_PROJECT_DIR`）一致，与 Orchestrator 写盘对齐。
- **`README.md` / `PROJECT.md` / `DEV.md` / `.env.example`**：同步项目目录与报告导出说明。
- **`tests/test_api/test_server.py`**：`GET /api/config` 契约去掉 `projects_root`。

### 涉及文件

- `hagoku/api/server.py`
- `hagoku_web/src/panels/SettingsPanel.tsx`
- `hagoku_web/src/panels/ReportPanel.tsx`
- `README.md`、`PROJECT.md`、`DEV.md`、`.env.example`
- `tests/test_api/test_server.py`

## 2026-05-14 — 设置页：LLM 主模型 + 副模型（两格）

### 变更概要

- **`hagoku/api/server.py`**：`POST /api/config/llm` 请求体改为 `main_model` + `sub_model`（副留空则与主相同）；写入时 `HAGOKYU_LLM_MODEL` 与 `HAGOKYU_LLM_MODEL_DEEP` 均为主，`HAGOKYU_LLM_MODEL_QUICK` 为副。`GET /api/config` 的 `llm` 增加 `main_model`、`sub_model`（与主相同时 `sub_model` 为空串便于表单展示），仍保留 `model` / `model_quick` / `model_deep` 供兼容。
- **`hagoku_web/src/panels/SettingsPanel.tsx`**：模型配置改为「主模型」「副模型（前面轻快步）」两栏，去掉第三格。
- **`tests/test_api/test_server.py`**：`TestConfigEndpoints` 随契约更新。
- **修订（文案）**：去掉「主模型 / 副模型」用语；改为「模型名称」+「可选：前面几步用另一个模型名」；保存校验提示改为「网址和模型名称不能为空」。
- **修订（设置页）**：去掉第二格模型名输入；本页只配置一个模型名，保存时始终与前面步骤统一。若 `.env` 里曾拆开两个名字，仅提示保存后会合并。

### 涉及文件

- `hagoku/api/server.py`
- `hagoku_web/src/panels/SettingsPanel.tsx`
- `tests/test_api/test_server.py`

## 2026-05-14 — 设置页：LLM 地址 / 模型 / Key + 写入 ~/.hagoku/.env

### 变更概要

- **`hagoku/api/server.py`**：`GET /api/config` 返回 `llm`（含 `api_key_configured`）与 `projects_root`；新增 **`POST /api/config/llm`** 写入 `HAGOKYU_LLM_*`。
- **`hagoku_web/src/panels/SettingsPanel.tsx`**：移除错误的「8000 + 提供商下拉 + 仅 localStorage」；改为常规三项 + 可选快速/深度模型；保存走 API。
- **修订**：设置页改为白话文案（去掉 Base URL、环境变量名、Agent 英文名）；保存成功提示改为口语「重启后端」。
- **修订**：去掉模型区分组边框；保存时快/深若留空则写入与默认相同；分析页闸门下不再隐藏输入框。
- **`tests/test_api/test_server.py`**：`TestConfigEndpoints` 契约测。

### 涉及文件

- `hagoku/api/server.py`
- `hagoku_web/src/panels/SettingsPanel.tsx`
- `tests/test_api/test_server.py`

---

## 2026-05-14 — Scout：字段描述 LLM 模型名修复 + 分析页展示思考事件

### 变更概要

- **`hagoku/agents/scout/agent.py`**：`_generate_field_descriptions` 中误用未定义变量 `model`，导致请求未发出；改为 `model_quick or model`；补充「正在调用模型…」thinking；自建 OpenAI 客户端增加 `timeout`。
- **`hagoku/llm/client.py`**：结构化 LLM 工厂为 `OpenAI` 增加 **120s** 超时，避免推理服务无响应时无限挂起。
- **`hagoku_web/src/panels/AnalyzePanel.tsx`**：将 `agent_thinking` 以系统提示展示在对话区，避免仅管道转圈、聊天区空白。

### 涉及文件

- `hagoku/agents/scout/agent.py`
- `hagoku/llm/client.py`
- `hagoku_web/src/panels/AnalyzePanel.tsx`

---

## 2026-05-14 — WebSocket：开发环境走 Vite 代理 + 回复失败可见

### 变更概要

- **`hagoku_web/src/hooks/useWebSocket.ts`**：`import.meta.env.DEV` 下默认 `ws(s)://{当前页面 host}/ws`，经 Vite 代理到后端；`send()` 返回是否已写出。
- **`hagoku_web/src/panels/AnalyzePanel.tsx`**：`respond` 未发出时插入系统提示；处理 WS `error` / `ack(respond)`，对「无暂停 / 无编排器」类错误恢复 `waitingAgent` 与 `gateOpen`。

### 涉及文件

- `hagoku_web/src/hooks/useWebSocket.ts`
- `hagoku_web/src/panels/AnalyzePanel.tsx`

---

## 2026-05-14 — AnalyzePanel：闸门暂停保留字段审查卡片锚点

### 变更概要

- **`hagoku_web/src/panels/AnalyzePanel.tsx`**：`user_input_requested` 仅含 `gate`、不含 `field_review` 时**不再**清空 `activeFieldReviewId` / `activeFieldReviewRevision`，避免「还有补充」回到 Scout 字段对齐后无法按 `interaction_revision` 原地更新同一张卡片。

### 涉及文件

- `hagoku_web/src/panels/AnalyzePanel.tsx`

---

## 2026-05-14 — 多轮对齐：文档同步（转发包）

### 变更概要

- **`docs/INTERACTION_MULTITURN_PLAN.md`**：§2 改为「前后对照 + 剩余缺口」；§4 验收勾选与 §5 Phase 0–2 **落地状态**同步。
- **`docs/AGENT_INTERACTION_CONTRACT.md`**：新增 **C4**（Scout 多轮 + `interaction_revision`）；§2 锚点表、§3 pytest 说明、§4 缺口表述更新。
- **`DEVELOPMENT_PROMPT.md`**：**阶段 2.8** 表（2.8.0→`[/]`、2.8.4→`[/]`）与 **最后更新**作者备注同步审查结论。
- **`docs/DEVELOPMENT.md`**：人机互动小节补充 **Scout 已落地 / 仍缺口** 一句。

### 涉及文件

- `docs/INTERACTION_MULTITURN_PLAN.md`
- `docs/AGENT_INTERACTION_CONTRACT.md`
- `DEVELOPMENT_PROMPT.md`
- `docs/DEVELOPMENT.md`

---

## 2026-05-13 — 互动场景夹具（可执行剧本，对照编排 + Web 分析页）

### 变更概要

- 新增 **`tests/fixtures/interaction_scenarios/full_web_pause_flow.json`**：按 WebSocket `event` 形状写出「三次结构化暂停 + 收尾」时间线；`steps[].note` 给人读，`gap` 标出与「话术动态」之间的差距。
- 新增 **`hagoku/devtools/interaction_scenarios.py`** 校验器、**`scripts/simulate_interaction_scenario.py`**（`--validate-all` / `--script`）、**`tests/test_product/test_interaction_scenarios.py`**。
- **`docs/AGENT_INTERACTION_CONTRACT.md`** 增加 §5 指向上述资产。

### 涉及文件

- `tests/fixtures/interaction_scenarios/full_web_pause_flow.json`
- `hagoku/devtools/__init__.py`、`hagoku/devtools/interaction_scenarios.py`
- `scripts/simulate_interaction_scenario.py`
- `tests/test_product/test_interaction_scenarios.py`
- `docs/AGENT_INTERACTION_CONTRACT.md`

---

## 2026-05-13 — Analyst 暂停：结构化 `analyst_review`（与 Scout/Cleaner 同权）

### 变更概要

- **`hagoku/manager/orchestrator.py`**：完整流水线在 Analyst 完成后暂停时改用 **`analyst_review_pause_payload`**（`message` 为空、结果表结构化），**不再**调用 `_generate_pause_message("analyst")` 用 LLM 生成整段「台词」。**（续）**载荷每行含 **`p_value`**、**`effect_summary`**、**`confidence_interval`**（与「精、准、狠」三要素一致）。
- **`hagoku_web/src/panels/AnalyzePanel.tsx`**：解析并渲染 **`analyst_review`** 工作流表（表头居中、表体左对齐）；表列含 **p 值 / 效应量 / 置信区间**；Cleaner 仅 **「确认继续」**，Analyst 另增 **「同意进入报告」**（图标+文字，写入用户回复事件）。
- **`docs/AGENT_INTERACTION_CONTRACT.md`**、**`tests/test_product/test_agent_interaction_contract.py`**：C2 扩展至 Analyst；契约测试覆盖三要素字段。

### 涉及文件

- `hagoku/manager/orchestrator.py`（备份：`hagoku/manager/UI_CHANGELOG_backup_20260513061101_orchestrator_analyst_review.py`）
- `hagoku_web/src/panels/AnalyzePanel.tsx`（备份：`hagoku_web/src/panels/UI_CHANGELOG_backup_20260513061101_AnalyzePanel_analyst_review.tsx`）
- `docs/AGENT_INTERACTION_CONTRACT.md`
- `tests/test_product/test_agent_interaction_contract.py`

---

## 2026-05-12 — Scout 暂停：结构化 `field_review` + Web 真表格（非 Markdown 气泡）

### 变更概要

- **`hagoku/manager/orchestrator.py`**：Scout 字段暂停后 **`apply_scout_user_field_reply_to_context`**（`Code=…`、`means`、中文连接词等写入 `column_descriptions`，纯确认不写库；`user_input_received` 带 **`applied_field_updates`**）。Cleaner 暂停 **`cleaning_review_pause_payload`**：`rows_removed`、**`_cleaning_quality_display`**（不再甩 `unknown`）、`impact_rate` 以报告为准并兼容编排传入兜底；**不再**调用会触发写死 fallback 的 `_generate_pause_message("cleaner")`。**根因**：`CleaningOp` 无 `.get`，Cleaner 分支曾抛错后**每次**落入 `_fallback_pause_message` 固定中文。另：**`_normalize_cleaning_operation`** 统一 `CleaningOp`/dict 供 prompt 回退路径。
- **`hagoku_web/src/panels/AnalyzePanel.tsx`**：`user_input_requested` 若含 `field_review`，插入 **`workflow` 角色**卡片并渲染 **HTML `<table>`**（表头 `text-center`，表体左对齐）；`message` 仅在有内容时追加为普通 agent 气泡，不设预设「Agent 台词」。**交互**：当前暂停点与表格消息 id 对齐时可点选行高亮、**「插入纠错」**写入 `字段名=`、**「确认无误」**或空内容 **Enter** 发送确认（与编排层空字符串一致）；输入区在有点选时轻微强调边框。收到 **`user_input_received`** 且含 **`applied_field_updates`** 时插入一条**系统**提示（事实反馈，非拟人 Agent）。**Cleaner**：解析 **`cleaning_review`** 工作流表；**「确认继续」**或空 **Enter** 与 Scout 同权；卡片去掉流程说教句，事实行用 `abbr`/`title` 区分删行影响率与列级「影响行」；Scout 表头缩为单行事实。
- **`tests/test_manager/test_scout_field_review_payload.py`**：`scout_field_review_pause_payload` 形状契约测试。
- **`tests/test_manager/test_scout_user_reply_apply.py`**：用户纠错句写入 `context` 的契约测试。
- **`tests/test_manager/test_cleaning_review_payload.py`**：`cleaning_review_pause_payload` / `_normalize_cleaning_operation` 契约测试。

### 涉及文件

- `hagoku/manager/orchestrator.py`（若本轮有改，以当次备份为准）
- `hagoku_web/src/panels/AnalyzePanel.tsx`（备份：`hagoku_web/src/panels/UI_CHANGELOG_backup_*_AnalyzePanel_field_review.tsx`）
- `tests/test_manager/test_scout_field_review_payload.py`
- `tests/test_manager/test_scout_user_reply_apply.py`
- `tests/test_manager/test_cleaning_review_payload.py`

---

## 2026-05-12 — Scout：字段说明不再是「列名抄一遍+类型」

### 变更概要

- **`scout/agent.py`**：字段描述 LLM 提示改为**业务含义向**、禁止统计类型词与「列名（类型）」式输出；去掉原先「未生成则写入 `列名（数值型）`」的兜底（无描述则视为待用户补充）。
- **`orchestrator.py`**：`_scout_field_digest_for_user` 展示前用 `_scout_description_is_meaningful_for_user` 过滤旧占位串，避免再把「BU（分类型）」当成有效理解。
- **`tests/test_agents/test_agents.py`**：`TestScoutUserFacingDescriptionFilter` 契约测试。

### 涉及文件

- `hagoku/agents/scout/agent.py`（备份：`hagoku/agents/scout/UI_CHANGELOG_backup_20260512190000_scout_descriptions.py`）
- `hagoku/manager/orchestrator.py`（备份：`hagoku/manager/UI_CHANGELOG_backup_20260512190000_orchestrator_scout_desc_filter.py`）
- `tests/test_agents/test_agents.py`

---

## 2026-05-12 — Scout 暂停：固定三列表格（字段名｜理解名称｜含义理解）

### 变更概要

- **`orchestrator._scout_field_digest_for_user`**：暂停文案改为 **Markdown 三列表**；单元格转义竖线；可选 `column_display_names`；拿不准列在「理解名称」标「（待核）」。
- **`scout` 批量描述 LLM**：要求每行 `字段名：理解名称｜含义理解`；解析时拆入 `column_display_names` 与 `column_descriptions`。
- **`_generate_confirmation_message`**：表头改为 **理解名称**（原「中文名」）。
- **测试**：表工具函数 + 竖线拆分单测。

### 涉及文件

- `hagoku/manager/orchestrator.py`，`hagoku/agents/scout/agent.py`，`tests/test_agents/test_agents.py`

---

## 2026-05-12 — Scout 暂停：去「小说化」+ 样本可读 + 单行清单

### 变更概要

- **`orchestrator.py`**：Scout 暂停**不再调用开场 LLM**，只发**一行说明 + 每列一行**（`*`/`·` + `列名 — 描述`）；去掉与清单重复的引言与逐列套话。
- **`scout/agent.py`**：样本 `_format_sample_preview` 去掉 `np.float64` 噪音；**保底推断句缩短**，不再带「初步推断…纠正」长尾巴；`_field_desc_auto_columns` 标记自动句，知识库不学习。
- **`tests/test_agents/test_agents.py`**：调整保底句断言。

### 涉及文件

- `hagoku/manager/orchestrator.py`，`hagoku/agents/scout/agent.py`，`tests/test_agents/test_agents.py`

---

## 2026-05-12 — Scout：字段描述解析 + 业务向保底推断

### 变更概要

- **`scout/agent.py`**：LLM 批量描述行解析兼容**半角/全角冒号**、列表前缀与反引号；输出 `max_tokens` 提高到至多 1600；优先 `model_quick`。
- 对仍无可用描述的列写入 **`_heuristic_column_business_hint`**（列名缩写 + 样本片段，明确写「初步推断」），避免暂停清单整屏「请补充」；**不写**统计类型占位。
- 知识库学习跳过以 **`初步推断：`** 开头的描述，避免把保底句当经验固化。
- **`orchestrator.py`**：清单底部提示改为「有错只改不对的几列」。
- **`tests/test_agents/test_agents.py`**：解析与保底句单测。

### 涉及文件

- `hagoku/agents/scout/agent.py`（备份：`hagoku/agents/scout/UI_CHANGELOG_backup_20260512193000_scout_parse_heuristic.py`）
- `hagoku/manager/orchestrator.py`（备份：`hagoku/manager/UI_CHANGELOG_backup_20260512193000_orchestrator_digest_footer.py`）
- `tests/test_agents/test_agents.py`

---

## 2026-05-12 — Scout 暂停：对话区可读性（换行 + 清单分段）

### 变更概要

- **`AnalyzePanel.tsx`**：Agent / 系统气泡增加 **`whitespace-pre-wrap`**，后端消息里的换行在界面上按行展示，不再挤成一段。
- **`orchestrator.py`**：Scout 暂停的 LLM 约束改为**短开场、不与逐列清单重复**；`_scout_field_digest_for_user` 改为列与列之间空行分段，去掉与引言重复的标题句；回退话术缩短。引言与清单之间多一空行。

### 涉及文件

- `hagoku_web/src/panels/AnalyzePanel.tsx`（备份：`UI_CHANGELOG_backup_20260512182000_AnalyzePanel_convo_prewrap.tsx`）
- `hagoku/manager/orchestrator.py`（备份：`hagoku/manager/UI_CHANGELOG_backup_20260512182000_orchestrator_scout_readability.py`）

---

## 2026-05-12 — 分析页：「重置分析」+ WS cancel / 编排中止

### 变更概要

- **`AnalyzePanel.tsx`**：标题栏在非 `setup` 阶段显示 **图标 + 文案**「重置分析」；点击后清空本会话状态、同步 `resetRunUiState()`，并 `send("cancel_analysis")`。
- **`workspace.ts`** / **`useAgentStatusSync.ts`**：`run_completed` 且 `cancelled: true` 时清空全局 `agents`，避免项目列表仍显示「进行中」。
- **`hagoku/api/ws_handler.py`**：新增命令 `cancel_analysis` → `Orchestrator.request_cancel()`；`analyze` 在单进程内串行（`_analysis_in_progress`），避免并发 `run()`。
- **`hagoku/manager/orchestrator.py`**：暂停哨兵 `HAGOKU_CANCEL_PAUSE_TOKEN`、步骤间取消检查、`runs.status=cancelled` 与带 `cancelled` 的 `RUN_COMPLETED`。

### 涉及文件

- `hagoku_web/src/panels/AnalyzePanel.tsx`（备份：`UI_CHANGELOG_backup_20260512174500_AnalyzePanel_reset.tsx`）
- `hagoku_web/src/stores/workspace.ts`（备份：`UI_CHANGELOG_backup_20260512174500_workspace_reset.ts`）
- `hagoku_web/src/hooks/useAgentStatusSync.ts`（备份：`UI_CHANGELOG_backup_20260512174500_useAgentStatusSync_reset.ts`）
- `hagoku/api/ws_handler.py`（备份：`hagoku/api/UI_CHANGELOG_backup_20260512174500_ws_handler_cancel.py`）
- `hagoku/manager/orchestrator.py`（备份：`hagoku/manager/UI_CHANGELOG_backup_20260512174500_orchestrator_cancel.py`）
- `tests/test_api/test_ws_handler.py`

---

## 2026-05-12 — 分析页：去掉「看板流程」条展示

### 变更概要

- **`AnalyzePanel.tsx`**：移除看板任务列表 UI 及对 `/kanban/tasks` 的拉取与轮询；流程只靠流水线条 + 对话区。开始前的说明改为简短操作提示。**`GET /api/projects/.../kanban/tasks` 仍保留**（可供他处或调试）。

### 涉及文件

- `hagoku_web/src/panels/AnalyzePanel.tsx`（备份：`UI_CHANGELOG_backup_20260512154000_AnalyzePanel_no_kanban_strip.tsx`）

---

## 2026-05-12 — 分析页：看板驱动引导 + 去掉对话区固定套话

### 变更概要

- **`hagoku/api/server.py`**：新增 `GET /api/projects/{name}/kanban/tasks`，从项目 `kanban.db` 只读返回当前**最新一轮**流水线任务（至多 4 条：按 `created_at` 取最新组，再按时间正序），字段含 Scribe 写入的 `title` / `description` / `status`。
- **`AnalyzePanel.tsx`**：分析进行中展示 **看板流程** 列表（文案来自 API，非前端杜撰台词）；对话区仅在 **`user_input_requested`** 带 `message` 时追加 Agent 气泡、**`agent_failed`** 仅展示后端 `error` 字符串；护栏拦截不再插入固定 system 气泡（仍用底部 CTA）。输入框 `placeholder` 取自当前 `blocked` 任务的 description/title。轮询 + WS 批次后刷新看板。
- **`tests/test_api/test_server.py`**：`TestKanbanTasksEndpoint` 契约测试。

### 涉及文件

- `hagoku/api/server.py`（备份：`UI_CHANGELOG_backup_20260512153000_server_kanban.py`）
- `hagoku_web/src/panels/AnalyzePanel.tsx`（备份：`UI_CHANGELOG_backup_20260512153000_AnalyzePanel_kanban_guide.tsx`）
- `tests/test_api/test_server.py`

---

## 2026-05-12 — 分析页：「开始分析」对齐编排暂停点（去掉固定欢迎话术）

### 变更概要

- **`AnalyzePanel.tsx`**：点击「开始分析」不再进入「先问研究问题」第二步、也不再插入固定 Agent 气泡（与 `PROJECT.md`「暂停点话术由 LLM 生成、不用固定模板冒充对话」一致）；改为直接 `send("analyze", …, query: "", phase: "full")`，由 Scout 完成后经 `user_input_requested` 等方式推送首条互动文案。已移除 `query` 阶段与对应输入框。

### 涉及文件

- `hagoku_web/src/panels/AnalyzePanel.tsx`（备份：`UI_CHANGELOG_backup_20260512152000_AnalyzePanel_start_flow.tsx`）

---

## 2026-05-12 — 侧栏切换：保持各面板挂载（分析态不丢）

### 变更概要

- **`App.tsx`**：主区同时挂载全部面板，仅对当前 `activeView` 使用 `h-full overflow-hidden`，其余 `hidden`，避免切换「项目 / 报告」等再回「分析」时 **`AnalyzePanel` 卸载导致会话状态重置**。

### 涉及文件

- `hagoku_web/src/App.tsx`（备份：`UI_CHANGELOG_backup_20260512151000_App.tsx`）

---

## 2026-05-12 — 项目页：API 未就绪时的提示文案

### 变更概要

- **`ProjectPanel.tsx`**：`GET /api/projects` 失败（常见原因：未启动 `hagoku-api`）时，将「加载失败，请检查服务」改为明确提示先启动后端（默认 8000）再刷新。

### 涉及文件

- `hagoku_web/src/panels/ProjectPanel.tsx`（备份：`UI_CHANGELOG_backup_20260512150605_ProjectPanel.tsx`）

---

## 2026-05-14 — 报告页 / 运行日志：护栏拦截（P1）

### 变更概要

- **`ReportPanel.tsx`**：并行拉取 `/api/projects/{project}/runs` 与 `/api/reports/{project}`；**按运行**列表展示：护栏拦截 run 用橙色卡片 + **图标+文字**「查看护栏说明」（`guardrails_notice_url`）；成功 run 链到 `report_url`。无 run 元数据时仍回退仅 HTML 列表。`run_completed` / Reporter 完成时刷新。
- **`EventTable.tsx` / `EventPanel.tsx`**：`run_completed` 且 `guardrails_blocked` 时独立样式（`run_completed（护栏未过）`、浅橙背景、详情说明文案）。
- **`utils/wsGuardrails.ts`**：`run_completed` / `run_id` 回退解析等（`AnalyzePanel` / `EventPanel` 共用）；Python 镜像契约见 `tests/test_web/test_ws_guardrails_parity.py`。

### 涉及文件

- `hagoku_web/src/utils/wsGuardrails.ts`
- `hagoku_web/src/panels/AnalyzePanel.tsx`（备份：`UI_CHANGELOG_backup_20260514_AnalyzePanel_wsutil.tsx`）
- `tests/test_web/test_ws_guardrails_parity.py`
- `tests/test_web/__init__.py`
- `hagoku_web/src/panels/ReportPanel.tsx`（备份：`UI_CHANGELOG_backup_20260514_ReportPanel.tsx`）
- `hagoku_web/src/components/EventTable.tsx`（备份：`UI_CHANGELOG_backup_20260514_EventTable.tsx`）
- `hagoku_web/src/panels/EventPanel.tsx`（备份：`UI_CHANGELOG_backup_20260514_EventPanel.tsx`）

---

## 2026-05-13 — 护栏拦截 × 用户沟通（P0 实施）

### 背景
对齐 `PROJECT.md`「统计护栏 → 产品原则」：强制级护栏未通过时不出正式双轨 HTML，但必须给用户说明。

### 变更概要

**API 层（`hagoku/api/server.py`）**：
- `GET /api/reports/{project}/{run_id}/{filename}`：扩展支持 `.md` 文件（原本只支持 `.html`），使前端可读到 `GUARDRAILS_BLOCKED.md`
- `GET /api/projects/{project}/runs`：返回字段新增 `guardrails_blocked: boolean`（检测 `runs/{run_id}/output/GUARDRAILS_BLOCKED.md` 是否存在）
- `GET /api/projects/{project}/detail`：返回字段新增 `last_guardrails_blocked: boolean`

**前端（`hagoku_web/src/panels/AnalyzePanel.tsx`）**：
- 新增 `guardrailsBlocked`、`blockedRunId` 状态
- 处理 `run_completed` + `guardrails_blocked: true` 事件 → 进入护栏拦截终态
- 处理 `agent_completed` + `skipped: true`（Reporter 跳过）→ 流水线 Reporter 步骤显示 "skipped" 状态（ShieldAlert 图标）
- 护栏拦截终态 UI：橙色边框/警告色（`border-app-warning`），非绿色成功
- 护栏说明气泡：灰色 system 气泡文案 "⚠️ 统计护栏未通过，未生成正式 HTML 报告。请查看护栏说明了解详情。"
- **CTA 按钮**：橙色 `查看护栏说明` 按钮（ShieldAlert 图标 + 文字），链接到 `/api/reports/{project}/{run_id}/GUARDRAILS_BLOCKED.md`
- 不显示「查看报告」成功链接

**Tailwind 主题（`hagoku_web/tailwind.config.js`）**：
- 新增 `app-warning-hover: #D97706`、`app-success-hover: #059669`、`app-error-hover: #DC2626`

### 2026-05-13（续）— 审查修复：`run_id`、API `status`、全局面板同步

- **`hagoku/manager/orchestrator.py`**：`RUN_COMPLETED` 增加 `run_id`、`project`（护栏拦截与正常完成两条路径）。
- **`hagoku/api/server.py`**：`detail` / `runs` 优先根据 `GUARDRAILS_BLOCKED.md` 判定 `guardrails_blocked`，再以 `report.html` 等判定 `completed`；`runs` 条目增加 `guardrails_notice_url`（可选）。
- **`hagoku_web`**：`AnalyzePanel` 新分析前重置护栏态；`run_completed` 使用 `run_id` 或从 `output_path` 解析；`useAgentStatusSync` 将 Reporter `skipped` 映射为 store `skipped`（`types/events.ts` 扩展 `AgentStatus`）；`ProjectPanel` 展示 `last_status: guardrails_blocked`（「护栏未过」）。
- **`README.md`**：护栏小节补充 Web 行为一句。

### 涉及文件
- `hagoku/manager/orchestrator.py`
- `hagoku/api/server.py`
- `hagoku_web/src/panels/AnalyzePanel.tsx`（备份：`UI_CHANGELOG_backup_20260513_AnalyzePanel.tsx`、`UI_CHANGELOG_backup_20260513120000_AnalyzePanel.tsx`）
- `hagoku_web/src/hooks/useAgentStatusSync.ts`
- `hagoku_web/src/types/events.ts`
- `hagoku_web/tailwind.config.js`
- `hagoku_web/src/panels/ProjectPanel.tsx`（备份：`UI_CHANGELOG_backup_20260513120500_ProjectPanel.tsx`）
- `UI_CHANGELOG_backup_20260513_AnalyzePanel.tsx`（首轮 AnalyzePanel 修改前）
- `UI_CHANGELOG_backup_20260513120500_ProjectPanel.tsx`（审查修复：`ProjectPanel` 展示 `last_status: guardrails_blocked`）

## 2026-05-12 — 口径对齐第二轮（端口 / 文档 / 依赖）

- **LLM 默认 `base_url`**：统一为 `http://localhost:8080/v1`（与 `hagoku-api` 默认 **8000** 区分），更新 `hagoku/config.py`、`.env.example`、`PROJECT.md`、`README.md`、`DEV.md`、`hagoku/cli.py`、`hagoku/tools/health.py`、`tests/test_pipeline/test_pipeline.py`。
- **克隆路径**：`README.md` / `DEV.md` 改为 `<repo-root>`，避免与包目录 `hagoku/` 混淆。
- **Playwright / 排错**：`docs/TROUBLESHOOTING.md`、`docs/DEVELOPMENT.md` 按当前 React 侧栏（「分析」）与历史 Streamlit 分段说明。
- **`manager_mode`（runs 表）**：`hagoku/storage/database.py` 默认改为 `balanced`，文档串说明其为内部编排元数据，非已移除的用户档位；`hagoku/manager/orchestrator.py` 保留对应注释。
- **报告模板**：`README.md` 标明仅 `default` 为双轨导航版式，`business_analysis` 等为风格化结构。
- **`PROJECT.md` 路线图**：「从模式 N 借鉴」改为「备选路线 N」；表头「借鉴模式」→「演进项」。
- **前端**：移除未引用的 `ScoutConfirmPanel.tsx`；`npm uninstall dockview` 清除未使用依赖。（若需回滚该组件，请从 Git 历史中恢复。）

## 2026-05-12 — 文档同步（Web UI 与人机互动理念）

- **PROJECT.md**：新增「人机互动理念」；删除/替换残留「用户三模式」叙述；CLI 表与模板默认说明对齐代码（`default` 双轨、无 `--mode`）；技术选型与 V2 交付物改为当前 **非 dockview** 的固定导航 SPA。
- **README.md / docs/DEVELOPMENT.md / DEV.md**：Web UI 描述、手动测试步骤、`report --template` 说明、配置示例与环境变量表与上述一致；移除已不生效的 `HAGOKYU_MANAGER_MODE` / `manager.mode` 编排档位描述。
- **`.env.example`**：删除 `HAGOKYU_MANAGER_MODE` 占位行。
- **`DEVELOPMENT_PROMPT.md`**：改为**可重复填写的任务传递模板**（非废弃），并指向 `PROJECT.md` 等现行口径；历史长文已移除以防误导。
- **`.gitignore` / `.env.example` / 文档**：明确 `~/.hagoku/.env` 为唯一加载路径；停止跟踪仓库根 `.env`。
- **README / PROJECT / DEV / TROUBLESHOOTING**：安装与排错说明与上述一致。

## 2026-05-09 — WebUI 优化（第二轮）

### 变更概要

针对 React 前端代码库进行了全面优化，消除运行时性能问题、类型不安全引用和冗余逻辑。

### 优化清单

| # | 变更 | 文件 | 说明 |
|---|------|------|------|
| 1 | 扩展类型定义 | `types/events.ts` | 新增 `AgentId` 联合类型（scout/cleaner/analyst/reporter）；`AgentStatus` 新增 `running`、`waiting_input` 值 |
| 2 | 修复 busy → running | `useAgentStatusSync.ts` | `agent_started` 事件映射从 `"busy"` 改为 `"running"`，与类型定义对齐 |
| 3 | 修复 busy → running | `App.tsx` | `SystemStatus` 组件中 `filter(s === "busy")` 改为 `filter(s === "running")` |
| 4 | 规范 Props 接口 | `PanelHeader.tsx` | 提取独立 `PanelHeaderProps` 接口；使用 `useCallback` 包裹 toggle 回调 |
| 5 | 提取 EmptyState 组件 | `EmptyState.tsx`（新建） | 从各面板内联样式统一为可复用无数据占位组件 |
| 6 | ErrorBoundary 组件 | `ErrorBoundary.tsx`（新建） | React class-based 错误边界，包裹每个面板防止单点崩溃白屏 |
| 7 | ConnectionIndicator | `ConnectionIndicator.tsx`（新建） | WebSocket 连接状态指示灯组件，按 disconnected/reconnecting/connecting/connected 显示不同颜色 |
| 8 | LogView 自动滚动 | `LogView.tsx` | 新增消息时自动滚动到底部，防止新日志被遮挡 |
| 9 | InputBar 优化 | `InputBar.tsx` | `useCallback` 包裹 submit/key 处理函数；通过 ref 直接操作 textarea 避免不必要的 re-render |
| 10 | EventTable 虚拟化 | `EventTable.tsx` | 引入 `@tanstack/react-virtual` 虚拟滚动，大量事件列表渲染性能提升 |
| 11 | 面板级 useMemo/useCallback | 所有 6 个 Panel | 面板组件内派生数据使用 useMemo 缓存；回调使用 useCallback 稳定引用 |
| 12 | WebSocket 心跳优化 | `useWebSocket.ts` | 连接空闲时降低 pingInterval；重连指数退避（1s → 30s，max 5 次后固定 30s） |
| 13 | Dockview 高度修复 | `App.tsx` | 外层 CSS Grid `gridTemplateRows: "auto 1fr"` + `minHeight: 0` 确保 dockview 正确获得固定高度 |

### 验证状态

| 检查项 | 结果 |
|--------|------|
| TypeScript 类型检查 | ✅ 零错误 |
| Vite 生产构建 | ✅ 成功（1754 modules，493KB JS + 103KB CSS，129KB gzip） |
| 所有面板 0 TypeScript Error | ✅ |

---

## 2026-05-09 — 架构重构：Streamlit → React + FastAPI

### 动机

旧 Streamlit WebUI（`hagoku/ui/`）存在以下问题：
- 页面/组件耦合度高，不支持面板拖拽布局
- Python 单页应用，无法利用现代前端生态
- 无实时 WebSocket 事件流，分析进度不可见
- 深色主题和 IDE 风格体验缺失

### 新架构

```
hagoku_web/ (React + TypeScript + Vite)  ← 前端
hagoku/api/  (FastAPI + WebSocket)       ← 后端
```

| 组件 | 旧（Streamlit） | 新（React + FastAPI） |
|------|----------------|----------------------|
| 框架 | Streamlit (Python) | React 19 + TypeScript + Vite 8 |
| 布局 | 固定侧边栏 + 主区域 | dockview 可拖拽面板（tabs/groups/grids） |
| 通信 | HTTP 轮询 | WebSocket 实时事件流 |
| 样式 | Streamlit 默认主题 | 深色 VSCode 风格（CSS 变量） |
| 图标 | emoji | lucide-react |
| 状态管理 | Streamlit session_state | Zustand (workspace store) |
| 构建产物 | 无（运行时渲染） | 487KB JS + 92KB CSS (126KB gzip) |

### 面板迁移对照

| 旧页面（Streamlit） | 新面板（React） | 文件 |
|---------------------|----------------|------|
| `app_projects.py` | **Projects** | `panels/ProjectPanel.tsx` |
| `app_analyze.py` | **Analyze** | `panels/AnalyzePanel.tsx` |
| `app_report.py` | **Reports** | `panels/ReportPanel.tsx` |
| `app_knowledge.py` | **Knowledge** | `panels/KnowledgePanel.tsx` |
| `app_settings.py` | **Settings** | `panels/SettingsPanel.tsx` |
| `event_log.py` | **Event Log** | `panels/EventPanel.tsx` |

### 新增后端 API

| 文件 | 职责 |
|------|------|
| `hagoku/api/server.py` | FastAPI app + CORS + 静态文件挂载（Vite dist） |
| `hagoku/api/ws_handler.py` | WebSocket `/ws` 端点：事件广播、心跳、分析命令处理 |
| `hagoku/api/__init__.py` | 模块导出 |

### 启动方式变更

**旧：** `hagoku-ui` → http://localhost:8501（Streamlit）

**新：**
```bash
# 终端 1：后端
hagoku-api          # http://localhost:8000

# 终端 2：前端
cd hagoku_web && npm run dev   # http://localhost:5173
```

### 删除的文件

- `hagoku/ui/` 整个目录（已废弃）
- 旧 Streamlit 组件：`event_log.py`, `file_uploader.py`, `folder_picker.py`, `project_sidebar.py`, `report_viewer.py`
- `hagoku/ui/components/folder_picker_component/`

### pyproject.toml 变更

- **删除依赖：** `streamlit`
- **新增依赖：** `fastapi>=0.115.0`, `uvicorn[standard]>=0.30.0`
- **新增脚本：** `hagoku-api = "hagoku.api.server:main"`

### 验证状态

| 检查项 | 结果 |
|--------|------|
| TypeScript 类型检查 | ✅ 零错误 |
| Vite 生产构建 | ✅ 成功（1744 modules） |
| Python 导入检查 | ✅ 通过 |

---

## 2026-05-05

### 项目管理页面 (app_projects.py)

1. 删除顶部统计栏（项目数/总分析次数/总数据文件/总存储 metric boxes）
2. 删除展开详情中的"项目记忆"模块（记忆笔记 text_area + 保存记忆按钮）
3. 删除整个展开详情模块（数据文件列表、过程文件列表）
4. 将"创建于/最近更新时间"从第二行移到第一行（项目名后面）
5. 编辑弹窗中加入文件清单及删除文件功能
6. 项目概况标题调大字体(html h2标签，2.5rem，cyan #00ffff)