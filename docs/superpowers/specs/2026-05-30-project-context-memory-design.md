# ProjectContext — Agent 上下文记忆系统设计规格

> 状态：草案 | 日期：2026-05-30 | 作者：HaGoKu Studio

## 1. 动机

当前 HaGoKu 在一次分析 run 内的上下文记忆由多个分散机制拼凑：

- `_session_messages`（Scout 多轮对话，手动拼接）
- `_conversation_history`（Cleaner 对话，ad-hoc）
- `utterances`（结构化用户原话日志）
- Scribe 4 通道（阶段交接）

这些机制各自为政，导致三个核心问题：

1. **Scout 多轮记忆丢失**：`_apply_scout_reply_with_llm` 在 session 路径下使用初始 Scout 的陈旧 system prompt，当前字段状态、命令上下文、分析目标状态均未送达 LLM。
2. **跨 Agent 信息衰减**：Cleaner/Analyst 无法看到 Scout 阶段的完整对话脉络，只能看到 Scribe 提取的摘要。
3. **代码碎片化**：同样的"拼接对话历史 + 注入当前状态"逻辑在多个 Agent 中以不同方式重复实现。

## 2. 设计目标

- 一次 run 内，所有 Agent 共享同一个追加式上下文日志
- 每个 Agent 调 LLM 时，自动获得：分析目标 + 当前字段状态 + 本阶段对话历史 + 上游阶段摘要
- 遵守所有通道完备性十律（尤其是律 1/2/3/5/6）
- 遵守铁律 1/2（代码不做语义判断，LLM 失败不兜底）
- 最小改动：先搭骨架并行运行，再逐步替换旧路径

## 3. 架构

### 3.1 组件定位

```
EventBus (已有)
  ├── Scribe (已有)         → process_log.md / context.md / kanban.db
  └── ProjectContext (新增)  → entries 追加 + build_prompt()
```

`ProjectContext` 是 EventBus 的被动消费者，不做任何流程控制——只记录和查询。

### 3.2 数据模型

```python
@dataclass
class ProjectContext:
    run_id: str
    analysis_goal: str           # 律 1：永远在 system_prefix 首行
    entries: list[ContextEntry]  # 追加式，不可删除

@dataclass
class ContextEntry:
    type: Literal["goal", "agent_response", "user_feedback", "stage_transition"]
    stage: str                   # scout / cleaner / analyst / reporter
    revision: int                # 阶段内轮数，从 0 开始
    timestamp: str               # ISO-8601
    content: str                 # 人类可读摘要
    raw_user_text: str | None    # 律 2：用户原话（type=user_feedback 时必填）
    snapshot: dict | None        # type=agent_response 时附带（从 column_semantics 实时派生）
```

### 3.3 事件监听 → 自动记录

| EventBus 事件 | 动作 |
|---|---|
| `AGENT_STARTED` | 追加 `stage_transition` entry |
| `AGENT_COMPLETED` | 从 `context["column_semantics"]` 实时派生 snapshot，追加 `agent_response` entry |
| `USER_INPUT_RECEIVED` | 追加 `user_feedback` entry（含 `raw_user_text`） |

### 3.4 build_prompt() — 上下文拼装

```
build_prompt(agent: str) -> dict:
  1. 从看板确认 agent 所处阶段及上游是否 done
  2. system_prefix:
     分析目标: {analysis_goal}
     当前字段状态: {从 column_semantics 实时派生}
     角色分配: target={}, features={}
     待确认: {pending 字段}
     命令上下文: {_pending_command_text}
  3. history_context:
     当前阶段的 user_feedback + agent_response entries（按时间序）
     上游阶段的 agent_response entries（仅结构化快照，不含对话）
```

### 3.5 集成点

每个 Agent 调 LLM 前，orchestrator 调用：

```python
ctx_block = project_context.build_prompt(agent_name)
messages = [
    {"role": "system", "content": agent_system_prompt + "\n\n" + ctx_block["system_prefix"]},
    {"role": "user",   "content": ctx_block["history_context"] + "\n\n" + current_task},
]
```

阶段 1：与旧路径并行。阶段 2：替换 `_session_messages` 等旧路径。

## 4. 两阶段实施路线

### 阶段 1：搭骨架

| 步骤 | 内容 | 文件 |
|------|------|------|
| 1a | `ProjectContext` + `ContextEntry` 数据类 | `hagoku/context/project_context.py`（新建） |
| 1b | EventBus 消费者注册：监听 AGENT_STARTED / COMPLETED / USER_INPUT_RECEIVED | 同上 |
| 1c | `build_prompt()` 方法 | 同上 |
| 1d | Orchestrator 接入：在 Agent 调用点调用 `build_prompt()`，与旧路径并行 | `hagoku/manager/orchestrator.py` |
| 1e | 单元测试 | `tests/test_context/test_project_context.py`（新建） |

### 阶段 2：突破字段理解

| 步骤 | 内容 | 文件 |
|------|------|------|
| 2a | `_apply_scout_reply_with_llm` 改用 `build_prompt("scout")` 替代 `_session_messages` | `hagoku/manager/orchestrator.py` |
| 2b | system_prefix 注入当前状态（修复断裂点 1） | 同上 |
| 2c | history_context 显示交互脉络（修复断裂点 2） | 同上 |
| 2d | command_context 通过 system_prefix 送达（修复断裂点 3） | 同上 |
| 2e | 清理旧代码：移除 `_session_messages` 手动拼接、`_conversation_history` 冗余路径 | `hagoku/manager/orchestrator.py`, `hagoku/agents/*/agent.py` |
| 2f | 信息抵达正向断言（律 6） | `tests/test_product/test_information_arrival.py` 新增用例 |

## 5. 错误处理与退化

遵守铁律 2——代码不兜底，不写默认值。

| 场景 | 行为 |
|------|------|
| EventBus 事件缺失 | `build_prompt()` 缺少某条 entry → 正常返回（只是那段历史不显示），不抛异常 |
| build_prompt 输出超长 | `history_context` 预算 ~2000 tokens：当前阶段全保留；超预算时上游阶段仅保留最近一轮 snapshot；仍超长则警告 |
| 看板状态不一致 | 降级：system_prefix 仅含 `analysis_goal` + 当前字段状态；history_context 为空 |
| ProjectContext 不可达 | 回退各 Agent 独立 system_msg（现有路径） |

## 6. 原则合规

| 原则 | 验证点 |
|------|--------|
| **铁律 1** | `build_prompt()` 的可见范围仅按 stage/type 做结构性过滤，不判断"相关性" |
| **铁律 2** | 所有降级路径保留原样，不写默认值；LLM 不可达 → `raise RuntimeError` |
| **律 1** | `analysis_goal` 在 `system_prefix` 首行 |
| **律 2** | `raw_user_text` 在 entry 中保留直到标记 consumed |
| **律 3** | `history_context` 含当前阶段全量交互 |
| **律 5** | `snapshot` 从 `column_semantics` 实时派生，不平行存储 |
| **律 6** | 阶段 2f 新增信息抵达断言 |
| **律 7** | 语义未理解时 `_last_understanding_failure` 写入 context（已有机制，不变） |
| **最小改动** | 两阶段渐进式，旧路径先并行再替换 |

## 7. 不做什么

- 不新建事件通道——复用 EventBus
- 不替代 Scribe 4 通道——`ProjectContext` 管对话记忆，Scribe 管持久化文档
- 不替代 MemoryManager——跨 run 的结构化知识仍由 MemoryManager 负责
- 不跨 run 保留对话日志——对话依附于当次分析目标，跨 run 保留造成语义污染
- 不在阶段 1 引入持久化——`ProjectContext` 在内存中运行，阶段 1 不写磁盘。crash 恢复是阶段 3（后续）工作
