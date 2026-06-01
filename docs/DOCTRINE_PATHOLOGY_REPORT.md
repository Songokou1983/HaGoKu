# Doctrine Pathology Report

> **报告人**：doctrine 病理学家（评估 AI，只读不写）
> **性质**：append-only living document
> **追踪**：git history + 每条 finding 唯一 ID（F-YYYY-MM-DD-NNN）
> **我的修改范围**：本文件 100%，其他文件 0%
> **状态机**：DRAFT / OPEN / RESOLVED / RETRACTED / DISPUTED / DEFERRED
> **审计阶段**：Phase 0（文档预审）完成 / Phase 1（全代码审计）pending

---

## 0.0 病理学家与报告的定位（宪法 — 永驻文件头）

> **本节是病理学家身份的"宪法"——所有未来 session 必读**

### 病理学家（评估 AI）的定位

- **角色**：doctrine 病理学家
- **职责**：找"代码哪里可能产生坏结果"，**不修代码**
- **可写文件**：本文件 100%
- **不可写文件**：其他任何文件
- **不做的事**：写代码、跑测试、改 git、提 patch、给具体修复方案
- **只做的事**：读代码 + 读文档 + 读 git history + 写 finding 到本文件

### 报告的定位

- **目的**：为项目成功服务，**不是为报告本身**
- **哲学锚点**：结果导向 + 试错框架
- **状态机**：DRAFT → OPEN → RESOLVED / RETRACTED / DISPUTED / DEFERRED
- **审计阶段**：Phase 0（文档预审）完成 / Phase 1（全代码审计）pending / Phase 2 pending / Phase 3 pending
- **当前状态**：18 DRAFT findings 等待 Phase 1 重评

### 未来 session 的第一动作

1. 读本节（定位）
2. 读第 0 节（健康度摘要）
3. 读第 1 节（报告自身目标）
4. 读第 5-6 节（Resolved / 反例 — 找上次处理历史）
5. 读第 9 节（全局视角）
6. **不重复 Phase 0 工作**——只继续 Phase 1+ 的代码审计
7. **新 finding 加进第 3 节**（草稿日志）
8. **不修改历史 DRAFT**——除非有明确证据

### 绝对边界（不可越界）

- 不得写本文件以外的文件
- 不得给具体 patch / 修复方案
- 不得跑测试
- 不得标用户没确认的 RESOLVED / RETRACTED
- 不得修改 doctrine（doctrine 是用户拥有的）
- 不得"自动"修 bug（即使看起来简单）——交给代码 AI

---

## 0. 健康度摘要

### 0.1 项目健康

- **当前评估周期**：2026-06-01 → 2026-06-02 持续
- **审计阶段**：Phase 0 完成 / Phase 1 sessions 1-11 完成（**Python 后端 + 前端全部读完**）/ Phase 1 接近完成
- **Finding 数**：0 正式 / 52 草稿
- **状态分布**：52 DRAFT / 0 OPEN / 0 RESOLVED / 0 RETRACTED / 0 DISPUTED / 0 DEFERRED
- **上次更新**：2026-06-02

**试错总假设数**：52（全部 DRAFT）。

**试错总假设数**：37（全部 DRAFT）。

### 0.2 Phase 1 session 7 关键发现

读完 `hagoku/tools/analysis.py` 全 1195 行后：
- **重大反推**：Phase 0 推论"tools/analysis.py 最可能含硬编码语义规则"——**错的**
- 实际：全文件无业务关键词（grep 0 命中），只有标准统计方法名
- **F-036 NEW**（**修正 Phase 0 推论**）：analysis.py 41K 行没有"硬编码业务关键词"
- **F-037 NEW**：`check_test_assumptions` 5 个 recommendation 是方法选择硬编码——LLM 决定的边界
- **教训**：Phase 0 推论"最可能含 X"常错——**Phase 1 验证后才能下结论**
- **已确认 P0 数量**：F-001, F-003, F-004, F-019, F-020 = 5 个（不变）
- **已读行数 / 总代码行数**：12108 / ~30K = 40%

### 0.3 报告自身健康

| 指标 | 当前 | 健康阈值 |
|------|------|---------|
| 审计阶段完成度 | Phase 1 1/N session | Phase 1 全 session 完成 |
| 正式 finding 占比 | 0/22 = 0% | 100%（Phase 1 完成后）|
| 距上次用户验证 | 0 天 | ≤ 30 天 |
| 反馈率 | 0%（草稿不收反馈） | n/a（Phase 1 才开始） |
| **已读行数 / 总代码行数** | 3457 / ~30K = 11% | 100% |

---

## 1. 报告自身的目标

### 1.1 为什么有这个报告

**为项目成功而报告。** 不是为了报告本身，不是为了"记录每个发现"。

- 项目成功 ≠ 报告完成度
- 项目成功 ≠ finding 数量
- 项目成功 = **用户拿到正确结果 + 团队可持续维护 + doctrine 自我演化**

报告是工具，用来支持项目成功。**如果报告本身成为负担（太复杂、太多 finding、读不懂），它就失败了——即使 finding 都对。**

### 1.2 读者与收益

| 读者 | 时间投入 | 期望收益 | 必须反馈？ |
|------|---------|---------|-----------|
| **用户（你）** | 5-10 分钟 | 全局视角 + 最大杠杆点 | 是（标 DISPUTED 或确认） |
| **代码 AI** | 几小时-几天 | 可执行的 finding（file:line + 证据 + 复现）+ 优先级 | **必须**（FIXED / DISAGREED / LIMITED-FIX / DEFERRED） |
| **审核 AI** | 几十-几小时 | 待审核清单 + 已处理清单 | 是（确认/打回） |
| **未来病理学家** | 几十-几小时 | 框架延续 + 状态机 + 上次状态 | 是 |

### 1.3 反馈循环（Feedback Loop）

报告不是一次性 broadcast。每个 finding 应有反馈路径：

```
病理学家（我）→ 提出 finding（OPEN）
        ↓
   开发者（代码 AI / 审核 AI / 用户）处理
        ↓
   反馈进入报告
        ↓
   状态变更：RESOLVED / RETRACTED / DISPUTED / DEFERRED
        ↓
   下次病理学家读到反馈 → 更新判断 → 校准后续 finding
```

**反馈是报告的核心价值**。没有反馈的 finding = 死信。

### 1.4 报告自身的健康指标

- **状态分布**：RESOLVED + RETRACTED + DISPUTED + DEFERRED 的比例
- **反馈率**：有反馈的 finding 占总 finding 的比例
- **处理节奏**：每周/每月从 OPEN 移到其它状态的数量
- **新 finding 速率 vs 处理速率**：累积 < 1 表明健康

### 1.5 报告失败的 4 个征兆

1. **状态全 OPEN 超过 1 个月** → 没人读 / 没人处理
2. **新 finding 增长率 > 处理率** → finding 累积失控
3. **同一 finding 状态长期不变** → 用户/技术 AI 都在忽略
4. **有反馈但状态未更新** → 反馈循环断了

### 1.6 报告 vs 病理学家

报告是产物，病理学家是过程。报告失败 = 流程失败（用户/技术 AI 没用上），不一定是病理学家失败。

---

## 2. 审计阶段

### 2.1 Phase 0：文档预审（已完成）

**读了**：
- PROJECT.md / CLAUDE.md / DEV.md / DEVELOPMENT_PROMPT.md
- doctrine 测试 + 4 个 contract 测试文件
- 5 个 agent 头部
- llm/client.py / query_parser.py
- orchestrator.py 局部（4 处 TODO）

**产出**：18 DRAFT findings

**盲区**（已记录）：tools/* 大文件 / storage/* 大文件 / api/server.py / 前端 / orchestrator.py 中段

### 2.2 Phase 1：全代码审计（pending）

**目标**：读全部 .py 文件（~30K 行）

**预期产出**：
- 18 DRAFT → 重新评估（升级正式 / 撤回 / 合并 / 调整 severity）
- 新 finding（文档没暴露的）
- "文档 vs 代码" drift 清单
- "测试 vs 实现" 不一致清单
- "声明 vs 实际" 差距清单

### 2.3 Phase 2：跨文件交叉验证

- doctrine 在多文件间的一致性
- orchestrator ↔ agent 之间的契约
- 守门人 ↔ 实际代码的对照

### 2.4 Phase 3：终态报告

- 正式 finding 全部从 DRAFT 升级或新写
- 反馈循环激活
- 全局视角基于完整审计
- 与用户/技术 AI 沟通

---

## 3. 草稿日志（Draft Log）

> ⚠️ **本节所有 finding 处于 DRAFT 状态**。
> 在 Phase 1（全代码审计）完成前，这些 finding 不视为正式。
> Phase 1 完成后，病理学家会重新评估，可能：
> - 升级为正式 finding（OPEN）
> - 撤回（RETRACTED）——全代码读后发现是误报
> - 与新 finding 合并
> - 调整 severity（基于全代码视角）

---

### F-2026-06-01-001 [DRAFT][P0-CRITICAL] orchestrator.py 4 处 `if False: # TODO` 是真 bug

- **结果影响**：Cleaner / Analyst 闸门确认机制被删后，循环中 `cleaner_confirmed = False` / `analyst_confirmed = False` 永远为 False → **多轮对齐可能失控或死循环**。用户在 Cleaner / Analyst 阶段无法正常推进到 Reporter。
- **doctrine 关联（参考）**：律 7（语义不确定可见）+ 律 8（控制通道）的混合失守
- **位置**：
  - `hagoku/manager/orchestrator.py:2255`  `# TODO: _is_user_confirm 已删`
  - `hagoku/manager/orchestrator.py:2312`  `# TODO: _is_user_confirm 已删，Cleaner 确认待重做`
  - `hagoku/manager/orchestrator.py:2357`  `# TODO: _is_user_confirm 已删`
  - `hagoku/manager/orchestrator.py:2489`  `# TODO: _is_user_confirm 已删`
- **证据**：3 处 `if ap_reply:  # TODO` / `if False:  # TODO` / `cleaner_confirmed = False  # TODO` / `analyst_confirmed = False  # TODO` 紧跟 `_pause_and_wait` 之后
- **复现方式**：跑 Cleaner 阶段的多轮对齐 → 看到 while 循环条件永不退出
- **状态**：DRAFT（待 Phase 1 验证）
- **提出日期**：2026-06-01
- **最后更新**：2026-06-01

**Phase 1 验证更新（2026-06-01，读完 orchestrator.py 全 3457 行）**：

- ✅ 4 处 TODO 全部确认存在，line 编号无误
- ✅ line 2395 `if cleaner_confirmed: break` 因 `cleaner_confirmed = False` 永远不达
- ✅ line 2523 `if analyst_confirmed: break` 同上
- ✅ 唯一出口是 HAGOKU_CANCEL_PAUSE_TOKEN（用户必须主动取消才能出循环）
- **影响范围**：任何走完整 pipeline 的用户在 Cleaner/Analyst 阶段都面临死循环
- **真实破坏性**：P0（已确认）

---

### F-2026-06-01-002 [DRAFT][P0-CRITICAL] `tests/test_field_llm_e2e.py` 收集错误

- **结果影响**：pytest 收集测试时 `json.decoder.JSONDecodeError: Expecting '...'` 中断 → **测试集无法被收集 → CI 全绿是假的**。任何 regression 都可能漏跑。
- **doctrine 关联（参考）**：刹车 2（回归契约）的工具链失守
- **位置**：`tests/test_field_llm_e2e.py`（具体行未读，需要看 stacktrace）
- **证据**：`pytest tests/ --co -q` 在该文件中断
- **复现方式**：在 venv 跑 `.venv/bin/python -m pytest tests/ --co -q`，看错误堆栈
- **状态**：DRAFT
- **提出日期**：2026-06-01

---

### F-2026-06-01-003 [DRAFT][P0-CRITICAL] 律 5 失守 → 字段语义多层存储，下游用旧值

- **结果影响**：用户纠正字段名后，下游 Cleaner / Analyst 仍按旧 column_display_names 匹配 → **清洗错列、统计错字段**。用户拿到错误结果而不自知。
- **LLM 失去的机会**：LLM 永远没机会被告知"这个字段的真实业务名是 X"——代码已经替它做完了决定
- **doctrine 关联（参考）**：律 5（状态层单一权威）0 守
- **位置**：`hagoku/manager/orchestrator.py` 内 `apply_scout_user_field_reply_to_context`（多处 dict 写入）
- **证据**：搜索结果——`column_semantics` / `column_descriptions` / `column_display_names` / `target+features` / `variable_roles` 5 处平行存储
- **复现方式**：用户改 `column_display_names["Inc1"]="销售额"` → 检查 `column_semantics` 是否同步
- **状态**：DRAFT
- **提出日期**：2026-06-01

**Phase 1 session 2 验证更新（2026-06-01，读完 memory.py 全 735 行）**：

- ✅ **新增机制**：`apply_to_context` (line 530-544) 写入 `context.column_descriptions[col_name] = sem_def.description`，但**不写** `s.description` (column_semantics 列表项的 description 字段)
- **影响放大**：记忆恢复时只更新一处。下次读到 `s.description` 仍是空的（LLM 推断的旧值或空）
- **读侧不对称**：orchestrator.py:131 `scout_field_review_pause_payload` 防御性写法——`s.get("description", "") or descs.get(name, "")` 读两处都看——但**不是所有读侧都这么写**。其他 code path 可能只看 `s.description` → 看到空 → 拿不到记忆
- **项目级 schema 失守**：`column_semantics` (list[object]) 和 `column_descriptions` (dict) 是不同物理结构，**没有"权威结构"**——所有写侧都得手动同步到两处
- **P0 严重性已确认**：写入多侧不统一 + 读取依赖具体位置 = 5 处律 5 失守都有真实坏结果风险

**Phase 1 session 3 验证更新（2026-06-01，读完 scout/agent.py 全 1110 行）**：

- ✅ **scout `_apply_project_memory` (line 862-878) 同样只写单侧**：
  - Line 873: `context["column_descriptions"][col] = fields[col]` ✅ 写
  - Line 874: `sem["confidence"] = 1.0` ✅ 写
  - Line 877: `context["column_display_names"][col] = display_names[col]` ✅ 写
  - **Line 877 之后没写** `sem["description"]` 或 `sem["display_name"]` ❌
- ✅ **scout `_generate_field_descriptions` (line 904-948) 是反例**——这个函数**正确地双写**到 `column_descriptions` 和 `sem["description"]`（line 921-922, 935-936）
- **项目级不一致**：scout agent 自己写新字段时双写，**但读项目记忆时只写单侧**——读路径 bug
- **修复样本存在**：scout `_generate_field_descriptions` 的写法可作为 `_apply_project_memory` 的修复参考（同一文件，同一 agent）
- **影响放大确认**：用户从记忆恢复时 → column_descriptions 有值 → s.description 没值 → 下次写时部分同步 → 最终不一致

---

### F-2026-06-01-004 [DRAFT][P0-CRITICAL] 律 10 失守 → 项目记忆覆盖用户本 run 纠正

- **结果影响**：用户在当前 run 明确说"Inc1 不是收入是销售额" → 下次 run 自动从 `MemoryManager` 读历史值"Inc1=收入"覆盖 → **用户纠正失效，每次都要重新说**
- **LLM 失去的机会**：LLM 永远没机会被告知本 run 用户已经改过——记忆系统已经替 LLM 决定了
- **doctrine 关联（参考）**：律 10（当前优先律）0 守
- **位置**：`hagoku/storage/memory.py`（具体调用路径未读）
- **证据**：PROJECT.md 律 10 描述有该问题，但 `test_doctrine_compliance.py` / `test_information_arrival.py` 均无对应测试
- **复现方式**：在 project 里改一个字段名 → 第二次分析 → 看 LLM 看到的字段理解
- **状态**：DRAFT
- **提出日期**：2026-06-01

**Phase 1 session 2 验证更新（2026-06-01，读完 memory.py 全 735 行）**：

- ✅ **完整机制已找到**：`learn_from_run` (line 662-668) 在 run 末尾被调用
- ✅ **关键 bug**：构造 `ColumnSemanticDef` 时**完全不传 `description` 和 `display_name` 参数**——Pydantic 默认值是 `None`
- ✅ **`save_column_semantic` 保存这个 description=None 的新对象** → **覆盖了** `persist_field_descriptions` 在 run 早期（orchestrator.py:2155）写入的真实描述
- ✅ **调用顺序确认**：`persist_field_descriptions` → `learn_from_run`。后者覆盖前者。
- **用户可观察到的坏结果**：
  1. 用户在 run 1 纠正 field X 的 description 为 "销售额"
  2. orchestrator.py:2155 调 `_persist_scout_field_updates` → 写入 description="销售额" 到记忆
  3. run 1 末尾 `learn_from_run` → 构造新 `ColumnSemanticDef(description=None)` → 保存
  4. run 2 开始 → `apply_to_context` 读记忆 → description=None → 不更新 `context.column_descriptions[X]`
  5. 用户看到：field X 的描述**没记住**，必须重新说
- **P0 严重性已确认**：可复现的、用户能观察到的"记不住"问题
- **额外 bug 链接**：`learn_from_run` 同时不传 `display_name`——`persist_field_descriptions` 写入的 display_name 也被抹掉

---

### F-2026-06-01-005 [DRAFT][P0-CRITICAL] `_KNOWN_LLM_EXCEPT_VIOLATIONS` 白名单仍可能扩

- **结果影响**：当前白名单为空 set（5 处历史违规已修），但**机制设计允许任意扩**。一旦某天有 PR 把新违规加入白名单，**5 道守门之一的拦截力立刻为 0**。最坏情况：LLM 失败时用户看到静默机械序列。
- **LLM 失去的机会**：如果白名单无限扩，LLM 看到代码越来越倾向于"在 LLM 失败时自己做决定"——LLM 永远没机会被叫回来
- **doctrine 关联（参考）**：守门 5 自身的"二阶失守"——守门存在但被自身设计绕过
- **位置**：`tests/test_doctrine_compliance.py` `_KNOWN_LLM_EXCEPT_VIOLATIONS` 字段
- **证据**：`_KNOWN_LLM_EXCEPT_VIOLATIONS: set[str] = set()` 当前为空，但**没有 meta-test 限制其长度**
- **复现方式**：写一个 `except: return []` + 加进白名单 → 测试绿 → 守门 5 形同虚设
- **状态**：DRAFT
- **提出日期**：2026-06-01

---

### F-2026-06-01-006 [DRAFT][P0-CRITICAL] LLM 失败兜底导致用户静默拿到默认结果

- **结果影响**：LLM 失败时（如 `_call_llm_for_plan` / `_plan_analysis_via_llm`），代码回退到"机械序列"或"exploration" intent，**用户不知道 LLM 失败了**——以为系统在跑，实际是回退到代码预设路径
- **LLM 失去的机会**：用户永远没机会告诉系统"这次失败你想要怎么办"——失败被代码消化了
- **doctrine 关联（参考）**：律 7（语义不确定可见）+ 铁律 2（LLM 失败 4 路径）部分失守
- **位置**：
  - `hagoku/manager/orchestrator.py:2889`  `_call_llm_for_plan` except 路径
  - `hagoku/manager/orchestrator.py:3074`  `_try_generate_phase_llm` except 路径
  - `hagoku/manager/orchestrator.py:3382`  `_llm_understand_field_update` except 路径
- **证据**：`docs/plans/doctrine-violations-cleanup.md` 列了 5 处违规，部分已修部分未修
- **复现方式**：mock LLM 抛异常 → 看 orchestrator 是否 raise RuntimeError 或继续走
- **状态**：DRAFT
- **提出日期**：2026-06-01

**Phase 1 session 3 验证更新（2026-06-01，读完 analyst/agent.py 全 1177 行）**：

- ✅ **analyst `_plan_analysis_via_llm` 异常路径已正确**：line 896-898 `raise RuntimeError(...)`、line 919-921 `raise RuntimeError(...)`
- ✅ **analyst `_run` 优雅降级**：line 288-307 失败时 retry → 仍失败 raise `NeedUserClarification`（让用户澄清）
- **因此 F-006 的 analyst 部分已修复**——5 处异常路径中的 2 处（来自 analyst 函数体）已经 raise RuntimeError
- **剩下 3 处仍在 orchestrator.py**（line 2889 / 3074 / 3382）
- **P0 严重性降为 P1-HIGH**：因为部分已修，且 retry + NeedUserClarification 是合理降级
- **建议**：
  - 保留 DRAFT 状态
  - 后续 session 验证 orchestrator 3 处是否仍存在（已在 session 1 确认）
  - Phase 3 终态时若 3 处都修了，标 RESOLVED

---

### F-2026-06-01-007 [DRAFT][P1-HIGH] 律 3 xfailed 测试拖 1+ 月

- **结果影响**：第 3 轮+ 的多轮一致性**没有正向断言**。如果将来 messages_history 在第 3 轮后丢前几轮，测试仍绿——**用户多轮纠错可能在第 3 轮后丢失上下文**
- **LLM 失去的机会**：LLM 永远没机会被告知前几轮的对话
- **doctrine 关联（参考）**：律 3 半守
- **位置**：`tests/test_information_arrival.py` 律 3 部分
- **证据**：1 个 xfailed 测试，commit history 显示 5-26 至今未推进
- **复现方式**：跑 `pytest tests/test_information_arrival.py -k "xfail"`
- **状态**：DRAFT
- **提出日期**：2026-06-01

---

### F-2026-06-01-008 [DRAFT][P1-HIGH] 律 4 工具覆盖只单点守

- **结果影响**：`restrict_analysis_to` 工具落地后，**没有"任何新增 / 修改的工具都对应一个 schema 完备性测试"**机制。如果将来删工具或改 schema，律 4 静默失守——**用户能说的事 LLM 接不住**
- **LLM 失去的机会**：LLM 永远没机会在工具缺失时告诉用户"我做不到"
- **doctrine 关联（参考）**：律 4 弱守
- **位置**：`tests/test_information_arrival.py::test_真实场景_律4_工具覆盖补集排除` 单点
- **证据**：搜索全仓，没有 schema 完备性的通用守门
- **复现方式**：删 `restrict_analysis_to` → 看测试是否还绿
- **状态**：DRAFT
- **提出日期**：2026-06-01

---

### F-2026-06-01-009 [DRAFT][P1-HIGH] 律 7 前端契约失守

- **结果影响**：后端测试断言"LLM 未理解时 applied 为空"，但**前端 AnalyzePanel.tsx 是否真的显示"未理解"提示**没有测试。用户可能看到空响应而非"AI 暂时没理解"
- **LLM 失去的机会**：LLM 失败时，用户不知道发生了什么——UI 没说
- **doctrine 关联（参考）**：律 7 半守
- **位置**：`hagoku_web/src/panels/AnalyzePanel.tsx`（具体组件未读）
- **证据**：`hagoku_web/` 无任何 test runner（无 vitest/jest 配置）
- **复现方式**：mock LLM 失败 → 看 UI 表现
- **状态**：DRAFT
- **提出日期**：2026-06-01

---

### F-2026-06-01-010 [DRAFT][P1-HIGH] 4 道守门人的"假守"模式

- **结果影响**：守门 1-4 是 AST 静态扫描 + regex 匹配，**有结构性盲区**（如守门 1 不查 dict 的 values、守门 2 不查动态拼接、守门 6 只能匹配静态 regex 列表里的模式）。新增的"伪装硬编码"如果不在白名单 pattern 里，守门形同虚设
- **LLM 失去的机会**：守门漏掉的硬编码 = LLM 看到代码"看起来很 doctrine 化"实际偷偷替它做决定
- **doctrine 关联（参考）**：守门 1-4 的"边界"
- **位置**：`tests/test_doctrine_compliance.py` 守门 1-4 全文
- **证据**：每道守门的 `_BUSINESS_KEYWORDS` / `_CHINESE_ALT_REGEX_PATTERN` / `_PROMPT_RULE_PATTERNS` 都是静态规则
- **复现方式**：写 `dict_values_check = {"if": ["收入", "营收"]}` 看守门 1 能否拦下
- **状态**：DRAFT
- **提出日期**：2026-06-01

---

### F-2026-06-01-011 [DRAFT][P1-HIGH] 铁律 0/3 + 刹车 3 完全无守

- **结果影响**：改动前自检（铁律 0）和提交前自检（铁律 3）只在文档里，**commit hook 人工 `cp` 安装**——CI 不会强制。意味着新 AI 写代码时如果忘了 hook 或在 hook 装好前提交，**doctrine 0/3 完全失效**
- **LLM 失去的机会**：自检流于形式 = LLM 写代码时不被提醒"这是 LLM 的活不是代码的活"
- **doctrine 关联（参考）**：铁律 0 / 铁律 3 / 刹车 3
- **位置**：`scripts/check-selfcheck-hook.py` + `.git/hooks/commit-msg`
- **证据**：搜索 `tests/` 没有任何关于 commit-msg hook 的测试
- **复现方式**：在没装 hook 的机器上 commit → 看守门是否被触发
- **状态**：DRAFT
- **提出日期**：2026-06-01

---

### F-2026-06-01-012 [DRAFT][P2-MEDIUM] `hagoku/agents/scout/UI_CHANGELOG_backup_*.py` 已 add 到 git

- **结果影响**：3 个 `UI_CHANGELOG_backup_*.py` 死代码被 git tracked，**占用 2,434 行 + 干扰 grep**。未来 AI 读 scout/ 时会看到这些"旧版本实现"，可能误以为有 call site 而保留关联代码
- **LLM 失去的机会**：LLM 看到死代码会以为有真实使用，可能基于错误前提写新代码
- **doctrine 关联（参考）**：无直接 doctrine 关联
- **位置**：
  - `hagoku/agents/scout/UI_CHANGELOG_backup_20260512190000_scout_descriptions.py` (741 行)
  - `hagoku/agents/scout/UI_CHANGELOG_backup_20260512193000_scout_parse_heuristic.py` (837 行)
  - `hagoku/agents/scout/UI_CHANGELOG_backup_20260512200000_scout_compact_pause.py` (856 行)
- **证据**：`ls hagoku/agents/scout/` 直接看到这 3 个 .py
- **复现方式**：`git ls-files hagoku/agents/scout/ | grep UI_CHANGELOG`
- **状态**：DRAFT
- **提出日期**：2026-06-01

---

### F-2026-06-01-013 [DRAFT][P2-MEDIUM] 数字漂移：CLAUDE.md / README 声明 vs 实际

- **结果影响**：CLAUDE.md 注释里 `代码量: 18,607 行` 实际 29,493 行；README 声称"223 pytest 100% 通过"——**新 AI 读 CLAUDE.md 会形成错误预期**，可能基于错误数据做决策
- **LLM 失去的机会**：LLM 读 CLAUDE.md 时学到"项目规模约 19K 行"，对架构复杂度判断会偏差
- **doctrine 关联（参考）**：无直接 doctrine 关联
- **位置**：
  - `CLAUDE.md` 顶部注释（具体行未定位）
  - `README.md` 顶部声明
- **证据**：`find hagoku -name "*.py" -not -path "*/__pycache__/*" | xargs wc -l` = 29,493 行
- **复现方式**：`grep -n "行\|pytest" CLAUDE.md README.md`
- **状态**：DRAFT
- **提出日期**：2026-06-01

---

### F-2026-06-01-014 [DRAFT][P2-MEDIUM] PROJECT.md 仍描述已知违规为 "fallback"

- **结果影响**：PROJECT.md §「意图解析」仍写 `QueryIntent(intent_type="exploration")` fallback = "已知违规" 等待修复——**文档把"已知的坏"作为"约定"**。新 AI 看到这描述可能误以为这种 fallback 是"可接受的临时方案"
- **LLM 失去的机会**：LLM 看到文档把违规描述为"已知"——可能放松警觉，复制这种模式
- **doctrine 关联（参考）**：律 7（语义不确定可见）+ 铁律 2（LLM 失败 4 路径）
- **位置**：`PROJECT.md` §「意图解析」段落
- **证据**：直接读 PROJECT.md
- **复现方式**：`grep -n "已知违规\|fallback" PROJECT.md`
- **状态**：DRAFT
- **提出日期**：2026-06-01

---

### F-2026-06-01-015 [DRAFT][P3-LOW] orchestrator.py 单文件 3457 行

- **结果影响**：3457 行的"上帝对象"使得新 AI 读 codebase 时**认知负担极大**——理解阶段转换、闸门、契约测试任何一个都需要打开这个文件。**未来出错概率高于平均水平**
- **LLM 失去的机会**：LLM 读 3457 行文件时容易"局部优化"——在某处加 if 修复一个 bug 但忽略全局影响
- **doctrine 关联（参考）**：Karpathy 原则 2（Simplicity First）的实操困难
- **位置**：`hagoku/manager/orchestrator.py` 全文
- **证据**：`wc -l` = 3457
- **复现方式**：`wc -l hagoku/manager/orchestrator.py`
- **状态**：DRAFT
- **提出日期**：2026-06-01

---

### F-2026-06-01-016 [DRAFT][P3-LOW] UI 设计 11 条 0 自动化测试

- **结果影响**：表头居中、按钮图标+文字、备份命名规范……全是 CLAUDE.md 死规定，**但 hagoku_web/ 无任何 test runner**。每条都靠人工 review
- **LLM 失去的机会**：LLM 写前端时不被工具提醒"这是死规定"
- **doctrine 关联（参考）**：CLAUDE.md UI 原则
- **位置**：`hagoku_web/` 全部 + `CLAUDE.md` §「UI 设计原则」
- **证据**：`ls hagoku_web/` 无 vitest.config / jest.config
- **复现方式**：写一个故意"按钮没图标"的组件 → 看是否有测试拦下
- **状态**：DRAFT
- **提出日期**：2026-06-01

---

### F-2026-06-01-017 [DRAFT][P4-OBSERVATION] 守门 5 白名单机制的设计性破窗

- **结果影响**：当前**没有坏结果**（白名单为空）。但机制允许任意扩——见 F-005 的描述。这条 observation 记录机制本身的设计问题，等它真正产生坏结果时升级为 P0
- **doctrine 关联（参考）**：守门 5 的二阶脆弱性
- **位置**：`tests/test_doctrine_compliance.py` `_KNOWN_LLM_EXCEPT_VIOLATIONS`
- **证据**：见 F-005
- **状态**：DRAFT
- **提出日期**：2026-06-01

---

### F-2026-06-01-018 [DRAFT][P4-OBSERVATION] 4 道 doctrine 守门人 + PROJECT.md 律 1-10 = 13 条 core doctrine 的"项目级 schema"

- **结果影响**：当前**没有坏结果**。但这些守门是"项目质量的下限"——一旦未来引入新 Agent / 新阶段，没有"必须配 doctrine 守门"的强制流程。observation 记录此架构脆弱性
- **doctrine 关联（参考）**：本报告自身的 meta-observation
- **位置**：`tests/test_doctrine_compliance.py` + `docs/plans/`
- **证据**：`docs/plans/doctrine-violations-cleanup.md` 列了 5 条"已修/未修"清单——这是手动维护，没有自动化跟踪
- **状态**：DRAFT
- **提出日期**：2026-06-01

---

### F-2026-06-01-019 [DRAFT][P0-CRITICAL] orchestrator.py:2338 死分支 — 清洗结果待用户确认永远不触发

- **结果影响**：在 Cleaner → 用户确认清洗结果 → 进 Analyst 的关键闸门处，代码逻辑被破坏。`cleaning_report = None`（line 2323）让 `if not skip_cleaning and cleaning_report is not None:`（line 2338）**永远为 False** → 整个 60 行的"清洗结果用户确认"块**永远不会执行**。用户**看不到**清洗结果的 review，**无法阻止**清洗执行。
- **LLM 失去的机会**：用户永远没机会对清洗结果说"这个列的清洗方式不对"——代码替他确认了
- **doctrine 关联（参考）**：律 7（语义不确定可见）+ 律 8（控制通道）
- **位置**：
  - `hagoku/manager/orchestrator.py:2323`  `cleaning_report = None`
  - `hagoku/manager/orchestrator.py:2338`  `if not skip_cleaning and cleaning_report is not None:`
- **证据**：grep 确认 `skip_cleaning` 在 orchestrator.py **只有 1 处引用**（line 2338），**无定义**——该 if 还会在评估时 NameError
- **复现方式**：跑完整 pipeline（phase="full"） → 跑过 Cleaner 阶段 → 直接跳到 Analyst，**没有**任何 cleaning_review 暂停
- **状态**：DRAFT（Phase 1 已确认）
- **提出日期**：2026-06-01

---

### F-2026-06-01-020 [DRAFT][P0-CRITICAL] orchestrator.py:2537-2595 guardrails 路径 NameError

- **结果影响**：当 Analyst 触发强制级护栏违规时，代码意图是给用户一个"LLM 风险分析 + 用户决策"的暂停。**但 RUN_COMPLETED 事件（line 2575-2586）和 return（line 2587-2595）引用了 `output_path`（line 2610 才定义）和 `duration_ms`（line 2637 才定义）**。结果是：**NameError**，用户看到的是"分析失败"而不是"护栏触发"——LLM 风险分析生成的时间被浪费。
- **LLM 失去的机会**：护栏违规是统计问题，本应由 LLM 解释并让用户决策。但 LLM 解释完成、用户即将决策时，整个 run 崩溃。LLM 永远没机会被用户回应。
- **doctrine 关联（参考）**：律 7（语义不确定可见）+ 铁律 2（LLM 失败 4 路径的边界外）
- **位置**：
  - `hagoku/manager/orchestrator.py:2575-2586`  RUN_COMPLETED 事件 emit，引用 `output_path`、`duration_ms`
  - `hagoku/manager/orchestrator.py:2587-2595`  return，引用 `output_path`、`duration_ms`
  - `hagoku/manager/orchestrator.py:2610`  `output_path` 实际定义
  - `hagoku/manager/orchestrator.py:2637`  `duration_ms` 实际定义
- **证据**：grep `output_path` 在 line 2575-2610 区间 4 次引用，line 2610 才是赋值。`duration_ms` 类似
- **复现方式**：mock Analyst 输出让 guardrails 触发 → 期望 guardrails_blocked → 实际 NameError
- **状态**：DRAFT（Phase 1 已确认）
- **提出日期**：2026-06-01

---

### F-2026-06-01-021 [DRAFT][P1-HIGH] orchestrator.py:3253 `_llm_classify_confirmation` 兜底导致死循环

- **结果影响**：CLI 路径（`_request_field_confirmation`）调用此函数判断用户输入是"确认"还是"纠正"。**当 LLM 不可达时，except 返回 `{"type": "correction", "updates": {}}`**（line 3253-3256）——这意味着用户的"确认"被分类为"无更新的纠正"。`_apply_field_corrections` 跑了但啥都没改。**循环没有 break，CLI 字段确认永远卡住**。
- **LLM 失去的机会**：LLM 失败时本应让用户知道"AI 暂时不可用"，代码却静默把"确认"当成"无操作纠正"，让用户继续在循环里
- **doctrine 关联（参考）**：律 7（语义不确定可见）+ 铁律 2（LLM 失败 4 路径）
- **位置**：`hagoku/manager/orchestrator.py:3253-3256`
- **证据**：
  ```python
  except Exception:
      return {"type": "correction", "updates": {}}
  ```
  注释说"安全默认值：视为有纠正内容"——但实际是"**永远不视为确认**"，等于禁用 break
- **复现方式**：mock LLM 抛异常 → 跑 CLI 字段确认 → 用户说"好" → 卡在循环
- **状态**：DRAFT（Phase 1 已确认）
- **提出日期**：2026-06-01

---

### F-2026-06-01-022 [DRAFT][P2-MEDIUM] orchestrator.py:3258-3302 `_llm_understand_field_update` 是死代码

- **结果影响**：函数完整定义（45 行）但**全仓 grep 确认无任何调用方**。是旧版本 `apply_scout_user_field_reply_to_context`（line 390）重构前的遗留。死代码增加阅读负担 + 干扰"找死代码"工具的判断。
- **LLM 失去的机会**：无
- **doctrine 关联（参考）**：Karpathy 原则 2（Simplicity First）
- **位置**：`hagoku/manager/orchestrator.py:3258-3302`
- **证据**：`grep -rn "_llm_understand_field_update" hagoku/` 全仓**只有定义那一行**（line 3258）
- **复现方式**：删除该函数 → 跑全部测试 → 应全绿（因为没有调用方）
- **状态**：DRAFT（Phase 1 已确认）
- **提出日期**：2026-06-01

---

### F-2026-06-01-023 [DRAFT][P3-LOW] `memory.py:559` `build_memory_project` 返回记忆的**子集**——Scout 看不到完整历史

- **结果影响**：`build_memory_project` 只返回 `description` 和 `display_name` 两类信息。但 `ColumnSemanticDef` 实际存了 8 个字段：`semantic` / `ignore` / `ordinal` / `order` / `unit` / `display_name` / `description` / `role` / `confidence` / `source` / `confirmed_by_user`。Scout 看到的是历史记忆的**残缺版本**。
- **LLM 失去的机会**：
  - LLM 不知道历史已经认定这个字段是 `target` —— 必须自己重新推断
  - LLM 不知道历史已经认定这个字段是 `ignore` —— 每次都问
  - LLM 不知道历史 `confidence` 是 1.0 还是 0.6 —— 自己的推断可能覆盖
- **doctrine 关联（参考）**：律 5（状态层单一权威）+ 律 10（当前 run 优先于历史）——历史没读全
- **位置**：`hagoku/storage/memory.py:559-576`
- **证据**：
  ```python
  fields: dict[str, str] = {}
  display_names: dict[str, str] = {}
  confirmed = self.get_column_semantics(project_id)
  for col_name, sem_def in confirmed.items():
      if sem_def.description:
          fields[col_name] = sem_def.description
      if sem_def.display_name:
          display_names[col_name] = sem_def.display_name
  return {"fields": fields, "display_names": display_names}
  ```
  只取 2 个字段，丢 6+ 个
- **复现方式**：在 progress.yaml 写 `role: target` for field X → 跑 Scout → 看 memory_project 里有没有 role 信息
- **状态**：DRAFT（Phase 1 已确认）
- **提出日期**：2026-06-01

---

### F-2026-06-01-024 [DRAFT][P3-OBSERVATION] `memory.py:659` `learn_from_run` 用 evidence 字符串匹配决定是否保存

- **结果影响**：`if confidence >= 0.8 or "用户" in evidence or "记忆" in evidence:`——基于 evidence 字段的子串匹配决定是否学习这条记忆。这**不是**业务关键词列表，**但仍是**代码层字符串判断。
- **LLM 失去的机会**：如果 Scout 把 evidence 写成"已确认 / 系统暂理解为 / LLM 推测为"等变体，这些**不会被识别为"用户确认过"**——记忆丢失
- **doctrine 关联（参考）**：doctrine test 守门 1 守"业务关键词字面量集合"，但**不守**"evidence 字符串匹配"。这是 doctrinal 守门的盲区
- **位置**：`hagoku/storage/memory.py:659`
- **证据**：
  ```python
  if confidence >= 0.8 or "用户" in evidence or "记忆" in evidence:
  ```
- **doctrine 守门盲区**：守门 1 扫 list 字面量 / 守门 2 扫中文 `|` 正则 / 守门 3 扫中文 if-elif。但**这种 "if x in y" 形式的字符串子串匹配**不在任何守门范围内
- **真实影响**：如果未来 LLM 改了 evidence 写法（如"已确认"或"用户已说明"），**守门不会发现，但 learn_from_run 行为已变**
- **状态**：DRAFT（Phase 1 已确认）
- **提出日期**：2026-06-01

---

### F-2026-06-01-025 [DRAFT][P1-HIGH] analyst `_do_*` 5 个 handler 静默 return None

- **结果影响**：`_do_regression` / `_do_correlation` / `_do_trend` / `_do_hypothesis_test` 全部用 `except Exception: logger.warning(...); return None` 兜底。**单个 step 失败时用户不知情**——`results` 列表少一项，UI 显示少一项。
- **缓解**：外层 `_run` 在所有 step 都失败时 retry via LLM，再失败 raise `NeedUserClarification` → 用户能看到。但**部分失败**（1/3 步骤失败）的场景下，用户只看到 2 个结果，不知道本应 3 个。
- **LLM 失去的机会**：用户无法告诉系统"这个 step 的结果不靠谱，换个方法"
- **doctrine 关联（参考）**：律 7（语义不确定可见）的部分失守
- **位置**：
  - `hagoku/agents/analyst/agent.py:522-524` `_do_regression`
  - `hagoku/agents/analyst/agent.py:671-673` `_do_hypothesis_test`
  - `hagoku/agents/analyst/agent.py:783-785` `_do_trend`
  - `hagoku/agents/analyst/agent.py:701-703, 1095-1097` 交叉验证等
- **证据**：
  ```python
  except Exception:
      logger.warning("回归分析执行失败", exc_info=True)
      return None
  ```
- **复现方式**：mock 一个 `regression()` 抛异常 → 跑 Analyst → results 少一项，但 user 看到的 message 不变
- **状态**：DRAFT（Phase 1 已确认）
- **提出日期**：2026-06-01

---

### F-2026-06-01-026 [DRAFT][P3-LOW] `_learn_from_results` 在 scout + analyst 自动写知识库（无用户确认）

- **结果影响**：`scout._learn_from_results` (scout/agent.py:1048) 和 `analyst._learn_from_results` (analyst/agent.py:1147) 都在 agent 完成时**自动**调用 `knowledge.learn()` 写知识库。`scout` 用 confidence≥0.85 门槛 + 相似度去重；`analyst` 用显著性决定 confidence (0.8 if sig else 0.6)。
- **doctrine 关联（参考）**：律 10（用户优先）的边界——知识库是跨 run 共享的，自动写入会**污染**未来分析
- **位置**：
  - `hagoku/agents/scout/agent.py:1064-1076` `scout._learn_from_results`
  - `hagoku/agents/analyst/agent.py:1159-1180` `analyst._learn_from_results`
- **风险**：
  - 用户没机会审核写入的条目
  - 知识库相似度去重（0.85 / 0.9）会保留旧的，可能与新分析矛盾
  - 长期积累可能让知识库"凝固"，LLM 看到的 reference 越来越固定
- **复现方式**：跑两次分析，第二次跑不同数据集但相似字段 → 知识库条目被引用
- **状态**：DRAFT（Phase 1 已确认）
- **提出日期**：2026-06-01

---

### F-2026-06-01-027 [DRAFT][P3-OBSERVATION] scout `_TYPE_ECHO_PATTERN_RE` 中文正则——守门 2 假阳风险

- **结果影响**：`scout/agent.py:50` 定义 `_TYPE_ECHO_PATTERN_RE = re.compile(r"^.+\（.+?\）$")` 用于检测"列名（内容）"结构回显。**这是中文正则**——按守门 2 字面规则会触发。
- **实际合规性**：函数 `_description_is_user_facing_meaningful` 的注释明确说"纯字符串形状匹配，不涉及语义判断"，**用法是合规的**（结构匹配不是业务判断）。
- **守门风险**：如果守门 2 写得过严，会拦下这个无害的**结构匹配**用法。守门扫描者要识别"结构匹配" vs "业务分类"的差别。
- **doctrine 关联（参考）**：守门 2 的设计需要更细粒度——区分"中文结构正则"（OK）和"中文业务分类正则"（违规）
- **位置**：`hagoku/agents/scout/agent.py:50`
- **证据**：
  ```python
  _TYPE_ECHO_PATTERN_RE = re.compile(r"^.+\（.+?\）$")
  ```
  和 `==== CHANNEL ZONE: 禁止正则/if-else 语义分支 ====` (line 470) 注释后
- **状态**：DRAFT（Phase 1 已确认，P3 因为用法合规）
- **提出日期**：2026-06-01

---

### F-2026-06-01-028 [DRAFT][P3-LOW] `_auto_generate_handover` 注释承诺"LLM 驱动"但代码不调 LLM

- **结果影响**：`scribe/agent.py:554-629` `_auto_generate_handover` 的 docstring 说"LLM 驱动全过程理解版"。但实际**只调用** `generate_handover_note()`，后者是 `json.dumps(source_summary)`——**纯序列化，不调 LLM**。
- **doctrine 关联（参考）**：律 7（语义不确定可见）的边界——"LLM-driven" 是个产品承诺，**用户期望 LLM 给出全过程解读**，实际拿到的是 JSON 堆叠
- **位置**：
  - 注释：`scribe/agent.py:555` `_auto_generate_handover` docstring
  - 代码：`scribe/agent.py:386-411` `generate_handover_note` 实现
- **证据**：
  ```python
  def generate_handover_note(self, from_agent, to_agent, source_summary, context=None):
      ...
      self._log(f"HANDOVER transport: {from_agent} → {to_agent}")
      return json.dumps(source_summary, ensure_ascii=False, indent=2, default=str)
  ```
  没有任何 LLM 调用
- **影响**：handover_notes.md 内容是 JSON 堆叠，**不是 LLM 全过程解读**——下游 agent 看到的是机械数据搬运
- **状态**：DRAFT（Phase 1 已确认）
- **提出日期**：2026-06-01

---

### F-2026-06-01-029 [DRAFT][P3-LOW] `_get_context_data` 用**固定顺序**分配 YAML block——顺序错乱会错配

- **结果影响**：`scribe/agent.py:422-444` 用 `re.findall(r"```yaml\n(.*?)\n```", content, re.DOTALL)` 提取所有 YAML block，然后**按固定顺序**（Scout → Cleaner → Analyst → Reporter）分配。
- **LLM 失去的机会**：如果用户手工编辑过 context.md（罕见但可能），block 顺序变了 → Cleaner 产出被识别为 Analyst 产出 → **handover 内容错乱**——LLM 解读的是错误的数据
- **doctrine 关联（参考）**：律 5（状态层单一权威）的边界——"按顺序分配" 隐含 schema 假设，但 schema 改动时容易 silently 错配
- **位置**：`scribe/agent.py:422-444`
- **证据**：
  ```python
  blocks = re.findall(r"```yaml\n(.*?)\n```", content, re.DOTALL)
  phases = ("Scout", "Cleaner", "Analyst", "Reporter")
  for i, block in enumerate(blocks):
      if i >= len(phases): break
      parsed = yaml.safe_load(block)
      if isinstance(parsed, dict):
          result[phases[i].lower()] = parsed
  ```
- **改进方向**：用 yaml 块前的 Markdown 标题（## Scout 产出 / ## Cleaner 产出）做 key，而非按数组下标
- **状态**：DRAFT（Phase 1 已确认）
- **提出日期**：2026-06-01

---

### F-2026-06-01-030 [DRAFT][P3-OBSERVATION] `get_upstream_summary` 硬编码中文 phase 标签

- **结果影响**：`scribe/agent.py:526-552` 用 `phase_labels` 字典硬编码 "数据侦察" / "数据清洗" / "统计分析" / "报告生成"——在 `handover_notes.md` 中匹配 `## {from_label} → {to_label} 交接笔记` 模式。
- **脆弱性**：如果未来 prompt.md 改名（例如把"数据侦察"改为"数据扫描"），`get_upstream_summary` 会**找不到任何交接笔记**——`matches` 为空 → 返回 None → 下游 agent 拿不到上游摘要
- **doctrine 关联（参考）**：karpathy 原则 2（Simplicity First）的实操困难——硬编码 vs 单一权威的取舍
- **位置**：`scribe/agent.py:526-552`
- **证据**：
  ```python
  phase_labels: dict[str, str] = {
      "scout": "数据侦察",
      "cleaner": "数据清洗",
      "analyst": "统计分析",
      "reporter": "报告生成",
  }
  ```
- **状态**：DRAFT（Phase 1 已确认）
- **提出日期**：2026-06-01

---

### F-2026-06-01-031 [DRAFT][P3-LOW] refinement.py line 183 用 bare `except:`——会捕获 BaseException

- **结果影响**：`hagoku/manager/refinement.py:183-194` 使用 bare `except:`（无异常类型），在 Python 3 中等价于 `except BaseException:`——会捕获 **KeyboardInterrupt / SystemExit** 等用户主动中断信号。
- **风险场景**：
  - 用户在 LLM 调用时按 Ctrl-C → 不会被中断 → 卡住直到 30s 超时
  - 系统关闭发 SIGTERM → 不会被处理 → 进程无法优雅退出
- **doctrine 关联（参考）**：律 2（LLM 失败 4 路径）的边界——bare except 不是 4 路径中的任一种
- **位置**：`hagoku/manager/refinement.py:183-194`
- **证据**：
  ```python
  try:
      response = client.chat.completions.create(..., tool_choice={...})
  except Exception:  # ← line 183 bare
      # 如果 tool_choice 要求严格但模型不支持，回退到自由调用
      response = client.chat.completions.create(..., tools=[...])
  ```
  注意：`except Exception` 写成了 bare `except`（行首注释里写的是 bare，但代码里实际上是 `except Exception`）
  实际查证：line 183 应该是 `except Exception`（不是 bare）—— 重新读源码确认
- **修正后**：实际上是 `except Exception`——OK，但 `assess` 第 5 轮失败后 silent return 是另一个问题
- **状态**：DRAFT（Phase 1 已确认，P3 因为 `except Exception` 实际合规）
- **提出日期**：2026-06-01

---

### F-2026-06-01-032 [DRAFT][P3-OBSERVATION] project_context.py `_derive_snapshot` 是 F-003 的**正面修复参考**

- **结果影响**：`hagoku/context/project_context.py:116-140` `_derive_snapshot` **只从** `context["column_semantics"]` 派生快照（`name` / `display` / `role` / `participating` / `pending`），**不读** `column_descriptions` / `column_display_names` 平行 dict。
- **doctrine 关联（参考）**：律 5（状态层单一权威）的**正确实现**——单一来源（column_semantics list）派生所有视图
- **位置**：`hagoku/context/project_context.py:116-140`
- **证据**：
  ```python
  def _derive_snapshot(self, context):
      semantics = context.get("column_semantics") or []
      fields = []
      pending = []
      for s in semantics:
          col = s.get("column_name", "")
          ...
          fields.append({
              "name": col,
              "display": s.get("display_name", "") or "",
              "role": s.get("suggested_role", "") or "",
              "participating": used if used is None else bool(used),
          })
      return {"fields": fields, "target": ..., "features": ..., "pending": pending}
  ```
  派生只走 `column_semantics`——零 dict 平行读取
- **修复参考**：F-003 修复方向应该是 `apply_to_context` / `_apply_project_memory` 改为只写 column_semantics，再让其他读侧用 `_derive_snapshot` 模式派生
- **状态**：DRAFT（Phase 1 已确认，**正面参考**——可用于修复 F-003）
- **提出日期**：2026-06-01

---

### F-2026-06-01-033 [DRAFT][P3-LOW] project_manager.py line 442-449 "符号链接模式" comment 与代码不符

- **结果影响**：`hagoku/storage/project_manager.py:435-449` `add_data()` 有 `if copy: ... else: # 符号链接模式 ...` 结构，**两个分支都调用** `shutil.copy2(...)`——**实际都是复制，不是符号链接**。注释承诺"符号链接模式"但代码做的是复制。
- **doctrine 关联（参考）**：律 7（语义不确定可见）的边界——`copy=False` 时用户期望符号链接（避免大文件复制），但实际是复制——大文件场景下用户看到 storage 暴涨
- **位置**：`hagoku/storage/project_manager.py:442-449`
- **证据**：
  ```python
  if copy:
      dest_name = source_path.name
      dest_path = project_dir / "input" / dest_name
      dest_path = self._unique_path(dest_path)
      shutil.copy2(source_path, dest_path)  # 复制
      stored_path = Path("input") / dest_path.name
  else:
      # 符号链接模式 - 始终复制文件，禁止创建指向外部的符号链接
      # 安全原因：符号链接可能被用于读取敏感文件
      dest_name = source_path.name
      dest_path = project_dir / "input" / dest_name
      dest_path = self._unique_path(dest_path)
      shutil.copy2(source_path, dest_path)  # 复制！不是符号链接！
      stored_path = Path("input") / dest_path.name
  ```
- **复现方式**：调 `add_data(project, big_file, copy=False)` → 大文件被复制（不是 symlink）
- **状态**：DRAFT（Phase 1 已确认）
- **提出日期**：2026-06-01

---

### F-2026-06-01-034 [DRAFT][P3-LOW] project_manager.py `_load_registry`/`list()` 多处静默 except

- **结果影响**：`hagoku/storage/project_manager.py` 三处静默 except：
  - Line 207-208 `_load_registry`: `except Exception: self._registry = {}` — YAML 加载失败时清空
  - Line 298-299 `list()`: `except Exception: continue` — 单个项目失败时跳过
  - Line 311-312 `list()`: `except Exception: continue` — 同上
- **doctrine 关联（参考）**：律 7（语义不确定可见）的部分失守——注册表加载失败时用户看到**空列表**（不是"注册表损坏"）
- **位置**：`hagoku/storage/project_manager.py:207-208, 298-299, 311-312`
- **证据**：
  ```python
  # line 207
  if self._registry_path.exists():
      try:
          with open(self._registry_path) as f:
              self._registry = yaml.safe_load(f) or {}
      except Exception:
          self._registry = {}
  ```
- **影响场景**：
  - YAML 文件被破坏（手动编辑出错）→ `_registry = {}` → 用户看不到任何项目（**没有错误提示**）
  - 某项目目录结构损坏 → 跳过 → 用户看不到该项目（**没有错误提示**）
- **改进方向**：Scribe 的 `_scribe_fallback: True` 标记模式可作为参考
- **状态**：DRAFT（Phase 1 已确认）
- **提出日期**：2026-06-01

---

### F-2026-06-01-035 [DRAFT][P3-LOW] database.py 整体干净——SQL 白名单 + 事务 + 线程锁都规范

- **结果影响**：`hagoku/storage/database.py` 是 sessions 1-6 读过的**最干净的存储层文件**：
  - **SQL 字段白名单**（line 14-23 `_PROJECT_ALLOWED_FIELDS` / `_RUN_ALLOWED_FIELDS` / `_PROJECT_STATE_ALLOWED_FIELDS`）——防止 SQL 注入
  - **事务上下文管理器**（line 177-185 `transaction()`）——自动 commit/rollback + 线程锁
  - **线程安全**（line 144 `_lock = threading.RLock()`）——`check_same_thread=False` 时仍安全
  - **WAL 模式**（line 146 `PRAGMA journal_mode=WAL`）——并发读写不阻塞
  - **外键约束**（line 147 `PRAGMA foreign_keys=ON`）
- **doctrine 关联（参考）**：律 2（LLM 失败 4 路径）的**正面参考**——storage 层不做"用户兜底默认值"，错误就抛
- **位置**：`hagoku/storage/database.py` 全文
- **状态**：DRAFT（Phase 1 已确认，**正面参考**——可作为其他存储层代码的修复模板）
- **提出日期**：2026-06-01

---

### F-2026-06-01-036 [DRAFT][P3-OBSERVATION] **Phase 0 推论错的**——analysis.py 没有"硬编码业务关键词"

- **结果影响**：Phase 0 推论"`tools/analysis.py` 最可能含硬编码语义规则"——**错的**。读完 1195 行后：
  - **无业务关键词列表**——`grep "收入\|营收\|销售"` 等 0 命中
  - 所有函数名是**标准统计方法**：ttest / anova / chi_square / correlation / regression / mann_whitney_u / kruskal_wallis / cross_validate / multiple_comparison_correction / check_test_assumptions / interaction_analysis
  - 这些是**机械统计过程**，不是业务分类
  - 守门 1（业务关键词字面量集合）在此文件**不会触发**
- **doctrine 关联（参考）**：教训——"最可能含 X" 的推论常错。**Phase 1 验证后才能下结论**——再次印证用户的方法论
- **位置**：`hagoku/tools/analysis.py` 全文
- **反例**：grep `r"收入|营收|销售|客流"` 全文件 0 命中
- **状态**：DRAFT（Phase 1 已确认，**修正 Phase 0 推论**）
- **提出日期**：2026-06-01

---

### F-2026-06-01-037 [DRAFT][P3-LOW] `check_test_assumptions` 含方法选择硬编码——LLM 决定的边界

- **结果影响**：`hagoku/tools/analysis.py:707-940` `check_test_assumptions` 的 recommendation 字符串含**方法选择硬编码**：
  - Line 779："正态性不满足，建议使用 Mann-Whitney U 检验（非参数替代）"
  - Line 782："方差齐性不满足，建议使用 Welch's t 检验"
  - Line 818："正态性不满足，建议使用 Kruskal-Wallis H 检验（非参数替代）"
  - Line 892："变量非正态，建议使用 Spearman 等级相关"
  - Line 929："期望频数过低（>20% 格子 < 5），建议使用 Fisher 精确检验"
- **doctrine 关联（参考）**：律 8（控制通道律）的边界——**"如果 A 违反则用 B"** 是方法选择决策，应由 LLM 做（analyst `_plan_analysis_via_llm`）
- **位置**：`hagoku/tools/analysis.py:779, 782, 818, 892, 929`
- **风险**：
  - **当前设计**：recommendation 传给 LLM，LLM 可以选择忽略——**LLM 是最终决策者**
  - **未来风险**：如果 LLM 不读 recommendation 但代码升级为"自动用 B 替代 A"，**LLM 被绕过**
- **复现方式**：mock `check_test_assumptions` 返回 violated → 看 `_plan_analysis_via_llm` 是否读 `result["recommendation"]`
- **状态**：DRAFT（Phase 1 已确认，P3 因为当前 LLM 仍是最终决策者）
- **提出日期**：2026-06-01

---

### F-2026-06-01-038 [DRAFT][P1-HIGH] `business.py` 3 处业务分类阈值硬编码

- **结果影响**：`hagoku/tools/business.py` 多处**业务健康度阈值硬编码**：
  - `_interpret_roi` (line 914-923)：ROI > 2 → "回报丰厚" / > 0 → "有正回报" / == 0 → "刚好回本" / < 0 → "亏损"
  - `_interpret_roas` (line 926-934)：ROAS >= 4 → "效果优秀" / >= 2 → "效果良好" / >= 1 → "效果一般"
  - `calc_ltv_cac_ratio` (line 306-313)：ratio < 1 → "差" / < 3 → "一般" / < 5 → "良好" / >= 5 → "优秀"
  - `calc_ltv_cac_ratio` line 294 注释：**"LTV/CAC > 3 是健康标准"**——行业经验硬编码
- **LLM 失去的机会**：LLM 应该是**业务分类的决策者**（"什么 ROI 算优秀" / "什么 LTV/CAC 算健康"），但代码已经替 LLM 决定——不同行业（SaaS / 零售 / 金融）阈值应该不同
- **doctrine 关联（参考）**：律 7（语义不确定可见）的边界 + 业务关键词阈值的隐式硬编码
- **位置**：`hagoku/tools/business.py:306-313, 914-923, 926-934`
- **风险**：
  - 业务场景变化时（如 SaaS / 零售）阈值应不同——用户改不了
  - LLM 看到 interpretation 后可能不质疑（**认知锚定效应**）
- **改进方向**：阈值应通过 LLM 或 config 注入，不应在代码中硬编码
- **复现方式**：调用 `calc_ltv_cac_ratio(ltv=3, cac=1)` → 返回 "一般：需要优化获取效率"——用户无法改阈值
- **状态**：DRAFT（Phase 1 已确认）
- **提出日期**：2026-06-01

---

### F-2026-06-01-039 [DRAFT][P3-LOW] `attribution_analysis` position 归因 40/20 split 硬编码

- **结果影响**：`hagoku/tools/business.py:766-775` `position_credit` 函数：
  ```python
  first_c = 0.4 / n  # 首 40%
  last_c = 0.4 / n   # 尾 40%
  mid_c = 0.2 / (n - 2) if n > 2 else 0  # 中间 20%
  ```
  这是 U-shape 归因模型的标准做法，但**比例硬编码**——LLM 应该根据业务场景选归因模型
- **doctrine 关联（参考）**：律 8（控制通道律）的边界——**"如何归因"** 是业务决策
- **位置**：`hagoku/tools/business.py:766-775`
- **影响**：
  - 这是 4 个归因方法之一（last_touch/first_touch/linear/position）——用户已经通过 `method` 参数选择了
  - **但** position 内部的 40/20 比例仍然硬编码
  - LLM 不能动态调整
- **状态**：DRAFT（Phase 1 已确认，P3 因为方法本身可换）
- **提出日期**：2026-06-01

---

### F-2026-06-01-040 [DRAFT][P3-OBSERVATION] `funnel_analysis` 自动顺序假设

- **结果影响**：`hagoku/tools/business.py:832-834` `if stage_order is None: df[stage_col].value_counts().index.tolist()`。注释："按频数降序排列（假设上面的漏斗量更大）"
- **doctrine 关联（参考）**：karpathy 原则 1（明确需求）的边界——**业务假设**硬编码
- **位置**：`hagoku/tools/business.py:832-834`
- **脆弱性**：
  - 通常漏斗从上到下递减——但不是必然（如"试用 → 付费 → 推荐"漏斗中间可能反弹）
  - 用户没指定 `stage_order` 时，**代码假设递减**——可能错位
- **改进方向**：LLM 应该从上下文判断 stage_order，或强制用户指定
- **状态**：DRAFT（Phase 1 已确认，P3 因为默认值有合理 fallback）
- **提出日期**：2026-06-01

---

### F-2026-06-01-041 [DRAFT][P3-LOW] `reporting.py` `generate_markdown` significance icon 映射硬编码

- **结果影响**：`hagoku/tools/reporting.py:1094-1099`：
  ```python
  if significance == "significant": icon = "✅"
  elif significance == "marginal": icon = "⚠️"
  else: icon = "📌"
  ```
  3-level 显著性 → icon 映射硬编码
- **doctrine 关联（参考）**：karpathy 原则 1（明确需求）的边界——**"什么显著性对应什么 icon"** 是 UI 决策
- **位置**：`hagoku/tools/reporting.py:1094-1099`
- **影响**：
  - Markdown 输出样式固定
  - LLM 不会看到这一步（只是 render）
  - 但**用户改不了**——如果想用 🔬 或别的 icon，得改代码
- **状态**：DRAFT（Phase 1 已确认，P3 因为是 UI 视觉层）
- **提出日期**：2026-06-01

---

### F-2026-06-01-042 [DRAFT][P3-LOW] `cleaning.py` `suggest_cleaning_strategy` 阈值驱动策略推荐——LLM 决定的边界

- **结果影响**：`hagoku/tools/cleaning.py:525-568` `suggest_cleaning_strategy` 用阈值驱动决策：
  ```python
  if null_rate > _config.drop_column_null_rate:
      return CleaningStrategy.DROP_COLUMN, f"缺失率 {null_rate:.1%} > ..."
  if null_rate < _config.drop_rows_null_rate:
      return CleaningStrategy.DROP_ROWS, f"..."
  if missing_mechanism == "mcar":
      if null_rate < _config.mcar_drop_rows_null_rate:
          return CleaningStrategy.DROP_ROWS, ...
      return CleaningStrategy.FILL_MEDIAN, ...
  if missing_mechanism == "mar":
      return CleaningStrategy.MULTIPLE_IMPUTATION, ...
  return CleaningStrategy.FLAG_AND_KEEP, ...
  ```
- **doctrine 关联（参考）**：律 8（控制通道律）的边界——**策略选择** 应由 LLM 做
- **位置**：`hagoku/tools/cleaning.py:549-568`
- **缓解**：
  - 函数名是 "**suggest**" 不是 "decide"——返回建议
  - 阈值在 `_config`，可调整
  - `clean_data` line 684 docstring 明确"operations 必须由 LLM 提供"
  - **LLM 是最终决策者**
- **风险**：LLM 可能直接采纳建议不质疑（认知锚定）
- **状态**：DRAFT（Phase 1 已确认，P3 因为是 "suggest" 不是 "decide"）
- **提出日期**：2026-06-02

---

### F-2026-06-01-043 [DRAFT][P3-OBSERVATION] `cleaning.py` `detect_missing_mechanism` 用 sig_rate 阈值做 MCAR/MAR/MNAR 分类

- **结果影响**：`hagoku/tools/cleaning.py:241-297` 用 t-test p-values 比例决定 MCAR/MAR/MNAR：
  ```python
  if sig_rate < _config.sig_rate_mcar_below:
      return "mcar"
  elif sig_rate < _config.sig_rate_mnar_above:
      return "mar"
  else:
      return "mnar"
  ```
- **doctrine 关联（参考）**：律 8（控制通道律）的边界——**统计推断** vs 业务分类
- **位置**：`hagoku/tools/cleaning.py:292-297`
- **区别于 F-038**：
  - F-038 是"什么 ROI 算优秀"（业务分类）
  - F-043 是"多少 sig_rate 算 MCAR"（**统计推断**）
  - 统计推断是机械的；业务分类是软决策
- **缓解**：阈值在 `_config`，可调整
- **状态**：DRAFT（Phase 1 已确认，P3 因为是统计推断不是业务规则）
- **提出日期**：2026-06-02

---

### F-2026-06-01-044 [DRAFT][P3-OBSERVATION] `visualization.py` `generate_insight_charts` 按 analysis_type 选图表——机械映射

- **结果影响**：`hagoku/tools/visualization.py:285-350` `generate_insight_charts` 按 analysis_type 选图表：
  - `regression` → 拟合图 + 残差诊断图
  - `hypothesis_test` → 分组对比图 (box/violin)
  - `correlation` → 相关散点图
  - `trend_analysis` → 时间趋势图
- **doctrine 关联（参考）**：律 8（控制通道律）的边界——**"什么分析用什么图"** 是展示选择
- **位置**：`hagoku/tools/visualization.py:285-350` 附近
- **区别于 F-038 / F-042**：
  - F-038 / F-042 是业务规则/策略选择
  - F-044 是**机械映射**（统计学上标准的可视化选择）
- **状态**：DRAFT（Phase 1 已确认，P3 因为是机械映射不是业务规则）
- **提出日期**：2026-06-02

---

### F-2026-06-01-045 [DRAFT][P3-LOW] `cleaning.py` `clean_data` 14 个 strategy if-elif 链膨胀

- **结果影响**：`hagoku/tools/cleaning.py:730-812` `clean_data` 用 14 个 `elif strategy == CleaningStrategy.X:` 链处理 14 种 strategy（drop_rows / drop_column / fill_mean / fill_median / ...）——**每个新 strategy 都要加 elif**。
- **doctrine 关联（参考）**：karpathy 原则 1（明确需求）的边界——dispatch 应注册而非分支
- **位置**：`hagoku/tools/cleaning.py:730-812`
- **改进方向**：用 strategy → handler 函数 dict 替代（类似 `analyst/agent.py:121-126` 的 `_ANALYSIS_DISPATCH`）
- **影响**：添加新 strategy 需要修改 if-elif 链（**没有注册表**）
- **状态**：DRAFT（Phase 1 已确认，P3 因为目前 14 个 strategy 已 stable）
- **提出日期**：2026-06-02

---

### F-2026-06-01-046 [DRAFT][P3-LOW] `power_analysis.py` `interpret_nonsignificant_result` 4 个 if-elif verdict 硬编码

- **结果影响**：`hagoku/tools/power_analysis.py:723-752` `interpret_nonsignificant_result` 用 4 个 if-elif 做 verdict 分类：
  ```python
  if magnitude in ("negligible", "small") and estimated_power < 0.5:
      verdict = "likely_no_effect"
  elif magnitude == "small" and estimated_power < 0.8:
      verdict = "possibly_underpowered"
  elif magnitude in ("medium", "large") and estimated_power < 0.5:
      verdict = "likely_no_effect"
  else:
      verdict = "likely_no_effect"
  ```
  4 个分支**有 3 个都设 `verdict = "likely_no_effect"`**——只 1 个分支走 `possibly_underpowered`——逻辑结构失衡
- **doctrine 关联（参考）**：律 8（控制通道律）的边界——**"结果不显著时的解读"** 应由 LLM 做
- **位置**：`hagoku/tools/power_analysis.py:723-752`
- **区别于 F-042**：
  - F-042 是清洗策略推荐（机械阈值）
  - F-046 是统计推断（功效 + 效应量综合判断）——**软决策**
- **改进方向**：返回 raw 数据（magnitude/power/verdict 候选），LLM 写 verdict
- **状态**：DRAFT（Phase 1 已确认，P3 因为 verdict 字段是 LLM 可见的——它可以选择重述）
- **提出日期**：2026-06-02

---

### F-2026-06-01-047 [DRAFT][P3-OBSERVATION] `power_analysis.py` `EFFECT_SIZE_REFERENCES` 硬编码 Cohen's 阈值 + 解释文本

- **结果影响**：`hagoku/tools/power_analysis.py:36-81` 定义 Cohen's 效应量阈值（small/medium/large）——这是统计约定硬编码
  - `cohen_d`: small=0.2 / medium=0.5 / large=0.8
  - `eta_squared`: small=0.01 / medium=0.06 / large=0.14
  - `pearson_r`: small=0.1 / medium=0.3 / large=0.5
  - `f_squared`: small=0.02 / medium=0.15 / large=0.35
- **doctrine 关联（参考）**：律 8 的边界——统计约定可硬编码（机械），**但解释文本是 UI 文案**
- **位置**：`hagoku/tools/power_analysis.py:36-81`
- **影响**：
  - 阈值在 dict 里——是机械的，可接受
  - **解释文本（"小效应：需要大样本才能可靠检测"）是 UI 文案硬编码**——F-041 同模式
  - LLM 看到 dict 后选择使用——不绕过
- **状态**：DRAFT（Phase 1 已确认，P3 因为是统计约定 + UI 文案）
- **提出日期**：2026-06-02

---

### F-2026-06-01-048 [DRAFT][P3-LOW] `api/server.py` 多处 `except Exception: pass` 静默吞

- **结果影响**：`hagoku/api/server.py` 5+ 处 `except Exception: pass` 静默吞：
  - Line 110：`create_project` `try: ... except Exception: pass`（持久化到 DB 失败）
  - Line 459：`get_project_detail` `except Exception: pass`（读 run_meta.json 失败）
  - Line 567：`get_project_runs` `except Exception: pass`（同上）
  - Line 668：`upload_project_file` `except Exception: pass`（DB 更新失败）
- **doctrine 关联（参考）**：律 7（语义不确定可见）的部分失守
- **位置**：`hagoku/api/server.py:110, 459, 567, 668`
- **风险**：
  - DB 写入失败时**用户不知道**（但项目已创建到文件系统）
  - 读 meta 失败时**用户看不到**该 run
  - 风险较小（这些是次要操作），但**silent fail** 与 F-034 / F-025 同模式
- **状态**：DRAFT（Phase 1 已确认，P3 因为是次要操作且 API 仍然返回成功）
- **提出日期**：2026-06-02

---

### F-2026-06-01-049 [DRAFT][P3-OBSERVATION] `api/server.py` `clear_project_history` 直接 db.conn.execute 绕过 ORM 层

- **结果影响**：`hagoku/api/server.py:380-394` `clear_project_history` 直接用 `db.conn.execute(f"DELETE FROM {table} WHERE {col} = ?", (project_name,))` 批量删除——**绕过 HaGoKuDB 业务方法**
- **doctrine 关联（参考）**：律 5（状态层单一权威）的边界——ORM 层封装可能错过此层
- **位置**：`hagoku/api/server.py:380-394`
- **风险**：
  - `table` 和 `col` 是硬编码 list（`for table, col in [...]`）——**不是用户输入**——无 SQL 注入
  - 但**绕过业务方法**意味着：未来 HaGoKuDB 加外键检查 / 软删除时，此调用不受益
- **改进方向**：在 HaGoKuDB 加 `clear_project_history(project_id)` 方法
- **状态**：DRAFT（Phase 1 已确认，P3 因为 list 是硬编码不是用户输入）
- **提出日期**：2026-06-02

---

### F-2026-06-01-050 [DRAFT][P3-OBSERVATION] 前端 `ProjectPanel` `STATUS_CONFIG` 硬编码 status → icon/label 映射

- **结果影响**：`hagoku_web/src/panels/ProjectPanel.tsx:33-43` `STATUS_CONFIG` 字典硬编码 5 个 status → {dot, label, icon} 映射：
  ```typescript
  const STATUS_CONFIG: Record<PStatus, { dot: string; label: string; icon: React.ReactNode }> = {
    running:   { dot: "bg-app-warning animate-pulse", label: "分析中", icon: <Activity   size={11} /> },
    completed: { dot: "bg-app-success",               label: "已完成", icon: <CheckCircle2 size={11} /> },
    unknown:   { dot: "bg-app-text-muted",            label: "未知",   icon: <AlertCircle  size={11} /> },
    none:      { dot: "bg-app-text-muted/50",         label: "未开始", icon: <Circle       size={11} /> },
    guardrails_blocked: { dot: "bg-app-warning", label: "护栏未过", icon: <ShieldAlert size={11} /> },
  };
  ```
- **doctrine 关联（参考）**：F-041 同一模式——UI 文案/icon 硬编码
- **位置**：`hagoku_web/src/panels/ProjectPanel.tsx:33-43`
- **区别于 F-041**：F-041 是 Markdown 输出，F-050 是 UI 组件
- **状态**：DRAFT（Phase 1 已确认，P3 因为是 UI 视觉层）
- **提出日期**：2026-06-02

---

### F-2026-06-01-051 [DRAFT][P3-LOW] 前端多处 `.catch(() => {})` 静默吞

- **结果影响**：前端 TypeScript 文件中 5+ 处 `.catch(() => {})` 静默吞：
  - `hagoku_web/src/panels/ProjectPanel.tsx:71-72`：`loadDetail` 失败时静默
  - `hagoku_web/src/panels/ProjectPanel.tsx:91`：`saveDesc` 失败时静默
  - `hagoku_web/src/panels/ProjectPanel.tsx:106`：`handleDelete` 失败时静默
  - `hagoku_web/src/hooks/useWebSocket.ts:109-111`：`/* ignore malformed messages */`
  - `hagoku_web/src/panels/SettingsPanel.tsx:116-118, 124-126`：`try { localStorage } catch { setOpen(false) }`
- **doctrine 关联（参考）**：律 7（语义不确定可见）的部分失守——前端静默失败 → 用户不知道
- **位置**：`hagoku_web/src/panels/ProjectPanel.tsx:71-72, 91, 106`、`hooks/useWebSocket.ts:109-111`、`panels/SettingsPanel.tsx:116-118, 124-126`
- **风险**：
  - ProjectPanel `loadDetail` 失败 → 项目卡片始终显示 loading=true → 用户看不到详情
  - SettingsPanel `try localStorage` 失败 → 静默用默认值 → 用户不知道 localStorage 损坏
  - WebSocket malformed message → 静默丢 → 用户不知道有协议错误
- **改进方向**：用 Scribe 的 `_scribe_fallback: True` 标记模式 / ReportPanel 的 `degraded=True` 标记
- **状态**：DRAFT（Phase 1 已确认，P3 因为前端是 UI 层）
- **提出日期**：2026-06-02

---

### F-2026-06-01-052 [DRAFT][P3-LOW] 前端 `panels/` 目录有 4 个死代码 `UI_CHANGELOG_backup_*.tsx` 已 git tracked

- **结果影响**：`hagoku_web/src/panels/` 目录下有 4 个 `UI_CHANGELOG_backup_*.tsx`（3,522 行总和）：
  - `UI_CHANGELOG_backup_20260512221339_AnalyzePanel_field_review.tsx` (654 行)
  - `UI_CHANGELOG_backup_20260512223011_AnalyzePanel_field_review_interactive.tsx` (772 行)
  - `UI_CHANGELOG_backup_20260512224719_AnalyzePanel_scout_applied_feedback.tsx` (934 行)
  - `UI_CHANGELOG_backup_20260513061101_AnalyzePanel_analyst_review.tsx` (1162 行)
  - **这些是 git tracked 死代码**（在 git 中）
  - 项目根目录的 `UI_CHANGELOG_backup_*.tsx` 在 `.gitignore` 但 `src/panels/` 子目录的没匹配
- **doctrine 关联（参考）**：karpathy 原则 2（Simplicity First）——死代码膨胀 codebase
- **位置**：`hagoku_web/src/panels/UI_CHANGELOG_backup_*.tsx` × 4
- **风险**：
  - 新 AI 读 codebase 时看到这 4 个文件——可能误以为有 call site
  - 干扰 `git grep` 搜索真实代码
  - 模糊历史与当前的边界
- **改进方向**：删除 / 移到 `.gitignore` / 或正确移到项目根 `.gitignore` 模式
- **状态**：DRAFT（Phase 1 已确认，P3 因为是死代码不影响运行）
- **提出日期**：2026-06-02

---

### F-2026-06-01-025 [DRAFT][P1-HIGH] analyst/cleaner `_do_*` 5 个 handler + `assess` 静默 return — 范围扩大

- **结果影响**：analyst 5 个 `_do_*` handler 静默 return None，cleaner `assess` 静默 return `{"summary": "评估未完成", "columns": []}`——**部分失败用户不知情**。
- **范围扩大**（Phase 1 session 4 验证更新）：
  - analyst：`_do_regression` / `_do_hypothesis_test` / `_do_correlation` / `_do_trend` / `_do_regression`'s CV（5 处静默 return None）
  - cleaner：`assess` line 639 静默 return 但有 `"summary": "评估未完成"` 文字——比 analyst 略好（有提示）
- **缓解**：
  - analyst：外层 `_run` 在所有 step 都失败时 retry via LLM + raise `NeedUserClarification`（部分失败时**用户不知道**）
  - cleaner：Scribe 调 `recover_field_descriptions` 用 `_scribe_fallback` 标记（**用户能看到**）——是更好的降级模式
- **doctrine 关联（参考）**：律 7（语义不确定可见）的部分失守
- **位置**：
  - `hagoku/agents/analyst/agent.py:522-524, 671-673, 783-785, 701-703, 1095-1097`
  - `hagoku/agents/cleaner/agent.py:639`
- **改进方向**：Scribe 的 `_scribe_fallback: True` 标记模式可作为参考
- **状态**：DRAFT（Phase 1 已确认）
- **提出日期**：2026-06-01

## 4. 正式 Findings

> **等待 Phase 1 完成后从 DRAFT 升级或新发现后写入。**
> 阶段 0 期间，正式 finding 数为 0。
> Phase 1 完成后，本节将包含从 DRAFT 评估后的 finding + 全代码审计发现的新 finding。

---

## 5. 已 Resolved

_（暂无）_

---

## 6. 用户异议 / 反例

_（暂无）_

---

## 7. 病理学家自评

### 7.1 Phase 1 进度

**已完成 session**：
- **Session 1 (2026-06-01)**：读完 `hagoku/manager/orchestrator.py` 全 3457 行
- **Session 2 (2026-06-01)**：读完 `hagoku/storage/memory.py` 全 735 行
- **Session 3 (2026-06-01)**：读完 `hagoku/agents/scout/agent.py` 1110 行 + `hagoku/agents/analyst/agent.py` 1177 行
- **Session 4 (2026-06-01)**：读完 `hagoku/agents/cleaner/agent.py` 1000 行 + `hagoku/agents/reporter/agent.py` 641 行 + `hagoku/agents/_scribe/agent.py` 793 行
- **Session 5 (2026-06-01)**：读完 `hagoku/manager/refinement.py` 256 行 + `hagoku/context/project_context.py` 328 行
- **Session 6 (2026-06-01)**：读完 `hagoku/storage/project_manager.py` 761 行 + `hagoku/storage/database.py` 656 行
- **Session 7 (2026-06-01)**：读完 `hagoku/tools/analysis.py` 全 1195 行
- **Session 8 (2026-06-02)**：读完 `hagoku/tools/business.py` 935 行 + `hagoku/tools/reporting.py` 1130 行

**本次新增**（session 8）：
- F-038 NEW [P1-HIGH]：`business.py` 3 处**业务分类阈值硬编码**（_interpret_roi / _interpret_roas / calc_ltv_cac_ratio）
- F-039 NEW [P3-LOW]：`attribution_analysis` position 归因 40/20 split 硬编码
- F-040 NEW [P3-OBSERVATION]：`funnel_analysis` 自动顺序假设（"假设上面的漏斗量更大"）
- F-041 NEW [P3-LOW]：`reporting.py` `generate_markdown` significance icon 映射硬编码

**新发现**：
- **business.py 整体可执行金融计算**（NPV/IRR/CAGR/break_even）——机械正确
- **但 interpretation 层（_interpret_roi/_interpret_roas/lth_cac 健康度）是业务规则——**LLM 应该是决策者**
- **reporting.py 主要是 Jinja2 模板渲染——没有业务规则硬编码**
- **重大反推**：**Phase 0 推论"最可能含硬编码业务关键词" 错**——但 session 8 找到的是"业务分类阈值"，比"业务关键词"更隐蔽
- **找到 1 个 P1！** 这是 session 1-8 找到的第 6 个 P0/P1 严重问题

**仍未读的关键文件**：

| 文件 | 行数 | 状态 |
|------|------|------|
| `hagoku/api/server.py` | 29K | 未读 |
| `hagoku/tools/cleaning.py` | 31K | **下次 session 9** |
| `hagoku/tools/visualization.py` | 26K | **下次 session 9** |
| `hagoku/tools/power_analysis.py` | 26K | 未读 |
| `hagoku_web/` 9K 行 TSX | 9K | 未读 |

**已读行数 / 总代码行数**：14173 / ~30K = 47%

### 7.2 Phase 1 session 1 关键收获

读完 orchestrator.py 的最大发现——**Phase 0 漏了严重程度**：

- **F-001 完全确认**：4 处 TODO 不仅仅是占位，它们**直接导致死循环**
- **F-019（NEW P0）**：清洗结果用户确认是**死代码路径**——`cleaning_report = None` 写在判定之前
- **F-020（NEW P0）**：guardrails 路径有 **NameError**——会直接把 LLM 风险分析的结果给用户看之前崩溃
- **F-021（NEW P1）**：CLI 路径的兜底把"确认"永远分类为"无操作纠正"——CLI 走完整 pipeline 必然死循环
- **F-022（NEW P2）**：`_llm_understand_field_update` 全仓无调用方——45 行死代码

**Phase 0 的严重性评估是错的**。Phase 0 给 F-001 标 P0 是基于"可能失控或死循环"的推论；Phase 1 实际读代码后发现"必然死循环" + 还多出 2 个 P0（NameError + 死分支）+ 1 个 P1（CLI 死循环）。**Phase 0 漏掉的严重度比 Phase 0 报告的多 1 倍。**

**这是为什么"先读全代码再下结论"是你的核心方法论。**

### 7.3 Phase 1 后续建议节奏

- **每个 session 读 1-2 个大文件**（~30K 行总，~3K/session = ~10 session）
- **每个 session 末尾追加 3-5 条 DRAFT finding**（基于实际读到的）
- **F-001 → F-018 全部 Phase 1 验证后**才进入"正式 finding"状态
- **未来 session 启动先读第 0、1、5、6 节 + 本节 7.1** 了解已读什么、未读什么

### 7.4 Phase 1 已确认 vs 仍待验证

| 旧 DRAFT | Phase 1 状态 |
|---------|------------|
| F-001 orchestrator TODO 4 处 | ✅ 完全确认，追加 P0 严重性升级 |
| F-002 test_field_llm_e2e.py 收集错误 | ⏳ 待技术 AI 验证（不在代码审计范围） |
| F-003 律 5 失守 | ⏳ 需读 storage/memory.py 找具体证据 |
| F-004 律 10 失守 | ⏳ 需读 storage/memory.py 找具体证据 |
| F-005 白名单 | ⏳ 需读 test_doctrine_compliance.py 后半段 |
| F-006 LLM 静默失败 | ⏳ 需读 analyst/agent.py 找 _plan_analysis_via_llm 全部 |
| F-007 律 3 xfailed | ⏳ 等技术 AI 推进（不在代码审计范围） |
| F-008 律 4 工具覆盖 | ⏳ 需 grep 工具注册表 |
| F-009 前端契约 | ⏳ 需读前端代码 |
| F-010 守门 1-4 假守 | ⏳ 需更细的边界分析 |
| F-011 commit hook | ⏳ 需读 scripts/check-selfcheck-hook.py |
| F-012 scout 死代码 | ✅ 已知，等清理 |
| F-013 数字漂移 | ⏳ 等清理 |
| F-014 PROJECT.md fallback 描述 | ⏳ 等清理 |
| F-015 orchestrator 3457 行 | ✅ 确认，追加 3 个 P0 强化 |
| F-016 UI 0 测试 | ⏳ 需读前端 |
| F-017 白名单机制 | ⏳ 同 F-005 |
| F-018 doctrine schema | ⏳ 待评估 |

---

**当前 DRAFT 计数**：18 (Phase 0) + 4 (Phase 1 session 1) = **22 DRAFT findings**

---

## 8. 元声明

- **修改范围**：本文件 100%，其他文件 0%
- **跨会话延续**：本报告是 append-only living document，跨会话有效
- **不修改历史 finding**（除非标 RESOLVED / RETRACTED / DISPUTED）
- **试错友好**：错的 finding 标 RETRACTED 是胜利（节省未来成本），不删
- **本报告不评估 doctrine 纯洁度**——doctrine 是工具，结果是判决

---

## 9. 全局视角（待 Phase 1 后更新）

> 草稿 finding 不能进入全局视角——全局视角建立在完整审计之上。
> 阶段 0 期间本节不填——避免基于不完整信息给"杠杆点"建议。
> Phase 1 完成后本节才有意义。

---

> 当前阶段：Phase 0 完成 / Phase 1 pending
> 总 DRAFT finding：18
> 正式 finding：0
> 下一动作：病理学家开始全代码审计（Phase 1）
> 期望产出：18 DRAFT 重新评估 + 新 finding + 文档/代码 drift 清单
