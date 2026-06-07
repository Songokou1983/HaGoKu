# [作废] 分析阶段二段化 brief（2026-06-07）

> ⛔ **本 brief 已作废，不要执行**。
>
> **作废原因**：本 brief §1 现状盘点基于错误的生产路径假设——以为 WebSocket 路径走 `AnalystAgent.begin()` / `respond()`，实际走 `_handle_analyst_reply` → `run_step()`。`begin/respond/run` 全部是死代码。
>
> **替代 brief**：`@/home/son_goku/HaGoKu/docs/plans/2026-06-07-analyst-and-routing-brief.md`
>
> 本文件保留作为审计史料，不删除。
>
> ---
>
> **文档定位**：架构审核方（Cascade）出具，交付实施 AI 执行。
> 
> 与 `2026-06-07-channel-hardening-brief.md` **同一执行流程契约**：实施→审核→退回返工→fixup。
>
> **本 brief 不是**：通道收口 brief 的延伸、新功能堆叠、Reporter 改造。
> **本 brief 是**：把 Analyst 阶段从「30 轮黑盒 + 三按钮 UX」改造为「阶段 1 自主分析（书面概括）+ 阶段 2 自由对话」。

---

## 0. 角色与边界（实施方必读）

继承 `channel-hardening-brief` §0 的全部规则：

- **不可越界事项**（铁律 -4 ~ 9 全部适用）
- **CH-7-fixup 自加契约 3 条全部继续生效**：
  1. body 中文件名 / grep / ls 类断言须有 shell 实测证据
  2. 数字（test count / 行数）必须当次实测，禁止抄写
  3. 否定断言（不存在 / 空 / 无）须两种工具交叉验证
- **commit message 前缀**：`[A-N]`（区别于上一个 brief 的 `[CH-N]`）
- **每任务独立 commit + 自检三组 pytest + body 实测证据**

### 本 brief 特定红线

| # | 红线 | 理由 |
|---|------|------|
| L1 | **不许动 Reporter** | Reporter 角色在本 brief 内不变 |
| L2 | **不许动 Scout/Cleaner** | 它们的对话通道已成熟，不在本 brief 范围 |
| L3 | **不许删除现有 `run_step()` / `run()`** | 旧入口可能仍被某些路径依赖；本 brief 只改 `begin()` / `respond()` 与新增 `_apply_analyst_reply_with_llm` |
| L4 | **阶段 1 的"书面概括"必须真 LLM 调用** | 禁止字符串拼接 / 模板填充 / format string 假装概括 |
| L5 | **不许写"建议 vs 决定"分支逻辑** | 利用 `route_to` 工具的天然语义（不传 stage = 留 / 传 stage = 跳）；代码不做挽留机制 |
| L6 | **不许给阶段 2 加按钮** | UX 必须是自由文本输入框；任何 `actions=[...]` 列表都属退回点 |

---

## 1. 现状盘点（背景，已审计完成）

### 1.1 现有能力已就位但被堵死

| 能力 | 位置 | 状态 |
|------|------|------|
| `route_to` 工具（4 阶段切换 + 留当前阶段语义） | `hagoku/tools/agent_tool_defs.py:565` | ✅ 已就绪 |
| `propose_method` / `run_statistical_test` / `update_analysis_scope` / `ask_user` / `submit_analysis` | `agent_tool_defs.py` | ✅ 已就绪 |
| 律 4 / 律 8 契约测试覆盖 Analyst | `tests/test_product/test_tool_schema_coverage.py` | ✅ 已就绪 |
| `_apply_scout_reply_with_llm`（自由文本对话样板） | `hagoku/manager/llm_dispatch/scout_reply.py` | ✅ 可参照 |
| 护栏违规后"修正后重跑"路径 | `hagoku/manager/payloads/pipeline_helpers.py:47-162` | ✅ 已就绪 |

### 1.2 缺口

| 缺口 | 位置 | 影响 |
|------|------|------|
| **阶段 1 输出 = 统计 results 列表直抛**，非书面概括 | `hagoku/agents/analyst/agent.py:425-446` | 用户面对 raw stats，不是分析师视角 |
| **阶段 2 = 写死三按钮 UX** | `hagoku/agents/analyst/agent.py:438` `["生成报告", "继续分析", "结束分析"]` | 没有自由输入框；上游所有工具能力被 UX 堵死 |
| **无 `_apply_analyst_reply_with_llm`** | `hagoku/manager/llm_dispatch/` | 阶段 2 接收用户文本无路径 |
| **Analyst prompt 角色 = "通往报告的关卡"** | `hagoku/agents/analyst/prompt.md:254` | 角色错位：分析员 ≠ 分析伙伴 |

### 1.3 设计契约（用户确认）

| 设计点 | 决定 |
|---|---|
| 阶段 1 形态 | 自主分析（基于上下文）→ **LLM 重写为书面概括化结论** |
| 阶段 1 产物结构 | 3-5 段叙述性发现，每段含 **[发现] [统计依据] [局限或解读]** 三要素 |
| 阶段 2 形态 | **自由文本对话**，输入框打开 |
| 阶段 2 LLM 工具集 | 复用现有（`run_statistical_test` / `update_analysis_scope` / `ask_user` / `route_to` / `submit_analysis`） |
| 阶段 2 终止机制 | LLM 自然调 `route_to(stage="reporter")` 收尾 / 调 `route_to(stage="scout")` 跳回 / 不调 = 留 |
| 用户挽留机制 | **零代码**——LLM 解读"再等等"自然不调 `route_to(stage=...)` |
| Reporter 角色 | **基于数据和结论**做可视化 / 专业 / 正式 / 永久——本 brief 不动 |

---

## 2. 任务清单（4 个任务，按依赖排序）

### A-1 阶段 1 输出书面概括化

**根因**
`hagoku/agents/analyst/agent.py:425-446` `begin()` 调 `self.run(df, context, plan)` 拿到 results 列表后直接 `_pause(message=summary, ...)`，summary 是字符串拼接（`"完成 N 项分析，X 项显著发现"`）——不是分析师视角的书面概括。

**改动范围**
- `hagoku/agents/analyst/agent.py:421-446` `begin()` 方法尾部
- 在 `results` 拿到后、`_pause` 之前**新增 LLM 调用**：把 `results + business_metrics + context.analysis_goal + ctx 上下文` 喂给 LLM，让它产出 3-5 段叙述性发现。
- 每段的结构契约（system prompt 强制约束）：

  ```
  ## [发现 N]：<一句话标题>
  
  [发现] <这个发现说了什么——一段叙述性表达>
  [统计依据] <p 值 / 效应量 / 置信区间 / 样本量；用人话说统计意义>
  [局限或解读] <注意事项 / 替代解释 / 适用边界>
  ```

- `_pause(message=...)` 的 `message` 改用 LLM 输出（非字符串拼接）
- `_pause` 的 `actions` 字段保留为空列表 `[]` 或不传——**不再硬编码三按钮**（A-2 会进一步利用）
- `data` 字段仍保留 `results` / `business_metrics`（供阶段 2 LLM 调用）

**契约（写到 system prompt 里）**
- 每段必须含三要素 [发现][统计依据][局限或解读]
- 不许编造未在 results 中出现的统计数字
- 不许给"建议进入报告阶段"这种诱导用户终止的句式

**验收标准**
1. `pytest tests/test_doctrine_compliance.py -q` → 全绿
2. `pytest tests/test_agents/ -q` → 全绿
3. `pytest -q` → 全绿（数字必须对账）
4. 新增单测 `tests/test_agents/test_analyst_phase1_summary.py`：mock LLM 客户端，断言：
   - LLM 被调用且 system prompt 含"三要素"约束词
   - LLM 输出原文写入 `_pause` 的 `message`
   - `_pause` 的 `actions` 不含 `"生成报告"` 字符串
5. **grep 反向断言**：`grep "生成报告.*继续分析.*结束分析" hagoku/agents/analyst/agent.py` → 空（旧三按钮已清）

**红线**
- L4：禁止用 f-string / .format() 拼凑"概括"假装是 LLM 输出
- 禁止删除 `_pause` / `_done` 公共 API
- 禁止改 `run()` / `run_step()` 内部循环逻辑（仅在 begin 末尾加新 LLM 调用）

---

### A-2 阶段 2 自由对话入口

**前置依赖**：A-1 完成

**根因**
`hagoku/agents/analyst/agent.py:452-481` `respond()` 仅识别 3 个写死的 `action` 字符串（`"生成报告"` / `"继续分析"` / 其他）。用户的自由文本（"我觉得方向不对" / "换 t 检验试试" / "再等等"）无路径。

**改动范围**

#### 2.1 新建 `hagoku/manager/llm_dispatch/analyst_reply.py`

参照 `scout_reply.py` 模式，签名：

```python
def _apply_analyst_reply_with_llm(
    context: dict,
    user_text: str,
    df: pd.DataFrame,
    client: Any,
    model: str,
    *,
    channel_logger: Any | None = None,
) -> dict:
    """阶段 2：把用户自由文本喂给 Analyst LLM，让它调用工具或文本回复。
    
    工具集：run_statistical_test / update_analysis_scope / propose_method / 
            ask_user / route_to / get_column_stats / get_sample_rows / list_columns / 
            group_stats / update_field_table / submit_analysis
    （即 agent_tools.to_openai("analyst") 全集）
    
    返回：{
        "reply_text": str,           # LLM 文本回复（如果有）
        "tool_calls_applied": list,  # 已 dispatch 的工具调用日志
        "next_action": str,          # "stay" | "route_to_<stage>" | "submitted"
        "route_target": str | None,  # 若 next_action == "route_to_*"
    }
    """
```

**关键实现点**：
- 把当前 `context` 完整作为 `_project_context.build_prompt("analyst", context)` 注入
- LLM 调用必须传 `tools=agent_tools.to_openai("analyst")`
- 处理 `tool_calls`：每个调用通过 `agent_tools.dispatch(name, args, ctx, df)` 执行
- `route_to` 是特殊工具：根据 `args.stage` 决定 `next_action`
  - 不传 stage → `next_action = "stay"`
  - 传 stage → `next_action = f"route_to_{stage}"`
- `submit_analysis` → `next_action = "submitted"`
- 必须 `dump_messages(...)` 全部 LLM 调用（沿用 CH-4 契约）

#### 2.2 改 `hagoku/agents/analyst/agent.py:452-481` `respond()`

```python
def respond(self, user_input: dict) -> InteractionResult:
    if self._phase != "next_step":
        return self._done("done", "阶段错误，请重新开始", {})
    
    user_text = user_input.get("text", "") or user_input.get("action", "")
    if not user_text:
        raise RuntimeError("Analyst.respond 收到空用户输入（通道断裂）")
    
    from ..manager.llm_dispatch.analyst_reply import _apply_analyst_reply_with_llm
    
    client = create_raw_client(self.llm_config)
    result = _apply_analyst_reply_with_llm(
        context=self._context,
        user_text=user_text,
        df=self._df,
        client=client,
        model=self.llm_config.model,
    )
    
    if result["next_action"] == "stay":
        # 留在阶段 2，继续对话
        return self._pause(
            phase="next_step",
            message=result["reply_text"],
            actions=[],  # L6: 自由输入框，无按钮
            pending_items=[],
            data={"tool_calls_applied": result["tool_calls_applied"]},
        )
    elif result["next_action"].startswith("route_to_"):
        target = result["route_target"]
        if self.orchestrator:
            self.orchestrator.unblock_task("analyst")
        return self._pause(
            phase="next_step",
            message=result["reply_text"] or f"切换到 {target} 阶段",
            actions=[],
            pending_items=[],
            data={"proceed_to": target},
        )
    elif result["next_action"] == "submitted":
        if self.orchestrator:
            self.orchestrator.unblock_task("analyst")
        return self._done("done", result["reply_text"] or "分析提交完成", {})
    else:
        raise RuntimeError(f"未知 next_action: {result['next_action']}（控制通道断裂）")
```

#### 2.3 删除旧三按钮分支
原 `respond()` 里 `if action == "生成报告"` / `"继续分析"` / `else` 三段全部删除。

**验收标准**
1. 新增 `tests/test_agents/test_analyst_reply_dispatch.py`，mock LLM 客户端，覆盖：
   - `test_user_text_triggers_route_to_reporter`（用户说"够了"→ LLM 调 route_to(reporter) → next_action == "route_to_reporter"）
   - `test_user_text_triggers_route_to_scout`（用户说"方向不对"→ LLM 调 route_to(scout) → next_action == "route_to_scout"）
   - `test_user_text_stays_in_phase_2`（用户说"再看看"→ LLM 不调 route_to → next_action == "stay"）
   - `test_user_text_triggers_run_statistical_test`（用户说"换 t 检验"→ tool_calls_applied 含 run_statistical_test）
   - `test_user_text_triggers_submit_analysis`（→ next_action == "submitted"）
2. `respond()` 单测 `tests/test_agents/test_analyst_respond.py`：mock `_apply_analyst_reply_with_llm`，断言三种 `next_action` 各自的 `_pause` / `_done` 行为
3. **grep 反向断言**：
   - `grep '"生成报告"\|"继续分析"\|"结束分析"' hagoku/agents/analyst/agent.py` → 空
   - `grep "actions=\[" hagoku/agents/analyst/agent.py` → 仅命中 `actions=[]` 空列表（无写死按钮）
4. 全量 `pytest -q` 全绿

**红线**
- L5：禁止在 `_apply_analyst_reply_with_llm` 内写"如果 LLM 没调 route_to 就主动建议用户" 类逻辑——LLM 不调就是不调
- L6：禁止在 `_pause(actions=[...])` 里塞任何字符串
- 禁止在 `respond()` 里 except + return 默认值（铁律 7）

---

### A-3 prompt 重写：从"通往报告的关卡" → "分析伙伴"

**前置依赖**：A-1 + A-2 完成（行为先就位再调 prompt）

**根因**
`hagoku/agents/analyst/prompt.md:254` 写明 `"建议进入报告阶段，你确认吗？"`——把 Analyst 定位成关卡。新角色应是"分析伙伴"。

**改动范围**
- `hagoku/agents/analyst/prompt.md` 整体角色段重写
- 删除"建议进入报告阶段"类话术
- 新增对阶段 1 / 阶段 2 各自行为的明确指令：
  - 阶段 1：自主选方法、产出书面概括化发现（三要素）
  - 阶段 2：与用户讨论 / 接受挑战 / 主动调工具 / 自然使用 `route_to`
- 明示工具使用：
  - 用户说"方向不对" / "应该看 X" → `update_analysis_scope` 或 `route_to(stage="scout")`
  - 用户说"换方法" → `propose_method` 或 `run_statistical_test`
  - 用户说"够了" / "可以了" → `route_to(stage="reporter")`
  - 用户说"再等等" / "我再看看" → 不调 `route_to`，自然回应

**验收标准**
1. `grep "建议进入报告" hagoku/agents/analyst/prompt.md` → 空
2. `grep "分析伙伴\|讨论\|挑战\|纠偏" hagoku/agents/analyst/prompt.md` → 至少各 1 命中
3. 全量 `pytest -q` 全绿（行为不变，prompt 文本调整不影响测试）
4. **手工冒烟**：跑一次完整 pipeline 到 Analyst 阶段 2，输入"换 t 检验试试"，看 LLM 是否调 `run_statistical_test`——commit body 附 dump 文件名作为证据

**红线**
- 禁止 prompt 中出现 LLM 模型名 / API URL / 具体 base_url（铁律 9）
- 禁止用"必须 / 一定 / 唯一" 的强约束语句把 LLM 锁死（与"自由对话"理念冲突）

---

### A-4 契约测试扩展（律 4 + 阶段 1 输出契约）

**前置依赖**：A-1 + A-2 + A-3 完成

**改动范围**

#### 4.1 扩展 `tests/test_product/test_tool_schema_coverage.py`

在 `ANALYST_USER_INTENTS` 中追加阶段 2 措辞（保持原有 10 条不动，**追加 ≥ 10 条**）：

```python
ANALYST_PHASE2_USER_INTENTS = [
    # 挑战 / 反驳
    ("这个相关性看起来有共线性", "run_statistical_test", "test_type"),
    ("p 值这么小是不是多重比较没校正", "run_statistical_test", "test_type"),
    # 方向纠偏（仍在分析阶段内）
    ("不应该按渠道分组，应该按周次", "update_analysis_scope", "add_columns"),
    ("把节假日这个变量加进去", "update_analysis_scope", "add_columns"),
    # 一开始就错了（跳回上游）
    ("数据从一开始就有问题，回去重看字段", "route_to", "stage"),
    ("Cleaner 的清洗方案不对，回去重做", "route_to", "stage"),
    # 接受 / 收尾
    ("够了，去写报告吧", "route_to", "stage"),
    ("可以了，结论我接受", "route_to", "stage"),
    # 留 / 挽留
    ("再等等，我再看看", "route_to", None),  # LLM 不传 stage 即留；测试断言工具存在
    ("先别急着收尾", "route_to", None),
    # 追问 / 深挖
    ("为什么节假日效应这么大", "ask_user", "question"),
    ("看下具体哪些店表现最差", "get_sample_rows", "column"),
]
```

合并到 `ANALYST_USER_INTENTS` 或新建独立常量并 parametrize（实施方自决）。

#### 4.2 新增阶段 1 输出契约测试

`tests/test_agents/test_analyst_phase1_summary.py`（A-1 验收已要求新增，此处追加更严的契约断言）：

- mock LLM 返回固定文本
- 断言 `begin()` 输出的 `message` 字段含 `"[发现]" / "[统计依据]" / "[局限或解读]"` 三要素标记（或等价结构）
- 断言至少有 1 段以 `## [发现` 开头（结构化）

#### 4.3 新增阶段 2 控制流测试

`tests/test_product/test_analyst_phase2_control_flow.py`：

- 端到端：mock LLM 调 `route_to(stage="reporter")` → 断言 Orchestrator 收到 `proceed_to: "reporter"` 信号
- 端到端：mock LLM 不调 `route_to` → 断言留在阶段 2（再次 `_pause(phase="next_step")`）
- 端到端：mock LLM 调 `route_to(stage="scout")` → 断言 `proceed_to: "scout"`

**验收标准**
1. `pytest tests/test_product/test_tool_schema_coverage.py -v` → 通过（新增 12 条 parametrize 全绿）
2. `pytest tests/test_agents/test_analyst_phase1_summary.py -v` → 通过
3. `pytest tests/test_product/test_analyst_phase2_control_flow.py -v` → 通过
4. 全量 `pytest -q` 全绿

**红线**
- 测试断言必须"窄"——禁止"工具任一存在即通过"宽契约
- 阶段 1 输出契约必须断言三要素结构（不能仅断言 message 非空）

---

## 3. 全局红线汇总

继承 `channel-hardening-brief` §3 的 G1-G10，**全部继续生效**。

新增本 brief 特定红线 L1-L6（见 §0）。

---

## 4. 审核方验收清单

每个任务收到 commit 后，按下表打勾（继承 `channel-hardening-brief` §4 + 本 brief 特定项）：

```
A-N 验收
[ ] commit message 以 [A-N] 开头
[ ] body 中所有数字 / 文件名 / grep 结果有 shell 实测证据（继承 CH-7-fixup 契约 1）
[ ] 数字（test count / 行数）当次实测，未抄写（继承契约 2）
[ ] 否定断言双工具交叉验证（继承契约 3）
[ ] diff 范围与本 brief "改动范围"一致（无越界）
[ ] L1-L6 逐条检查无违反
[ ] 任务"验收标准"逐条满足
[ ] 自检三组 pytest 输出已附
[ ] grep 反向断言输出已附
```

任一未通过 → 退回返工。

---

## 5. 提交格式约定

```
[A-N] <一句话描述>

【自检】判断：LLM 拿到分析目标和数据后能自己判断 [本任务的核心问题] 吗？
答案：能 / 不能 → LLM 的活 / 代码的活。
（沿用 channel-hardening 自检模板）

【数字对账 — 当次实测】
- pytest --tb=no -q | tail -3 → <粘贴当次输出>
- 关键 grep / wc / ls 输出 → <粘贴当次输出>

根因：brief A-N — <引用本 brief 哪一条>
改动：<文件 + 行号范围>
验收：
- pytest tests/test_doctrine_compliance.py -q → <结果>
- pytest tests/test_product/test_information_arrival.py -q → <结果>
- pytest -q → <结果>
- <任务特定验证>

未越界声明：本 commit 未改动 brief 列出范围之外的文件。
```

---

## 6. 任务依赖与建议顺序

```
A-1 (阶段 1 书面概括化)
        ↓
A-2 (阶段 2 自由对话入口) ← 依赖 A-1（阶段 1 已不再三按钮，A-2 才能落地）
        ↓
A-3 (prompt 重写)         ← 依赖 A-2（行为先就位再调 prompt 才有意义）
        ↓
A-4 (契约测试扩展)        ← 最后做，护住前 3 项不退化
```

**建议节奏**：每天 1 个任务，4 天内收口。A-2 是最大的（新建文件 + 改 respond + 5+ 测试），可能跨 1.5 天。

---

## 7. 何时回到架构审核方

继承 `channel-hardening-brief` §7 的 5 种情形，新增本 brief 特定的：

6. 发现"阶段 1 书面概括"用现有 LLM 提示工程难以稳定产出三要素结构（应停下来反馈，而非自行降级为字符串拼接绕过 L4）
7. 发现 `_apply_analyst_reply_with_llm` 与 `_apply_scout_reply_with_llm` 有大段可抽取的公共逻辑（应停下来反馈，本 brief 不允许顺手抽公共——抽公共是新课题）

---

**Brief 出具时间**：2026-06-07
**Brief 出具方**：Cascade（架构审核方）
**预计完成**：2026-06-11
**前置依赖**：通道收口 brief（`2026-06-07-channel-hardening-brief.md`）已全部闭环 ✅
**下一次评估**：A-1 ~ A-4 收口后，跑一次完整 pipeline 端到端冒烟，记录 Analyst 阶段 1 + 阶段 2 行为符合本 brief §1.3 全部设计契约。
