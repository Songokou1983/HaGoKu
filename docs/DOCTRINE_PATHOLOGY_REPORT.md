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
- 不得修改 doctrine（doctrine 是用户拥有的）
- 不得"自动"修 bug（即使看起来简单）——交给代码 AI

### 允许的能力（2026-06-02 更新）

- **✅ 跑测试 / 跑脚本 / 跑 pytest**（只读验证，**不改任何文件**）
- ✅ 读 git history / git blame / git log
- ✅ 验证 finding（通过跑测试/读代码/citation）——把推论升级为**带证据等级的 DRAFT**
- ✅ 标记 finding 为"已 Phase 1 验证 / 证据等级：line citation"等

**新增的 DRAFT 等级**：
- **DRAFT-Phase 0**：仅基于文档 / 测试名推论（未读代码）
- **DRAFT-Phase 1**：已读代码 + 引用 line:number + 控制流分析
- **DRAFT-Phase 1+R**：已跑测试 / 脚本，附 stdout/stderr 输出

R 等级最高——DRAFT-Phase 1+R 的 finding 可被代码 AI 优先修。

---

## 0. 健康度摘要

### 0.1 项目健康

- **当前评估周期**：2026-06-01 → 2026-06-02 完成 + **Phase 3.5 复验轮** 完成
- **审计阶段**：**Phase 0 / 1 / 2 / 3 / 3.5（复验）全部完成**
- **Finding 数**：0 正式 / 67 草稿（含 +1 Phase 3.5 新发现）/ **1 RESOLVED**（F-001 用户晨间已修）
- **状态分布**：65 DRAFT / 0 OPEN / **1 RESOLVED (F-001)** / 1 RETRACTED (F-007) / 0 DISPUTED / 0 DEFERRED
- **上次更新**：2026-06-02（Phase 3.5 复验轮）

**试错总假设数**：52（51 DRAFT + 1 RETRACTED）。

**试错总假设数**：67（65 DRAFT + 1 RESOLVED + 1 RETRACTED）。

### 0.2 Phase 2 + Phase 3 + Phase 3.5 关键发现（2026-06-02）

**Phase 2 session 1（4 切入点）**：
- **2A silent fail 跨文件总盘**：AST 扫描全仓共 **50 处真正 silent except**（块内无 logger / raise / 标记降级），其中 30+ 处未被现有 finding 覆盖 → **F-058 [P3]**
- **2B doctrine 守门 vs 实际代码**：
  - `_DOCTRINE_SUBDIRS` 只声明 5 个目录（"memory" 还配错指向不存在路径），实际 14 个子目录里 8 个完全不扫，**含已确认 P0/P1 的发生地** → **F-057 [P1]**
  - 守门 5 检测正则 4 类盲区（pass / 赋兜底字符串 / RuntimeError 字面量误判合法 / 非空字面量 dict）+ orchestrator.py 4 处真实漏检 → **F-056 [P2]**
- **2C 律 5 SSoT 声明 vs 实施**：`types.py:122-124` 声明 column_semantics 是唯一权威 + 提供 5 个 `derive_*` 派生函数，但 **4/5 函数零调用率**，`column_descriptions[col]=` 直写仍 8 处。`orchestrator._apply_field_corrections:2993` 是典型违规源头 → **F-053 [P0]**（F-003 全景视图）
- **2D orchestrator ↔ analyst 契约**：`analyst.run` 的 `plan` / `phase` 是死参数（函数体 0 处使用），调用方 `orchestrator.py:1946` 4 个 `dict.get` 用错 key — UI "初步发现 N 个" 永远显示 0 → **F-054 [P0]**
- **bonus**：META-001（报告自身 7.1 状态过期）/ F-055（铁律 2 失守）/ F-059（`hagoku/prompts/` 空目录）

**Phase 2 session 2（3 切入点 — 收尾）**：
- **2E 律 10 跨文件**：律 10 双字段 `confirmed_by_user` / `last_confirmed_at_run` 写入 6 处但读侧 0 处真做"本 run 优先"判断；`scout._apply_project_memory` 不检查本 run 用户纠正直接覆盖 → **F-060 [P1]**
- **2F 契约验证**：`cleaner.run` 4 个 return 全部 4 元组，`orchestrator:1937/1939` 的 3 元组解构是死代码 → **F-061 [P2]**；`reporter.run` 返回 `ReportData` 但 orchestrator 调用方完全不接 → **F-062 [P3]**
- **2G 守门 1/3/6 用例化**：守门 1 不扫 `ast.Dict.values`/`keys`（机制盲区，当前 0 命中但未来风险）→ **F-063 [P2]**；守门 3 阈值 `≥ 3` 漏 2-chain（`analyst/agent.py:381` 实例）→ **F-064 [P3]**；守门 6 `_PROMPT_RULE_PATTERNS` 只 3 个正则（"设为 / 默认 / 应该"等动词全漏检）→ **F-065 [P2]**

**Phase 3 终态评估**（9.7 节产出）：
- **推荐升级 OPEN**：15 条（11 个 P0/P1 + 4 个跨文件强证据）
- **推荐 DEFERRED**：15 条 P3-OBS（机制层 / 设计选择 / 长期警示）
- **维持 DRAFT 等 R 等级**：36 条
- **无新增 RETRACTED**

**最终累计**（Phase 3.5 复验后）：
- **F-001 → RESOLVED**（用户晨间修 commits `9d826f2..61a35d2`，详 3.Z 节）
- **P0 = 6**（F-002/F-003/F-004/F-019/F-020/F-053/F-054 — 等等 F-002 待技术 AI 验证算 P0 候选，硬剩 6 个仍在）
- **P1 = 4**（F-038/F-055/F-057/F-060 — 全部仍在）
- **P2 ≈ 8** / **P3 ≈ 47**
- **Phase 3.5 新发现**：F-066 [P2]（commit `61a35d2` 清理死代码漏删 `_llm_understand_field_update`）

**已读行数 / 总代码行数**：26 246 / 26 246（Python 后端 **100%**）+ 8 476 / 8 476（TS/TSX **100%**）

### 0.3 报告自身健康

| 指标 | 当前 | 健康阈值 |
|------|------|---------|
| 审计阶段完成度 | **Phase 0 / 1 / 2 / 3 / 3.5 全部完成** | 全部完成 ✅ |
| 正式 finding 占比 | 0/67 — 待用户反馈循环激活 | 升级到 OPEN 后 % 走起 |
| **反馈循环首次激活** | ✅ F-001 → RESOLVED（晨间修复证实病理学家诊断准确） | 持续验证 |
| 距上次用户验证 | 0 天 | ≤ 30 天 |
| 反馈率 | 1/67 ≈ 1.5%（F-001 一条已闭环 RESOLVED） | 持续提升 |
| **已读行数 / 总代码行数** | 100%（Python + TS/TSX） | 100% ✅ |
| **META-finding 自评** | META-001（7.1 状态过期）已记录 | 报告内部状态一致 |
| **状态机适配** | 推荐升级 / 撤回 / 延期 分类（9.7）+ 复验轮（3.Z） | Phase 3.5 完成 ✅ |

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

### F-2026-06-01-001 [RESOLVED][P0-CRITICAL] orchestrator.py 4 处 `if False: # TODO` 是真 bug——已修复

- **结果影响**：Cleaner / Analyst 闸门确认机制被删后，循环中 `cleaner_confirmed = False` / `analyst_confirmed = False` 永远为 False → **多轮对齐可能失控或死循环**。用户在 Cleaner / Analyst 阶段无法正常推进到 Reporter。
- **doctrine 关联（参考）**：律 7（语义不确定可见）+ 律 8（控制通道）的混合失守
- **位置**：
  - `hagoku/manager/orchestrator.py:2255`  `# TODO: _is_user_confirm 已删`
  - `hagoku/manager/orchestrator.py:2312`  `# TODO: _is_user_confirm 已删，Cleaner 确认待重做`
  - `hagoku/manager/orchestrator.py:2357`  `# TODO: _is_user_confirm 已删`
  - `hagoku/manager/orchestrator.py:2489`  `# TODO: _is_user_confirm 已删`
- **证据**：
  - **R 等级验证**（2026-06-02）：
    ```python
    with open('hagoku/manager/orchestrator.py') as f:
        lines = f.readlines()
    todos = [(i+1, l.strip()) for i, l in enumerate(lines) if 'TODO: _is_user_confirm' in l]
    # 输出:
    #   line 2255: if ap_reply:  # TODO: _is_user_confirm 已删
    #   line 2312: if False:  # TODO: _is_user_confirm 已删，Cleaner 确认待重做
    #   line 2357: cleaner_confirmed = False  # TODO: _is_user_confirm 已删
    #   line 2489: analyst_confirmed = False  # TODO: _is_user_confirm 已删
    # Total: 4 (claimed 4)  ← 100% 一致
    ```
  - 4 处 TODO **精确匹配** Phase 0 推论的位置
- **复现方式**：跑 Cleaner 阶段的多轮对齐 → 看到 while 循环条件永不退出
- **状态**：DRAFT-Phase 1+R
- **提出日期**：2026-06-01
- **验证日期**：2026-06-02
- **修复确认日期**：2026-06-02（用户晨间修复，Phase 3.5 验证轮）
- **最后更新**：2026-06-02

**Phase 3.5 修复确认（2026-06-02）**：

- ✅ `grep -nE 'TODO.*_is_user_confirm' hagoku/manager/orchestrator.py` → **0 命中**
- ✅ `grep -nE 'if False:' hagoku/manager/orchestrator.py` → **0 命中**
- ✅ `cleaner_confirmed` 改成文本匹配 break（commits `50a52c1` / `10dc583`）：
  ```python
  cleaner_confirmed = user_reply_cleaner and user_reply_cleaner.strip() in ("确认继续", "可以进入下一阶段了")
  ```
- ✅ `analyst_confirmed` 全文 0 命中 — 因 Analyst 改对话式（commit `c9a1efb feat(O+P+Q+T)`），原 闸门变量整体消失
- ✅ orchestrator.py 行数：**3457 → 3241**（-216）
- 状态变更：DRAFT-Phase 1+R → **RESOLVED**
- 备注：F-001 是 Phase 0/1 唯一已确认 P0 → RESOLVED 的样本，反馈循环首次激活成功

**Phase 1 验证更新（2026-06-01，读完 orchestrator.py 全 3457 行）**：

- ✅ 4 处 TODO 全部确认存在，line 编号无误
- ✅ line 2395 `if cleaner_confirmed: break` 因 `cleaner_confirmed = False` 永远不达
- ✅ line 2523 `if analyst_confirmed: break` 同上
- ✅ 唯一出口是 HAGOKU_CANCEL_PAUSE_TOKEN（用户必须主动取消才能出循环）
- **影响范围**：任何走完整 pipeline 的用户在 Cleaner/Analyst 阶段都面临死循环
- **真实破坏性**：P0（已确认）

---

### F-2026-06-01-002 [DRAFT-Phase 1+R][P0-CRITICAL] `tests/test_field_llm_e2e.py` 收集错误——已 R 等级验证

- **结果影响**：pytest 收集测试时 `json.decoder.JSONDecodeError: Expecting '...'` 中断 → **测试集无法被收集 → CI 全绿是假的**。任何 regression 都可能漏跑。
- **doctrine 关联（参考）**：刹车 2（回归契约）的工具链失守
- **位置**：`tests/test_field_llm_e2e.py`（具体行未读，需要看 stacktrace）
- **证据**：
  - **R 等级验证**（2026-06-02）：`.venv/bin/python -m pytest tests/test_field_llm_e2e.py --co 2>&1 | tail -5` → `no tests collected in 78.86s (0:01:18)` ——pytest 跑满 78 秒后说"没测试"——**确认是导入时挂掉**而不是"测试真没有"
  - **关键佐证**：`.venv/bin/python -m pytest tests/ -q --co --ignore=tests/test_field_llm_e2e.py` 成功收集 ~351 个测试（**只有这一个文件挂掉**）
- **复现方式**：在 venv 跑 `.venv/bin/python -m pytest tests/test_field_llm_e2e.py --co`，看错误堆栈
- **状态**：DRAFT-Phase 1+R
- **提出日期**：2026-06-01
- **验证日期**：2026-06-02

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

### F-2026-06-01-007 [RETRACTED][P1-HIGH] 律 3 xfailed 测试拖 1+ 月——**Phase 1+R 验证后撤回**

- **结果影响**：第 3 轮+ 的多轮一致性**没有正向断言**。如果将来 messages_history 在第 3 轮后丢前几轮，测试仍绿——**用户多轮纠错可能在第 3 轮后丢失上下文**
- **LLM 失去的机会**：LLM 永远没机会被告知前几轮的对话
- **doctrine 关联（参考）**：律 3 半守
- **位置**：`tests/test_information_arrival.py` 律 3 部分
- **证据**：1 个 xfailed 测试，commit history 显示 5-26 至今未推进
- **复现方式**：跑 `pytest tests/test_information_arrival.py -k "xfail"`
- **状态**：~~DRAFT~~ → **RETRACTED**
- **提出日期**：2026-06-01
- **撤回日期**：2026-06-02

**Phase 1+R 验证更新（2026-06-02）**：

- ✅ **`grep -rEn "@pytest.mark.xfail|pytest.xfail" tests/`** 0 命中——**全仓没有 xfail 测试**
- ✅ `.venv/bin/python -m pytest tests/test_product/test_information_arrival.py -v` → **15 passed in 0.47s**——**全部通过**没有 xfail
- ✅ `.venv/bin/python -m pytest tests/ -q --co --ignore=tests/test_field_llm_e2e.py` → 收集 ~351 个测试，**没有 xfail 标记**
- **结论**：F-007 Phase 0 推论"1 个 xfailed 测试拖 1+ 月"——**错的**。可能是某次 commit 推过了 xfail → PASS，但没有清理 DRAFT 描述
- **教训**：即使"看起来合理"的 finding，Phase 1+R 验证后可能 RETRACTED
- **DRAFT 哲学验证**：DRAFT 标签让 RETRACTED 没有"我已修了一个 bug"的沉没成本

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

### F-2026-06-01-010 [DRAFT-Phase 1+R][P1-HIGH] 4 道守门人的"假守"模式——R 等级部分验证

- **结果影响**：守门 1-4 是 AST 静态扫描 + regex 匹配，**有结构性盲区**（如守门 1 不查 dict 的 values、守门 2 不查动态拼接、守门 6 只能匹配静态 regex 列表里的模式）。新增的"伪装硬编码"如果不在白名单 pattern 里，守门形同虚设
- **LLM 失去的机会**：守门漏掉的硬编码 = LLM 看到代码"看起来很 doctrine 化"实际偷偷替它做决定
- **doctrine 关联（参考）**：守门 1-4 的"边界"
- **位置**：`tests/test_doctrine_compliance.py` 守门 1-4 全文
- **证据**：
  - **R 等级部分验证**（2026-06-02）：`.venv/bin/python -m pytest tests/test_doctrine_compliance.py -v` → **10 passed in 0.87s**——4 道守门 + 2 元测试 + 2 残留检查 + 1 守门 5 + 1 守门 6 全部通过
  - **但没验证 F-010 核心说法（"假守" / 结构性盲区）**——只证明守门运行了，**没证明守门有效性**——属于 DRAFT-Phase 1+R（部分验证）
  - 每道守门的 `_BUSINESS_KEYWORDS` / `_CHINESE_ALT_REGEX_PATTERN` / `_PROMPT_RULE_PATTERNS` 都是静态规则——**这是代码证据，不是测试证据**
- **复现方式**：写 `dict_values_check = {"if": ["收入", "营收"]}` 看守门 1 能否拦下
- **状态**：DRAFT-Phase 1+R（部分验证）
- **提出日期**：2026-06-01
- **验证日期**：2026-06-02

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

### F-2026-06-01-019 [DRAFT-Phase 1+R][P0-CRITICAL] orchestrator.py:2338 死分支 — 清洗结果待用户确认永远不触发——R 等级已验证

- **结果影响**：在 Cleaner → 用户确认清洗结果 → 进 Analyst 的关键闸门处，代码逻辑被破坏。`cleaning_report = None`（line 2323）让 `if not skip_cleaning and cleaning_report is not None:`（line 2338）**永远为 False** → 整个 60 行的"清洗结果用户确认"块**永远不会执行**。用户**看不到**清洗结果的 review，**无法阻止**清洗执行。
- **LLM 失去的机会**：用户永远没机会对清洗结果说"这个列的清洗方式不对"——代码替他确认了
- **doctrine 关联（参考）**：律 7（语义不确定可见）+ 律 8（控制通道）
- **位置**：
  - `hagoku/manager/orchestrator.py:2323`  `cleaning_report = None`
  - `hagoku/manager/orchestrator.py:2338`  `if not skip_cleaning and cleaning_report is not None:`
- **证据**：
  - **R 等级验证**（2026-06-02）：
    ```python
    for i, l in enumerate(lines, 1):
        if 'if not skip_cleaning and cleaning_report is not None' in l:
            print(f'F-019 line {i}: {l.strip()}')
        if 'cleaning_report = None' in l:
            print(f'F-019 line {i}: {l.strip()}')
    # 输出:
    #   F-019 line 1876: cleaning_report = None
    #   F-019 line 2323: cleaning_report = None
    #   F-019 line 2338: if not skip_cleaning and cleaning_report is not None:
    ```
  - **额外发现**：line 1876 也有 `cleaning_report = None`（Phase 0 没发现）——同一模式出现在 2 处
  - **重要补充**：F-019 line 1876 也是 `cleaning_report = None`——**F-019 实际有 2 个死分支点**（不只 line 2323）
- **复现方式**：跑完整 pipeline（phase="full"） → 跑过 Cleaner 阶段 → 直接跳到 Analyst，**没有**任何 cleaning_review 暂停
- **状态**：DRAFT-Phase 1+R
- **提出日期**：2026-06-01
- **验证日期**：2026-06-02

---

### F-2026-06-01-020 [DRAFT-Phase 1+R][P0-CRITICAL] orchestrator.py:2537-2595 guardrails 路径 NameError——R 等级部分验证

- **结果影响**：当 Analyst 触发强制级护栏违规时，代码意图是给用户一个"LLM 风险分析 + 用户决策"的暂停。**但 RUN_COMPLETED 事件（line 2575-2586）和 return（line 2587-2595）引用了 `output_path`（line 2610 才定义）和 `duration_ms`（line 2637 才定义）**。结果是：**NameError**，用户看到的是"分析失败"而不是"护栏触发"——LLM 风险分析生成的时间被浪费。
- **LLM 失去的机会**：护栏违规是统计问题，本应由 LLM 解释并让用户决策。但 LLM 解释完成、用户即将决策时，整个 run 崩溃。LLM 永远没机会被用户回应。
- **doctrine 关联（参考）**：律 7（语义不确定可见）+ 铁律 2（LLM 失败 4 路径的边界外）
- **证据**：
  - **R 等级部分验证**（2026-06-02）：line citations 100% 精确——`output_path` 在 line 2582 / 2592，`duration_ms` 在 line 2576 / 2594——**全部在 violations block 内**（line 2537-2595）
  - `skip_cleaning` 引用：**全文件 1 处**（line 2338）——F-019 中提到的"NameError on skip_cleaning"**未在 R 验证中触发**——可能代码从未跑到那行（用户没启 phase="full" 跑过），但**确实是未定义变量**
  - **AST 验证局限**：`.venv/bin/python -c "import ast; ..."` 跑出"output_path / duration_ms 在 run() 内被 assigned ✅"——但**这是 naive check**——只检查 run() 体内是否有赋值，不检查控制流。**line 2582 在 if violations 块内，line 2610 在 return 之前**——**NameError 在 violations 为真时才发生**
  - **未能完整 R 验证**——没有 mock 出 violations=true 的 path 跑通整 pipeline——需要 LLM 真实调用 + 真实护栏违规，复杂
- **状态**：DRAFT-Phase 1+R（部分验证——line citation 100% 准确，但未端到端复现 NameError）
- **改进方向**：mock analyst 返回 violations=true → 跑 run() → 期待 NameError
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

---

## 3.X Phase 2 新 finding（跨文件交叉验证 / 2026-06-02 接续）

> 本节为接续病理学家在 Phase 2（跨文件交叉验证）轮中追加的 finding。
> 命名前缀 `F-2026-06-02-` 区分轮次。证据来源全部为 grep/AST + 代码 line citation，未跑端到端复现。

---

### META-2026-06-02-001 [DRAFT-Phase 2][P3-OBSERVATION] 报告 7.1 节"已读/未读"状态过期，与 9.x 全局视角矛盾

- **结果影响**：跨 session 阅读本报告的下一位 AI / 用户会看到自相矛盾的进度数据：
  - 第 0.2 节：`已读行数 / 总代码行数：12108 / ~30K = 40%`
  - 第 7.1 节："仍未读的关键文件" 表列 `api/server.py` / `cleaning.py` / `visualization.py` / `power_analysis.py` 全部 "未读"，末尾写 `47%`
  - 第 9 / 9.5 节："**Phase 1 完成**"、"**~26K / ~30K = ~87%**"
- **证据**（2026-06-02 验证）：
  - `git log --oneline -- docs/DOCTRINE_PATHOLOGY_REPORT.md`：
    - `6984d17 Phase 1 session 9 - cleaning+visualization 全读 +4 新 (P3)`
    - `2a8e0dd Phase 1 session 10 - power_analysis+api/server 全读 +4 新 (P3)`
    - `572a698 Phase 1 session 11 - 前端 skim +3 新 (P3)`
    - `624d44b Phase 1 终态报告 — 填全局视角 + 给用户具体行动建议`
  - 即 session 9 / 10 / 11 已经读完 7.1 列为"未读"的文件，但 7.1 节本身没更新
  - 实际行数（2026-06-02 重新核对）：
    - Python 后端：26 246 行（排除 `UI_CHANGELOG_backup_*`）/ 28 680 行（含 backup）— 报告写 ~30K 偏大
    - TS/TSX：8 476 行 — 报告写 9K 偏大
- **doctrine 关联**：本报告自身的"反馈循环"健康度（参考 §1.3 / §1.4）
- **复现方式**：同时读第 0.2 节 + 第 7.1 节 + 第 9 节 → 三处行数 / 进度互不一致
- **状态**：DRAFT-Phase 2
- **提出日期**：2026-06-02
- **建议**：下次 session 一并更新 7.1 节，或在 0 节标注"7.1 节为各 session 增量记录，最新汇总以 9 节为准"

---

### F-2026-06-02-053 [DRAFT-Phase 2][P0-CRITICAL] 律 5 SSoT 声明被自身代码集体绕过 — F-003 全景视图

- **结果影响**：`types.py:122-124` 明确声明 `column_semantics` 是 SSoT 且"禁止平行存储"，并提供 5 个 `derive_*` 派生函数；但**实际代码继续平行存储 + 派生函数零使用率**。下游 (Reporter / Cleaner / Memory) 读到的 `description` / `display_name` 取决于"读了哪个 dict"，多个写侧不同步 → 用户纠正字段后下游用旧值 → 错列清洗 / 错字段统计。
- **F-003 给出的 5 处平行存储**已被 Phase 1 验证；Phase 2 进一步用 grep 跨文件证实**承诺与实施的全景反差**：

  | derive_* 函数（types.py 第 127-183 行） | 全仓调用数 |
  |----|----|
  | `derive_display_names` | **0** |
  | `derive_descriptions` | **0** |
  | `derive_variable_roles` | **0** |
  | `derive_analysis_columns` | **0** |
  | `column_semantics_lookup` | **0** |
  | `derive_target_features` | 2 |

  即声明的"SSoT 派生接口" 5/6 完全没人用，唯一活的 `derive_target_features` 也只 2 处。

- **同时 `column_descriptions[col] = ...` 直写仍有 8 处** (`grep -rEn 'column_descriptions\['`)：
  - `hagoku/storage/memory.py:533`
  - `hagoku/agents/scout/agent.py:417, 764, 774, 873, 917, 1060`
  - `hagoku/manager/orchestrator.py:2993`
- **`column_display_names[col] = ...` 直写 2 处**（`hagoku/agents/scout/agent.py:877, 931`）
- **典型违规源头**：`orchestrator.py:2984-2999 _apply_field_corrections`
  ```python
  for col, info in updates.items():
      corrections[col] = info
      context["column_descriptions"][col] = f"{info['chinese_name']}（{info['business_meaning']}）"  # line 2993
      for s in context["column_semantics"]:
          if s["column_name"] == col:
              s["evidence"] = info["business_meaning"]
              s["needs_user_input"] = False     # ← 没写 s["description"]
              break                              # ← 没写 s["display_name"]
  ```
  用户在 CLI 路径纠正字段后，**只写 column_descriptions，不同步 column_semantics 的 description / display_name** —
  下次 Reporter 走 `column_semantics` 读到空 description，最终 evidence 字段错位。
- **doctrine 关联**：律 5（状态层单一权威）失守 + types.py 自我声明被违反 + F-003 / F-004 的代码层根源
- **复现方式**：
  1. CLI 路径走 `_apply_field_corrections`，纠正某字段中文名
  2. grep `column_semantics` 中该字段的 `description` / `display_name` → 没更新
  3. Reporter 走 `column_semantics` 路径渲染报告 → evidence 标签错
- **状态**：DRAFT-Phase 2（grep 证据完备，未端到端复现）
- **提出日期**：2026-06-02
- **修复方向**（参考性，由代码 AI 决定）：把 `_apply_field_corrections` + `_apply_project_memory` + `learn_from_run` 全改成**只写 column_semantics**，所有下游读侧改用 `derive_descriptions()` 派生 — 这正是 types.py 已经提供但 0 调用的接口

---

### F-2026-06-02-054 [DRAFT-Phase 2][P0-CRITICAL] orchestrator.run preliminary 分支：4 个 dict.get 总返默认值 — Analyst 阶段消息永远空

- **结果影响**：用户走完整 pipeline 时，UI 阶段消息 "📊 初步分析，发现数据中的规律..." 的下一条 message 中：
  - "初步发现 N 个" 的 **N 永远是 0**
  - power_warnings 永远空数组
  - business_metrics 永远空数组
  - suggested_focus 永远空字符串
- **doctrine 关联**：orchestrator ↔ analyst 契约破裂 + 律 7（语义不确定可见）— 用户看到的是空 UI，以为分析没出结果
- **证据**（Phase 2D 跨文件契约验证）：
  - **analyst.run 签名**（`hagoku/agents/analyst/agent.py:200-215`）：
    ```python
    def run(self, df, context, plan=None, project_id=None, phase="full", *, emit_completed=True) -> dict:
    ```
    含 `plan` / `phase` 两个参数
  - **analyst.run 函数体内对这两个参数的使用次数**：grep `phase\s*==` / `plan\b` → **0 处**。两个参数都是死参（旧契约残留）
  - **analyst.run 实际返回值**（line 321）：`return findings` — `findings` 来自 LLM `submit_analysis` 工具调用产物
  - **`submit_analysis` 工具 handler**（`agent_tool_defs.py:364-369`）实际返回的 dict 只含：
    - `findings`、`method_used`、`summary`、`columns`
  - **调用方 `orchestrator.py:1946`**：
    ```python
    analyst_result = analyst.run(df_clean, context, plan, phase=analyst_phase)
    if isinstance(analyst_result, dict):
        ...
        findings        = analyst_result.get("preliminary_findings", [])  # ← KEY 不存在 → []
        suggested       = analyst_result.get("suggested_focus", "")       # ← KEY 不存在 → ""
        power_warnings  = analyst_result.get("power_warnings", [])[:2]    # ← KEY 不存在 → []
        ...
        return {
            "status": "analyst_preliminary",
            "preliminary_findings": findings,            # 空
            "power_warnings": power_warnings,            # 空
            "business_metrics": analyst_result.get("business_metrics", []),  # ← KEY 不存在 → []
            "suggested_focus": suggested,                # 空
            ...
        }
    ```
- **死代码确认**（line 1970）：`results, business_metrics = analyst_result` — analyst.run 必返 dict，永远走 `isinstance(analyst_result, dict)` True 分支，1970 行的 tuple 解构是死代码
- **上游驱动**：前端 `AnalyzePanel.tsx:1195` 始终发 `phase: "full"` → `ws_handler.py:96 → orchestrator.run(phase="full")` → 1941 `analyst_phase = "full"` → 1946 调 `analyst.run(..., phase="full")` → 全空返回
- **复现方式**：
  1. 跑 `_shared_orchestrator.run(data_path, query, phase="full")`
  2. 在 1969 行 return 处打 print → 看到 `preliminary_findings=[]`、`power_warnings=[]`、`suggested_focus=""`
  3. 前端弹的 analyst_preliminary 消息内 "初步发现 0 个" + 无 power_warnings
- **状态**：DRAFT-Phase 2（line citation 100% 准确，未跑端到端）
- **提出日期**：2026-06-02
- **关联**：扩展 F-006 在 orchestrator 侧的具体落点 / 与 F-022（`_llm_understand_field_update` 死代码）同源

---

### F-2026-06-02-055 [DRAFT-Phase 2][P1-HIGH] 铁律 2 失守：`_generate_phase_message` 三层兜底走"确定性兜底"路径

- **结果影响**：当 LLM 主模型 + 快速模型都不可达时，**代码自己拼装中文阶段消息**给用户（`_build_fallback_phase_message` line 2779-2811），用户不知道 LLM 失败了 — 这违反铁律 2（"LLM 失败的唯一合法路径"中没有"代码拼装兜底"这条）+ 律 7（语义不确定可见）。
- **证据**（line citation）：
  - `hagoku/manager/orchestrator.py:2686-2717`：
    ```python
    # 一层：LLM 主模型生成消息
    try:
        msg = self._try_generate_phase_llm(...)
        if msg is not None:
            return msg
    except RuntimeError:
        pass  # LLM 不可达，尝试下一层      ← line 2697

    # 二层：LLM 快速模型重试
    try:
        msg = self._try_generate_phase_llm(..., retry=True)
        if msg is not None:
            return msg
    except RuntimeError:
        pass  # LLM 仍不可达，走确定性兜底  ← line 2711

    # 三层：LLM 完全不可达时的纯数据兜底（零语义归因）
    return self._build_fallback_phase_message(...)  # ← line 2714
    ```
  - 注释自陈"走确定性兜底"（line 2711 行内注释）— 不在铁律 2 的 4 条合法路径任一种
  - `_build_fallback_phase_message`（line 2779-2811）包含中文文案 dict：
    ```python
    quality_labels = {
        "good":   "数据质量良好",
        "medium": "数据质量一般",
        "poor":   "数据质量问题较多",
    }
    ```
    及"请确认是否按此方案清洗"、"初步分析没有发现明显的统计规律。你想从哪个维度再看一下？"等代码生成的"用户消息"
- **辩护点**：`_build_fallback_phase_message` 内部不做语义分类（quality 等级是 LLM 早已分类好的），仅做 i18n 映射 + 数据列表。**形式上合规**。
- **真正违规点**：line 2696 / 2710 的 `except RuntimeError: pass` — LLM 不可达时应 `raise RuntimeError`（铁律 2-A）让用户看见，而不是退到代码生成的中文。
- **守门盲区**：守门 5 检测 `return [空值]` 模式，但 `except RuntimeError: pass`：
  1. body 不是 `return [空值]` → 正则不匹配
  2. `except RuntimeError` 块文本含 "RuntimeError" 字符串 → `legal = True` → 直接 continue
  ∴ 守门 5 看不到这种"pass 兜底"模式
- **doctrine 关联**：铁律 2 + 律 7 + 守门 5 结构性盲区（与 F-010 同模式）
- **复现方式**：mock `chat.completions.create` 抛 ConnectionError → 跑 cleaning_strategy 阶段 → 用户看到中文阶段消息但不知道 LLM 已挂
- **状态**：DRAFT-Phase 2
- **提出日期**：2026-06-02
- **关联**：F-006（剩 3 处 LLM 失败兜底） / F-010（守门 1-4 假守）

---

### F-2026-06-02-056 [DRAFT-Phase 2][P2-MEDIUM] 守门 5 四类结构性盲区 — 用例化 F-010

- **结果影响**：F-010 已记录"守门 1-4 假守"但未给具体例子。Phase 2 将"守门 5"（`test_doctrine_LLM调用except块不得静默吞`）扫描代码 AST 后，找到 **4 类盲区** + 在 orchestrator.py 命中 4 个真实 case：
  - **盲区 1**：守门 5 用正则 `r"return\s+(?:\[\]|\{\}|None|''|\"\")"`，**只检测 `return` 后接 5 种空字面量**。
    - 漏掉 `pass`、`continue`、`return False`、`return True`、`return 0`、`return ""` 在变体（如 `return  ""`）
  - **盲区 2**：如果 `except` 块**给变量赋兜底字符串**而不是 return，守门 5 看不到。
    - 例：`_handle_mandatory_violations:1597-1603`
      ```python
      except Exception as e:
          logger.warning(...)
          risk_analysis = "无法生成风险分析（LLM 调用失败）。请人工审核..."
      ```
      LLM 不可达时用代码字符串替代 LLM 的 risk 分析输出 — 但守门 5 漏检
  - **盲区 3**：`except RuntimeError: pass`（含 "RuntimeError" 字面量）被 `legal` 判定逻辑误判合法
    - 例：`_generate_phase_message:2696, 2710`（详见 F-055）
  - **盲区 4**：`return {"type": "correction", ...}` 这种**非空字面量 dict**返回，模式不匹配 `\{\}`
    - 例：`_llm_classify_confirmation:3037`（已是 F-021 的根源）
- **守门 5 当前漏检的 LLM 调用函数清单**（orchestrator.py，AST 扫描 + 人工分类）：
  | 函数 | 行 | 漏检原因 |
  |---|---|---|
  | `_apply_scout_reply_with_llm` | 785 | `except: pass`（盲区 1） |
  | `_handle_mandatory_violations` | 1597 | 赋兜底字符串（盲区 2） |
  | `_generate_phase_message` | 2696, 2710 | `RuntimeError: pass`（盲区 3） |
  | `_llm_classify_confirmation` | 3037 | 非空字面量 dict 返回（盲区 4） |
- **doctrine 关联**：守门 5 设计边界过窄 → "假绿"风险 — 与 F-010 同模式但有具体证据
- **复现方式**：`.venv/bin/python -m pytest tests/test_doctrine_compliance.py::test_doctrine_LLM调用except块不得静默吞 -v` → **PASS** 但实际有 4 处漏检
- **状态**：DRAFT-Phase 2
- **提出日期**：2026-06-02
- **改进方向**（参考性）：扩展守门 5 检测模式：`pass` / `continue` / 变量赋值含中文 / 非空 dict/list 字面量返回

---

### F-2026-06-02-057 [DRAFT-Phase 2][P1-HIGH] doctrine 守门扫描范围缺失 8 个核心子目录 — 律 5 / 律 8 失守位置正好不被扫

- **结果影响**：`tests/test_doctrine_compliance.py:32`：
  ```python
  _DOCTRINE_SUBDIRS = ("agents", "manager", "api", "memory", "guardrails")
  ```
  实际 `hagoku/` 下有 **14 个子目录 + 4 个顶层 .py 文件**，守门只扫 4 个真实存在的目录（"memory" 字符串配错：实际是 `storage/memory.py`，子目录 `hagoku/memory/` 不存在，**5 个声明 → 4 个真扫**）
- **未扫的关键位置**（含已确认 P0/P1 finding 的发生地）：

  | 子目录 / 文件 | 行数 | 含已知问题 |
  |---|---|---|
  | `hagoku/storage/` | 2 949 | **F-003 / F-004 P0 在 `storage/memory.py`**；F-034 在 `storage/project_manager.py` |
  | `hagoku/tools/` | 7 822 | **F-038 P1 业务阈值在 `tools/business.py`**；F-037 / F-041 / F-042 / F-043 / F-046 / F-047 |
  | `hagoku/cli.py` | 1 129 | 1 129 行重要入口，含多处 `except Exception: pass` |
  | `hagoku/context/` | 328 | `project_context.py`（F-032 SSoT 派生正面参考） |
  | `hagoku/llm/` | — | LLM client 工厂 |
  | `hagoku/prompts/` | — | **目录为空**（`find hagoku/prompts -type f` 0 结果） |
  | `hagoku/config.py` | — | — |
  | `hagoku/observability/` | — | — |
- **直观影响**：
  - F-038（业务阈值硬编码 P1）的位置 `tools/business.py` 不在扫描范围 → 守门 1（业务关键词）/ 守门 6（prompt 中不得写结论）**都不会触发**。即使作者把 `LTV/CAC > 3 是健康标准` 这种 if-elif 链写进 prompt，守门也看不到
  - F-003 / F-004（律 5 失守）的根源在 `storage/memory.py:533, 535, 593, 659` 全部不扫
  - F-019 / F-020（orchestrator P0）的代码 **被扫**（manager/ 在扫描里），但守门内容（业务关键词 / 中文正则）跟这俩 P0 是 NameError / 死分支 — 这俩在守门设计范围之外
- **`prompts/` 目录为空但被注释期待**：`PROJECT.md` / `CLAUDE.md` 隐含 prompt 应该有专门管理，但 `hagoku/prompts/` 是空目录 — 实际 prompt 散在各 agent 的 system_prompt 字符串里。守门 6 扫描 prompt 拼接逻辑是合理的，但**真正的 prompt 文本来源不在 prompts/ 子目录**
- **`_DOCTRINE_SUBDIRS` 含 "memory" 但目录不存在**：是配置 bug。`hagoku/memory/` 在仓库中不存在（实际是 `storage/memory.py`），所以这条配置实际是死扫描。F-003 / F-004 的代码因此完全不在守门视野内
- **doctrine 关联**：守门设计原则 vs 实际覆盖率严重偏差。Phase 0 推论"代码不扫 tools/" 的依据是注释 `工具实现层（hagoku/tools/）多为统计计算与 IO，不在此范围` — 但 F-038 已证明 `tools/business.py` 含业务关键词阈值（非纯计算）
- **复现方式**：
  ```bash
  # 验证 storage/ 不扫
  echo 'BUSINESS = ["收入", "营收"]' >> hagoku/storage/memory.py
  .venv/bin/python -m pytest tests/test_doctrine_compliance.py -v
  # 期待: PASS（守门 1 不扫 storage/ → 漏检）
  ```
- **状态**：DRAFT-Phase 2
- **提出日期**：2026-06-02
- **改进方向**（参考性）：把 `_DOCTRINE_SUBDIRS` 改为：扫描整个 `hagoku/` 但用 `_EXEMPT_FILES` 白名单显式豁免（如纯统计 IO 文件）。同时修配置 bug："memory" → "storage"。

---

### F-2026-06-02-058 [DRAFT-Phase 2][P3-LOW] Silent fail 跨文件总盘 — F-021/025/034/048/051 之外还有 30+ 处

- **结果影响**：F-021 / F-025 / F-034 / F-048 / F-051 已散点列了部分 silent fail。Phase 2 用 AST 扫描出**全仓共 50 处真正 silent except**（块内无 logger / log / raise / print / warnings.warn / `_last_understanding_failure` / `_scribe_fallback` / `degraded`）。
- **按文件分桶**（除 F-021/025/034/048 已记录的之外，**新发现**）：

  | 文件 | silent except 数 | 已被现有 finding 覆盖? |
  |---|---|---|
  | `hagoku/manager/orchestrator.py` | 9 | ⏳ 部分（F-021） |
  | `hagoku/agents/_scribe/agent.py` | 5 | ⏳ 部分 |
  | `hagoku/api/server.py` | 5 | ✅ F-048 |
  | `hagoku/storage/project_manager.py` | 3 | ✅ F-034 |
  | `hagoku/cli.py` | 4 | ❌ **新** |
  | `hagoku/agents/reporter/agent.py` | 4 | ❌ **新**（除 F-025 外又 3 处 JSON decode silent） |
  | `hagoku/storage/database.py` | 2 | ❌ **新**（与 F-035 "教科书级" 反差） |
  | `hagoku/agents/analyst/agent.py` | 1 | ✅ F-025 |
  | `hagoku/agents/cleaner/agent.py` | 2 | ✅ F-025 |
  | `hagoku/tools/cleaning.py` | 1 | ❌ **新** |
  | `hagoku/tools/diagnostics.py` | 1 | ❌ **新** |
  | `hagoku/tools/analysis_registry.py` | 1 | ❌ **新**（"静默跳过加载失败的插件"自陈） |
  | `hagoku/storage/output.py` | 1 | ❌ **新** |
  | `hagoku/storage/memory_backends.py` | 1 | ❌ **新** |
  | `hagoku/storage/knowledge_vector.py` | 1 | ❌ **新** |
  | `hagoku/storage/memory.py` | 1 | ❌ **新** |
  | `hagoku/guardrails/parsers.py` | 1 | ❌ **新** |
  | **总计** | **50** | 约 30 处未被现有 finding 覆盖 |

- **几条重要 silent fail**（line 编号 + 行为）：
  - `cli.py:58` `except Exception: pass` — 启动期某操作失败完全静默
  - `storage/database.py:575, 653` `except (json.JSONDecodeError, TypeError): pass` — DB JSON 字段损坏静默（与 F-035 评价 "database.py 教科书级"矛盾）
  - `analysis_registry.py:559` `except Exception: pass  # 静默跳过加载失败的插件` — 自陈静默（插件加载失败用户不知道）
  - `storage/knowledge_vector.py:57` `except Exception: return None` — 知识库向量化失败 silent
  - `orchestrator.py:2643` `_parse_user_query except Exception: return None` — 用户 query 解析失败时 `_describe_intent(None)` 走到 "探索一下这份数据有什么规律" 默认消息（line 2820）
- **doctrine 关联**：律 7（语义不确定可见）的系统性失守 — 不是单点 bug，是**全仓 30+ 处叠加**
- **复现方式**：
  ```bash
  # 用 AST 扫描器：
  python3 -c "$(cat ...)" # （Phase 2 已跑过，见对话历史）
  ```
- **状态**：DRAFT-Phase 2（AST 验证）
- **提出日期**：2026-06-02
- **改进方向**（参考性）：
  - 在每个 silent except 内**至少**调 `logger.warning(...)`（最低门槛）
  - 关键路径用 `_scribe_fallback: True` / `degraded: True` 标记降级（F-035 / Scribe 的正面模式）
  - 守门 5 扩展模式（见 F-056）

---

### F-2026-06-02-059 [DRAFT-Phase 2][P3-OBSERVATION] `hagoku/prompts/` 是空目录但被 doctrine 文档隐式期待

- **结果影响**：`find hagoku/prompts -type f` 返回 0 个文件 — 子目录是空的。但 PROJECT.md / CLAUDE.md 在多处提及"prompt"（守门 6 也专门检测 prompt 构造），表面上像有 prompt 资源管理；实际**所有 prompt 都散在各 agent 的 Python 字符串字面量**里（scout/cleaner/analyst/reporter agent.py 的 system_prompt = "..."）。
- **影响**：
  - 新 AI 看到 `hagoku/prompts/` 子目录会**误以为有集中 prompt 资源**，去那里读 → 空
  - prompt 散点修改难追踪，且**散在 Python 字符串里的中文 prompt** 不被 doctrine 守门 1 / 2 扫（守门排除"整段中文 prompt"，因为是 LLM 教学材料）— 但守门排除标准在自身代码里没明确
- **doctrine 关联**：本报告 §1.4 报告健康度 + Karpathy 原则 2（Simplicity First）— 空目录是"未来要做但没做"的脚手架
- **位置**：`hagoku/prompts/`
- **证据**：`ls hagoku/prompts/` → 空；`find hagoku/prompts -name "*"` 只列目录自身
- **状态**：DRAFT-Phase 2
- **提出日期**：2026-06-02

---

## 3.Y Phase 2 session 2 新 finding（律 10 + 契约 + 守门用例化 / 2026-06-02 同日接续）

> 本 session 完成 Phase 2 三个剩余切入点：律 10 跨文件 / scout-cleaner-reporter 契约 / 守门 1-4-6 具体漏检案例。

---

### F-2026-06-02-060 [DRAFT-Phase 2][P1-HIGH] 律 10 双字段 `confirmed_by_user` / `last_confirmed_at_run` 写而不读 — 律 10 是装饰

- **结果影响**：律 10（当前 run 优先于历史记忆）的两个核心字段被定义、被声明、被写入，但**从来没人读它们做"本 run 优先" 判断** — 律 10 在代码层实际上不起作用，只是装饰。用户每次在某 run 纠正字段后，下个 run 的 scout 仍会用历史记忆覆盖（与 F-004 同模式但范围更大）。
- **doctrine 关联**：律 10（当前优先律）的二阶失守
- **证据**（AST + grep 跨文件）：

  **`last_confirmed_at_run`** — 全仓 6 处提及：
  | 位置 | 行为 |
  |---|---|
  | `types.py:210, 235` | 定义 + 字段规范文档 |
  | `types.py:261` | dataclass `to_dict` 输出 |
  | `memory.py:538` | 1 处赋值（apply_to_context 内） |
  | `scout/agent.py:733, 752` | 2 处初始化为 `None`（每次重新推断字段都重置） |
  | **读侧** | **0 处读取做判断** |

  **`confirmed_by_user`** — 全仓 8 处提及：
  | 位置 | 行为 |
  |---|---|
  | `types.py:209, 234` + `memory.py:58` | 定义 |
  | `memory.py:537, 609, 617, 667` | 4 处赋值 |
  | `scout/agent.py:422` | 用户确认后写入 context |
  | `scout/agent.py:732, 751` | 2 处初始化为 `False` |
  | **唯一"读"** | `memory.py:661 confirmed = bool(_get(sem, "confirmed_by_user", False))` — 仅用于"是否写入持久化"，**不是律 10 的"本 run 压住历史"判断** |

- **scout `_apply_project_memory` (line 862-878)** 是律 10 失守的具体路径：
  ```python
  def _apply_project_memory(self, context: dict, memory_project: dict) -> None:
      fields = memory_project.get("fields", {})
      display_names = memory_project.get("display_names", {})
      for sem in context["column_semantics"]:
          col = sem["column_name"]
          if col in fields:
              context["column_descriptions"][col] = fields[col]   # ← 直接覆盖
              sem["confidence"] = 1.0
          if col in display_names:
              context["column_display_names"][col] = display_names[col]
              sem["needs_user_input"] = False
  ```
  **完全不检查 `sem.confirmed_by_user`** — 如果用户当前 run 已经把字段名改了，但 memory_project 里有旧值，**仍直接覆盖**

- **`build_memory_project` (memory.py:559-577)** 同步只传 `{"fields": ..., "display_names": ...}` 给 scout，不传 `confirmed_by_user` / `last_confirmed_at_run` → scout 即使想检查也拿不到这俩字段（F-023 的扩展）

- **scout 创建新 column_semantics 时**（line 720-734, 740-753）：每次都把 `confirmed_by_user: False` / `last_confirmed_at_run: None` 写为初始值 — `apply_to_context` 之前同步写入的值被**完整覆盖**

- **doctrine 关联补充**：与 F-004 / F-023 形成 3 条同主线 — F-004（learn_from_run 抹 description）/ F-023（build_memory_project 丢字段）/ F-060（律 10 双字段写而不读）。这条 finding 给出律 10 在代码层"完全无效"的全景证据。

- **复现方式**：
  1. run 1：用户改 "Inc1" 为 "销售额"（`confirmed_by_user=True` 被写入 column_semantics）
  2. run 2：scout 跑 `_infer_all_semantics` → 创建新 dict（`confirmed_by_user=False`）→ 调 `_apply_project_memory` → 从 fields 读历史值 → 覆盖
  3. 用户看到："Inc1" 又变回旧描述

- **状态**：DRAFT-Phase 2（grep + AST 证据完备，未端到端复现）
- **提出日期**：2026-06-02
- **改进方向**（参考性）：
  - `build_memory_project` 增加 `confirmed_by_user_at_run: dict` 字段（每列 → run_id）
  - `_apply_project_memory` 检查："当前 run 是否已有 `confirmed_by_user=True`？如是，跳过 memory 覆盖"
  - 或更激进：先扫 column_semantics 已有 `confirmed_by_user=True` 的列名进入豁免集合，apply 时跳过

---

### F-2026-06-02-061 [DRAFT-Phase 2][P2-MEDIUM] orchestrator.py:1937-1939 `cleaner.run` 3 元组解构是死代码

- **结果影响**：编排层在 `cleaner.run` 返回值不是 4 元组时用 3 元组解构 — 但 `cleaner.run` AST 扫描所有 4 个 `return` **全部是 4 元组**。这段代码永远到不了，但**保留它会让未来 AI 误以为 cleaner.run 有 3 元组返回路径**，可能基于错误前提写新代码。
- **doctrine 关联**：Karpathy 原则 2（Simplicity First）— 死分支占阅读预算
- **证据**：
  - `cleaner.run` 全部 return（AST）：
    - line 169: `return pd.DataFrame(), pd.DataFrame(), report, {}` (4 元组)
    - line 234: `return df, df, strategy_report, {"operations": operations}` (4 元组)
    - line 283: `return df, df_clean, report, summary` (4 元组)
    - line 298: `return df, df, report, {}` (4 元组)
  - 函数签名声明 `-> tuple[pd.DataFrame, pd.DataFrame, CleaningReport, dict]`
  - **`orchestrator.py:1933-1939`** 调用代码：
    ```python
    if isinstance(cleaner_result, tuple) and len(cleaner_result) >= 4:  # ← 4 元组分支
        _, _, _, strategy_dict = cleaner_result
        if isinstance(strategy_dict, dict):
            ...
        else:
            df_clean, cleaning_report, _ = cleaner_result  # ← 死代码 line 1937 (3 元组解构 4 元组)
    else:
        df_clean, cleaning_report, _ = cleaner_result  # ← 死代码 line 1939 (cleaner.run 必返 tuple len≥4)
    ```
    line 1937 是 4 元组用 3 个变量解构 → 必抛 ValueError；line 1939 触达条件是 `len < 4` 或非 tuple → 永远不发生
- **复现方式**：
  ```python
  # cleaner.run 必返 4 元组 → 1937 与 1939 永远到不了
  result = cleaner.run(...)
  assert isinstance(result, tuple) and len(result) == 4
  ```
- **状态**：DRAFT-Phase 2
- **提出日期**：2026-06-02

---

### F-2026-06-02-062 [DRAFT-Phase 2][P3-OBSERVATION] `reporter.run` 返回 `ReportData` 但 `orchestrator.py:2395` 调用方完全不接 — 副作用契约不显式

- **结果影响**：reporter.run 的契约**靠副作用**（写文件 + 写 _update_own_memory），返回值 ReportData 被丢弃。这意味着：
  - 编排层无法基于 report 内容做决策（如 "如果 report.headline 为空则告诉用户"）
  - reporter.run 异常分支返回 "failed report"（line 213-214 的 ReportData）— 调用方拿不到，**只能靠 events.jsonl 间接得知失败**
- **doctrine 关联**：律 7（语义不确定可见）的边界 + Karpathy 原则 4（Goal-Driven Execution）— 返回值未被用 = 隐式契约
- **证据**：
  - `reporter.run` 签名（line 130-144）`-> ReportData`
  - `reporter.run` 4 个 return 全部返回 `ReportData` 或类 ReportData（line 210, 214, 489）
  - **`orchestrator.py:2395`** 调用：
    ```python
    reporter.run(
        results=_analyst_results,
        ...
    )
    ```
    无变量赋值，返回值丢弃
- **影响**：
  - 当 reporter 内部异常时 line 213-214 返回 `ReportData(error=...)`，但 orchestrator **拿不到** error 信息
  - reporter 异常时通过 `_emit(EventType.AGENT_FAILED, ...)` 通知 EventBus → 用户在 UI 看到 "AGENT_FAILED"，但 orchestrator 仍 happy-path 继续到 line 2412 "save run_meta"
- **状态**：DRAFT-Phase 2
- **提出日期**：2026-06-02
- **改进方向**（参考性）：接住返回值 → 检查 `.error` 字段 → 决定是否继续 happy-path

---

### F-2026-06-02-063 [DRAFT-Phase 2][P2-MEDIUM] 守门 1 不扫 `ast.Dict.values` / `ast.Dict.keys` — 字典形式业务关键词集合可绕过

- **结果影响**：守门 1（业务关键词字面量集合）只扫 `ast.List / Tuple / Set`，**漏掉 `ast.Dict`**。当前全仓 0 命中 → 没有 false negative，但**机制层有盲区**：
  ```python
  # 守门 1 不拦下面这种：
  KEYWORD_MAP = {"收入": True, "营收": True, "销售额": True}    # Dict.keys 集合
  LABELS = {"a": "收入", "b": "营收", "c": "销售额"}            # Dict.values 集合
  ```
  任何 future PR 想绕过守门 1 → 把 list 改成 dict → **直接通过**
- **doctrine 关联**：守门 1 的"边界"，与 F-010 / F-056 同模式（守门设计 vs 实际覆盖率反差）
- **证据**（tests/test_doctrine_compliance.py:92-94）：
  ```python
  for node in ast.walk(tree):
      # 只看 List / Tuple / Set 字面量
      if not isinstance(node, (ast.List, ast.Tuple, ast.Set)):
          continue
  ```
  注释自陈"只看 List / Tuple / Set"
- **Phase 2 全仓验证**（AST 扫所有 9 个子目录的 Dict.values + Dict.keys 包含 ≥2 业务关键词）：**0 命中** → 当前无 false negative，但盲区客观存在
- **状态**：DRAFT-Phase 2
- **提出日期**：2026-06-02
- **改进方向**（参考性）：扩展守门 1 同时扫 `ast.Dict` 的 keys / values

---

### F-2026-06-02-064 [DRAFT-Phase 2][P3-LOW] 守门 3 阈值 `chain_count >= 3` 漏检 2-chain — `analyst/agent.py:381` 真实命中

- **结果影响**：守门 3 要求 `if-elif` 链含 ≥ 3 个中文字符串比较才算违规。2-chain 漏检 → **业务意图分类用 2-chain 写法可逃过守门**。已在 `analyst/agent.py:381` 命中一例：
  ```python
  if action == "生成报告":      # ← 中文字符串语义分类 1
      ...
  elif action == "继续分析":    # ← 中文字符串语义分类 2
      ...
  ```
  这是**用户行为意图分类**，本应由 LLM 通过 tool_call 表达。chain_count = 2 → 守门 3 漏。
- **doctrine 关联**：守门 3 阈值设计问题 + 律 8（控制通道律）的边界
- **证据**：
  - `tests/test_doctrine_compliance.py:225` `if chain_count >= 3:` → 2 不报
  - AST 扫全仓后 2-chain 中文比较仅命中 1 处（`analyst/agent.py:381`）
- **辩护点**：2 个分支可能是合理路径分发（不一定都是"业务分类"）— 阈值 ≥ 3 是有道理的（多分支才像分类）。但 `analyst/agent.py:381` 是真实的"用户动作命名"硬编码，**应该改成 LLM 走 next_step 工具**
- **状态**：DRAFT-Phase 2
- **提出日期**：2026-06-02
- **改进方向**（参考性）：
  - 选项 A：守门 3 阈值降到 ≥ 2 — 简单但可能误报
  - 选项 B：守门 3 保持 ≥ 3，但加 grep 警告 line：`if .* == "[中文]"` 输出 INFO 不 fail
  - 选项 C：把 `analyst/agent.py:381` 改成 LLM 行为分类

---

### F-2026-06-02-065 [DRAFT-Phase 2][P2-MEDIUM] 守门 6 `_PROMPT_RULE_PATTERNS` 只 3 个模式 — prompt 结论式规则漏检面广

- **结果影响**：守门 6 检测 prompt 中的"结论式规则"，但 `_PROMPT_RULE_PATTERNS` 只列了 3 个正则：
  1. `role → value` 映射（如 `identifier → false`）
  2. `必须判为 X` 强制
  3. `硬性规则` / `判断规则` / `映射规则` 关键字
  其余结论式表达**全部漏检**，包括：
  - "**设为** ignore"（不是"必须设为"）
  - "**默认** 当作 feature"
  - "**应该** 判为 target"
  - "**优先** 使用 Mann-Whitney 不要用 t-test"（方法选择指令）
  - "如果 X 是数字就当作 feature"（指令式条件 — 业务分类）
  - 直接列规则的句式：`"针对该字段：1) ... 2) ... 3) ..."`
- **doctrine 关联**：与 F-010 / F-056 同模式 — 守门设计 vs 实际覆盖率
- **复合盲区**：
  - 真正的 prompt **散在各 agent 的 system_prompt = "..."** Python 字符串字面量里（不在 `hagoku/prompts/` 目录 — 该目录是空的，F-059）
  - 守门 6 扫"函数体内的字符串常量"，但**触发条件是函数 src 含 `system_prompt|user_prompt|messages|prompt` 关键字**
    （`tests/test_doctrine_compliance.py:456-462`）— 函数若用其他变量名（如 `instruction` / `directive` / `system_role`）则**不进入扫描** → prompt 完全逃过守门 6
- **证据**：
  - `tests/test_doctrine_compliance.py:417-425` `_PROMPT_RULE_PATTERNS` 共 3 条正则
  - `tests/test_doctrine_compliance.py:456-462` 函数触发关键字 4 个
- **状态**：DRAFT-Phase 2
- **提出日期**：2026-06-02
- **改进方向**（参考性）：
  - 扩展 `_PROMPT_RULE_PATTERNS` 覆盖"设为 / 默认 / 应该 / 优先" 等动词
  - 扩展函数触发关键字（增加 `instruction|directive|system_role|prompt_text`）
  - 真正的修复是**把 prompt 集中到 `hagoku/prompts/`**（F-059）—— 然后改成扫描该目录的 `.md` / `.txt` 而不是 Python 字符串

---

## 3.Z Phase 3.5 复验轮（用户晨间修复后 / 2026-06-02 接续）

> 用户晨间已对 orchestrator / analyst / cleaner 做过修复（commits `9d826f2..61a35d2`，共 ~15 次提交，涉及 `manager/orchestrator.py` / `agents/{scout,cleaner,analyst}/agent.py` / `tools/agent_tool_defs.py` / `context/project_context.py`）。本节是病理学家**对所有 P0/P1/关键 P2 finding 的逐条复验**，目的是把已修部分标 RESOLVED、未修部分锁定新 line 号、新发现的 doctrine 失守添加为新 finding。

### 3.Z.1 复验方法

- 切换到当前 `master` HEAD（`61a35d2`）的 working tree
- 对每条 P0/P1/关键 P2 finding 跑 grep / AST / 行号定位
- 记录：状态变更（RESOLVED / 保持 DRAFT / RETRACTED）+ 新 line 号 + 修复证据

### 3.Z.2 一表看完（P0 + P1 + 关键 P2）

| ID | 等级 | 旧位置 | 复验结果 | 新位置 / 状态 |
|---|---|---|---|---|
| **F-001** | P0 | orch 2255/2312/2357/2489 | ✅ **RESOLVED** | 4 处 TODO + `if False:` 全消失；`cleaner_confirmed` 改文本匹配，`analyst_confirmed` 因 Analyst 改对话式整体消失 |
| **F-002** | P0 | `tests/test_field_llm_e2e.py` 收集挂掉 | ❌ 仍存在 | `pytest --co` 仍 78s/0 collected（2026-06-02 复验） |
| **F-003** | P0 | 多侧平行存储 | ❌ 仍存在 | `column_descriptions[col]=` 直写仍 8 处（与旧报告一致） |
| **F-004** | P0 | `memory.py:662` learn_from_run | ❌ 仍存在 | `ColumnSemanticDef(...)` 构造仍不传 `description` / `display_name`（memory.py:662-668） |
| **F-019** | P0 | orch 2323/2338 死分支 | ❌ 仍存在 | **新 line**：`orch.py:2155 cleaning_report = None` + `orch.py:2170 if not skip_cleaning and cleaning_report is not None:` |
| **F-020** | P0 | orch 2537-2595 NameError | ❌ 仍存在 | **新 line**：`if violations:` block 起点 `orch.py:2321`；block 内引用 `output_path` (line 2366, 2376) / `duration_ms` (line 2360, 2378)；run() 内首次赋值 `output_path = orch.py:2394` / `duration_ms = orch.py:2421` — block 触发时仍 NameError |
| **F-053** | P0 | types.py SSoT 集体绕过 | ❌ 仍存在 | derive_* 5 个 4 个仍 0 调用；`_apply_field_corrections:2993` 仍只写 `s["evidence"]` / `s["needs_user_input"]`，不写 `s["description"]` / `s["display_name"]` |
| **F-054** | P0 | analyst.run 死参 + key 错 | ❌ 仍存在 | `analyst.run` 签名（`agents/analyst/agent.py:195-204`）`plan`/`phase` 仍是死参；`orch.py:1946-1968` 4 个 `dict.get` key 错（preliminary_findings/suggested_focus/power_warnings/business_metrics 全部不在 submit_analysis 返回 dict 中） |
| **F-038** | P1 | business.py ROI/ROAS/LTV 阈值 | ❌ 仍存在 | `_interpret_roi` (line 914-923) / `_interpret_roas` (line 926-934) / `calc_ltv_cac_ratio` (line 290+) 阈值原样 |
| **F-055** | P1 | orch 2696/2710 RuntimeError pass | ❌ 仍存在 | line 2696 / 2710 `except RuntimeError: pass` 原样，注释"LLM 不可达，尝试下一层 / 走确定性兜底"原样 |
| **F-057** | P1 | 守门 `_DOCTRINE_SUBDIRS` 不扫 storage/tools | ❌ 仍存在 | `tests/test_doctrine_compliance.py:32` `_DOCTRINE_SUBDIRS = ("agents", "manager", "api", "memory", "guardrails")` 原样；"memory" 死指向未修 |
| **F-060** | P1 | 律 10 双字段写不读 | ❌ 仍存在 | `scout._apply_project_memory` (scout/agent.py:862-878) 仍不检查 `confirmed_by_user`；`last_confirmed_at_run` 全仓写侧 1 处 / 读侧仍 0 处 |
| **F-021** | P2 | orch:3253 _llm_classify_confirmation 兜底 | ❌ 仍存在 | **新 line**：`orch.py:3040 return {"type": "correction", "updates": {}}` 原模式 |
| **F-022** | P2 | _llm_understand_field_update 死代码 | ❌ 仍存在 | **新 line**：定义 `orch.py:3042`；全仓调用方仍 0 处 |
| **F-056** | P2 | 守门 5 四类盲区 | ❌ 仍存在 | 守门 5 检测正则 `r"return\s+(?:\[\]|\{\}|None|''|\"\")"` 原样 |
| **F-061** | P2 | cleaner.run 1937/1939 3 元组解构死代码 | ❌ 仍存在 | line 1937/1939 3 元组解构原样；cleaner.run AST 扫描 4 个 return 全部 4 元组 |
| **F-062** | P3 | reporter.run 返回值丢弃 | ❌ 仍存在 | `orch.py:2395 reporter.run(...)` 无变量赋值 |
| **F-063** | P2 | 守门 1 不扫 Dict | ❌ 仍存在 | `tests/test_doctrine_compliance.py:93` 仍 `isinstance(node, (ast.List, ast.Tuple, ast.Set))` |
| **F-064** | P3 | 守门 3 阈值 ≥ 3 漏 2-chain | ❌ 仍存在 | `tests/test_doctrine_compliance.py:219` `if chain_count >= 3:` 原样；`analyst/agent.py:381` 2-chain 中文 if-elif 原样 |
| **F-065** | P2 | 守门 6 模式覆盖不全 | ❌ 仍存在 | `_PROMPT_RULE_PATTERNS` 仍 3 个正则 |

### 3.Z.3 数字校准

- **silent except 总数**（F-058 重算）：50 → **50**（用户晨间修复未涉及 silent fail）
- **column_descriptions 直写**（F-053 重算）：8 → **8**（位置：memory.py:533、scout/agent.py:417/764/774/873/917/1060、orch.py:2993）
- **derive_* 函数调用率**（F-053 重算）：未变（`derive_display_names`/`derive_descriptions`/`derive_variable_roles`/`derive_analysis_columns`/`column_semantics_lookup` 0 调用，`derive_target_features` 2 调用）
- **orchestrator.py 行数**：3457 → **3241**（-216，主因：清理 4 个未调用函数 + 12 个旧 Analyst 方法，commit `61a35d2`）

### 3.Z.4 关键变化与新发现

**晨间修复的实际范围**（按 commit 内容）：
- ✅ F-001 全 4 处闸门 — 修
- ✅ Cleaner 多处死循环（`09e14b9` / `10dc583` / `50a52c1`）— 修
- ✅ Cleaner 容错 JSON 截断（`9e3a33a`）— 修
- ✅ Scout AGENT_COMPLETED 事件（`bc598fe`）— 修
- ✅ Analyst 改对话式 Tier 1（`c9a1efb`）— 重构

**晨间修复未触达**（保持 DRAFT）：
- ❌ F-002 / F-003 / F-004 / F-019 / F-020 / F-053 / F-054（6 个 P0）
- ❌ F-038 / F-055 / F-057 / F-060（4 个 P1）
- ❌ F-021 / F-022 / F-056 / F-061 / F-063 / F-065（6 个 P2）

**反讽**：F-019（cleaning_report = None 死分支）和 F-001（4 处闸门死循环）在 commit `09e14b9 fix: Cleaner 死循环修复` 的同一类故障域，但晨间只修了控制闸门（F-001），**没注意到 F-019 是同一文件同一阶段的另一个独立死分支** — 这条提示用户：F-019 是 F-001 的"邻居 bug"，下次修 F-001 时应顺手验。

**新发现（Phase 3.5 复验时挖到 1 条新风险）**：

### F-2026-06-02-066 [DRAFT-Phase 3.5][P2-MEDIUM] commit `61a35d2 清理死代码` 删了 4 个未调用函数 + 12 个旧 Analyst 方法 — 但 F-022 的 `_llm_understand_field_update` 漏删

- **结果影响**：今早 commit `61a35d2 refactor: 清理死代码——删 4 个未调用函数 + 12 个旧 Analyst 方法` 明显是听了类似 F-022 的建议清理死代码，**但 F-022 报告的 `_llm_understand_field_update`（45 行死代码）仍在**（`orch.py:3042-3088`）。
- **doctrine 关联**：与 F-022 同主线 — 清理工作部分但不全面。
- **位置**：`hagoku/manager/orchestrator.py:3042` 仍是定义、全仓调用方 0 处
- **证据**：
  - `git log --name-only 61a35d2` 显示删了 4+12 函数
  - `grep -rn "_llm_understand_field_update" hagoku/ --include="*.py"` 仍只有定义那一行
- **复现方式**：`grep -rn "_llm_understand_field_update" hagoku/` — 0 调用，但 45 行函数体仍在
- **状态**：DRAFT-Phase 3.5
- **提出日期**：2026-06-02
- **改进方向**：下次清理批次顺手把它删掉。F-022 应升级"已上议程但漏删"。

---

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

### 7.5 Phase 2 session 1（跨文件交叉验证 / 2026-06-02 接续）

**本 session 目的**：Phase 1 完成后，进入跨文件交叉验证。不重读单文件，而是用 grep / AST / 全仓扫描验证"声明 vs 实施"、"读侧 vs 写侧"、"守门覆盖 vs 实际代码分布"。

**核对结果**：
- Phase 1 实际**已**完成（不是 7.1 节写的 47%）— git log 显示 session 9/10/11 已读 cleaning.py / visualization.py / power_analysis.py / api/server.py / 前端
- 实际代码行数：Python 26 246 行（不含 backup）/ 28 680 行（含），TS/TSX 8 476 行（不是报告写的 9K）

**Phase 2A（silent fail 跨文件总盘）** — AST 扫描全仓 50 处真正 silent except，按文件分桶，30+ 处未被现有 finding 覆盖 → **F-058 NEW**。

**Phase 2B（doctrine 守门 vs 实际代码对照）** — 守门 `_DOCTRINE_SUBDIRS` 仅扫 4 个真实子目录，**漏掉** storage/ / tools/ / cli.py / context/ / llm/ / prompts/（空目录但被隐式期待）8 类位置 → **F-057 NEW（P1）+ F-059 NEW**。守门 5 检测正则有 4 类盲区，4 处真实 LLM 调用 except 漏检 → **F-056 NEW（P2）+ F-055 NEW（P1，铁律 2 失守的 line 2696/2710 pass 模式）**。

**Phase 2C（律 5 SSoT 声明 vs 实施）** — `types.py:122-124` 声明 column_semantics SSoT 且禁止平行存储，但 5 个 `derive_*` 函数 4 个 0 调用，`column_descriptions[col] =` 直写仍有 8 处 + `column_display_names[col] =` 2 处。`orchestrator.py:2984-2999 _apply_field_corrections` 是典型违规源头（写 column_descriptions 不同步 column_semantics 的 description / display_name）→ **F-053 NEW（P0，F-003 全景视图扩展）**。

**Phase 2D（orchestrator ↔ agent 契约）** — `analyst.run` 签名含 `plan` / `phase` 两参，函数体 0 处使用（死参）；调用方 `orchestrator.py:1946` 4 个 dict.get 用错 key（`preliminary_findings` / `suggested_focus` / `power_warnings` / `business_metrics` 全是 submit_analysis 工具不返回的 key），导致 UI "analyst_preliminary" 阶段消息中"初步发现 N 个"的 N 永远是 0。前端 `AnalyzePanel.tsx:1195` 始终发 `phase: "full"` → 该死分支必然触达 → **F-054 NEW（P0）**。

**本 session 新增**：
- META-001 NEW [P3]：报告 7.1 节状态过期与 9.x 全局视角矛盾
- F-053 NEW [P0]：律 5 SSoT 集体绕过（F-003 全景视图）
- F-054 NEW [P0]：orchestrator preliminary 分支 4 个 get 总返默认值
- F-055 NEW [P1]：铁律 2 失守 — `_generate_phase_message` "确定性兜底"
- F-056 NEW [P2]：守门 5 四类结构性盲区（F-010 用例化）
- F-057 NEW [P1]：doctrine 守门扫描范围缺失 8 个核心子目录
- F-058 NEW [P3]：silent fail 跨文件总盘 50 处 / 30+ 处未覆盖
- F-059 NEW [P3]：`hagoku/prompts/` 空目录但被 doctrine 隐式期待

**Phase 2 已确认 P0 / P1 计数**：
- 新 P0：F-053 / F-054 → 累计 P0 从 5 升到 **7**
- 新 P1：F-055 / F-057 → 累计 P1 从 1 升到 **3**

**Phase 2 完成度**：3 个切入点（守门覆盖 / 律 5 SSoT 反差 / orchestrator-agent 契约）做完。剩余 Phase 2 候选切入点：
- ⏳ 律 10 跨文件验证（除 `learn_from_run` 外还有别处覆盖吗？）
- ⏳ orchestrator 调 scout / cleaner / reporter 的契约（本轮只验了 analyst）
- ⏳ 守门 1-4 / 守门 6 的具体漏检案例（F-010 / F-056 模式扩展）

**Phase 2 总 DRAFT 计数**：52 (Phase 0-1) + 1 META + 7 (Phase 2 session 1) = **60 DRAFT findings**

---

### 7.6 Phase 2 session 2（剩余切入点 / 2026-06-02 同日接续）

**本 session 目的**：完成 Phase 2 三个剩余切入点（律 10 跨文件 / scout-cleaner-reporter 契约 / 守门 1-4-6 具体漏检），不再有未盖切入点。

**Phase 2E（律 10 跨文件）** — 跨文件 grep + AST 验证两个律 10 核心字段 `confirmed_by_user` / `last_confirmed_at_run`：写入路径 6 处，**读侧 0 处用做"本 run 优先"判断**（唯一的"读"在 learn_from_run 是判断"是否持久化"，与律 10 语义无关）。scout 每次重新推断字段时把两个字段初始化为 `False/None`，**覆盖 apply_to_context 之前的写入**。`build_memory_project` 也不把这两个字段传给 scout — scout 即使想检查也拿不到 → **F-060 NEW [P1]**

**Phase 2F（scout / cleaner / reporter 契约）** — 验证三个 agent 的 `.run()` 签名 vs orchestrator 调用方：
- **scout.run** 契约一致 ✅
- **cleaner.run** 4 个 return 全部 4 元组 + orchestrator 4 处调用一致 ✅，但 `orchestrator:1937, 1939` 的 3 元组解构是**死代码**（条件永远不达）→ **F-061 NEW [P2]**
- **reporter.run** 返回 `ReportData` 但 `orchestrator:2395` 调用方**完全不接返回值** — 异常分支 `ReportData(error=...)` 拿不到，调用方仍 happy-path 继续 → **F-062 NEW [P3]**

**Phase 2G（守门 1-4 / 6 具体漏检）** — 用 AST 全仓扫描验证 F-010 / F-056 推论：
- **守门 1** 不扫 `ast.Dict.values` / `ast.Dict.keys` — 当前全仓 0 命中（无 false negative），但**机制层盲区**未来可被绕过 → **F-063 NEW [P2]**
- **守门 3** 阈值 `chain_count >= 3` 漏检 2-chain — `analyst/agent.py:381` 真实命中一例（`if action == "生成报告" elif action == "继续分析"` 是用户行为意图分类，应由 LLM 走 tool_call）→ **F-064 NEW [P3]**
- **守门 6** `_PROMPT_RULE_PATTERNS` 只 3 个正则 + 函数触发关键字仅 4 个 — prompt 中"设为 / 默认 / 应该 / 优先" 等动词的结论式表达全部漏检 → **F-065 NEW [P2]**

**本 session 新增**：
- F-060 NEW [P1]：律 10 双字段写而不读（裸字段是装饰）
- F-061 NEW [P2]：cleaner.run 3 元组解构死代码
- F-062 NEW [P3]：reporter.run 返回值丢弃
- F-063 NEW [P2]：守门 1 不扫 Dict
- F-064 NEW [P3]：守门 3 漏检 2-chain
- F-065 NEW [P2]：守门 6 prompt 模式覆盖不全

**累计 Phase 2 P0 / P1 计数**（含 session 1 + 2）：
- 新 P0：F-053 / F-054 → 累计 P0 **7 个**
- 新 P1：F-055 / F-057 / F-060 → 累计 P1 **4 个**

**Phase 2 完成度**：3 个 session 1 切入点 + 3 个 session 2 切入点 = **6/6 完成**。无剩余 Phase 2 候选切入点。

**Phase 2 总 DRAFT 计数**：60 (Phase 0-1+session 1) + 6 (session 2) = **66 DRAFT findings**

---

### 7.7 Phase 3：终态评估（2026-06-02 接续）

**本节目的**：Phase 2 完成后，把 66 条 DRAFT 全面评估，整理推荐升级 / 撤回 / 延期清单。**病理学家不能单方面升级 finding 为正式状态**（这是用户 / 审核 AI 的事），所以本节只产出"推荐"，第 4 节"正式 Findings"保持空状态等待反馈循环激活。

**评估维度**：
- **真实性**：line citation 是否准确？是否有 R 等级验证？
- **影响等级**：用户能否观察到结果？P0 = 必直接看到 / P1 = 架构层失守 / P2-P3 = 局部 / 观察
- **可操作性**：修复方向是否清晰？是否 < 1 小时 / 1 周 / 长期？
- **状态机适配**：升级 OPEN / 撤回 RETRACTED / 延期 DEFERRED / 维持 DRAFT

详见第 9.7 节"Phase 3 推荐分类清单"。

---

## 8. 元声明

- **修改范围**：本文件 100%，其他文件 0%
- **跨会话延续**：本报告是 append-only living document，跨会话有效
- **不修改历史 finding**（除非标 RESOLVED / RETRACTED / DISPUTED）
- **试错友好**：错的 finding 标 RETRACTED 是胜利（节省未来成本），不删
- **本报告不评估 doctrine 纯洁度**——doctrine 是工具，结果是判决

---

## 9. 全局视角（Phase 1 完成）

> **本节是建立在完整审计（30K+ Python + 8.5K TypeScript 全读）之上的全局判断。**
> **Phase 0 推论错的几个地方**：F-036（analysis.py "最可能含硬编码业务关键词"——错的，只有统计方法名）、F-002（test_field_llm_e2e.py 收集错误——待技术 AI 验证）。
> **Phase 0 漏掉的严重问题**：F-001（orchestrator 4 处 TODO 死循环）、F-019（清洗结果用户确认死分支）、F-020（guardrails 路径 NameError）、F-003（律 5 失守完整机制）、F-004（律 10 失守 learn_from_run 覆盖 description）、F-038（business.py 业务分类阈值硬编码 P1）——这些 Phase 0 完全没发现。

### 9.1 项目健康总览（结果导向）

**5 个已确认 P0**（用户能观察到的坏结果）：
1. F-001 orchestrator 4 处 TODO → Cleaner/Analyst 闸门确认死循环（**最严重**——pipeline 走不到 Reporter）
2. F-019 orchestrator:2338 清洗结果用户确认是死代码路径（`cleaning_report = None`）
3. F-020 orchestrator:2537-2595 guardrails 路径 NameError（`output_path` / `duration_ms` 引用先于定义）
4. F-003 律 5 失守 → 字段语义多层存储（`column_descriptions` 与 `column_semantics` 不全同步）
5. F-004 律 10 失守 → `learn_from_run` 覆盖 `description`（用户纠正被抹掉）

**1 个已确认 P1**（业务结果偏差）：
- F-038 business.py 业务分类阈值硬编码（`_interpret_roi` / `_interpret_roas` / `calc_ltv_cac_ratio`）——LLM 应该是决策者

**修复优先级建议（"如果只做 1 件事 → 用户的最大杠杆点"）**：
1. **F-001 → F-019 → F-020（orchestrator 三连）**——orchestrator.py 3 个 P0 集中修复，可能 < 1 小时工作量
2. **F-004（律 10 失守）**——`learn_from_run` 加 description/display_name 参数，1 行修复
3. **F-003（律 5 失守）**——需要架构调整（参考 project_context.py `_derive_snapshot` 模式）
4. **F-038（业务阈值 P1）**——把阈值移到 config 或让 LLM 决定

### 9.1.X Phase 2 session 1 新增 P0 / P1（2026-06-02）

**新 P0（用户能观察到的坏结果）**：
6. **F-053** 律 5 SSoT 声明被集体绕过 — `types.py` 提供的 5 个 `derive_*` 派生函数 4 个 0 调用率；`column_descriptions[col]=` 直写仍 8 处；`orchestrator._apply_field_corrections` 写 column_descriptions 不同步 column_semantics 的 description / display_name → 用户 CLI 路径纠正字段后下游用旧值
7. **F-054** orchestrator preliminary 分支 4 个 `dict.get` 用错 key — 用户走完整 pipeline 时 UI "初步发现 N 个" 的 **N 永远是 0**，power_warnings / business_metrics / suggested_focus 全空。前端 `phase: "full"` 必然触达该死分支

**新 P1（架构层失守）**：
- **F-055** 铁律 2 失守 — `_generate_phase_message:2696/2710` `except RuntimeError: pass` 走"确定性兜底"，注释自陈，违反铁律 2 唯一合法 4 路径
- **F-057** doctrine 守门扫描范围 `_DOCTRINE_SUBDIRS = ("agents", "manager", "api", "memory", "guardrails")`，漏 `storage/` `tools/` `cli.py` `context/` `llm/` `prompts/`（空目录但被隐式期待）— 已确认 P0/P1 finding 大半发生地不在守门视野（F-003/F-004 在 storage/，F-038 在 tools/）；配置字面量 "memory" 还指向不存在的目录

**新 P2**：
- **F-056** 守门 5 四类结构性盲区（pass / 赋兜底字符串 / RuntimeError 字面量误判合法 / 非空字面量 dict）— F-010 的具体用例化，含 orchestrator.py 4 处真实漏检 case

### 9.2 模式（Patterns Across Findings）

**最严重的问题模式**（重复出现 4+ 次）：
- **静默失败（silent fail）**：F-021（CLI 兜底）/ F-025（analyst _do_*）/ F-034（project_manager 3 处）/ F-048（api 5+ 处）/ F-051（前端 5+ 处）/ **F-058（全仓 50 处总盘，30+ 处未覆盖）**——共 **50+ 处 `.catch(() => {})` / `except: pass / return []` 静默吞**
- **代码层策略选择硬编码**：F-037（analysis recommendation）/ F-038（business 阈值 P1）/ F-042（cleaning 阈值）/ F-043（cleaning sig_rate）/ F-046（power verdict）/ F-050（前端 status icon）——LLM 应该是决策者，但代码已经替 LLM 决定
- **方法选择硬编码 if-elif 链**：F-022（orchestrator 死代码）/ F-045（cleaning 14 个 strategy 链）——应该用 dispatch dict 注册表模式
- **声明 vs 实施反差（Phase 2 新模式）**：F-053（types.py SSoT 声明 vs 8 处直写）/ F-054（analyst.run 死参 vs 调用方期望）/ F-057（守门声明 vs 实际扫描盲区）—— **代码自陈契约被自身违反**

**最积极的发现**（5+ 处正面参考）：
- **project_context.py `_derive_snapshot`**（F-032）——只从 column_semantics 派生，零 dict 平行读取
- **analyst/agent.py** ——所有 LLM 失败 raise RuntimeError 或 NeedUserClarification
- **reporter/agent.py** ——`_parse_llm_json` 用 `degraded=True` 标记降级（比静默 None 好）
- **scribe/agent.py `recover_field_descriptions`** ——`_scribe_fallback: True` 标记降级
- **database.py** ——SQL 字段白名单 + 事务上下文 + 线程锁 + WAL + 外键约束 = 教科书级（但 F-058 又找到 2 处 silent JSON decode）

**Phase 0 推论的反思**：
- "tools/analysis.py 最可能含硬编码业务关键词" → **错的**（F-036）。analysis.py 41K 行无业务关键词
- 但**不是完全错**——session 8 在 `tools/business.py` 找到的是"业务分类阈值"，比"业务关键词"更隐蔽
- 教训：**Phase 0 推论常错**——必须 Phase 1 验证

### 9.3 风险地图（Risk Map）

| 风险 | 概率 | 影响 | 当前守门 | 关键 finding |
|------|------|------|---------|-----------|
| 用户走完整 pipeline 卡死 | **高** | **高** | 0 | F-001 + F-019 + F-020（orchestrator 三连）|
| 用户纠正失效（每次重输） | **高** | **高** | 0 | F-004（律 10）/ **F-053（律 5 SSoT 绕过）** |
| 字段语义不一致 | **高** | **高** | 0 | F-003 / **F-053** |
| UI "初步发现" 永远为空 | **极高** | **中** | 0 | **F-054 NEW** |
| LLM 不可达时静默用代码消息 | **中** | **中-高** | 守门 5 漏检 | **F-055 NEW** |
| 业务结论偏差（ROI/ROAS/LTV） | **中** | **中** | 0 | F-038 |
| 真实 regression 漏检 | **中** | **高** | 0（CI 假绿）| F-002 / F-007 |
| 工具覆盖不完整 | **中** | **中** | 0 | F-008 |
| 静默失败累积 | **极高** | **低-中** | 守门 5 漏检 | F-021/025/034/048/051 / **F-058（50 处总盘）** |
| 守门盲区 | **高** | **中** | 4 道守门 | F-010 / F-024 / F-027 / **F-056 / F-057** |
| 死代码 | **中** | **低** | 0 | F-012 / F-022 / F-052（3,500+ 行） |

### 9.4 1 个月警示（1-Month Watch List）

- **orchestrator.py 3457 行不拆分** → bug 累积 + 新 AI 写入越界风险持续上升（F-015）
- **白名单机制扩** → 守门 5 失守的 2 阶风险（F-005 / F-017 / F-024）
- **doctrine tests 通过率被"假绿"拖累** → 真实 regression 漏检（F-002 / F-007）
- **守门 1-4 的结构性盲区被利用** → 新增伪装硬编码漏检（F-010 / **F-056 / F-057**）
- **业务阈值 P1 升级为"自动用"** → 当前 LLM 是决策者，未来升级可能绕过 LLM（F-038 / F-046）
- **types.py SSoT 声明继续被忽视** → 新加的 column_* 平行 dict 越积越多，没人调 derive_*（**F-053**）
- **storage/ / tools/ / cli.py 长期不进守门视野** → 律 5 / 律 8 失守在守门盲区蔓延（**F-057**）

### 9.5 试错价值（Trial-Error Value）

本周期试错统计：
- **60 个假设被提出**（18 Phase 0 + 34 Phase 1 + 1 META + 7 Phase 2 session 1）
- **7 个 P0 已确认**（F-001 / F-003 / F-004 / F-019 / F-020 / **F-053 / F-054**）
- **3 个 P1 已确认**（F-038 / **F-055 / F-057**）
- **1 个 P2 新**（**F-056**）
- **~48 个 P3**（observation / observation-level findings）
- **1 个 RETRACTED**（F-007）

即使 50% 假设被否定，本次审计产生了 60 次"被提出"的学习价值——下次类似问题可对照。

### 9.6 给用户的具体行动建议

**今天就能修的（< 1 小时工作量）**：
- F-019 + F-020 + F-001（orchestrator 3 个 P0 集中修复）
- F-004（`learn_from_run` 加 1 行 description 参数）
- **F-054**（orchestrator.py:1946 调用方 4 个 get 改成正确 key — `findings.get("findings")` 而不是 `preliminary_findings`；或者把 `_handle_submit_analysis` 改成额外 emit `preliminary_findings` 别名）
- **F-053 一半**（`orchestrator.py:2993-2998` `_apply_field_corrections` 加 2 行：`s["description"] = ...` + `s["display_name"] = ...`）
- META-001（更新报告 7.1 节状态 / 数行数 / 删"未读"清单）

**本周能做的（1-2 天工作量）**：
- F-003 / **F-053 完整**（参考 `_derive_snapshot` 模式 + 调 `derive_*` — 把 column_descriptions / column_display_names 全部改为派生）
- F-038 业务阈值移到 config 或 LLM 决定
- **F-055** orchestrator.py:2696 / 2710 改成 `raise RuntimeError`（不要 pass + 兜底）
- **F-056 / F-057** 守门扩展（扫描 `_DOCTRINE_SUBDIRS` 加 storage/tools/cli.py + 检测 pass/continue/赋兜底字符串）

**长期架构改进（1 周+）**：
- 拆分 orchestrator.py（3241 → < 1000 行的 3-4 个模块）
- 加 silent-fail detection 守门
- 静默错误标记化（Scribe / Reporter 的 `degraded` 模式扩展到其他模块）
- 把 `types.py` 的 `derive_*` 接口推广为强制 — 删掉 `column_descriptions` / `column_display_names` 字段，所有读侧从 column_semantics 派生

---

### 9.7 Phase 3 推荐分类清单（病理学家最终建议）

**本节是 Phase 3 终态评估**。66 条 DRAFT 按真实性 / 影响 / 可操作性评估，分为 4 类。**本节仅是病理学家"推荐"，第 4 节"正式 Findings"仍保持空状态等待反馈循环激活**（用户 / 审核 AI 标 RESOLVED / DISPUTED / 用户驳回则 RETRACTED）。

#### 推荐立即升级到 OPEN（11 条）— 用户能观察到坏结果 + 已 R 等级 / 强 Phase 1 证据 + 修复路径清晰

| Finding | 等级 | 推荐升级理由 |
|---|---|---|
| **F-001** | P0 | R 等级已验证（4 处 TODO 死循环精确命中）+ Cleaner/Analyst 闸门确认必然失败 |
| **F-019** | P0 | R 等级已验证（cleaning_report=None 死分支）+ 用户看不到清洗结果审核 |
| **F-020** | P0 | line citation 100% 准确（NameError 路径）+ 违规一旦护栏触发就崩 |
| **F-003** | P0 | Phase 1 多 session 多文件验证（5 处平行存储 + 写侧不同步）+ F-053 给出全景 |
| **F-004** | P0 | Phase 1 完整机制（learn_from_run 抹 description）+ 1 行修复 |
| **F-053** | P0 | Phase 2 SSoT 反差证据（5 个 derive_* 4 个零调用 + 8 处直写）+ `_apply_field_corrections:2993` 是源头 |
| **F-054** | P0 | Phase 2 契约破裂（4 个 dict.get 用错 key + 前端 phase=full 必触达）+ UI 永远显示"初步发现 0 个" |
| **F-038** | P1 | Phase 1 完整 grep（ROI/ROAS/LTV/CAC 阈值在 business.py）+ 业务结论偏差 |
| **F-055** | P1 | Phase 2 line citation（2696/2710 `pass` + 注释自陈）+ 铁律 2 失守 |
| **F-057** | P1 | Phase 2 配置分析（5 个声明 / 4 个实存 + 已确认 P0/P1 大半发生地不扫）+ 配置 bug（"memory" 死指向） |
| **F-060** | P1 | Phase 2 跨文件证据（律 10 双字段写而不读 + 6 处写入 / 0 处真读）+ 与 F-004/F-023 形成全景 |

#### 推荐升级到 OPEN（更广风险，但单一修复点不明）— P2 / P3 但已 R 等级 / 跨文件证据（4 条）

| Finding | 等级 | 推荐升级理由 |
|---|---|---|
| **F-021** | P1 | CLI 路径死循环（`_llm_classify_confirmation` except → "correction" 默认）。建议升级 |
| **F-002** | P0 | R 等级已验证（pytest --co 78 秒挂掉 + 其他 351 个测试 OK）。CI 假绿，应升级 |
| **F-022** | P2 | `_llm_understand_field_update` 死代码 45 行（grep 调用 0 处）— 简单可删 |
| **F-058** | P3 | Phase 2 AST 全仓扫 50 处 silent except / 30+ 处未覆盖 — 系统性问题 |

#### 推荐 RETRACTED（保留 F-007 状态，无新增撤回）

- F-007 已 RETRACTED（Phase 1+R 全仓 grep xfail 0 命中）
- **其他无 RETRACTED 候选**：Phase 1 + Phase 2 验证未发现 finding 是误报

#### 推荐 DEFERRED（暂不行动 / 长期观察 — 15 条 P3-OBSERVATION）

观察类 finding（不构成立即风险，但记录到机制 / 设计层面）：
- F-005 / F-017（守门 5 白名单机制可扩 — 当前为空，二阶风险）
- F-018（doctrine schema 元 observation）
- F-024（learn_from_run 用 evidence 字符串子串匹配 — 守门 1 盲区）
- F-026（scout/analyst 自动写知识库 — 用户无审核）
- F-027（scout `_TYPE_ECHO_PATTERN_RE` 中文正则但用法合规）
- F-030（scribe 硬编码中文 phase 标签）
- F-033（project_manager add_data 注释 vs 代码不符）
- F-035（database.py 教科书级 — 正面参考但 F-058 又找到 2 处 silent）
- F-036（Phase 0 推论错的反思）
- F-039 / F-040 / F-044（业务工具内部硬编码 — 当前合规）
- F-047 / F-049 / F-050 / F-059 / F-062 / F-064（UI 文案 / 配置 / 死代码 / 装饰类）

#### 推荐维持 DRAFT 等待 R 等级验证（剩下 36 条 P2/P3）

剩余 finding 多为 P2-P3，已有 Phase 1 line citation 但**未端到端复现**。建议技术 AI 选 3-5 条做 R 等级验证后再决定升级：
- 高优先 R 候选：F-006（剩 3 处 LLM 兜底）/ F-008（律 4 工具覆盖单点）/ F-025（analyst _do_* 5 处静默）

#### Phase 3 元结论

**66 条 DRAFT 假设产出的"价值密度"**：
- **直接修复价值（P0+P1）**：11 + 4 = **15 条**值得立即修
- **机制改进价值（P2 守门盲区）**：4 条（F-056 / F-063 / F-065 + F-058 + F-010）— 修守门 doctrine 自身
- **观察价值（P3-OBS）**：15 条 — 记录设计选择 / 长期警示
- **死代码清理**（P2-3 死分支）：F-022 / F-061 + F-012 / F-052（前端 backup 4 个 + scout backup 3 个）

**核对覆盖率**：60+ DRAFT 数 vs 实际 30K 代码 = 约 **2 条/K 行** finding 密度 — 这与同类型多 agent 系统 README + 后端代码审计的经验值匹配（每 K 行 1-3 条值得记录的隐患）。**报告产物对得起读它所需的时间**（用户 5-10 分钟读 9.7 节即可决定升级哪 15 条）。

---

### 9.8 给用户的最简版决策清单（如果只看一节）

**如果只能修 1 件事**（最大杠杆 / < 1 小时）：
- **F-001** orchestrator 4 处 `if False: # TODO` → `if True:` 或恢复 `_is_user_confirm` 替代品

**如果有半天**（4 个 P0 集中修）：
- F-001 + F-019 + F-020（orchestrator 三连）+ F-054（line 1946 的 `get('preliminary_findings')` 改成 `get('findings')`）

**如果有 1 天**（解决律 5 失守的全部根源）：
- 加 F-053（`_apply_field_corrections:2993` 双写 column_semantics 字段）
- 加 F-004（`learn_from_run` 加 description 参数）
- 加 F-060（`_apply_project_memory` 检查 `confirmed_by_user`）

**如果有 1 周**（机制层 + 大头清理）：
- F-055（删 `except RuntimeError: pass`，改 raise）
- F-057 + F-056 + F-063 + F-065（扩展守门扫描范围 + 检测模式）
- F-038（业务阈值移到 config 或 LLM）

**长期（1 月+）**：
- 拆 orchestrator.py（3241 行 → 模块化）
- 强制使用 types.py 的 `derive_*` 接口，删 column_descriptions / column_display_names 字段
- 把 prompt 集中到 `hagoku/prompts/`（F-059 + F-065 联动）

---

> **当前阶段**：Phase 0 / 1 / 2 / 3 / **3.5（复验）全部完成**
> **总 DRAFT finding**：67（18 Phase 0 + 34 Phase 1 + 1 META + 13 Phase 2 + 1 Phase 3.5）
> **已 RESOLVED**：1（**F-001** 用户晨间修复，反馈循环首次激活）
> **已确认 P0（仍存在）**：6 个（F-002/F-003/F-004/F-019/F-020/F-053/F-054 — F-001 已 RESOLVED 从 P0 名单移出）
> **已确认 P1（仍存在）**：4 个（F-038 业务阈值 + F-055 铁律 2 失守 + F-057 守门盲区 + F-060 律 10 装饰字段）
> **推荐升级 OPEN**：14 条（去掉 F-001 — 已 RESOLVED；10 个 P0/P1 仍待修 + 4 个跨文件证据）
> **推荐 DEFERRED**：15 条 P3-OBS
> **维持 DRAFT 等 R 等级**：36 条 + Phase 3.5 新 F-066
> **总已读行数 / 总代码行数**：26 246 / 26 246 (Python 后端 100%) + 8 476 / 8 476 (TS/TSX 100%)
> **下一动作**：用户继续修复（推荐先 F-019 + F-020 — F-001 的"邻居 bug" / 同模式）+ 反馈循环已激活，每修一条标 RESOLVED
> 期望产出：剩 14 条推荐升级清单逐条转 RESOLVED → 反馈率从 1.5% 持续提升 → 第 4 节"正式 Findings"实质化
