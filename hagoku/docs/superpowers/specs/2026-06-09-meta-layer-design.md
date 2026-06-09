# HaGoKu Meta 层设计：Prompt Lab + HaGoKu Agent

> 状态：设计稿 v3 | 日期：2026-06-09 | 作者：用户 + AI

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

不是某一个 commit 的锅——是三个独立改动逐层叠加，每一层都让情况更糟。

**层 1：上下文被删**（5/31 `f4d4e763`）

`knowledge_section`（跨项目知识库参考）和 `command_context`（用户最近指令/纠正）从 Scout 系统提示词中消失。LLM 看不到历史经验和用户纠正——但当时行为还没明显退化，因为提示词本身的指令仍然是中性的。

**层 2：流程变结论**（6/1 `af0509e` + 6/3 `cd3c2c3`）

`used_in_analysis` 指令从"判断每个字段是否参与，说明原因"变成"只勾选直接回答分析目标必需的字段"。这是一个**结论性指令**——代码替 LLM 预设了"应该只选必需的"这个判断方向。LLM 变得过度保守，大量字段被排除。

同时 Cleaner 的 `prompt.md` 从 36 行重写为 64 行（6/8 `3b16f10`），删掉了【推理链路】（分析目标 → 字段含义 → 数据分布 → 极端值是业务规律还是错误 → 是否需要清洗 → 用什么策略）和关键指令（"不要在看完数据后继续探索、不要重复调用同一个工具。数据够了就提交。"）。

**层 3：纠正通道被切断**（6/9 `bccdeca` + `fb488c3`）

用户纠正字段名后，LLM 原本会重新判断 `used_in_analysis`。这两个 commit 先删除了重判指令，再把 hint 改成"禁止重判"。被层 2 排除的字段永远回不来——用户纠正变成无效操作。

**共同特征**：每次改动都很小（删几行、改一句话），每次改动后测试都 GREEN，冒烟都通过，没有人在改完后开 dump 看 LLM 实际输出。

### 为什么测试没拦住

`test_scout_prompt_contains_ignore_role_instruction` 诞生于层 2。它验证"提示词是否含 ignore 关键词"——这正是层 2 污染提示词的**工具**。

```
测试框架对代码正确性验证非常强
     ↓
有人把同一套方法论套到提示词上
     ↓
assert "ignore" in prompt 诞生
     ↓
"prompt 缺 ignore → 加一句 → 测试 GREEN ✅"
     ↓
LLM 行为退化，但测试 GREEN，无人复查
     ↓
上线 → 用户发现崩溃
```

**范畴错误**：用关键词匹配验证 LLM 行为。这类测试完全没有信号价值（GREEN ≠ 正确，RED ≠ 错误），却有极强的负信号——它驱使开发者污染提示词来让测试变绿。

### 为什么现有防线全部失效

| 防线 | 为什么没拦住 |
|------|------------|
| 铁律 3（三组测试） | 验证代码行为（有无硬编码、通道是否完整），不验证 LLM 行为 |
| 冒烟测试 | 只验证流程是否 crash。全选→GREEN，全排除→GREEN，乱洗→GREEN |
| 人工 review | 提示词 diff 看起来像正常的"优化表述"，没有 dump 对比看不出问题 |

### 破坏提示词的三种典型路径

| 路径 | 表现 | 本次案例 |
|------|------|---------|
| **"优化"式破坏** | 觉得某段话多余、重复、不优雅 → 删掉 | 删 `knowledge_section` + `command_context` |
| **"修 bug"式破坏** | LLM 行为异常（全选）→ 加限制性指令 → 行为走向另一个极端 | "只选必需的" → 全部排除 |
| **"重构"式破坏** | 代码拆分/重写时顺手删掉看起来不重要的内容 | Cleaner prompt.md 36→64 行，删推理链路 |

### 解决方案：制度 + 工具

**制度层**：铁律 10 + 三道刹车（已写入 CLAUDE.md）

| 刹车 | 机制 | 阻止什么 |
|------|------|---------|
| A: 禁止关键词测试 | 不准写 `assert "ignore" in prompt` | 去掉错误的验证手段 |
| B: dump 对比门禁 | 改 prompt 的 PR 必须附带 dump 对比 | 把"看 LLM 实际输出"从建议变为强制 |
| C: 冒烟不充分声明 | 冒烟 GREEN ≠ 可以合并 | 明确边界——只管 crash，不管判断 |

- A 是**事前刹车**：不让你写那种测试，就不会被误导
- B 是**事中刹车**：PR 没 dump 对比直接拒
- C 是**事后刹车**：冒烟 GREEN 不够，必须额外人工看 dump

刹车依赖人的自律——但人有惰性。**工具让正确的做法变容易、错误的做法变难。**

**工具层**：Meta 层 = Prompt Lab + HaGoKu Agent（即本文档的设计内容）

### 正向修复原则

铁律 -1："只做正向修复，不做回滚"。本次修复正是这个原则的实践：
- 不回滚 commit，而是把正确的提示词从历史版本**抄回来**
- 不是简单 revert，而是理解旧版为什么对、新版为什么错之后，手工恢复正确的部分
- 同时修正旧版的已知问题：旧版 hint "对照分析目标判断是否直接相关"太模糊 → 新版"逐字段重判，只判断当前字段"

---

## 设计思路

### 为什么是 Meta 层

HaGoKu 的核心是数据处理 pipeline（Scout → Cleaner → Analyst → Reporter）。四个 Agent 做的是理解数据、清洗数据、分析数据、生成报告。

Meta 层做的是完全不同的事：**维护这个系统本身**。

```
数据层：分析用户上传的 CSV
  用的 LLM：HAGOKYU_LLM_MODEL / _DEEP / _QUICK

Meta 层：分析系统自身的 LLM 行为
  用的 LLM：HAGOKYU_LLM_MODEL_META（独立配置）
```

为什么分层：
- **故障隔离**：pipeline 的 LLM 崩了，meta 层还能读 dump 定位问题
- **不同能力需求**：meta 层需要强推理（对比两版输出差异、判断是否退化），不需要快
- **独立计费**：meta 调用低频但单次 token 大（读整份 dump），走独立预算

### 为什么 Prompt Lab 是第一个

铁律 10 说"改提示词必须开 dump 人工看"。现在的人工流程：
1. 改 prompt → 2. 跑完整 pipeline（2-5 分钟，5-20 次 LLM 调用）→ 3. 翻 dump 文件 → 4. 人工读 JSON

Prompt Lab 把它变成：
1. 改 prompt → 2. 侧边栏点「运行」（5-15 秒，1 次 LLM 调用）→ 3. 立刻看到 tool_calls

**降低验证成本 = 提高验证频率 = 减少退化上线。**

### 为什么 HaGoKu Agent 需要独立 LLM

HaGoKu Agent 的诊断逻辑：比较同一段输入在两版 prompt 下的输出差异，判断是否有退化。

如果和 pipeline 共用模型：
- Pipeline LLM 升级 → 所有输出都变了 → 误报退化
- Pipeline LLM 崩了 → HaGoKu Agent 也崩 → 无法诊断
- Pipeline LLM 有偏见 → 用同一模型诊断 → 无法识别这是偏见

独立模型 = 独立视角 = 能识别 pipeline 模型自身的系统性偏差。

### 为什么是侧边栏

Prompt Lab 的核心场景是"引用现有提示词"——从正在运行的分析中取上下文、从 Agent 的 prompt.md 取系统提示词。侧边栏触手可及，不用切换窗口。

HaGoKu Agent 需要访问 dump 历史（同机）和 Prompt Lab API。同样不该是独立应用。

---

## 架构

```
┌──────────────────────────────────────────────────────────────┐
│                       HaGoKu Meta 层                          │
│                                                               │
│  ┌─────────────────────────┐  ┌───────────────────────────┐  │
│  │ 🤖 HaGoKu Agent         │  │ 🧪 Prompt Lab             │  │
│  │ (MetaAgentPanel.tsx)    │  │ (PromptLabPanel.tsx)      │  │
│  │                         │  │                           │  │
│  │ 巡检: 读 dump 历史       │  │ 手动试 prompt             │  │
│  │   → meta LLM 分析        │  │ 选 dump → 改 prompt → 跑  │  │
│  │   → 生成巡检报告         │  │ 对比两版输出              │  │
│  │                         │  │                           │  │
│  │ 诊断: 用户报问题          │  │ 被 HaGoKu Agent API 调用  │  │
│  │   → 调 POST /api/       │  │   → POST /api/           │  │
│  │     prompt-lab/run      │  │     prompt-lab/run       │  │
│  │   → 逐 dump 回放对比     │  │                           │  │
│  │   → 生成诊断报告         │  │                           │  │
│  │                         │  │                           │  │
│  │ 守门: CI 触发            │  │                           │  │
│  │   → 调 Prompt Lab API   │  │                           │  │
│  │   → 对比改前/改后        │  │                           │  │
│  │   → diff 报告贴 PR       │  │                           │  │
│  └──────────┬──────────────┘  └───────────┬───────────────┘  │
│             │                             │                   │
│             ▼                             ▼                   │
│  ┌─────────────────────────────────────────────────────────┐  │
│  │              后端 API: /api/prompt-lab/*                 │  │
│  │                                                         │  │
│  │  POST /run             调 LLM（可指定 model/messages）    │  │
│  │  GET  /prompt?agent=X  取 Agent 的 prompt.md 原文         │  │
│  │  GET  /dumps           列 dump 目录文件列表                │  │
│  │  GET  /dumps/:name     取单个 dump 文件完整 JSON           │  │
│  │  POST /compare         并发跑两次，返回并排对比结果         │  │
│  └─────────────────────────────────────────────────────────┘  │
│                                                               │
│  ┌─────────────────────────────────────────────────────────┐  │
│  │              后端 API: /api/meta/*                       │  │
│  │                                                         │  │
│  │  POST /inspect         触发巡检，返回巡检报告              │  │
│  │  POST /diagnose        触发诊断，返回诊断报告              │  │
│  └─────────────────────────────────────────────────────────┘  │
│                                                               │
│  独立 LLM: HAGOKYU_LLM_MODEL_META                              │
│    未设置 → 回退 HAGOKYU_LLM_MODEL（不推荐）                    │
└──────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────┐
│                       HaGoKu 数据层                           │
│                                                               │
│  Scout → Cleaner → Analyst → Reporter                         │
│     HAGOKYU_LLM_MODEL / _DEEP / _QUICK                        │
└──────────────────────────────────────────────────────────────┘
```

---

## 基础数据：Dump 文件格式

所有 meta 层功能都依赖 dump 文件。理解其结构是后续设计的前提。

### 文件位置

- 运行期路径：`{run_dir}/llm_dumps/`（由 `Orchestrator.run()` 调用 `set_run_dir()` 设定）
- 回退路径：`~/.hagoku/llm_dumps/`（`set_run_dir` 从未调用时）
- 文件名格式：`{seq:03d}_{stage}_{timestamp}.json`
- 示例：`003_scout_infer_all_semantics_20260609_17305123456.json`

### JSON 结构

```json
{
  "seq": 3,
  "stage": "scout_infer_all_semantics",
  "model": "deepseek-v4-pro",
  "timestamp": "2026-06-09T17:30:51.234567",
  "run_id": "run_20260609_173045",
  "messages": [
    {"role": "system", "content": "直接调用 submit_field_inference..."},
    {"role": "user", "content": "请分析以下数据集的字段语义：\n```json\n{...}\n```"}
  ],
  "extra": {
    "query": "分析收入趋势",
    "tools": ["submit_field_inference"],
    "response_tool_calls": [
      {
        "name": "submit_field_inference",
        "arguments": "{\"columns\":[{\"name\":\"StoreID\",\"inferred_type\":\"id\",...}]}"
      }
    ],
    "response_content": "{\"columns\":[...]}",
    "tokens": 1234,
    "duration_ms": 850
  }
}
```

**关键字段**：

| 字段 | 用途 |
|------|------|
| `messages` | LLM 收到的完整输入。Prompt Lab 从这里提取 system/user message |
| `extra.response_tool_calls` | LLM 返回的工具调用。对比模式的核心——比对新旧两版的 tool_calls 差异 |
| `extra.response_content` | LLM 返回的文本内容（含 `<think>` 剥离后的正文） |
| `extra.tokens` / `extra.duration_ms` | 性能指标，巡检可追踪趋势 |
| `stage` | 标识哪个 Agent 的哪次调用。巡检用它分组统计 |

### 现有 dump 覆盖

每个 Agent 的关键调用点都通过 `dump_messages()` 记录了两条 dump（调用前 + 调用后）：

| Agent | dump stage | 包含内容 |
|-------|-----------|---------|
| Scout | `scout_infer_all_semantics` / `_response` | 初始字段推断的 prompt + LLM 输出 |
| Scout | `scout_reply_review` / `_response` | 用户纠正字段后的 prompt + LLM 输出 |
| Cleaner | `cleaner_run_step` / `_response` | 对话式清洗的每轮 LLM 调用 |
| Cleaner | `cleaner_dialogue` / `assess_response` | 首次评估的 prompt + LLM 输出 |
| Cleaner | `cleaner_planning` / `_response` | 自动规划清洗操作的 prompt + LLM 输出 |
| Analyst | `analyst_run_step` / `_response` | 对话式分析的每轮 LLM 调用 |
| Reporter | `reporter_run_step` / `_response` | 报告生成的每轮 LLM 调用 |

---

## 一、Prompt Lab

### 组件树

```
PromptLabPanel
├── InputSourceSelector     # 三个 tab: Dump / 当前上下文 / 手写
│   ├── DumpPicker          # 下拉列表 + 搜索 + 预览
│   ├── ContextPreview      # 只读展示当前分析上下文
│   └── ManualEditor        # 空白 textarea
├── AgentSelector           # Scout / Cleaner / Analyst / Reporter 下拉
├── PromptEditor            # 可编辑 textarea，monospace 字体
│   ├── ToolBar             # [从 prompt.md 加载] [清空] [格式化 JSON]
│   └── Editor              # Ctrl+Enter 触发运行
├── ModelDisplay            # 当前使用的模型名称（只读）
├── ActionBar               # [▶ 运行] [📋 对比原版] [⬇ 导出]
├── ResultPanel             # 可折叠的结果区
│   ├── TabBar              # [tool_calls] [原始 content] [tokens]
│   ├── ToolCallViewer      # 格式化的 JSON，语法高亮
│   ├── ContentViewer       # 纯文本
│   └── StatsRow            # tokens / 耗时 / 模型
└── ComparePanel            # 并排对比（对比模式时显示）
    ├── DiffHeader           # 改前 / 改后 标签 + 差异统计
    ├── LeftPane             # 原版结果
    └── RightPane            # 新版结果（差异高亮）
```

### 状态管理（Zustand store: `usePromptLabStore`）

```typescript
interface PromptLabState {
  // 输入源
  inputMode: 'dump' | 'context' | 'manual';
  selectedDumpFile: string | null;      // dump 文件名
  selectedAgent: 'scout' | 'cleaner' | 'analyst' | 'reporter';

  // 编辑区
  systemPrompt: string;                 // 可编辑的 system 消息
  userMessage: string;                  // 可编辑的 user 消息
  toolsMode: 'auto' | 'none' | 'custom';
  customTools: string;                  // 手写 tools JSON

  // 模型
  model: 'auto' | string;               // 'auto' = 用当前配置

  // 运行状态
  isRunning: boolean;
  lastResult: LabResult | null;
  lastError: string | null;

  // 对比模式
  isCompareMode: boolean;
  baselineResult: LabResult | null;     // 原版结果
  currentResult: LabResult | null;      // 新版结果

  // 历史（内存，不持久化）
  history: LabRun[];                    // 最近 20 次运行
}

interface LabResult {
  content: string;
  toolCalls: ToolCall[];
  tokens: { prompt: number; completion: number; total: number };
  durationMs: number;
  modelUsed: string;
  timestamp: string;
}

interface LabRun {
  id: string;
  systemPrompt: string;
  userMessage: string;
  agent: string;
  result: LabResult;
  timestamp: string;
}
```

### 输入源的三种模式的数据流

**模式 1：从 dump 选取**

```
用户选 dump 文件
  → GET /api/prompt-lab/dumps          （取文件列表，展示文件名 + stage + 时间戳）
  → GET /api/prompt-lab/dumps/{name}   （取完整 JSON）
  → 提取 messages[0].content           （system prompt → 填入编辑区）
  → 提取 messages[1].content           （user message → 填入编辑区，置灰可选编辑）
  → 提取 extra.response_tool_calls     （存为 baselineResult，供对比模式使用）
```

**模式 2：用当前上下文**

```
用户选 Agent
  → GET /api/prompt-lab/prompt?agent=scout   （取 prompt.md 原文 → 填入 system 编辑区）
  → 从 AnalysisPanel 当前状态取分析目标 + 字段上下文 → 自动构建 user message
```

user message 的自动构建逻辑（以后端 `POST /api/prompt-lab/context` 实现）：

```python
# 示例：Scout 的 user message 自动构建
query = context.get("query", "") or "未指定分析目标"
columns = [s["column_name"] for s in context.get("column_semantics", [])]
user_msg = f"分析目标：{query}\n可用列：{', '.join(columns)}\n数据行数：{context.get('n_rows', '?')}"
```

**模式 3：手写**

```
空白编辑区，用户自行粘贴 system + user message。
可以手动输入 tools JSON（当测试非标准工具时）。
```

### 后端 API 详细契约

#### `POST /api/prompt-lab/run`

```
Request:
{
  "model": "auto",                    // "auto" = 用 HaGoKuConfig.llm.model
  "messages": [
    {"role": "system", "content": "..."},
    {"role": "user", "content": "..."}
  ],
  "tools": "auto",                    // "auto" | "none" | [{"type":"function",...}]
  "agent": "scout",                   // "auto" 模式下从注册表拉 tools
  "temperature": null,                // null = 用 agent 默认值
  "max_tokens": null                  // null = 不限制
}

Response 200:
{
  "content": "LLM 文本响应（已剥离 <think>）",
  "tool_calls": [
    {"name": "submit_field_inference", "arguments": "{\"columns\":[...]}"}
  ],
  "tokens": {"prompt": 450, "completion": 180, "total": 630},
  "duration_ms": 850,
  "model_used": "auto → deepseek-v4-pro"
}

Response 422:
{
  "error": "invalid_request",
  "detail": "tools 参数格式错误：当 tools='custom' 时必须提供有效的 tools JSON"
}

Response 502:
{
  "error": "llm_unreachable",
  "detail": "LLM 不可达：Connection error. 请检查 API 配置。"
}
```

#### `POST /api/prompt-lab/compare`

```
Request:
{
  "model": "auto",
  "agent": "scout",
  "baseline": {                        // 原版（从 dump 提取）
    "system": "旧版 system prompt...",
    "user": "用户消息..."
  },
  "current": {                         // 新版（用户编辑的）
    "system": "新版 system prompt...",
    "user": "用户消息..."
  }
}

Response 200:
{
  "baseline": {                        // 原版结果
    "content": "...",
    "tool_calls": [...],
    "tokens": {...},
    "duration_ms": 800
  },
  "current": {                         // 新版结果
    "content": "...",
    "tool_calls": [...],
    "tokens": {...},
    "duration_ms": 820
  },
  "diff": {
    "tool_calls_changed": true,        // tool_calls 有差异
    "changed_fields": ["columns[2].used_in_analysis"],  // 变化的具体路径
    "content_similarity": 0.92         // content 文本相似度（0-1）
  }
}
```

**对比模式 diff 算法**（后端实现）：

```python
def _diff_tool_calls(baseline: list[dict], current: list[dict]) -> dict:
    """比较两版 tool_calls 的结构差异，返回变化路径列表。"""
    changed = []
    # 按函数名分组比较
    baseline_by_name = {tc["name"]: tc for tc in baseline}
    current_by_name = {tc["name"]: tc for tc in current}

    for name in set(baseline_by_name) | set(current_by_name):
        if name not in baseline_by_name:
            changed.append(f"新增 tool_call: {name}")
        elif name not in current_by_name:
            changed.append(f"删除 tool_call: {name}")
        else:
            # 比较 arguments 内部的 JSON 路径
            b_args = json.loads(baseline_by_name[name]["arguments"])
            c_args = json.loads(current_by_name[name]["arguments"])
            paths = _diff_json_paths(b_args, c_args, prefix=f"{name}.arguments")
            changed.extend(paths)

    # 文本相似度
    from difflib import SequenceMatcher
    similarity = SequenceMatcher(
        None,
        json.dumps(baseline, sort_keys=True),
        json.dumps(current, sort_keys=True)
    ).ratio()

    return {
        "tool_calls_changed": len(changed) > 0,
        "changed_fields": changed,
        "content_similarity": round(similarity, 4),
    }
```

#### `GET /api/prompt-lab/dumps`

```
Response 200:
{
  "dumps": [
    {
      "filename": "003_scout_infer_all_semantics_20260609_17305123456.json",
      "stage": "scout_infer_all_semantics",
      "timestamp": "2026-06-09T17:30:51",
      "model": "deepseek-v4-pro",
      "size_bytes": 4521
    },
    ...
  ],
  "total": 47,
  "directory": "~/.hagoku/llm_dumps/"
}
```

按 `timestamp` 降序排列，默认返回最近 50 条。支持 `?agent=scout&limit=20` 过滤。

#### `GET /api/prompt-lab/prompt?agent=scout`

```
Response 200:
{
  "agent": "scout",
  "prompt": "# Scout Agent — 数据侦察员\n\n## 角色\n\n你是**数据侦察员**...",
  "length": 3642,
  "path": "hagoku/agents/scout/prompt.md"
}
```

#### `POST /api/prompt-lab/context`

```
Request:
{
  "agent": "scout"
}

Response 200:
{
  "system": "<prompt.md 全文>",
  "user": "分析目标：分析收入趋势\n可用列：StoreID, Revenue, Quantity\n数据行数：5000",
  "context_available": true
}

Response 200 (无活跃分析):
{
  "system": "<prompt.md 全文>",
  "user": "",
  "context_available": false,
  "hint": "当前无活跃分析。可以手动输入 user message，或上传 CSV 后使用「用当前上下文」模式。"
}
```

### 前端交互细节

**运行流程**：
1. 用户点「▶ 运行」或 Ctrl+Enter
2. 按钮变 spinner + "运行中..."
3. `POST /api/prompt-lab/run`（超时 30s）
4. 成功 → ResultPanel 展开，显示 tool_calls + content + 统计
5. 失败 → toast 显示错误信息，ResultPanel 显示错误详情
6. 自动添加到 history（内存，不持久化）

**对比流程**：
1. 用户从 dump 选取输入源（必须有 baseline）
2. 编辑 system prompt
3. 点「📋 对比原版」
4. 并发两个请求：`POST /compare`（后端内部并发跑两次 LLM）
5. ComparePanel 并排展示，差异字段黄色高亮
6. 如果 tool_calls 无差异，显示 "✅ 两版输出一致"

**导出**：
- 点「⬇ 导出」→ 下载当前运行的完整结果 JSON（含 prompt + response）
- 格式与 dump 文件兼容，可直接放入 `llm_dumps/` 目录供 HaGoKu Agent 巡检

### 边缘情况

| 场景 | 处理 |
|------|------|
| dump 目录为空 | 显示"尚无 dump 文件。请先运行一次分析生成 dump，或使用「手写」模式。" |
| dump 文件 JSON 损坏 | 跳过该文件，列表中标记 ⚠️ |
| LLM 超时（>30s） | 显示"LLM 响应超时，请检查模型配置或网络。" + 重试按钮 |
| tools="auto" 但 agent 无注册工具 | 降级为 tools="none"，仅获取文本响应 |
| 对比时基线版 LLM 调用失败 | 显示"原版 LLM 不可达，无法完成对比。"——不阻塞新版结果展示 |
| 用户切换到其他面板再回来 | 状态保留（编辑区内容不丢失），结果区保持展开 |
| 长 prompt（>50KB） | 编辑区自动启用虚拟滚动，运行前显示 token 估算 |

### 安全考量

- `/api/prompt-lab/run` 无认证（本地工具，与主 API 同端口）
- 不记录 prompt 内容到日志（仅记录 stage + tokens）
- `model` 参数仅允许 `"auto"` 或当前配置中的模型名——不允许任意指定，防止滥用

### 改动清单

| 层 | 文件 | 改动 | 行数 |
|---|------|------|------|
| 前端 store | `src/stores/workspace.ts` | PanelId 加 `"prompt-lab"` | +1 |
| 前端 store | `src/stores/promptLab.ts`（新建） | Zustand store | ~60 |
| 前端导航 | `src/App.tsx` | 加导航项 + panel mapping | +5 |
| 前端面板 | `src/panels/PromptLabPanel.tsx`（新建） | 主面板 | ~250 |
| 前端面板 | `src/panels/PromptLabPanel/`（新建目录） | DumpPicker, PromptEditor, ResultPanel, ComparePanel | ~200 |
| 前端 API | `src/api/promptLab.ts`（新建） | fetch 封装 | ~40 |
| 后端路由 | `hagoku/api/server.py` | 注册 `/api/prompt-lab/*` | +6 |
| 后端逻辑 | `hagoku/api/prompt_lab.py`（新建） | 5 个端点 | ~120 |
| 后端辅助 | `hagoku/observability/llm_dump.py` | 加 `list_dumps()` 函数 | +25 |

**总计**：~700 行，4 个新文件，不碰 Pipeline / Orchestrator / kanban。

---

## 二、HaGoKu Agent

### 内部架构

```
MetaAgent(BaseAgent)
├── role = "meta"
├── _memory_yaml_key = "meta_inspections"
│
├── prompt: 从 prompt.md 加载（Meta Agent 专用系统提示词）
│
├── inspect(dump_dir: Path, llm_config: LLMConfig) → InspectionReport
│   ├── 1. 扫描 dump 目录，按 stage 分组
│   ├── 2. 提取每组的统计特征（tool_call 频率、token 趋势、文本相似度）
│   ├── 3. 调 meta LLM 分析统计特征 → 识别异常模式
│   └── 4. 返回结构化报告
│
├── diagnose(dump_dir: Path, target_agent: str, time_range: tuple) → DiagnosisReport
│   ├── 1. 筛选目标 Agent 的 dump
│   ├── 2. 逐对比较相邻 dump 的 tool_calls 差异
│   ├── 3. 调 Prompt Lab API 回放关键 dump（可选，如果原始响应丢失）
│   ├── 4. 关联 git log（git log --since --until -- **/agent.py **/prompt.md）
│   └── 5. 调 meta LLM 生成诊断报告
│
└── gate(baseline_dump: Path, new_prompt: str) → GateReport
    ├── 1. 调 POST /api/prompt-lab/run（用 baseline dump 的 user message + 新 prompt）
    ├── 2. 对比新旧 tool_calls
    ├── 3. 差异超阈值 → 报告
    └── 4. 返回 GateReport（含 diff + 建议）
```

### Meta Agent 的系统提示词（`hagoku/agents/meta/prompt.md` 设计）

```markdown
# Meta Agent — 系统诊断员

你是 HaGoKu 的**系统诊断员**。你不分析用户数据——你分析系统自身的 LLM 行为。

## 核心能力

你读取 `llm_dumps/` 目录中的 JSON 文件，每个文件记录了系统与 LLM 的一次交互：
- `messages`: 发送给 LLM 的完整 prompt
- `extra.response_tool_calls`: LLM 返回的工具调用
- `extra.tokens` / `extra.duration_ms`: 性能指标

你的任务是从这些记录中发现异常。

## 异常判定标准

### 结构性异常（不需要 LLM，代码直接检测）
- 连续 N 次 dump 中某 Agent 未调用任何 tool
- 连续 N 次 dump 中某 Agent 只调用了 route_to
- token 用量突然翻倍或减半

### 行为性异常（需要 LLM 语义理解）
- 工具调用模式变化：Scout 的 submit_field_inference 中 used_in_analysis 全 true 或全 false
- 响应质量下降：tool_calls 的 arguments 中出现大量空字段
- 阶段跳转异常：本该 stay 的 Agent 频繁 route_to 其他阶段

## 报告格式

巡检报告必须是结构化 JSON，包含：
- summary: 一句话概述
- anomalies: [{severity, agent, description, evidence, suggestion}]
- trend: {stage, metric, before, after, direction}
```

### 巡检功能的完整流程

```
用户点「开始巡检」（或 HaGoKu Agent 面板首次打开自动触发）

1. POST /api/meta/inspect
   ├── 后端调用 MetaAgent.inspect()
   ├── 扫描 ~/.hagoku/llm_dumps/ （或当前 run_dir/llm_dumps/）
   ├── 按 stage 分组统计：
   │   scout_infer_all_semantics: 15 次
   │   scout_reply_review: 8 次
   │   cleaner_run_step: 22 次
   │   ...
   ├── 提取特征：
   │   - 各 stage 的 tool_call 名称频率分布
   │   - used_in_analysis true/false 比例趋势
   │   - submit_assessment 调用率
   │   - token 用量趋势
   │   - 响应时间趋势
   ├── 调 meta LLM：发送统计摘要 → 识别异常模式
   └── 返回 InspectionReport JSON

2. 前端渲染巡检报告
   ├── 顶部：一句话概述
   ├── 异常列表：卡片式，每张含严重程度标签 + agent + 描述 + 建议
   ├── 趋势图（可选）：used_in_analysis 比例变化折线图
   └── 操作按钮：[查看详情] [导出 JSON] [标记已读]
```

**巡检报告的完整 JSON schema**：

```json
{
  "summary": "发现 2 个异常：Cleaner 提交率下降，Scout 字段排除率上升",
  "inspected_at": "2026-06-09T19:45:00",
  "dump_count": 47,
  "date_range": {"from": "2026-06-07", "to": "2026-06-09"},
  "anomalies": [
    {
      "id": "anomaly-001",
      "severity": "medium",
      "agent": "cleaner",
      "stage": "cleaner_run_step",
      "description": "Cleaner 连续 3 次未调用 submit_assessment",
      "evidence": {
        "dump_files": ["012_cleaner_run_step_xxx.json", "014_...", "015_..."],
        "pattern": "3 次 cleaner_run_step 中 tool_calls 均不包含 submit_assessment",
        "baseline_rate": "85%（正常时期）",
        "current_rate": "40%"
      },
      "suggestion": "检查 prompt.md 中「数据够了就提交」指令是否存在。近期 prompt.md 被重写（commit 3b16f10）。"
    },
    {
      "id": "anomaly-002",
      "severity": "low",
      "agent": "scout",
      "stage": "scout_infer_all_semantics",
      "description": "Scout used_in_analysis 全 false 频率上升",
      "evidence": {
        "before_0608": "12% 的字段被排除",
        "after_0608": "45% 的字段被排除",
        "change_point": "dump 007 → 008（6/8 17:30）"
      },
      "suggestion": "检查 agent.py system_prompt 中 used_in_analysis 指令。关联 commit: cd3c2c3。"
    }
  ],
  "trends": [
    {
      "stage": "scout_infer_all_semantics",
      "metric": "used_in_analysis_false_ratio",
      "before": 0.12,
      "after": 0.45,
      "direction": "up",
      "concern": "medium"
    },
    {
      "stage": "cleaner_run_step",
      "metric": "submit_assessment_rate",
      "before": 0.85,
      "after": 0.40,
      "direction": "down",
      "concern": "high"
    }
  ]
}
```

### 诊断功能的完整流程

```
用户报告问题："Scout 字段理解崩了" 或 "Cleaner 不洗了"

1. POST /api/meta/diagnose
   body: {
     "agent": "scout",                  // 目标 Agent
     "description": "字段理解崩溃",      // 用户描述（可选）
     "time_range": ["2026-06-07", "2026-06-09"]  // 可选，默认最近 3 天
   }

2. 后端：
   a. 筛选目标 Agent 的 dump 文件，按时间排序
   b. 从每个 dump 提取 key metrics：
      - Scout: used_in_analysis true/false 比例、suggested_role 分布
      - Cleaner: submit_assessment 调用率、清洗策略分布
   c. 找变化点：metrics 发生显著变化的时间点
   d. 对变化点前后的 dump，用 Prompt Lab API 回放对比：
      POST /api/prompt-lab/run（用早期 dump 的 user message + 早期 prompt）
      POST /api/prompt-lab/run（用早期 dump 的 user message + 晚期 prompt）
      → 确认行为差异是否由 prompt 变化导致
   e. 关联 git log：
      git log --since=<变化点前1天> --until=<变化点> -- **/agent.py **/prompt.md **/scout_reply.py
      → 找到可疑 commit
   f. 调 meta LLM：发送所有证据 → 生成诊断报告

3. 返回 DiagnosisReport JSON
```

**诊断报告 JSON schema**：

```json
{
  "agent": "scout",
  "diagnosis": "Scout 字段理解退化：提示词改动导致 LLM 过度排除字段",
  "change_point": {
    "dump_before": "007_scout_infer_all_semantics_20260608_1729.json",
    "dump_after": "008_scout_infer_all_semantics_20260608_1731.json",
    "timestamp": "2026-06-08T17:30"
  },
  "suspected_commit": {
    "hash": "cd3c2c3",
    "message": "fix(scout): prompt 补 used_in_analysis=false 约束",
    "files": ["hagoku/agents/scout/agent.py"]
  },
  "before_behavior": {
    "sample_dump": "007_...",
    "used_in_analysis_true_pct": 0.88,
    "field_roles": {"StoreID": "identifier", "Revenue": "target", "Quantity": "feature"}
  },
  "after_behavior": {
    "sample_dump": "008_...",
    "used_in_analysis_true_pct": 0.55,
    "field_roles": {"StoreID": "identifier", "Revenue": "target", "Quantity": "ignore"}
  },
  "replay_confirmation": {
    "old_prompt_with_current_data": "Quantity → feature (used_in_analysis=true)",
    "new_prompt_with_current_data": "Quantity → ignore (used_in_analysis=false)",
    "confirmed": true
  },
  "root_cause": "提示词中加了「只勾选直接回答分析目标必需的字段」→ LLM 过度保守，将 Quantity 排除",
  "suggestion": "将指令回退为「判断并说明原因」，或改为中性流程指令「建议角色：相关→target/feature，无关→ignore」"
}
```

### 守门（CI 集成）

```
PR 修改了 hagoku/agents/scout/agent.py 中的 system_prompt
  ↓
CI 触发: .github/workflows/prompt-gate.yml
  ↓
运行 scripts/ci/prompt_gate.py:
  1. 找到最近一次主分析的 dump 文件（scout_infer_all_semantics 类型）
  2. 提取其中的 user message（测试数据）
  3. POST /api/prompt-lab/run:
     - system = 当前 main 分支的 system_prompt（基线）
     - user = dump 中的 user message
     → 基线结果
  4. POST /api/prompt-lab/run:
     - system = PR 分支的 system_prompt（新版本）
     - user = 同一 user message
     → 新版本结果
  5. 对比两个版本的 tool_calls
  6. 差异超过阈值（tool_calls 变化 > 20% 或 content 相似度 < 0.8）
     → PR 打标签 ⚠️ prompt-change
     → 在 PR 中贴 diff 报告
     → CI 不通过（需要人工 review）
  7. 差异在阈值内
     → CI 通过
     → PR 中贴 "✅ 提示词变更无显著影响" 报告
```

**守门脚本的参数**：

```bash
python scripts/ci/prompt_gate.py \
  --agent scout \
  --baseline-ref main \              # 基线分支
  --pr-ref HEAD \                    # PR 分支
  --dump-dir ~/.hagoku/llm_dumps/ \
  --threshold-tool-change 0.2 \      # tool_calls 变化 > 20% → 报警
  --threshold-content-sim 0.8 \      # 内容相似度 < 0.8 → 报警
  --output pr-comment                 # 输出格式：pr-comment | json | text
```

### 后端 API

#### `POST /api/meta/inspect`

```
Request:
{
  "dump_dir": "auto",              // "auto" = 当前 run_dir 或 ~/.hagoku/llm_dumps/
  "agents": ["scout", "cleaner"],  // 可选，默认全部
  "days": 3                        // 扫描最近 N 天的 dump
}

Response 200:
{ InspectionReport }               // 见上文 schema

Response 200 (无 dump):
{
  "summary": "无可用 dump 文件。请先运行一次分析。",
  "anomalies": [],
  "dump_count": 0
}
```

#### `POST /api/meta/diagnose`

```
Request:
{
  "agent": "scout",
  "description": "字段理解崩溃，字段全被排除",
  "time_range": ["2026-06-07", "2026-06-09"],
  "dump_dir": "auto"
}

Response 200:
{ DiagnosisReport }                // 见上文 schema
```

### 改动清单

| 组件 | 文件 | 行数 |
|------|------|------|
| 配置 | `hagoku/config.py` — `model_meta` 字段 | +3 |
| Agent | `hagoku/agents/meta/__init__.py`（新建） | +2 |
| Agent | `hagoku/agents/meta/agent.py`（新建） — MetaAgent | ~200 |
| Agent | `hagoku/agents/meta/prompt.md`（新建） — 系统提示词 | ~80 |
| 后端 | `hagoku/api/server.py` — 注册 `/api/meta/*` | +4 |
| 后端 | `hagoku/api/meta.py`（新建） — inspect/diagnose 端点 | ~150 |
| 前端 | `hagoku_web/src/stores/workspace.ts` — 加 PanelId | +1 |
| 前端 | `hagoku_web/src/panels/MetaAgentPanel.tsx`（新建） | ~300 |
| 前端 | `hagoku_web/src/api/meta.ts`（新建） | ~30 |
| 前端 | `hagoku_web/src/App.tsx` — 导航项 | +3 |
| CI | `scripts/ci/prompt_gate.py`（新建） | ~120 |

**总计**：~900 行。依赖 Prompt Lab API（Phase 1 必须先完成）。

---

## 实施顺序

```
Phase 1: Prompt Lab（独立，不依赖其他）
  ├── 1a. hagoku/observability/llm_dump.py: 加 list_dumps() 辅助函数
  ├── 1b. hagoku/api/prompt_lab.py: 5 个端点
  ├── 1c. hagoku/api/server.py: 注册路由
  ├── 1d. hagoku_web: Zustand store + API 层 + PromptLabPanel
  └── 验收: 手动改 Scout prompt → Prompt Lab 跑 → 看到结果

Phase 2: HaGoKu Agent（依赖 Phase 1）
  ├── 2a. hagoku/config.py: model_meta 配置
  ├── 2b. hagoku/agents/meta/: MetaAgent + prompt.md
  ├── 2c. hagoku/api/meta.py: inspect + diagnose 端点
  ├── 2d. hagoku_web: MetaAgentPanel
  ├── 2e. scripts/ci/prompt_gate.py: CI 守门
  └── 验收: 手动触发巡检 → 看到报告，手动触发诊断 → 看到退化定位
```

---

## 不做什么

- 不做自动修复（Meta Agent 只报告，不改提示词——铁律 -2）
- 不做 A/B 测试平台（手工 Prompt Lab + 自动化守门够用）
- 不做线上监控报警（运维层的事，不是开发工具的职责）
- 不做 dump 文件自动清理（磁盘管理是用户的事）
- 不做多项目 dump 聚合（v1 只处理当前机器的 dump）

## 开放问题

1. **Meta Agent 是否需要自己的 `prompt.md`**？目前设计是"需要"——80 行的专用提示词。好处是巡检/诊断逻辑可调，坏处是多一个需要铁律 10 保护的提示词文件。

2. **巡检触发方式**？建议 Phase 2 先做手动触发（面板上的「开始巡检」按钮）。自动触发（每次分析完成后跑 / 定时跑）放 Phase 3。

3. **守门 CI 的 golden set**？建议用最近一次主分析的 Scout dump 作为固定测试数据。备选：维护一个 `tests/fixtures/prompt_gate/` 目录，包含一组代表性 CSV + 预期 tool_calls。

4. **`HAGOKYU_LLM_MODEL_META` 未设置时的行为**？建议：**记录 warning 但允许回退**到 `HAGOKYU_LLM_MODEL`。拒绝启动太激进——用户可能只有一个模型但依然需要诊断能力。

5. **对比模式的 diff 阈值怎么定**？tool_calls 变化 > 20% 和 content 相似度 < 0.8 是初始值，需要实际使用后校准。Phase 2 的守门可以先只报告不阻断（soft gate），积累数据后再升级为 hard gate。
