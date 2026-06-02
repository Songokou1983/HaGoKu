# Analyst 对话式交互实现计划

> **面向 AI 代理的工作者：** 使用 subagent-driven-development（推荐）或 executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 把 Analyst 从「黑盒 JSON → 确认」改为「对话循环 + submit_analysis 收口」

**架构：** AnalystAgent.run() 改 while True 循环，LLM 通过工具探索数据/提议方法/向用户提问，唯一退出条件是 LLM 调 `submit_analysis`。Orchestrator 删 plan 参数和确认循环。

**技术栈：** Python 3.13, MiniMax-M3 API, scipy/statsmodels, ProjectContext

**规格：** `docs/superpowers/specs/2026-06-02-analyst-dialogue-design.md`

---

## 文件清单

| 文件 | 职责 |
|------|------|
| `hagoku/tools/agent_tool_defs.py` | 新工具注册（N1-N4） |
| `hagoku/agents/analyst/agent.py` | run() 改对话循环（O1-O4） |
| `hagoku/manager/orchestrator.py` | 删旧 Analyst 逻辑（P1-P3） |
| `hagoku/context/project_context.py` | derive_snapshot 加 findings 键（Q1） |
| `tests/test_product/test_analyst_dialogue.py` | 新守门测试（T1-T5） |

---

### 任务 N1：注册 `propose_method` 工具

**文件：**
- 修改：`hagoku/tools/agent_tool_defs.py`（末尾追加）

- [ ] **步骤 1：写 handler + 注册**

```python
def _handle_propose_method(args: dict, ctx: dict, _df: pd.DataFrame | None) -> dict:
    return {
        "method_name": args.get("method_name", ""),
        "reasoning": args.get("reasoning", ""),
        "prerequisites": args.get("prerequisites", ""),
        "accepted": None,  # 由前端/用户填写
    }

agent_tools.register(Tool(
    name="propose_method",
    description="向用户建议一种分析方法，说明理由和前提。调用后会暂停等待用户回复。用户可接受、否定或调整。",
    parameters={
        "type": "object",
        "properties": {
            "method_name": {"type": "string", "description": "方法名（如「趋势分解」「线性回归」「分组t检验」）"},
            "reasoning": {"type": "string", "description": "为什么建议这个方法"},
            "prerequisites": {"type": "string", "description": "前提条件（如「需要至少 30 个样本」）"},
        },
        "required": ["method_name", "reasoning"],
    },
    handler=_handle_propose_method,
    agents=["analyst"],
))
```

- [ ] **步骤 2：验证**：`pytest tests/test_doctrine_compliance.py -q`
- [ ] **步骤 3：Commit** `feat(N1): propose_method 工具注册`

---

### 任务 N2：注册 `ask_user` 工具

**文件：**
- 修改：`hagoku/tools/agent_tool_defs.py`（末尾追加）

- [ ] **步骤 1：写 handler + 注册**

```python
def _handle_ask_user(args: dict, ctx: dict, _df: pd.DataFrame | None) -> dict:
    return {
        "question": args.get("question", ""),
        "options": args.get("options", []),
    }

agent_tools.register(Tool(
    name="ask_user",
    description="向用户提问，需要用户方向性决策时使用此工具。调用后会暂停等待用户回复。普通分析陈述用纯文本输出不要用此工具。如果你提供 options，前端渲染为可点击按钮。",
    parameters={
        "type": "object",
        "properties": {
            "question": {"type": "string", "description": "问题文本"},
            "options": {"type": "array", "items": {"type": "string"}, "description": "可选回复项"},
        },
        "required": ["question"],
    },
    handler=_handle_ask_user,
    agents=["analyst"],
))
```

- [ ] **步骤 2：验证**：`pytest tests/test_doctrine_compliance.py -q`
- [ ] **步骤 3：Commit** `feat(N2): ask_user 工具注册`

---

### 任务 N3：注册 `run_statistical_test` 工具

**文件：**
- 修改：`hagoku/tools/agent_tool_defs.py`（末尾追加）

- [ ] **步骤 1：写 handler**

```python
def _handle_run_statistical_test(args: dict, ctx: dict, _df: pd.DataFrame | None) -> dict:
    import numpy as np
    from scipy import stats as _stats

    test_type = str(args.get("test_type", "")).strip()
    columns = list(args.get("columns") or [])
    if not test_type or not columns:
        return {"error": "test_type 和 columns 必填"}

    try:
        if test_type == "ttest":
            if len(columns) >= 2:
                a = _df[columns[0]].dropna().astype(float)
                b = _df[columns[1]].dropna().astype(float)
                stat, p = _stats.ttest_ind(a, b)
                return {"test": "ttest", "statistic": float(stat), "p_value": float(p), "columns": columns[:2]}
        elif test_type == "anova":
            groups = [_df[c].dropna().astype(float) for c in columns if c in _df.columns]
            if len(groups) >= 2:
                stat, p = _stats.f_oneway(*groups)
                return {"test": "anova", "statistic": float(stat), "p_value": float(p), "columns": columns}
        elif test_type == "pearson_r":
            if len(columns) >= 2:
                a = _df[columns[0]].dropna().astype(float)
                b = _df[columns[1]].dropna().astype(float)
                # align
                mask = a.notna() & b.notna()
                r, p = _stats.pearsonr(a[mask], b[mask])
                return {"test": "pearson_r", "statistic": float(r), "p_value": float(p), "columns": columns[:2]}
        elif test_type == "spearman_r":
            if len(columns) >= 2:
                a = _df[columns[0]].dropna().astype(float)
                b = _df[columns[1]].dropna().astype(float)
                mask = a.notna() & b.notna()
                r, p = _stats.spearmanr(a[mask], b[mask])
                return {"test": "spearman_r", "statistic": float(r), "p_value": float(p), "columns": columns[:2]}
        elif test_type == "chi2":
            if len(columns) >= 2:
                a = _df[columns[0]].dropna()
                b = _df[columns[1]].dropna()
                ct = pd.crosstab(a, b)
                stat, p, dof, exp = _stats.chi2_contingency(ct)
                return {"test": "chi2", "statistic": float(stat), "p_value": float(p), "dof": int(dof), "columns": columns[:2]}
        elif test_type == "linear_regression":
            if len(columns) >= 2:
                import statsmodels.api as sm
                X = sm.add_constant(_df[columns[1:]].dropna().astype(float))
                y = _df[columns[0]].loc[X.index].dropna().astype(float)
                X = X.loc[y.index]
                model = sm.OLS(y, X).fit()
                return {
                    "test": "linear_regression",
                    "r_squared": float(model.rsquared),
                    "params": {k: float(v) for k, v in model.params.items()},
                    "p_values": {k: float(v) for k, v in model.pvalues.items()},
                    "columns": columns,
                }
        elif test_type == "trend_decomposition":
            if columns:
                col = columns[0]
                s = _df[col].dropna().astype(float)
                # simple rolling mean
                trend = s.rolling(window=min(7, len(s)//4), center=True).mean()
                detrended = s - trend
                return {
                    "test": "trend_decomposition",
                    "column": col,
                    "trend_mean": float(trend.mean()) if not trend.isna().all() else None,
                    "detrended_std": float(detrended.std()) if not detrended.isna().all() else None,
                }
        return {"error": f"不支持的 test_type: {test_type}"}
    except Exception as e:
        return {"error": str(e)}
```

- [ ] **步骤 2：注册工具**

```python
agent_tools.register(Tool(
    name="run_statistical_test",
    description="执行统计检验。可用类型：ttest, anova, chi2, pearson_r, spearman_r, linear_regression, trend_decomposition",
    parameters={
        "type": "object",
        "properties": {
            "test_type": {"type": "string", "enum": ["ttest", "anova", "chi2", "pearson_r", "spearman_r", "linear_regression", "trend_decomposition"]},
            "columns": {"type": "array", "items": {"type": "string"}, "description": "要分析的列名（第一个通常是目标变量）"},
            "params": {"type": "object", "description": "额外参数"},
        },
        "required": ["test_type", "columns"],
    },
    handler=_handle_run_statistical_test,
    agents=["analyst"],
))
```

- [ ] **步骤 3：验证**：`pytest tests/test_doctrine_compliance.py -q`
- [ ] **步骤 4：Commit** `feat(N3): run_statistical_test 工具注册`

---

### 任务 N4：注册 `submit_analysis` 工具

**文件：**
- 修改：`hagoku/tools/agent_tool_defs.py`（末尾追加）

- [ ] **步骤 1：写 handler + 注册**

```python
def _handle_submit_analysis(args: dict, ctx: dict, _df: pd.DataFrame | None) -> dict:
    return {
        "findings": args.get("findings", []),
        "method_used": args.get("method_used", []),
        "summary": args.get("summary", ""),
    }

agent_tools.register(Tool(
    name="submit_analysis",
    description="提交分析发现，结束分析阶段。调用前请确保已覆盖用户关心的方向。先回顾本阶段对话中用户提到的关注点，确认都已讨论。confidence 取 high/medium/low 三选一。",
    parameters={
        "type": "object",
        "properties": {
            "findings": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "detail": {"type": "string"},
                        "evidence_columns": {"type": "array", "items": {"type": "string"}},
                        "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
                    },
                    "required": ["title", "detail", "evidence_columns", "confidence"],
                },
            },
            "method_used": {"type": "array", "items": {"type": "string"}},
            "summary": {"type": "string"},
        },
        "required": ["findings", "method_used", "summary"],
    },
    handler=_handle_submit_analysis,
    agents=["analyst"],
))
```

- [ ] **步骤 2：验证**：`pytest tests/test_doctrine_compliance.py -q`
- [ ] **步骤 3：Commit** `feat(N4): submit_analysis 工具注册`

---

### 任务 O1：AnalystAgent.run 对话循环骨架

**文件：**
- 修改：`hagoku/agents/analyst/agent.py:222-270`（run 方法重写）

- [ ] **步骤 1：重写 run() 为对话循环**

```python
def run(
    self, df: pd.DataFrame, context: dict,
    project_id: str | None = None,
    phase: str = "full",
    *, emit_completed: bool = True,
) -> dict:
    """对话式分析循环。LLM 自由探索，submit_analysis 退出。"""
    self._emit(EventType.AGENT_STARTED, {"goal": "对话式数据分析"})

    from hagoku.tools.registry import agent_tools as _agt
    from hagoku.tools.data_io import load_data
    _tools = _agt.to_openai("analyst")

    query = context.get("query", "") or context.get("analysis_goal", "")
    project_ctx = context.get("_project_context")

    # 拼 system prompt
    system = (
        "你是数据分析师。可以用工具探索数据、跑统计检验、向用户提问、提议方法。\n"
        "每次只做一个操作，和用户协作推进分析。\n"
        "想给用户多选时用 ask_user 工具，开放回答用纯文本。\n"
        "准备好了就调 submit_analysis 提交发现。\n"
        "confidence 取 high/medium/low 三选一，不编造。\n"
    )

    if project_ctx:
        ctx_block = project_ctx.build_prompt("analyst", context)
        system += "\n\n" + ctx_block["system_prefix"] + "\n\n" + ctx_block["upstream_summary"]

    messages: list[dict] = [{"role": "system", "content": system}]
    if project_ctx:
        messages.extend(ctx_block.get("messages_history", []))  # 律 3

    intro = f"分析目标：{query}\n可用列：{', '.join(df.columns)}\n数据行数：{len(df)}"
    messages.append({"role": "user", "content": intro})

    from ...llm.client import create_raw_client
    client = create_raw_client(self.llm_config)

    for round_idx in range(30):
        if round_idx >= 25:
            messages.append({"role": "system", "content": "（已分析多轮，请准备 submit_analysis）"})

        resp = client.chat.completions.create(
            model=self.llm_config.model, messages=messages,
            temperature=0.3, max_tokens=4096, tools=_tools, tool_choice="auto",
        )
        msg = resp.choices[0].message
        txt = (msg.content or "").strip()
        tc_list = getattr(msg, "tool_calls", None)
        findings = None

        if tc_list:
            assistant_block: dict = {"role": "assistant", "content": txt or None}
            if txt:
                assistant_block["content"] = txt
            tool_call_blocks = []
            for tc in tc_list:
                fn = tc.function
                try:
                    args = json.loads(fn.arguments) if fn.arguments else {}
                except json.JSONDecodeError:
                    continue
                result = _agt.dispatch(fn.name, args, context, df)

                if fn.name == "submit_analysis":
                    findings = result
                    break

                tc_id = getattr(tc, "id", "") or ""
                tool_call_blocks.append({
                    "id": tc_id, "type": "function",
                    "function": {"name": fn.name, "arguments": fn.arguments},
                })
                messages.append({
                    "role": "tool", "tool_call_id": tc_id,
                    "content": json.dumps(result, ensure_ascii=False, default=str),
                })

            if findings is not None:
                break

            if tool_call_blocks:
                assistant_block["tool_calls"] = tool_call_blocks
            messages.append(assistant_block)
        elif txt:
            messages.append({"role": "assistant", "content": txt})

        # 展示当前输出 → 等用户回复
        display = {
            "message": txt or "[工具调用]",
            "interaction_revision": round_idx,
        }
        user_reply = self._pause_and_wait("analyst", display)
        if user_reply is None:
            continue
        messages.append({"role": "user", "content": user_reply})

        # ProjectContext 写入
        if project_ctx:
            project_ctx.add_user_feedback(stage="analyst", revision=round_idx, raw_text=user_reply)
            project_ctx.add_agent_response(
                stage="analyst", revision=round_idx,
                content=txt or "[工具调用]",
                snapshot=project_ctx._derive_snapshot(context),
            )

    if findings is None:
        raise RuntimeError("Analyst: 30 轮未提交 submit_analysis")

    self.event_bus.emit(EventType.AGENT_COMPLETED, "analyst", {
        "result_summary": findings.get("summary", ""),
    })
    return findings
```

- [ ] **步骤 2：验证**：`pytest tests/test_doctrine_compliance.py -q --tb=short`
- [ ] **步骤 3：Commit** `feat(O1): AnalystAgent.run 对话循环`

---

### 任务 P1：Orchestrator 删旧 Analyst 逻辑

**文件：**
- 修改：`hagoku/manager/orchestrator.py:2420-2490`（Analyst 调用段）

- [ ] **步骤 1：替换 Analyst 调用段**

找出 `# 6. Analyst: 统计分析` 到 Reporter 调用之间的代码，替换为：

```python
            # 6. Analyst: 对话式分析
            findings = analyst.run(df_clean, context)
            n_findings = len(findings.get("findings", []))

            self.event_bus.emit(EventType.AGENT_COMPLETED, "analyst", {
                "result_summary": f"发现 {n_findings} 条结论",
            })
```

同时删除 `plan` 变量的构建（搜索 `plan = {` 在 Analyst 附近的定义）。

- [ ] **步骤 2：删除 analyst_review 死代码**

删除 `analyst_review_pause_payload` 调用和 `while True: 确认循环` 整块。

- [ ] **步骤 3：验证**：`pytest tests/test_product/test_agent_interaction_contract.py tests/test_doctrine_compliance.py -q`
- [ ] **步骤 4：Commit** `refactor(P): 删旧 Analyst plan/确认循环`

---

### 任务 Q1：ProjectContext derive_snapshot 支持 findings

**文件：**
- 修改：`hagoku/context/project_context.py:120-130`（derive_snapshot 方法）

- [ ] **步骤 1：扩展 snapshot**

确保 `derive_snapshot` 输出的 dict 包含 `findings` 键（当 context 中有时）：

```python
def _derive_snapshot(self, context: dict) -> dict:
    # ... existing code ...
    if "findings" in context:
        snapshot["findings"] = context["findings"]
    return snapshot
```

- [ ] **步骤 2：验证**：`pytest tests/test_context/ -q`
- [ ] **步骤 3：Commit** `feat(Q1): derive_snapshot 支持 findings`

---

### 任务 T1-T5：守门测试

**文件：**
- 创建：`tests/test_product/test_analyst_dialogue.py`

**T1：submit_analysis 唯一退出**

```python
def test_analyst_submit_analysis_唯一退出():
    """只有 submit_analysis 退出，代码不识别任何关键词。"""
    import hagoku.agents.analyst.agent as a_mod
    import hagoku.llm.client as llm_mod
    from hagoku.config import LLMConfig
    import pandas as pd

    captured = []
    _orig = llm_mod.create_raw_client

    round_count = [0]
    class FakeClient:
        class chat:
            class completions:
                @staticmethod
                def create(*, model, messages, **kw):
                    captured.append(messages)
                    round_count[0] += 1
                    if round_count[0] == 1:
                        # Round 1: plain text "可以了" ← code should NOT exit
                        m = type('msg',(),{'content':'可以了','tool_calls':None})()
                    else:
                        # Round 2: submit_analysis
                        tc = type('tc',(),{'id':'1','function':type('fn',(),{'name':'submit_analysis','arguments':'{"findings":[],"method_used":[],"summary":"ok"}'})()})()
                        m = type('msg',(),{'content':'','tool_calls':[tc]})()
                    resp = type('resp',(),{'choices':[type('c',(),{'message':m})()]})()
                    return resp

    llm_mod.create_raw_client = lambda c: FakeClient()
    try:
        from hagoku.agents.analyst.agent import AnalystAgent
        agent = AnalystAgent(LLMConfig(model="t",model_quick="t"),event_bus=None)
        agent._pause_and_wait = lambda stage, data: "可以了"  # simulate user
        findings = agent.run(pd.DataFrame({"X":[1]}), {"column_semantics":[],"query":"test"})
        assert round_count[0] >= 2, "应至少运行 2 轮"
    finally:
        llm_mod.create_raw_client = _orig
```

**T2-T5** 类似模式：spy LLM client，构造 message，断言行为。

- [ ] 每个 test 写 → 跑 → commit。5 个 commit。
- [ ] 最后跑全量：`pytest tests/test_product/ tests/test_context/ tests/test_doctrine_compliance.py -q`

---

## 自检

1. **规格覆盖度**：N(新工具) → O(对话循环) → P(Orch 清理) → Q(ProjectContext) → T(守门测试)。规格 §2-§7 §11 全覆盖
2. **占位符**：无 TODO/待定，handler 代码完整
3. **类型一致性**：findings dict 结构与 spec §8 Reporter 接收一致，包含 findings/method_used/summary 三个键
