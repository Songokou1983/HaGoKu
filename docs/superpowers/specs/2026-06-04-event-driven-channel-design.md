# 事件驱动通道 —— 去循环、去阻塞

> 日期: 2026-06-04 | 状态: 设计阶段

## 核心理念

通道是事件驱动的对话，不是阻塞循环。`_pause_and_wait` 卡线程 = 代码在替 LLM 等用户。正确的通道是 LLM 产出 → 事件通知 → 返回 → 用户输入到达 → 下一段逻辑。

就像我们的对话：我回了消息，等着。你打字，发送，我收到，处理，回复。没有 `while True` 在等你的下一条。

## 当前问题

`orchestrator.run()` 是线程阻塞长函数：
- `_pause_and_wait` 用 `Event.wait()` 卡线程
- Scout 字段对齐用双层 `while True` 处理纠正
- Cleaner 评估用 `while True` 处理反馈

每个阶段都在同一个 `run()` 线程里转圈。通道被代码绑架了。

## 设计方案

### 架构

`run()` 不再阻塞。每个阶段执行完就返回。下一个事件由 `respond()` 驱动。

```
analyze → run() → Scout 推断 → emit 字段表 → 返回
respond → 处理纠正 → emit 更新字段表 → 返回
respond → 确认 → Cleaner 评估 → emit 评估表 → 返回
respond → 确认 → Analyst 单步 → emit LLM 输出 → 返回
respond → 继续 → Analyst 下一步 → emit → 返回
respond → submit_analysis → Reporter → emit 报告 → 完成
```

### 状态机

`orchestrator` 维护当前阶段状态。`respond()` 根据状态路由到对应处理函数。

| 状态 | 触发 | 执行 | 产出 |
|------|------|------|------|
| `scout_review` | analyze 完成后 | 展示字段表，等用户 | USER_INPUT_REQUESTED → 返回 |
| `scout_review` | respond(纠正文本) | LLM 处理，更新字段表 | 展示新字段表 → 返回 |
| `scout_review` | respond("进入下一阶段") | 确认 | 切换到 `cleaner_review` |
| `cleaner_review` | 自动 | Cleaner.assess() | 展示评估表 → 返回 |
| `cleaner_review` | respond(反馈) | LLM 重新评估 | 展示新评估表 → 返回 |
| `cleaner_review` | respond("确认") | 确认 | 切换到 `analyst` |
| `analyst` | 自动 | Analyst 单步 | LLM 文本 → 返回 |
| `analyst` | respond(回复) | Analyst 继续下一步 | LLM 文本 → 返回 |
| `analyst` | submit_analysis | 分析完成 | 切换到 `reporter` |
| `reporter` | 自动 | Reporter 生成 | 报告 → 完成 |

### 数据保留

状态切换时保留 `context`（字段表、评估、对话历史）。`ProjectContext` 追加记录每次交互。

### 不改

- Scout/Cleaner/Analyst/Reporter 内部 LLM 逻辑
- WebSocket 协议
- 前端

### 改

| 文件 | 改动 |
|------|------|
| `orchestrator.py` | 拆 `run()`：`_run_scout()` / `_run_cleaner()` / `_run_analyst_step()` / `_run_reporter()` |
| `orchestrator.py` | `respond()` 根据状态路由到对应函数 |
| `orchestrator.py` | 删 `_pause_and_wait`，删所有 `while True/for` 循环 |
| `analyst/agent.py` | `run()` 改单步：传入对话历史，返出一轮输出。下次继续从历史续 |
| `ws_handler.py` | `respond` 路由到 orchestrator 状态机 |
