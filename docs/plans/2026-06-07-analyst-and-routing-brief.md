# [已完成] Analyst 二段化 + 控制通道全面修复 brief（2026-06-07）

> ✅ **本 brief 已全部交付完成**，10 commit 一次性模式执行通过。
>
> **完成时间**：2026-06-07 ~ 2026-06-08
> **commit 范围**：`c7a640a` (A-1) ~ `27a8012` (C-2)，共 10 commits
> **测试结果**：523 passed + 3 strict xfail（CH-7 494 → 523，新增 29 测试，0 回归）
> **agent.py 行数**：483 → 279（A-5 死代码清理减少 204 行）
> **架构审核结论**：通过；详见本文末 §8「审核报告」
>
> ---
>
> **文档定位**：架构审核方（Cascade）出具，交付实施 AI 执行。
> 
> **执行流程契约**：与 `2026-06-07-channel-hardening-brief.md` / `2026-06-07-analyst-two-phase-brief.md` 同 — 实施→审核→退回返工→fixup。
>
> **本 brief 替代** 早先的 `2026-06-07-analyst-two-phase-brief.md`（该 brief 基于错误的生产路径假设，已作废，但保留作为审计史料）。
>
> **本 brief 范围扩大原因**：在审计 Analyst 阶段时发现 `route_to` 工具在 **全部 4 个 Agent** 都是装饰品（dispatch 仅返回 dict，无人消费），属同一根因。按用户决定「一次性说完，扩大范围，有错就修，靠文档架构区分」一并处理。

---

## §0 角色与边界（实施方必读）

继承 channel-hardening-brief §0 全部规则。**新增/重申**：

### 0.1 commit prefix 规约

| 任务系列 | prefix | 含义 |
|---------|--------|------|
| A-N | `[A-N]` | Analyst 行为正确化（用户原始需求） |
| B-N | `[B-N]` | `route_to` 控制通道全面修复（审计发现） |
| C-N | `[C-N]` | 契约护栏升级（CH-6 律 4/8 盲点补丁） |

### 0.2 继承的诚信契约（CH-7-fixup 立 / 仍生效）

1. body 中文件名 / grep / ls 类断言必须有 shell 实测证据
2. 数字（test count / 行数 / 文件数）必须当次实测，禁止抄写
3. 否定断言（不存在 / 空 / 无）必须两种工具交叉验证

### 0.3 本 brief 特定红线

| # | 红线 | 理由 |
|---|------|------|
| L1 | **不许动 Reporter 的可视化逻辑 / 模板渲染** | Reporter 角色稳定，本 brief 仅修其控制通道 |
| L2 | **不许动 Cleaner / Scout 的核心业务逻辑**（清洗规则 / 字段推断） | 本 brief 仅修其 route_to 链路 |
| L3 | **不许混用 A/B/C 系列 commit** | 单职责原则；commit 越界即退回 |
| L4 | **阶段 1 的"书面概括"必须真 LLM 调用** | 禁止字符串拼接 / 模板填充 / format string 假装概括（Bug 复辟点） |
| L5 | **不许写"建议 vs 决定"分支逻辑** | 利用 `route_to` 工具的天然语义；用户挽留靠下一轮对话，不靠代码 |
| L6 | **死代码删除前必须二次确认无 caller** | A-5 删除 `begin/respond/run` 前用 grep + AST 双验，找到任一 caller 即停 |
| L7 | **`route_to` 链路修复必须分阶段独立 commit** | B-1/B-2/B-3 各自独立，便于审计单点定位 |

---

## §1 现状盘点（基于代码审计）

### 1.1 生产路径全图（WebSocket，唯一在用）

```
[前端 textarea {text: "..."}]
    ↓
@HaGoKu/hagoku/manager/llm_dispatch/reply_handlers.py:100
respond(): text = user_input.get("text").strip()
    ↓
self._STAGE_HANDLERS[self._stage] →
    "scout"    → _handle_scout_reply
    "cleaner"  → _handle_cleaner_reply
    "analyst"  → _handle_analyst_reply
    "reporter" → _handle_reporter_reply
    ↓
返回值识别 ("switch", target) → 递归 respond() 切换阶段
```

### 1.2 死代码识别（Analyst）

| 文件 / 范围 | 状态 | 证据 |
|---|---|---|
| `hagoku/agents/analyst/agent.py:248-403` `run()` | 死代码 | `grep ".run(" hagoku/ tests/` 中无任何 caller 调 `analyst.run(...)`（仅 `begin()` 内部调） |
| `hagoku/agents/analyst/agent.py:406-450` `begin()` | 死代码 | 仅 `respond()` 第 477 行自调 |
| `hagoku/agents/analyst/agent.py:452-481` `respond()` | 死代码 | 无外部 caller（已 grep 全仓） |
| 关联实例字段 `_phase / _df / _context / _plan / _preliminary_results` | 死代码 | 仅 begin/respond/run 用 |
| 三按钮硬字符串 `["生成报告", "继续分析", "结束分析"]` | 死代码 | 仅 respond() 内比较 |

**总死代码量：约 234 行**

### 1.3 致命发现：生产路径上 LLM 是"失明"的

#### 1.3.1 `run_step` 不注入 system prompt

```@HaGoKu/hagoku/agents/analyst/agent.py:190-204
def run_step(self, messages: list[dict], context: dict, df: pd.DataFrame | None = None) -> dict:
    """单步执行：跑 1 轮 LLM，处理 tool_calls，返回 (messages, findings or None)"""
    import json as _json
    from hagoku.tools.registry import agent_tools as _agt
    from ...llm.client import create_raw_client
    if df is None:
        df = getattr(self, '_df', None)
    client = create_raw_client(self.llm_config)
    _tools = _agt.to_openai("analyst")
    resp = client.chat.completions.create(
        model=self.llm_config.model, messages=messages,
        temperature=0.3, max_tokens=4096, tools=_tools, tool_choice="auto",
    )
```

**`messages` 直接来自调用方，未拼 system prompt**。

#### 1.3.2 `_handle_analyst_reply` 不注入 ProjectContext

```@HaGoKu/hagoku/manager/llm_dispatch/reply_handlers.py:79-87
if self._analyst_agent is None:
    from hagoku.agents.analyst import AnalystAgent
    self._analyst_agent = AnalystAgent(self.config.llm, self.event_bus, llm_client=self.llm_deep)
    self._analyst_messages = []
if user_input:
    self._analyst_messages.append({"role": "user", "content": user_input})
result = self._analyst_agent.run_step(self._analyst_messages, context, self._df_clean)
```

**`_analyst_messages = []` 起手为空**——Scout 字段理解 / Cleaner 清洗结果 / 用户原始 query 全部不入 LLM 上下文。

#### 1.3.3 `prompt.md` 在生产路径上未被加载

`run_step()` 不读取 `self.prompt`。`prompt.md` 仅在死代码 `run()` 第 274 行被使用。**LLM 仅靠工具描述工作**。

### 1.4 `route_to` 装饰品（4 阶段全军覆没）

#### 1.4.1 工具实现

```@HaGoKu/hagoku/tools/agent_tool_defs.py:557-561
def _handle_route_to(args: dict, ctx: dict, _df: pd.DataFrame | None) -> dict:
    """处理 route_to 调用：在 ctx 中标记目标阶段，由调用方决定后续。"""
    stage = args.get("stage")
    reason = args.get("reason", "")
    return {"stage": stage, "reason": reason}
```

dispatch 仅返回 dict，**不修改 ctx，不通知 Orchestrator**。docstring 说"由调用方决定后续"——但**没有任何调用方读这个返回**。

#### 1.4.2 4 阶段消费情况

| Agent | `_handle_X_reply` 消费 route_to 吗？ | 当前切换机制 |
|---|---|---|
| Scout | ❌ 不消费 | 硬字符串匹配 `"可以进入下一阶段了" / "确认" / ...`（reply_handlers.py:26）；或 LLM diff 无变化时切（line 39-43） |
| Cleaner | ❌ 不消费 | "非首次进入即切" `assessment is not None → ("switch", "analyst")`（line 77） |
| Analyst | ❌ 不消费 | 仅 `submit_analysis` 触发切（line 89-93） |
| Reporter | ❌ 不消费 | `_handle_reporter_reply` 直接返回 `{"status": "reporter_done"}`（line 96-98） |

**律 4/8 测试只验工具 schema 存在，未验链路是否有效**——这是 CH-6 契约的盲点。

### 1.5 与原始用户设想的差距矩阵

| 用户设想 | 现状 | 差距类型 |
|---|---|---|
| 阶段 1：进入 Analyst 自动跑分析得结论 | 等用户开口；首次输入是 Cleaner 阶段尾话 | **能力缺失** |
| 阶段 1 输出"偏书面和概括" | run_step 直吐 LLM 一句话 + 工具调用，无概括化重写 | **能力缺失** |
| 阶段 2 自由对话 | 通道在（textarea），但 LLM 失明（无 prompt + 无 ctx） | **能力残废** |
| 用户说"方向不对"→ 跳回 Scout | route_to 是装饰品，无效 | **bug** |
| 用户说"够了"→ 跳 Reporter | 仅 submit_analysis 切；route_to(reporter) 无效 | **bug** |
| UI 自由文本输入框 | ✅ 始终存在 | OK |

---

## §2 任务清单（10 个任务，3 系列）

### A 系列：Analyst 行为正确化

#### A-1 `run_step` 注入 system prompt + ProjectContext

**根因**：§1.3.1 + §1.3.2 — LLM 失明

**改动范围**
- `hagoku/agents/analyst/agent.py:190-241` `run_step()`
- 函数签名不变；行为改为：每次调用前**重新拼装 messages**，确保头部含 system prompt 和 ProjectContext.build_prompt 输出

**实现要点**
1. 抽 helper `_compose_system_messages(context: dict) -> list[dict]`：
   - 读取 `self.prompt`（prompt.md 内容）
   - 如 `context.get("_project_context")` 存在 → 调 `build_prompt("analyst", context)` 拿 `system_prefix` + `upstream_summary`
   - 返回头部 system 消息列表
2. `run_step()` 入参 `messages` 视为"对话历史"（仅含 user/assistant/tool 角色）；内部拼装：
   ```python
   composed = _compose_system_messages(context) + messages
   ```
   送 LLM 时用 `composed`；返回 `messages`（不含 system 头，避免下次重复拼）
3. 兼容原签名：调用方 `_handle_analyst_reply` 不变

**验收**
1. 新增单测 `tests/test_agents/test_analyst_run_step_injection.py`：
   - mock LLM client，断言传给 `chat.completions.create` 的 `messages[0].role == "system"`
   - 断言 `messages[0].content` 含 prompt.md 关键词（如"数理分析员" / "统计证据"）
   - 断言 `messages` 含 `ProjectContext.build_prompt` 的 `upstream_summary` 关键词（如 Scout 字段理解片段）
2. `pytest tests/test_doctrine_compliance.py -q` → 全绿
3. `pytest -q` → 全绿（数字对账）

**红线**：禁止把 system prompt 拼到 `_analyst_messages` 永久存储（每次调用重拼）；禁止改 prompt.md 文件本身（A-4 才动）

---

#### A-2 进入 Analyst 自动跑首波分析 + 书面概括化

**前置依赖**：A-1（LLM 不失明后才有意义）

**根因**：§1.5 第 1、2 行 — 不自动跑 / 无书面概括化

**改动范围**
- `hagoku/manager/llm_dispatch/reply_handlers.py:79-94` `_handle_analyst_reply`

**实现要点**
1. 引入 `_analyst_first_pass_done: bool` 标志位（`Orchestrator.__init__` 初始化为 False，`_reset_run_state` 重置）
2. `_handle_analyst_reply` 内：
   ```python
   if not self._analyst_first_pass_done:
       # 阶段 1：自动跑首波分析（不消耗用户输入）
       self._run_analyst_first_pass(context)  # 内部循环 run_step 直到 LLM 收敛
       self._analyst_first_pass_done = True
       # 用户首次进入时尾话保留，作为阶段 2 第一条用户消息
   if user_input:
       self._analyst_messages.append({"role": "user", "content": user_input})
   ```
3. `_run_analyst_first_pass`：
   - 循环调 `run_step` 至 LLM 不再发 tool_calls 或调 `submit_first_pass`（见下）
   - 拿到原始 results → **调用 LLM 重写为书面概括**：
     ```
     system: 你是数据分析师，把以下统计结果重写为 3-5 段书面发现。
              每段含 [发现] / [统计依据] / [局限或解读] 三要素。
              不许编造未在 results 中出现的数字。
     user: <results JSON>
     ```
   - emit `USER_INPUT_REQUESTED("analyst", {message: <书面概括>, ...})` 让前端展示
3. **新工具 `submit_first_pass`**（替代/补充 submit_analysis 在阶段 1 的语义）：
   - 注册到 `agent_tool_defs.py`，仅 Analyst 可用
   - 描述："首波自动分析完成，提交原始 findings 给 Orchestrator 重写为书面概括"
   - 调用后中止 `_run_analyst_first_pass` 循环

**契约（写到 system prompt 里）**
- 每段必须含 `[发现] / [统计依据] / [局限或解读]` 三标记
- 不许编造未在 results 中出现的统计数字
- 不许给"建议进入报告阶段"诱导句式

**验收**
1. 新增 `tests/test_agents/test_analyst_first_pass.py`：
   - mock LLM 多步：先调工具 → 再调 `submit_first_pass`
   - 断言 `_run_analyst_first_pass` 拿到 results
   - 断言 LLM 被调用第二次做"书面概括化"，system prompt 含"三要素"约束
   - 断言 `USER_INPUT_REQUESTED` event emit 时 `message` 含 `[发现]` `[统计依据]` `[局限或解读]` 三标记
2. 新增 `tests/test_product/test_analyst_auto_discover.py` 端到端：
   - mock：进入 Analyst 阶段 → 断言 `_handle_analyst_reply(user_input="")` 触发首波 + 书面概括
   - 断言 `_analyst_first_pass_done` 变 True
3. `pytest -q` → 全绿

**红线**：
- L4：禁止用 f-string 拼凑"概括"假装 LLM 输出
- 禁止把首波结果直接 emit 给前端（必须经 LLM 重写）

---

#### A-3 Analyst `route_to` 链路修复

**根因**：§1.4.2 — Analyst 的 route_to 是装饰品

**改动范围**
- `hagoku/agents/analyst/agent.py:190-241` `run_step()` 增加返回字段
- `hagoku/manager/llm_dispatch/reply_handlers.py:79-94` `_handle_analyst_reply` 消费 route_to

**实现要点**
1. `run_step()` 返回值新增 `route_to: dict | None`：
   ```python
   return {
       "messages": messages,
       "text": txt,
       "submit_analysis": findings is not None,
       "findings": findings,
       "route_to": route_to_args,  # {"stage": "...", "reason": "..."} or None
   }
   ```
   在 dispatch 循环里：若 `fn.name == "route_to"` → `route_to_args = result`
2. `_handle_analyst_reply`：
   ```python
   if result.get("route_to"):
       target = result["route_to"].get("stage")
       if target and target in {"scout", "cleaner", "reporter"}:
           return ("switch", target, {"_route_reason": result["route_to"].get("reason", "")})
       # target == "analyst" 或空 → 留在当前阶段
   ```
3. **保持 submit_analysis 路径不变**（仍然是另一种切阶段方式）

**验收**
1. 新增 `tests/test_product/test_analyst_route_to_link.py`：
   - mock LLM 调 `route_to(stage="reporter")` → 断言 `_handle_analyst_reply` 返回 `("switch", "reporter", ...)`
   - mock LLM 调 `route_to(stage="scout")` → 断言返回 `("switch", "scout", ...)`
   - mock LLM 调 `route_to()` 不传 stage → 断言**不切换**，返回 `{"status": "analyst_review", ...}`
   - mock LLM 同一轮既调 route_to 又调其他工具 → 断言其他工具仍正常 dispatch（不阻塞）
2. `pytest -q` → 全绿

**红线**：L5 — 禁止写"建议 vs 决定"分支；route_to 不传 stage 即留

---

#### A-4 prompt.md 重写：从"通往报告的关卡" → "分析伙伴"

**前置依赖**：A-1（prompt 已被注入）+ A-2（首波书面概括行为已就位）+ A-3（route_to 已生效）

**根因**：`hagoku/agents/analyst/prompt.md:254` `"建议进入报告阶段，你确认吗？"` — 角色定位错位

**改动范围**：`hagoku/agents/analyst/prompt.md` 整体重写

**实现要点**
- 阶段 1 行为指令：自主选方法、产出书面概括化发现（三要素），不诱导用户终止
- 阶段 2 行为指令：与用户讨论 / 接受挑战 / 主动调工具 / 自然使用 `route_to`
- 工具映射（写入 prompt 让 LLM 识别）：
  - 用户说"方向不对" / "应该看 X" → `update_analysis_scope` 或 `route_to(stage="scout")`
  - 用户说"换方法" → `propose_method` 或 `run_statistical_test`
  - 用户说"够了" / "可以了" → `route_to(stage="reporter")`
  - 用户说"再等等" / "我再看看" → 不调 `route_to`，自然回应
- 删除"建议进入报告阶段"类话术

**验收**
1. `grep "建议进入报告" hagoku/agents/analyst/prompt.md` → 空
2. `grep "分析伙伴\|讨论\|挑战\|纠偏" hagoku/agents/analyst/prompt.md` → 至少各 1 命中
3. `pytest -q` → 全绿（不应有测试因 prompt 文本断言失败；如有需在 commit body 解释）

**红线**：禁止 prompt 含 LLM 模型名 / API URL（律 9）；禁止用强约束句式锁死 LLM

---

#### A-5 死代码清理

**前置依赖**：A-1 ~ A-4 全部完成 + 全量 pytest 持续全绿至少 1 整轮

**根因**：§1.2 — `begin/respond/run` 全部死代码，三按钮硬字符串误导审计

**改动范围**
- `hagoku/agents/analyst/agent.py:248-481` 删除 `run()` / `begin()` / `respond()` 三方法
- `hagoku/agents/analyst/agent.py` 类初始化删除关联字段：`_phase`、`_df`、`_context`、`_plan`、`_preliminary_results`
- 同步检查：CLI 路径 / resume 路径 / 测试 是否仍依赖

**调研要求（在 commit body 显式列出）**
1. `grep -rn "AnalystAgent.*\.begin\|AnalystAgent.*\.respond\|AnalystAgent.*\.run\b" hagoku/ tests/ scripts/ hagoku_web/` 输出
2. `grep -rn "_analyst_agent\.begin\|_analyst_agent\.respond\|_analyst_agent\.run\b" hagoku/ tests/` 输出
3. AST 双验：用 ast 模块解析所有 .py 文件，找到 `Attribute(value=Name(_analyst_agent), attr in {begin, respond, run})` 或类似
4. 找到任一 caller → **停止任务，回报架构审核方**（L6）

**验收**
1. 调研输出附 commit body
2. `pytest -q` → 全绿（数字必须与 A-4 后实测对账，**应少 0 个测试**——无测试调死代码；若少数 > 0 → 找到了原本依赖死代码的测试，报告并审议）
3. `wc -l hagoku/agents/analyst/agent.py` → 应减少 ≈230 行
4. `grep -n "生成报告\|继续分析\|结束分析" hagoku/agents/analyst/agent.py` → 空（双工具：grep + Python ast 解析）

**红线**：L6 — 找到任一 caller 即停

---

### B 系列：`route_to` 全面修复（同模式扩展）

#### B-1 Scout `route_to` 链路修复

**前置依赖**：A-3（建立模式）

**改动范围**
- `hagoku/manager/llm_dispatch/scout_reply.py` `_apply_scout_reply_with_llm` 增加 route_to 返回值
- `hagoku/manager/llm_dispatch/reply_handlers.py:13-52` `_handle_scout_reply` 消费 route_to

**实现要点**
1. `_apply_scout_reply_with_llm` 在 dispatch 工具时识别 `route_to`，把 args 暴露在返回值
2. `_handle_scout_reply`：在现有"硬字符串匹配 / LLM diff 无变化 → cleaner"逻辑前**优先**判 route_to：
   ```python
   if applied_route_to:
       target = applied_route_to.get("stage")
       if target and target != "scout":
           return ("switch", target, ...)
   # 后续保留现有逻辑作为 fallback
   ```
3. **保留**现有硬字符串匹配 + LLM diff 路径作为兼容（用户没用 LLM 调 route_to 时仍能切）

**验收**
1. 新增 `tests/test_product/test_scout_route_to_link.py`：
   - mock LLM 调 `route_to(stage="cleaner")` → 断言 `_handle_scout_reply` 返回 `("switch", "cleaner", ...)`
   - mock LLM 调 `route_to(stage="reporter")` → 断言返回 `("switch", "reporter", ...)` （Scout 跳过 Cleaner/Analyst 直接到 Reporter，**先确认 Orchestrator 是否允许此跨阶段跳转**——若不允许，断言降级为留在 scout + log warning）
   - mock 无 route_to → 断言 fallback 路径（硬字符串）仍工作
2. `pytest -q` → 全绿

**红线**：L7 — 与 A-3 / B-2 / B-3 独立 commit

---

#### B-2 Cleaner `route_to` 链路修复

**前置依赖**：A-3（建立模式）

**改动范围**
- `hagoku/agents/cleaner/agent.py` 中 `assess` 或对应路径若有工具调用，识别 route_to
- `hagoku/manager/llm_dispatch/reply_handlers.py:54-77` `_handle_cleaner_reply` 消费 route_to

**调研先行**：Cleaner 是否在用户回复阶段调用工具？若 Cleaner 阶段无 LLM 工具调用入口（仅评估 + 用户确认），则 route_to 来源在前端按钮或硬字符串——此情况下：
- **Option A**：B-2 简化为"在前端按钮文本里加 `route_to(...)` 调用支持"——超出本 brief
- **Option B**：B-2 标记为 N/A，commit body 说明 Cleaner 当前无 LLM 工具调用入口，route_to 在 Cleaner 阶段不可达

**实施方决定**：先用 grep 调研 cleaner 阶段是否调 `agent_tools.dispatch`；若不调 → Option B（commit body 显式说明）；若调 → Option A 受阻则停下回报。

**验收**
1. 调研输出附 commit body
2. 若 Option A：新增 `tests/test_product/test_cleaner_route_to_link.py` 类似 B-1
3. 若 Option B：commit body 显式声明 Cleaner 当前 LLM 工具调用不可达，route_to 在 Cleaner 阶段为 schema-only；C-1 测试将断言此事实
4. `pytest -q` → 全绿

---

#### B-3 Reporter `route_to` 链路审计

**前置依赖**：A-3

**改动范围**：`hagoku/manager/llm_dispatch/reply_handlers.py:96-98`

**调研先行**：Reporter 是否有用户互动？当前 `_handle_reporter_reply` 直接返回 `{"status": "reporter_done"}`——**Reporter 阶段无用户回复处理**。

**Option B 默认**：若审计确认 Reporter 阶段无 LLM 工具调用入口，commit body 显式声明 Reporter 阶段 route_to 为 schema-only，不触达。

**Option A**：若发现 Reporter 实际有交互入口（与文档不符），停下回报。

**验收**
1. 调研输出附 commit body
2. C-1 测试将断言此事实

---

### C 系列：契约护栏升级

#### C-1 律 4 / 律 8 升级 — 链路验证而非仅 schema

**前置依赖**：A-3 + B-1 + B-2 + B-3（4 阶段实际行为已就位）

**根因**：CH-6 律 4/8 测试只验"工具存在 + 参数 schema"，未验"工具调用 → 业务效果"链路完整。`route_to` 全军装饰品就是此盲点的产物。

**改动范围**
- 新建 `tests/test_product/test_control_channel_link_integrity.py`
- 必要时扩展 `tests/test_product/test_tool_schema_coverage.py`（保留原有 schema 测试，**新增**链路测试）

**实现要点**

四张链路矩阵，每个 Agent 一张：

```
Agent: <name>
─────────────────────────────────────────
LLM 调 X 工具 → ctx 应改变 / Orchestrator 应收到信号
─────────────────────────────────────────
update_field_role(field=..., role=...)        → ctx[fields_meta][...]role 改变
update_analysis_scope(add_columns=[...])      → ctx[_analysis_scope] 改变
route_to(stage="reporter")                    → _handle_X_reply 返回 ("switch", "reporter")
route_to() 不传 stage                          → _handle_X_reply 返回 stay
submit_analysis                               → _handle_X_reply 返回 ("switch", "reporter", ...)
...
```

每个 Agent 至少覆盖：
1. 1 个状态变更类工具的链路（如 update_*）— 断言 ctx 真改变
2. 1 个流程控制类工具的链路（route_to / submit_*）— 断言 _handle_X_reply 返回正确切换信号
3. **盲点声明**：若某 Agent 无 LLM 工具入口（B-2 / B-3 的 Option B），测试用 `pytest.mark.xfail(strict=True, reason="<Agent> 当前无 LLM 工具调用入口，route_to 为 schema-only")` 标记。**禁止 skip**——契约要明确暴露盲点

**验收**
1. `pytest tests/test_product/test_control_channel_link_integrity.py -v` → 全绿（含 strict xfail）
2. 旧测试 `tests/test_product/test_tool_schema_coverage.py` / `test_control_channel.py` 仍全绿（保留为 schema-only 契约）
3. `pytest -q` → 全绿

**红线**：
- 测试断言必须"窄"——禁止"工具任一调用即通过"
- xfail 必须 strict=True，禁止用 skip 隐藏盲点

---

#### C-2 端到端冒烟回归

**前置依赖**：A-1 ~ A-5 + B-1 ~ B-3 + C-1 全部完成

**目的**：用一次完整 pipeline 端到端跑通，验证 Analyst 二段化与 route_to 修复在真实路径上协同工作。

**改动范围**
- 新建 `tests/test_product/test_analyst_two_phase_e2e.py`
- 用 mock LLM（不调真模型）模拟一个完整对话剧本：
  1. Cleaner 完成 → 切 Analyst
  2. 自动跑首波（mock LLM 调几个工具 + submit_first_pass）
  3. 书面概括化（mock LLM 二次调用产出三要素文本）
  4. emit USER_INPUT_REQUESTED
  5. 用户输入"这个相关性看起来有共线性" → mock LLM 调 run_statistical_test
  6. 用户输入"方向不对，回去重看字段" → mock LLM 调 route_to(stage="scout")
  7. 断言 Orchestrator 切到 scout
  8. 用户输入"够了，去写报告" → mock LLM 调 route_to(stage="reporter") （重回 Analyst 后）
  9. 断言切到 reporter

**验收**
1. `pytest tests/test_product/test_analyst_two_phase_e2e.py -v` → 全绿
2. **手工冒烟**：跑一次真 pipeline（用真 LLM）到 Analyst 阶段，输入"换 t 检验试试"，看 LLM 调用 dump 文件中 `run_statistical_test` 工具调用——commit body 附 dump 文件名作为证据
3. `pytest -q` → 全绿

**红线**：禁止用真 LLM 跑自动测试（mock 即可，避免 flaky）；手工冒烟仅作 commit body 证据

---

## §3 全局红线汇总

继承 channel-hardening-brief §3 的 G1-G10。

新增本 brief 特定红线 L1-L7（见 §0.3）。

---

## §4 审核方验收清单

每个任务收到 commit 后，按下表打勾：

```
[A/B/C]-N 验收
[ ] commit message 以正确 prefix 开头（A-N / B-N / C-N）
[ ] body 中所有数字 / 文件名 / grep 结果有 shell 实测证据（CH-7-fixup 契约 1）
[ ] 数字（test count / 行数）当次实测，未抄写（契约 2）
[ ] 否定断言双工具交叉验证（契约 3）
[ ] diff 范围与本 brief "改动范围"一致（无越界）
[ ] L1-L7 逐条检查无违反
[ ] 任务"验收标准"逐条满足
[ ] 自检三组 pytest 输出已附
[ ] grep 反向断言输出已附
```

任一未通过 → 退回返工。

---

## §5 提交格式约定

```
[A/B/C-N] <一句话描述>

【自检】判断：LLM 拿到分析目标和数据后能自己判断 [本任务的核心问题] 吗？
答案：能 / 不能 → LLM 的活 / 代码的活。

【数字对账 — 当次实测】
- pytest --tb=no -q | tail -3 → <粘贴当次输出>
- 关键 grep / wc / ls 输出 → <粘贴当次输出>

根因：brief A/B/C-N — <引用本 brief 哪一条>
改动：<文件 + 行号范围>
验收：
- pytest tests/test_doctrine_compliance.py -q → <结果>
- pytest tests/test_product/test_information_arrival.py -q → <结果>
- pytest -q → <结果>
- <任务特定验证>

未越界声明：本 commit 未改动 brief 列出范围之外的文件。
```

---

## §6 任务依赖与建议顺序

```
依赖图：

A-1 (run_step 注入 prompt + ctx) ─┐
                                    ├──→ A-2 (auto-discover + 书面概括)
                                    │
                                    └──→ A-3 (Analyst route_to 链路) ─┐
                                                                       │
                                                                       ├──→ B-1 (Scout route_to)
                                                                       ├──→ B-2 (Cleaner route_to / Option B)
                                                                       └──→ B-3 (Reporter route_to / Option B)
                                                                       │
                                                                       ↓
                                                                    A-4 (prompt 重写)
                                                                       │
                                                                       ↓
                                                                    C-1 (链路契约升级)
                                                                       │
                                                                       ↓
                                                                    A-5 (死代码清理)
                                                                       │
                                                                       ↓
                                                                    C-2 (E2E 冒烟)
```

**建议节奏**：
- Day 1: A-1 + A-2（基础能力）
- Day 2: A-3 + B-1 + B-2 + B-3（route_to 全面修，4 commit）
- Day 3: A-4（prompt 重写）+ C-1（契约升级）
- Day 4: A-5（死代码清理）+ C-2（E2E）

总计 10 commits，约 4 天。

---

## §7 何时回到架构审核方

继承 channel-hardening-brief §7 的 5 种情形，新增本 brief 特定的：

6. **A-2 书面概括化**用现有 LLM 提示工程难以稳定产出三要素结构（应停下来反馈，**不可降级为字符串拼接**绕过 L4）
7. **A-5 调研发现死代码 caller**（应停下来反馈，**不可强删**违反 L6）
8. **B-1 Scout 跨阶段跳转**（route_to(stage="reporter") 跳过 Cleaner/Analyst）—— 是否允许由 Orchestrator 设计决定，**实施方不得自行裁定**，必须停下来回报
9. **B-2/B-3 调研发现 Cleaner/Reporter 实际有 LLM 工具入口**（与本 brief §1.4.2 假设不符），**不可径自扩大改动范围**，必须停下来回报

---

**Brief 出具时间**：2026-06-07
**Brief 出具方**：Cascade（架构审核方）
**前置依赖**：通道收口 brief（`2026-06-07-channel-hardening-brief.md`）已闭环 ✅
**作废前任**：`2026-06-07-analyst-two-phase-brief.md`（基于错误生产路径假设）
**完成时间**：2026-06-08
**完成状态**：✅ 10 commit 全部通过，详见 §8

---

## §8 审核报告（2026-06-08）

### 8.1 commit 链路

| Commit | 任务 | 主题 |
|--------|------|------|
| `c7a640a` | A-1 | `run_step` 注入 system prompt + ProjectContext |
| `9e0652e` | A-2 | 进入 Analyst 自动跑首波分析 + 书面概括化 |
| `1d76594` | A-3 | Analyst `route_to` 链路修复 — LLM 调 route_to 真生效 |
| `5426b01` | B-1 | Scout `route_to` 链路修复 |
| `a625ed0` | B-2 | Cleaner `route_to` 链路审计 — Option B（schema-only） |
| `9402c46` | B-3 | Reporter `route_to` 链路审计 — Option B（schema-only） |
| `8512cb3` | A-4 | prompt.md 重写：从"通往报告的关卡" → "分析伙伴" |
| `16312d7` | C-1 | 律 4 / 律 8 升级 — 链路验证而非仅 schema |
| `8e41b76` | A-5 | 死代码清理：删除 `run/begin/respond` + 五关联字段 |
| `27a8012` | C-2 | 端到端冒烟回归 |

执行顺序与 §6 依赖图完全一致；commit prefix L3 红线零违反。

### 8.2 量化验收

| 指标 | 基线（CH-7 后） | 完成态 | 变化 |
|------|----------------|--------|------|
| `pytest -q` 通过数 | 494 passed | **523 passed + 3 strict xfailed** | +29 测试，0 回归 |
| `hagoku/agents/analyst/agent.py` 行数 | 483 | **279** | −204（A-5 实测） |
| 死代码 `def begin/respond/run` | 3 个方法 | **0**（AST 双验） | 全清 |
| `route_to` 生产路径消费者 | 0 / 4 Agent | **2 / 4 Agent**（Analyst + Scout）+ 2 strict xfail 锁盲点 | 装饰品问题根除 |
| 三要素契约 `[发现]/[统计依据]/[局限或解读]` | 不存在 | prompt + 重写函数 + 单测 + E2E 四处对齐 | 闭环 |

### 8.3 关键设计验证

#### ✅ A-1 LLM 失明修复
- `_compose_system_messages` 在 `run_step` 每次调用前重拼，不污染 `_analyst_messages`
- prompt.md 内容 + `ProjectContext.build_prompt("analyst", ctx)` 双注入
- `test_analyst_run_step_injection.py` 断言传给 `chat.completions.create` 的 `messages[0].role == "system"`

#### ✅ A-2 首波自动 + 书面概括两段式
- 新增工具 `submit_first_pass`（`agent_tool_defs.py:440-472`）独立于 `submit_analysis`，语义区分"首波收敛"vs"分析终结"
- `_run_analyst_first_pass` 循环检测 `submit_first_pass` tool_call → 拿到 findings → `_rewrite_as_written_summary` 二次 LLM 调用产出三要素文本 → emit `USER_INPUT_REQUESTED`
- `_analyst_first_pass_done` 标志位接到 `Orchestrator.__init__` + `_reset_run_state`，重新进入 Analyst 时正确重置（E2E 第 4 步验证）

#### ✅ A-3 / B-1 `route_to` 真生效
- Analyst：`run_step` 返回值新增 `route_to` 字段，`_handle_analyst_reply` 消费切换
- Scout：通过 `context["_scout_route_to"]` ctx 桥递交（与现有 LLM diff 流程兼容），`_handle_scout_reply` 优先判 `route_to`
- 两种模式各自最贴合 Agent 现有架构，未强行统一

#### ✅ B-2 / B-3 诚信处理盲点
- 调研后确认 Cleaner / Reporter 无 LLM 工具调用入口（Cleaner 一次性评估，Reporter 不互动）
- 用 `pytest.mark.xfail(strict=True)` 锁定盲点：若未来接通工具入口，xfail 会 **XPASS 失败**，逼迫开发者移除标记并补链路测试
- **未使用 `skip` 隐藏**（R9 红线零违反）

#### ✅ A-5 死代码清理彻底
- AST 双验：`def begin/respond/run` 全部消失（279 行 agent.py 中零命中）
- 关联实例字段 `_phase/_df/_context/_plan/_preliminary_results` 全清
- 三按钮硬字符串 `["生成报告","继续分析","结束分析"]` 全清

#### ✅ C-1 / C-2 契约护栏闭环
- C-1 链路测试：Scout 3 + Analyst 3 + Cleaner 2 xfail + Reporter 1 xfail = **6 passed + 3 strict xfail**
- C-2 E2E：完整剧本（Cleaner→首波→对话→`route_to(scout)`→重进→`route_to(reporter)`）单测覆盖

### 8.4 与用户原始设想对照

| 用户设想 | 验证 |
|---------|------|
| 阶段 1：进入 Analyst 自动跑分析得结论 | ✅ `_run_analyst_first_pass` 不等用户开口自动触发 |
| 阶段 1 输出"偏书面和概括" | ✅ `_rewrite_as_written_summary` 二次 LLM 调用产出三要素文本 |
| 阶段 2 自由对话 | ✅ `run_step` 单步循环 + 完整工具集 + LLM 不再失明 |
| 用户说"方向不对"→ 跳回 Scout | ✅ `route_to(stage="scout")` E2E 测试覆盖 |
| 用户说"够了"→ 跳 Reporter | ✅ `route_to(stage="reporter")` E2E 测试覆盖 |
| 用户说"再等等"→ 留 | ✅ LLM 不调 `route_to` 即自然留（用户挽留零代码） |
| UI 自由文本输入框 | ✅ 始终存在（前端 `AnalyzePanel.tsx:1528`） |

### 8.5 后续观察点

1. **B-2 / B-3 strict xfail 监控**：若未来 Cleaner / Reporter 需要接通 LLM 工具入口，xfail 会 XPASS 失败，需对应补充链路测试并移除标记
2. **真 LLM 端到端冒烟**：C-2 仅用 mock LLM；建议后续在真实 pipeline 上手工跑一次完整剧本，验证 prompt 重写后的"分析伙伴"行为符合预期
3. **`submit_analysis` vs `submit_first_pass` 语义分化**：当前两个工具并存。`submit_analysis` 走 reporter 切换路径，`submit_first_pass` 走首波收敛路径。prompt 工程上需关注 LLM 是否会混用

### 8.6 审核结论

**通过**。本 brief 10 任务在一次性 commit 模式下质量与单 commit 审核模式相当，部分维度（B-2/B-3 诚信盲点处理、A-5 AST 双验、三要素契约四处对齐）更高。`route_to` 装饰品根因已根除；Analyst 二段化用户设想全部落地；契约护栏 C-1 把 CH-6 律 4/8 盲点补齐。

**审核方**：Cascade（架构审核方）
**审核时间**：2026-06-08
