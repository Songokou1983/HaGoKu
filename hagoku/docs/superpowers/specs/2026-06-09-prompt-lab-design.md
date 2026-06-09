# Prompt Lab — 侧边栏提示词实验室

> 状态：设计稿 | 日期：2026-06-09 | 作者：用户 + AI

## 动机

铁律 10（提示词修改慎重律）确立了原则：提示词修改必须以 dump 对比为证据，不能用关键词匹配测试替代行为验证。但当前实践中缺少一个低成本的提示词试错工具——每次验证提示词效果都需要跑完整 pipeline（上传 CSV → Scout → Cleaner → Analyst → Reporter，5-20 次 LLM 调用，2-5 分钟），导致提示词迭代极其笨重。

**Prompt Lab 是铁律 10 的工具化落地**：把"开 dump 看 LLM 输出"这个诊断动作从手工流程变成一个侧边栏一键操作。

## 核心目标

1. **低成本**：改一行 prompt，5-15 秒看到 LLM 输出，不跑 pipeline
2. **同环境**：复用当前 LLM 配置和工具注册表，结果与生产一致
3. **可对比**：并排展示改前/改后两版输出
4. **不侵入**：独立面板，不碰 Orchestrator / Pipeline / kanban

## 用户故事

1. 我在 Scout 的 prompt 里加了一句"建议角色：相关→target/feature，无关→ignore"，我想立刻看 LLM 对 demo.csv 的字段理解输出是什么
2. 上周有个 dump 显示 Cleaner 无限循环，我想用同一段输入重放，换一种 prompt 表述看会不会好
3. 我想并排对比两版 prompt 的 tool_calls，确认新版没退化

## 界面布局

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
│  │ 直接调用 submit_field_inference，         │ │
│  │ 给每个字段一个中文名。                    │ │
│  │ 建议角色：与目标直接相关的字段             │ │
│  │ →target/feature，无关的→ignore。          │ │
│  │                                           │ │
│  │ (可编辑，Ctrl+Enter 运行)                 │ │
│  └──────────────────────────────────────────┘ │
│                                               │
│  模型  [当前配置: auto]                        │
│                                               │
│  [▶ 运行]  [📋 对比原版]                      │
│  ──────────────────────────────────────────── │
│  结果                                         │
│  ┌──────────────────────────────────────────┐ │
│  │ tool_calls:                              │ │
│  │   submit_field_inference({               │ │
│  │     columns: [                           │ │
│  │       {name:"StoreID", role:"identifier", │ │
│  │        used_in_analysis: false},          │ │
│  │       {name:"Revenue", role:"target",     │ │
│  │        used_in_analysis: true},           │ │
│  │       ...                                 │ │
│  │     ]                                     │ │
│  │   })                                      │ │
│  │                                           │ │
│  │ tokens: 1,234 | 耗时: 850ms               │ │
│  └──────────────────────────────────────────┘ │
└──────────────────────────────────────────────┘
```

## 输入源设计

### 模式 A：从 dump 选取

- 下拉列表展示 `~/.hagoku/llm_dumps/` 下最近 20 个 dump 文件
- 显示格式：`003_scout_infer_all_semantics_20260609_1730`
- 选中后自动解析 JSON，提取 `messages` 数组中的 `system` 消息填充到提示词编辑区
- 提取 `user` 消息作为上下文参考（展示但不默认编辑）
- `extra.response_tool_calls` 作为"原版结果"供对比

### 模式 B：用当前上下文

- 如果 AnalysisPanel 正在运行，取当前分析目标和字段上下文
- 选 Agent → 自动拉取该 Agent 的 `prompt.md`（通过新增 API `GET /api/prompt-lab/prompt?agent=scout`）
- 用户可编辑提示词后运行

### 模式 C（未来）：手写

- 完全空白编辑区，用户自己粘贴 system + user messages
- 工具列表手动输入或从 Agent 注册表拉

## 后端 API

### `POST /api/prompt-lab/run`

```
Request:
{
  "model": "auto",           // "auto" = 用当前配置的模型
  "messages": [
    {"role": "system", "content": "..."},
    {"role": "user", "content": "..."}
  ],
  "tools": "auto",           // "auto" | "none" | [{...}]
  "agent": "scout",          // 用于 "auto" 时从工具注册表拉 tools
  "temperature": null,       // null = 用 agent 默认值
  "max_tokens": null
}

Response:
{
  "content": "LLM 文本响应",
  "tool_calls": [
    {"name": "submit_field_inference", "arguments": "{...}"}
  ],
  "tokens": {"prompt": 450, "completion": 180, "total": 630},
  "duration_ms": 850,
  "model_used": "auto → deepseek-v4-pro"
}
```

### `GET /api/prompt-lab/prompt?agent=scout`

返回该 Agent 的 `prompt.md` 原文，供编辑区初始化。

### `GET /api/prompt-lab/dumps`

返回 `~/.hagoku/llm_dumps/` 下最近 dump 文件列表（文件名 + 时间戳 + stage）。

### `GET /api/prompt-lab/dumps/{filename}`

返回单个 dump 文件的完整 JSON。

## 对比模式

点击「对比原版」时：
1. 发送当前编辑区的 prompt（改后版）
2. 同时用 dump 中原始 system 消息（原版）再发一次请求
3. 前端并排展示两列：左=原版结果，右=改后结果
4. tool_calls 中有差异的字段高亮

## 改动清单

### 前端（hagoku_web/）

| 文件 | 改动 | 行数估计 |
|------|------|---------|
| `src/stores/workspace.ts` | PanelId 加 `"prompt-lab"` | 1 |
| `src/App.tsx` | 加导航项 + panel mapping + PANEL_ORDER | ~5 |
| `src/panels/PromptLabPanel.tsx` | **新建**：面板主体 | ~200 |
| `src/api/promptLab.ts` | **新建**：API 调用封装 | ~30 |

### 后端（hagoku/）

| 文件 | 改动 | 行数估计 |
|------|------|---------|
| `hagoku/api/server.py` | 注册 prompt-lab 路由 | ~5 |
| `hagoku/api/prompt_lab.py` | **新建**：run / prompt / dumps 三个端点 | ~80 |
| `hagoku/observability/llm_dump.py` | 可能需要加 `list_dumps()` 辅助函数 | ~20 |

**总计**：~340 行，3 个新文件，3 个修改文件。

## 不做什么

- **不做**提示词版本管理（那是 git 的事）
- **不做**批量跑（那是 CI 的事）
- **不做**自动评分（LLM-as-judge 太重，且铁律 10 说人工看 dump）
- **不做**prompt 模板库
- **不碰**Orchestrator / Pipeline / kanban

## 成功标准

1. 改 Scout 提示词一句话 → 5 秒内看到 LLM 对 demo.csv 的字段理解输出
2. 从 dump 选取一条历史记录 → 回放看到与原版一致的输出
3. 对比两版提示词 → 并排展示 tool_calls 差异
4. 不影响主分析流程（Prompt Lab 崩溃不拖垮 AnalysisPanel）

## 开放问题

1. 对比模式跑两次 LLM 调用——如果模型是云端 API，费用怎么处理？（短期：只显示 token 数，不拦截）
2. prompt.md 是全文发送还是只发送 CLEANING_PLAN_RULES 片段？（建议：全文，因为 Agent 实际收到的就是全文）
3. 是否需要持久化 lab 运行历史？（建议 v1 不做，内存即可）
