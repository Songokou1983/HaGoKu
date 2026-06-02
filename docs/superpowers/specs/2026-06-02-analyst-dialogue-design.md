# Analyst 对话式交互设计

**日期**：2026-06-02 · **审查**：2026-06-02 · **状态**：R2 修订
**作者**：开发 + 审查方

---

## 0. 现状审计

### 当前 Analyst 流程

```
orchestrator.run() 
  → analyst.run(df, context, plan)           [agent.py:222]
    → _plan_analysis_via_llm()               [agent.py:788]  一次 LLM 调，输出 JSON 计划
    → 代码跑统计 (scipy) 
    → 返回 results, business_metrics
  → analyst_review_pause_payload(results)    [orchestrator.py:1361]
  → while True: _pause_and_wait → 确认循环   [orchestrator.py:2438]
  → Reporter.run(results, context, ...)
```

### 要改的文件
- `hagoku/agents/analyst/agent.py` — run() 改对话循环
- `hagoku/manager/orchestrator.py` — 删 plan/analyst_review_pause/确认循环
- `hagoku/tools/agent_tool_defs.py` — 新工具注册
- `hagoku/agents/reporter/agent.py` — prompt 适配 findings
- `hagoku_web/src/panels/AnalyzePanel.tsx` — 对话气泡 + 卡片

---

## 1. 目标

Analyst 从黑盒 JSON → 对话循环。LLM 和用户协作挖掘数据，LLM 主动提议方法、提问，用户引导方向。结束条件：LLM 调 `submit_analysis` 工具。

## 2. 核心约束

- **不代替决策**：`submit_analysis` 是发现汇总，不是商业建议
- **唯一退出条件**：LLM 调 `submit_analysis`。代码不识别任何关键词（包括"可以了"）
- **通道透传**：代码只提供工具和通道
- **资源防护**：25 轮起 prompt 追加「请准备 submit_analysis」是资源约束兜底，LLM 仍可继续；30 轮硬退出。此为非语义判断的工程保护，§13 自检表已标注

## 3. 交互模型

```
系统注入：上游上下文 + 知识库 + ProjectContext 对话历史
while True（上限 30 轮，第 25 轮起 prompt 提示「请准备 submit_analysis」）:
    LLM 调工具 / 输出文本
    if LLM 调 submit_analysis: break → 返回 findings → Reporter
    前端展示 LLM 输出 → _pause_and_wait("analyst", payload)
    用户回复 → 透传给 LLM 下一轮
```

## 4. 工具设计

### 已有工具（复用）
- `get_column_stats` / `get_sample_rows` / `group_stats` — 数据探索

### 新增工具

#### `propose_method`

```
name: propose_method
description: 向用户建议一种分析方法，说明理由和前提。用户可接受、否定或调整。
parameters:
  method_name: string   — 方法名（如「趋势分解」「线性回归」「分组t检验」）
  reasoning: string     — 为什么建议这个方法
  prerequisites: string — 前提条件（如「需要至少 30 个样本」「目标变量需正态分布」）
handler: 只做通道——返回给前端渲染，不执行分析
```

【自检】LLM 能自己判断要不要建议方法吗？能——它根据分析目标和数据特征决定。

#### `run_statistical_test`

```
name: run_statistical_test
description: 执行统计检验。可用类型：ttest, anova, chi2, pearson_r, spearman_r, linear_regression, trend_decomposition
parameters:
  test_type: string            — 上面列举的枚举值
  columns: [string]            — 要分析的列名
  params: object (optional)    — 额外参数
handler: dispatch 到 scipy/statsmodels，返回结果 JSON
```

【自检】LLM 能自己判断用什么 test 吗？能——工具描述已列出可用类型，LLM 根据数据特征选择。白名单仅做安全栏板。

#### `ask_user`

```
name: ask_user
description: 向用户提问。当需要用户提供方向性决策时使用（如"要深挖这个异常吗？"）。
            普通分析陈述和开放式讨论用纯文本输出，不用此工具。
            如果你提供 options，前端渲染为可点击按钮。
parameters:
  question: string            — 问题文本
  options: [string] (optional) — 可选回复项，用户可点击或自由回答
handler: 触发 _pause_and_wait，展示问题卡片
```

【自检】LLM 能自己判断该用 ask_user 还是纯文本吗？能——需要用户决策时用 ask_user，普通输出用文本。system prompt 明确此规则。

#### `submit_analysis`

```
name: submit_analysis
description: 提交分析发现，结束分析阶段。调用前请确保已覆盖用户关心的方向。
parameters:
  findings: [{
    title: string,            — 发现标题
    detail: string,           — 详细描述
    evidence_columns: [string], — 引用的列名
    confidence: "high"|"medium"|"low"  — 枚举，三选一
  }]
  method_used: [string]       — 实际使用的分析方法列表
  summary: string             — 一句话总结
handler: 结束循环，返回 findings 给 Orchestrator
```

【自检】LLM 能自己判断分析够了、该提交了吗？能——它根据用户反馈和探索深度决定。

## 5. 知识库注入

同 Scout 模式，build_prompt 时注入：

1. **跨项目知识库**：`knowledge.yaml` 中相似数据的历史分析记录
2. **本项目记忆**：上游阶段上下文（Scout 字段语义 + Cleaner 清洗策略）

注入格式：

```
【知识库参考 — 历史分析经验，供参考而非决定】
- 类似数据曾使用「线性回归 + 季节性分解」分析收入趋势
- 字段 Inc1 在类似项目中被识别为收入指标

【本项目上下文】
（system_prefix 含上游阶段摘要 + 字段状态 + 用户原话）
```

## 6. ProjectContext 集成（律 1/2/3）

### 6.1 对话历史

每轮 LLM 调用的 messages：
```
system: [角色 + 工具定义 + 知识库 + upstream_summary + upstream_user_words]
messages_history: [当前 analyst 阶段的 user/assistant 对话]  # 律 3，对齐任务 M
user: [本轮用户输入或其上下文]
```

### 6.2 事件写入

| 事件 | 时序 | ProjectContext 写入 |
|------|------|-------------------|
| 每轮用户回复 | USER_INPUT_RECEIVED emit | add_user_feedback(stage="analyst", raw_text=...) |
| 每轮 LLM 响应 | 该轮工具执行后 | add_agent_response(stage="analyst", content=..., snapshot=derive_snapshot(context)) |
| 最终提交 | submit_analysis 触发时 | add_agent_response(stage="analyst", content=..., snapshot={findings: [...]}) — 最终快照 |

**关键**：
- 每轮都写，不是只写最后一条。确保重启/dump 能看到中间过程
- agent_response 在 user_feedback 之后写入（对齐任务 G）

### 6.3 下游继承

Reporter 通过 `project_ctx.build_prompt("reporter")` 自然继承 Analyst 的全部对话历史（messages_history + upstream_summary），无需单独传 findings。findings 作为 snapshot 结构额外传给 Reporter 的 system_prefix。

## 7. AnalystAgent 改造

```python
def run(self, df, context, memory_project=None):
    # 加载知识库
    # project_ctx = context.get("_project_context")
    # 拼 system prompt：角色 + 工具 + 知识库 + ctx_block["system_prefix"] + ctx_block["upstream_summary"]
    # messages = [system] + ctx_block["messages_history"] + [intro]
    # 
    # for _round in range(30):
    #   if _round >= 25: prompt 追加「请准备 submit_analysis」
    #   resp = self._llm.chat(messages, tools=TOOLS)
    #   
    #   for tool_call in resp.tool_calls:
    #     if submit_analysis: return findings
    #     if ask_user: 触发 _pause → 用户回复 → 追加到 messages
    #     if propose_method: 展示 + _pause → 用户回复
    #     if run_statistical_test: dispatch → 结果追加到 messages
    #     其他: 执行 → 结果追加
    #   
    #   if resp.text: 展示 + _pause → 用户回复 → 追加到 messages
```

## 8. Orchestrator 改造

```python
# 当前（删除）
plan = ...                    # 不再构建
results, metrics = analyst.run(df, context, plan)  # plan 参数删除
analyst_review_pause_payload(...)  # 删除
while True: 确认循环             # 删除

# 改后
findings = analyst.run(df, context, memory_project=memory_project)
# findings 存入 context → 直接进 Reporter
```

**plan 信息去向**：plan 承载的清洗规划信息通过 `upstream_summary`（Cleaner 阶段 add_agent_response 的 snapshot）传入 Analyst system_prefix。不新建单独通道。

## 9. 前端展示

| LLM 输出类型 | 前端渲染 |
|-------------|---------|
| 纯文本 | 对话气泡（复用 Scout 样式） |
| propose_method | 方法卡片：方法名 + 理由 + 前提 |
| ask_user | 问题卡片，options 渲染为可点击按钮 |
| submit_analysis | findings 列表卡片 + 方法清单 |
| run_statistical_test 结果 | 统计结果卡片（表格/数值） |

### 前端任务
- 复用 Scout 对话气泡组件
- 新增 `MethodProposal` / `AskUser` / `FindingsList` 三个卡片组件
- 旧 Analyst 表格组件暂时保留（兼容旧数据），新路径用对话渲染

## 10. Reporter 适配

Reporter 当前接收 `results / business_metrics`（计算数值）。新 findings 是 LLM 文字结论 + evidence_columns。

**适配方案**：新增 `findings` 参数（可选，兼容旧路径）。system prompt 追加：

```
【分析发现（来自 Analyst）】
{json.dumps(findings)}
```

Reporter 的 LLM 自己把 findings 融入报告叙事。不改 Reporter 核心代码结构，只改 prompt 拼装和参数传递。

## 11. 守门测试（§验收硬指标）

```python
# tests/test_product/test_analyst_dialogue.py

def test_analyst_submit_analysis_唯一退出():
    """Analyst 对话循环中，只有 LLM 调 submit_analysis 工具才退出。
    代码不响应任何关键词（含"可以了"）。"""
    # monkeypatch _llm → 第一轮纯文本"可以了"，第二轮调 submit_analysis
    # 断言：第一轮不退出，第二轮退出

def test_analyst_messages_history_注入():
    """Analyst LLM 调用的 messages 含 ProjectContext messages_history。"""
    # 构造 project_ctx 含 analyst 阶段 2 轮对话
    # spy create_raw_client 截 messages
    # 断言 messages 含锚点字符

def test_analyst_agent_response_写入时序():
    """agent_response 在 user_feedback 之后写入（对齐任务 G）。"""
    # 模拟一轮对话，检查 entries 顺序

def test_analyst_submit_analysis_findings_非空():
    """submit_analysis 返回的 findings 含至少 1 条带 evidence_columns 的发现。"""
    # 构造 LLM 调 submit_analysis，断言 findings 结构合规

**30 轮失败模式**：第 30 轮 prompt 追加「必须立即调 submit_analysis」。若 LLM 仍不提交，`raise AnalystOverRoundError`。Orchestrator 捕获后展示给用户：「分析超时，是否基于已有发现继续？」用户可选择继续/重跑/放弃。

def test_analyst_30轮上限():
    """第 30 轮后强制退出，不无限循环。"""
    # monkeypatch LLM 永远不调 submit_analysis
    # 断言 30 轮内 raise 或自动退出
```

## 12. 任务拆分（Tier 化）

| ID | 任务 | 范围 | 优先级 |
|----|------|------|--------|
| N | 新工具注册 | `agent_tool_defs.py` | Tier 1 |
| O | AnalystAgent.run 对话循环 | `analyst/agent.py` | Tier 1 |
| P | Orchestrator 删旧 Analyst 逻辑 | `orchestrator.py` | Tier 1 |
| Q | ProjectContext 集成 + 律 3 | `analyst/agent.py` + `orchestrator.py` | Tier 1 |
| R | Reporter prompt 适配 findings | `reporter/agent.py` | Tier 2 |
| S | 前端对话气泡 + 卡片 | `AnalyzePanel.tsx` | Tier 2 |
| T | 守门测试 | `test_analyst_dialogue.py` | Tier 1 |
| U | dump 验收 | 跑一次全流程用 dump 验证 | Tier 2 |

## 13. 自检总则

| 工具/决策点 | LLM 能自己判断吗？ | 答案 |
|------------|-----------------|------|
| 是否调 propose_method | 能，根据数据和目标 | ✅ |
| 选什么 test_type | 能，工具描述已列 | ✅ |
| 用 ask_user 还是纯文本 | 能，需要决策时用工具 | ✅ |
| 是否调 submit_analysis | 能，根据用户反馈 | ✅ |
| 代码是否替 LLM 做判断 | 否，只透传 | ✅ |
| 25 轮 prompt 追加 | 资源约束兜底（非通道，非规则） | LLM 仍可不调 submit_analysis |
