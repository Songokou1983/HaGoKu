# 收缩改造 — 4 Agent → 1 数据分析师 + 工具箱（2026-06-11）

> **文档定位**：架构审核方出具，交付实施 AI 执行。
>
> **本 brief 改变项目重心**：从「多 Agent 协作 pipeline」收缩为「1 个数据分析师 LLM + 专业工具箱」。
>
> **前置依赖**：本 brief 是独立改造，不依赖其他 brief。但 `2026-06-09-meta-layer-design.md`（HaGoKu Doctor / Prompt Lab）**应暂停**，直到本 brief 的 Phase D 完成后再决定 Doctor 是否还需要——见 §6 红线 5。
>
> **执行流程契约**：Phase A 一次性多 commit；Phase B/C/D 每个 Phase 之间必须真 LLM 冒烟通过 + 审核者验收，才能进入下一个；Phase E/F 持续 / 收尾。

---

## §0 来龙去脉

### 0.1 触发场景

2026-06-11 用户与架构审核方就「HaGoKu 当前架构是否过度复杂」展开讨论。讨论起点是用户读完 `docs/superpowers/specs/2026-06-09-meta-layer-design.md`（HaGoKu Doctor / Meta 层设计 v5）后的困惑：

> "我很困惑为什么不能做出来像 OpenCode / Claude Code 那种 agent 干净的通道。"

### 0.2 讨论时间线

| 步 | 内容 | 结论 |
|----|------|------|
| 1 | 审核方先做项目评估，发现 `hagoku/api/server.py` 207-223 行被 commit `ce4e44e` 改坏（3 处错误），三条 API 测试硬挂；同时确认 doctrine 守门 + information arrival 契约全绿、真 LLM 冒烟通过、文档 / 病理报告体系扎实 | 项目设计严谨度高，但当前 main 有止血级 bug |
| 2 | 用户提出"为什么不能做出 Claude Code 那种干净通道"——读完 Meta 设计文档后发现 HaGoKu Doctor + Phase 0 通道守门是在治标，没碰根本 | 审核方诊断：HaGoKu 复杂度的根因是「每次 LLM 调用都从 context dict 重拼 messages」这个动作存在本身。律 / 刹车 / Doctor 都是为了维持这套架构长出来的免疫系统 |
| 3 | 用户明确项目期待：**「只专业服务于数据分析，依靠大模型的能力，并逐渐成长」** | 三条期待对照现状：专业性 ✅；依靠 LLM 能力 ⚠️（信条对，手上没完全对）；逐渐成长 ❌（现在的"成长"是加律加守门，反方向）|
| 4 | 审核方调整建议方向：不照搬 Claude Code 通用 agent loop，而是「1 个数据分析 LLM + 专业工具箱」——同一信条在数据分析域的具体形态 | 用户确认接受 |
| 5 | 用户质疑：你说"代码不干扰 LLM、做干净通道"的想法是错的吗？ | 审核方明确：信条一字未动；调的是"参考样板"——从 Claude Code 通用 loop 换成「数据分析 LLM + 专业工具箱」。两者**都是干净通道的实现**，只是工具箱专不专业 |
| 6 | 用户主动指出：4 agent 是宣传话术（多 agent 听起来牛逼），事实上反而有害 | 审核方确认：「多 agent」在 2026 已商品化；技术圈（Claude Code / Cursor / Cline / Aider）全在反向走 1 agent + 强工具；收成 1 个反而踩在新风口 |
| 7 | 用户决策：出改造方案，开发者写代码，审核方审核 | 形成本 brief |

### 0.3 关键发现

**发现 1：scout_reply.py 是退化温床的范式**

`hagoku/manager/llm_dispatch/scout_reply.py` 552 行，过去半年被多次"优化"删减。Meta 设计文档 §「来龙去脉」时间线记录了 4 起独立的 prompt 退化事件，每次都"测试 GREEN、冒烟通过、没人察觉"。根因不是"开发者不小心"，是**"每次 LLM 调用从碎片重拼 prompt"这个动作本身**——只要存在这个动作，就有"拼装代码被悄悄改坏"的可能。

**发现 2：Meta Doctor 是聪明的绕路，不是治本**

`docs/superpowers/specs/2026-06-09-meta-layer-design.md` 设计的 HaGoKu Doctor 本质上是承认"我们改不了'每次重拼 prompt'这个架构，那就建一个 Meta LLM 来 watch 我们重拼有没有拼错"。这是聪明工程，但是绕过去而不是穿过去——它没让系统变简单，让"检测系统失败"这件事变可靠。**Claude Code 不需要 Doctor，因为没东西可以悄悄退化。**

**发现 3：4 个 agent 是宣传话术 + CrewAI 时代心智化石**

- `pyproject.toml:29` 仍挂着 `crewai>=0.100.0`，但 `grep "from crewai"` 全仓 0 命中——心智模型留下，代码早删
- 行业从 2024 的「多 agent 协作」叙事，到 2026 已经回到「1 agent + 强工具」（Claude Code / Cursor / Cline / Aider）
- 用户自陈："出于宣传角度堆 4 agent 觉得跟别人说多 agent 听起来牛逼，但是可能事实却是相反"
- 「多 agent」标签已商品化，「严肃统计 + 本地优先」才是 HaGoKu 真正的稀缺差异

**发现 4：律的增长是反信号**

| 时间 | 律 / 刹车 / 守门数量 | 文档量 |
|------|-------------------|------|
| 早期 | 铁律 1-7 | 几百行 |
| 2026-06-09 起 | 铁律 -4 ~ 11（共 16 条）+ 4 重刹车 + 通道完备性 11 律 + 触发词速查表 + HaGoKu Doctor + Phase 0 通道守门 | CLAUDE.md 523 行 / PROJECT.md 780 行 / DOCTRINE_PATHOLOGY_REPORT.md 4144 行 |

每次架构出问题 → 加一条律 → 律加多了 → 系统更难动 → 改一处要查 16 条律 → 加更多律来辅助 AI 实现者记住。**这是不稳定均衡。** 律的减少才是干净度的真实度量。

---

## §1 项目重心变更（决策）

### 1.1 旧重心（即将退役）

> **HaGoKu Studio 是一个多 Agent 数据分析平台——四个分工明确的 LLM Agent 协作（Scout → Cleaner → Analyst → Reporter）。**

### 1.2 新重心（自 2026-06-11 起）

> **HaGoKu Studio 是一个本地优先的严肃数据分析师——基于大模型能力，配备深度统计工具箱。LLM 是分析师，代码是工具箱与执行环境。**

### 1.3 三句话差异

| 维度 | 旧叙事 | 新叙事 |
|------|--------|--------|
| **是什么** | 4 个 Agent 协作 pipeline | 1 个数据分析师 + 专业工具箱 |
| **稀缺点** | 多 Agent 编排 | 严肃统计 + 本地优先 + 小模型也能跑 |
| **成长方式** | 加 Agent / 加律 / 加守门 | 加工具 / 加护栏维度 |

### 1.4 不变的部分

- ✅ LLM 主导信条（铁律 1）—— 一字未动
- ✅ 失败在场（铁律 7）—— 一字未动
- ✅ 提示词修改慎重（铁律 10）—— 一字未动
- ✅ 工作流刹车（铁律 -1 / -2 / -3 / -4）—— 一字未动
- ✅ 统计护栏 / dump 通道 / 工具注册表 —— 全部保留
- ✅ 数据不出本机 —— 一字未动
- ✅ 知识/记忆体系**重组为清晰三层**（① 学术方法库 / ② Agent 成长记忆 / ③ 单项目记忆）—— 见 [`2026-06-11-memory-three-layer-brief.md`](2026-06-11-memory-three-layer-brief.md)

### 1.5 已删 / 已简化（事实勘误，2026-06-11 对账）

| 项目 | 状态 | 说明 |
|------|------|------|
| **双层 LLM（deep / quick）** | ❌ commit `e262599` 已删 | 5 处残留待 Phase A 清理（见 §3 CO-A4）|
| **Scribe** | ✅ 已删干净 | `hagoku/_scribe/` 不存在，仅 1 处历史注释 |
| **Meta 层 v5（HaGoKu Doctor）** | ⚠️ 基建入仓但 Agent 未实现 | `create_meta_client / config.meta_llm / API 端点`保留；Agent 改由 [`2026-06-11-meta-layer-v2-brief.md`](2026-06-11-meta-layer-v2-brief.md) 重新设计（路径 B+）|

**核心信条没动**，动的是「架构怎样落实信条」。当前架构是"嘴上信条对、手上没完全对"——重拼 prompt = 代码替 LLM 决定它看到什么 = 违背信条。本 brief 让架构与信条一致。

---

## §2 角色边界

### 2.1 commit prefix

| 系列 | prefix | 含义 |
|------|--------|------|
| CO-A | `[CO-A]` | Collapse Phase A 止血 |
| CO-B | `[CO-B]` | Collapse Phase B prompt 拼装单点化 |
| CO-C | `[CO-C]` | Collapse Phase C 阶段控制 LLM 化 |
| CO-D | `[CO-D]` | Collapse Phase D 4 agent 合 1 |
| CO-E | `[CO-E]` | Collapse Phase E 工具箱扩张 |
| CO-F | `[CO-F]` | Collapse Phase F 律的减法 |

### 2.2 本 brief 特定红线

| # | 红线 | 理由 |
|---|------|------|
| L1 | **每个 Phase（B/C/D）之间必须真 LLM 冒烟通过才能进下一个** | 不能只跑 mock；架构改造的行为差异只在真模型下显形 |
| L2 | **铁律 -2 适用**：Phase B / C / D 每一步动手前必须先报告"改哪些文件、删哪些行"，得到用户许可才动 | 大改的不可逆点须二次确认 |
| L3 | **铁律 -1 适用**：每个 Phase 都是正向修复，不准 `git revert`；删错了用户许可才能恢复 | 防止"出问题就回滚"的反射动作 |
| L4 | **Phase D 之前 Meta 层开发受限**：✅ 基建保留（`create_meta_client / config.meta_llm / API 端点`已入仓不动）；❌ Meta agent 实现不准动；❌ Prompt Lab Web 面板不准开始；❌ 原 v5 设计文档迭代暂停。Phase D 完成后按 [`2026-06-11-meta-layer-v2-brief.md`](2026-06-11-meta-layer-v2-brief.md) 实施 v2（路径 B+）| 治本先做，v2 路径已确定 |
| L5 | **Phase D 的 prompt 起草受铁律 10 保护** | 必须配 dump 对比，不准凭"觉得"改 |
| L6 | **每个 Phase 完成时必须交"律的减法"清单** | 没有减法 = Phase 没做到位。审核者按此验收 |
| L7 | **统计护栏 / 数据 I/O / 可视化工具不允许在本 brief 内改动** | 它们是工具箱本身，不属于架构层；改它们另开 brief |

---

## §3 六个 Phase 详细方案

### Phase A — 止血（1 天，零架构改动）

**目标**：先把 main 修绿、化石依赖清掉。**这是无风险动作，可以立即执行。**

| # | 任务 | 涉及文件 | 备注 |
|---|------|---------|------|
| CO-A1 | 修 3 处 `hagoku/api/server.py` 错误：207/212 行 `false` → `False`；215-219 行孤悬字段移回新建的 `class LlmConfigBody(BaseModel)`；223 行 `req: LlmConfigBody` 确保引用得到 | `hagoku/api/server.py:207-223` | 当前 main 坏；POST /api/config/llm 100% 失败 |
| CO-A2 | 删 `pyproject.toml` 中 `crewai>=0.100.0` 依赖 | `pyproject.toml:29` | `grep "from crewai" hagoku/` 全仓 0 命中，已是化石 |
| CO-A3 | 同步 `docs/plans/doctrine-violations-cleanup.md` 与现状（5 处 LLM-except 历史违规已在白名单清空，文档仍描述"待修"） | `docs/plans/doctrine-violations-cleanup.md` | 标记 `[已闭环 2026-XX]`，不删原始描述 |
| CO-A4 | **双层 LLM 残留清理**（commit `e262599` 已删主体，5 处残留待清）—— ① `hagoku/tools/health.py:52,63-64,148,165` 健康检查不再读 model_quick / model_deep；② `hagoku/config.py:193-194` 删 LLMConfig 的 model_deep / model_quick 退化字段；③ `hagoku/api/server.py:227-228` POST `/api/config/llm` docstring 删 HAGOKU_LLM_MODEL_DEEP/_QUICK 描述；④ `tests/test_doctrine_compliance.py:249,329` 守门正则删 `create_quick_client` 残留；⑤ PROJECT.md「多模型分派」段 + CLAUDE.md「双层 LLM」描述删除 | 5 处文件 | 已删主体的清账动作 |

**Phase A 审核清单**：
- [ ] `pytest tests/test_api/test_server.py::TestConfigEndpoints -q` 全绿
- [ ] `grep -rn "crewai" hagoku/ pyproject.toml` 返回 0
- [ ] `doctrine-violations-cleanup.md` 与代码 git diff 状态一致
- [ ] `grep -rn "model_deep\|model_quick\|MODEL_DEEP\|MODEL_QUICK\|create_quick_client" hagoku/ tests/test_doctrine_compliance.py` 返回 0（docs/CODE_SEMANTIC_AUDIT.md 历史审计文档残留可保留）

---

### Phase B — prompt 拼装单点化（3-5 天）

**目标**：消灭"每次 LLM 调用从 context dict 重拼 messages"这个动作。让 `build_messages()` 真正成为**物理唯一**入口；4 套 `_*_messages` 实例变量合并为 ProjectContext 持有的**一条 chat**。

| # | 任务 | 涉及文件 | 增删估算 |
|---|------|---------|---------|
| CO-B1 | 强化 `build_messages()` 为严格 schema 入口；任何调用方传非 `query` / `user_input` / `history` / `system_extra` 之外的参数 → raise | `hagoku/channel.py` | +50 |
| CO-B2 | 删 `scout_reply.py` 残留拼装代码，全部走 `build_messages()` | `hagoku/manager/llm_dispatch/scout_reply.py` | -300 |
| CO-B3 | 删 `_scout_messages` / `_cleaner_messages` / `_analyst_messages` / `_reporter_messages` 4 套实例变量 | `hagoku/manager/orchestrator.py:201-205` / `reply_handlers.py:117/274/314` | -150 |
| CO-B4 | `ProjectContext` 升级为**唯一 chat 持有者**——所有 agent 的所有 LLM 调用都从同一条 chat append；阶段切换不重置 chat | `hagoku/context/project_context.py` | +100 / -200 |
| CO-B5 | 加 pre-commit hook + ruff 规则禁止 `hagoku/agents/` 和 `hagoku/manager/` 内直接 `messages = [...]` 或 `messages.append({...})` | `scripts/` + `pyproject.toml` ruff 配置 | +30 |

**Phase B 审核清单**：
- [ ] `grep -rnE "messages\s*=\s*\[.*role" hagoku/agents/ hagoku/manager/` 返回 0 行
- [ ] `pytest tests/test_doctrine_compliance.py tests/test_product/test_information_arrival.py -q` 全绿
- [ ] **真 LLM 冒烟**：`HAGOKU_DUMP_LLM=1 python scripts/smoke/analyst_two_phase_smoke.py ...` 跑通；改前 / 改后 dump 对比 chat 物理上是同一条
- [ ] 律的减法清单（必须交）：律 5（单一权威）自动满足可降级；4 套 `_*_messages` 死代码彻底清除

---

### Phase C — 阶段切换 LLM 化（3-5 天）

**目标**：阶段切换不是 code 决定，是 LLM 自己说"我做完了，跳下一个"。kanban 从控制对象降级为 UI 显示对象。"暂停"做成 chat turn 而不是 orchestrator state。

| # | 任务 | 涉及文件 | 备注 |
|---|------|---------|------|
| CO-C1 | 工具 registry 中统一 `done_with_stage(next_stage, summary)` 工具；现 `route_to` 已部分存在，统一升级 | `hagoku/tools/agent_tool_defs.py` | 不破现有 schema |
| CO-C2 | orchestrator 不再决定阶段切换，只机械执行 LLM 的 `done_with_stage` tool_call | `hagoku/manager/orchestrator.py` | 删 `_stage` 转换 if-else 链 |
| CO-C3 | `kanban.db` 降级为 UI 显示对象：保留进度条数据写入，删 block / unblock 控制语义 | `hagoku/storage/kanban.py` | 不删 db，删控制方法 |
| CO-C4 | 暂停 = LLM 调 `ask_user(question, expected_format)` 工具；不再由 orchestrator emit USER_INPUT_REQUESTED 作决策 | `hagoku/tools/agent_tool_defs.py` + `orchestrator.py` | 暂停从 state 变成 chat turn |

**Phase C 审核清单**：
- [ ] `grep -n "self\._stage\s*=\s*[\"']" hagoku/manager/orchestrator.py` 返回 0 行
- [ ] `grep -n "USER_INPUT_REQUESTED" hagoku/manager/` 数量大幅减少（暂停来自 LLM tool_call 不来自 code 决策）
- [ ] **真 LLM 冒烟**：用户说"够了" → LLM 调 `done_with_stage(reporter)` → 阶段切换；code 完全不参与判断
- [ ] 律的减法清单：律 8（控制通道律）4-agent 部分自动满足可降级

---

### Phase D — 4 agent 合 1（5-7 天，**最大不可逆点**）

**目标**：scout / cleaner / analyst / reporter 合并为 1 个数据分析师 agent。4 套 prompt 合并为 1 个，按"关注点"组织（理解字段 / 评估清洗 / 跑统计 / 写报告），LLM 自己决定切换。

| # | 任务 | 涉及文件 | 增删估算 |
|---|------|---------|---------|
| CO-D1 | **先**起草「数据分析师」统一 system prompt；用 Prompt Lab / 临时脚本跑历史 dump 对比验证（铁律 10 适用） | 新建 `hagoku/agents/analyst/prompt.md` | +200 |
| CO-D2 | 4 agent.py 合并为 1 个 `hagoku/agents/agent.py`；删 `scout/` / `cleaner/` / `analyst/` / `reporter/` 4 目录 | 大改 | -3000 |
| CO-D3 | 工具的 `agents=[...]` 字段改为 `phase_tag=[...]`（仅 LLM 自己看做参考，不做可见性过滤）；全工具对 LLM 可见 | `hagoku/tools/agent_tool_defs.py` | 改字段语义 |
| CO-D4 | orchestrator 退化为「LLM 客户端管理 + tool dispatch + WebSocket 桥」 | `hagoku/manager/orchestrator.py` 709 → ~200 行 | -500 |
| CO-D5 | UI 进度条改成按 chat 里的 phase tag 渲染 | `hagoku_web/src/panels/` 显示逻辑变 | 估 +50 / -100 |

| CO-D6 | **Memory 三层重组**——`hagoku/kb/` 整迁到 `hagoku/memory/methods/`；`storage/memory.py` 重构到 `memory/projects/`；删 4 份 `agents/*/knowledge.py`；新建 `memory/lessons.jsonl` 骨架。详见 [`2026-06-11-memory-three-layer-brief.md`](2026-06-11-memory-three-layer-brief.md) §3 Phase D 内任务 | 多处文件迁移 | 与 D1-D5 同步 |

**不动什么**：
- 工具实现（统计 / 清洗 / 可视化都不动）
- 统计护栏（guardrails 完整保留）
- ProjectContext（Phase B 已升级，本 phase 直接复用）
- Meta 层基建（`create_meta_client / config.meta_llm` 保留；Meta agent 由 v2 brief 接管）

**Phase D 审核清单**：
- [ ] 4 个旧 agent 目录删干净，`grep -rn "from hagoku.agents.scout\|cleaner\|analyst\|reporter" hagoku/` 返回 0
- [ ] `hagoku/kb/` 目录消失；`grep -rn "from hagoku.kb" hagoku/` 返回 0
- [ ] 4 份 `agents/*/knowledge.py` 全删
- [ ] **真 LLM 冒烟**：用 `tests/fixtures/smoke_demo.csv` 跑 5 步剧本（首波收敛 / 工具调用 / 阶段切换 / 用户挑战 / 留下/跳转）全过
- [ ] chat dump 是**物理上一条**（不再是 4 条拼起来）
- [ ] 律的减法清单：律 3（同阶段多轮记忆）自动满足；律 9（重推断触发）作废；律 8 完全作废

---

### Phase E — 工具箱深化（持续）

**目标**：扩张方向从"加 agent / 加律 / 加守门"改为"加工具 / 加护栏维度"。

| # | 任务 | 触发时机 |
|---|------|---------|
| CO-E1 | 审查 `tools/business.py` (905 行) / `tools/cleaning.py` (856 行) / `tools/reporting.py` (1130 行) 内部是否有"代码替 LLM 判断"的部分（铁律 1） | 持续，每次改 |
| CO-E2 | 新分析方法（贝叶斯 / 时序分解 / 因果识别 / power 计算 / 元分析 …）→ 加 tool 注册，不加 agent | 用户提需求时 |
| CO-E3 | 新护栏维度（共线性 / 多重比较 / 效应量 / 异常值 …）→ 新增维度 = 新 tool，让 LLM 主动调 | 用户提需求时 |
| CO-E4 | **Memory 工具化**——新建 `hagoku/tools/memory_tools.py` 暴露 8 个工具（query_method / read_method / save_lesson / recall_lessons / correct_lesson / remember_field / query_project_memory / forget_project）。详见 [`memory brief`](2026-06-11-memory-three-layer-brief.md) §3 Phase E | Phase D 完成后立即 |
| CO-E5 | **Meta 层 v2 启动**——按 [`2026-06-11-meta-layer-v2-brief.md`](2026-06-11-meta-layer-v2-brief.md) 实施 4 组件（Prompt Lab Web + LessonAuditor Agent + prompt_gate CI + 辅助 CLI）| Phase D 完成后立即 |

**Phase E 审核标准（每次扩张）**：
- 新功能 = 1 个 tool 注册 + 0 行 orchestrator 改动 + 0 行新律
- 如果新功能要求加律或加守门 → **审核者拒绝，回到设计**

---

### Phase F — 律的减法（1 天，文档清账）

**目标**：把已经被架构自动满足的律 / 刹车 / 守门从 PROJECT.md / CLAUDE.md 删干净。**律变少是干净度的真实证明。**

**预期删（或降级为"历史参考"）**：

| 删什么 | 为什么 |
|--------|--------|
| 律 5（状态层单一权威） | Phase B 后只有一条 chat，没有派生视图 |
| 律 3（同阶段多轮记忆） | Phase D 后只有一条 chat，自动满足 |
| 律 8 4-agent 部分 | Phase C 后阶段控制权在 LLM |
| 律 9（重推断触发） | Phase D 后没有"重推断"概念，只有 LLM 继续 chat |
| 铁律 11（通道优先律） | Phase B 后通道是物理唯一的，不存在"通道残缺"可能 |
| Meta Doctor / Prompt Lab 设计 | Phase D 后大部分功能不需要；剩余的"chat inspector"职责单独保留 |

**保留的**：
- 铁律 1（零硬编码语义）
- 铁律 7（失败在场）
- 铁律 10（提示词修改慎重）
- 铁律 -1 / -2 / -3 / -4（工作流约束）
- Phase 0 build_messages 守门（B 之后变成"必然遵守"，刹车降为提醒）

**目标行数**：
- `CLAUDE.md`：523 → ~150 行
- `PROJECT.md`：780 → ~300 行
- `DOCTRINE_PATHOLOGY_REPORT.md`：4144 行不删，归档为"历史病理日志"，新审计另起文件

---

## §4 审核者职责

审核者（Cascade / 你指定的 AI / 用户本人）每个 Phase 验完才能进下一个。**硬性清单**：

### 4.1 代码层
- 每个 Phase 列的 `grep` / `pytest` 命令实际跑过，输出粘贴在 PR 描述
- 真 LLM 冒烟脚本输出 dump 路径 + 关键 turn 截图

### 4.2 测试层（最少必跑）
```bash
.venv/bin/python -m pytest tests/test_doctrine_compliance.py -q
.venv/bin/python -m pytest tests/test_product/test_information_arrival.py -q
.venv/bin/python -m pytest --tb=short -q
```

### 4.3 dump 层
- `HAGOKU_DUMP_LLM=1` 跑 `tests/fixtures/smoke_demo.csv` 完整流程
- 对照改前 / 改后 dump：**LLM 看到的信息更多 / 更完整 / 更连贯**（不是更少）
- 任何"LLM 看到的信息变少"的改动 → 拒绝合并

### 4.4 律的减法层
- 开发者交付时附"本 Phase 让 X 条律 / 刹车 / 守门变冗余"清单
- 没有减法 = Phase 没做到位 → 退回重做

---

## §5 时间线与风险

| Phase | 工期 | 风险 | 不可逆点 |
|-------|------|------|---------|
| A | 1 天 | 无 | 无 |
| B | 3-5 天 | 中（4 套 `_*_messages` 删除可能漏迁移点） | 部分（删了不好恢复） |
| C | 3-5 天 | 中（kanban 降级 UI 可能要重做） | 部分 |
| D | 5-7 天 | **高**（4 prompt 合 1，行为改变是 LLM 级的） | **最大不可逆点** |
| E | 持续 | 低 | 无 |
| F | 1 天 | 无 | 文档可恢复 |

**总工期估算**：2-3 周到 D 完成，之后 E（持续扩张）+ F（清账）。

---

## §6 红线（重申）

1. **每个 Phase（B/C/D）之间必须真 LLM 冒烟通过才能进下一个**——不能只跑 mock 测试就推进
2. **Phase B / C / D 每一步动手前，开发者必须先报告"改哪些文件、删哪些行"，得到用户许可才动**（铁律 -2）
3. **每个 Phase 都是正向修复，不准 `git revert`**；删错了用户许可才能恢复（铁律 -1）
4. **Phase D 的 prompt 起草必须配 dump 对比**，不准凭"觉得"改（铁律 10）
5. **Phase D 之前 Meta 层基建保留 / Agent 不准建 / Prompt Lab Web 不准开始** —— Phase D 完成后按 v2 brief 路径 B+ 启动（详见 §2.2 L4 修订版）
6. **统计护栏 / 数据 I/O / 可视化工具的实现不在本 brief 改动范围**——它们是工具箱本身

---

## §7 FAQ

**Q1：信条变了吗？**
没。铁律 1 / 7 / 10 / 工作流刹车一字未动。变的是"架构如何落实信条"——当前架构嘴上信条对、手上没完全对（重拼 prompt = 代码替 LLM 决定它看到什么），本 brief 让架构与信条一致。

**Q2：4 agent 真的有必要砍掉吗？保留分工不行吗？**
分工保留——LLM 自己有"理解字段 / 评估清洗 / 跑统计 / 写报告"4 个关注点，这是数据分析的自然流程。砍掉的是「code 把分工固化成 4 个独立 agent + 4 套 chat + 4 套 prompt 拼装」这个**实现选择**。

**Q3：UI 的 Scout → Cleaner → Analyst → Reporter 进度条会消失吗？**
不会。Phase D 后 UI 进度条按 chat 里的 phase tag 渲染——用户视角上还是 4 段，只是底层是同一个 LLM 在切焦点。

**Q4：HaGoKu Doctor 的工作全废了吗？**
不全废，**重新设计为路径 B+**——详见 [`2026-06-11-meta-layer-v2-brief.md`](2026-06-11-meta-layer-v2-brief.md)。v2 保留用户 3 个原始需求（日常维护 / 提示词模拟 / 防过度拼装）+ 新增 ② 层 lesson 守护，**总实现量从 v5 的 ~1400 行降到 ~1080 行**。Phase D 完成后立即启动。原 v5 文档归档为决策历史。

**Q5：宣传上失去"多 agent"标签会不会很被动？**
不会，反而是机会。审核方判断：「多 agent」在 2026 已商品化（市面上 LLM 数据分析工具几乎全在说），技术圈反向走 1 agent + 强工具（Claude Code / Cursor / Cline / Aider）。新叙事「严肃统计 + 本地优先 + 1 个深度数据分析师」是**别人难抄的稀缺定位**。

**Q6：项目从 0.1.0 Alpha 直接动这么大的架构改造，会不会太激进？**
不激进。0.1.0 Alpha 正是动架构的最佳窗口——用户极少、外部依赖少、回退成本低。等用户基数大了再改才激进。

---

## §8 立刻可做

**Phase A 三件事都是无风险止血**，不需要等其他决定。建议今天就让开发者按 §3 Phase A 清单执行。

Phase B / C / D 等用户确认本 brief 整体方向后启动，按红线 L2 逐步推进。

---

## §9 文档同步动作（本 brief 落地后立即执行）

为让全项目知道重心变更，本 brief 提交后审核方将立即更新以下文件**顶部加段**（不删除现状描述，符合铁律 -1 正向小步）：

- `README.md`：开头加「项目演进方向（2026-06-11 起）」段落，指向本 brief
- `PROJECT.md`：§「灵魂」之后加「演进方向」段落，指向本 brief
- `CLAUDE.md`：§「新人 30 秒入门」加一条「项目演进方向」指针

更新原则：**不替换现有"现状"描述**——现状还在跑，方案要执行后才落地。等 Phase D 完成后再统一重写。
