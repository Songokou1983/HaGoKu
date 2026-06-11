# Meta 层 v2 设计 — 路径 B+（2026-06-11）

> **文档定位**：架构审核方出具，交付实施 AI 执行。
>
> **本 brief 替代** [`hagoku/docs/superpowers/specs/2026-06-09-meta-layer-design.md`](../../hagoku/docs/superpowers/specs/2026-06-09-meta-layer-design.md)（v5）。
>
> **本 brief 是** [`2026-06-11-collapse-to-single-agent-brief.md`](2026-06-11-collapse-to-single-agent-brief.md) 的子 brief。
>
> **前置依赖**：collapse brief Phase D 完成（4 agent 合 1）+ [`2026-06-11-memory-three-layer-brief.md`](2026-06-11-memory-three-layer-brief.md) 的 ② 层落地。
>
> **实施时机**：collapse brief Phase D 完成后，作为 Phase E 的特殊子项。

---

## §0 来龙去脉

### 0.1 v5 设计的初心（用户原始三需求）

2026-06-11 用户重申 Meta 层的三个原始诉求：

> 1. 日常的维护
> 2. 提示词的模拟
> 3. 防止提示词在开发过程中被过度拼装
>
> **如果提示词被判断对项目有关键作用，我觉得还是需要。**

### 0.2 为什么 v5 设计需要被替代

`2026-06-09-meta-layer-design.md` v5（858 行）的核心问题：

| 问题 | 现状 |
|------|------|
| 治标不治本 | 大部分功能是为了 watch "4 套 prompt 重拼是否被改坏"——而 collapse brief Phase B/C/D 把"重拼 prompt"这个动作本身消灭了 |
| 复杂度过高 | ~1400 行实现 / 6 phase / Prompt Lab 6 子组件 / 自检回路 / 二分查找诊断 |
| 漏新风险 | 没考虑 collapse 引入的 ② 层 lesson 系统的污染问题 |
| 没对齐用户原始需求 | inspect / gate / diagnose 三场景里"模拟器"被弱化为子工具，但用户原诉求里它是独立第 2 项 |

### 0.3 新架构下 prompt 的角色变化

Phase D 后**只剩 1 个 prompt.md**——数据分析师的全部人格 / 流程 / 判断方式 / 关注点切换都靠它。

| 时代 | prompt 风险 |
|------|------------|
| 4 agent 时代 | 4 个 prompt 各管一摊，单个坏掉只影响一段 |
| Phase D 后 | **1 个 prompt = 整个分析师**——改坏 = 全局崩溃 |

**prompt 在新架构下更关键，不是更弱。Meta 必要性也更强，不是更弱。**

### 0.4 v2 设计原则

1. 对齐用户**原始三需求**（日常维护 / 提示词模拟 / 防过度拼装）
2. 覆盖新架构**新风险**（② 层 lesson 污染）
3. **砍掉** v5 中 4-agent 时代的负担（自检回路 / 二分诊断 / inspect 大场景）
4. **保留** v5 中已入仓的基建（`config.meta_llm` / `create_meta_client` / API 端点）
5. 总行数比 v5 减 23%（~1080 vs ~1400）

---

## §1 v2 四组件总览

| 组件 | 对应用户需求 | 形态 | 行数 |
|------|------------|------|------|
| **A. Prompt Lab Web 面板** | 需求 2「提示词的模拟」 | UI 面板 + 后端 API | ~370 |
| **B. LessonAuditor Agent** | 需求 1「日常维护」+ 新风险「lesson 污染」 | 独立 LLM Agent，周期触发 | ~280 |
| **C. prompt_gate CI** | 需求 3「防过度拼装」 | CI 脚本 + pre-commit hook | ~100 |
| **D. 辅助 CLI** | 需求 1 的另一半 | 3 个独立 Python 脚本 | ~180 |
| 总计 | | | **~930** |

加上 collapse brief Phase B 已落地的 `build_messages()` 通道守门，**Meta 层全套 ~1080 行**（含已入仓的 `create_meta_client` 50 行）。

---

## §2 组件 A：Prompt Lab Web 面板

### 2.1 设计

```
hagoku_web/src/panels/PromptLabPanel.tsx   ~250 行
├── DumpPicker          ← 选历史 dump 作输入源（或"当前 chat"或"手写"）
├── PromptEditor        ← Monaco / textarea，临时改 prompt.md
├── ToolsSelector       ← 勾选要给 LLM 看哪些工具（默认全选）
├── ActionBar           ← [▶ 运行] [📋 对比原版] [💾 应用到 prompt.md]
├── ResultPanel         ← tool_calls JSON / content / tokens / duration
└── ComparePanel        ← 并排：基线 vs 当前，diff 高亮变化的 tool_calls 路径
```

### 2.2 API

```
hagoku/api/prompt_lab.py                   ~120 行

POST /api/prompt-lab/run
  body: { prompt_md: str, messages: list, tools: list, model: "meta"|"pipeline" }
  resp: { content, tool_calls, tokens, duration_ms }

POST /api/prompt-lab/compare
  body: { baseline_prompt: str, current_prompt: str, messages: list, tools: list }
  resp: { baseline: {...}, current: {...}, diff: {changed_paths, similarity} }

GET /api/prompt-lab/dumps?limit=20
  resp: { dumps: [{seq, stage, timestamp, tokens, model}] }

GET /api/prompt-lab/dump/:id
  resp: { messages, extra }
```

### 2.3 「应用到 prompt.md」的硬约束

避免"在 Lab 调好了 → 复制粘贴到 prompt.md → 忘了跑 gate"的疏漏：

**点 [💾 应用]** → 强制走 prompt_gate（组件 C）同样的对比逻辑 → diff 报告给用户 → 用户二次确认 → 写盘。

绕过 UI 直接编辑 `prompt.md` 仍由组件 C 的 pre-commit hook 守护。

### 2.4 与 v5 Prompt Lab 的差异

| 维度 | v5 | v2 |
|------|----|----|
| 子组件数 | 6（DumpPicker / AgentSelector / Editor / ActionBar / ResultPanel / ComparePanel）| 6（同，但 AgentSelector 删——只剩 1 个 agent）|
| caller=agent 参数 | 有（被 MetaAgent 调用）| **删**——v2 没有 MetaAgent 调用它 |
| 超时与重试逻辑 | 60s + 3 次重试 | 简化：30s 单次 |
| 应用到 prompt.md 流程 | 未明确 | 强制走 gate |

---

## §3 组件 B：LessonAuditor Agent

### 3.1 设计

```
hagoku/agents/lesson_auditor/
├── agent.py                       ~200 行
├── prompt.md                      ~80 行
└── __init__.py
```

**独立 LLM**：用 `create_meta_client(config)`（已入仓）跑——避免 pipeline LLM 升级时同步影响审核能力。

### 3.2 两个工作

#### 工作 1：lesson 质量审核

**触发**：
- 自动：每写入 N=10 条新 lesson 触发一次
- 手动：UI 上「立即审一次」按钮 / CLI `hagoku lesson-audit`

**职责**：
- 去重：相近 scenario / lesson 的合并提议（不自动合并，输出提议给人审）
- 标低置信：检测 `confidence=high` 但 `what_failed=none` 的疑似过度自信
- 找内部矛盾：lesson A 说"X 适用"，lesson B 说"X 不适用"——标出
- 找过拟合：scenario 描述过窄（如包含具体公司名）→ 建议泛化

**输出**：`~/.hagoku/audits/lesson_audit_<timestamp>.md` + UI 通知

#### 工作 2：跨 run 趋势报告

**触发**：每月一次（cron 或 UI 按钮）

**职责**：
- 统计本月新增 lesson 数 / 分布
- 找到分析师"反复犯同一类型错"的迹象（同 scenario 多次 lesson 但无收敛）
- 找到分析师"明显进步"的领域（某类问题 lesson 引用频次上升 + 用户 validation 比例上升）

**输出**：`~/.hagoku/audits/monthly_trend_<YYYYMM>.md` + UI 通知

### 3.3 工具 schema

```python
review_lessons_batch(lesson_ids: list[str]) -> LessonAuditReport
merge_duplicates_proposal(lesson_ids: list[str], proposed_merged: Lesson) -> None
flag_low_confidence(lesson_id: str, reason: str) -> None
write_audit_report(report_type: "quality" | "trend", content: str) -> str
```

### 3.4 LessonAuditor 不做什么

- ❌ 不修改 lesson 内容（只输出"建议"，交人/UI 审）
- ❌ 不审核 ① 学术方法库（那是静态的）
- ❌ 不审核 ③ 项目记忆（那是用户 + LLM 双向的，不归 auditor 管）
- ❌ 不做 chat / dump 异常巡检（v5 inspect 场景废弃）
- ❌ 不做单次故障诊断（用户直接看 chat）
- ❌ 不做 prompt 退化诊断（组件 C CI gate 守住）

---

## §4 组件 C：prompt_gate CI

### 4.1 设计

```
scripts/ci/prompt_gate.py                  ~100 行
```

### 4.2 触发场景

1. **CI**：PR 改动 `hagoku/agents/prompt.md` 时自动跑
2. **pre-commit hook**：本地 commit 时跑（可 `--skip-gate` 跳过，但留警告）
3. **Prompt Lab「应用」按钮**：组件 A 应用 prompt 前跑

### 4.3 逻辑

```
1. detect: git diff 触发的 prompt.md 改动
2. load baseline: git show HEAD:hagoku/agents/prompt.md
3. load current: hagoku/agents/prompt.md（工作区）
4. load corpus: tests/fixtures/gate_corpus/*.json  (10-20 个标准 dump 作为输入)
5. for each input:
     run LLM(baseline_prompt, input) → baseline_response
     run LLM(current_prompt, input)  → current_response
     compute diff:
       - tool_calls 数量变化
       - tool_calls 名称变化
       - tool_calls.arguments 字段变化（按 JSON path）
6. aggregate metrics:
     tool_calls_change_pct        ← 变化比例
     content_similarity           ← 文本相似度
7. report:
     soft gate（前 3 个月）：always pass，输出 diff 报告 + 写入校准日志
     hard gate（3 个月后）：超阈值（默认 30% tool_calls 变化）→ fail
8. 写校准日志 → ~/.hagoku/gate_calibration.jsonl
```

### 4.4 校准日志 schema

```json
{
  "date": "2026-07-01",
  "commit": "abc123",
  "baseline_sha": "def456",
  "current_sha": "abc123",
  "corpus_size": 15,
  "tool_calls_change_pct": 0.27,
  "content_similarity": 0.81,
  "soft_gate_verdict": "pass_with_warning",
  "hard_gate_verdict_simulated": "fail",
  "changed_paths": ["columns[3].used_in_analysis", "..."],
  "human_review": null,
  "accepted": null
}
```

3 个月后用此数据校准 hard gate 阈值。

### 4.5 不做什么

- ❌ 不跑全 pytest 套件（CI 另有标准 test job）
- ❌ 不诊断"为什么变了"（diff 报告人工读）
- ❌ 不写 commit message / 不自动 revert

---

## §5 组件 D：辅助 CLI

```
scripts/dev/dump_show.py                   ~50 行
  hagoku dump-show <run_id> [--seq N]
  → 渲染单条 dump 给人看（高亮 system / user / assistant / tool）

scripts/dev/lesson_review.py               ~50 行
  hagoku lesson-review [--limit 20] [--since YYYY-MM-DD]
  → 列最近 N 条 lesson 表格形式，让人快速浏览
  → 不调 LLM，纯本地

scripts/dev/health_check.py                ~80 行
  hagoku health-check
  → 一键体检：
    - dump 链路完整性（是否有缺失的 _response）
    - lesson 重复率（用简单字符串相似度，不调 LLM）
    - prompt.md 自 HEAD 起的修改状态
    - memory 三层目录完整性
```

---

## §6 实施分解

### Phase Meta-1（collapse brief Phase D 完成后立即开始）

| # | 任务 | 涉及 | 行数 |
|---|------|------|------|
| CO-M1.1 | 创建 `tests/fixtures/gate_corpus/` 标准输入集（从历史 dump 挑 15 条）| fixtures | 数据 |
| CO-M1.2 | 实现 `scripts/ci/prompt_gate.py`（组件 C）| 新建 | ~100 |
| CO-M1.3 | 加 pre-commit hook | `.git/hooks/` 或 husky | ~20 |
| CO-M1.4 | 实现 `scripts/dev/dump_show.py`（组件 D）| 新建 | ~50 |
| CO-M1.5 | 实现 `scripts/dev/lesson_review.py`（组件 D）| 新建 | ~50 |
| CO-M1.6 | 实现 `scripts/dev/health_check.py`（组件 D）| 新建 | ~80 |

### Phase Meta-2（M1 通过后）

| # | 任务 | 涉及 | 行数 |
|---|------|------|------|
| CO-M2.1 | 实现 `hagoku/api/prompt_lab.py`（组件 A 后端）| 新建 | ~120 |
| CO-M2.2 | 实现 `hagoku_web/src/panels/PromptLabPanel.tsx`（组件 A 前端）| 新建 | ~250 |
| CO-M2.3 | 接入 SettingsPanel 导航 + 路由 | 修改 | ~10 |

### Phase Meta-3（M2 通过后，可选并行 M2）

| # | 任务 | 涉及 | 行数 |
|---|------|------|------|
| CO-M3.1 | 实现 `hagoku/agents/lesson_auditor/`（组件 B）| 新建 | ~200 |
| CO-M3.2 | 起草 `lesson_auditor/prompt.md`（铁律 10 适用）| 新建 + dump 对照 | ~80 |
| CO-M3.3 | 接入触发器（lesson 写入触发 + cron 触发 + UI 按钮）| 多处 | ~50 |

---

## §7 与 collapse brief 的边界

| 由 collapse brief 负责 | 由本 brief 负责 |
|---------------------|--------------|
| Phase B `build_messages()` 通道守门 | 不重复 |
| Phase D 合并 4 agent 为 1 个 + 1 个 prompt.md | 本 brief 守护这个 prompt.md |
| Phase E 工具注册表扩张 | 本 brief 加 4 个工具到 LessonAuditor |
| Phase F 律的减法 | 本 brief 不产生新律 |
| §6 红线 L4 「Meta 层暂停」| 本 brief 启动后 L4 失效（M1 / M2 / M3 替代）|

---

## §8 与 v5 设计的对照

| 维度 | v5（858 行 spec / ~1400 行实现） | v2（本 brief / ~1080 行）|
|------|--------------------------------|------------------------|
| 总 Agent | 1 大 MetaAgent + 3 场景 + loop + 自检 | 1 LessonAuditor + 2 工作 |
| Prompt Lab Web 面板 | 6 组件 + caller=agent/human 双模式 | 6 组件 + 单模式 + 强制 gate |
| 守门 | gate 场景 + 校准日志 | 同（但只守 1 个 prompt.md，更简）|
| 巡检 | inspect 场景（4 agent 跨 dump 模式） | **废弃**（单 chat 不需要）|
| 故障诊断 | diagnose 场景（二分查找 + git 关联）| **废弃**（用户直接看 chat）|
| 自检回路 | git diff HEAD --prompt.md | **删**（gate hook 已守住）|
| lesson 守护 | **未考虑** | **核心新功能**（LessonAuditor） |
| 跨 run 趋势 | 未考虑 | LessonAuditor 月报 |
| 治标 vs 治本 | 治 4 agent 架构的标 | 守 1 prompt + 守 ② 层（治新本）|

---

## §9 审核标准

| 组件 | 验收 |
|------|------|
| A Prompt Lab | UI 能选 dump / 改 prompt / 跑 LLM / 看对比；"应用"按钮强制走 gate 流程 |
| B LessonAuditor | 真 LLM 跑通：注入 20 条带矛盾 / 重复的 lesson，生成 audit 报告能识别 |
| C prompt_gate | 改一条 prompt 关键句 → CI 报告 tool_calls_change_pct > 0；校准日志写入 |
| D 辅助 CLI | 3 个 CLI 跑通，无 crash |
| 全局 | `config.meta_llm` 配置端到端打通，未配置时回退到 pipeline + 明确警告 |

---

## §10 红线

1. **LessonAuditor 不允许修改 lesson 内容**——只能输出"建议"
2. **Prompt Lab 的"应用"按钮不允许跳过 gate**——任何旁路 = 违规
3. **prompt_gate 校准期间不允许提前转 hard**——必须 ≥ 3 个月 + ≥ 20 条校准日志
4. **`lesson_auditor/prompt.md` 修改受铁律 10 保护**——必须配 dump 对比
5. **本 brief 任何组件出现 4 agent 时代逻辑（route_to / inspect / diagnose）→ 拒绝**

---

## §11 不做什么

- 不做 v5 自检回路（git diff HEAD）
- 不做 v5 二分查找诊断
- 不做 v5 inspect 大场景
- 不做"自动修复"（铁律 -2 / -3）
- 不做 LessonAuditor 调用 Prompt Lab 形成嵌套（避免 v5 那种复杂 loop）
- 不做 A/B 测试 / 不做线上监控 / 不做 SaaS 集成（v5 § "替代方案" 结论保留）

---

## §12 成本

| 场景 | 频率 | 单次 token | 月度 token |
|------|------|----------|-----------|
| Prompt Lab 跑一次 | 按需，估月 20 次 | ~3K | 60K |
| LessonAuditor 质量审 | 每 10 条 lesson | ~5K | ~50K（若月增 100 条 lesson）|
| LessonAuditor 月报 | 月 1 次 | ~10K | 10K |
| prompt_gate CI | 每次改 prompt 的 PR | ~15K（15 corpus × 1K）| ~60K（若月 4 次 prompt 改动）|
| **合计** | | | **~180K tokens / 月** |

按云端模型估 ~$0.50/月，本地 0。**完全可忽略。**

---

## §13 v5 文档处置

`hagoku/docs/superpowers/specs/2026-06-09-meta-layer-design.md`：
- **不删**（保留决策历史，符合铁律 -1 精神）
- **文档头加 banner**：
  ```
  > ⚠️ **已被 [docs/plans/2026-06-11-meta-layer-v2-brief.md](../../../docs/plans/2026-06-11-meta-layer-v2-brief.md) 替代**
  > 
  > 本文档为 v5 历史设计，针对 4 agent 架构。
  > 2026-06-11 collapse 改造后架构变更，v2 重新设计基于「1 数据分析师 + 工具箱 + 三层记忆」。
  > 保留本文档作为决策演进记录。
  ```
