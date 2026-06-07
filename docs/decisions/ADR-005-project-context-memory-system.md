# ADR-005：ProjectContext 统一上下文记忆系统

> **历史 ADR**（2026-05-30）：本决策仍有效。**2026-06-06 Scribe 删除不影响本 ADR**——ProjectContext 与 Scribe 原本就无功能重叠，详见 `docs/superpowers/plans/scribe-redesign-brief.md` 结论段。

- **日期**：2026-05-30（设计） / 2026-05-31（review 已发布）
- **状态**：🟡 设计中（待修订后实施）
- **相关律 / 铁律**：律 1（意图穿透律）、律 2（原话不可销毁律）、律 3（同阶段多轮记忆律）、律 5（状态层单一权威律）、律 6（信息抵达正向断言）

## 背景

项目所有者诊断：「**用户感觉在连续对话，LLM 并不是**」——这是项目最隐蔽的 B 类语义漏水。

现状（律 3 仅部分落地）：

- `_session_messages`（Scout 多轮对话，手动拼接）
- `_conversation_history`（Cleaner 对话，ad-hoc）
- `utterances`（结构化用户原话日志）
- Scribe 4 通道（阶段交接）

各自为政，导致：

1. Scout 多轮记忆丢失：`_apply_scout_reply_with_llm` 在 session 路径下使用陈旧 system prompt
2. 跨 Agent 信息衰减：Cleaner / Analyst 看不到 Scout 完整对话脉络
3. 同样的"拼接对话历史 + 注入当前状态"逻辑在多 Agent 中重复实现

## 决策

新增 `hagoku/context/project_context.py`，作为 EventBus 的**被动消费者**（与 Scribe 平级），监听 `AGENT_STARTED` / `AGENT_COMPLETED` / `USER_INPUT_RECEIVED` 事件自动追加 entries。

数据模型：

```python
@dataclass
class ContextEntry:
    type: Literal["goal", "agent_response", "user_feedback", "stage_transition"]
    stage: str
    revision: int
    timestamp: str
    content: str
    raw_user_text: str | None      # 律 2
    snapshot: dict | None           # 从 column_semantics 实时派生（律 5）

@dataclass
class ProjectContext:
    run_id: str
    analysis_goal: str              # 律 1
    entries: list[ContextEntry]     # 追加式只增不改
```

提供 `build_prompt(agent, context)` 方法为每个 Agent 拼装：

- `system_prefix`：分析目标 + 当前字段状态 + 命令上下文
- `messages_history`：当前阶段对话的标准 messages list（**修订后**，详见 review）

两阶段实施：阶段 1 与旧路径并行；阶段 2 替换旧路径。

## 替代方案

| 方案 | 否决理由 |
|------|---------|
| 全局对话 buffer | 跨阶段语义污染（用户在 Scout 说的话被 Analyst LLM 误读）；prompt 膨胀 |
| 各 Agent 各自维护 buffer（保持现状） | 律 5 单一权威违反；维护成本翻倍 |
| 把对话记忆塞进 Scribe | Scribe 是**确定性引擎 + 持久化文档**，对话记忆是**运行时上下文拼装**，职责不同 |
| 用 LangGraph / 第三方对话框架 | 引入大量耦合；本项目通道哲学不需要框架级抽象 |

## 后果

**正面**：

- 律 1/2/3/5/6 五律一并合规
- 各 Agent LLM 调用获得统一上下文，跨 Agent 对话脉络不丢
- `_session_messages` / `_conversation_history` 旧路径可清理

**负面 / 待办（详见 review 文件 3 必修 + 5 建议）**：

- 🔴 必修 1：`history_context` 当前 plan 拼成单 user 消息文本——违反律 3「message list 形式」精神
- 🔴 必修 2：`system_prefix` 与 Agent 自身 system_prompt 双重注入 `analysis_goal` / `command_context`
- 🔴 必修 3：`subscribe(bus, context_ref=None)` 让初始 Scout 快照丢失
- 🟡 建议 4：`utterances` vs `entries` 律 5 二选一
- 🟡 建议 5-8：边界明示、合规属性、防御分支清理、stage_transition 渲染

**影响范围**：

- 新建：`hagoku/context/project_context.py`、`tests/test_context/`
- 修改：`hagoku/manager/orchestrator.py`（接入点 + 旧路径清理）
- 修改：各 Agent system_prompt 删除重复注入（必修 2）
- 文档：`PROJECT.md §「ProjectContext 统一上下文记忆系统」`（已合入）

## 引用

- 设计规格：`docs/superpowers/specs/2026-05-30-project-context-memory-design.md`
- 实现计划：`docs/superpowers/plans/2026-05-30-project-context-memory-plan.md`
- **审核报告（必读）**：`docs/superpowers/specs/2026-05-30-project-context-memory-review.md`
- 相关律：`PROJECT.md §「通道完备性十律」§ 律 1/2/3/5/6`

## 当前阻塞

实施前必须按 review 文件的「修订 checklist」改 spec 与 plan：

- spec 7 项修订
- plan 6 项修订

修订完毕后再开 8 任务流程。
