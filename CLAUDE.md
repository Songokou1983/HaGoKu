# CLAUDE.md

## 这个项目只做两件事

1. **完整信息传递** — LLM 收到的数据必须和用户给的一样。不截断，不摘要，不代劳。
2. **提供工具** — 工具是 LLM 的物理延伸。通用、批量、不替 LLM 做判断。

prompt 越短越好，工具越少越好，数据越完整越好。

**提示词改一行，LLM 行为全变。顺序决定优先级——LLM 先看到什么就先做什么。改前 dump，改后 dump，对比。**

## 本次大修的教训（2026-06-18，12小时，30+ commits）

### 1. 工具设计决定 LLM 行为
- 一次一列 → LLM 被迫选 markdown。批量 → LLM 自然调 `set_columns`
- `grep` 搜 LLM 自己输出而非原始数据 → LLM 调 5 次全空。删
- 知识不是工具。ROI 公式在 LLM 训练数据里，不需要包成 `calc_roi`
- 36 工具 → 16 工具。和 Reasonix 一样：通用、批量、不替 LLM 判断

### 2. 提示词：不写工具名，不写"禁止"
- 工具名放在 tool schema（API 自动传），不在 prompt 里重复
- 顺序很重要：任务在前，角色在后
- "禁止"规则是掩盖 mismatch——先查 mismatch 再决定是否加规则
- 最终 prompt：15行，四个阶段目标描述，零工具名

### 3. 信息通道：每一个出口都检查
- `scout_msg` 被计算但 `return` 硬编码覆盖 → LLM 文本丢失
- `_handle_scout_reply` emit 空 `{"message":""}` → 前端收不到
- 跟进轮 batch 调用不走流式 → 文本走 `_scout_text` → `message`

### 4. 不兜底，不填坑
- 不替 LLM 生成字段表（删 `_build_basic_from_column_info`）
- 不循环检查 `column_semantics`（LLM 自己决定何时调工具）
- 跟进行为从 `if` 改 `while`——给轮次，不给指令

## ⛔ 改代码前必须有这四行

```
1. dump:   <paste exact dump content, line numbers>
2. path:   <file:line → file:line → breakpoint>
3. gap:    <what LLM received vs what it should have received>
4. exists: <this system already handles this at file:line — yes/no>
```

**没有这四行 → 没有 edit_file。没有例外。没有"我先改着"。**

## ⚡ 系统架构（改代码前必须知道）

- **单 Agent**：`DataAnalystAgent`，4 关注点（理解字段/评估清洗/跑统计/写报告）
- **单入口**：`to_messages_for_llm()` → `build_messages()`，唯一 LLM 消息构造路径
- **对话循环**：`run_step()` 已含工具调用→dispatch→回传→继续的完整循环。不要自己写
- **流程控制**：LLM 通过 `route_to` 决定阶段切换，代码不做 if-elif 阶段判断
- **代码只做机械执行**：不替 LLM 做语义判断，不加"禁止"堵行为
- **PROJECT.md** = 设计真相来源

---

## 铁律（违反 = 无效）

| # | 规则 | 一句话 |
|---|------|--------|
| 0 | 查 dump 再开口 | `ls -lt ~/.hagoku/llm_dumps/ \| head -5`，贴证据 |
| -2 | 用户确认前禁止改代码 | 报根因 + 方案 → 等用户说"修" → 才动 |
| -3 | 禁止无证据归因外部 | 不说"可能是模型问题"——贴 dump 行号 |
| -4 | 禁止绕过已有诊断 | dump 没读完不准加新日志 |
| 1 | 零硬编码语义 | 关键词列表/中文if-elif/regex → 全禁 |
| 7 | 失败在场 | LLM失败 → `raise RuntimeError`，不except兜底 |
| 9 | 配置中性 | 不写死模型名/URL/端口 |
| 10 | 提示词修改慎重 | 改 prompt 必须：开dump→定位→最小改→dump对比 |
| 11 | 提示词不预设结论 | 说"你面对什么"✅ 说"你应该得出什么"❌ |

---

## 刹车（最常犯的排前面）

| 刹车 | 触发词 | 一句话 |
|------|--------|--------|
| **F** | "可能是模型的问题" | 默认假设代码/prompt/通道有bug，归因LLM必须带代码证据 |
| **G** | prompt里出现"禁止/不要/不准" | 先查mismatch：prompt说的工具真能用吗？字段真传到了吗？修mismatch，不加禁止 |
| **C** | `setdefault` / `.get("role","feature")` | LLM没给的值代码不准填 |
| **D** | `_scout_text` → payload → message | LLM文本直接送前端，不经过代码多层周转 |
| **E** | 改完代码 | 跑 `bash scripts/ci/self_check.sh` 全部通过才提交 |

---

## 触发词速查

| 你在写 | 违反 |
|--------|------|
| `except: return []` / `except: return None` | 铁律 7 |
| `["收入","营收"]` / `re.search(r"收入\|销售")` | 铁律 1 |
| `setdefault("used_in_analysis", True)` / `.get("suggested_role", "feature")` | 刹车 C |
| `_scout_text` / 多层包装LLM输出 | 刹车 D |
| prompt里「必须判断为」「应该理解成」「不要分析」 | 铁律 11 |
| prompt里「禁止」「不要」「不准」 | 刹车 G |
| `@lru_cache` 装饰 LLM 调用 | 铁律 7 |

---

## 常见错误 → 正确做法

| 本能 | 正确 |
|------|------|
| 测试不绿 → 加规则 | 查 prompt/tool schema |
| LLM 行为不对 → 加「禁止」「不要」 | 查 mismatch——prompt 说能用的工具真能用吗？ |
| LLM 失败 → except 兜底 | `raise RuntimeError` |
| 觉得 prompt 啰嗦 → 精简 | 不动（铁律 10） |

---

## 项目

**HaGoKu Studio — 1 个数据分析师 + 专业工具箱**（Phase D 已完成 4 agent 合 1）。详见 [`PROJECT.md`](PROJECT.md)。

## 已由架构自动守门（不需人记）
- `build_messages()` 唯一入口 → pre-commit hook 自动拦截
- `to_messages_for_llm()` 统一 LLM 调用 → agent 内无法直接构造 messages
- `route_to` 阶段切换 → 代码无 if-elif 中文分支

## 开发背景 — 全程 AI 协作

### 协作模型（三个角色）

| 角色 | 干什么 | 不干什么 |
|---|---|---|
| **用户** | 决策、逻辑 QA、细节指挥 | 不写代码、不读语法细节 |
| **代码-AI** | 写代码（**用户的日常搭档**）| 不自己定方案，听用户+问题-AI 反馈 |
| **问题-AI** | 找问题 + 被问时给建议 | 不写代码、不主动给 ABCD 选项菜单 |

### 用户的实际能力

- ❌ 不会写代码
- ✅ 基本代码逻辑有感觉——经常在代码-AI 写的时候就看出问题
- ✅ 能从用户可见行为推断系统问题
- ✅ 能直接指挥细节
- ⚠️ 不能读代码语法细节——但能读懂逻辑层描述

### 为什么规则这么严

铁律、刹车不是品味——是"AI 不约束就会犯的错"的反模式清单。核心：AI 的本能是"帮用户干活"——本项目的"帮"=**让 LLM 自己判断 + 让代码做机械执行**。AI 一旦越界做判断，整个架构的"LLM 自主"前提就塌了。

### 验证协议

1. 重启 desktop
2. 跑一次 run
3. 把 `run.log` + `ls llm_dumps/` + 关键 dump 复制给问题-AI
4. 问题-AI 看 dump 验证：现象是否消失 / 是否引入新问题

**没验证 = 没改完**。

### Prompt 修改的 cascade 效应

**原则**：每条 prompt 改动**单独看都合理**——**组合起来**才能解释 LLM 行为。**不是加法，是乘法**。

**反例（121412 → 124238 → 134226 倒退链）**：
- 加 C1-C5 "工作方式" 段 → LLM 进入"多轮规划"模式
- 加 "工具段"（带参数签名）→ LLM 知道"我有工具"
- 加 "字段更新铁律" → LLM 觉得"调完工具才出表"
- 加 "工具是给你用的" → LLM 觉得"应该调工具"
- d989a5d 给第一轮 tools → LLM **真的去调**
- 组合效果：LLM 在第一轮**调 17 个工具 + 5 个空匹配 grep + 不出表**

**隐藏原因 — prompt 顺序**：
- "用工具"暗示在 system message 前段（line 4）
- "出表"指令在后段（line 7+）
- LLM 训练里有"工具可用就用"的强倾向（agent RLHF）
- **早出现的指令压晚出现的**——出表指令被埋没

**问题-AI 给 prompt 建议时**：
- ❌ "加这条规则处理 X"（只看单独）
- ✅ "这会让 LLM 偏向'调工具'，需要把'出表'指令移到顶部"
- ❌ "prompt 没问题，是模型差"（云端大模型通常不是）
- ✅ "prompt 结构压住了模型的自然判断"
