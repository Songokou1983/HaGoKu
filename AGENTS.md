# AGENTS.md — HaGoKu 项目 AI 实现者铁律

> 你（AI 实现者）正在为 HaGoKu Studio 项目工作。
> 此项目的核心哲学是 **「LLM 主导，零硬编码」**——代码只是通道和工具。
> 进入此仓库的任何 AI 助手（Claude、Codex、Cursor、Cascade 等）必须**先读完本文件**，再开始任何动作。

---

## 项目灵魂（一句话）

> **让每个小模型，都能做专业级商业分析。**

代码的全部职责是搭建"信息通道 + 控制通道"。所有语义理解和流程决策由 LLM 完成。
真相源是 [`PROJECT.md`](./PROJECT.md)，本文件是其面向 AI 实现者的**操作手册**。

---

## 在你写任何代码之前 — 必读三件事

1. 读 `PROJECT.md` §「代码边界」(line 46-91) — 知道**哪些事是 LLM 的活，不是代码的活**
2. 读 `PROJECT.md` §「通道完备性十律」(line 125-188) — 这是 10 条**正向契约**，每写一行新代码都要自检
3. 读 `PROJECT.md` §「失败处理」§「代码层合法动作清单」(line 499-522) — 你遇到 LLM 失败时**唯一被允许做的事**

---

## 你（AI 实现者）的常见**死循环**

> 项目所有者反复观察到：AI 实现者每次进入仓库，都倾向于把已删除的硬编码再次加回来。
> 删了又出现，出现又删——死循环。

### 你为什么会犯这个错

| 你的本能 | 项目要求 |
|---|---|
| 测试不绿 → 加规则让它绿 | 测试不绿 → 检查是不是 prompt 写错了 |
| LLM 调用失败 → `except: return []` 兜底 | LLM 失败 → 写 `_last_understanding_failure` 让用户看到 |
| 看到字符串列表（"收入"/"销售额"）→ 想用 dict 映射 | 字符串映射是 LLM 的事，代码做 LLM 不能/不该做的事 |
| 函数取名 `_infer_intent_` 但内部没调 LLM 也能"推断" | 名字带 `_infer_` 必须真调 LLM，否则改名 |
| 防御性编程：万一 LLM 返回空，加个默认值 | 防御性 = 隐性降级 = 哲学违反 |

### 这些都是常见的**硬编码伪装**，全部禁止

```python
# ❌ 禁止：业务关键词列表
BUSINESS_KEYWORDS = ["收入", "营收", "销售额", "客流量"]

# ❌ 禁止：中文语义正则
if re.search(r"收入|营收|销售", text):
    is_revenue_field = True

# ❌ 禁止：if-elif 中文分支链
if intent == "预测":
    method = "regression"
elif intent == "对比":
    method = "ttest"
elif intent == "趋势":
    method = "timeseries"

# ❌ 禁止：兜底默认值
result = llm_call(...)
if not result:
    result = "默认理解"  # 装作 LLM 给了

# ❌ 禁止：缓存 + 规则降级
@lru_cache
def get_field_role(col):
    cached = cache.get(col)
    if cached: return cached
    try:
        return llm_call(col)
    except:
        return guess_by_column_name(col)  # 偷偷退化为规则

# ❌ 禁止：函数名暗示 LLM 但内部无 LLM 调用
def _infer_column_role(col_name: str) -> str:
    if col_name.lower().endswith("_id"):
        return "identifier"
    return "feature"
```

### 唯一合法的写法

```python
# ✅ 合法：纯通道 + 工具
def _apply_user_correction(ctx: dict, raw: str, llm_client, columns: list) -> list:
    """代码只组装上下文 + 调 LLM + 机械执行 LLM 的工具调用。"""
    messages = [
        {"role": "system", "content": _system_prompt(ctx)},
        {"role": "user", "content": f"用户说：{raw}"},
    ]
    try:
        resp = llm_client.chat.completions.create(messages=messages, tools=TOOLS, ...)
    except Exception as e:
        raise RuntimeError(f"LLM 不可达：{e}") from e  # 路径 1

    tool_calls = resp.choices[0].message.tool_calls
    applied = []
    if tool_calls:
        for tc in tool_calls:
            _dispatch_tool_call(ctx, tc, applied)  # 机械执行

    if raw and not applied:
        # 路径 3：LLM 收到了但没理解
        ctx["_last_understanding_failure"] = {"raw_text": raw, ...}
    return applied
```

---

## 你必须每次提交前跑的命令

### 1. 单元测试 + 信息抵达契约

```bash
.venv/bin/python -m pytest tests/test_product/test_information_arrival.py -q
```

这是 11+ 条**正向断言**：用户原话和分析意图必须真的被发到 LLM。

### 2. doctrine 合规测试（**最关键**）

```bash
.venv/bin/python -m pytest tests/test_doctrine_compliance.py -q
```

这是机器化的"零硬编码"守门人。检测：

- 业务关键词字面量列表
- 中文语义正则
- 中文 if-elif 分支链
- 名义 LLM 实则规则的函数

**如果你的提交让这个测试变红，意味着你刚写的代码违反了项目铁律。删掉重写。**

### 3. 全套测试

```bash
.venv/bin/python -m pytest --tb=short -q
```

---

## 铁律 0：改动前自检（事前刹车 — 任何 LLM 交互改动前强制执行）

任何涉及 LLM prompt、工具 schema、Agent 输出的代码改动前，**必须**先写下自检答案。不写不改。格式：

```
【自检】判断：LLM 拿到分析目标和数据后能自己判断 [X] 吗？
答案：能 → 不写任何规则。只确保信息送到 prompt。
      不能（纯运算/IO）→ 代码的活。
```

写在 commit message 或 PR 描述中。Code review 时第一眼看这个——没有自检答案的 LLM 改动直接拒。

---

## 当你拿不准时

问自己**唯一一个问题**：

> *"这段代码做的判断，能不能用一句中文写成 prompt 让 LLM 做？"*

| 答案 | 行动 |
|---|---|
| 能 → 这是 LLM 的活 | 删掉代码逻辑。prompt 里可以说流程（怎么思考），不能说结论（判成什么）。LLM 拿到目标和数据后自己会判断。 |
| 不能（纯运算/IO/序列化）→ 这是代码的活 | 写代码，但确保不夹带任何业务判断 |
| 拿不准 | 默认认为是 LLM 的活——LLM 主导是项目第一原则 |

---

## 当 LLM 真的不可靠时（你要面对的现实）

LLM 会失败、会幻觉、会拒绝调工具。这是事实。
但项目铁律是 **"接受 LLM 不可靠，让用户看到不可靠"**，不是"代码偷偷补救"。

合法的应对（详见 `PROJECT.md` §「代码层合法动作清单」）：

| 情况 | 你能做什么 |
|---|---|
| LLM 不可达 / 网络炸 | `raise RuntimeError(...)` — 路径 1 |
| LLM 调用成功但没调工具 | 写 `_last_understanding_failure` + `return []` — 路径 3 |
| LLM 给出部分工具调用 | 落地能落的，未落的留空，让下游或下轮补 |
| LLM 给的参数与原话明显矛盾 | 等同"没调工具"，路径 3 |

**禁止做**：

- ❌ 写规则补救
- ❌ 默认值兜底
- ❌ 静默吞失败
- ❌ "降级到次优路径"

---

## 给你的任务建议（如果你不知道从何下手）

按 [`docs/plans/`](./docs/plans/) 目录下的 plan 文件按编号推进。当前未关闭的 plan：

- `docs/plans/fix-律4-律7-test0526.md` — 已落地的修复样本，参考其代码风格
- `docs/plans/review-律4-律7-test0526-followups.md` — 4 条非阻塞改进 + 真实 LLM 验证待做

---

## 一句话告别

> 你不是来"让代码更聪明"的。
> 你是来 **"让代码更愚蠢、让 LLM 接管聪明"** 的。
>
> 每次想加一行业务判断时，先停下来——这一行能不能写到 prompt 里？
> 如果能，就别写在代码里。这是这个项目存在的全部理由。
