# HaGoKu Meta 层设计：HaGoKu Agent

> 状态：设计稿 v4 | 日期：2026-06-09 | 作者：用户 + AI

## v3→v4 changelog

| 变更 | 类型 |
|------|------|
| 标题从"Prompt Lab + HaGoKu Agent"改为"HaGoKu Agent" | 🔴 必改 |
| 架构翻转：Agent 为主，Prompt Lab 是它的工具/API | 🔴 必改 |
| 新增 § 定位：一段话定死"维修员 + 模拟器"主从关系 | 🆕 |
| 新增 § Meta Agent 自检回路：启动前对比 git HEAD diff | 🆕 |
| 新增 § 修复方案格式：结构化 schema（哪里坏/为什么/改哪行/预期效果） | 🆕 |
| 新增 § 成功度量：4 个指标 | 🆕 |
| 新增 § 替代方案对比：为什么不是 LangSmith/Langfuse | 🆕 |
| 新增 § dump 完整性自检 | 🆕 |
| 新增 § 成本估算 | 🆕 |
| 新增 § 维护者说明 | 🆕 |
| HaGoKu Agent 内部架构重写：run_scenario() 入口 + 内部多轮 loop | 🔴 必改 |
| 巡检/诊断/守门重命名为"三种工作场景"，按触发频率排列 | 🟢 建议 |
| Prompt Lab API：加 ?caller=agent|human 参数 | 🟡 应改 |
| 守门 CI：明确前 3 个月 soft gate | 🟡 应改 |
| 实施顺序：守门从 Phase 2 末尾提到 Phase 2a 最先 | 🔴 必改 |
| 实施顺序：Phase 1 拆分 5 个子阶段 + 扩展验收标准（≥10 次使用 + 4 指标采样） | 🔴 必改 |
| 新增 § 诊断提示词草案（Phase 1d） | 🆕 |
| 新增 § 守门软启动校准数据采集机制 | 🆕 |
| 不做什么：修复方案改为"agent 提议 + 用户确认 + 铁律 -1 正向执行" | 🔴 必改 |

---

## 来龙去脉

### 事件时间线

```
5/18  e12564a2  memory_notes 正常
5/29  de888098  Scout 系统提示词完整: knowledge_section + command_context + 中性指令
5/31  f4d4e763  删除 knowledge_section 和 command_context（"优化"式重构）
6/1   af0509e   把 used_in_analysis 指令从"判断并说明原因"改成"只选必需的"（"修 bug"式加结论）
6/3   cd3c2c3   进一步加固：要求 used_in_analysis=false 与 ignore 强行一致
6/7   fbbdcf8   CH-5: 拆分 orchestrator，scout_reply.py 诞生（迁移未引入新问题）
6/7   8512cb3   A-4: Analyst prompt.md 全文重写（256→181 行）
6/8   3b16f10   CL-4: Cleaner prompt.md 全文重写（36→64 行，"推理链路"被删）
6/8   fa30373   SK-FIX-0: 新增 test_scout_prompt_contains_ignore_role_instruction（关键词测试）
6/9   bccdeca   删除 scout_reply 中重判 used_in_analysis 的指令
6/9   fb488c3   把 hint 从"逐字段判断"改成"禁止重判"
6/9   用户发现字段理解崩溃 + 清洗评估异常
6/9   定位根因 → 正向修复 Scout + Cleaner → 立铁律 10 → 标 xfail 违规测试
```

### 根因：三层累积破坏

**层 1：上下文被删**（5/31）：`knowledge_section` + `command_context` 从 Scout 系统提示词中消失。

**层 2：流程变结论**（6/1-6/3）：`used_in_analysis` 指令从"判断并说明原因"变成"只选直接必需的"。Cleaner prompt.md 36→64 行，删推理链路。

**层 3：纠正通道被切断**（6/9）：删除纠正时的重判指令，hint 改成"禁止重判"。被排除的字段永远回不来。

**共同特征**：每次改动都很小，每次测试都 GREEN，每次冒烟都通过，没人在改完后开 dump 看 LLM 实际输出。

### 为什么测试没拦住

`assert "ignore" in prompt` 是范畴错误——用关键词匹配验证 LLM 行为。GREEN ≠ 正确，RED ≠ 错误。完全没有信号价值，却有极强的负信号：驱使开发者污染提示词来让测试变绿。

### 为什么现有防线全部失效

| 防线 | 为什么没拦住 |
|------|------------|
| 铁律 3（三组测试） | 验证代码行为，不验证 LLM 行为 |
| 冒烟测试 | 只验证不 crash。全选→GREEN，全排除→GREEN |
| 人工 review | diff 看起来像"优化表述"，没 dump 看不出问题 |

### 破坏提示词的三种典型路径

| 路径 | 表现 | 本次案例 |
|------|------|---------|
| "优化"式破坏 | 觉得多余、重复 → 删掉 | 删 `knowledge_section` + `command_context` |
| "修 bug"式破坏 | 行为异常 → 加限制 → 走向另一个极端 | "只选必需的" → 全部排除 |
| "重构"式破坏 | 拆分/重写时顺手删 | Cleaner prompt.md 36→64 行 |

### 解决方案：制度 + 工具

**制度层**：铁律 10 + 三道刹车（已写入 CLAUDE.md）

| 刹车 | 机制 | 阻止什么 |
|------|------|---------|
| A: 禁止关键词测试 | 不准写 `assert "ignore" in prompt` | 去掉错误的验证手段 |
| B: dump 对比门禁 | 改 prompt 的 PR 必须附带 dump 对比 | 把"看 LLM 实际输出"从建议变为强制 |
| C: 冒烟不充分声明 | 冒烟 GREEN ≠ 可以合并 | 只管 crash，不管判断 |

刹车依赖人的自律——**工具让正确的做法变容易、错误的做法变难。**

**工具层**：HaGoKu Agent（即本文档的设计内容），包含 Prompt Lab 作为其核心工具。

---

## 定位

HaGoKu Agent 是 HaGoKu 系统的**维修员**。Prompt Lab 是它的**模拟器工具**。

主从关系不可颠倒：

```
HaGoKu Agent（维修员）
  │
  ├── 故障处理：用户报错 → 调 Prompt Lab 回放 dump → 定位退化点 → 输出修复方案 → 用户确认 → 执行
  ├── 日常保养：定期读取 dump 历史 → 分析异常模式 → 生成巡检报告 → 在用户发现之前预警
  └── 定期检查：PR 改 prompt → 自动对比改前/改后输出 → diff 报告 → 3 个月内 soft gate

Prompt Lab（模拟器）
  ├── 被 HaGoKu Agent 调用：POST /api/prompt-lab/run?caller=agent
  └── 被开发者调用：POST /api/prompt-lab/run?caller=human（侧边栏手动操作）
```

**一句话定死**：HaGoKu Agent 是维修员。Prompt Lab 是它手里的模拟器——维修员用它验证故障、测试修复方案。开发者也可以直接拿模拟器研究提示词语义。但维修员才是 Meta 层的主角。

---

## 设计思路

### 为什么是 Meta 层

HaGoKu 的核心是数据处理 pipeline（Scout → Cleaner → Analyst → Reporter）。Meta 层做的事完全不同：**维护这个系统本身**。

```
数据层：分析用户上传的 CSV → HAGOKYU_LLM_MODEL / _DEEP / _QUICK
Meta 层：分析系统自身的 LLM 行为 → HAGOKYU_LLM_MODEL_META（独立配置）
```

为什么分层：故障隔离（pipeline 崩了 meta 还能诊断）、不同能力需求（强推理 vs 快响应）、独立计费。

### 为什么 HaGoKu Agent 需要独立 LLM

诊断逻辑是比较同一段输入在两版 prompt 下的输出差异。如果和 pipeline 共用模型：LLM 升级→误报退化，崩了→无法诊断，有偏见→无法识别。独立模型 = 独立视角。

### 为什么是侧边栏

HaGoKu Agent 需要访问 dump 历史（同机）和 Prompt Lab API。侧边栏触手可及，不需要独立应用。

---

## 架构

```
┌──────────────────────────────────────────────────────────────┐
│                       HaGoKu Meta 层                          │
│                                                               │
│  ┌──────────────────────────────────────────────────────────┐ │
│  │               🤖 HaGoKu Agent（维修员）                    │ │
│  │                                                          │ │
│  │  【自检回路】启动前对比 git HEAD diff                     │ │
│  │     → 发现自己 prompt 被改过 → 暂停让用户确认              │ │
│  │                                                          │ │
│  │  run_scenario("inspect" | "diagnose" | "gate")           │ │
│  │     → 内部多轮 loop（读 dump → 调 Prompt Lab → 对比 →    │ │
│  │        输出报告/修复方案）                                 │ │
│  └──────────┬───────────────────────────────────────────────┘ │
│             │                                                 │
│             │  POST /api/prompt-lab/*?caller=agent            │
│             ▼                                                 │
│  ┌──────────────────────────────────────────────────────────┐ │
│  │               🧪 Prompt Lab（模拟器）                      │ │
│  │                                                          │ │
│  │  POST /run?caller=agent|human   调 LLM                   │ │
│  │  GET  /prompt?agent=X           取 prompt.md              │ │
│  │  GET  /dumps                    列 dump 列表              │ │
│  │  GET  /dumps/:name              取单个 dump               │ │
│  │  POST /compare                  改前/改后对比              │ │
│  │                                                          │ │
│  │  被调用方（Agent + 开发者双方）                            │ │
│  └──────────────────────────────────────────────────────────┘ │
│                                                               │
│  ┌──────────────────────────────────────────────────────────┐ │
│  │              后端 API: /api/meta/*                        │ │
│  │  POST /run         触发 run_scenario()，返回报告          │ │
│  └──────────────────────────────────────────────────────────┘ │
│                                                               │
│  独立 LLM: HAGOKYU_LLM_MODEL_META                              │
│    未设置 → 回退 + warning（不推荐）                            │
└──────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────┐
│                       HaGoKu 数据层                           │
│  Scout → Cleaner → Analyst → Reporter                         │
│     HAGOKYU_LLM_MODEL / _DEEP / _QUICK                        │
└──────────────────────────────────────────────────────────────┘
```

---

## Meta Agent 自检回路

Phase 1 必做。Meta Agent 是维修员——如果维修员自己的工具坏了，它就不能修别人。

### 实现

```python
# hagoku/agents/meta/agent.py

def _self_check(self) -> bool:
    """启动前自检：Meta Agent 自身 prompt.md 是否被改动过。"""
    import subprocess

    # 检查当前工作区是否有未提交的 prompt.md 修改
    result = subprocess.run(
        ["git", "diff", "HEAD", "--", "hagoku/agents/meta/prompt.md"],
        capture_output=True, text=True
    )
    if result.stdout.strip():
        # 有改动 → 暂停，让用户确认
        return False  # 调用方应 emit USER_INPUT_REQUESTED
    return True
```

### 界面行为

Meta Agent 面板首次打开时运行自检：
- ✅ 通过 → 正常显示面板
- ⚠️ 未通过 → 面板显示："⚠️ Meta Agent 自身的提示词已被修改。维修员需要经过验证的提示词才能准确诊断其他 Agent。请确认是否继续使用当前版本。[继续] [回退到 git HEAD]"

### 为什么不直接拒绝

如果拒绝启动，用户改了 Meta Agent 的 prompt 后无法验证改动是否正确——形成死锁。暂停确认即可。

---

## 基础数据：Dump 文件格式

### JSON 结构

```json
{
  "seq": 3,
  "stage": "scout_infer_all_semantics",
  "model": "deepseek-v4-pro",
  "timestamp": "2026-06-09T17:30:51.234567",
  "run_id": "run_20260609_173045",
  "messages": [
    {"role": "system", "content": "..."},
    {"role": "user", "content": "..."}
  ],
  "extra": {
    "query": "分析收入趋势",
    "tools": ["submit_field_inference"],
    "response_tool_calls": [{...}],
    "response_content": "{...}",
    "tokens": 1234,
    "duration_ms": 850
  }
}
```

| 字段 | 用途 |
|------|------|
| `messages` | Prompt Lab 提取 system/user message |
| `extra.response_tool_calls` | 对比模式核心——比对新旧 tool_calls |
| `extra.tokens` / `duration_ms` | 巡检追踪性能趋势 |
| `stage` | 巡检分组统计 |

### 现有 dump 覆盖

| Agent | dump stage | 包含内容 |
|-------|-----------|---------|
| Scout | `scout_infer_all_semantics` / `_response` | 初始字段推断 |
| Scout | `scout_reply_review` / `_response` | 用户纠正字段 |
| Cleaner | `cleaner_run_step` / `_response` | 对话式清洗 |
| Cleaner | `cleaner_dialogue` / `assess_response` | 首次评估 |
| Cleaner | `cleaner_planning` / `_response` | 自动规划清洗 |
| Analyst | `analyst_run_step` / `_response` | 对话式分析 |
| Reporter | `reporter_run_step` / `_response` | 报告生成 |

### dump 完整性自检

巡检时如果发现某些 agent 的 dump 缺失（如只有 `scout_infer_all_semantics` 但没有对应的 `_response`），说明 dump 链路不完整——标记为结构性异常，提示用户检查 `dump_messages()` 调用点。

---

## 一、HaGoKu Agent

### 内部架构

```
MetaAgent(BaseAgent)
├── role = "meta"
│
├── _self_check() → bool
│    启动前对比 git diff HEAD -- hagoku/agents/meta/prompt.md
│
├── run_scenario(scenario: str, params: dict) → MetaReport
│    统一入口。scenario ∈ {"inspect", "diagnose", "gate"}
│    内部多轮 loop：读 dump → 调 Prompt Lab API → meta LLM 分析 → 输出
│
├── _run_inspect(dumps: list[dict]) → InspectionReport
│    日常保养：读 dump 历史 → meta LLM 找异常模式
│
├── _run_diagnose(stage: str, since: str) → DiagnosisReport
│    故障处理：逐 dump 回放对比 → 定位退化点 → 关联 git commit
│       → 输出修复方案（FixPlan schema）
│
└── _run_gate(baseline: dict, current: dict) → GateReport
      定期检查：PR 改 prompt → 对比改前/改后 → diff 报告
```

`run_scenario()` 内部的统一 loop：

```python
def run_scenario(self, scenario: str, params: dict) -> dict:
    if not self._self_check():
        return {"status": "blocked", "reason": "self_check_failed"}

    if scenario == "inspect":
        return self._run_inspect(params.get("dump_dir"), params.get("limit", 50))
    elif scenario == "diagnose":
        return self._run_diagnose(params["stage"], params["since"])
    elif scenario == "gate":
        return self._run_gate(params["baseline"], params["current"])
```

### 三种工作场景

按触发频率从高到低排列，而非并列模式：

**工作场景 1：日常保养（inspect）** — 频率最高，主动预防

定期读取 dump 历史 → meta LLM 分析异常模式 → 生成巡检报告。

```
🤖 HaGoKu Agent 巡检报告 — 2026-06-09 19:45

⚠️ 发现 2 个异常：

1. [中] Cleaner 连续 3 次未调用 submit_assessment
   涉及 dump: 012, 014, 015
   建议：检查 prompt.md 中「数据够了就提交」指令是否存在

2. [低] Scout used_in_analysis 全 true 频率上升
   6/7 前: 12%, 6/8 后: 45%
   建议：检查 agent.py system_prompt 是否包含过度保守的指令
```

**工作场景 2：定期检查（gate）** — 频率中，CI 触发

PR 改 prompt → 自动调 Prompt Lab API 对比改前/改后输出 → diff 报告。

**前 3 个月 soft gate**：只报告不阻断。积累一个月数据后校准阈值，再升级为 hard gate。

**工作场景 3：故障处理（diagnose）** — 频率低，用户主动触发

用户报错 → 调 Prompt Lab API 逐 dump 回放对比 → 定位退化点 → 输出修复方案。

### 修复方案格式（DiagnosisReport.fix_plan）

HaGoKu Agent 的故障处理场景下，诊断报告必须包含结构化修复方案——这是它的一等输出，不是建议。

```python
@dataclass
class FixPlan:
    """HaGoKu Agent 故障处理后输出的修复方案"""
    what_broke: str          # 哪里坏了："Scout 字段理解中 Quantity 被错误排除"
    why: str                 # 为什么："提示词中'只选直接必需的'导致 LLM 过度保守"
    which_line: str          # 改哪行："hagoku/agents/scout/agent.py:558"
    from_text: str           # 当前文本
    to_text: str             # 建议改成什么
    expected_effect: str     # 预期效果："Quantity 恢复参与分析，StroeID 保持排除"
    confidence: str          # "high" | "medium" | "low"
    evidence_dumps: list[str]  # 支撑证据的 dump 文件名
```

### 系统提示词

Phase 2 先用纯 system prompt 拼接（`api/meta.py` 中硬编码），验证效果后 Phase 3 提取为 `prompt.md`。

#### 巡检提示词（inspect）

巡检是统计归纳任务——读 50 条 dump 摘要，找异常模式。提示词相对简单，可以在 `_run_inspect()` 中硬编码。

#### 诊断提示词（diagnose）—— 需要独立设计

诊断是嵌套在"维修员"里的"调查员"人格。它和巡检完全不同——巡检是归纳（找模式），诊断是推理（找因果链）。这个提示词本身也是受铁律 10 保护的对象，**必须在 Phase 1d 同步起草，不能放到 Phase 2c 才写**。

```
你是 HaGoKu 系统的诊断专家。你的任务是：
当用户报告某个 Agent 行为异常时，逐条回放 dump 记录，
精确定位行为变化的时间点，关联 git commit，
输出修复方案。

诊断流程：
1. 接收用户报告（如"Scout 字段理解崩溃"）
2. 拉取指定 Agent 的最近 N 条 dump
3. 按时间顺序逐条回放：
   - 调 POST /api/prompt-lab/run?caller=agent
   - 比较每条 dump 的 response_tool_calls
4. 定位行为变化点：输出"dump X → dump Y 之间行为发生变化"
5. 关联 git log：查找变化时间点附近的 commit
6. 输出 FixPlan：
   - what_broke: 描述行为变化
   - why: 推断根因
   - which_line: 指出可疑代码行
   - from_text / to_text: 建议修改
   - expected_effect: 预期修复效果
   - confidence: 置信度
   - evidence_dumps: 支撑证据的 dump 文件名列表

约束：
- 只报告，不执行修改（铁律 -2）
- 置信度为 "low" 时必须明确标注，不得隐瞒不确定性
- 如果无法确定根因，输出"需要人工介入"而非猜测
```

**这个 prompt.md 的设计时机**：Phase 1d（Prompt Lab 后端完成后），在开始 Phase 2 之前。起草时用 Prompt Lab 手动验证——用历史上真实的退化案例（如本次 Scout 崩溃的 dump 序列）测试诊断提示词能否正确定位根因。

### 工具定义

```
tools:
  - inspect_dumps      读取 dump 目录，返回每条 dump 的摘要
  - diagnose_regression  输入两段 dump 组，对比差异，输出退化判断
  - list_dump_summaries  按 agent/stage 分组统计
```

### 改动清单

| 组件 | 行数 |
|------|------|
| `hagoku/config.py` — `model_meta` 配置 | +3 |
| `hagoku/agents/meta/agent.py` — MetaAgent(BaseAgent) + 自检回路 | ~350 |
| `hagoku/api/server.py` — 注册 `/api/meta/*` 路由 | +5 |
| `hagoku/api/meta.py` — `run_scenario()` 端点 | ~150 |
| `hagoku_web/src/panels/MetaAgentPanel.tsx` | ~250 |
| `hagoku_web/src/App.tsx` — 导航项 | +3 |
| `scripts/ci/prompt_gate.py` — CI 守门脚本 | ~100 |

---

## 二、Prompt Lab（HaGoKu Agent 的模拟器工具）

### 定位

Prompt Lab 是 HaGoKu Agent 的核心工具，也是一个独立的侧边栏面板。**HaGoKu Agent 调用它时走 `?caller=agent`，开发者手动操作时走 `?caller=human`。**

两种调用方的差异：

| 维度 | `?caller=agent` | `?caller=human` |
|------|----------------|-----------------|
| 触发方式 | HaGoKu Agent 内部 loop | 用户点侧边栏「运行」 |
| 超时 | 60s（可重试） | 30s |
| 重试 | 自动 3 次 | 手动点击重试 |
| 输出格式 | JSON（机器可读） | JSON + 前端渲染 |

### 组件树

```
PromptLabPanel
├── InputSourceSelector     # Dump / 当前上下文 / 手写
├── AgentSelector           # Scout / Cleaner / Analyst / Reporter
├── PromptEditor            # Ctrl+Enter 运行
├── ActionBar               # [▶ 运行] [📋 对比原版] [⬇ 导出]
├── ResultPanel             # tool_calls / content / tokens
└── ComparePanel            # 并排对比 + diff 高亮
```

### API（关键端点，加 caller 参数）

**`POST /api/prompt-lab/run?caller=agent|human`**

```
Request:  { "model":"auto", "messages":[...], "tools":"auto", "agent":"scout" }
Response: { "content":"...", "tool_calls":[...], "tokens":{...}, "duration_ms":850 }
```

**`POST /api/prompt-lab/compare?caller=agent|human`**

```
Request:  { "baseline":{...}, "current":{...}, "agent":"scout" }
Response: { "baseline":{...}, "current":{...}, "diff":{...} }
```

Diff 算法：按 tool_call 名称对齐 → 逐 arguments JSON 路径比较 → 返回变化路径列表 + 文本相似度。

### 改动清单

| 层 | 文件 | 行数 |
|---|------|------|
| 前端 store | `workspace.ts` + `promptLab.ts`（新建） | +61 |
| 前端面板 | `PromptLabPanel.tsx` + 子组件（新建） | ~450 |
| 前端 API | `api/promptLab.ts`（新建） | ~40 |
| 后端路由 | `api/server.py` | +6 |
| 后端逻辑 | `api/prompt_lab.py`（新建） | ~120 |
| 后端辅助 | `observability/llm_dump.py` — `list_dumps()` | +25 |

---

## 实施顺序

```
Phase 1a: Prompt Lab 后端 API（/api/prompt-lab/*） + ?caller 参数
Phase 1b: Prompt Lab 前端面板
Phase 1c: 自检回路（Meta Agent _self_check 框架）
Phase 1d: 诊断提示词起草（用 Prompt Lab 手动验证）
Phase 1e: 基线数据采集启动

Phase 2a: 守门（最先做）
  ├── CI 脚本 prompt_gate.py
  ├── /api/meta/run?scenario=gate
  └── 前 3 个月 soft gate

Phase 2b: 巡检
  ├── MetaAgent._run_inspect()
  └── MetaAgentPanel 巡检触发 + 报告展示

Phase 2c: 诊断
  ├── MetaAgent._run_diagnose()
  └── 修复方案（FixPlan schema）
```

### Phase 1 扩展验收标准

Phase 1 不只是"Prompt Lab 能用"。必须达到以下条件才能进入 Phase 2：

1. Prompt Lab 功能完整（API + 前端面板 + 三种输入源模式）
2. **已积累 ≥ 10 次真实使用记录**（包括手动跑 + 对比模式）
3. **成功度量 4 指标首次采样完成**（反馈延迟 / 回归检出率 / 误报率 / 人工 dump 审查频率）
4. 诊断提示词草案已通过 Prompt Lab 手动验证（用历史退化案例测试）

### 守门软启动期间的校准数据采集

前 3 个月 soft gate 期间，**必须并行维护一份校准日志**，否则 3 个月后 gate 无数据可校准：

```
~/.hagoku/gate_calibration.jsonl

每行一条记录：
{"date":"2026-07-01","commit":"abc123","agent":"scout","prompt_diff":"...",
 "baseline_dump":"005_scout_...","current_dump":"N/A (Prompt Lab)",
 "tool_calls_changed":true,"changed_fields":["columns[3].used_in_analysis"],
 "human_review":"接受——Quantity 确实应该排除","accepted":true}
```

**数据来源**：
- 每次 PR 改 prompt → 守门 CI 自动跑 → 结果写入校准日志
- 每次开发者手动用 Prompt Lab 对比 → 如果用户判断"接受"或"拒绝"→ 手动追加一行
- 每次实际退化被事后发现 → 手工补录，标记 `detected_by_human: true`

3 个月后的校准动作：统计 `tool_calls_changed=true` 且 `accepted=false` 的比例 → 这就是真实退化率。用这个数据调阈值，将 soft gate 升级为 hard gate。

---

## 成功度量

Phase 1 上线后即开始追踪。基线值需要 Phase 1 用 1-2 个月的自然使用积累。

| 指标 | 定义 | Phase 1 目标（基线采集） | Phase 2a+ 目标 |
|------|------|----------------------|--------------|
| 反馈延迟 | 从改一句 prompt 到看到 LLM 输出 | 建立基线：记录每次 Prompt Lab 运行的耗时 | < 30 秒 |
| 回归检出率 | 守门 CI 拦截的退化 / 实际发生的退化 | 采集 ≥ 10 次校准日志记录 | > 80% |
| 误报率 | 守门 CI 报退化但实际无退化 | 采集 ≥ 10 次校准日志记录 | < 20% |
| 人工 dump 审查频率 | 开发者每周手动开 dump 看的次数 | 建立基线：Phase 1 前采样 1 次，Phase 1 结束后采样 1 次 | 希望提高 |

**Phase 1 验收时**，"Prompt Lab 能用"之外还必须确认"4 指标首次采样完成 + 已积累 ≥ 10 次真实使用记录"。没有这两项数据，Phase 2 的阈值校准和守门升级都缺乏依据。

---

## 成本估算（Phase 2）

| 模型选择 | 单次巡检 token | 月度费用估算 |
|---------|-------------|------------|
| 本地模型（Meta LLM = 35B Q4） | ~8K tokens（读 50 条 dump 摘要） | ~$0（本地） |
| 云端模型（如 deepseek-v4） | ~8K tokens | ~$0.05/次，月 $1-3 |

建议 Meta LLM 优先本地——诊断低频，不需要快，本地 35B 足够。

---

## 不做什么

- **不做自动修复**：修复方案由 Agent **提议** → 用户确认 → 铁律 -1 正向执行（不回滚，手工修改指定行）
- 不做 A/B 测试平台
- 不做线上监控报警

## 替代方案

**为什么不是 LangSmith / Langfuse？**
- 它们是外部 SaaS，需要上传 dump 数据到云端——安全风险（用户 CSV 数据可能包含敏感信息）
- 它们是通用 LLM 可观测性平台，不感知 HaGoKu 的 Agent 结构（stage、tool_calls 语义）
- 本地 dump 目录 + Prompt Lab 是零依赖方案，完全离线可用

## 维护者说明

| 项目 | 负责人 |
|------|-------|
| Meta Agent prompt.md | 用户 final review（铁律 10 适用） |
| 守门 CI 阈值（20%/0.8） | 积累一个月数据后用户校准 |
| 巡检报告严重级别定义 | 用户定义（高/中/低） |

## 开放问题

1. **HaGoKu Agent prompt.md？** Phase 2 先用硬编码，Phase 3 提取为 prompt.md。

2. **巡检触发方式？** Phase 2b 手动触发，Phase 3 自动 + 定时。

3. **`HAGOKYU_LLM_MODEL_META` 未设置？** 记录 warning + 回退。warning："建议配置独立模型以保证故障隔离。"

4. **对比 diff 阈值？** tool_calls 变化 > 20%、content 相似度 < 0.8。前 3 个月 soft gate，积累数据后校准。

5. **巡检历史持久化？** `~/.hagoku/inspections/inspection_{timestamp}.json`。

6. **修复方案可否直接执行？** 不可——铁律 -2。Agent 提议 + 用户确认 + 铁律 -1 正向执行。
