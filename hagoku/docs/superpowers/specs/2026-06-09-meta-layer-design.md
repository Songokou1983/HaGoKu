# HaGoKu Meta 层设计：Prompt Lab + HaGoKu Agent

> 状态：设计稿 | 日期：2026-06-09 | 作者：用户 + AI

## 动机

铁律 10（提示词修改慎重律）确立了三道刹车，但刹车是制度层面的——依赖人的自律。我们需要工具层面的支撑：

- **Prompt Lab**：让人能低成本验证提示词效果（替代"改一行 → 跑全 pipeline → 等 5 分钟"）
- **HaGoKu Agent**：让系统能自主巡检 LLM 行为，发现退化时主动报告（替代"用户用到崩了才知道"）

两者共同构成 **HaGoKu Meta 层**——不是分析数据的，是维护分析系统本身的。

## 架构关系

```
┌─────────────────────────────────────────────────┐
│                  HaGoKu Meta 层                   │
│                                                   │
│  HaGoKu Agent（侧边栏面板）                        │
│    ├── 巡检：读 dump 历史，发现异常                  │
│    ├── 诊断：回放 dump，定位退化点                   │
│    ├── 守门：PR 自动对比新旧 prompt 输出             │
│    └── 调用 Prompt Lab API                         │
│         │                                          │
│         ▼                                          │
│  Prompt Lab（侧边栏面板）                           │
│    ├── 手动试 prompt：人选 dump，改 prompt，跑       │
│    ├── 对比两版输出                                 │
│    └── 被 HaGoKu Agent 调用（自动化）               │
│                                                   │
│  后端 API: /api/prompt-lab/*                       │
│    ├── POST /run         调 LLM                    │
│    ├── GET  /prompt      取 prompt.md              │
│    ├── GET  /dumps       列 dump 文件               │
│    └── GET  /dumps/{id}  取单个 dump               │
└─────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────┐
│                  HaGoKu 数据层                     │
│                                                   │
│  Scout → Cleaner → Analyst → Reporter              │
│     HAGOKYU_LLM_MODEL / _DEEP / _QUICK             │
└─────────────────────────────────────────────────┘
```

## 一、Prompt Lab

### 定位

人工操作的提示词试错工具。侧边栏面板，一键跑 LLM，5-15 秒出结果。

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

#### `POST /api/prompt-lab/run`

```
Request:
{
  "model": "auto",
  "messages": [{"role": "system", "content": "..."}, {"role": "user", "content": "..."}],
  "tools": "auto",     // "auto" | "none" | [{...}]
  "agent": "scout",    // 用于 "auto" 时从注册表拉 tools
  "temperature": null,
  "max_tokens": null
}

Response:
{
  "content": "...",
  "tool_calls": [{"name": "submit_field_inference", "arguments": "{...}"}],
  "tokens": {"prompt": 450, "completion": 180, "total": 630},
  "duration_ms": 850,
  "model_used": "auto → deepseek-v4-pro"
}
```

#### `GET /api/prompt-lab/prompt?agent=scout`

返回该 Agent 的 `prompt.md` 原文。

#### `GET /api/prompt-lab/dumps`

返回最近 dump 文件列表。

#### `GET /api/prompt-lab/dumps/{filename}`

返回单个 dump 文件的完整 JSON。

### 对比模式

点击「对比原版」时并发跑两次：当前编辑版 + dump 中原始 system 消息版。前端并排展示，差异高亮。

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

**总计** ~340 行，不碰 Pipeline / Orchestrator / kanban。

---

## 二、HaGoKu Agent

### 定位

Meta 层自主 Agent。和 Scout/Cleaner/Analyst/Reporter 同级，但不处理数据——它诊断系统本身。

### 独立 LLM 配置

```
HAGOKYU_LLM_MODEL_META=   # HaGoKu Agent 专用
```

未设置时回退到 `HAGOKYU_LLM_MODEL`，但不推荐——meta Agent 应该和被诊断对象用不同模型，保证故障隔离。

### 侧边栏入口

侧边栏第 10 个面板：「🤖 HaGoKu Agent」，排在 Prompt Lab 旁边：

```
… → 命令指引 → 🧪提示词实验室 → 🤖HaGoKu Agent → 运行日志 → 设置
```

### 三大能力

#### 1. 巡检

周期性地（或用户手动触发）读取 `~/.hagoku/llm_dumps/` 中的历史 dump，调用 meta LLM 分析：

- 哪些 Agent 反复犯同类错误（如 Cleaner 一直不调 `submit_assessment`）
- 哪些提示词改动后行为发生了显著变化
- 输出巡检报告：异常列表 + 严重程度 + 建议

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

#### 2. 诊断

用户报告问题（"字段理解又崩了"）→ HaGoKu Agent：

1. 拉取最近 N 次 Scout dump
2. 调用 Prompt Lab API 回放，对比不同时间点的输出
3. 定位行为变化的精确时间点
4. 关联 git log，找到对应 commit
5. 输出诊断报告

```
🤖 诊断：Scout 字段理解退化

行为变化点：dump 007 → 008（6/8 17:30）
关联 commit: cd3c2c3 "fix(scout): prompt 补 used_in_analysis=false 约束"

变化前: StoreID(ignore), Revenue(target), Quantity(feature) ← 正常
变化后: StoreID(ignore), Revenue(target), Quantity(ignore) ← Quantity 被错误排除

根因: 提示词加了「只勾选直接必需的字段」→ LLM 过度保守
建议: 回退该句为「判断并说明原因」
```

#### 3. 守门

集成到开发流程：

- 开发者改提示词 → 提交 PR
- CI 触发 HaGoKu Agent 守门模式
- 自动用 Prompt Lab 跑改前/改后对比（使用历史 dump 作为输入）
- 输出 diff 报告贴在 PR 里
- 差异超过阈值 → PR 打标签 `⚠️ prompt-change`，需人工 review dump

### 与 Prompt Lab 的关系

```
HaGoKu Agent
  │
  ├── 巡检: 读 dump 文件，调 meta LLM 分析
  │
  ├── 诊断: 调 Prompt Lab API 回放 dump
  │         → POST /api/prompt-lab/run
  │         → 对比输出
  │
  └── 守门: 同上，自动化
```

Prompt Lab 是工具，HaGoKu Agent 是使用者之一。

### 改动清单（估算）

| 组件 | 说明 | 行数 |
|------|------|------|
| `hagoku/config.py` | 新增 `model_meta` 配置项 | +3 |
| `hagoku/agents/meta/` | 新建目录：MetaAgent(BaseAgent) | ~300 |
| `hagoku/api/server.py` | 注册 meta agent 相关路由 | +5 |
| `hagoku/api/meta.py` | 巡检/诊断 API 端点 | ~150 |
| `hagoku_web/src/panels/MetaAgentPanel.tsx` | 新建面板 | ~250 |
| `hagoku_web/src/App.tsx` | 加导航项 | +3 |
| `scripts/ci/prompt_gate.py` | CI 守门脚本 | ~100 |

**总计** ~800 行。依赖 Prompt Lab API（先做 Prompt Lab，再做 HaGoKu Agent）。

---

## 实施顺序

```
Phase 1: Prompt Lab（独立，不依赖其他）
  └── 后端 API + 前端面板

Phase 2: HaGoKu Agent（依赖 Prompt Lab API）
  ├── 独立 LLM 配置
  ├── 巡检能力
  ├── 诊断能力
  └── 守门能力（CI 集成）
```

---

## 不做什么

- 不做自动修复（Agent 只报告，不自动改提示词——铁律 -2）
- 不做提示词 A/B 测试平台（太重，手工 + Prompt Lab 够用）
- 不做线上监控报警（那是运维层的事，不是 Meta 层的范围）

## 开放问题

1. HaGoKu Agent 是否需要自己的 `prompt.md`？还是纯 system prompt 拼接？
2. 巡检频率：手动触发 vs 每次分析完成自动跑 vs 定时？
3. 守门 CI：用什么作为 golden set 的测试数据？固定 CSV + 固定 query 还是最近 N 次 dump？
