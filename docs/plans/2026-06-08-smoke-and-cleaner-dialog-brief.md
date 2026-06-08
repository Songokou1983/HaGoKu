# 真 LLM 冒烟 + Cleaner 对话化 brief（2026-06-08）

> **文档定位**：架构审核方（Cascade）出具，交付实施 AI 执行。
>
> **前置依赖**：`2026-06-07-analyst-and-routing-brief.md` 已闭环 ✅（10 commit 通过，523 passed + 3 strict xfailed）
>
> **执行流程契约**：继承 `2026-06-07-analyst-routing-execution-protocol.md`（一次性多 commit，无中途审核，触发 §6 任一条立刻停）

---

## §0 任务定位

本 brief 完成 Analyst brief 收尾后的两件事：

1. **Phase 1 真 LLM 冒烟（必做，阻塞门）**：把 Analyst 二段化从"代码合格"推进到"产品合格"。C-2 全是 mock，真模型行为未验证。
2. **Phase 2 Cleaner 对话化（条件触发）**：让 Cleaner 像 Analyst 一样能与用户对话、被挑战、用 `route_to` 跳转。同时把 C-1 中 Cleaner 的 `strict xfail` XPASS 后改为正测试（契约自我演进机制兑现）。

**Phase 2 必须在 Phase 1 通过后才能开始**。

---

## §1 角色边界

继承 `analyst-routing-execution-protocol.md` 全部规则。

### 1.1 commit prefix

| 系列 | prefix | 含义 |
|------|--------|------|
| SK-N | `[SK-N]` | Smoke（冒烟工具准备、冒烟分析、冒烟修补） |
| CL-N | `[CL-N]` | Cleaner 对话化 |

### 1.2 本 brief 特定红线

| # | 红线 | 理由 |
|---|------|------|
| L1 | **Phase 1 冒烟必须用真 LLM，禁止 mock** | mock 已在 C-2 验证；本阶段验真模型 |
| L2 | **Phase 2 不许在 Phase 1 通过前开始** | 跳过冒烟门 = 等于没做 |
| L3 | **CL-N 必须镜像 Analyst 模式**（参照 A-1/A-2/A-3） | 减少认知成本；避免发明新模式 |
| L4 | **不许抽 Analyst/Cleaner 公共代码** | 公共抽取是后续 brief；本 brief 单职责 |
| L5 | **不许动 Reporter** | 仍在 B-3 schema-only 状态，不在本 brief 范围 |
| L6 | **不许动 `submit_analysis` / `submit_first_pass` 工具语义** | 若冒烟暴露歧义 → SK-FIX 修 prompt 不动工具 |

---

## §2 Phase 1：真 LLM 冒烟

### 2.1 任务 SK-1：准备冒烟工具

**改动范围**：新建 `scripts/smoke/analyst_two_phase_smoke.py`

**交付物**：单一脚本，参数化运行：

```bash
.venv/bin/python scripts/smoke/analyst_two_phase_smoke.py \
  --data tests/fixtures/<small_dataset>.csv \
  --query "<冒烟剧本的分析问题>" \
  --dump-dir ./smoke_runs/<timestamp>/
```

脚本职责：
1. 起 Orchestrator + 真实 LLM 客户端
2. 跑 Scout → Cleaner → Analyst 全流程
3. 在 Analyst 阶段按**冒烟剧本**（见 §2.2）逐条注入用户输入
4. 每轮 LLM 调用 dump 到 `--dump-dir`
5. 跑完后输出**自动检查清单**（见 §2.3）的初步结果，但**不替代人工核验**

**禁止**：脚本内 mock LLM；脚本内吞异常（沿铁律 7）；脚本写死敏感凭据。

**验收**：
- 单测 `tests/test_product/test_smoke_kit_structure.py`：仅断言脚本可 import、参数解析正确、不验证真 LLM 行为
- `pytest -q --tb=no | tail -3` 全绿

---

### 2.2 冒烟剧本（SK-2 执行）

**触发**：SK-1 commit 后。**由用户或实施方运行真 LLM**（视环境与配额）。

**剧本步骤**（5 步，覆盖关键 LLM 行为）：

| # | 用户输入 | 期望 LLM 行为 | 验证字段 |
|---|---------|--------------|---------|
| 0 | (无，自动进入 Analyst) | 阶段 1 自动跑首波，调 `submit_first_pass`（≤10 轮内） | dump 中 `tool_calls` 含 `submit_first_pass` |
| 1 | （阶段 1 完成，前端展示概括）查看输出 | 输出含 `[发现]/[统计依据]/[局限或解读]` 三标记 | emit 的 `USER_INPUT_REQUESTED` payload 的 `message` |
| 2 | "换 t 检验试试" | 调 `run_statistical_test(test_type="ttest", ...)` | dump 中 tool_call |
| 3 | "我觉得方向不对，应该看渠道维度" | 调 `update_analysis_scope` 或 `route_to(stage="scout")` | dump 中 tool_call |
| 4 | "够了，去写报告吧" | 调 `route_to(stage="reporter")` | dump 中 tool_call + `_handle_analyst_reply` 返回 `("switch", "reporter", ...)` |
| 5 | （阶段 2 中间）"再等等" | **不调** `route_to(stage=...)`；纯文本回应 | dump 中无 `route_to` tool_call 或 `route_to` args 不传 stage |

### 2.3 通过标准（4 条全过 = Phase 1 通过）

1. **三要素稳定**：步骤 1 的 LLM 输出 100% 含三标记（若浮动 → SK-FIX-1）
2. **工具映射正确**：步骤 2/3/4 LLM 调对工具（若调错 → SK-FIX-2）
3. **挽留无代码**：步骤 5 LLM **不调** `route_to(stage=...)`（若误调 → SK-FIX-3）
4. **首波收敛合理**：步骤 0 在 ≤10 轮内调 `submit_first_pass`（若 >10 轮或无调用 → SK-FIX-4）

### 2.4 任务 SK-2：冒烟分析 + 落盘报告

**改动范围**：新建 `docs/plans/SMOKE-REPORT-2026-06-08.md`

**报告结构**（必填）：

```markdown
# 真 LLM 冒烟报告（2026-06-08）

## 运行环境
- 模型：<model_name>
- 数据集：<file_path>
- dump 目录：<path>
- 运行时长：<seconds>

## 5 步剧本逐条结果
| # | 期望 | 实际 | dump 引用 | 通过/不通过 |

## 通过标准 4 条逐条评估
1. 三要素稳定：<原文片段截图/引用>
2. 工具映射正确：<tool_call 名 + args>
3. 挽留无代码：<dump 第 N 轮 tool_calls 为空 / route_to 不传 stage>
4. 首波收敛轮数：<N 轮，是否 ≤10>

## 总结
- 全部通过 → 进入 Phase 2
- 部分不通过 → 触发 SK-FIX-X，列出修补任务
```

**验收**：报告含上述 4 部分；每条结论引用至少 1 个 dump 文件路径或行号。

### 2.5 SK-FIX 修补分支（条件触发）

若 Phase 1 4 条标准任一不通过：

| 失败条 | 修补任务 | 改动范围 |
|--------|---------|---------|
| 三要素不稳定 | **SK-FIX-1** | `reply_handlers._rewrite_as_written_summary` 的 system prompt 加强约束（如 few-shot 示例、严格格式要求） |
| 工具映射错 | **SK-FIX-2** | `hagoku/agents/analyst/prompt.md` 工具映射表加强（更明确的"用户说 X → 调工具 Y"） |
| 误调 route_to 留 | **SK-FIX-3** | `prompt.md` 强化"用户说挽留时不调 `route_to(stage=...)`"约束 |
| 首波超轮 | **SK-FIX-4** | `submit_first_pass` 工具描述加强（让 LLM 更主动调用）；max_rounds 不动 |

**禁止**：动 `submit_analysis` / `submit_first_pass` 工具签名（L6）；改 `_run_analyst_first_pass` 循环逻辑。

**每个 SK-FIX 完成后必须重跑冒烟剧本**（重新执行 §2.2），并在 SMOKE-REPORT 追加"修补后复跑"章节。

---

## §3 Phase 2：Cleaner 对话化（条件触发）

**触发条件**：Phase 1 SMOKE-REPORT §「总结」明确写「全部通过」。否则 Phase 2 不允许开始。

### 3.1 任务清单（镜像 Analyst A-1/A-2/A-3/A-4/C-1）

| 任务 | 镜像对应 | 主题 |
|------|---------|------|
| **CL-1** | A-1 | Cleaner 新增 `run_step` + `_compose_system_messages` |
| **CL-2** | A-2 | `_handle_cleaner_reply` 首次自动评估改为对话循环；保留首次评估作为首波展示 |
| **CL-3** | A-3 + B-1 | Cleaner `route_to` 链路修复；让 C-1 中 `TestCleanerControlChannelBlindSpot` 两个 strict xfail XPASS |
| **CL-4** | A-4 | `hagoku/agents/cleaner/prompt.md` 重写为"清洗伙伴"角色 |
| **CL-5** | C-1 | 移除 Cleaner xfail，改为正向链路测试；新增 Cleaner 端到端冒烟单测（mock） |

### 3.2 与 Analyst 的关键差异

| 维度 | Analyst | Cleaner |
|------|---------|---------|
| 首波产出形态 | 书面概括（3-5 段三要素叙述） | 结构化清洗评估（已有 `cleaning_assessment` dict） — **不需要书面化重写** |
| 阶段 2 工具集 | `run_statistical_test` / `update_analysis_scope` / `route_to` 等 | `propose_cleaning_rule`（**新增**）/ `compare_before_after`（**新增**）/ `route_to` / `ask_user` |
| LLM 主动建议 | "够了去写报告" → `route_to(reporter)` | "清洗方案 OK 继续" → `route_to(analyst)` |

**CL-2 关键**：保留现有 `Cleaner.assess` 作为首波产出，CL-2 在评估完成后**不立即切 analyst**，改为打开对话窗口。`_analyst_first_pass_done` 的 Cleaner 版本 = `_cleaner_dialog_open`。

**新增工具**（CL-1 内顺手做）：
- `propose_cleaning_rule(column, rule, reason)`：LLM 提议清洗规则
- `compare_before_after(rule, sample_size=10)`：跑 before/after 对比给用户看

工具注册到 `agent_tool_defs.py`，仅 `agents=["cleaner"]`，对应 dispatch handler 实现。

### 3.3 验收（每任务）

继承 Analyst brief §4 验收清单（commit prefix / shell 实测证据 / 数字当次实测 / 否定双工具 / diff 范围 / 自检三组 pytest）。

**额外特定项**：
- **CL-3 必须使 `TestCleanerControlChannelBlindSpot` 中 2 个 strict xfail XPASS**（被 pytest 标记为 FAIL）→ CL-5 把它们改为正测试
- **CL-2 commit body 必须验证**：进入 Cleaner 不再"评估完直接切 analyst"，而是 `_pause` 给前端展示并等用户输入
- **CL-5 端到端测试**必须覆盖 Cleaner 阶段 2 至少 3 种用户意图（接受 / 挑战 / `route_to`）

### 3.4 Phase 2 完成 = C-1 盲点缩减

完成后 `tests/test_product/test_control_channel_link_integrity.py` 状态变化：

- 删除 `TestCleanerControlChannelBlindSpot`（2 个 xfail）
- 新增 `TestCleanerControlChannelLinks`（≥3 个正测试）
- Reporter 的 `TestReporterControlChannelBlindSpot` 保留（1 个 xfail，超出本 brief 范围）

**期望全量测试结果**：从 `523 passed + 3 strict xfailed` → `≥523+N passed + 1 strict xfailed`（N = CL-5 新增数，至少 5）。

---

## §4 任务依赖与建议顺序

```
SK-1 (冒烟工具) ─→ [冒烟运行] ─→ SK-2 (冒烟报告)
                                       │
                       ┌───────────────┴───────────────┐
                       │ 全部通过                       │ 部分失败
                       ↓                              ↓
                CL-1 → CL-2 → CL-3 → CL-4 → CL-5     SK-FIX-N → 复跑剧本
                                                          ↓
                                                       SK-2 追加章节
                                                          ↓
                                                       (回到决策点)
```

**建议节奏**：
- Day 1：SK-1（半天）+ 冒烟运行 + SK-2（半天）
- Day 2-3：CL-1 ~ CL-3
- Day 4：CL-4 + CL-5

---

## §5 何时回到架构审核方

继承 `analyst-routing-execution-protocol.md` §B 全部 9 种。新增本 brief 特定：

10. **冒烟暴露非 §2.5 表格列出的失败模式**（如 LLM 输出乱码、tool_call args 结构错误、`run_step` 返回值异常）→ 不属于 prompt 工程范围，应停下回报
11. **CL-2 调研发现 Cleaner 的 `assess` 与对话循环架构冲突**（如 `assess` 内部已有 LLM 调用，难以无缝接入 `run_step` 模式）→ 应停下回报，避免强行迁移
12. **新增工具 `propose_cleaning_rule` / `compare_before_after` 与现有 Cleaner 业务逻辑不兼容**（如清洗规则数据结构需要重新设计）→ 应停下回报

---

## §6 与现有契约的衔接

- 本 brief 是 `2026-06-07-analyst-and-routing-brief.md` §8.5 三个观察点中**第 1 条（B-2 xfail 监控）和第 2 条（真 LLM 冒烟）**的兑现
- §8.5 第 3 条（`submit_analysis` vs `submit_first_pass` 语义分化）由 SK-FIX-2/SK-FIX-4 兜底
- Reporter 互动化（原 §8.5 未列）超出本 brief，留待后续 brief

---

**Brief 出具时间**：2026-06-08
**Brief 出具方**：Cascade（架构审核方）
**执行模式**：一次性多 commit，Phase 1 完成是 Phase 2 阻塞门
