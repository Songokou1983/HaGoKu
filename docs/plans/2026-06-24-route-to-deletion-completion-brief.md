# Route_to 删除后 4 动作完成 brief（2026-06-24）

> **文档定位**：架构审核方（Claude Opus 4）出具，交付开发 AI（代码-AI）执行。
>
> **审计依据**：`docs/audits/2026-06-24-post-route-to-deletion-audit.md`（7 finding，4 动作方案，dump 基线已留）
>
> **前置依赖**：30 个 commit 已落地（Session 重构 / route_to 删除 / UI 拍平 / 4 个功能断裂 fix）。**本 brief 不重做这些 commit，只完成收尾的 4 个动作。**

---

## §0 任务定位

route_to 删除链（7c131de 起）已完成核心清理，但最近 4 个 fix commit 留下**未对齐 PROJECT.md 的半成品**。本 brief 收尾 4 个动作，让项目回到「代码不做 if-elif 阶段判断」「单数据源 Session」「prompt 三问」三条核心原则的完全对齐。

4 个动作按依赖排序：

| # | 动作 | 改动量 | 风险 |
|---|---|---|---|
| 1 | prompt.md 清理 | -6 行 | 低（prompt 改动按铁律 10 必须 dump 对比） |
| 2 | scout 阶段 hint 注入（修 bug #1） | +1 行 | 低 |
| 3 | session 推断当前关注点（彻底方案） | +18 行 / -4 行 | 中 |
| 4 | 删历史包袱（_stage + 19d085a + focusAreas） | -50 行 | 高（删比加风险大） |

---

## §1 角色边界与红线

### 1.1 你的角色

你是**开发 AI（代码-AI）**——动手改代码的人。**审计 AI** 是 Claude Opus 4（另一个 AI 实例），它不动手，只审你的 commit。

**对接流程**：
1. 你按 4 动作顺序改代码（每动作一个独立 commit）
2. 每个 commit 后跑端到端测试 + dump 验证（按 §5 验收清单）
3. commit body 贴 dump 关键行 + pytest 结果 + 反向断言
4. 提交后审计 AI 按 §5 清单审核 → 通过 / 退回

### 1.2 commit prefix

| 动作 | prefix | 示例 |
|---|---|---|
| 1 | `[R-1]` | `[R-1] prompt.md 清理——4 阶段行为指导改为动态注入` |
| 2 | `[R-2]` | `[R-2] scout 阶段 hint 注入——修 infer_field_semantics context 缺 _current_stage` |
| 3 | `[R-3]` | `[R-3] session.infer_current_focus()——让 Session 成为阶段真相源` |
| 4 | `[R-4]` | `[R-4] 删 _stage 字段 + 19d085a 被动观测 + focusAreas 孤儿` |

### 1.3 红线（CLAUDE.md 铁律 + PROJECT.md 不可写清单）

| # | 红线 | 违反后果 |
|---|---|---|
| L1 | **改代码前必须有 dump 实证**（按 CLAUDE.md 调试铁流程） | 退回 |
| L2 | **prompt 改动必须 dump 对比**（铁律 10） | 退回 |
| L3 | **禁止加诊断日志代替读 dump**（CLAUDE.md 铁律 -4） | 退回 |
| L4 | **禁止在 prompt 加「禁止/不要/不准」**（刹车 G） | 退回 |
| L5 | **禁止 setdefault/.get 带默认值**（刹车 C） | 退回 |
| L6 | **禁止 except 兜底返回 None**（铁律 7） | 退回 |
| L7 | **禁止 prompt 里出现工具名**（PROJECT.md 不可写清单） | 退回 |
| L8 | **禁止再加 commit 改 agent.py:543-558**（已改 5 次，LESSONS_DRAFT.md 红色信号） | 退回 |
| L9 | **禁止 let 代码根据 _stage 决定工具可见性**（违反「工具全量可见」原则） | 退回 |
| L10 | **commit message 必须写具体改动**（不是 "update/fix"） | 退回 |

---

## §2 动作 1：[R-1] prompt.md 清理

### 2.1 改动

`hagoku/agents/prompt.md`

```diff
- 你是数据分析师。分析按四个阶段推进。
- 
- 【理解字段】你收到数据集后，逐列给出中文名、业务含义、是否参与分析。用 `set_columns` 写入，然后把完整的字段理解表展示给用户确认。
- 【评估清洗】检查参与分析的列是否需要清洗（缺失、异常、分布），给出建议。用 `submit_assessment` 提交评估表让用户确认。
- 【统计分析】根据分析目标和数据特征选择方法，跑检验，产出有统计支撑的发现。用 `submit_findings` 提交。
- 【撰写报告】将确认的分析发现整理为正式报告。
- 
- 每次回复都要让用户知道：你做了什么、结果是什么、接下来可以做什么。
- 不要只描述过程——要展示结果。不确定就问用户。
- 用户说的就是事实，冲突时以用户最新说的为准。
- 你被反复调用，每次都能看到完整对话历史和工具结果。不需要重复确认已有结果。
+ 你是数据分析师。当前关注点会在每轮对话顶部动态注入。
```

### 2.2 验收

- [ ] dump 改前基线已 cat 出来（4 文件名贴 commit body）
- [ ] dump 改后基线已 cat 出来
- [ ] dump 改前 vs 改后 system content 对比（关键差异 1-3 行）
- [ ] `grep "【理解字段】\|【评估清洗】\|【统计分析】\|【撰写报告】" hagoku/agents/prompt.md` 应零命中
- [ ] pytest -q --tb=no 全绿
- [ ] commit body 含未越界声明（本 commit 未改超出本动作范围的文件）

---

## §3 动作 2：[R-2] scout 阶段 hint 注入（修 bug #1）

### 3.1 改动

`hagoku/agents/agent.py:240-247`

```diff
  context = {
      "_session": session,
      "query": query,
+     "_current_stage": "scout",   # 修 bug #1: hint 注入在 scout 阶段失效
      "column_semantics": [],
      "_column_info": {c: str(df[c].dtype) for c in df.columns},
      "_pending_command_text": (actx.get("_pending_command_text") or "").strip() if actx else "",
  }
```

### 3.2 验收

- [ ] 动作 1 已落地（否则 4 阶段文字 + hint 同时存在相互干扰）
- [ ] dump 改前 vs 改后：system content 顶部**必须出现** `【当前关注点：理解字段】`
- [ ] dump 改后 LLM 响应有 tool_calls（非空）——证明 hint 注入生效后 LLM 调工具
- [ ] pytest -q --tb=no 全绿

---

## §4 动作 3：[R-3] session 推断当前关注点

### 4.1 改动 A：`hagoku/context/session.py` 新增方法

```python
KEY_TOOL_TO_FOCUS = [
    ("submit_findings", "撰写报告"),
    ("submit_assessment", "统计分析"),
    ("set_columns", "评估清洗"),
]

def infer_current_focus(self) -> str:
    """从 session.messages 推断当前关注点——只读，不修改 messages。

    推断逻辑：扫描 assistant 消息的 tool_calls，找最近的关键工具调用。
    - 没调过任何关键工具 → "理解字段"（首次进入）
    - 调过 set_columns → "评估清洗"
    - 调过 submit_assessment → "统计分析"
    - 调过 submit_findings → "撰写报告"
    """
    last_focus = "理解字段"  # 默认首次进入
    for msg in self.messages:
        if msg.get("role") != "assistant":
            continue
        for tc in (msg.get("tool_calls") or []):
            name = tc.get("function", {}).get("name", "")
            for key, focus in KEY_TOOL_TO_FOCUS:
                if name == key:
                    last_focus = focus
    return last_focus
```

### 4.2 改动 B：`hagoku/agents/agent.py:438-442` 替换

```diff
  agent_extra = self.prompt
- phase_hint = context.get("_current_stage", "")
- if phase_hint:
-     stage_names = {"scout": "理解字段", "cleaner": "评估清洗", "analyst": "统计分析", "reporter": "撰写报告"}
-     agent_extra = f"【当前关注点：{stage_names.get(phase_hint, phase_hint)}】\n\n" + agent_extra
+ phase_hint = context["_session"].infer_current_focus()
+ agent_extra = f"【当前关注点：{phase_hint}】\n\n" + agent_extra
```

### 4.3 验收

- [ ] 动作 1+2 稳定（dump 验证 LLM 调工具成功）
- [ ] dump 改前 vs 改后：4 阶段切换时 hint 跟着变
  - 模拟 LLM 调 set_columns → 下轮 hint = "评估清洗"
  - 模拟 LLM 调 submit_assessment → 下轮 hint = "统计分析"
  - 模拟 LLM 调 submit_findings → 下轮 hint = "撰写报告"
- [ ] pytest -q --tb=no 全绿
- [ ] 反向断言：`git grep -n "_current_stage\|stage_names" hagoku/` 应零命中
- [ ] **OpenAI tool_calls 结构确认**：assistant.message.tool_calls 是 list of `{id, type, function: {name, arguments}}`——如果 dump 显示结构不同，需调整推断逻辑

---

## §5 动作 4：[R-4] 删历史包袱

### 5.1 改动清单（按文件分批，每批一个 commit）

**R-4a：删 `_stage` 字段定义和读写**

| 文件 | 行 | 改 |
|---|---|---|
| `hagoku/manager/orchestrator.py` | 125, 156, 351 | 删 `self._stage: str = ""` |
| 同上 | 195 | 删 `"stage": self._stage,` |
| 同上 | 231 | 删 `orch._stage = state.get("stage", "")` |
| 同上 | 257 | 删 logger.info 里的 `orch._stage` |
| 同上 | 414 | 删 `self._stage = "scout"` |
| `hagoku/api/ws_handler.py` | 172, 282, 292, 399 | 删 stage 字段相关（4 处） |

**R-4b：删 19d085a 被动观测 + 死写入**

| 文件 | 行 | 改 |
|---|---|---|
| `hagoku/manager/llm_dispatch/reply_handlers.py` | 27-33 | 删 19d085a 被动观测块（9 行） |
| 同上 | 30, 33 | 删 `_cleaner_assessment` / `_analyst_findings` 写入 |
| 同上 | 70 | 删 `ctx["_current_stage"] = self._stage` |
| `hagoku/agents/agent.py` | 591 | 删 `if findings is not None or assessment is not None: break` |

**R-4c：删前端 focusAreas 孤儿**

| 文件 | 改 |
|---|---|
| `hagoku_web/src/constants/focusAreas.ts` | 删整个文件 |

### 5.2 验收（R-4a/b/c 每个 commit 都要做）

- [ ] dump 改前 vs 改后：hint 注入仍正确（动作 3 的推断逻辑不受影响）
- [ ] `git grep -n "_stage" hagoku/` 应只在 `db.py` (历史 schema)、`business.py` (分析语义)、`storage/artifact.py` (lineage) 命中
- [ ] `git grep -n "_current_stage" hagoku/` 应零命中
- [ ] `git grep -n "focusAreas" hagoku_web/` 应零命中
- [ ] pytest -q --tb=no 全绿
- [ ] npm run build 成功（仅 R-4c 需要）

---

## §6 通用验收清单（每个 commit 必须填）

```
[ ] dump 改前基线已 cat 出来（4 文件名）
[ ] dump 改后基线已 cat 出来（4 文件名）
[ ] dump 改前 vs 改后对比（关键差异 1-3 行）
[ ] commit message 描述具体改动（不是 "update/fix"）
[ ] commit 单步可独立回滚（git revert HEAD 可工作）
[ ] pytest -q --tb=no 全绿
[ ] 反向断言（grep 验证已删项零命中）
[ ] 未越界声明（本 commit 未改超出本动作范围的文件）
```

---

## §7 触发条件（碰到立即停手回报审计 AI）

按 CLAUDE.md §6 触发条件 + 本 brief 特定触发：

1. dump 改后 system content 结构与预期不符（不是工具结果问题，是代码路径问题）
2. pytest 红——`git reset --soft HEAD~1` 撤回，回报根因
3. OpenAI tool_calls 结构与动作 3 §4.3 假设不符
4. 调研发现 dump 4（fixture 模拟 hint）实际不是 fixture 而是真实对话
5. 任何红线（L1-L10）被触发的边缘情况

---

## §8 执行节奏建议

按 LESSONS_DRAFT.md 第 49 行「真根因修复会照亮周围死代码」+ REFACTORING_REPORT.md「一步一 commit」：

| commit | 包含动作 | 验证时长（估计） |
|---|---|---|
| `[R-1]` | 动作 1（prompt.md） | 10 分钟（dump 对比） |
| `[R-2]` | 动作 2（agent.py +1 行） | 5 分钟（dump 验证 hint） |
| `[R-3]` | 动作 3（session + agent.py 替换） | 20 分钟（4 阶段切换 dump 验证） |
| `[R-4a]` | 动作 4a（删 _stage 字段） | 10 分钟 |
| `[R-4b]` | 动作 4b（删观测 + 死写入） | 10 分钟 |
| `[R-4c]` | 动作 4c（删 focusAreas） | 5 分钟（前端 build） |

**总 6 个 commit，估计 60 分钟**。每个 commit 必须等审计 AI 通过再做下一个。

---

## §9 dump 操作指引

```bash
# 触发端到端（任选一种）
HaGoKu run data.csv -q "你的测试 query"
# 或 Web UI 跑一次

# 读最新 dump
ls -lt ~/.hagoku/llm_dumps/ | head -10
cat ~/.hagoku/llm_dumps/001_agent_run_step_*.json  # 最近一个
cat ~/.hagoku/llm_dumps/002_agent_run_step_response_*.json
cat ~/.hagoku/llm_dumps/003_agent_run_step_r2_*.json  # 如果有
cat ~/.hagoku/llm_dumps/004_agent_run_step_r2_response_*.json  # 如果有
```

dump 基线（2026-06-24 15:25 真实 scout 阶段）：

```
~/.hagoku/llm_dumps/001_agent_run_step_20260624_07254967.json
~/.hagoku/llm_dumps/002_agent_run_step_response_20260624_07254967.json
~/.hagoku/llm_dumps/003_agent_run_step_r2_20260624_07254970.json
~/.hagoku/llm_dumps/004_agent_run_step_r2_response_20260624_07254970.json
```

---

**brief 出具时间**：2026-06-24
**预计完成**：2026-06-24（同日）
**审计 AI**：Claude Opus 4（不动手，按 §6 验收清单审每个 commit）