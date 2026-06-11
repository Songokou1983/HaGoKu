# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 新人 30 秒入门（AI session 必读）

**项目**：HaGoKu Studio 多 Agent 数据分析平台（Scout → Cleaner → Analyst → Reporter）
**核心信条**：LLM 在语义判断上比代码更可靠。Code 的活是构建通道让 LLM 自由发挥，不替 LLM 干活。
完整信条见 [`PROJECT.md`](PROJECT.md) 顶部。

> 📍 **项目演进方向（2026-06-11 起）**：项目正在从「4 Agent 协作 pipeline」收缩为「1 个数据分析师 LLM + 专业工具箱」。改造按 6 Phase 推进。核心信条不变。
> 任何架构层改动前**必读** [`docs/plans/2026-06-11-collapse-to-single-agent-brief.md`](docs/plans/2026-06-11-collapse-to-single-agent-brief.md)，确认方向一致。

**绝对不能做**：
- if-elif 中文分支判断意图 / 字段角色（铁律 1）
- except 兜底默认值 / 静默重试（铁律 7）
- 缓存 LLM 决策 / 隐藏 LLM 状态（铁律 6, 8）
- 业务关键词列表 / 中文语义正则（铁律 1 配套）
- **项目文档/AI 输出/记忆绑具体 LLM 模型名 / 部署 URL（铁律 9）**
- **全文重写 prompt.md / 删 system_prompt 拼接片段 / 无 dump 对比改提示词（铁律 10）**
- **绕过 `build_messages()` 直接构造发给 LLM 的 messages（通道守门 / Phase 0）**

**绝对要做**：
- LLM 走 `tool_calls` + Pydantic 收结构（铁律 4 通道）
- LLM 失败 `raise RuntimeError`，让用户看见（铁律 7）
- 状态显式注入 prompt，不偷影响 LLM（铁律 8）
- **所有 Agent 调 LLM 必须走 `build_messages()`，不准直接构造 messages（通道守门）**

**5 分钟读这四处**（按顺序）：
1. [`PROJECT.md`](PROJECT.md) 顶部核心信条
2. 本文件「铁律」节（0-11 全部）
3. `PROJECT.md` §「代码边界」+「通道完备性十律」
4. [`docs/superpowers/specs/2026-06-09-meta-layer-design.md`](docs/superpowers/specs/2026-06-09-meta-layer-design.md) — HaGoKu Doctor 设计

**不确定时**：见下方「拿不准时问自己两个问题」节。

---

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

### 铁律 9（配置中性律）

项目文档 / AI 输出 / 记忆 / 源代码注释**不绑具体部署配置**（LLM 模型名、API 端点、端口等）。这些是用户运行时通过设置功能选择的，不是项目真理。

**❌ 反例**：
- `PROJECT.md` 写 `HAGOKYU_LLM_MODEL=Qwen3.6-35B-A3B` 当默认值——一旦换模型就过时
- `CLAUDE.md` 写 "通过 llama-server (localhost:8000) 调用本地 35B"——绑死部署形态
- `.env.example` 写 `HAGOKYU_LLM_BASE_URL=http://localhost:8080/v1` 当模板值——云端模型不是这个地址
- AI 输出 "因为当前用 35B 模型 context 是 128K"——把 runtime config 当 design constraint
- memory 写 "项目当前用某个云端模型 1M context"——memory 跨 session 持久，runtime 变了就误导

**✅ 唯一合法写法**：
- 文档/示例里出现模型名时 → `<用户配置>` 占位
- BASE_URL / port 等部署值 → 留空 + `# 用户配置` 注释
- 描述列加 "（用户运行时通过设置功能选择）" 说明
- 涉及 LLM 能力时 → 按"配置范围"评估（"假设 context 在 128K-1M 之间"），不绑具体模型
- 评估 LLM 是否胜任某任务时 → 先问用户当前用的是什么，把答案当 runtime config 不当 design constraint
- `config.py` 数据类默认值可保留（Python 类行为），但 docs 描述不许指向具体值

**检验**：
```bash
grep -rn "Qwen\|A3B\|localhost:8\|text-embedding" CLAUDE.md PROJECT.md .env.example  # 应空
grep -rn "minimax\|claude\|gpt-\|gemini" hagoku/ docs/  # AI 内部输出不留具体模型名
```

### 铁律 10（提示词修改慎重律）— 提示词非代码，不可随意重构

**提示词（prompt.md、agent.py 中的 system_prompt 字符串、tool description）和代码有本质区别。**

代码可以审计——看逻辑、跑测试、静态分析。提示词是**与 LLM 多轮交互迭代总结出来的**，其效果取决于 LLM 对自然语言的理解，无法通过简单审计评价好坏。

**❌ 绝对禁止的操作**：
- **全文重写 prompt.md**：把 36 行精简成 64 行"清洗伙伴"风格——删掉的可能是多轮迭代后沉淀的关键指令
- **"优化"提示词表述**：觉得某句话啰嗦，改成更简洁的版本——"啰嗦"可能是 LLM 需要的关键上下文
- **删减 system_prompt 拼接片段**：如 `knowledge_section`、`command_context`——这些片段是用户反馈通道，删掉 = LLM 看不到用户说过什么
- **把流程指令改成结论指令**："判断并说明原因"→"只选直接必需的"——前者是流程，后者是替 LLM 预设结论方向
- **在没有 dump 对比的情况下改提示词**：不知道改之前 LLM 怎么想的、改之后怎么想的，就动手改

**✅ 修改提示词的正规流程**：
1. **先开 dump**：`HAGOKU_DUMP_LLM=1` 跑一次，看 LLM 收到的完整 prompt 和完整响应
2. **定位具体问题**：是字段理解错了？是漏了步骤？是无限循环？——精确到哪一句话导致
3. **最小修改**：改一行，跑 dump 对比。不改多行
4. **保留原文对照**：commit message 必须引用删/改的原文，让后人知道"之前是这么写的"
5. **跑冒烟**：改完必须跑对应的冒烟测试（smoke 脚本或手动端到端），确认行为改善

**什么时候可以改提示词**：
- 有 dump 证据证明某句话导致 LLM 行为异常
- 新增功能需要新指令 → 加句子，不删已有句子
- 工具 schema 变更需要同步更新 → 改 schema 对应的描述部分
- 用户反馈某个 Agent 反复犯同一个错误 → dump 定位到具体语句后修改

**什么时候绝对不可以改提示词**：
- 觉得"写得不够好""风格不统一""太啰嗦"——这不构成修改理由
- 代码重构顺手"优化"——提示词不是代码，不遵循 DRY/SOLID
- 测试不绿就改提示词让它绿——这是头痛医头，治标不治本
- 换 LLM 模型后行为变了——应该适配模型，不是改提示词迁就

**检验**：
```bash
# 检视所有 prompt.md 的最近修改
git -C hagoku log --oneline -10 -- '**/prompt.md' '**/prompts/*.md'
# 检视所有 agent.py 中 system_prompt 片段的最近修改
git -C hagoku log --oneline -10 -S "system_prompt" -- '**/agent.py'
```
任何最近 5 个 commit 内的提示词修改都必须附带 dump 对比证据，否则应视为可疑。

### 刹车 A — 禁止对提示词内容做关键词匹配测试

**❌ 绝对禁止写这种测试**：
```python
def test_scout_prompt_contains_ignore_role_instruction():
    prompt = agent._build_prompt(...)
    assert "ignore" in prompt.lower()  # ← 范畴错误
```

**为什么禁止**：`assert "ignore" in prompt` 只能验证"提示词里有没有这个词"，不能验证"LLM 行为是否正确"。
- 提示词缺 ignore → LLM 仍可能正确使用 ignore（因为 tool schema 里有）
- 提示词有 ignore → 加了"只选必需的"这种结论性指令，LLM 反而变得过度保守
- 测试 GREEN ≠ 行为正确，测试 RED ≠ 行为错误——这个测试没有任何信号价值

**但会产生严重的负信号**：测试 RED → 开发者加一句让测试 GREEN → 提示词被污染 → 实际行为退化 → 无人发现。

**✅ 正确的验证方法**：
- 开 dump (`HAGOKU_DUMP_LLM=1`)，人工看 LLM 实际返回的 `suggested_role` 和 `used_in_analysis` 值
- 跑端到端冒烟，确认字段参与列勾选合理
- 如果确实需要自动化回归 → **mock LLM 返回已知字段语义，验证代码层不覆盖 LLM 决策**（这是代码行为测试，不是提示词内容测试）

**已存在的违规测试**：`tests/test_product/test_scout_uia_prompt.py::test_scout_prompt_contains_ignore_role_instruction` — 此测试为铁律 10 明确禁止的模式，应标记 `xfail` 并注明"提示词内容测试，不能反映 LLM 实际行为"。

### 铁律 11（通道优先律）— 执行闸门：LLM 行为异常 → 第一步查通道，不准改提示词

收到 LLM 行为异常报告（如字段全选、角色乱判、阶段跳转错误）后：

1. **第一个动作必须是查 dump 验证通道完整性**，检查 LLM 收到的信息里：
   - 分析目标在不在？
   - 完整上下文（字段表、数据画像）在不在？
   - 工具 schema 能不能表达 LLM 的决策？
2. 通道确认完整 → LLM 行为仍不对 → 才可以看提示词
3. 提示词改动必须在 commit message 里引用 dump 文件名作为证据
4. 改提示词超过 2 次仍不行 → 停止，问题不在提示词，回到通道

**反例**：2026-06-10，LLM 纠正字段名后全选。AI 反复改提示词七八次。根因是 dump 里 LLM think 写道"逐字段重新判断 used_in_analysis"——这是 prompt 指令，不是通道问题。删掉三行指令即修复。如果第一步看 dump，10 分钟解决。实际花了半天。

### 刹车 B — 提示词修改 PR 必须附带 dump 对比

任何修改以下文件的 PR，PR body 中**必须**包含改前/改后的 dump 对比：
- `**/prompt.md`
- `**/agent.py` 中 `system_prompt` 字符串
- `**/agent_tool_defs.py` 中 `description` 字段
- `**/scout_reply.py` 中 `system_msg` 字符串

对比格式：
```
### 改前 dump（HAGOKU_DUMP_LLM=1）
- LLM 收到的完整 system prompt: <粘贴>
- LLM 返回的 tool_calls: <粘贴>
- 行为表现: <描述：字段参与列勾选是否合理>

### 改后 dump
- LLM 收到的完整 system prompt: <粘贴>
- LLM 返回的 tool_calls: <粘贴>
- 行为表现: <描述：改善了什么>
```

无 dump 对比的提示词 PR → **直接拒**。

### 刹车 C — 冒烟测试只管流程，不管判断

现有冒烟测试验证的是"流程是否跑通"（有无 crash、有无返回结果）。**流程 GREEN ≠ LLM 判断正确。**

- 冒烟 GREEN 但字段全选 → 通过，无人察觉
- 冒烟 GREEN 但字段全排除 → 通过，无人察觉  
- 冒烟 GREEN 但清洗策略乱选 → 通过，无人察觉

冒烟测试是**必要但不充分**的。提示词修改后，必须在冒烟之上额外做人工 dump 审查——没有例外。

### 触发词速查表（写代码时秒查）

看到以下代码模式 / 写以下逻辑时，先查对应铁律：

| 触发场景 | 应用铁律 |
|---------|---------|
| `if intent == "..."` / `if category == "..."` — 对 LLM 输出按含义分支 | 6 行为中性 |
| `@lru_cache` / `@cache` 装饰 LLM 调用 | 6 行为中性 |
| `default_value: "X"` / "默认值" 出现在 prompt 模板 | 5 通道洁净 |
| `except: pass` / `except: continue` / `except: return default` | 7 失败在场 |
| `for attempt in range(N): try: llm_call(); except: continue` | 7 失败在场 |
| 全局/实例状态（`self.mode` / `self.strategy`）影响 LLM 但不注入 prompt | 8 状态显化 |
| 代码按某字段筛选后才传 LLM，没标注字段被筛过 | 8 状态显化 |
| `INTERNAL_.*MAP = {...}` / `.*_CACHE = {...}` 与 LLM 决策平行存在 | 4 决策位置 |
| 缓存的"上次分析结论"作为 LLM 上下文但不标注 | 8 状态显化 |
| LLM 失败时返回 cached 上次结果 | 7 失败在场 |
| `PROJECT.md` / `.env.example` / AI 输出写具体 LLM 模型名 / `localhost:<port>` / 厂商 URL | 9 配置中性 |
| memory / commit message / docstring 出现 `Qwen3.6-35B-A3B` / `minimax` / `claude` / `gpt-4` 等具体模型名 | 9 配置中性 |
| 全文重写 prompt.md / 删除 system_prompt 中的 `knowledge_section` 等拼接片段 | 10 提示词慎重 |
| "优化"提示词表述 / 觉得啰嗦就改简洁 / 无 dump 对比就改 | 10 提示词慎重 |
| 流程指令（"判断并说明原因"）改成结论指令（"只选必需的"） | 10 提示词慎重 |
| `assert "ignore" in prompt` / 任何对 prompt 内容做关键词匹配的测试 | 10 刹车 A |
| 改 prompt.md / system_prompt / tool description 但 PR 无 dump 对比 | 10 刹车 B |
| 冒烟 GREEN 就合并提示词修改 | 10 刹车 C |

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

### 拿不准时问自己两个问题

> **问题 1**："这段代码做的判断，能不能用一句中文写成 prompt 让 LLM 做？"

| 答案 | 行动 |
|------|------|
| 能 → 这是 LLM 的活 | 删掉代码。prompt 里给的是分析目标和数据，不是 id→false 这种结论 |
| 不能（纯运算/IO/序列化）→ 代码的活 | 写代码，但确保不夹带业务判断 |
| 拿不准 | 默认是 LLM 的活（LLM 主导是项目第一原则） |

> **问题 2**："我正在拼装传给 LLM 的 messages——我是在追加信息，还是在筛选/删减/重排信息？"

| 答案 | 行动 |
|------|------|
| 筛选/删减/重排 → 你在替 LLM 决定它应该看到什么 | 删掉。走 `build_messages()`，只追加不筛选 |
| 追加 → 可以 | 确保用 `build_messages()` 而非直接构造 messages |
| 不确定 | 走 `build_messages()`——它是唯一合法的 messages 构造入口 |

## hagoku/ — HaGoKu Studio 多 Agent 数据分析平台

> 项目灵魂、Agent 表、架构原则、命令参考、技术栈 → 见 **[PROJECT.md](PROJECT.md)**（唯一真相源）。
> 文档索引、环境变量 → 见 **[DEV.md](DEV.md)**。

### 当前架构关键点（已实施的 P0 项）

**结构化输出解析器（P1.2）**：`hagoku/guardrails/parsers.py`
- `parse_pvalue()`、`parse_effect_size()`、`parse_conclusion_count()`、`parse_confidence_interval()`
- `validate_analysis_output()` 综合 4 项检查
- Reporter 需调用解析器验证 Analyst 输出结构完整性

**Orchestrator 看板**（Step 4，2026-06-06 取代原 Scribe Agent）：kanban.db 状态机（7 状态）+ 事件驱动 promote 已内联到 `Orchestrator` 类内部。4 agent 通过 `orchestrator.block_task` / `orchestrator.unblock_task` 控制门控。原 `_scribe/` 目录已删，4 通道文件（process_log.md / context.md / handover_notes.md）已删。详见 `docs/superpowers/plans/scribe-redesign-brief.md` 结论段。

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