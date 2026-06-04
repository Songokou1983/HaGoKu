# 事件驱动通道 —— R2（回应诊断意见）

> 日期: 2026-06-04 | 修订: R2 | 状态: 设计阶段

## 核心理念

通道是事件驱动的对话。`_pause_and_wait` 卡线程 = 代码在替 LLM 等用户。
通道应该是：LLM 产出 → 事件通知 → 函数返回 → 用户输入到达 → 下一段函数执行。

## 当前问题（重写：敌是编排层串行阻塞，不是内层循环）

`orchestrator.run()` 在单线程里依次阻塞 3 次：Scout 暂停 → Cleaner 暂停 → Analyst 暂停。线程始终卡着不释放。

Scout 多轮对齐已拆到 `scout.respond()`，Analyst 用了 `pause_callback` —— 内层没有 `while True`。唯一残留是 CLI 路径的 `_request_field_confirmation`。

**真正的敌人**：编排层把 3 个阶段串起来在同一个线程里跑完。应该每次跑一个阶段就返回，等用户输入再跑下一个。

## 设计方案

### 1. 架构

```
analyze → run() → Scout 推断 → emit 字段表 → 返回（线程释放）
respond(用户输入) → 根据当前阶段 + LLM 的 route_to tool_call 决定下一步
```

阶段切换由 **LLM 自己决定**：`route_to(stage="cleaner")` / `route_to(stage="scout")` / 不调 tool 留在当前阶段。

### 2. 路由：律 8 落地

**不用 if-elif 链判断"确认继续"**。LLM 通过 `route_to` 工具主动表达切换意图。

```
Tool: route_to
description: 表达流程意图。留在当前阶段继续对话，或切换到下一阶段。
parameters:
  stage: "scout" | "cleaner" | "analyst" | "reporter" | null
  reason: string  # 切换原因（null=留在当前阶段继续）
```

代码行为：
- LLM 不调 `route_to` → 留在当前阶段，继续对话
- LLM 调 `route_to(stage="cleaner")` → 代码执行 Cleaner 入口，展示评估表，暂停
- LLM 调 `route_to(stage="scout")` → 回到 Scout 字段对齐

**为什么不是代码判断"确认继续"**：LLM 比代码更懂当前对话意图。用户说"好"可能真的是确认，也可能是"好但是我还要改 Inc2"。代码不该替 LLM 做这个判断。

**哪个 LLM 调 `route_to`**：各阶段 Agent 自己的 LLM。Scout 字段对齐时由 Scout 的 LLM 调，Analyst 对话时由 Analyst 的 LLM 调。**不是 orchestrator 层调。** 代码只负责收到 tool_call 后执行路由。

### 3. 状态存储（跨 respond() 调用）

`run()` 拆成多段独立函数，每次返回。状态不在线程栈上，需要显式存储。

| 状态 | 存哪 | 生命周期 |
|------|------|---------|
| 当前阶段 (`_stage`) | `self._stage: str` | run() 到 run() |
| 上下文 (`context`) | `self._context: dict` | 整个分析生命周期 |
| DataFrame (`df_clean`, `df_raw`) | `self._df_clean: pd.DataFrame` | 整个分析生命周期 |
| 对话历史 (`messages`) | `self._context["column_semantics"]` / ProjectContext | 整个分析生命周期 |
| CleaningReport | `self._cleaning_report` | Cleaner 阶段 |
| Analyst messages | `self._analyst_messages: list` | Analyst 阶段 |
| 项目/run 元数据 | `self._run_meta: dict` | 整个分析生命周期 |

**为何放 self 不重建**：每次都 `load_data` + `assess` 浪费 LLM token。DataFrame 在内存中的开销可接受。
**释放策略**：`run()` 入口检查 `self._df_clean is not None` → 先 `del self._df_clean` 再加载新数据。`self._context` 同理。Orchestrator 是全局单例，不释放 = 内存累积泄漏。

### 4. 路由表定义

`respond()` 根据 `self._stage` 分发：

```python
_STAGE_HANDLERS = {
    "scout":      "_handle_scout_reply",
    "cleaner":    "_handle_cleaner_reply",
    "analyst":    "_handle_analyst_reply",
    "reporter":   "_handle_reporter_reply",
}
```

每个 handler 内部处理 LLM tool_calls。如果 LLM 调了 `route_to(stage="X")`，handler 返回 `("switch", "X")`。外层根据返回值调下一阶段入口。

不嵌套 if-elif 判断用户文本中的"确认继续"关键词。

### 5. Analyst 单步：方案 B（保留 30 轮循环，只换暂停方式）

Analyst 的 `for round_idx in range(30)` 循环保留——这是对话轮次，不是通道循环。

**改的是暂停方式**：不传 `pause_callback`（阻塞），改为 Analyst 每轮输出后直接 return。下一轮由 `respond()` 驱动继续。

```
analyst.run_step(messages) → LLM 调工具/返文本 → return (messages, 是否 submit_analysis)
respond(用户回复) → messages.append(用户回复) → analyst.run_step(messages) → ...
```

不选方案 A（跑 1 轮就返回）因为那样需要把 `for` 循环提到编排层，把 Analyst 内部逻辑外泄。

### 6. 现有 phase 模式去留

| phase | 行为 | 事件驱动后 |
|-------|------|-----------|
| `full` | Scout→Cleaner→Analyst→Reporter | 默认行为 |
| `scout_first` | 只跑 Scout | `route_to` 停在 Scout |
| `analyst_first` | Scout(缓存)+Cleaner(已确认)+Analyst | 废弃——resume 机制替代 |
| `cleaning_first` | 同 analyst_first | 同上 |

保留 `phase="full"` 和 `phase="scout_first"`。废弃 `analyst_first`/`cleaning_first`。

### 7. Cancel 机制

"重置分析"时前端发送 `cancel_analysis`。事件驱动下：
- 设置 `self._cancel_requested = True`
- 任何 `respond()` 到达时检查标志 → 返回 `cancelled` 状态
- 前端收到后回到初始页面

### 8. 律 2 raw_text 跨调用保留

每次 `respond()` 调用时，`raw_text` + `stage` + `revision` 写入 ProjectContext：

```python
project_ctx.add_user_feedback(stage=self._stage, revision=self._revision, raw_text=user_input)
```

LLM 下一轮对话时，ProjectContext 的 `messages_history` 自动包含上游用户原话。不需额外设计。

### 9. 错误边界

每个 handler 内部 try/except。失败时：
- 记 `self._error = e`
- 写 `db.fail_run(run_id, duration_ms, error=str(e))`
- emit `RUN_FAILED`
- 下次 `respond()` 检查 `self._error` → 返回错误状态

### 10. 守门测试

| 编号 | 测试 |
|------|------|
| G1 | `run()` 返回后线程释放（`_analysis_in_progress = False`） |
| G2 | `respond()` 两次纠正 + 一次确认 → Scout→Cleaner 切换 |
| G3 | LLM 调 `route_to(stage="cleaner")` → 阶段切换 |
| G4 | `respond()` 在 `cancel_requested` 状态 → 返回 cancelled |
| G5 | handler 异常 → `_error` 设置 + `RUN_FAILED` emit |
| G6 | raw_text 跨两次 `respond()` 调用 → ProjectContext entries 递增 |

### 已知遗留（实现过程中补）

| # | 隐患 | 处理时机 |
|---|------|---------|
| 3 | phase 废弃模式 → 前端传 `analyst_first` 的行为 | 实现过程中 ws_handler 加 400 或自动转 full |
| 4 | 守门测试覆盖律 1/3/6/7 | 提测前补 G7（raw_text 录回）、G8（跨 respond messages 累积） |
| 5 | 错误恢复路径（`self._error` + 重置 `self.*`） | `run()` 入口补重置逻辑 |
| 6 | dump 验收（LLM 调用次数 = 阶段数 + 纠正次数） | 实现完成后跑完整流程验证 |

## 改动清单

| 文件 | 改什么 |
|------|--------|
| `orchestrator.py` | `run()` 改入口：执行 Scout 推断 → 设置 `self._stage="scout"` → 返回 |
| `orchestrator.py` | 新增 `_handle_scout_reply()` / `_handle_cleaner_reply()` / `_handle_analyst_reply()` / `_handle_reporter_reply()` |
| `orchestrator.py` | `respond()` 根据 `self._stage` 路由到对应 handler |
| `orchestrator.py` | 删 `_pause_and_wait` |
| `analyst/agent.py` | `run()` 改接受可选 `messages` 参数（续跑）；每轮输出后 return |
| `analyst/agent.py` | 删 `pause_callback` 参数 |
| `ws_handler.py` | `run()` 返回后释放 `_analysis_in_progress`（已在现有 finally 中） |
| `tools/agent_tool_defs.py` | 新增 `route_to` 工具 |

### 不改

- Scout/Cleaner/Analyst/Reporter 内部 LLM 调用逻辑
- WebSocket 协议
- 前端
