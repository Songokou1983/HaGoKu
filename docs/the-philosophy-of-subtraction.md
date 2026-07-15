# The Philosophy of Subtraction · 减法的哲学

> How a non-programmer used AI-to-AI review to discover ten engineering principles of AI development
> 一个不会写代码的人，如何用 AI 互相审查，发现 AI 开发的十条工程学理念

---

## Prologue: The Inner Journey · 序言：心路历程

### Stage 1: Euphoria / 第一阶段：狂喜 (5/1—5/3)

"I can really build something complete with AI."

12 commits assembled a multi-agent platform. Every step felt like magic — say "add a Reporter" and the AI adds one. No ceiling in sight. You didn't know how much pain those agents would cause later. You only knew they ran.

**Key psychology: unconditional trust in AI.** AI wrote 86,000 lines of code. You had no idea how many would later be deleted.

"我真的能用 AI 做一个完整的东西。"

12 个 commits 搭出了一个多 Agent 平台。每一步都像变魔术——你说"加一个 Reporter"，AI 就加一个。感觉没有上限。你不知道这些 Agent 以后会让你多痛苦，你只知道"它们跑起来了"。

**关键心理：对 AI 的信任是无条件的。** AI 写了 86,000 行代码，你不知道里面有多少是将来要删的。

---

### Stage 2: Inflation / 第二阶段：膨胀 (5/4—6/10)

"Everything can be added!"

Streamlit Web UI, React rebuild, knowledge base, Doctor diagnostics, 44 tools, dual LLM. 78 commits on a single day. You felt like you were flying.

In reality, you were laying the foundation for every pitfall to come. You just hadn't seen what those pitfalls looked like yet.

**Key psychology: quantity = progress.** You didn't even have the concept of "architecture."

"什么都能加！"

Streamlit Web UI、React 重建、知识库、Doctor 诊断、44 个工具、双层 LLM。有一天 78 个 commits。你觉得"我们在飞速前进"。

实际上你正在踩未来所有坑的地基。只是当时你还没见过这些坑长什么样。

**关键心理：量 = 进步。** 你甚至没有"架构"这个词的概念。

---

### Stage 3: Silent Collapse / 第三阶段：沉默的崩塌 (6/11)

"Why did it come to this."

44 days of accumulated complexity erupted simultaneously. Fix one thing, break three. The system became uncontrollable in your hands.

You made a decision you didn't yet know was critical: **delete.** 4 Agents → 1 Agent. Dual LLM deleted. KanbanDB deleted. CLAUDE.md slashed from 520 lines to 67.

**Key psychology: the first time you said no to AI's suggestions.** Not to a specific suggestion — to the entire premise that "multi-agent is the right architecture." AI can stack blocks. Judging whether the tower stands is your job.

"为什么会变成这样。"

44 天积累的复杂度在一个点上同时爆发。修一个地方坏三个地方。系统在你手上变得不可控。

你做了一个当时不知道有多重要的决定：**删。** 4 Agent → 1 Agent。双层 LLM 删了。CLAUDE.md 从 520 行砍到 67 行。

**关键心理：第一次对 AI 的建议说不。** 不是某个具体建议——是对整个"多 Agent 是正确方案"的假设说不。AI 可以搭积木，但评判积木搭得好不好是你的活。

---

### Stage 4: Channel Awakening / 第四阶段：通道觉醒 (6/12—6/22)

"Code should not make any decisions for the LLM."

The most painful ten days. Every step forward overturned the previous day's work. June 18: six reversions in a single day. Added a loop — reverted. Added tool restrictions — reverted. Added field generation — reverted. Each addition felt logically correct at the time. Each reversion revealed the same flaw: **code was thinking for the LLM instead of letting the LLM think for itself.**

The iron laws, brakes, and trigger words born in this phase are not "knowledge acquired" — they are "finally being able to articulate that wrong feeling."

**Key psychology: from "AI, help me" to "AI, stop helping without being asked."** You stopped asking AI "how do I fix this bug" and started asking "what message did the LLM receive before this bug occurred" — demoting AI from repairman to forensic tool.

"代码不该替 LLM 做任何决定。"

最痛苦的十天。每走一步都在推翻前一天的自己。6/18 一天六次撤回：加了循环、撤了。加了工具限制、撤了。加了字段生成、撤了。加的时候每次都觉得"这个逻辑对"，撤回的时候每次都觉得"这个逻辑对但方向错"。方向错在哪？**代码在替 LLM 出主意，而不是让 LLM 自己做判断。**

这个阶段诞生的铁律、刹车、触发词——不是"学到的知识"，是"终于能把那种不对的感觉说清楚了"。

**关键心理：从"AI 你帮我"变成了"AI 你别乱帮"。** 不再问 AI "你怎么修这个 bug"，而是问 AI "这个 bug 出现之前，LLM 收到了什么消息"——把 AI 从修理工降级为取证工具。

---

### Stage 5: Validation / 第五阶段：验证 (6/24)

"I can spot a patch at a glance now."

Same bug, same symptoms. AI proposed two patches. Day-5 you would have said "go ahead, merge." Today's you saw 15 lines of new code and went silent. Saw "add diagnostic logging" and became alert. Then demanded: **find the real root cause.**

Result: the real root cause was changing one number from `5` to `99`. Net deletion: 135 lines.

"我能一眼认出补丁了。"

同一个 bug，同样的症状，AI 给出了两个补丁。第 5 天的你会说"好，加进去"。今天的你看到 15 行新增，沉默了。看到"添加诊断日志"，警觉了。然后要求：**重新定位根因。**

结果：真正的根因是一个数字 `5` 改成 `99`。净删 135 行代码。

---

### Stage 6: Channel Purification / 第六阶段：通道终极化 (6/25)

"The boundary between code and LLM is finally clear."

Deleted the concept of "phase" from the code. Session.py's `infer_current_focus()` — gone. Agent.py's `phase_hint` injection — gone. The prompt's "current phase will be annotated" — gone. Frontend `STAGE_LABELS` — gone. **The code no longer knows, cares about, or tells the LLM "what phase you're in."**

The channel gained its positive/negative definition: code does what LLM cannot (computation, I/O) → channel completion ✓. Code guesses what LLM intends → violation ✗.

"代码和 LLM 的边界终于清楚了。"

删除阶段概念。session.py 的 `infer_current_focus()`——删。agent.py 的 phase_hint 注入——删。prompt 的"当前阶段会标注"——删。前端 STAGE_LABELS——删。**代码不再知道、不再关心、不再告诉 LLM"你在哪个阶段"。**

通道有了正反面定义：代码做 LLM 不能做的（纯运算、IO）→ 通道补全 ✓。代码替 LLM 猜意图 → 违轨 ✗。

---

### Stage 7: Channel Verified / 第七阶段：通道验证 (6/25 evening)

"On clean architecture, features stack linearly."

Same day. Morning: 30 commits, two reversions, deleting 87 lines — **cleaning.** Evening: 4 commits, zero reversions, adding 243 lines — **building.** Cleaning is the prerequisite for building. Not a sequence — a causal relationship. You cannot build on an unclean foundation.

"干净架构上，功能是直线累加。"

同一天。早晨：30 commits，两次撤回，删 87 行——**清理。** 晚间：4 commits，零撤回，加 243 行——**建设。** 清理是建设的前提。不是先后顺序——是因果关系。不清理就建设不了。

---

### Stage 8: Philosophy Validated / 第八阶段：哲学验证 (7/10)

"The channel is not a technical solution — it's a reproducible principle set."

Four milestones landed on the same day, each validating the channel philosophy from a different dimension: preset system (same channel, different prompt → three domains), JSON mode removal (code doesn't bind to model capabilities), Doctor operations manual (code doesn't hardcode rules), Doctor closed loop (LLM decides, code executes).

**Key psychology: from "I feel this is wrong" to "I can explain why, using principles."**

"通道不是一个技术方案——是一套可复现的原则。"

四个里程碑在同一天落地，各自从不同维度验证通道哲学：预设系统（同通道换提示词适配三领域）、删 JSON mode（代码不绑模型能力）、Doctor 操作手册（代码不硬编码规则）、Doctor 闭环（LLM 决定，代码执行）。

**关键心理：从"直觉觉得不对"变成了"能用原则解释为什么对"。**

---

This was never a detour. Your eyes can now recognize the potholes on both sides of the road. The first time, you walk through them on foot. The second, you drive past them. The third, you don't even notice them — because you no longer think of them as "road."

这不全是弯路。是你现在的眼睛能认出路两边的坑了。第一遍用腿走，第二遍用车开，第三遍你都不知道自己在绕坑——因为你已经不觉得那是路了。

---

## Chapter 1: Ten Engineering Principles · 第一章：十条工程学理念

HaGoKu: 69 days, ~1,110 commits, 26 reversions. From this data, ten transferable principles emerge. They are unrelated to Python, to data analysis, to WebSocket. They are the engineering science of building things with AI.

HaGoKu 69 天，~1,110 个 commits，26 次撤回。从这些数据里提炼出十条可迁移的理念。它们跟 Python 无关、跟数据分析无关、跟 WebSocket 无关。它们是"用 AI 建东西"的工程学。

---

### 1. Code Only Does What LLM Cannot · 代码只做 LLM 做不到的事

The positive/negative definition of the channel. Positive: load data, compute statistics, write files — things the LLM cannot do, code helps. Negative: guess phase, guess intent, guess state — things the LLM can judge for itself, code must not touch.

通道的正反面定义。正面：加载数据、计算统计、写文件——LLM 做不到的，代码帮你做。反面：猜阶段、猜意图、猜状态——LLM 自己能判断的，代码不准碰。

---

### 2. Fixing Is Subtraction · 修复是做减法

AI's instinct is to add conditions to eliminate symptoms. Real fixes produce *less* code — tearing down walls, not patching holes. In HaGoKu's history, every true advance resulted in a net line reduction.

AI 的倾向是加判断来消除症状。真正的修复产出的是更少的代码——拆墙，不补洞。HaGoKu 的历史中，每一次真正的进步结果都是代码量下降。

---

### 3. LLM Decides, Code Executes · LLM 决定，代码执行

Correct pause pattern: LLM calls `ask_user` → code breaks. Correct repair pattern: LLM outputs `[fix:xxx]` → code executes. LLM is active, code is passive. Code never guesses when the LLM should stop; never judges whether the LLM is "exploring."

正确的暂停模式：LLM 调 `ask_user` → 代码 break。正确的修复模式：LLM 输出 `[fix:xxx]` → 代码执行。LLM 主动，代码被动。代码不猜 LLM 什么时候该停、不判断 LLM 是不是在探索。

---

### 4. A Patch Is Not a Fix · 补丁不等于修复

Repeated problems in the same area → the architecture is wrong, not missing a patch. AI will never proactively say "this module should be rebuilt." You are the only one who knows "this area has been fixed N times."

同一功能区域反复出问题 → 架构错了，不是缺补丁。AI 永远不会主动说"这个模块该重建"。你是唯一知道"这里修过几次"的人。

---

### 5. You Are the Temporal Awareness Node · 你是时间感知节点

AI has no cross-session memory. Every new conversation, a bug is "the first time" to the AI. You are the only one with cumulative memory. You don't need to understand code — you need to remember "how many times has this area been fixed."

AI 没有跨会话记忆。每次对话，bug 对 AI 都是"第一次见"。唯一拥有累积记忆的是你。你不需要懂代码——你需要记得"这个区域修过几次"。

---

### 6. Every Reversion Is a Learning Event · 撤回是学习事件

Channel-violation reversions and protocol-debugging reversions differ in nature but share the same attitude: both demand gravity. A reversion that teaches nothing is the only kind that's wasted.

通道违轨撤回和协议调试撤回性质不同，但态度相同——每次撤回都应慎重。撤回了但没学到东西，才是真正的浪费。

---

### 7. Dirty Architecture Punishes Addition · 脏架构惩罚加法

In the feature explosion phase, 581 commits — every feature addition risked chain-collapse. After channel purification, multi-project support: 4 commits, zero reversions. Multi-sheet support: 14 commits, zero reversions. **Same act of adding features: exponential cost on dirty foundation, linear cost on clean foundation.**

功能爆炸期的 581 commits 每次加功能都可能触发连锁崩塌。通道净化后，加多项目 4 commits 零撤回，加多 Sheet 14 commits 零撤回。**同样加功能，脏架构成本指数增长，干净架构成本线性增长。**

---

### 8. Describe, Don't Prescribe · 描述，不规定

Tell the LLM what resources exist and what the goal is. Don't tell it "what you should do." A 15,520-byte prompt made the LLM call 17 tools without producing a table — because instructions fought each other, and order buried order. A 10-line prompt says only phase goals and available resources — the LLM finds its own path.

告诉 LLM 有什么资源和目标是什么。不告诉它"你应该怎么做"。15,520 字节的 prompt 让 LLM 调 17 个工具但不出表——指令打架，顺序压顺序。10 行的 prompt 只说阶段目标和可用资源——LLM 自己找路径。

---

### 9. Strengthen LLM = Give Tools, Not Knowledge · 增强 LLM = 给工具，不给知识

`calc_roi` was a wrong move — the ROI formula is in the LLM's training data; wrapping it as a tool is doing arithmetic for the LLM. `generate_report` was correct — writing an HTML file to disk is something the LLM cannot do. The 44→15 tool reduction was filtering out "false augmentation" and keeping "true augmentation."

`calc_roi` 是错误示范——ROI 公式在 LLM 训练数据里，包成工具是替 LLM 做算术。`generate_report` 是正确示范——写 HTML 文件到磁盘 LLM 做不到。44→15 工具的精简过程就是筛掉"错误增强"，保留"正确增强"。

---

### 10. Hardcoded Constants Are Hidden Patches · 硬编码常量是隐藏的补丁

`MAX_TOOL_ROUNDS = 5` looks like a "configuration." It's really code deciding how many rounds the LLM needs. Every hardcoded threshold, limit, or timeout is code guessing what the LLM requires — wrong guesses become bugs, and the distance between symptom (field table not displaying) and root cause (round limit) is vast.

`MAX_TOOL_ROUNDS = 5` 看起来像"配置"，实际是代码替 LLM 决定它需要几轮。所有硬编码的阈值、上限、超时，本质上都是代码在猜 LLM 需要什么——猜错了就是 bug，且症状和根因之间距离极远，极难定位。

---

## Chapter 2: Four Dimensions of the Channel · 第二章：通道的四个维度

The four milestones of v2.0.1 validated the same principle from four directions — each corresponding to a classic pattern of "code overstepping."

v2.0.1 的四大里程碑从四个方向验证了同一个原则——每个方向对应一种"代码越界"的典型模式。

---

### Dimension 1: Don't Bind to Model Capabilities · 维度一：不绑模型能力

`response_format=json_object` is OpenAI-specific. Depending on it = explosion when switching models. The fix was not "add a compatibility layer" — it was **delete the dependency on model-specific features.** The prompt says "please return JSON" instead. Code provides a universal channel.

`response_format=json_object` 是 OpenAI 专用功能。依赖它 = 换模型必炸。修复不是"加兼容层"——是**删掉对模型能力的依赖。** prompt 写"请返回 JSON"替代。代码提供通用通道。

---

### Dimension 2: Don't Hardcode Rules · 维度二：不硬编码规则

Doctor used a hardcoded fix lookup table. Replaced with reading an operations manual (`docs/doctor-operations.md`). The LLM reads the manual and decides autonomously. Code doesn't judge "which operation to use."

Doctor 原来用硬编码修复速查表。改为读取操作手册，LLM 根据手册内容自主决策。代码不替 LLM 做"该用什么操作"的判断。

---

### Dimension 3: Don't Distinguish Domains · 维度三：不做领域区分

Same engine, different prompt → three domains (general/stock/e-commerce). `_load_prompt()` reads from `~/.hagoku/active_preset`. One-click domain switch. **Simultaneously deleted the command panel** — code no longer guesses user intent; the LLM understands on its own.

同一个引擎，换一段 prompt → 三个领域（通用/股市/电商）。`_load_prompt()` 从 `~/.hagoku/active_preset` 读取，一键切换。**同步删除命令面板**——代码不再猜用户意图，LLM 自己理解。

---

### Dimension 4: Execute, Don't Decide · 维度四：只执行不决策

Doctor closed loop: LLM outputs `[fix:restore_default_prompt]` → code calls API → result appended to conversation. Isomorphic to "LLM calls `ask_user` → code breaks." Code acts only when the LLM issues an explicit directive. Never proactively decides.

Doctor 闭环：LLM 输出 `[fix:restore_default_prompt]` → 代码调用 API → 结果追加到对话。与"LLM 调 `ask_user` → 代码 break"是同构模式。代码只在 LLM 明确发出指令时行动，不主动决策。

---

## Chapter 3: Patchology — A Taxonomy of 26 Reversions · 第三章：补丁学——26 次撤回的分类学

### The Reversion Rate Curve · 撤回率曲线

| Period / 时期 | Rate / 撤回率 | Character / 特征 |
|------|--------|------|
| Feature explosion / 功能爆炸 | 1.7% | Didn't know they were mistakes / 不知道在犯错 |
| Channel purification / 通道净化 | 5.6% | Systematically finding violations / 系统性清除违轨 |
| Validation+Purification / 验证+终极化 | 6.4% | Concentrated phase/loop violation removal / 集中清除 |
| Construction phase / 建设期 | 1.6% | Violation reversions at zero / 违轨撤回归零 |

The purification phase had the *highest* reversion rate — because it was systematically discovering and removing violations. After cleanup, violation-type reversions dropped to zero.

通道净化期撤回率最高——因为正在系统性地发现和清除违轨代码。清除完毕后，违轨类撤回归零。

---

### Two Kinds of Reversions · 两种撤回

**Channel-violation reversions** (24): Code made a decision for the LLM. The fix is always deletion. **Protocol-debugging reversions** (4): Technical trial-and-error (WebSocket keepalive). Same gravity, different conclusion — violation reversions end in deletion; protocol reversions end in a different approach.

**通道违轨撤回**（24 次）：代码替 LLM 做了判断。修复方式永远是删代码。**协议调试撤回**（4 次）：技术问题试错（WebSocket keepalive）。同样慎重，但结论不同——违轨撤回后删代码，协议撤回归因是换方案。

---

### Patches on Patches · 补丁套补丁

June 24's "phase-hint mapping table" was the previous link in the chain that led to June 25's deletion of the entire phase concept. June 24 thought "the mapping is wrong." June 25 discovered "the idea of mapping is wrong." **If a fix makes you think "this feels off but works for now" — it's masking a real architectural problem, not solving it.**

6/24 的"阶段提示映射表"是 6/25 删掉整个阶段概念的上一环。6/24 以为是"映射错了"，6/25 发现是"映射这个想法本身就是错的"。**如果上一个修复让你觉得"有点怪但暂时能用"——它在掩盖真正的架构问题。**

---

## Chapter 4: The Iron Law System · 第四章：铁律体系

Iron laws = repeatedly verified rules with enforcement mechanisms. Six core laws selected, each with a real case.

铁律 = 被反复验证、有强制执行机制的规则。精选六条，每条附真实案例。

---

**Iron Law 0: Zero Hardcoded Semantics · 铁律 0：零硬编码语义**

Code performs no semantic judgment. `if "revenue" in text`, keyword lists, Chinese if-elif chains — all forbidden. LLM judgments must come only from LLM invocation results.

代码不做语义判断。`if "收入" in text`、关键词列表、中文 if-elif — 全禁。LLM 的判断只能来自 LLM 调用结果。

---

**Iron Law 1: LLM Failure Has Only Four Paths · 铁律 1：LLM 失败只能四条路**

A. `raise` B. Record understanding failure C. Partial landing D. Refuse write. Forbidden: `except` fallback, default values, cache degradation.

A. `raise` B. 记录理解失败 C. 部分落地 D. 拒绝写入。禁止 `except` 兜底、默认值、缓存降级。

---

**Brake C: Never Fill Default Values · 刹车 C：不准填默认值**

`setdefault("used_in_analysis", True)` — the LLM didn't provide this value; code must not supply it. Real case: `used_in_analysis` was derived as True by code, then reverted.

`setdefault("used_in_analysis", True)` — LLM 没给的值代码不准填。案例：`used_in_analysis` 被代码推导为 True 后撤回。

---

**Brake G: Never Write "Forbidden" · 刹车 G：不写"禁止"**

When "forbidden/don't/must not" appears in a prompt → first check the mismatch: can the tools the prompt references actually be called? Did the fields actually arrive? Fix the mismatch. Don't add prohibition.

prompt 出现"禁止/不要/不准"→ 先查 mismatch：prompt 说的工具真能用吗？字段真传到了吗？修 mismatch，不加禁止。

---

## Chapter 5: Operations Manual for Non-Programmers · 第五章：给非技术人的操作法

**Choose stepwise projects, not one-shot generation.** Every intermediate output must be visible and interruptible.

**选步进式项目，别选一次性生成。** 每一步产出你都能看懂、都能插嘴。

---

**Read the dump: the three-question localization method.** What did the user say last? What did the LLM respond? Were tools called? **Have the AI configure the dump on day one; you only need to `cat` a file.**

**读 dump：三问定位法。** 用户最后说了什么？LLM 回了什么？工具调用了吗？**第一天就让 AI 配好 dump，你只需 `cat` 一个文件。**

---

**AI reviews AI; you are the judge.** You don't need to understand code. You need to judge: "Has this pattern broken before?" Use a cheaper model for review.

**AI 互审，你做裁判。** 不需要懂代码，需要判断"这个模式之前真的坏过吗"。审查用便宜模型。

---

**Establish rules at the first repeated bug.** You don't know what rules are necessary at first success. But the second time the same type of error appears, you know it will return — that's when rules have teeth.

**第一次重复 bug 时立刻立规矩。** 功能第一次跑通你不知道什么规则必要。但同一类错误出现第二次时，你知道它会再来——那时候立的规矩才有针对性。

---

**The repetition principle.** Repeated problems in the same area → don't fix, rebuild the architecture. Have AI maintain a `CHANGES.md`. Same module appearing frequently → 🔴 → call halt.

**重复性原则。** 同一功能区域反复出问题 → 不修，重建架构。让 AI 维护 `CHANGES.md`。同一模块频繁出现 → 🔴 → 喊停。

---

**Beware "adding diagnostic logging."** AI's default when it can't find the root cause. Ask: "Without adding a single line of logging, what are the possible root causes of this bug?" — force reasoning mode, not patching mode.

**警惕"加诊断日志"。** AI 找不到根因时的默认反应。问 AI："在不加一行日志的前提下，这个 bug 的可能根因有哪些？"——强迫推理模式，不进补丁模式。

---

## Chapter 6: One Line · 第六章：一条线

If this project must be summarized in one sentence, it is not "built a data analysis tool" — it is **used 1,110 commits to strip code from "doing everything for the LLM" down to "doing only what the LLM cannot."**

如果用一句话总结这个项目，不是"做了一个数据分析工具"——是**用 1,110 个 commits 把代码从"替 LLM 做一切"剥成了"只做 LLM 做不到的事"。**

```
Away from channel / 远离                        Toward channel / 逼近
┌──────────────────────────┐          ┌──────────────────────────┐
│ 4 Agents coordinating     │          │ 1 Agent deciding          │
│ Manager orchestrating     │          │ No orchestration layer    │
│ Dual LLM                  │          │ Single LLM                │
│ Code tracks phase         │          │ LLM advances naturally    │
│ Code injects phase hints  │          │ Prompt describes flow     │
│ Command panel guesses     │          │ LLM understands user      │
│ Hardcoded fix table       │          │ Doctor reads manual       │
│ Binds to model capability │          │ Prompt universal compat   │
│ 1 domain                  │          │ 3+ domains (switch prompt)│
└──────────────────────────┘          └──────────────────────────┘
         Away ←─────────────────────────────────→ Toward
              Each layer removed = one step closer
```

Every real advance resulted in net code reduction. The cleaner the channel, the less code. The stronger the functionality, the less code. These two trends contradict in traditional software engineering. Here, they converge — because "functionality" resides not in code, but in the LLM's autonomy.

每一次真正的进步，净效果都是代码减少。通道越干净，代码越少。功能越强，代码越少。这两个趋势在传统软件工程里是矛盾的——在这里是统一的。因为"功能"不在代码里，在 LLM 的自主权里。

69 days. One line. From "code controls everything" to "code does only what the LLM cannot." This line was not designed — it was accumulated through every single act of deleting violation code across 1,110 commits.

69 天。一条线。从"代码掌控一切"到"代码只做 LLM 做不到的事"。这条线不是设计出来的——是 1,110 个 commits 中每一次"删掉违轨代码"累积出来的。

---

## Appendix A: The Ten Principles · 附录 A：十条理念速查

1. Code only does what LLM cannot · 代码只做 LLM 做不到的事
2. Fixing is subtraction · 修复是做减法
3. LLM decides, code executes · LLM 决定，代码执行
4. A patch is not a fix · 补丁不等于修复
5. You are the temporal awareness node · 你是时间感知节点
6. Every reversion is a learning event · 撤回是学习事件
7. Dirty architecture punishes addition · 脏架构惩罚加法
8. Describe, don't prescribe · 描述，不规定
9. Strengthen LLM = give tools, not knowledge · 增强 LLM = 给工具，不给知识
10. Hardcoded constants are hidden patches · 硬编码常量是隐藏的补丁

---

## Appendix B: Four Dimensions of the Channel · 附录 B：通道四个维度

1. Don't bind to model capabilities · 不绑模型能力
2. Don't hardcode rules · 不硬编码规则
3. Don't distinguish domains · 不做领域区分
4. Execute, don't decide · 只执行不决策

---

## Appendix C: The Debugging Iron Protocol · 附录 C：调试铁流程

1. Read dump + read logs (both mandatory) · 读 dump + 读日志（两者缺一不可）
2. Three questions: What did LLM receive? What did it reply? What tools did it call? · 三问定位
3. Trace the code path: which branch did the LLM response enter? · 对照代码路径
4. State the root cause: X caused Y · 报根因
5. Propose a fix (don't act yet), wait for confirmation · 提方案（不动手），等确认后改
