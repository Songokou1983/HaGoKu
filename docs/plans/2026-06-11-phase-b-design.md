# Phase B 详细设计稿 — prompt 拼装单点化 + tool 协议 + UI 透明化（2026-06-11，方案 B 终稿）

> **文档定位**：架构审核方出具的 Phase B 落地设计，**一次性完整执行包**，交付实施 AI 执行。
>
> **上游 brief**：[`2026-06-11-collapse-to-single-agent-brief.md`](2026-06-11-collapse-to-single-agent-brief.md) §3 Phase B
>
> **前置条件**：Phase A 5 个 commit（含收尾删 xfailed 测试）已合并。
>
> **关键设计决策（用户已审）**：
> - **方案 B**：tool 调用走 OpenAI 标准协议（assistant.tool_calls + tool.tool_call_id），不字符串化。理由：LLM 看到自己真实推理链 + 用户能透明看到 AI 思考 + Phase D 不重做。
> - **UI 展示 tool exchange**：HaGoKu 透明化核心体验。CO-B6 必做。
> - **CO-B3 单独审批门**：6 步中只有 CO-B3（最大改动）动手前需再次报告审核方，其他 5 步本稿已审完可直接执行。
>
> **不可越界**：开发者**不许**先动 §4 / §5 / §6 之外的文件。任何「顺手优化」需先经审核方许可。

---

## 目录

- §0 来龙去脉 + brief 校正
- §1 真实工作量
- §2 `build_messages()` 升级（方案 B：tool 协议）
- §3 `ProjectContext` 升级（新增 `tool_exchange` entry + `to_messages_for_llm`）
- §4 4 个 agent 改造清单
- §5 3 套 `_*_messages` 删除路径
- §6 `scout_reply.py` 收缩范围
- §7 pre-commit hook + ruff
- §8 真 LLM 冒烟测试
- §9 律的减法清单
- §10 风险点 + 应对（12 个）
- §11 6 个 CO-B 任务的精确执行顺序
- §12 终审清单
- §13 不做什么
- §14 审核方对开发者的硬规则
- §15 完成标准
- §16 UI 展示 tool exchange（新增章节）

---

## §0 来龙去脉 + brief 校正

### 0.1 触发场景

Phase A 收官后，进入 Phase B。审核方 explore 调研当前代码现状，发现 brief 几处估算与实际有出入——**不是 brief 错，是写 brief 时只看了高层框架，没逐文件 grep**。本设计稿在 brief 框架上做**精确校正 + 落地展开**，并不改动 brief 文件本身（铁律 -1，保持历史可追溯）。

### 0.2 brief 校正清单

| brief 描述 | 实际代码现状 | 影响 |
|---|---|---|
| 「4 套 `_*_messages` 实例变量」 | **只有 3 套**：`_cleaner_messages` / `_analyst_messages` / `_reporter_messages`。`_scout_messages` **不存在**——Scout 阶段对话直接走 `ProjectContext` | 工作量减少。Scout 阶段已是"通道目标态"的局部样本 |
| 「reply_handlers.py 在 `hagoku/manager/` 下」 | 实际路径 `hagoku/manager/llm_dispatch/reply_handlers.py` | 路径校正 |
| 「scout_reply.py 552 行」 | 实际 **652 行** | -300 行估算保留，但起点更高 |
| 「3-5 天工期」 | 维持估算 | 看 §1 工作量明细 |
| 「全 agent 都走 `build_messages()`」隐含假设 | 实际只 scout 完整走；cleaner 部分走（仅 `_plan_via_llm`）；**analyst / reporter 完全不走** | 改造量比 brief 暗示的大 |
| 「ProjectContext 升级为唯一 chat 持有者」 | ProjectContext 已是物理唯一持有者（`entries: list[ContextEntry]`）。**问题不是它不持有，是 agent 不读它** | 真正要做的是让 agent 不再持有 `_*_messages`，强制从 ProjectContext 读 |

### 0.3 真正要根除的反模式（用调研结果重新陈述）

经调研，"prompt 拼装碎片化" 在仓库内有 **4 种形态**，本 Phase 全部根除：

| 反模式 | 现存位置 | 危害 |
|---|---|---|
| **形态 1**：agent 内直接 `messages = [{"role":"system", ...}]` | `cleaner/agent.py:675`、`reporter/agent.py:177` | 完全绕过 `build_messages()`，没人能在编译期拦住 |
| **形态 2**：`_compose_system_messages()` + `composed.append()` | `analyst/agent.py:218-223`、`reporter/agent.py:80-82`、`cleaner/agent.py:167` | 用一个"辅助函数"包装直接拼装，伪装成合规 |
| **形态 3**：orchestrator 持有 `_*_messages` 实例变量 | `orchestrator.py:162/166/169`、`reply_handlers.py` 11 处 | 与 ProjectContext 形成**双权威**（违反铁律 4） |
| **形态 4**：调用 `build_messages()` 但漏传 `system_extra` | `scout_reply.py:408`（漏传 ProjectContext 的 `system_prefix`/`upstream_summary`） | LLM 看不到分析目标和字段状态——铁律 5（通道洁净）违规 |

---

## §1 Phase B 真实工作量（方案 B + UI 后精确版）

| 文件 | 净改动行数估算 | 类别 | 备注 |
|---|---|---|---|
| `hagoku/channel.py` | +110 行 | 升级 | schema 严格化、ChatTurn 支持 tool 协议、role 字段语义校验 |
| `hagoku/context/project_context.py` | +120 / -10 | 升级 | 新增 `to_messages_for_llm()`、`tool_exchange` entry 类型、持久化兼容 |
| `hagoku/agents/scout/agent.py` | +5 / -5 | 微调 | 已合规，只需把 `system_extra` 改为读 ProjectContext |
| `hagoku/agents/cleaner/agent.py` | +60 / -120 | **重写 LLM 调用块** | `run_step` / `assess` / `_plan_via_llm` 全改；多轮 tool 写回 ProjectContext |
| `hagoku/agents/analyst/agent.py` | +35 / -60 | **重写 LLM 调用块** | 删 `_compose_system_messages`，多轮 tool 写回 |
| `hagoku/agents/reporter/agent.py` | +35 / -60 | **重写 LLM 调用块** | 同 analyst |
| `hagoku/manager/orchestrator.py` | +5 / -30 | 删 `_*_messages` 实例字段 | 3 处定义 + reset 块 |
| `hagoku/manager/llm_dispatch/reply_handlers.py` | +20 / -80 | 重构 | 不再持有 messages 列表，全从 ProjectContext 读 |
| `hagoku/manager/llm_dispatch/scout_reply.py` | -250（净减） | **大幅收缩** | 删拼装残留 + 删 dump 旁路独立 messages 构造 |
| `pyproject.toml` | +15 行 | 新增 | ruff 自定义规则 / 配置项 |
| `scripts/check_no_direct_messages.py` | +80 行（新文件） | 新增 | pre-commit hook 脚本（ruff plugin 无法表达的语义） |
| `.pre-commit-config.yaml` | +10 行（或新文件） | 新增/更新 | 接入 hook |
| `tests/test_channel/test_build_messages_strict.py` | +150 行（新文件） | 新增测试 | schema 严格性测试（含 tool 协议场景） |
| `tests/test_context/test_tool_exchange.py` | +80 行（新文件） | 新增测试 | tool_exchange entry 序列化 / 反序列化 / build_prompt |
| `tests/test_doctrine/test_no_direct_messages.py` | +40 行（新文件） | 新增测试 | AST 守门 |
| `hagoku/api/ws_handler.py`（或事件 emit 点） | +30 行 | UI emit | `TOOL_EXCHANGE` 事件 |
| `hagoku_web/src/...`（前端 chat 组件） | +200 / -20 | UI 渲染 | 新增 `ToolExchangeTurn` 组件 + WS hook 适配 |
| **合计净** | **约 -250 行代码 / +600 行新增（测试 + UI）** | | **工期估算 5-7 天** |

> 工期相比 brief 原估算（3-5 天）增加，原因：方案 B 引入 tool 协议支持 + UI 展示 tool exchange。换来 Phase D 不重做 + LLM 行为稳定 + HaGoKu 透明化核心体验落地。

---

## §2 `build_messages()` 升级设计

### 2.1 现状缺陷

```13:40:hagoku/channel.py
def build_messages(
    *,
    query: str,
    user_input: str,
    history: list[dict[str, Any]] | None = None,
    system_extra: str | None = None,
) -> list[dict[str, Any]]:
    ...
```

- 无 schema 校验：`history` 任意 `dict[str, Any]` 可塞
- 多传参数 → `TypeError`（防御靠 Python 自身，**没有可读的错误提示**）
- 漏传 `system_extra` → 静默接受（这是 `scout_reply.py` 漏传 ProjectContext 的根因）
- role 不限制：`{"role": "fake_role", ...}` 可塞进 history

### 2.2 升级后签名（方案 B：支持 tool role 标准协议）

```python
# hagoku/channel.py
from __future__ import annotations
from typing import Literal, TypedDict, Required, NotRequired
from pydantic import BaseModel, Field, model_validator


class ToolCallFunction(TypedDict):
    """OpenAI tool_call 的 function 子字段。"""
    name: str
    arguments: str  # JSON 字符串


class ToolCall(TypedDict):
    """OpenAI tool_call 标准格式。"""
    id: str
    type: Literal["function"]
    function: ToolCallFunction


class ChatTurn(TypedDict, total=False):
    """LLM 消息单元的严格类型。

    role 必填；content / tool_calls / tool_call_id 按 role 选择性必填：
    - role="system" / "user"        → content 必填
    - role="assistant"              → content 与 tool_calls 至少一个非空
    - role="tool"                   → content + tool_call_id 必填
    """
    role: Required[Literal["system", "user", "assistant", "tool"]]
    content: NotRequired[str]
    tool_calls: NotRequired[list[ToolCall]]   # 仅 role=assistant 时允许
    tool_call_id: NotRequired[str]            # 仅 role=tool 时必填


class _ChatTurnValidator(BaseModel):
    """逐条 turn 的语义校验（role 与字段的对应规则）。"""
    model_config = {"extra": "forbid"}

    role: Literal["system", "user", "assistant", "tool"]
    content: str | None = None
    tool_calls: list[dict] | None = None
    tool_call_id: str | None = None

    @model_validator(mode="after")
    def _check_role_field_rules(self):
        if self.role in ("system", "user"):
            if self.content is None or not self.content.strip():
                raise ValueError(f"role={self.role} 的 turn content 必须非空")
            if self.tool_calls or self.tool_call_id:
                raise ValueError(f"role={self.role} 不允许 tool_calls/tool_call_id")
        elif self.role == "assistant":
            if not self.content and not self.tool_calls:
                raise ValueError("role=assistant 的 turn 必须有 content 或 tool_calls")
            if self.tool_call_id:
                raise ValueError("role=assistant 不允许 tool_call_id")
        elif self.role == "tool":
            if not self.content:
                raise ValueError("role=tool 的 turn content 必须非空")
            if not self.tool_call_id:
                raise ValueError("role=tool 的 turn 必须有 tool_call_id")
            if self.tool_calls:
                raise ValueError("role=tool 不允许 tool_calls")
        return self


class BuildMessagesInput(BaseModel):
    """build_messages() 的严格输入 schema（未知顶层字段被拒绝）。"""
    model_config = {"extra": "forbid", "frozen": True}

    query: str = Field(..., min_length=1, description="第一条 user 消息，永不删除")
    user_input: str = Field(..., min_length=1, description="最后一条 user 消息")
    history: list[ChatTurn] = Field(default_factory=list, description="中间历史，逐条按 role 规则验证")
    system_extra: str = Field(default="", description="可选 system 前缀")

    @model_validator(mode="after")
    def _validate_history(self):
        for i, turn in enumerate(self.history):
            try:
                _ChatTurnValidator(**turn)
            except Exception as e:
                raise ValueError(f"history[{i}] 不符合 ChatTurn 规则: {e}") from e
        return self


def build_messages(
    *,
    query: str,
    user_input: str,
    history: list[ChatTurn] | None = None,
    system_extra: str = "",
) -> list[ChatTurn]:
    """构建发给 LLM 的 messages — 唯一合法入口。

    与升级前的区别：
    1. history 支持 OpenAI 标准 tool 协议（assistant.tool_calls + tool.tool_call_id）
    2. 内部用 BuildMessagesInput + _ChatTurnValidator 做严格校验
    3. role/字段组合不合法 → ValidationError（带详细错误位置）
    4. system_extra 默认空串而非 None（消除"传 None vs 空"的歧义）
    """
    validated = BuildMessagesInput(
        query=query,
        user_input=user_input,
        history=list(history or []),
        system_extra=system_extra,
    )
    msgs: list[ChatTurn] = []
    if validated.system_extra:
        msgs.append({"role": "system", "content": validated.system_extra})
    msgs.append({"role": "user", "content": validated.query})
    msgs.extend(validated.history)
    msgs.append({"role": "user", "content": validated.user_input})
    return msgs
```

### 2.3 行为契约（写入测试）

| 输入 | 期望行为 |
|---|---|
| `query=""` | `ValidationError`（min_length=1）|
| `history=[{"role": "junk", "content": "x"}]` | `ValidationError`（Literal 校验失败）|
| `history=[{"role": "user"}]`（缺 content）| `ValidationError`（content 必填）|
| `history=[{"role": "assistant", "tool_calls": [{"id": "t1", "type": "function", "function": {"name": "x", "arguments": "{}"}}]}]` | **通过**（assistant 可只有 tool_calls）|
| `history=[{"role": "tool", "content": "result"}]`（缺 tool_call_id） | `ValidationError`（tool 必须有 tool_call_id）|
| `history=[{"role": "user", "tool_calls": [...]}]` | `ValidationError`（user 不允许 tool_calls）|
| 多传未知参数 `extra_arg="x"` | `TypeError`（keyword-only 拒绝）|
| `system_extra=None` | `TypeError`（类型不符）|
| `system_extra=""`（默认） | 不注入 system 消息 |

### 2.4 反例（这些写法**禁止**通过）

```python
# ❌ 直接构造 messages
messages = [{"role": "system", "content": "..."}]

# ❌ messages.append（哪怕已经走 build_messages）
messages = build_messages(...)
messages.append({"role": "user", "content": "..."})  # 改回 build_messages 重建

# ❌ 用 ChatTurn 之外的 role
build_messages(query="x", user_input="y", history=[{"role": "manager", "content": "..."}])

# ❌ 漏传 system_extra（场景 4）
build_messages(query=q, user_input=u, history=h)
# 当 ProjectContext 有 system_prefix 时必须传——靠 review，无法静态检查

# ❌ tool turn 缺 tool_call_id
build_messages(query=q, user_input=u, history=[
    {"role": "assistant", "tool_calls": [{"id": "t1", ...}]},
    {"role": "tool", "content": "result"},  # 缺 tool_call_id="t1"
])
```

---

## §3 `ProjectContext` 升级设计

### 3.1 现状（已是物理唯一持有者）

```python
@dataclass
class ProjectContext:
    run_id: str
    analysis_goal: str
    entries: list[ContextEntry]  # ← append-only，已是单一物理来源
    # ...

    def build_prompt(self, agent: str, context: dict) -> dict[str, str]:
        # 返回 {system_prefix, upstream_summary, messages_history}
        # messages_history 只含 stage==agent 的 entries
```

**结论**：ProjectContext 已经是 chat 的物理唯一持有者。Phase B **不动 ProjectContext 核心结构**，只补一个辅助方法让调用方更省心。

### 3.2 新增辅助方法

```python
# hagoku/context/project_context.py
def to_messages_for_llm(
    self,
    agent: str,
    context: dict[str, Any],
    user_input: str,
) -> list[ChatTurn]:
    """打通 ProjectContext → build_messages 的链路。

    内部行为：
    1. 调 self.build_prompt(agent, context) 拿 {system_prefix, upstream_summary, messages_history}
    2. system_extra = system_prefix + "\n\n" + upstream_summary（如有）
    3. query 取自 self.analysis_goal
    4. 调 build_messages(...) 返回最终 messages

    任何 agent 想调 LLM 时，调这一个方法即可，**禁止**手动拼装。
    """
    from hagoku.channel import build_messages

    parts = self.build_prompt(agent, context)
    system_full = parts["system_prefix"]
    if parts["upstream_summary"]:
        system_full += "\n\n" + parts["upstream_summary"]

    return build_messages(
        query=self.analysis_goal,
        user_input=user_input,
        history=parts["messages_history"],
        system_extra=system_full,
    )
```

### 3.3 `build_prompt()` 微调

行 217 `current_stage_entries = [e for e in self.entries if e.stage == agent]` 保留不动——Phase B 不动 4-agent 模型（那是 Phase D 的事）。

唯一改动：行 218-223 当前只处理 `user_feedback` / `agent_response` 两种 entry 类型。新增 §3.4 的 `tool_exchange` entry 类型后，本方法也要扩展为 3 种 entry 都序列化进 messages_history。

唯一不动：行 153-179 拼装 `system_prefix` 的逻辑里，`cmd_text = context.get("_pending_command_text")`——这个 `_pending_command_text` 走的是 `context` dict（非 ProjectContext 字段），形成"半结构化半 dict"的混乱。**Phase B 不动它**——这是 Phase D 拼装与状态收口的目标。

### 3.4 新增 entry 类型：`tool_exchange`（方案 B 必需）

#### 数据结构

```python
# hagoku/context/project_context.py（修订 ContextEntry）

ContextEntryType = Literal[
    "goal",
    "agent_response",
    "user_feedback",
    "stage_transition",
    "tool_exchange",  # 新增
]


@dataclass
class ToolCallRecord:
    """单次工具调用 + 结果的记录。"""
    tool_call_id: str
    name: str
    arguments: str          # JSON 字符串
    result: str             # 工具执行返回值（已 stringify）
    error: str | None = None  # 工具执行失败时填错误信息（铁律 7 失败在场——不吞）


@dataclass
class ContextEntry:
    type: ContextEntryType
    stage: str
    revision: int
    timestamp: str
    content: str                              # 人类可读摘要（UI 展示用）
    raw_user_text: str | None = None
    snapshot: dict[str, Any] | None = None
    tool_calls: list[ToolCallRecord] | None = None  # 仅 type="tool_exchange" 时填
```

#### 新增方法

```python
def add_tool_exchange(
    self,
    stage: str,
    revision: int,
    tool_calls: list[ToolCallRecord],
    assistant_content: str = "",  # LLM 在调工具前可能也说了话
) -> None:
    """记录一轮 assistant tool_calls + tool results。

    序列化进 messages_history 时展开为 OpenAI 协议标准的两类 turn：
      [{"role":"assistant", "content":..., "tool_calls":[...]}, 
       {"role":"tool", "content":result, "tool_call_id":id}, ...]
    """
    # content（UI 展示用）汇总为人类可读
    summary_lines = []
    if assistant_content:
        summary_lines.append(assistant_content)
    for tc in tool_calls:
        line = f"→ 调用 {tc.name}({tc.arguments})"
        if tc.error:
            line += f"  ❌ 错误: {tc.error}"
        else:
            line += f"  ✓ {tc.result[:120]}"
        summary_lines.append(line)
    content_summary = "\n".join(summary_lines)

    entry = ContextEntry(
        type="tool_exchange",
        stage=stage,
        revision=revision,
        timestamp=self._now(),
        content=content_summary,
        tool_calls=tool_calls,
    )
    self.add_entry(entry)
```

#### `build_prompt()` 的 `messages_history` 部分扩展

```python
# 改前（行 218-223）
for e in current_stage_entries:
    if e.type == "user_feedback":
        messages_history.append({"role": "user", "content": e.raw_user_text or e.content})
    elif e.type == "agent_response":
        messages_history.append({"role": "assistant", "content": e.content})

# 改后
for e in current_stage_entries:
    if e.type == "user_feedback":
        messages_history.append({"role": "user", "content": e.raw_user_text or e.content})
    elif e.type == "agent_response":
        messages_history.append({"role": "assistant", "content": e.content})
    elif e.type == "tool_exchange":
        # 展开为 OpenAI 标准协议
        oai_tool_calls = [
            {
                "id": tc.tool_call_id,
                "type": "function",
                "function": {"name": tc.name, "arguments": tc.arguments},
            }
            for tc in (e.tool_calls or [])
        ]
        # assistant turn（含 tool_calls）
        assist_turn: dict = {"role": "assistant", "tool_calls": oai_tool_calls}
        # content 可能为空——OpenAI 允许 assistant 只有 tool_calls
        # 用 entry.snapshot 区分"assistant 调工具前也说了话" vs 纯工具调用
        pre_text = (e.snapshot or {}).get("assistant_pre_text", "")
        if pre_text:
            assist_turn["content"] = pre_text
        messages_history.append(assist_turn)
        # 每个 tool 调用结果作为 tool turn
        for tc in (e.tool_calls or []):
            messages_history.append({
                "role": "tool",
                "content": tc.error or tc.result,
                "tool_call_id": tc.tool_call_id,
            })
```

#### 持久化兼容

`save_jsonl` / `load_jsonl` 需新增 `tool_exchange` 类型的反序列化分支（含 `tool_calls` 嵌套结构的 dict ↔ dataclass 转换）。已有 jsonl 文件无 `tool_exchange` entry，向后兼容自然。

---

## §4 4 个 agent 改造清单

### 4.1 Scout（`hagoku/agents/scout/agent.py`，1075 行）

**当前**：2 处 LLM 调用（行 616、1008），都走 `build_messages()`，但 `system_extra` 传的是本地变量 `system_prompt`，**不读 ProjectContext**。

**改动**：

```python
# 行 618-622（_infer_all_semantics）
# 改前
messages = build_messages(
    query=query_text,
    user_input=user_input,
    system_extra=system_prompt,
)
# 改后
messages = project_ctx.to_messages_for_llm(
    agent="scout",
    context=ctx,
    user_input=user_input,
) if project_ctx else build_messages(
    query=query_text,
    user_input=user_input,
    system_extra=system_prompt,  # 单测路径保留
)
```

> 注：Scout 的 `system_prompt`（含字段语义指令）仍要拼到 system 头部。改造时确认 `to_messages_for_llm` 内的 `system_full` 已包含 Scout 域指令——若没有，需在 Scout 调用时把 `system_prompt` **作为 `user_input` 的前置内容** 注入（不是再开第二个 system message）。**这点在 PR 时审核方要确认**。

### 4.2 Cleaner（`hagoku/agents/cleaner/agent.py`，1183 行）—— **改造最重**

#### 当前违规清单

| 函数 | 行号 | 违规形态 | 改法 |
|---|---|---|---|
| `run_step` | 167 | `composed = _compose_system_messages(context) + messages` 直接给 LLM | 改 `to_messages_for_llm` |
| `assess` | 675 | `messages = [{"role":"system", ...}]` 起手 | 改 `to_messages_for_llm` |
| `assess` | 698-776 | 循环内 8 处 `messages.append` | 每轮调 `to_messages_for_llm` 重建（不再持有列表）|
| `_plan_via_llm` | 1008 | 已走 `build_messages` | 升级为 `to_messages_for_llm` |

#### 关键设计：多轮 tool-call 改造（**方案 B 标准协议**）

`assess()` 在 698-776 行内是个**循环**——每轮 LLM 返回 tool_calls，代码执行 tool，把结果反馈给 LLM。

Phase B 改造为方案 B：**tool exchange 写回 ProjectContext，下一轮重建 messages 时按 OpenAI 标准协议恢复**。

```python
# 改前模式（违规——直接拼装）
messages = [{"role": "system", "content": sys}]
messages.extend(history)
messages.append({"role": "user", "content": user_input})
while True:
    resp = llm.chat.completions.create(messages=messages, tools=tools)
    if not resp.tool_calls:
        break
    messages.append(resp.message)  # assistant + tool_calls
    for tc in resp.tool_calls:
        messages.append({"role": "tool", "content": tool_exec(tc), "tool_call_id": tc.id})

# 改后模式（方案 B 合规——ProjectContext 持久化 + 重建）
project_ctx.add_user_feedback("cleaner", revision, raw_text=original_user_input)
while True:
    messages = project_ctx.to_messages_for_llm(
        agent="cleaner", context=ctx, user_input="",  # user_input 已写入 ProjectContext
    )
    resp = llm.chat.completions.create(messages=messages, tools=tools)
    if not resp.tool_calls:
        project_ctx.add_agent_response("cleaner", revision, resp.content)
        break
    # 执行 tool 并写回 ProjectContext（保留 OpenAI 协议字段）
    tool_records = []
    for tc in resp.tool_calls:
        try:
            result = tool_exec(tc)
            tool_records.append(ToolCallRecord(
                tool_call_id=tc.id,
                name=tc.function.name,
                arguments=tc.function.arguments,
                result=result,
                error=None,
            ))
        except Exception as e:
            # 铁律 7：失败在场——tool 执行失败也写入，让 LLM 看见
            tool_records.append(ToolCallRecord(
                tool_call_id=tc.id,
                name=tc.function.name,
                arguments=tc.function.arguments,
                result="",
                error=str(e),
            ))
    project_ctx.add_tool_exchange(
        stage="cleaner",
        revision=revision,
        tool_calls=tool_records,
        assistant_content=resp.message.content or "",
    )
    # 下一轮循环：to_messages_for_llm 会从 ProjectContext 读出 tool_exchange entry
    # 并按 OpenAI 协议展开为 assistant(tool_calls) + tool(result) 两类 turn
```

> **方案 B 的优势**（vs 字符串化）：
> 1. LLM 看到自己完整的 tool 调用历史 + 结果，推理链不断裂
> 2. UI 可以渲染 "AI 调用 schema_lint → 结果 passed → AI 决定下一步" 这种透明流程（见 §16）
> 3. 与 OpenAI/Anthropic 协议一致，LLM 训练数据中这种格式见过千万次，行为最稳定
> 4. Phase D 后直接复用（1 agent 多轮 tool 循环就是天然结构）
>
> **方案 B 的代价**：
> - ChatTurn TypedDict 多 2 个可选字段（已在 §2.2 设计完整）
> - ProjectContext 多 1 个 entry 类型（`tool_exchange`，已在 §3.4 设计完整）
> - 持久化 / UI 渲染需同步支持
>
> **接受这些代价**——它们是项目灵魂（LLM 透明、信条一致）的合规成本。

### 4.3 Analyst（`hagoku/agents/analyst/agent.py`，292 行）

**当前违规**：

- 行 218-223 `_compose_system_messages` + `composed.append`
- 行 234 `chat.completions.create(messages=composed)`
- 行 280-283 `messages.append`（与 orchestrator 的 `_analyst_messages` 共生）

**改法**：与 Cleaner 同——删 `_compose_system_messages`，每次 LLM 调用前调 `to_messages_for_llm` 重建。orchestrator 持有的 `_analyst_messages` 删除（见 §5）。

### 4.4 Reporter（`hagoku/agents/reporter/agent.py`，704 行）

**当前违规**：

- 行 80-82 `_compose_system_messages`
- 行 88 `messages=composed`
- 行 177-180 `_call_llm_with_tools` 内 `_messages = [{"role":"system", ...}]`
- 行 182 `messages=_messages`

**改法**：与 Cleaner 同。两处 LLM 调用点（行 88、182）都改 `to_messages_for_llm`。删 `_compose_system_messages`。

---

## §5 3 套 `_*_messages` 删除路径

### 5.1 删除目标

| 字段 | 定义位置 | 使用位置 |
|---|---|---|
| `_cleaner_messages` | `orchestrator.py:166`、`:205` reset | `reply_handlers.py:117, 135, 137-138` |
| `_analyst_messages` | `orchestrator.py:162, 308`、`:201` reset | `reply_handlers.py:169-182, 209, 274, 282, 286, 288-289` |
| `_reporter_messages` | `orchestrator.py:169` | `reply_handlers.py:314, 317, 319-320` |

### 5.2 迁移步骤

#### Step 1：reply_handlers.py 全部改读 ProjectContext

替换所有 `self._cleaner_messages.append(...)` / `self._analyst_messages.append(...)` / `self._reporter_messages.append(...)` 为 `project_ctx.add_user_feedback(...)` 或 `project_ctx.add_agent_response(...)`。

具体映射：

| 旧调用 | 新调用 |
|---|---|
| `self._cleaner_messages.append({"role":"user","content":text})` | `project_ctx.add_user_feedback("cleaner", revision, raw_text=text)` |
| `self._analyst_messages.append({"role":"user","content":text})` | `project_ctx.add_user_feedback("analyst", revision, raw_text=text)` |
| 取 `_*_messages` 给 agent 用 | agent 内部改读 `project_ctx`，handler 不再传 messages |
| `result["messages"]` 全量覆盖 `_*_messages` | agent 不再返回 `messages` 字段，改返回结构化结果；handler 把 assistant 结论调 `add_agent_response` |

#### Step 2：agent 的 `run_step()` 签名变化

```python
# 改前
def run_step(self, context: dict, messages: list[dict]) -> dict:
    composed = self._compose_system_messages(context) + messages
    resp = llm.chat.completions.create(messages=composed, ...)
    messages.append({"role": "assistant", "content": resp.content})
    return {"messages": messages, "result": ...}

# 改后
def run_step(self, context: dict, user_input: str) -> dict:
    project_ctx: ProjectContext = context["_project_context"]
    messages = project_ctx.to_messages_for_llm(
        agent=self.AGENT_NAME, context=context, user_input=user_input,
    )
    resp = llm.chat.completions.create(messages=messages, ...)
    # 写回 ProjectContext
    project_ctx.add_agent_response(self.AGENT_NAME, revision=context["revision"], content=resp.content)
    return {"result": ...}
```

#### Step 3：orchestrator 删字段

```python
# 删除 hagoku/manager/orchestrator.py:162/166/169/308 的字段定义
# 删除 hagoku/manager/orchestrator.py:201/205 的 reset 行
# 删除 reply_handlers.py:117/274/314 的 reset 行
```

---

## §6 `scout_reply.py` 收缩范围

### 6.1 当前规模 vs 目标

- 当前：652 行
- 目标：~400 行（-250 行）

### 6.2 删除清单

| 范围 | 行数 | 删除理由 |
|---|---|---|
| 行 443-448 dump 旁路构造 messages | -6 | 改为 `dump_messages` 接受 `build_messages` 输出 + 单独的 `assistant_turn` |
| 行 465-474 assistant_turn 字符串拼装 | 保留 | 它是 dump 用，不参与 LLM；只确认它不被误塞回 messages |
| 行 401-412 `build_messages` 调用补 `system_extra` | +5 | 现在漏传，补上后约 -5 行注释清理 |
| `_get_scout_tools` 重复定义 / 死代码扫描 | 估 -50 | grep 出未被引用的 helper |
| 多版本兼容代码（看注释里有无 "已废弃 / TODO" 段）| 估 -150 | 调研时未细扫，开发者执行时按 §11 列出的 grep 命令找出 |
| ProjectContext 写回 redundant code | 估 -40 | reply_handlers 已写回的不重复写 |

> **执行注意**：开发者改 `scout_reply.py` 时必须先跑 `git diff` 让审核方看到具体删除范围；不允许"按 brief 估算的 300 行"随意删——必须基于 grep 证据。

---

## §7 pre-commit hook + ruff 规则设计

### 7.1 ruff 自定义规则（如可表达）

ruff 当前不支持自定义 lint 规则（用 Python AST）—— 我们改用 **`flake8-custom`** 或独立 pre-commit 脚本。**推荐独立脚本**（最低依赖）。

### 7.2 `scripts/check_no_direct_messages.py`

```python
"""Pre-commit hook: 禁止在 hagoku/agents/ 和 hagoku/manager/ 直接构造 messages。

规则：
1. 禁止 `messages = [{"role": ...}]` 或 `_messages = [{"role": ...}]`
2. 禁止 `messages.append({"role": ...})`
3. 例外：`hagoku/channel.py` 本身；测试文件 `tests/`
4. 例外：dump 用的 messages（行内含 `dump_messages(` 调用——AST 分析）

退出码：违规 → 1；干净 → 0
"""

import ast
import sys
from pathlib import Path


WATCHED_DIRS = ["hagoku/agents", "hagoku/manager"]
EXEMPT_FILES = {"hagoku/channel.py"}

# AST 模式：检测 `<var> = [<dict with role key>]` 和 `<var>.append({...})`
# ... 实现略，见开发交付时


if __name__ == "__main__":
    violations = scan()
    if violations:
        print("\n".join(violations), file=sys.stderr)
        sys.exit(1)
```

### 7.3 接入 `.pre-commit-config.yaml`

```yaml
repos:
  - repo: local
    hooks:
      - id: check-no-direct-messages
        name: 禁止直接构造 LLM messages
        entry: .venv/bin/python scripts/check_no_direct_messages.py
        language: system
        files: ^hagoku/(agents|manager)/.*\.py$
        pass_filenames: true
```

### 7.4 测试守门（独立测试，不依赖 hook）

`tests/test_doctrine/test_no_direct_messages.py`：

```python
"""通道守门：hagoku/agents/ 和 hagoku/manager/ 不许直接构造 messages。

这是 pre-commit hook 的 CI 镜像，确保即使 hook 被绕过，CI 也会拦下。
"""

def test_no_direct_messages_assignment_in_agents():
    """grep -rE 'messages\s*=\s*\[' hagoku/agents/ → 必须 0 行"""
    ...

def test_no_messages_append_in_agents():
    """grep -rE 'messages\.append\(' hagoku/agents/ → 必须 0 行"""
    ...
```

---

## §8 真 LLM 冒烟测试设计

### 8.1 冒烟脚本：`scripts/smoke/phase_b_channel_smoke.py`

```python
"""Phase B 真 LLM 冒烟：验证所有 LLM 调用都走 build_messages。

步骤：
1. HAGOKU_DUMP_LLM=1 启动
2. 加载 tests/fixtures/smoke_demo.csv
3. 走完 scout → cleaner → analyst → reporter 4 阶段
4. 收集所有 dump 文件，对每个 dump：
   - 验证 messages 第一条是 system（如果有 system_extra）
   - 验证 messages 至少 3 条（query / [history] / user_input）
   - 验证所有 role 都在 {"system","user","assistant"}
5. 对比 Phase B 改前 / 改后 dump：
   - LLM 看到的 system_prefix 应等于 ProjectContext.build_prompt()['system_prefix']
   - LLM 看到的 upstream_summary 应等于 ProjectContext.build_prompt()['upstream_summary']
   - LLM 看到的 history 应等于 ProjectContext.build_prompt()['messages_history']
"""
```

### 8.2 dump 对比基线

Phase B 改前先跑一次冒烟保留基线 dump：

```bash
# 改前基线
git stash  # 如有未提交改动
HAGOKU_DUMP_LLM=1 python scripts/smoke/phase_b_channel_smoke.py
mv ~/.hagoku/llm_dumps ~/.hagoku/llm_dumps.phase_b_before

# 改后对比
HAGOKU_DUMP_LLM=1 python scripts/smoke/phase_b_channel_smoke.py
python scripts/diff_dumps.py \
    ~/.hagoku/llm_dumps.phase_b_before \
    ~/.hagoku/llm_dumps \
    --report scripts/smoke/phase_b_dump_diff.md
```

### 8.3 对比报告必须包含

| 维度 | 期望 |
|---|---|
| 每个 dump 文件的 messages 行数 | 改后 = 改前 **或更多**（信息只多不少，对应 brief §4.3） |
| system_prefix 内容 | 完全相同（如果 ProjectContext 没动）|
| 4 agent 的 history 长度 | 改后 ≥ 改前（消除了"agent 各持一份残缺 history"的旧问题）|
| 任何 messages 包含 `"role": "fake_*"` | 0 个 |
| token 用量增加比例 | < 30%（接受 trade-off，但要监控）|

**审核硬门**：任何一个 dump 显示"改后 LLM 看到的信息变少"→ **拒绝合并**。

---

## §9 律的减法清单（Phase B 完成后）

| 律 / 刹车 | 当前文档位置 | Phase B 后状态 | 处理 |
|---|---|---|---|
| **律 5（状态层单一权威）** | `PROJECT.md §通道完备性十律` | 自动满足——ProjectContext 是物理唯一来源 | **降级为"历史背景"**，不删，加注「Phase B 后由架构保证」 |
| **铁律 11（通道优先律）** | `CLAUDE.md` 铁律 11 | 自动满足——`to_messages_for_llm` 强制路径 | **降级**，加注「`to_messages_for_llm` 是 Phase B 后的唯一合法入口」 |
| **Phase 0 build_messages 守门**（CLAUDE.md「不能做」第 5 条） | `CLAUDE.md` 「30 秒入门」 | 由 pre-commit hook + 测试自动守门 | **保留**，但措辞从"绝对不能做" → "技术上已拦截"|
| **触发词速查表** 中 "绕过 build_messages 直接构造 messages" 一行 | `CLAUDE.md` | 由 hook 拦截，触发词表降级为"了解项目历史" | **保留**，但标"已由 hook 自动拦截" |
| **新增反模式：tool 调用结果字符串化** | — | 方案 B 杜绝 | 加到 CLAUDE.md「绝对不能做」：禁止把 OpenAI tool 协议改写为 user 消息字符串——LLM 必须看到自己真实的推理链 |

**不动**：铁律 1 / 7 / 10 / -1 / -2 / -3 / -4。

---

## §10 风险点 + 应对（方案 B 修订版）

| # | 风险 | 概率 | 影响 | 应对 |
|---|---|---|---|---|
| R1 | 删 `_*_messages` 后 agent 失去多轮上下文，行为退化 | 中 | 高 | §8 冒烟对比 + 真 LLM 测试 |
| R2 | `to_messages_for_llm` 内 `system_prefix + upstream_summary` 拼接顺序与原 agent 期望不符 | 高 | 中 | 改造每个 agent 时先 dump 改前 system 字符串，改后对比 |
| R3 | ~~tool 字符串化导致 LLM 行为退化~~ | — | — | **方案 B 已解决**（标准 tool 协议）|
| R4 | pre-commit hook 误伤合法代码 | 中 | 低 | hook 排除 `tests/` 和 `hagoku/channel.py` |
| R5 | Pydantic 校验失败时错误信息不清楚 | 低 | 中 | 测试覆盖每种失败场景 |
| R6 | `scout_reply.py` 收缩时误删 ProjectContext 写回逻辑 | 中 | 高 | §6 强制 git diff 审核 |
| R7 | reply_handlers.py 改造后 `_run_analyst_first_pass` 行为变化 | 中 | 中 | 单独冒烟脚本验证首波行为 |
| R8 | ProjectContext 在 LLM 调用失败后状态污染 | 低 | 中 | `add_agent_response` "成功才写"——失败走铁律 7 RuntimeError |
| **R9** | **tool_exchange entry 持久化反序列化漏字段** | 中 | 中 | CO-B2-5 强制覆盖写入/读出完全相等 |
| **R10** | **UI 渲染 tool exchange 在长 tool 调用列表时性能差** | 低 | 低 | 默认折叠超过 5 个 tool 调用的条目；CO-B6 自查 |
| **R11** | **WebSocket 现有事件流与 `TOOL_EXCHANGE` 事件名冲突** | 低 | 中 | CO-B6-1 调研后报告审核方，无冲突再继续 |
| **R12** | **LLM 实际返回的 tool_calls 字段结构与 `ToolCall` TypedDict 不严格对齐**（如有些 LLM 网关包装层略不同）| 中 | 中 | CO-B3 改造时打印 resp.tool_calls 真实结构对比；必要时 `ToolCall` 改为 `dict` 宽松 |

---

## §11 6 个 CO-B 任务的精确执行顺序（方案 B + UI）

每个任务必须**独立 commit**（不允许把多个任务合在一个 commit 里）。每个任务完成后跑验证，**绿了**才能进下一个。

### CO-B0（预备步骤，0.5 天）

**目的**：建立改前基线，让后续每步都可对比。

| 子任务 | 命令 |
|---|---|
| B0-1 | 跑一次真 LLM 全流程（用现有冒烟脚本或手动 UI 走 scout→cleaner→analyst→reporter 全流程），保留改前 dump：`HAGOKU_DUMP_LLM=1` |
| B0-2 | `cp -r ~/.hagoku/llm_dumps ~/.hagoku/llm_dumps.before_phase_b` |
| B0-3 | 跑 `pytest tests/ -q` 记录当前 passed 数（基线 540）|

**Commit**：无（这是准备工作）。

---

### CO-B1：升级 `build_messages()` 为严格 schema + tool 协议支持（1 天）

| 子任务 | 操作 | 验证 |
|---|---|---|
| B1-1 | 按 §2.2（方案 B）升级 `hagoku/channel.py`——含 ChatTurn / ToolCall / _ChatTurnValidator / BuildMessagesInput | `python -c "from hagoku.channel import build_messages, BuildMessagesInput, ChatTurn, ToolCall"` |
| B1-2 | 新建 `tests/test_channel/test_build_messages_strict.py` 覆盖 §2.3 全部 8 种场景 | `pytest tests/test_channel/ -v` 8/8 pass |
| B1-3 | 跑全套测试 | 540 passed（不应有回归——所有调用方仍传 system/user/assistant content；tool role 进 history 是 CO-B3 才开始用）|

**预期问题**：某些调用方传的 `history` 含 `OpenAI assistant.message` 对象（带 `tool_calls`）会触发新 ValidationError → 这些调用方在 B3 改造时统一改 `to_messages_for_llm`。B1 阶段不需调整调用方——`history` 默认空时新校验不会触发。

**Commit message**：

```
[CO-B1] feat(channel): build_messages 升级支持 OpenAI tool 协议 + Pydantic 严格 schema

- ChatTurn TypedDict 支持 system/user/assistant/tool 四种 role + tool_calls/tool_call_id 字段
- _ChatTurnValidator 按 role 验证字段组合（assistant 可空 content 但必须有 tool_calls；
  tool 必须有 tool_call_id；user/system 不许有工具字段）
- BuildMessagesInput 顶层未知字段拒绝（extra='forbid'）
- 加测试覆盖 8 种边界场景
- 律 11（通道优先）从"靠人记住" → "技术拦截"
- 为方案 B（tool exchange 进 history）的多轮 tool 循环改造铺路
```

---

### CO-B2：升级 `ProjectContext` 支持 tool_exchange + `to_messages_for_llm`（1 天）

| 子任务 | 操作 | 验证 |
|---|---|---|
| B2-1 | 按 §3.4 在 `project_context.py` 新增 `tool_exchange` entry 类型 + `ToolCallRecord` dataclass | `pytest tests/test_context/ -v` 仍绿（旧测试不受影响） |
| B2-2 | 按 §3.4 扩展 `build_prompt()` 的 `messages_history` 部分支持 tool_exchange 展开 | 单测：含 tool_exchange 的 entries → 展开为 assistant+tool turn 序列 |
| B2-3 | 按 §3.4 实现 `add_tool_exchange()` 方法（含 emit `TOOL_EXCHANGE` 事件——开发者照 §16.4 适配现有 event_bus）| 单测：调用后 entries 增加 + event_bus 收到事件 |
| B2-4 | 按 §3.2 增加 `to_messages_for_llm()` 方法 | 单测：返回 messages 等于 `build_prompt + build_messages` 手动拼装 |
| B2-5 | 持久化兼容：`save_jsonl` / `load_jsonl` 新增 tool_exchange 反序列化 | 单测：写入 → 读出 → 完全相同 |
| B2-6 | 新建 `tests/test_context/test_tool_exchange.py`（覆盖 B2-1~B2-5 全部场景，~80 行） | 全绿 |

**Commit message**：

```
[CO-B2] feat(context): ProjectContext 新增 tool_exchange entry + to_messages_for_llm 统一入口

- 新增 ContextEntry.type="tool_exchange" 和 ToolCallRecord dataclass
- 新增 add_tool_exchange() 方法（含 TOOL_EXCHANGE 事件 emit 给 UI）
- build_prompt() 的 messages_history 扩展支持 tool_exchange 展开为
  OpenAI 标准协议（assistant(tool_calls) + tool(result)）
- 新增 to_messages_for_llm() 封装 build_prompt → build_messages 链路
- save_jsonl / load_jsonl 持久化兼容 tool_exchange
- 测试 6 个场景全覆盖

为 CO-B3（agent 多轮 tool 循环改造）和 CO-B6（UI 展示）铺路。
```

---

### CO-B3：4 agent 改造 + 删 3 套 `_*_messages`（2.5 天，**最大改动**）

⚠️ **本步动手前必须再次报告给审核方**——铁律 -2 + brief §2.2 红线 L2。

| 子任务 | 操作 | 验证 |
|---|---|---|
| B3-1 | Scout：行 618-622 改 `to_messages_for_llm`（保留单测路径）| `pytest tests/test_agents/test_scout/ -v` |
| B3-2 | Cleaner：删 `_compose_system_messages`；`run_step` / `assess` / `_plan_via_llm` 全改；多轮 tool 循环按 §4.2 方案 B 模式（每轮 `project_ctx.add_tool_exchange` + `to_messages_for_llm` 重建）| `pytest tests/test_agents/test_cleaner/ -v` |
| B3-3 | Analyst：删 `_compose_system_messages`；所有 LLM 调用改；tool 循环同 cleaner | `pytest tests/test_agents/test_analyst/ -v` |
| B3-4 | Reporter：同 Analyst（两处 LLM 调用点） | `pytest tests/test_agents/test_reporter/ -v` |
| B3-5 | orchestrator.py 删 3 个 `_*_messages` 字段 + 2 处 reset | `python -c "from hagoku.manager.orchestrator import Orchestrator"` |
| B3-6 | reply_handlers.py 11 处 `_*_messages` 使用改 `project_ctx.*` 调用；agent.run_step 签名从 `(context, messages)` 改 `(context, user_input)` | `pytest tests/test_manager/ -v` |
| B3-7 | **真 LLM 冒烟**：手动 UI 走全流程或现有冒烟脚本，`HAGOKU_DUMP_LLM=1` | 跑通无错 |
| B3-8 | dump 对比：手动 diff `~/.hagoku/llm_dumps.before_phase_b` 与新 dump | **所有 dump LLM 看到的信息只多不少**；多轮 tool 循环 dump 含标准 assistant(tool_calls) + tool(result) turn |

**Commit message**：

```
[CO-B3] refactor(agents): 4 agent 全部改走 ProjectContext.to_messages_for_llm（含方案 B tool 协议）

删除：
- _compose_system_messages（cleaner/analyst/reporter 各 1 处）
- _cleaner_messages / _analyst_messages / _reporter_messages 实例字段 + reset
- reply_handlers.py 11 处 _*_messages 操作

改为：
- 所有 LLM 调用点先 project_ctx.to_messages_for_llm() 重建 messages
- agent.run_step() 签名从 (context, messages) → (context, user_input)
- 多轮 tool 循环按方案 B：每轮 project_ctx.add_tool_exchange(tool_records) 
  写回，下一轮 to_messages_for_llm 自动展开为 OpenAI 标准协议
  (assistant(tool_calls) + tool(result) turn)

真 LLM 冒烟：通过（dump 对比无"LLM 看到信息变少"问题）
律的减法：律 5 自动满足；铁律 11 从"靠人记住"→"由架构保证"
```

---

### CO-B4：scout_reply.py 收缩（0.5 天）

| 子任务 | 操作 | 验证 |
|---|---|---|
| B4-1 | 按 §6.2 清单删除死代码 | `git diff --stat` 显示 ≤ -250 行 |
| B4-2 | 跑 Scout 阶段冒烟 | 字段语义推断行为不变 |

**Commit message**：

```
[CO-B4] refactor(scout_reply): 删除拼装残留与 dump 旁路死代码（净 -250 行）

- 删 dump 旁路独立构造 messages（行 443-448）—— 改用 build_messages 输出 + assistant_turn 字符串
- 删多版本兼容残留（具体见 git diff）
- ProjectContext 写回重复代码合并

文件从 652 行 → ~400 行
Scout 行为 dump 对比：完全一致
```

---

### CO-B5：pre-commit hook + ruff + CI 测试守门（0.5 天）

| 子任务 | 操作 | 验证 |
|---|---|---|
| B5-1 | 新建 `scripts/check_no_direct_messages.py`（§7.2） | `python scripts/check_no_direct_messages.py hagoku/agents/scout/agent.py` → 退 0 |
| B5-2 | 故意在 `hagoku/agents/scout/agent.py` 加一行 `messages = [{"role":"user"}]` 测 hook | 退 1，错误信息清晰 |
| B5-3 | 接入 `.pre-commit-config.yaml`（§7.3） | `pre-commit run --all-files` 通过 |
| B5-4 | 新建 `tests/test_doctrine/test_no_direct_messages.py`（§7.4） | `pytest tests/test_doctrine/ -v` 绿 |
| B5-5 | **回滚** B5-2 的故意违规 | grep 验证无残留 |

**Commit message**：

```
[CO-B5] chore(ci): pre-commit hook + 测试守门——禁止直接构造 messages

新增：
- scripts/check_no_direct_messages.py（AST 扫描）
- .pre-commit-config.yaml hook 接入
- tests/test_doctrine/test_no_direct_messages.py（CI 镜像）

例外：hagoku/channel.py 本身、tests/、dump_messages 调用

效果：未来任何 agent 想绕过 build_messages 直接拼装 → 提交即被拦
```

---

### CO-B6：UI 展示 tool exchange（1 天）

按 §16 完整设计实施。

| 子任务 | 操作 | 验证 |
|---|---|---|
| B6-1 | 调研 `hagoku/api/ws_handler.py` 和 `hagoku_web/src/` 现有 chat 事件流（按 §16.6 grep 命令）→ 报告审核方现状（在 PR 描述中贴 grep 输出） | 审核方确认契约与现有架构兼容 |
| B6-2 | 后端：按 §16.4 在 `ProjectContext.add_tool_exchange()` 末尾 emit `TOOL_EXCHANGE` 事件；按现有 WS 事件流模式（CO-B2 已铺好框架，仅在此挂事件名）| 前端 console 收到事件 |
| B6-3 | 前端：按 §16.5 新增 `ToolExchangeTurn` 组件 + WS hook 适配 + CSS 样式 | 手动测试：UI 渲染 "调用 schema_lint → 通过" 类条目 |
| B6-4 | 默认展开 + 可折叠；错误工具用红色样式（§16.5 关键 UI 决策） | UI 自查 |
| B6-5 | **真 LLM 冒烟 + UI 截图**：跑全流程，截图保留——证明用户能看到 AI 思考过程 | 截图贴 PR |

**Commit message**：

```
[CO-B6] feat(ui): chat 渲染 AI 工具调用过程（透明化核心体验）

后端：
- ProjectContext.add_tool_exchange 末尾 emit TOOL_EXCHANGE 事件
- 事件 payload 含工具名 / 简化入参与结果 / 错误信息

前端：
- 新增 ToolExchangeTurn 组件（默认展开 / 可折叠 / 错误红色）
- 处理 TOOL_EXCHANGE WebSocket 事件
- chat 渲染顺序：用户输入 → AI 思考 → 工具调用 → 工具结果 → AI 总结

效果：用户首次能看到 AI 的真实推理链——查字段 → 跑检验 → 看结果 → 下一步
这是 HaGoKu 与黑盒分析工具的核心差异
```

---

## §12 终审清单（开发者完成全部 CO-B 后给审核方）

```markdown
# Phase B 完成汇报（方案 B + UI）

## 改动统计
- 净代码减少：__ 行
- 净测试新增：__ 行
- 新增 pre-commit hook：1
- 新增测试：__ 个
- 新增前端组件：1（ToolExchangeTurn）

## 验证结果（全绿才能交付）
- B1: `pytest tests/test_channel/ -v` PASS __ / 8 场景全覆盖
- B2: `pytest tests/test_context/ -v` PASS __ / 6 场景全覆盖
- B3: `pytest tests/ -q` PASS __ / FAIL __
- B3 真 LLM 冒烟：脚本路径或手动 UI 操作截图
- B3 dump 对比：__ 处对比无"LLM 看到的信息变少"问题
- B3 多轮 tool 循环 dump 检查：含标准 assistant(tool_calls) + tool(result) turn
- B4: scout_reply.py 行数 __ → __
- B5: `pre-commit run --all-files` PASS
- B6: UI 截图（chat 渲染 "调用 schema_lint → 通过" 类条目）+ LLM 看到 tool 协议 dump 截图

## 4 种反模式根除证据
- 形态 1（messages = [...]）：`rg -nE 'messages\s*=\s*\[' hagoku/agents/ hagoku/manager/` 命中 __
- 形态 2（_compose_system_messages）：grep 命中 __
- 形态 3（_*_messages）：grep 命中 __
- 形态 4（build_messages 漏 system_extra）：人工 review 通过 __

## 律的减法
- 律 5：从 "用 grep 守门" → "由 ProjectContext 唯一来源结构保证"
- 铁律 11：从 "靠人记住" → "由 pre-commit hook 拦截"
- 触发词速查表第 4/5 条：可降级为"历史背景"
- CLAUDE.md「绝对不能做」新增："tool 调用结果字符串化"

## 6 个 commit 哈希
- CO-B1: __
- CO-B2: __
- CO-B3: __
- CO-B4: __
- CO-B5: __
- CO-B6: __

## 风险残留
- __（如无填"无"）
```

---

## §13 不做什么（明确边界）

- ❌ 不动 `ProjectContext.build_prompt` 的核心结构（per-agent 派生逻辑保留——Phase D 才统一）
- ❌ 不动 4 个 agent 的 prompt.md（铁律 10 适用——动 prompt 必须配 dump 对比，且不在本 Phase 范围）
- ❌ 不动统计护栏 / 数据 I/O / 可视化工具（brief §2.2 红线 L7）
- ❌ 不动 Meta 层基建（brief §2.2 红线 L4）
- ❌ 不引入新依赖（除非必须，且要在 commit message 写明理由）
- ❌ 不"顺手"做任何 Phase C/D/E/F 的工作

---

## §16 UI 展示 tool exchange（HaGoKu 透明化的核心体验）

### 16.1 设计目标

让用户在 chat UI 看到 AI 真实的思考过程：「查字段 → 跑检验 → 看结果 → 下一步」。这是 HaGoKu 区别于"黑盒分析工具"的核心差异化体验。

### 16.2 当前 WebSocket / 事件流

调研时未深入 `hagoku/api/ws_handler.py` 和 `hagoku_web/src/`，本节给**接口契约**和**行为期望**，开发者按现有事件流模式实现。

### 16.3 WebSocket 事件契约（新增）

```typescript
// hagoku_web/src/types/events.ts（新增类型）

interface ToolCallEvent {
  type: "tool_exchange";
  stage: "scout" | "cleaner" | "analyst" | "reporter";
  revision: number;
  timestamp: string;
  assistant_pre_text?: string;  // LLM 在调工具前可能说的话
  tool_calls: Array<{
    id: string;
    name: string;           // 工具名（如 "schema_lint", "zero_var_check"）
    arguments_summary: string;   // 简化的入参展示（不展示完整 JSON）
    result_summary: string;      // 简化的结果展示
    error: string | null;
    duration_ms: number;
  }>;
}
```

### 16.4 后端 emit 点（新增）

在 `ProjectContext.add_tool_exchange()` 调用后，通过 `_event_bus` emit 事件。具体改动：

```python
# hagoku/context/project_context.py 的 add_tool_exchange 末尾
def add_tool_exchange(self, ...):
    # ... 已有逻辑
    self.add_entry(entry)

    # 新增：emit 事件
    if self._event_bus:
        self._event_bus.emit("TOOL_EXCHANGE", stage, {
            "stage": stage,
            "revision": revision,
            "timestamp": entry.timestamp,
            "assistant_pre_text": assistant_content or None,
            "tool_calls": [
                {
                    "id": tc.tool_call_id,
                    "name": tc.name,
                    "arguments_summary": _summarize_arguments(tc.arguments),
                    "result_summary": _summarize_result(tc.result, tc.error),
                    "error": tc.error,
                    "duration_ms": 0,  # tool_exec 计时由 agent 传入；本设计稿不展开
                }
                for tc in tool_calls
            ],
        })
```

### 16.5 前端 UI 设计

#### 渲染样式（推荐）

```
[AI thinking icon]  分析师正在思考...
  ↓
  → 调用 schema_lint(cols=["Code", "Revenue"])   ✓ 通过
  → 调用 zero_var_check(col="Code")              ❌ Code 列零方差
  → 调用 unique_count(col="Code")                ✓ 5 个唯一值
[AI message icon]   "Code 列只有 5 个唯一值，0 方差——建议作为 identifier 而非 feature。"
```

#### 关键 UI 决策

| 决策 | 选择 | 理由 |
|---|---|---|
| 默认是否展开 tool 调用详情 | **默认展开**（用户已选）| HaGoKu 透明化核心体验 |
| 是否可折叠 | 可折叠（点击 tool 调用条目展开/收起完整入参与结果）| 进阶用户深查 |
| 工具调用 + assistant 文本是否合并展示 | 合并展示（一组 tool_exchange + 后续 agent_response 作为一个"思考-行动-总结"块）| 推理链可视化 |
| arguments / result 完整 vs 摘要 | 默认摘要，点击查看完整 | 信息密度可控 |
| 错误工具调用的样式 | 红色 + 错误信息（铁律 7 失败在场——UI 也要让用户看见）| 与代码层一致 |

#### 前端文件改动（估算）

| 文件 | 改动 |
|---|---|
| `hagoku_web/src/components/ChatTurn.tsx`（或现有 chat 组件）| 新增 `ToolExchangeTurn` 子组件 |
| `hagoku_web/src/hooks/useWsEvents.ts`（或现有 WS hook）| 处理 `TOOL_EXCHANGE` 事件，append 到 chat 列表 |
| `hagoku_web/src/styles/chat.css` | 新增 tool 调用条目样式 |

### 16.6 调研缺口（开发者执行时补）

**审核方未深查 WebSocket 现有事件流和前端 chat 组件结构**——开发者执行 §11 CO-B6 前先 grep 摸清：

```bash
# 后端：现有事件 emit 模式
rg -n "event_bus.emit|EventType\." hagoku/api/ hagoku/context/ hagoku/manager/

# 前端：现有 chat 渲染入口
rg -n "ChatTurn|MessageRender|chat_history" hagoku_web/src/
```

开发者将基于实际模式适配；如果发现现有架构与本设计稿假设不符，**先报告审核方再动**——不许"按自己理解"扩展。

---

## §14 审核方对开发者的硬规则

1. 本设计稿用户已审完整版（含方案 B + UI），CO-B1/B2/B4/B5/B6 可按本稿直接执行，**不需要每步重新申请**
2. **CO-B3（最大改动）动手前必须再次报告审核方**——铁律 -2 + brief §2.2 红线 L2，单独门禁
3. 任何回滚都不许 `git revert`，只能正向修复（铁律 -1）
4. 任何"我觉得"的判断都不算数——必须给 dump / grep / 测试输出做证据
5. 6 个 commit 必须**严格独立**，不允许"为了方便"合并
6. 任何超出本设计稿范围的改动（哪怕看起来很合理）→ 先停下来问审核方
7. 全套测试任何 FAIL → 停下来贴 stderr 给审核方，不许自己尝试修
8. CO-B6 前端改动如果涉及调研缺口（§16.6 grep 显示现有架构与本稿假设不符）→ 报告审核方再继续

---

## §15 完成标准

Phase B **完成** ≡ 同时满足：

- [ ] 6 个 CO-B commit 全部合并到主分支
- [ ] §11 每步验证全绿
- [ ] §12 终审清单完整且全绿
- [ ] §8 真 LLM 冒烟 dump 对比报告通过审核方检视
- [ ] 律的减法清单已更新到 PROJECT.md 和 CLAUDE.md
- [ ] UI 截图显示用户能看到 AI 工具调用过程（CO-B6）
- [ ] 风险残留经审核方接受

Phase B 完成后才能开 Phase C 设计稿。
