# 通道日志系统设计

## 目的

让开发者能在一分钟内定位通道问题——query 是否到达 LLM、LLM 输出什么、哪个代码环节改动了值。今天调试「字段全选」问题花了 5 小时，有日志的话 5 分钟。

## 核心原则

- **决策链**：每个值记录来源，不只看"是什么"，看"谁决定的"
- **临时性**：跟着 run 走，清除项目历史时一起删
- **低侵入**：不改变现有函数签名，用一个全局 logger 实例收拢

## 文件结构

```
~/.hagoku/projects/<project>/runs/<run_id>/
├── context.md
├── run.log      ← 通道事件 + 决策链
└── llm.log      ← LLM 完整输入输出
```

## run.log — 通道事件 + 决策链

JSONL 格式，每行一条。字段：

| 字段 | 说明 |
|------|------|
| ts | ISO 时间戳 |
| agent | scout / cleaner / analyst / reporter / orchestrator |
| event | 事件类型（见下表） |
| * | 事件相关数据 |

事件类型：

| event | 触发时机 | 关键数据 |
|-------|---------|---------|
| run_start | 新 run 开始 | query, project, run_id |
| scout_start | Scout 启动 | data_path, columns |
| cache_check | 缓存查询 | result: hit/miss, cached_query, current_query |
| llm_call | LLM 调用前 | model, prompt_len |
| llm_response | LLM 返回后 | columns, tokens, duration_ms |
| uia_set | used_in_analysis 被设置 | column, value, source: llm/cache/user |
| role_set | suggested_role 被设置 | column, value, source |
| field_updated | 用户纠正字段 | column, field, old_value, new_value |
| reinference_triggered | 触发重推断 | reason |
| channel_summary | run 结束 | query_arrived, uia_breakdown, warnings |
| error | 异常 | type, message, traceback |

## llm.log — LLM 完整输入输出

每条一条 JSON 记录：

| 字段 | 说明 |
|------|------|
| ts | ISO 时间戳 |
| agent | scout / cleaner / analyst / reporter |
| model | 模型名 |
| system_prompt | 完整 system prompt |
| user_prompt | 完整 user prompt |
| response_tool_calls | LLM 返回的 tool_calls 数组 |
| response_content | LLM 返回的 text（如有） |
| tokens | token 消耗 |
| duration_ms | 调用耗时 |

## ChannelLogger API

```python
class ChannelLogger:
    """每个 run 一个实例"""

    def __init__(self, run_dir: Path):
        self.run_log = run_dir / "run.log"
        self.llm_log = run_dir / "llm.log"

    # 通道事件
    def log(self, agent: str, event: str, **kwargs) -> None:
        """写 run.log"""

    # LLM 调用录制
    def log_llm(self, agent: str, model: str, system_prompt: str,
                user_prompt: str, response, tokens: int, duration_ms: int) -> None:
        """写 llm.log"""

    # 决策链 — 记录值是如何决定的
    def trace_value(self, agent: str, column: str, field: str,
                    value: Any, source: str) -> None:
        """写 run.log，event=uia_set/role_set/..."""

    # 通道健康摘要
    def summary(self, query_arrived: bool, uia_breakdown: str,
                warnings: list[str]) -> None:
        """写 run.log，event=channel_summary"""
```

## 接入点

不改现有函数签名。在以下位置插入 `channel_logger.log(...)`：

1. **Orchestrator.run()** — 创建 ChannelLogger 实例，存入 `self._channel_logger`
2. **Orchestrator.run() → Scout 调用** — 记录 scout_start, cache_check, uia_set, role_set
3. **Scout._infer_all_semantics()** — 记录 llm_call, llm_response + 完整 prompt
4. **Orchestrator._apply_scout_reply_with_llm()** — 记录 field_updated, reinference_triggered
5. **Orchestrator.run() 结束时** — channel_summary
6. **所有 except 块** — error

Agent 通过构造参数 `channel_logger` 接收，由 Orchestrator 在创建 Agent 时传入。

## 不覆盖

- 文件 IO、数据库、看板操作
- UI 渲染、WebSocket 消息
- 纯计算函数（统计、数据清洗）

## 存储

- 每个 run 两个文件，不轮转，不压缩
- 清除项目历史时随 run 目录一起删除
- 无持久化索引——用 grep/jq 查
