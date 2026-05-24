# HaGoKu 命令系统设计

## 背景

用户在暂停点与 LLM 交互时，直接发送的自然语言消息被流程控制逻辑拦截，无法有效传递给 LLM。命令系统作为**定向沟通通道**，用户通过 `/命令 <参数>` 格式，将意图绕过流程拦截、精确送达当前阶段 LLM。

命令不是快捷键，不是硬编码逻辑，而是**沟通意图标签**——系统负责路由，LLM 负责理解。

---

## 设计原则

1. **流程控制不占命令**：确认、跳过、取消等操作由 UI 按钮完成，命令专注于用户→LLM 的沟通
2. **定向路由到 LLM**：命令内容剥离 `/命令 ` 前缀后，完整转发给当前停留阶段的 LLM
3. **统一格式规范**：全部命令遵循 `/<命令> <固定结构参数>` 格式，参数结构可解析，内容由 LLM 理解
4. **阶段命令自动分流**：Scout 阶段的命令路由给 Scout Agent，Cleaner 阶段的路由给 Cleaner Agent，无需用户指定接收方
5. **后续阶段按需扩充**：Cleaner、Analyst、Reporter 阶段命令按相同格式规范后期设计

---

## 全局命令（所有阶段通用）

| 命令 | 格式 | 作用 |
|------|------|------|
| `/goal` | `/goal <分析目的>` | 补充/修正分析目标 |

### 示例

```
/goal 分析各店铺收入增长趋势
/goal 找出影响客户退货率的关键因子
```

---

## Scout 阶段 · 字段理解

Scout 向用户展示字段核对表（三列：`field_name` | `chinese_name` | `meaning`）。用户通过以下命令纠正 LLM 的理解偏差：

| 命令 | 格式 | 作用 |
|------|------|------|
| `/rename` | `/rename <原始列名>=<中文名称> [, ...]` | 纠正 LLM 猜错的中文显示名（第二列），更新 `column_display_names` |
| `/use` | `/use <列名1>, <列名2>, ...` | 指定本次分析参与字段，超出范围的标记 `used_in_analysis=False` |

### 示例

```
/rename Code=店铺编号, Amt=收入金额, Date=营业日期
/use 收入金额, 客流, 营业日期, 店铺编号
```

### 参数说明

#### `/rename`

- `<原始列名>`：LLM 展示的字段核对表第一列（CSV 原始列名）
- `<中文名称>`：用户对该列的业务命名，替代 LLM 的猜测（第二列 chinese_name）
- 多组用英文逗号分隔，每组用 `=` 连接
- 不纠正 meaning（第三列），meaning 由 LLM 自己根据中文名称更新

#### `/use`

- `<列名>`：原始列名（field_name）
- 多列用英文逗号分隔
- 指定后，未列出的字段标记为不参与分析（`used_in_analysis=False`）

---

## 前端命令面板

**组件**：`hagoku_web/src/panels/CommandsPanel.tsx`

前端已实现完整的命令速查面板（457 行），按阶段（Scout / Cleaner / Analyst / Reporter）分类展示：
- **FastCommand 卡片**：`/goal`（补充分析目的）、`/rename`（字段重命名）、`/use`（选择参与字段）
- **StageRefCommands**：每个 Agent 阶段的结构化命令列表，含命令格式、描述、示例
- **FAQ 区**：命令系统的常见问题解答
- **搜索过滤**：支持按命令名搜索
- **快捷插入**：点击命令卡片可快速填入当前输入框

**当前状态**：前端命令面板已完备，但后端命令路由（命令 → LLM 转发）尚未完全对接（`_detect_user_intent_via_llm` 已定义但未调用）。命令解析器（`command_parser.py`）已就绪，解析结果在 `orchestrator.py` 暂停入口被检查，但尚未进入 LLM 转发通道。

---

## 预留阶段命令

### Cleaner 阶段 · 清洗核对

待设计。格式规范同上：`/<命令> <固定结构参数>`

### Analyst 阶段 · 统计分析

待设计。格式规范同上。

### Reporter 阶段 · 报告生成

待设计。格式规范同上。

---

## 命令解析器

**文件：** `hagoku/manager/command_parser.py`

### 解析规则

```
以 "/" 开头 → 识别为命令
  → 提取命令名（第一个空格前的部分）
  → 剩余部分按命令的固定格式解析参数

不以 "/" 开头 → 不是命令，走现有自然语言处理逻辑
```

### 解析输出格式

```python
# /goal 各店铺收入增长趋势
{"command": "goal", "args": "各店铺收入增长趋势"}

# /rename Code=店铺编号, Amt=收入金额
{"command": "rename", "args": [("Code", "店铺编号"), ("Amt", "收入金额")]}

# /use 收入, 客流, 日期
{"command": "use", "args": ["收入", "客流", "日期"]}
```

### 支持的全局命令

- `goal` — 参数为自然语言文本

### 支持的阶段命令

- `rename` — 参数为 `key=value` 对列表
- `use` — 参数为逗号分隔的列名列表

---

## 后端集成

**文件：** `hagoku/manager/orchestrator.py`

### 暂停点改造

`_pause_and_wait` 入口处先调用 `command_parser.parse()` 判定：

- **命令** → 去掉 `/命令 ` 前缀，内容路由给当前停留阶段的 LLM
  - Scout 阶段：`/rename` `/use` 触发字段理解更新
  - Cleaner 阶段：预留
  - Analyst 阶段：预留
- **自然语言** → 走现有 `respond` 流程

### 路由规则

命令始终路由到**当前停留阶段的 LLM**。停留阶段由看板状态机决定：

- 状态 `SCOUT_FIELD_REVIEW` / `SCOUT_ALIGNMENT` → Scout
- 状态 `CLEANING_REVIEW` / `CLEANING_ALIGNMENT` → Cleaner
- 状态 `ANALYSIS_REVIEW` / `ANALYSIS_ALIGNMENT` → Analyst
- 其他 → 全局命令（`/goal`）

---

## 前端展示

### CommandsPanel.tsx（重写）

替换当前 361 行错误指引，改为按阶段折叠的命令速查表：

```
Scout · 字段理解
  /goal                补充分析目的
  /rename <列名>=<中文名称> [, ...]   纠正中文显示名
  /use <列名1>, <列名2>, ...          指定参与字段

Cleaner · 清洗核对
  暂未开放阶段命令

Analyst · 统计分析
  暂未开放阶段命令

Reporter · 报告生成
  暂未开放阶段命令
```

### 消息输入框

- 输入 `/` 时弹出命令补全提示（`/goal` `/rename` `/use`）
- 选中命令后显示对应格式提示

---

## 文档索引

| 文件 | 内容 |
|------|------|
| `docs/COMMAND_SYSTEM.md`（本文件） | 命令系统完整设计 |
| `PROJECT.md` → 命令系统章节 | 命令系统概要（架构级描述） |
| `hagoku/manager/command_parser.py` | 命令解析器实现 |
| `hagoku/manager/orchestrator.py` | 暂停点命令路由集成 |
| `hagoku_web/src/panels/CommandsPanel.tsx` | 命令速查表面板 |