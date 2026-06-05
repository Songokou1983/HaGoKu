# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

> **单源声明**：本文件是项目**唯一** AI 实现者手册（`AGENTS.md` 仅是指向本文件的指针）。所有 AI 助手（Claude / Codex / Cursor / Cascade 等）入仓库后均以本文件为操作手册。规则冲突时一律以 [`PROJECT.md`](PROJECT.md) 为权威源。

## Repository Context

This repository contains **one primary project**: `hagoku/`（主项目）。其他同名目录下的项目不在此仓库管理范围内。

## 铁律（PR 级硬约束 — 违反任何一条 PR 直接拒）

### 铁律 0（查 dump 再开口）— 执行闸门：无 dump 引用 = 不准改代码

收到用户报错或描述异常行为后：
1. 第一个 tool call **必须**是 `ls -lt ~/.hagoku/llm_dumps/ | head -5` 或等效 dump 查询
2. **改代码前，必须在回复中引用 dump 文件名或日志行号作为证据。** 格式：`` `文件名:行号` 内容摘要 ``
3. 没有 dump/日志引用就调 `edit_file` / `write_file` → **直接违规**

### 铁律 -1（禁用回滚，只做正向修复）

**绝对禁止 `git revert`、`git reset`、`git checkout -- file`、删除已实现功能、或任何形式的代码回退。**
修复只能前向——定位问题行，改那一行，不改其他地方。删错了才允许回滚，且必须用户明确许可。

### 铁律 -2（用户确认前禁止改代码）— 执行闸门：无用户"修/改/做" = 不动代码

发现任何问题后，先报告根因和方案，等用户说"修"或"改"或"做"才能动代码。
可以先读文件、查 dump、分析原因——但 `edit_file` / `write_file` / `multi_edit` 必须在用户明确许可后执行。

### 铁律 -3（禁止将问题推给 LLM / 浏览器 / 网络）— 执行闸门：无日志证据 = 不准归因

**绝对禁止以下句式，除非附带服务器日志或 dump 中的具体行作为证据：**
- "可能是模型的问题"
- "可能是浏览器超时"
- "可能是 vite 代理"
- "可能是网络问题"
- 任何将问题归于代码之外的陈述

**必须**先引用日志/dump 中的具体内容，再下结论。

### 铁律 -4（禁止绕过已有诊断信息）— 执行闸门：dump 没读完 = 不准加日志

**dump 和服务器日志是完整的诊断信息。** 禁止在 dump 和日志未被完整阅读前：
- 加新的 `logging.warning` / `print` 调试语句
- 写 E2E 测试脚本替代阅读已有 dump
- 重启服务以"重新捕获"已有信息

**先读完已有 dump 和日志的全部内容，确认信息不足后，才能加新的诊断。**

### 其他铁律

开始任何代码动作前，请先做这两件事：

1. 读完 [PROJECT.md](PROJECT.md) 的三个章节：
   - §「代码边界」（哪些事 LLM 干、哪些事代码干）
   - §「通道完备性十律」（10 条正向契约）
   - §「失败处理」§「代码层合法动作清单」（LLM 失败时唯一允许的代码动作）

### 铁律 1（零硬编码）

任何"业务概念分类 / 自然语言意图判断 / 中文同义识别"必须由 LLM 完成。代码不准做。如果你想写：

- `["收入", "营收", "销售额", ...]` 这样的关键词列表
- `re.search(r"收入|营收|销售", text)` 这样的中文语义正则
- `if intent == "预测" elif intent == "对比"` 这样的中文 if-elif 链
- 函数名带 `_infer_`/`_detect_`/`_classify_` 但内部没调 LLM

→ 全部禁止。停下来想：这个判断能不能写成一句中文，让 LLM 拿到分析目标和数据后自己判断？
能 → 删掉它。不要在任何地方替 LLM 写结论。
   prompt 可以告诉 LLM 流程（先看目标、再看字段、判断角色、提交结果），
   但不能告诉 LLM 结论（id→false、Period必须feature、逐一检查是否服务目标）。
   流程 = 怎么思考。结论 = 判成什么。代码和 prompt 都只能说流程，不能说结论。
不能（纯运算/IO/序列化）→ 才允许写代码。

### 铁律 2（LLM 失败的唯一合法路径）

当 LLM 调用失败时，你只能做四件事：

- **A.** `raise RuntimeError(...)` — LLM 不可达 / 通道异常时
- **B.** 写 `ctx["_last_understanding_failure"] = {raw_text, ...}` 然后 `return []` — LLM 调用成功但没产生有效工具调用时
- **C.** 落地能落的工具调用，未落的留空 — LLM 给出部分输出时
- **D.** 拒绝写入权威结构（同 B） — LLM 输出与原话明显矛盾时

禁止写：`except: return []` / `except: return None` / 默认值兜底 / 缓存+规则降级。

### 违禁代码速查（这些全是硬编码伪装，见一个删一个）

```python
# ❌ 禁止：业务关键词列表
BUSINESS_KEYWORDS = ["收入", "营收", "销售额", "客流量"]

# ❌ 禁止：中文语义正则
if re.search(r"收入|营收|销售", text):
    is_revenue_field = True

# ❌ 禁止：if-elif 中文分支链
if intent == "预测": method = "regression"
elif intent == "对比": method = "ttest"

# ❌ 禁止：兜底默认值
result = llm_call(...)
if not result: result = "默认理解"

# ❌ 禁止：缓存 + 规则降级
try: return llm_call(col)
except: return guess_by_column_name(col)

# ❌ 禁止：函数名暗示 LLM 但内部无 LLM 调用
def _infer_column_role(col): ...
```

### 唯一合法写法

```python
# ✅ 纯通道 + 工具：组装上下文 → 调 LLM → 机械执行 tool_calls
try:
    resp = llm_client.chat.completions.create(messages=msgs, tools=TOOLS)
except Exception as e:
    raise RuntimeError(f"LLM 不可达：{e}") from e  # 路径 1

if raw and not resp.choices[0].message.tool_calls:
    ctx["_last_understanding_failure"] = {"raw_text": raw}  # 路径 3
```

### 铁律 3（提交前自检）

完成任何代码改动后，必须跑过这三组测试。任一变红 = 改坏了：

```bash
.venv/bin/python -m pytest tests/test_doctrine_compliance.py -q
.venv/bin/python -m pytest tests/test_product/test_information_arrival.py -q
.venv/bin/python -m pytest --tb=short -q
```

### 铁律 4（决策位置律）

任何决策（行为、阈值、命名、状态、策略）必须只在**代码**或 **LLM** 中存在一次。代码里定义的决策 LLM 不可推翻；LLM 的决策代码不可预判。**绝不允许在两边各存一份。**

**❌ 反例**：
- `ctx["target"] = "revenue"`（LLM 写）+ `INTERNAL_TARGET_MAP = {"收入": "revenue"}`（代码同时存）— 两端各存
- LLM 推字段语义 + 代码维护字段语义缓存 — 双权威

**✅ 唯一合法写法**：
- LLM 推字段语义 → 写入 `ctx["fields"]`，代码只读不存平行
- 单一权威结构，所有派生视图从权威读

**检验**：`grep -rn "INTERNAL_.*MAP\|.*_CACHE.*= {" hagoku/ tests/`

### 铁律 5（通道洁净律）

代码的预计算、默认值、兜底必须 **LLM 看得见**。LLM 看不见的"代码善意" = 剥夺 LLM 独立判断的可能。

**❌ 反例**：
- 代码预解析列类型**但不写入 prompt** — LLM 失去独立判断的可能
- prompt 里有 `default_value: "revenue"` — LLM 看到默认就偷懒
- except 兜底返回 `{intent: "未知"}` — LLM 答错时用"未知"填空

**✅ 唯一合法写法**：
- 预计算了 → prompt 里写"我已计算 X，置信度 Y"，LLM 选择信不信
- 没默认 → prompt 里写"暂无"，让 LLM 决定怎么办

**检验**：`grep -rn "default_value\|默认值\|fallback.*=" hagoku/agents/`

### 铁律 6（行为中性律）

必要**结构**收窄合法；非必要**语义**收窄非法。LLM 的结构输出必须能解析（Pydantic 合法），但不能对含义预分支、不能缓存 LLM 决策、不能为 LLM 的特定行为写降级路径。

**❌ 反例**：
- `if intent == "预测": method = "regression"` — 对 LLM 输出的**语义**分流
- `@lru_cache` 装饰 `llm_call` — 缓存 LLM 决策，剥夺重新评估的可能
- 为"LLM 答错 X"专门写降级分支 — 预判 LLM 行为

**✅ 唯一合法写法**：
- Pydantic schema 解析 LLM 输出的**结构** — 必要结构收窄合法
- LLM 决策不缓存，每次重新评估
- 解析逻辑只对**结构**分支，不对**含义**分支

**检验**：`grep -rn "if.*intent\|if.*category\|@lru_cache.*llm\|@cache.*llm" hagoku/`

### 铁律 7（失败在场律）

LLM 失败必须**对用户可见**。代码不得自动重试到"看起来对了"。**用户看得见 AI 不会答 = 用户信任 AI 会的时刻。**

**❌ 反例**：
- `for attempt in range(3): try: return llm_call(); except: continue` — 静默重试
- `except: return fallback_default` — 兜底返回默认值
- LLM 失败时返回 cached 上次结果

**✅ 唯一合法写法**：
- `raise RuntimeError(f"AI 这次没答：{e}")` — 让用户看见
- 写 `ctx["_last_understanding_failure"] = {"raw": ..., "stage": ...}` — 标记给下游看
- UI 层展示失败状态

**检验**：`grep -rn "except.*pass\|except.*continue\|except.*return.*default" hagoku/`

### 铁律 8（状态显化律）

影响 LLM 决策的状态必须在 prompt 中**显式**出现。LLM 看不见的状态 = 对 LLM 不存在的状态 = 代码偷影响。

**❌ 反例**：
- 全局变量影响 LLM 行为但不注入 prompt（`self.mode = "aggressive"` 注入 LLM 但不告诉它这个值）
- 代码按某字段筛选后才传 LLM（`df = df[fields]`，没告诉 LLM 字段被筛过）
- 缓存的"上次分析结论"作为 LLM 上下文但不标注

**✅ 唯一合法写法**：
- 影响决策的状态 → 显式写在 prompt（"已筛选字段：X"、"当前模式：Y"）
- 不影响决策的纯技术状态（cache_key、lock_id、request_id）→ 不显式
- 任何 LLM 决策路径上**没有**"代码偷偷影响"的状态

**检验**：`grep -rn "self\.\(mode\|strategy\|state\|context\)" hagoku/agents/`，确认所有相关状态都已注入 prompt

### 常见错误模式（每次都会犯，请警惕）

| 你的本能 | 正确做法 |
|---------|---------|
| 测试不绿 → 加规则让它绿 | 检查是不是 prompt 写错了 / 工具 schema 不全 |
| LLM 调用失败 → 加 except 兜底 | `raise RuntimeError` 让用户看见 |
| 看到字段名（"收入"/"销售额"）→ 加 dict 映射 | 让 LLM 用 `_resolve_to_column_names` 之类的工具映射 |
| 防御性编程 "万一 LLM 返回空"→ 加默认值 | 写 `_last_understanding_failure` 让用户看到没理解 |

### 铁律 0：改动前自检（事前刹车）

任何涉及 LLM prompt、工具 schema、Agent 输出的代码改动前，**必须**先写下：
```
【自检】判断：LLM 拿到分析目标和数据后能自己判断 [X] 吗？
答案：能 → 不写任何规则，只确保信息送到 prompt。
      不能（纯运算/IO）→ 代码的活。
```
不写不改。Code review 没有自检答案 → 直接拒。

### 拿不准时问自己唯一一个问题

> "这段代码做的判断，能不能用一句中文写成 prompt 让 LLM 做？"

| 答案 | 行动 |
|------|------|
| 能 → 这是 LLM 的活 | 删掉代码。prompt 里给的是分析目标和数据，不是 id→false 这种结论 |
| 不能（纯运算/IO/序列化）→ 代码的活 | 写代码，但确保不夹带业务判断 |
| 拿不准 | 默认是 LLM 的活（LLM 主导是项目第一原则） |

## hagoku/ — HaGoKu Studio 多 Agent 数据分析平台

> 项目灵魂、Agent 表、架构原则、命令参考、技术栈 → 见 **[PROJECT.md](PROJECT.md)**（唯一真相源）。
> 文档索引、环境变量 → 见 **[DEV.md](DEV.md)**。

### 当前架构关键点（已实施的 P0 项）

**双层 LLM（P0.3）**：通过 `HAGOKYU_LLM_MODEL_DEEP` / `HAGOKYU_LLM_MODEL_QUICK` 环境变量区分。
- `llm_deep`：Analyst（假设检验/回归推理）、仲裁器（计划决策）
- `llm_quick`：Scout（类型推断）、Cleaner（清洗决策）、Reporter（格式化渲染）
- 工厂函数在 `hagoku/llm/client.py`：`create_deep_client()` / `create_quick_client()`
- 回退逻辑：未设置 deep/quick 时复用 `HAGOKYU_LLM_MODEL`

**结构化输出解析器（P1.2）**：`hagoku/guardrails/parsers.py`
- `parse_pvalue()`、`parse_effect_size()`、`parse_conclusion_count()`、`parse_confidence_interval()`
- `validate_analysis_output()` 综合 4 项检查
- Reporter 需调用解析器验证 Analyst 输出结构完整性

**Scribe**：确定性 Agent，仅字段描述不完整时用 LLM 补全。负责：看板管理、记忆维护、知识库检索与注入、字段仲裁。详见 PROJECT.md Agent 表。

**P0 架构净化（2026-05-20）**：移除 6 处代码级硬编码语义，彻底贯彻 `LLM 输出 → 代码搬运 → 用户` 通道原则：

| # | 变更 | 文件 | 说明 |
|---|------|------|------|
| P0-1 | 意图解析 LLM 化 | `hagoku/manager/query_parser.py` | 移除关键词硬匹配，改为 LLM structured output（`PlanRequestFields` schema）|
| P0-2 | Scout 分布判断 LLM 化 | `hagoku/agents/scout/agent.py` | 移除硬编码倍数阈值（`maxv > q75v * 10` 等），shape analysis 由 LLM 完成 |
| P0-3 | 删除 `_parse_llm_field_desc_line()` | `hagoku/agents/scout/agent.py` | 死代码已清除（无调用方），列语义由 LLM structured output 接管 |
| P0-4 | 保留 `_format_sample_preview()` | `hagoku/agents/scout/agent.py` | 纯数据工具函数（列值取样 → 字符串），不含业务语义决策；LLM 需要看到具体样本值才能做语义推理 |
| P0-5 | Plan 构建 LLM 化 | `hagoku/manager/orchestrator.py` | 移除关键词映射表，改为 `_call_llm_for_plan()` |
| P0-6 | 阶段消息 LLM 化 | `hagoku/manager/orchestrator.py` | 移除 `llm_lines` 硬编码消息，改为 `_generate_phase_message()` LLM 生成 |

> 删除的硬编码常量（`DISTRIBUTION_CATEGORICAL_THRESHOLD` 等）位于 `hagoku/agents/constants.py`。完整审查 → `docs/AGENT_HARDCODED_REVIEW.md`。

**代码层角色限定**：serialize → validate → transport。判断的事 LLM 做。

---

## HaGoKu Studio UI 设计原则（每一条改动都必须遵守）

1. **考虑用户体验**：每次改动想清楚用户看到什么、怎么用
2. **差异化**：和市面上产品有明显区别，不是功能堆砌
3. **互动性**：Agent 主动引导用户，不是等着用户输入
4. **不要出现重复功能**：一个功能只在一个地方
5. **不要重复犯错**：同一错误不犯第二次
6. **理解确认清楚需求再改动**：不确定就问用户，不要乱猜
7. **表格规则（HTML table via st.markdown() 实现时）**：
   - 表头 **必须居中**（`text-align:center`）— 这是死规定，**绝对不允许违反**
   - 数据列内容 **不要居中**，保持默认左对齐
   - 绝不添加未经用户明确要求的功能（如"文件数列"、"总项目数"等汇总栏）
8. **新建项目表单**：始终固定在页面底部，不可在顶部
9. **操作按钮**：图标 + 文字双重要素，缺一不可
10. **最小改动原则**：每次只改用户要求的那一个地方，不做额外的改动，不改变未要求的元素
11. **每次改动前必须备份（二选一即可）**：**优先**用 Git（`git stash` / 小步 `commit`）保留可回滚点；若仍习惯 `cp` 本地快照，文件名须为 `UI_CHANGELOG_backup_YYYYMMDDHHMMSS_原文件名`（该模式已 `.gitignore`，**勿** `git add`）。堆积后可运行 `python3 scripts/clean_ui_changelog_backups.py` 查看列表，`--older-than N --apply` 按修改时间清理（见 [DEV.md](DEV.md)）。每一步 UI/编排相关改动仍须记录到 `UI_CHANGELOG.md`。

---

## Karpathy 编码原则（自动应用）

### 1. Think Before Coding
**不猜、不藏疑点，先说假设。**
- 不确定 → 先问，不要猜
- 有多种解释 → 说出来，不要自己选
- 有更简单方案 → 提出来，不要闷头实现
- 不清楚 → 停下来，说清楚，问用户

### 2. Simplicity First
**最少代码解决问题，不 speculative。**
- 不做没要求的功能
- 单次使用的代码不抽象
- 不做没被要求的"灵活性"
- 200 行能解决就不要写 2000 行

### 3. Surgical Changes
**只改需要改的，不顺手优化。**
- 不改旁边没问题的代码
- 不顺手格式化
- 不删除没被要求删除的代码
- 只清理自己改动产生的孤儿代码

### 4. Goal-Driven Execution
**给可验证的成功标准。**
- "修 bug" → 先写测试复现，再修
- "加功能" → 先说清楚怎么算完成
- 多步任务 → 先列计划，每步有验证点