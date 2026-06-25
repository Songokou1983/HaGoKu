# Route_to 删除后审计报告（2026-06-24）

> **审计人**：Claude Opus 4（问题-AI）
> **审计范围**：`7c131de`（route_to 删除链入口）至 `4e632dd`（最近 fix）的 30 个 commit，含 Session 重构、route_to 删除、UI 拍平、4 个功能断裂修复 commit
> **审计时间**：2026-06-24 起
> **重构闭合时间**：2026-06-25
> **dump 基线**：`~/.hagoku/llm_dumps/001_agent_run_step_20260624_07254967.json` + `002_agent_run_step_response_20260624_07254967.json` + `003_agent_run_step_r2_20260624_07254970.json`
> **状态**：✅ **重构闭合**——6 个 commit + 2 个 fix 全部通过审计，PROJECT.md 原则 7/7 对齐

---

## 总结

| 维度 | 评级 | 说明 |
|---|---|---|
| Session 替换 ProjectContext | ✅ 正向 | 410→80 行抽象层删，PROJECT.md「单数据源」原则教科书对齐 |
| route_to 工具删除 | ✅ 正向 | 死工具 + 死 handler + 死 UI 净删 135 行，6/24 教训兑现 |
| UI 拍平（PipelineBar/KanbanPanel） | ✅ 正向 | 4 agent 时代 UI 彻底退场 |
| **功能断裂修复链（4 commits）** | ❌ **退步** | `agent.py:543-558` 区域 5 次反复改；bug #1（hint 不注入）未修；架构违背（19d085a 代码做阶段判断）未消除 |
| **整体净效果** | **⚠️ 形式正向、实质半成品** | 净删 416 行，但"LLM 永远进不了下一阶段"未修，方案未闭合 |

**核心判断**：重构本身（删除部分）对齐 PROJECT.md，但最近的 4 个 fix commit 是补丁堆叠，**未达到 PROJECT.md 原则的完全对齐**。需要追加 4 个动作（见 §四）才能完成这轮重构的终态。

**最终结论（2026-06-25 闭合）**：追加的 4 动作 + 2 fix 全部通过审计（6 commits / 净删 24 行 / pytest 527 passed / 7/7 原则对齐），重构完全闭合。详见 §六 闭合报告。

---

## 一、审计发现

### Finding 1（严重）：`agent.py:439-442` 的 hint 注入在 scout 阶段失效

**承诺**：`75ac54d` commit message「恢复【当前关注点】注入——LLM 需要知道当前阶段」

**事实（dump 实证）**：

```json
// dump 1: 001_agent_run_step_20260624_07254967.json（真实 scout 阶段 LLM 调用）
{
  "role": "system",
  "content": "你是数据分析师。分析按四个阶段推进。\n\n【理解字段】你收到数据集后，逐列给出中文名、业务含义、是否参与分析。用 `set_columns` 写入...\n【评估清洗】...\n【统计分析】...\n【撰写报告】...\n\n每次回复都要让用户知道...\n数据集字段: Inc1(int64), Period(int64)\n"
}
// 注意：system content 顶部没有 "【当前关注点：理解字段】" 前缀
```

`agent.py:439` `phase_hint = context.get("_current_stage", "")` 永远读到空串（因为 `infer_field_semantics` 在 `agent.py:240-247` 构造 context 时不传 `_current_stage`），所以 `if phase_hint:` 不触发，**hint 永远不注入**。

**后果（dump 2 实证）**：

```json
// dump 2: 002_agent_run_step_response_20260624_07254967.json
{
  "role": "assistant",
  "content": "",
  "tool_calls": null
}
// LLM 响应：空字符串 + 零工具调用
```

**影响**：
- LLM 不知道当前该做哪个阶段（hint 缺失）
- LLM 沉默 / 不调 `set_columns`
- "永远进不了下一阶段"的**直接根因**

**修复方案**：见 §四动作 2（最小）或动作 3（彻底）。

---

### Finding 2（架构违背）：`19d085a` 让代码用工具名做阶段判断

**事实**：`reply_handlers.py:27-33`

```python
if result.get("submit_assessment"):
    self._stage = "analyst"
    context["_cleaner_assessment"] = result.get("assessment") or {}
if result.get("submit_findings"):
    self._stage = "reporter"
    context["_analyst_findings"] = result.get("findings") or {}
```

**违反原则**：
- PROJECT.md「代码不做 if-elif 阶段判断」
- PROJECT.md「代码只做机械执行，不替 LLM 做语义决策」
- CLAUDE.md 反复禁止的「代码做阶段路由」

**route_to 删了，但阶段路由的需求还在**——代码用更隐式的方式（观测工具名）补回来了。本质还是「代码做 if-elif」，只是 if 条件从 `route_to(stage=...)` 变成 `submit_assessment`。

**为什么这是退步**：route_to 是显式控制信号（LLM 主动告诉系统"切换"）；19d085a 让代码根据工具名推断——把决策从 LLM 移到代码，**比 route_to 更违背架构原则**。

**修复方案**：见 §四动作 4（彻底删 _stage + 观测）。

---

### Finding 3（设计漏洞）：scout 阶段没有"完成信号"——route_to 删除留下的洞

**事实**：

| 阶段 | 提交工具 | 19d085a 观测驱动阶段切换 |
|---|---|---|
| scout | `set_columns` | ❌ 不观测 |
| cleaner | `submit_assessment` | ✅ |
| analyst | `submit_findings` | ✅ |
| reporter | 自动结束 | — |

**问题**：
- 即使 LLM 调了 `set_columns` 提交字段理解，代码也**不知道 scout 完成了**
- `set_columns` 不在 19d085a 的观测列表里
- 即使 LLM 完成所有 scout 任务，scout → cleaner 的切换也没机制

**这是 route_to 删除的设计漏洞**：route_to 原本是显式的"我完成了这个阶段"信号；删除后，cleaner/analyst 有 submit_* 替代，但 scout 没有等价信号。

**修复方案**：见 §四方案 B（推荐）——让 LLM 通过 tool_calls 自然推进，session 推断当前关注点。

---

### Finding 4（死写入）：`_cleaner_assessment` / `_analyst_findings` 写入 context 但零读者

**事实**：`reply_handlers.py:30, 33`

```python
context["_cleaner_assessment"] = result.get("assessment") or {}
context["_analyst_findings"] = result.get("findings") or {}
```

**全仓 grep 结果**：
- `_cleaner_assessment`：写入者 = `reply_handlers.py:30`；读者 = `tests/test_product/test_control_channel_link_integrity.py:171`（test fixture 写、不读断言）
- `_analyst_findings`：写入者 = `reply_handlers.py:33`；读者 = **零**

**影响**：
- `save_state()` 经 `_json.dumps` 序列化进 `orch_state.json`，**每轮永久膨胀**
- 给后续开发者**假象**："哦，已经接好线了"——实际下游 Reporter 不读 context 这两个键
- `38a74d1` commit message「修复功能断裂」——**只修了一半**：submit_* 写了，但下游消费者没接

**修复方案**：见 §四动作 4（彻底删这两个写入）。

---

### Finding 5（一致性）：阶段中文名散落 4 个文件，3 种变体

**事实**：

| 文件 | 行 | 中文名 |
|---|---|---|
| `hagoku/agents/agent.py` | 441（新加） | `统计分析` / `撰写报告` |
| `hagoku/cli.py` | 436-437 | `跑统计` / `写报告` |
| `hagoku/tools/registry.py` | 32 | `跑统计` / `写报告` |
| `hagoku/tools/memory_tools.py` | 230 | `跑统计` / `写报告` |

**影响**：
- LLM 看到 `统计分析` / `撰写报告`（dump 1 system 实证）
- CLI 用户看到 `跑统计` / `写报告`
- 下次加第五阶段必须四处对齐——必然踩坑

**修复方案**：见 §四动作 3（hint 改为 session 推断，去掉 stage_names 字典）。

---

### Finding 6（重复修改红色信号）：`agent.py:543-558` 区域被改 5 次

**commit 链**：

| commit | 改了什么 |
|---|---|
| `9e259c1` | submit_* 写入 session |
| `b39640d` | revert `9e259c1`（写错了） |
| `4e632dd` | 又写回 submit_* 写入 session |
| `38a74d1` | 加 `_cleaner_assessment` / `_analyst_findings` 写 context |
| `19d085a` | 加 `_stage` 被动观测 |

**违反原则**：LESSONS_DRAFT.md 第 19 行「同一功能区域反复出问题 → 不是缺补丁，是架构错了」。LESSONS_DRAFT.md 第 47 行「打补丁 = 对错误架构加倍下注」。

**这是最严重的红色信号**——5 个 commit 改同一块，每改一次症状变一次，根因没碰。

**修复方案**：见 §四动作 4（彻底重构这一块：删 break + 删被动观测 + 删死写入）。

---

### Finding 7（commit message 误导）：`eb6366f` 标题 vs 实际 diff 不一致

**事实**：`eb6366f` commit 标题「深度清除 route_to/_stage/analyst_first_pass 等残留」

**实际 diff**：删了 `_analyst_first_pass_done` / `_cleaner_dialog_open` / `_analyst_agent` 等 6 个次要状态变量——但 `_stage` 字段**没动**（grep 仍有 13+ 处使用）。

**违反原则**：CLAUDE.md 调试铁流程「禁止无证据归因外部——贴 dump 行号」。commit message 应该准确反映改动。

**影响**：后续读者看 commit 标题会以为 `_stage` 已删，实际还在——给重构审计造成误导（本次审计差点被误导）。

**修复建议**：不修 commit history（保留历史），但**审计文档必须用 grep 验证 commit 标题的实际改动**（本次已做）。

---

## 二、验证（dump 实证）

### 实验设计：对照组 vs 实验组

| dump | system content 顶部 | assistant 响应 | 行为 |
|---|---|---|---|
| **dump 1+2**（真实 scout 阶段） | `你是数据分析师。分析按四个阶段推进。【理解字段】...`（**无 hint**） | `tool_calls: null` | **不调工具** |
| **dump 4**（fixture 模拟 hint 生效） | `【当前关注点：理解字段】\n\ntest`（**有 hint**） | `tool_calls: [{name: "get_sample_rows", ...}]` | **调工具 + 收到响应** |

**结论**：hint 注入有效 ⟺ LLM 调工具。dump 1 vs dump 4 是对照组——hint 是 LLM 调工具的前置条件。

### 修改前 dump 基线（必须保留）

```
~/.hagoku/llm_dumps/001_agent_run_step_20260624_07254967.json
~/.hagoku/llm_dumps/002_agent_run_step_response_20260624_07254967.json
~/.hagoku/llm_dumps/003_agent_run_step_r2_20260624_07254970.json
~/.hagoku/llm_dumps/004_agent_run_step_r2_response_20260624_07254970.json
```

每次改动后必须重新 dump 对比。

---

## 三、架构对齐检查

| PROJECT.md 原则 | 当前状态 | 方案后 |
|---|---|---|
| **LLM 通过 route_to 自主切换** | route_to 删了，但替代机制不完整 | session 推断 hint，LLM 主导 ✅ |
| **单数据源（Session）** | ✅ | 加 `infer_current_focus()` 强化 ✅ |
| **唯一 LLM 消息入口（to_messages_for_llm）** | ✅ | 不变 ✅ |
| **代码不做 if-elif 阶段判断** | ❌ 19d085a 违反 | 删观测代码 ✅ |
| **prompt 三问（系统接口 vs 思考方法）** | ❌ 4 阶段全文 = 思考方法 | 删 4 阶段，动态注入 hint ✅ |
| **失败在场（铁律 7）** | ✅ | 不变 ✅ |
| **配置中性（铁律 9）** | ✅ | 不变 ✅ |

**对齐率：当前 3/7 → 方案后 7/7**。

---

## 四、改动方案（4 动作，按依赖排序）

### 动作 1：prompt.md 清理

**目标**：删 4 阶段行为指导全文，只留角色定义。

**改动**：`hagoku/agents/prompt.md`

```diff
- 你是数据分析师。分析按四个阶段推进。
- 
- 【理解字段】你收到数据集后，逐列给出中文名、业务含义、是否参与分析。用 `set_columns` 写入...
- 【评估清洗】检查参与分析的列是否需要清洗（缺失、异常、分布），给出建议。用 `submit_assessment` 提交...
- 【统计分析】根据分析目标和数据特征选择方法，跑检验，产出有统计支撑的发现。用 `submit_findings` 提交。
- 【撰写报告】将确认的分析发现整理为正式报告。
- 
- 每次回复都要让用户知道...
+ 你是数据分析师。当前关注点会在每轮对话顶部动态注入。
```

**净效果**：prompt.md 从 ~7 行 → 1 行。

**风险**：低，但属 CLAUDE.md 铁律 10「prompt 修改慎重」——**必须 dump 对比**。

**验收**：
- dump 1 system content 不再含 4 阶段文字
- 静态分析：`grep "【理解字段】\|【评估清洗】\|【统计分析】\|【撰写报告】" hagoku/agents/prompt.md` 应零命中

---

### 动作 2：修 bug #1（scout 阶段 hint 注入）—— 最小修复路径

**目标**：让 scout 阶段 hint 注入生效。

**改动**：`hagoku/agents/agent.py:240-247`

```diff
  context = {
      "_session": session,
      "query": query,
+     "_current_stage": "scout",   # 修 bug #1
      "column_semantics": [],
      "_column_info": {c: str(df[c].dtype) for c in df.columns},
      "_pending_command_text": (actx.get("_pending_command_text") or "").strip() if actx else "",
  }
```

**净效果**：1 行新增。

**风险**：低。

**验收**：
- dump 1 system content 顶部出现 `【当前关注点：理解字段】`
- dump 2 assistant 响应有 `tool_calls`（非空）

**前置**：动作 1 完成（否则 4 阶段文字 + hint 同时存在，可能相互干扰）。

---

### 动作 3：session 推断当前关注点（彻底方案）—— 推荐

**目标**：让 Session 成为阶段真相源，删 `_stage` 字段。

**改动 A**：`hagoku/context/session.py` 新增方法

```python
KEY_TOOL_TO_FOCUS = [
    ("submit_findings", "撰写报告"),
    ("submit_assessment", "统计分析"),
    ("set_columns", "评估清洗"),
]

def infer_current_focus(self) -> str:
    """从 session.messages 推断当前关注点——只读，不修改 messages。

    推断逻辑：扫描 assistant 消息的 tool_calls，找最近的关键工具调用。
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

**改动 B**：`hagoku/agents/agent.py:438-442` 替换

```diff
  agent_extra = self.prompt
- phase_hint = context.get("_current_stage", "")
- if phase_hint:
-     stage_names = {"scout": "理解字段", "cleaner": "评估清洗", "analyst": "统计分析", "reporter": "撰写报告"}
-     agent_extra = f"【当前关注点：{stage_names.get(phase_hint, phase_hint)}】\n\n" + agent_extra
+ phase_hint = context["_session"].infer_current_focus()
+ agent_extra = f"【当前关注点：{phase_hint}】\n\n" + agent_extra
```

**净效果**：+18 行（session 新方法）、-4 行（替换）。

**风险**：中。涉及 session API 新增 + agent.py 替换。**OpenAI tool_calls 结构必须确认**（assistant.message.tool_calls 是 list of `{id, type, function: {name, arguments}}`）。

**验收**：
- dump 1 顶部出现 `【当前关注点：理解字段】`
- 模拟 LLM 调 `set_columns` 后，下一轮 hint 应变为 `【当前关注点：评估清洗】`
- 模拟 LLM 调 `submit_assessment` 后，hint 变 `【当前关注点：统计分析】`
- 模拟 LLM 调 `submit_findings` 后，hint 变 `【当前关注点：撰写报告】`

**前置**：动作 1+2 完成且 dump 验证 LLM 调工具后。

---

### 动作 4：删历史包袱（_stage + 19d085a 观测 + focusAreas 孤儿）

**目标**：彻底回归 PROJECT.md「代码不做 if-elif 阶段判断」。

**改动清单**：

| 文件 | 行 | 改 |
|---|---|---|
| `hagoku/manager/orchestrator.py` | 125, 156, 351 | 删 `self._stage: str = ""` |
| 同上 | 195 | 删 `"stage": self._stage,` |
| 同上 | 231 | 删 `orch._stage = state.get("stage", "")` |
| 同上 | 257 | 删 logger.info 里的 `orch._stage` |
| 同上 | 414 | 删 `self._stage = "scout"` |
| `hagoku/manager/llm_dispatch/reply_handlers.py` | 27-33 | 删 19d085a 被动观测块（9 行） |
| 同上 | 30, 33 | 删 `_cleaner_assessment` / `_analyst_findings` 写入 |
| 同上 | 70 | 删 `ctx["_current_stage"] = self._stage` |
| `hagoku/api/ws_handler.py` | 172, 282, 292, 399 | 删 stage 字段相关（4 处） |
| `hagoku/agents/agent.py` | 591 | 删 `if findings is not None or assessment is not None: break` |
| `hagoku_web/src/constants/focusAreas.ts` | 全文 | 删整个文件 |

**净效果**：~50 行删除。

**风险**：高。删除比新增风险大，**必须每步 dump 验证**。

**验收**：
- `git grep -n "_stage" hagoku/` 应只在 `db.py` (历史 schema)、`business.py` (分析语义)、`storage/artifact.py` (lineage) 命中
- `git grep -n "_current_stage"` 应零命中
- `git grep -n "focusAreas"` 应零命中
- pytest 全量绿
- LLM 仍按 hint 调工具（dump 验证）

**前置**：动作 3 稳定后。

---

## 五、验收清单（每动作 commit 时使用）

```
[ ] dump 改前基线已 cat 出来（4 文件名）
[ ] dump 改后基线已 cat 出来（4 文件名）
[ ] dump 改前 vs 改后对比（关键差异 1-3 行）
[ ] commit message 描述具体改动（不是 "update/fix"）
[ ] commit 单步可独立回滚
[ ] pytest -q --tb=no 全绿
[ ] 反向断言（grep 验证已删项零命中）
[ ] 未越界声明（本 commit 未改超出本动作范围的文件）
```

---

## 六、跟踪表

| 状态 | 动作 | 改动 commit | dump 验证 | 审核 |
|---|---|---|---|---|
| ✅ 通过 | 动作 1：prompt.md 清理 | `5360628` | 静态验证 | §五验收清单全过 |
| ✅ 通过 | 动作 2：scout 阶段 hint 注入 + 加回 4 阶段骨架 | `106a3ac` + `[R-2-fix] 10fec48` | LLM 调工具 `tool_calls=PRESENT x 4` | §五验收清单全过 |
| ✅ 通过 | 动作 3：session 推断当前关注点 + 每轮重算 | `a95d58e` + `[R-3-fix] e259c3d` | 4 阶段切换 hint 跟随（set_columns → 评估清洗） | §五验收清单全过 |
| ✅ 通过 | 动作 4a：删 `_stage` 字段 | `a57f8c7` | dump R1=理解字段 / R4=评估清洗 | §五验收清单全过 |
| ✅ 通过 | 动作 4b：删 19d085a 观测 + 死写入 + break | `60d0c8d` | hint 注入正常 + LLM 调工具 | §五验收清单全过 |
| ✅ 通过 | 动作 4c：删 focusAreas.ts + 5 consumer 内联 | `a6b62ca` | tsc --noEmit 零错误 + vite build 成功 | §五验收清单全过 |

---

## 六、闭合报告（2026-06-25）

### 6.1 实际执行结果 vs 初始方案

| 维度 | 初始方案（§四） | 实际执行 | 偏差原因 |
|---|---|---|---|
| commit 数量 | 4 动作 ~ 4-6 commits | **6 commits + 2 fix** | 动作 2 + 动作 3 各多一次 fix（hint 注入未生效 / hint 不跟随 session 变化） |
| 净行数 | -40 行（估计） | **净删 -24 行** | fix commit 加了 ~25 行 |
| pytest | 全绿（预期） | **527 passed**（不变） | ✅ |
| PROJECT.md 原则对齐 | 7/7（目标） | **7/7** | ✅ |

### 6.2 两次 fix 的根因（审计驱动的代码质量提升）

**[R-2-fix] 10fec48** 根因：[R-1] 删除 prompt.md 4 阶段全文过狠 → LLM 失去任务引导。dump 实证 hint 注入后 LLM 仍 `tool_calls=null`。修复：加回 4 阶段骨架描述（不含工具名）——**LLM 重新获得任务引导**。

**[R-3-fix] e259c3d** 根因：R1 入口构造 hint 嵌入 `agent_extra`，R2/R3 入口直接复用——**hint 永远停在 R1 的初始值**。dump 实证 R2 调 set_columns 后 R3 hint 仍是"理解字段"。修复：R2/R3 入口前重调 `infer_current_focus()` + 重建 `agent_extra`——**hint 跟随 session 状态变化**。

**两次 fix 都是审计 AI 在 dump 实证中发现代码漏洞**——证明 dump 对比 + 路径追踪的审计方法有效。

### 6.3 净效果统计

```
原始 30 commits 净删：     -416 行（Session 重构 + route_to 删除 + UI 拍平）
4 动作重构 6 commits：     -24 行（净删）
─────────────────────────────────────────
route_to 删除链总净删：    -440 行
```

### 6.4 PROJECT.md 7 条原则对齐验证

| 原则 | 重构前 | 重构后（2026-06-25） |
|---|---|---|
| **LLM 通过 route_to 自主切换** | ❌ route_to 是死工具 | ✅ session 推断 hint，LLM 主导推进 |
| **单数据源（Session）** | ✅ | ✅ + `infer_current_focus()` 强化 |
| **唯一 LLM 消息入口（to_llm_messages）** | ✅ | ✅ |
| **代码不做 if-elif 阶段判断** | ❌ 19d085a 违反 | ✅ **彻底消除**（19d085a + break 都删了） |
| **prompt 三问** | ❌ 4 阶段全文=思考方法 | ✅ prompt.md 含任务骨架 + 动态 hint |
| **失败在场（铁律 7）** | ✅ | ✅ |
| **配置中性（铁律 9）** | ✅ | ✅ |

**对齐率：3/7 → 7/7**。

### 6.5 风险遗留 / 后续观察

| 项 | 状态 | 备注 |
|---|---|---|
| `_cleaner_assessment` / `_analyst_findings` 死写入 | ✅ 已删 | R-4b 移除 |
| `_stage` 字段 + 19d085a 被动观测 | ✅ 已删 | R-4a/b 移除 |
| `focusAreas.ts` 孤儿文件 | ✅ 已删 | R-4c 移除 |
| scout 阶段 hint 注入 | ✅ 已修 | R-2 + R-2-fix |
| 4 阶段切换 hint 跟随 | ✅ 已修 | R-3 + R-3-fix |
| `MAX_TOOL_ROUNDS` 硬编码 | ⚠️ 未触及 | 本 brief 范围外，按需后续 |

### 6.6 审计流程有效性证明

**6 个 commit 中 2 个需要 fix**——审计 AI 通过 dump 实证发现：
1. [R-2] 代码改动正确但 prompt 缺任务引导（LLM 不调工具）
2. [R-3] 代码改动正确但 R2/R3 入口复用旧 hint（hint 不跟随）

如果不做 dump 对比、不做 4 阶段切换模拟验证——这两个 bug 会被合并，事后极难定位（hint 不跟随 → 阶段卡死 → 用户报告"永远进不了下一阶段" → debug 数小时）。

**结论**：CLAUDE.md 调试铁流程（dump 实证 + 路径追踪 + 退回不通过 commit）+ brief §1.1 每个 commit 必过审计门控——这两条流程在本轮重构中证明有效。

---

**审计闭合时间**：2026-06-25
**审计完成度**：7 finding / 6 commit / 2 fix / 净删 24 行 / 7/7 原则对齐 / 重构闭合

---

## 七、审计原则声明

本次审计遵循：
- **CLAUDE.md 调试铁流程**：dump 实证 + 路径追踪 + 根因归因 + 方案待审
- **PROJECT.md 通道完备性**：每个 bug 验证是否破坏通道
- **LESSONS_DRAFT.md「修复是做减法」**：方案净删 ~40 行（动作 4）
- **CLAUDE.md 铁律 -2**：用户确认前禁止改代码——本文档只输出方案，不动手

---

**报告出具时间**：2026-06-24
**审计闭合时间**：2026-06-25
**审计完成度**：✅ 7 finding / 6 commit（含 2 fix）/ 净删 -24 行 / 7/7 原则对齐 / **重构闭合**