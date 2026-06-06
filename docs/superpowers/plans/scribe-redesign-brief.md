# 新 Session 任务：设计 Scribe agent 的新定位

**这是设计讨论，不是 audit**。请先读完下面背景再开始。

---

## 项目最关键的事（必先校准，否则会读反）

**核心信条**：LLM 在语义判断上比代码更可靠。Code 的活是构建通道让 LLM 自由发挥，**不是防御 LLM**。

详见 `PROJECT.md` 顶部 1 句核心信条 + `CLAUDE.md` 顶部"30 秒入门"。

---

## Scribe 是什么

HaGoKu Studio 有 5 个 agent：
- 主流水线：Scout → Cleaner → Analyst → Reporter
- **Scribe**（`hagoku/agents/_scribe/`，下划线前缀 = 内部支持角色）

Scribe 名义上管 4 件大事：看板管理、记忆维护、知识库检索与注入、字段仲裁。

**当前实际状态**：调用稀疏，主流水线大部分场景绕开。CLAUDE.md 对 Scribe 的描述是"确定性 Agent，仅字段描述不完整时用 LLM 补全"——听起来像补全者，不是主角。

**唯一被实际用的功能**：`recover_field_descriptions` —— 当 LLM 没填全字段描述时，生成结构化占位（"字段 A (int64)"）+ 打 `_scribe_fallback=True` 标记。这是合规的"打标记的兜底"。

---

## 用户的判断（这次讨论的目标）

> "当初是有这么个设计，现在的个agent的处境很尴尬，几乎没有作用。但我觉得可能取到画龙点睛的作用。"

用户认为：Scribe 当前没用 ≠ 该删。Scribe 可能是项目"画龙点睛"的关键。但**还没想清楚具体怎么设计**。

---

## 这次要回答的 3 个问题

1. **用户在哪儿"感受到系统活着的痕迹"？**
   - 跨 run 的记忆？个性化？项目级上下文？协作协调？

2. **Scribe 尴尬的根因是什么？**
   - 职责错位？位置错位（应是"贯穿全程"而非"补字段"）？接口错位（4 Agent 不知道怎么调它）？

3. **"画龙点睛"的"眼睛"具体是什么？**
   - A. 协作协调（仲裁 + 状态机）
   - B. 用户感知（记忆 + 学习 + 个性化）
   - C. 知识管理（项目级上下文）
   - D. 别的

---

## 不要做的事

- ❌ 不要直接改 Scribe 内部代码（600+ 行没读，避免无方向乱改）
- ❌ 不要假设 Scribe 现有设计是错的
- ❌ 不要"顺手扩展"当前功能
- ❌ 不要写"全景式 Scribe 报告"——这是设计讨论

---

## 期望产出

1. 回答上面 3 个问题
2. 给 Scribe 一个**明确的"在新架构里的位置"**（一句话能说清）
3. 列出实现该位置**需要做的工作**（清单即可，不动手）
4. **等用户说"开始改"再动代码**

---

## 角色定位

不是"audit Scribe"，是**"和用户一起设计 Scribe 的新定位"**。要：
- 听用户说、提问题
- 把用户"画龙点睛"的直觉**翻译成具体架构选项**
- 不替用户做最终决定

---

## 相关资源

打开 `~/.claude/projects/-home-son-goku-HaGoKu/memory/` 读这 4 条：
- `project-core-thesis.md`（核心信条）
- `feedback-iron-rule-anti-obvious.md`（铁律措辞反话正说）
- `project-scribe-future.md`（这次讨论的来源 + 4 个潜在方向 A/B/C/D）
- `user-work-style.md`（用户偏好小步走 + 自我批判）

代码位置：
- `hagoku/agents/_scribe/agent.py`（600+ 行没读，**这次也别读**）
- `hagoku/agents/_scribe/{prompt.md, memory.md, knowledge.yaml}`（Scribe 自己的配置，**不读**避免预设）
- `hagoku/agents/{scout,cleaner,analyst,reporter}/`（4 主线 agent，**知道存在即可**）

---

## 讨论起点建议

先问用户：
> "你说 Scribe 能'画龙点睛'——上次做完一次分析、看到报告，那个时刻，**你作为用户，希望从哪儿感受到'系统是活的、记得我、懂我'？**"

从这个具体体验出发，把"画龙点睛"落到一个能**被 1 句话说清**的位置。

---

## 结论（2026-06-06）

本次讨论最终决定：**回归简单，把 Scribe 简化为 Orchestrator 内部的一部分**。不 LLM 化、不保留 agent 抽象。

**4 步执行**（5 个 commit 含 1 个 initial）：

| 步骤 | Commit | 内容 |
|---|---|---|
| Step 1 | `237310d` | Orchestrator 拿 `self.kanban` + `block_task` / `unblock_task` 方法 |
| Step 2 | `2e3197d` | 4 agent 切到 `orchestrator.block_task` / `unblock_task`（13 调用点） |
| Step 3 | `3728f4b` | 删 4 通道文件（process_log.md / context.md / handover_notes.md） + handover 改 None + Scribe 793→363 行 |
| Step 4 | `d2772dd` | 删 `_scribe/` 目录 + `prompt.md` + Scribe 测试（440/440 pass） |
| Step 5 | （本次） | 文档同步：CLAUDE.md / PROJECT.md / brief / memory |

**架构变更**：
- ❌ 删 `hagoku/agents/_scribe/` 整目录
- ❌ 删 4 通道文件（process_log.md / context.md / handover_notes.md）
- ❌ 删 4 个 Scribe 测试（`TestScribeRecoverFieldDescriptions`）
- ❌ 删 `recover_field_descriptions`（LLM 兜底，0 生产调用方）
- ❌ 删 `handover_notes.md`（handover 内容直接由 orchestrator 注入下游 agent prompt）
- ✅ Kanban 状态机内联到 `Orchestrator`（`self.kanban` + `_on_event` + 3 个 handler + `_auto_promote_next` + `_init_pipeline_tasks`）
- ✅ 4 agent 改用 `orchestrator.block_task` / `unblock_task`（门控流程不变）

**为何不 LLM 化**：
- Scribe 4 件真活（kanban / handover / block-unblock / init_pipeline）都是确定性 Python 状态机，不涉及 LLM 语义判断
- 8 个 public 方法（`claim_task` / `record_interaction` / `update_context` 等）从未被调——证明"LLM 兜底"路径无人需要
- 唯一 LLM 调用点 `recover_field_descriptions` 全仓 0 生产调用方
- LLM 化（让 Scribe 做"活的协调者"）属于"愿景驱动"而非"需求驱动"

**结果**：
- pytest 444 → 440（删 4 个 Scribe 测试）
- `_scribe/` 目录删除（-793 行 Scribe 代码 + 12KB prompt.md）
- Orchestrator 净增 ~150 行内联 kanban 逻辑
- 整体代码净减 600+ 行

后续如需"活的协调者"愿景，可基于内联后的 Orchestrator 状态机做加法（每个新 LLM 节点是独立 commit、可独立回滚）。本次仅做减法。
