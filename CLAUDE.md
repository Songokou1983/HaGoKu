# CLAUDE.md

## 调试铁流程（出错/停住/行为不对时，必须按顺序执行，不许跳步）

```
步骤 0: 读 dump + 读日志（两者缺一不可）
   ls -lt ~/.hagoku/llm_dumps/ | head -5
   tail -30 /tmp/hagoku.log
   ↓ 贴出来，说明你看到了什么

步骤 1: 定位断点
   从 dump 里回答三个问题：
   a) LLM 收到的 messages 最后一条是什么？（用户说了啥？）
   b) LLM 的 response 是纯文本还是有 tool_calls？
   c) 如果有 tool_calls，是哪些？如果没有，为什么没有？
   ↓ 写出你的判断

步骤 2: 对照代码路径
   根据步骤 1 的结论，追踪代码中对应的处理路径：
   - tool_calls 存在 → run_step 循环是否正确 dispatch？
   - tool_calls 不存在 → handler 走到了哪个分支？返回了什么？
   - route_to 存在 → orchestrator 是否正确执行了切换？
   ↓ 指出具体行号

步骤 3: 报根因
   用一句话说清楚：「X 导致了 Y」
   禁止：「可能是…」「也许…」「试试…」

步骤 4: 提方案（不动手）
   说改哪里、改什么、预期效果
   等用户说"改"才动手
```

**违反此流程的行为**：
- ❌ 不看 dump 就说"我来修一下"
- ❌ 不看日志就说"后端没问题"
- ❌ 看了 dump 但不贴证据就下结论
- ❌ 加日志代替读 dump（铁律 -4）
- ❌ 说"可能是模型问题"（铁律 -3 / 刹车 F）
- ❌ 改了代码不验证就说"应该修好了"

---

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
- 36 → 16 → 15 工具。工具三问：LLM 自己能做吗？描述里有"何时用"吗？同一件事几个入口？
- 工具描述只写"我做什么"，不写"你什么时候该用我"——后者是 prompt 的事
- 详见 `docs/TOOL_DESIGN.md`

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

### 5. run_step 多轮循环：每轮必须对称检测控制工具（2026-06-21）
- `run_step` 第一轮检测 `route_to` / `submit_*` → 正确提取
- 第二轮（LLM 看到工具结果后再回复）只做普通 dispatch → **控制工具被丢弃**
- LLM 最自然的路径："调 `set_columns` → 看成功 → 调 `route_to`"永远不生效
- **通道里每个出口必须有相同检测能力。不对称 = 控制权只通了一半**

### 6. 写入单点化：add_user_feedback 只能有一个入口（2026-06-21）
- `respond()` 外层写一遍 + handler 内部写一遍 → 用户每句话在历史出现两遍
- 递归 `respond()` 又写一遍 → 三遍
- **信息写入和信息读取一样，必须有唯一入口**（读取已有 `to_messages_for_llm()`）

## ⛔ 改代码前必须有这四行

```
1. dump+log: <paste exact dump content + log key lines, line numbers>
2. path:   <file:line → file:line → breakpoint>
3. gap:    <what LLM received vs what it should have received>
4. exists: <this system already handles this at file:line — yes/no>
```

**没有这四行 → 没有 edit_file。没有例外。没有"我先改着"。
违反 → commit-msg hook 拦截。edit_file 前必须先有 read_file/grep。
每次对话开始必须先 /hagoku-iron-laws。**

## ⚡ 系统架构（改代码前必须知道）

- **单 Agent**：`DataAnalystAgent`，4 关注点（理解字段/评估清洗/跑统计/写报告）
- **单入口**：`to_messages_for_llm()` → `build_messages()`，唯一 LLM 消息构造路径
- **对话循环**：`run_step()` 已含工具调用→dispatch→回传→继续的完整循环。不要自己写。**每轮都必须对称检测控制工具**
- **流程控制**：LLM 通过 `route_to` 决定阶段切换，代码不做 if-elif 阶段判断
- **代码只做机械执行**：不替 LLM 做语义判断，不加"禁止"堵行为
- **流程保障 ≠ 替代决策**：数据分析有固定骨架（加载→画像→理解字段→清洗→分析→报告）。代码确保每步发生，LLM 决定每步的内容。`run_scout_phase` 调 load_data → generate_profile → 调 LLM 推断字段 是流程保障，不是越界
- **通道铁律**：代码可以做一切辅助（透传/工具/日志/dump/校验），只要不做决策、不碰 LLM 输出。删掉代码后用户看到的内容不变 → 通道。变了 → 越界。
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
| **D** | 代码"搬运"LLM文本 | LLM流式已经送达前端。禁止从context/column_semantics取LLM文本，通过事件/返回值再发一次。删掉搬运代码用户看到的不变→搬运。变了→原有通道断裂 |
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

## 反模式经验录 → [docs/CHANNEL.md](docs/CHANNEL.md)

反复出现的错误模式：搬运 LLM 文本、只流式第 1 轮、代码替 LLM 做阶段决策、守门太窄。

## 常见错误 → 正确做法

| 本能 | 正确 |
|------|------|
| 测试不绿 → 加规则 | 查 prompt/tool schema |
| LLM 行为不对 → 加「禁止」「不要」 | 查 mismatch——prompt 说能用的工具真能用吗？ |
| LLM 失败 → except 兜底 | `raise RuntimeError` |
| 觉得 prompt 啰嗦 → 精简 | 不动（铁律 10） |

---

## 项目

**HaGoKu Studio — 用本地模型做专业级商业分析**（单 DataAnalystAgent + 15 工具 + Session 会话）。详见 [`PROJECT.md`](PROJECT.md)。

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
