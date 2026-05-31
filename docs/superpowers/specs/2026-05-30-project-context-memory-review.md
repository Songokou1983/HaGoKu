# ProjectContext 设计审核报告

> 审核对象：
> - `docs/superpowers/specs/2026-05-30-project-context-memory-design.md`（设计规格）
> - `docs/superpowers/plans/2026-05-30-project-context-memory-plan.md`（8 任务实现计划）
> - `PROJECT.md` §「ProjectContext — 统一上下文记忆系统」（已合入主文档）
>
> 审核时间：2026-05-31
> 审核结论：**思路核心成立，但 plan 中有 3 个必修问题、5 个建议问题。按当前 plan 直接落地会出现「假实现律 3」「双重注入」「初始快照缺失」三重退化，必须修订 spec 与 plan 后再开工。**

---

## 一、设计核心评价

### ✅ 已经做对的事

1. **诊断准确**：识别出 `_session_messages` / `_conversation_history` / `utterances` 各自为政的现状
2. **架构定位干净**：`ProjectContext` 作为 `EventBus` 的被动消费者，与 `Scribe` 平级互补，不干涉流程控制
3. **追加式只增不改**：`entries` 不可删除、不可修改，提供律 2 审计性 + 不可变历史
4. **律 5 显式合规**：`snapshot` 由 `_derive_snapshot(context)` 从 `column_semantics` 实时派生，spec §6 表格明确不平行存储
5. **两阶段渐进路线**：阶段 1 与旧路径并行，阶段 2 替换旧路径，风险可控
6. **测试覆盖完备**：单元测试（11 条）+ EventBus 集成（4 条）+ 信息抵达正向断言（3 条）

---

## 二、🔴 必修 3 处（不修则方案落地后通道弱于现状）

### 必修 1：`history_context` 拼为单 user 消息文本，违反律 3「message list 形式」

**问题位置**：`plan` 任务 5 步骤 2

```python
# plan 当前写法
messages = [
    {"role": "system", "content": system_msg + "\n\n" + ctx_block["system_prefix"]},
    {"role": "user",   "content": ctx_block["history_context"] + "\n\n【当前用户输入】\n" + raw},
]
```

**为什么是退化**：

- 律 3 原文（`PROJECT.md:141-145`）：「同一 Agent 在同一暂停点的多轮交互必须以 **message list** 形式累积」
- 当前 P1 已落地的 `_apply_scout_reply_with_llm` 是真正的 messages list 结构（`hagoku/manager/orchestrator.py:984-994`），LLM 看到 `[user, assistant, user, assistant, ...]` 标准多轮交替
- 新方案把整段历史拼成一个 user 消息文本，**LLM 对「这段是历史 vs 当前」的角色边界识别变弱**——这是文本日志，不是对话

**修法**：`build_prompt` 应该返回标准 messages list 而非纯文本：

```python
# 修后的 build_prompt 返回
{
    "system_prefix": str,           # 状态描述（拼到 system role）
    "upstream_summary": str,        # 上游阶段摘要（拼到 system role 末尾）
    "messages_history": list[dict], # 当前阶段对话，标准 messages list
}

# 调用方
messages = [
    {"role": "system", "content": system_msg + "\n\n" + ctx_block["system_prefix"]
                                  + "\n\n" + ctx_block["upstream_summary"]},
    *ctx_block["messages_history"],  # [{"role": "user", ...}, {"role": "assistant", ...}]
    {"role": "user", "content": raw},
]
```

**对应改动**：
- `spec §3.4` 改 `build_prompt` 返回字典 schema
- `plan 任务 1 步骤 2` 改 `build_prompt` 实现
- `plan 任务 5 步骤 2` 改调用方拼装

---

### 必修 2：`system_prefix` 与 Agent 自身 system_prompt **双重注入** analysis_goal / command_context

**问题位置**：

- `hagoku/agents/scout/agent.py:608-628` 已注入 `analysis_goal_line`、`command_context`
- `plan 任务 1 步骤 2` 的 `system_prefix` **又写了一遍**这两项

**为什么是问题**：

- LLM 看到 `分析目标: X` 在 system 里出现两次但措辞不同 → 解读不一致
- 出 bug 时定位难（"是哪一边的 prompt 写错了？"）
- 维护成本翻倍——任一处规则变更须双更新

**修法**：spec §3.5「集成点」必须明确分工：

| 注入位 | 职责 | 内容 |
|--------|------|------|
| Agent 自身 system_prompt | **静态身份与工具行为** | "我是 Scout，我能调 X/Y/Z 工具" + `prompt.md` 行为约束 |
| `ProjectContext.system_prefix` | **动态运行时状态** | analysis_goal / 当前字段状态 / pending / `_pending_command_text` |

**配套代码改动**（plan 任务 5 应同步包含）：
- 删除 `hagoku/agents/scout/agent.py:608-628` 的 `analysis_goal_line` 拼接
- 删除 `hagoku/agents/scout/agent.py:599-606` 的 `command_context` 拼接
- 删除其他 Agent 的同类重复（按各自 agent.py 检视）

---

### 必修 3：`subscribe(bus, context_ref=None)` 让初始 Scout 快照丢失

**问题位置**：`plan` 任务 3 步骤 1-3

```python
# 任务 3 步骤 1（run() 早期）
self._project_context.subscribe(self.event_bus, context_ref=None)

# 任务 3 步骤 2（Scout 跑完后再补）
self._project_context._context_ref = context
```

**为什么是问题**：

- Scout 跑完前，`AGENT_STARTED` / `AGENT_COMPLETED` / `USER_INPUT_RECEIVED` 事件仍会触发回调
- 回调中 `_derive_snapshot(self._context_ref)` 在 `_context_ref=None` 时退化为空 snapshot
- **初始 Scout 字段推断的 snapshot 整个丢失**——而这恰恰是下游 Cleaner / Analyst 看 history_context 时最重要的上游摘要
- 这是 ProjectContext 想解决的核心问题，结果 plan 直接跳过它

**修法**：在 `Orchestrator.run()` 最开始就建空 `context` dict 并保持引用稳定：

```python
# run() 开头（修后）
context: dict[str, Any] = {}  # ← 一次性建立，从头到尾保持同一引用
self._project_context = ProjectContext(run_id=run_id, analysis_goal=query)
self._project_context.subscribe(self.event_bus, context_ref=context)

# Scout 跑完后，往同一个 dict 里写而非重新赋值
scout_result = scout.run(...)
context.update(scout_result)  # ✅ 不要写 context = scout.run(...)
```

**关键约束**：`context` 必须自始至终是同一个 dict 引用——任何 `context = ...` 重新赋值都会破坏 ProjectContext 已注册的引用。`plan 任务 3` 必须明确这一约束并在 doctrine compliance 加守门。

---

## 三、🟡 建议 5 处（影响合规清晰度，强烈建议同步处理）

### 建议 4：`utterances` vs `entries` — 律 5 单一权威要二选一

**现状**：用户原话同时记录两处

| 数据 | 写入位 | 用途 |
|------|------|------|
| `context["utterances"]` | `_apply_scout_reply_with_llm` 入口 (`orchestrator.py:805-810`) | 律 2 审计 |
| `ProjectContext.entries[type=user_feedback]` | EventBus `USER_INPUT_RECEIVED` 回调 | history_context 拼装 |

这是律 5 隐性违规——同一信息平行存储两份。下个 AI 看到会困惑：律 2 落地点是哪个？

**修法**（任选其一，spec §3.2 必须明示）：
- **方案 A（推荐）**：`entries[type=user_feedback]` 已含 `raw_user_text`，删除独立的 `utterances` 数组
- **方案 B**：保留 `utterances` 作为不可变 raw 原料源，`entries` 通过索引/时间戳引用，不复制 raw 文本

---

### 建议 5：spec §7「不做什么」漏写关键边界

**现 spec §7** 列了 5 条不做。建议追加 3 条：

```markdown
- 不替代律 4「工具 schema 覆盖完备律」——工具治理仍归各 Agent 各自维护
- 不替代 _last_understanding_failure ——律 7 的写入点仍是 context dict，
  ProjectContext 通过 EventBus 监听同步进 entries 作为审计
- 不做跨 run 持久化（重申，已有但建议加粗强调）
```

否则下个 AI 看到 ProjectContext「统一系统」可能误以为律 4/律 7 也该融进来，开始过度集中化。

---

### 建议 6：`build_prompt` 的中文枚举映射要明确合规属性

**问题代码**（plan 任务 1 步骤 2）：

```python
status = "参与" if f["participating"] is True else ("不参与" if f["participating"] is False else "待定")
```

这是 `bool/None → 中文标签` 的格式化映射，**属于代码合法职责**（律 5「派生视图渲染」）。但措辞像极了 doctrine compliance test 守门 3 抓的「中文 if-elif 语义分支」。

**风险**：未来实施 AI 看到这段，可能错误延伸为：

```python
# AI 误以为合法的扩展
if role == "目标变量": ...
elif role == "特征变量": ...
elif role == "无关字段": ...  # ← 这就违规了
```

**修法**：spec §6 合规表格追加一条：

> | 类别 | 判定 |
> |------|------|
> | **格式化职责** | `build_prompt` 内 `bool/None → 中文标签` 映射属于派生视图渲染，非语义判断。约束：分支数 ≤3 且不引入新业务概念。`test_doctrine_compliance.py` 守门 3 不会拦此类映射。 |

---

### 建议 7：阶段 2 收尾必须清理所有 `if project_ctx else 旧路径` 防御性分支

**现 plan 任务 5/6** 留了大量：

```python
if project_ctx:
    # 新路径
else:
    # 降级旧路径
```

两阶段并行结束后，这些分支必须删干净——否则会再积累出新的「`_KNOWN_LLM_EXCEPT_VIOLATIONS` 类历史债务」。

**修法**：`plan 任务 8` 末尾追加步骤：

```markdown
- [ ] **步骤 4：清理阶段 1 留下的 if project_ctx 防御分支**

```bash
grep -n "if project_ctx\|if hasattr.*_project_context\|_session_messages" hagoku/manager/orchestrator.py
# 全部清除——ProjectContext 应作为强制依赖而非可选组件
```

- [ ] **步骤 5：在 doctrine compliance 加守门**

在 `tests/test_doctrine_compliance.py` 追加：

```python
def test_doctrine_无_session_messages_残留() -> None:
    """阶段 2 完工后，_session_messages 字面量不得在 hagoku/ 中出现。"""
    violations = []
    for path in HAGOKU_ROOT.rglob("*.py"):
        if "_session_messages" in _read(path):
            violations.append(str(path.relative_to(HAGOKU_ROOT)))
    assert not violations, f"_session_messages 残留: {violations}"
```
```

---

### 建议 8：`stage_transition` 不应混进 `history_context` 对话流

**问题代码**（plan 任务 1 步骤 2）：

```python
elif e.type == "stage_transition":
    history_parts.append(f"── {e.content} ──")
```

LLM 看到 user/Agent 对话中突然冒出 `── 进入 cleaner 阶段 ──`，会困惑「这是谁说的」（用户？系统？Agent？）。

**修法**：

- 当前阶段的 `messages_history` 中不渲染 `stage_transition`
- 上游摘要中以独立 system 注入或专门字段表达，例如：

```python
upstream_summary = (
    "【上游阶段摘要】\n"
    f"Scout 完成: target=Revenue, features=[Code, Period]\n"
    f"Cleaner 完成: 已剔除缺失 >50% 列\n"
    "（用户对你的当前输入即将开始）"
)
```

`stage_transition` 仅作为 `entries` 内部时间戳分隔，不进入 LLM messages。

---

## 四、修订 checklist（给实现 AI 逐项核对）

修订 spec 时打勾：

- [ ] §3.4 `build_prompt` 返回值 schema 改为含 `messages_history: list[dict]`（必修 1）
- [ ] §3.5 集成点表格明确「Agent system_prompt 静态、ProjectContext system_prefix 动态」分工（必修 2）
- [ ] §4 阶段 1 任务 3 的 `subscribe` 步骤明确 `context_ref` 传递的是真实的空 dict 引用（必修 3）
- [ ] §3.2 数据模型明示 `utterances` 与 `entries` 的二选一决议（建议 4）
- [ ] §7「不做什么」追加 3 条边界（建议 5）
- [ ] §6 合规表格追加「格式化职责」条目（建议 6）
- [ ] §4 阶段 2 末尾追加「清理 if project_ctx 防御分支」步骤（建议 7）

修订 plan 时打勾：

- [ ] 任务 1 步骤 2 改 `build_prompt` 实现（必修 1：返回 messages_history、必修 6：枚举映射的合规注释）
- [ ] 任务 3 步骤 1-3 改 `subscribe` 流程（必修 3）
- [ ] 任务 5 步骤 2 改 `messages` 拼装（必修 1）
- [ ] 任务 5 新增步骤：删除 Agent 自身 system_prompt 中的 `analysis_goal_line` / `command_context`（必修 2）
- [ ] 任务 6 新增步骤：明示 `utterances` 是否同步移除（建议 4）
- [ ] 任务 8 步骤 4-5：清理防御分支 + 加 doctrine 守门（建议 7）

---

## 五、修订后再做的事

修订完成后：

1. 让实现 AI 拿修订版 plan 走 8 任务流程
2. 每完成一阶段跑：`pytest tests/test_doctrine_compliance.py tests/test_product/test_information_arrival.py tests/test_context/`
3. 阶段 2 完成后跑全套 `pytest --tb=short -q`
4. 真实 LLM 验证：用 test0526 同构数据集走 Scout→Cleaner→Analyst 三阶段，断言 Cleaner 阶段 LLM 在 prompt 中看到 Scout 阶段的 snapshot 摘要

通过以上验证，方案才算真正完成「跨 Agent 对话连续性」的目标。

---

## 六、给项目所有者的一句话

> 你的实现 AI 抓到了正确方向（统一上下文系统），但 plan 里把"用 messages list"误改成"用文本日志"，把"统一注入"误做成"双重注入"，把"快照引用稳定"误处理成"None + 后补"。
>
> 这三处都是**通道完备性十律的微妙边界——文档说得越抽象，实施 AI 越容易在落地时悄悄偏移**。
> 修订 spec 与 plan 把这 3 必修的边界写死，再交给实施 AI，方案就稳了。
