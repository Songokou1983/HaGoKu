# HaGoKu Meta 层设计：Prompt Lab + HaGoKu Agent

> 状态：设计稿 | 日期：2026-06-09 | 作者：用户 + AI

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

**共同特征**：
- 每次改动都很小（删几行、改一句话）
- 每次改动后测试都 GREEN
- 每次改动后冒烟都通过
- 没有人在改完后开 dump 看 LLM 实际输出

### 为什么测试没拦住

`test_scout_prompt_contains_ignore_role_instruction` 诞生于层 2（6/8）。它验证"提示词是否含 ignore 关键词"——这正是层 2 污染提示词的**工具**。

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

**范畴错误**：用关键词匹配验证 LLM 行为。就像用卡尺量体温——读数很精确，但体温不能这样量。这类测试完全没有信号价值（GREEN ≠ 正确，RED ≠ 错误），却有极强的负信号——它驱使开发者污染提示词来让测试变绿。

Cleaner 同理：`prompt.md` 重写没有对应测试，冒烟测试只管流程不 crash，LLM 判断退化无人察觉。

### 为什么现有防线全部失效

| 防线 | 为什么没拦住 |
|------|------------|
| 铁律 3（三组测试） | doctrine compliance 和 information arrival 验证的是代码行为（有无硬编码、通道是否完整），不验证 LLM 行为 |
| 冒烟测试 | 只验证"流程是否 crash"。全选→GREEN，全排除→GREEN，乱洗→GREEN |
| 人工 review | 提示词 diff 看起来像正常的"优化表述"，没有 dump 对比看不出问题 |

### 破坏提示词的三种典型路径

| 路径 | 表现 | 本次案例 |
|------|------|---------|
| **"优化"式破坏** | 觉得某段话多余、重复、不优雅 → 删掉 | 删 `knowledge_section` + `command_context` |
| **"修 bug"式破坏** | LLM 行为异常（全选）→ 加限制性指令 → 行为走向另一个极端 | "只选必需的" → 全部排除 |
| **"重构"式破坏** | 代码拆分/重写时顺手删掉看起来不重要的内容 | Cleaner prompt.md 36→64 行，删推理链路 |

### 解决方案：制度 + 工具

**制度层**：铁律 10 + 三道刹车（写入 CLAUDE.md）

| 刹车 | 机制 | 阻止什么 |
|------|------|---------|
| A: 禁止关键词测试 | 不准写 `assert "ignore" in prompt` | 去掉错误的验证手段，不被误导去污染提示词 |
| B: dump 对比门禁 | 改 prompt 的 PR 必须附带 dump 对比 | 把"看 LLM 实际输出"从建议变为强制 |
| C: 冒烟不充分声明 | 冒烟 GREEN ≠ 可以合并 | 明确冒烟测试边界——只管 crash，不管判断 |

三道刹车的设计逻辑：
- A 是**事前刹车**：不让你写那种测试，就不会被误导
- B 是**事中刹车**：PR 没 dump 对比直接拒，不管你多自信
- C 是**事后刹车**：冒烟 GREEN 不够，必须额外人工看 dump

刹车依赖人的自律——但人有惰性。**工具让正确的做法变容易、错误的做法变难。**

**工具层**：Meta 层 = Prompt Lab + HaGoKu Agent（即本文档的设计内容）

### 正向修复原则

铁律 -1 说"只做正向修复，不做回滚"。本次修复正是这个原则的实践：

- 不回滚 commit，而是把正确的提示词从历史版本**抄回来**
- 不是简单 revert，而是理解旧版为什么对、新版为什么错之后，手工恢复正确的部分
- 同时修正旧版的已知问题（MiniMax 全选）：旧版 hint 说"对照分析目标判断是否直接相关"太模糊 → 新版改成"逐字段重判，只判断当前字段"

---

## 设计思路

### 为什么是 Meta 层

HaGoKu 的核心是数据处理 pipeline（Scout → Cleaner → Analyst → Reporter）。这四个 Agent 做的事是理解数据、清洗数据、分析数据、生成报告。

Meta 层做的是完全不同的事：**维护这个系统本身**。

```
数据层：分析用户上传的 CSV
  用的 LLM：HAGOKYU_LLM_MODEL / _DEEP / _QUICK

Meta 层：分析系统自身的 LLM 行为
  用的 LLM：HAGOKYU_LLM_MODEL_META（独立配置）
```

为什么要分层？
- **故障隔离**：pipeline 的 LLM 崩了，meta 层还能读 dump 定位问题。不能用病人给自己看病。
- **不同能力需求**：meta 层需要强推理（对比两版 prompt 的输出差异、判断是否退化），不需要快。pipeline 的 quick 模型追求速度。
- **独立计费**：meta 调用低频但单次 token 大（读整份 dump 文件），走独立预算，不干扰 pipeline 配额。

### 为什么 Prompt Lab 是第一个

铁律 10 说"改提示词必须开 dump 人工看"。但现在的人工流程是：
1. 改 prompt
2. 跑完整 pipeline（上传 CSV → Scout → Cleaner → Analyst → Reporter，2-5 分钟，5-20 次 LLM 调用）
3. 去 `~/.hagoku/llm_dumps/` 翻文件
4. 人工读 JSON 中的 messages 和 tool_calls

这个流程**太重**。Prompt Lab 把它变成：
1. 改 prompt
2. 侧边栏点「运行」（5-15 秒，1 次 LLM 调用）
3. 立刻看到 tool_calls 和 content

**降低验证成本 = 提高验证频率 = 减少退化上线。**

### 为什么 HaGoKu Agent 需要独立 LLM

HaGoKu Agent 的诊断逻辑是：比较同一段输入在两版 prompt 下的不同输出，判断是否有退化。

如果它和 pipeline 用同一个模型：
- Pipeline 的 LLM 升级了 → 所有输出都变了 → HaGoKu Agent 误报退化
- Pipeline 的 LLM 崩了 → HaGoKu Agent 也跟着崩 → 无法诊断
- Pipeline 的 LLM 有偏见（如过度保守地排除字段）→ HaGoKu Agent 用同一个模型诊断 → 无法识别这是偏见

独立模型 = 独立视角 = 能识别 pipeline 模型自身的系统性偏差。

### 为什么是侧边栏而不是独立应用

Promp Lab 的核心场景是"引用现有提示词"——从正在运行的分析中取上下文、从 Agent 的 prompt.md 取系统提示词。侧边栏天然触手可及，不需要切换窗口、导入导出数据。

HaGoKu Agent 的核心场景是"巡检和诊断"——它需要访问 dump 历史（在同一台机器上）和 Prompt Lab API。同样不应该是独立应用。

---

## 架构

```
┌─────────────────────────────────────────────────┐
│                  HaGoKu Meta 层                   │
│                                                   │
│  🤖 HaGoKu Agent（侧边栏面板）                      │
│    ├── 巡检：读 dump 历史 → meta LLM 分析 → 报告     │
│    ├── 诊断：用户报问题 → 回放 dump → 定位退化点      │
│    ├── 守门：PR 自动对比新旧 prompt → diff 报告       │
│    └── 调用 Prompt Lab API                         │
│         │                                          │
│         ▼                                          │
│  🧪 Prompt Lab（侧边栏面板）                         │
│    ├── 手动试 prompt：选 dump → 改 prompt → 跑       │
│    ├── 对比两版输出：改前/改后 side-by-side           │
│    └── 被 HaGoKu Agent 调用（自动化）               │
│                                                   │
│  后端 API: /api/prompt-lab/*                       │
│    ├── POST /run         调 LLM                    │
│    ├── GET  /prompt      取 prompt.md              │
│    ├── GET  /dumps       列 dump 文件               │
│    └── GET  /dumps/{id}  取单个 dump               │
│                                                   │
│  独立 LLM: HAGOKYU_LLM_MODEL_META                   │
│    未设置时回退到 HAGOKYU_LLM_MODEL（不推荐）         │
└─────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────┐
│                  HaGoKu 数据层                     │
│                                                   │
│  Scout → Cleaner → Analyst → Reporter              │
│     HAGOKYU_LLM_MODEL / _DEEP / _QUICK             │
└─────────────────────────────────────────────────┘
```

---

## 一、Prompt Lab

### 界面

```
┌──────────────────────────────────────────────┐
│  🧪 提示词实验室                              │
│  ──────────────────────────────────────────── │
│                                               │
│  输入源  [从 dump 选取 ▾]  [用当前上下文]      │
│                                               │
│  Agent   [Scout ▾]                            │
│                                               │
│  提示词                                        │
│  ┌──────────────────────────────────────────┐ │
│  │ (可编辑，Ctrl+Enter 运行)                 │ │
│  └──────────────────────────────────────────┘ │
│                                               │
│  模型  [当前配置: auto]                        │
│                                               │
│  [▶ 运行]  [📋 对比原版]                      │
│  ──────────────────────────────────────────── │
│  结果                                         │
│  ┌──────────────────────────────────────────┐ │
│  │ tool_calls / content / tokens / 耗时      │ │
│  └──────────────────────────────────────────┘ │
└──────────────────────────────────────────────┘
```

### 输入源

| 模式 | 说明 |
|------|------|
| 从 dump 选取 | 下拉列出 `~/.hagoku/llm_dumps/` 最近 20 个文件，选中后自动提取 messages |
| 用当前上下文 | 取当前分析目标 + 字段上下文 + Agent 的 prompt.md |
| 手写 | 空白编辑区，自己粘贴 |

### 后端 API

**`POST /api/prompt-lab/run`**

```json
// Request
{
  "model": "auto",
  "messages": [
    {"role": "system", "content": "..."},
    {"role": "user", "content": "..."}
  ],
  "tools": "auto",
  "agent": "scout",
  "temperature": null,
  "max_tokens": null
}

// Response
{
  "content": "...",
  "tool_calls": [{"name": "submit_field_inference", "arguments": "{...}"}],
  "tokens": {"prompt": 450, "completion": 180, "total": 630},
  "duration_ms": 850,
  "model_used": "auto → deepseek-v4-pro"
}
```

**`GET /api/prompt-lab/prompt?agent=scout`** — 返回 Agent 的 prompt.md 原文。

**`GET /api/prompt-lab/dumps`** — 返回最近 dump 文件列表。

**`GET /api/prompt-lab/dumps/{filename}`** — 返回单个 dump 的完整 JSON。

### 对比模式

「对比原版」并发跑两次：当前编辑版 + dump 中原始 system 消息版。前端并排展示，tool_calls 差异高亮。

### 改动清单

| 层 | 文件 | 行数 |
|---|------|------|
| 前端 store | `workspace.ts` | +1 |
| 前端导航 | `App.tsx` | +5 |
| 前端面板 | `PromptLabPanel.tsx`（新建） | ~200 |
| 前端 API | `api/promptLab.ts`（新建） | ~30 |
| 后端路由 | `api/server.py` | +5 |
| 后端逻辑 | `api/prompt_lab.py`（新建） | ~80 |
| 后端辅助 | `observability/llm_dump.py` | +20 |

~340 行。不碰 Pipeline / Orchestrator / kanban。

---

## 二、HaGoKu Agent

### 定位

Meta 层自主 Agent。和 Scout/Cleaner/Analyst/Reporter 同级——但不分析数据，而是诊断系统本身。

### 独立 LLM

```
HAGOKYU_LLM_MODEL_META=   # 新增，专供 HaGoKu Agent
```

未设置时回退到 `HAGOKYU_LLM_MODEL`。不推荐——meta Agent 和被诊断对象应使用不同模型。

### 侧边栏入口

第 10 个面板「🤖 HaGoKu Agent」，排在 Prompt Lab 旁边：

```
… → 命令指引 → 🧪提示词实验室 → 🤖HaGoKu Agent → 运行日志 → 设置
```

### 巡检

定期（或手动触发）读取 dump 历史，meta LLM 分析异常：

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

### 诊断

用户报告问题 → HaGoKu Agent 调 Prompt Lab API 回放 dump → 对比定位：

```
🤖 诊断：Scout 字段理解退化

行为变化点：dump 007 → 008（6/8 17:30）
关联 commit: cd3c2c3 "fix(scout): prompt 补 used_in_analysis=false 约束"

变化前: StoreID(ignore), Revenue(target), Quantity(feature) ← 正常
变化后: StoreID(ignore), Revenue(target), Quantity(ignore) ← 被错误排除

根因: 提示词加了「只勾选直接必需的字段」→ LLM 过度保守
建议: 回退该句为「判断并说明原因」
```

### 守门

CI 集成：PR 改 prompt → 自动用 Prompt Lab 对比改前/改后输出 → diff 报告贴在 PR 里。差异超阈值 → PR 打 `⚠️ prompt-change` 标签。

### 改动清单

| 组件 | 行数 |
|------|------|
| `hagoku/config.py` — `model_meta` 配置 | +3 |
| `hagoku/agents/meta/` — MetaAgent(BaseAgent) | ~300 |
| `hagoku/api/server.py` — 路由 | +5 |
| `hagoku/api/meta.py` — 巡检/诊断端点 | ~150 |
| `hagoku_web/src/panels/MetaAgentPanel.tsx` | ~250 |
| `hagoku_web/src/App.tsx` — 导航项 | +3 |
| `scripts/ci/prompt_gate.py` — CI 守门脚本 | ~100 |

~800 行。依赖 Prompt Lab API。

---

## 实施顺序

```
Phase 1: Prompt Lab（独立，不依赖其他）
  └── 后端 API + 前端面板

Phase 2: HaGoKu Agent（依赖 Prompt Lab API）
  ├── 独立 LLM 配置
  ├── 巡检
  ├── 诊断
  └── 守门（CI 集成）
```

---

## 不做什么

- 不做自动修复（只报告，不改提示词——铁律 -2）
- 不做 A/B 测试平台（太重）
- 不做线上监控报警（运维层的事）

## 开放问题

1. HaGoKu Agent 是否需要自己的 `prompt.md`，还是纯 system prompt 拼接？
2. 巡检：手动触发 vs 每次分析完成自动跑 vs 定时？
3. 守门 CI：golden set 用固定 CSV + 固定 query，还是最近 N 次 dump？
4. `HAGOKYU_LLM_MODEL_META` 未设置时的行为：回退到 `MODEL` 还是拒绝启动？
