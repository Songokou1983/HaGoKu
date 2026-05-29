# HaGoKu 开发任务简报 — 给 AI 实现者的提示词模板

本文件提供三种**复制粘贴即用**的提示词，按场景选用。
所有场景的核心目的：**防止 AI 实现者在写代码时悄悄加硬编码**。

---

## 场景 A：长任务起手（最常用）

> 复制下方整段，粘贴到与 AI 助手（Claude/Cursor/Codex/Cascade 等）的对话开头，
> 然后再描述具体任务。

```
你正在为 HaGoKu Studio 项目工作。开始任何代码动作前，请先做这两件事：

1. 读完仓库根目录的 AGENTS.md
2. 读完 PROJECT.md 的三个章节：
   - §「代码边界」（哪些事 LLM 干、哪些事代码干）
   - §「通道完备性十律」（10 条正向契约）
   - §「失败处理」§「代码层合法动作清单」（LLM 失败时唯一允许的代码动作）

【项目铁律 — 你违反任何一条，PR 直接拒】

铁律 1（零硬编码）：任何"业务概念分类 / 自然语言意图判断 / 中文同义识别"
  必须由 LLM 完成。代码不准做。如果你想写：
    - ["收入", "营收", "销售额", ...] 这样的关键词列表
    - re.search(r"收入|营收|销售", text) 这样的中文语义正则
    - if intent == "预测" elif intent == "对比" 这样的中文 if-elif 链
    - 函数名带 _infer_/_detect_/_classify_ 但内部没调 LLM
  → 全部禁止。停下来想：这个判断能不能写成一句中文，让 LLM 拿到分析目标和数据后自己判断？
    能 → 说明 LLM 不需要你帮它——删掉这条规则，代码和 prompt 里都不要有。
       「写到 prompt 里」≠ 把 id→false 从 .py 搬到 system prompt。是在 prompt 里给 LLM 分析目标和数据，不是替它写好结论。
    不能（纯运算/IO/序列化）→ 才允许写代码。

铁律 2（LLM 失败的唯一合法路径）：当 LLM 调用失败时，你只能做四件事：
  A. raise RuntimeError(...) — LLM 不可达 / 通道异常时
  B. 写 ctx["_last_understanding_failure"] = {raw_text, ...} 然后 return [] —
     LLM 调用成功但没产生有效工具调用时
  C. 落地能落的工具调用，未落的留空 — LLM 给出部分输出时
  D. 拒绝写入权威结构（同 B） — LLM 输出与原话明显矛盾时
  禁止写：except: return [] / except: return None / 默认值兜底 / 缓存+规则降级。

铁律 3（提交前自检）：完成任何代码改动后，必须跑过这三组测试。任一变红 = 改坏了：
    .venv/bin/python -m pytest tests/test_doctrine_compliance.py -q
    .venv/bin/python -m pytest tests/test_product/test_information_arrival.py -q
    .venv/bin/python -m pytest --tb=short -q

【你的常见错误模式 — 每次都会犯，请警惕】

- 测试不绿 → 你的本能：加规则让它绿。
                正确做法：检查是不是 prompt 写错了 / 工具 schema 不全。
- LLM 调用失败 → 你的本能：加 except 兜底。
                正确做法：raise RuntimeError 让用户看见。
- 看到字段名（"收入"/"销售额"）→ 你的本能：加 dict 映射。
                正确做法：让 LLM 用 _resolve_to_column_names 之类的工具映射。
- 防御性编程 "万一 LLM 返回空"→ 你的本能：加默认值。
                正确做法：写 _last_understanding_failure 让用户看到没理解。

【拿不准时问自己唯一一个问题】

  "这段代码做的判断，能不能用一句中文写成 prompt 让 LLM 做？"
  能 → LLM 的活，删代码。prompt 里给的是目标和数据，不是替 LLM 写好的结论。
  不能 → 代码的活，但确保不夹带业务判断。
  拿不准 → 默认是 LLM 的活（项目第一原则是 LLM 主导）。

【你的真实任务从下一段开始】
```

> 替换最后一行为你的具体任务描述（如「修复 docs/plans/foo.md 中描述的问题」）。

---

## 场景 B：单点修改（短提示，token 节省版）

> 当任务很小（修一行、加一个测试），可以用这个浓缩版。

```
HaGoKu 项目铁律：LLM 主导，零硬编码。代码只是通道+工具。

禁止：业务关键词列表、中文语义正则、中文 if-elif 链、_infer_/_detect_ 函数无 LLM 调用、
     except 静默吞失败（必须 raise RuntimeError 或写 _last_understanding_failure）。

提交前必跑：pytest tests/test_doctrine_compliance.py

拿不准时：LLM 拿到目标和数据后能自己判断吗？能 → 代码和 prompt 里都别替它写结论。

任务：[在此描述]
```

---

## 场景 C：代码评审 / 审计他人 PR

> 当你让 AI 帮你审 PR diff 是否违反 doctrine 时使用。

```
请审核以下 HaGoKu 项目的 diff，按这五条 doctrine 标准判断每处变更：

1. 是否引入了业务关键词字面量列表（["收入"/"营收"/...]）？
2. 是否引入了中文语义正则（re.search(r"概念A|概念B|...", ...)）？
3. 是否引入了中文字符串的 if-elif 分类链（≥3 分支）？
4. 是否新增了 _infer_/_detect_/_classify_ 命名的函数但函数体内无 LLM 调用？
5. 是否在 LLM 调用的 except 块直接 return [] / return None 而无 raise / 未理解信号？

对每处变更给出判定：
  ✅ 合规 — 简述为何属于"代码合法职责"
  ❌ 违规 — 指出违反第几条，建议修法（让 LLM 做 / raise / 写 _last_understanding_failure）
  ⚠️ 可疑 — 需人工裁定

最后给一句总结：通过 / 退回。

Diff:
[在此粘贴 diff]
```

---

## 怎么用这些提示词

| 场景 | 推荐用法 |
|------|---------|
| 你雇的开发者用 AI（Cursor / Claude Desktop / Codex） | 把场景 A 设为他们与 AI 对话的**项目级 system prompt**（Cursor `.cursorrules` / Claude Project instructions） |
| 你自己用 Cascade（Windsurf 内置） | 已经覆盖：`AGENTS.md` 在仓库根目录，Cascade 进仓库自动读取 |
| 给 GPT/Claude 临时跑一个改动 | 复制场景 B，省 token |
| 让 AI 审你不放心的 PR | 复制场景 C |

---

## 推荐的项目级配置（一次配好，长期生效）

### Cursor 用户

把场景 A 的内容存为 `.cursorrules`（仓库根目录），Cursor 会自动注入每个会话。

### Claude Code / Claude Desktop 用户

把场景 A 设为 Project Instructions。`AGENTS.md` 已存在，Claude 会自动识别。

### Cascade（Windsurf）用户

`AGENTS.md` 已落地，无需额外配置。

### Codex / Aider / 其他

把场景 A 存为 `~/.config/your-tool/system-prompt.md`，每次启动时加载。

---

## 关于这套防御为什么有效

死循环的根因是 **AI 实现者每次都"无记忆地"重新违反规则**。三道防线：

1. **进仓库时**：`AGENTS.md` 让 AI 看到铁律
2. **写代码时**：上面的提示词让 AI 自检
3. **提交前**：`tests/test_doctrine_compliance.py` 机器拦截

任意一道防线漏过，下一道兜底。**只要白名单 `_KNOWN_LLM_EXCEPT_VIOLATIONS` 不被随便添加**，
新增硬编码无法通过 CI——AI 实现者必须删掉重写。

---

## 一句话告别

> 与其指望 AI"理解你的哲学"，不如把哲学变成它**绕不过去的红线**。
> 这套提示词就是红线本身。
