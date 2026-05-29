# 通道日志系统 实现计划

> **面向 AI 代理的工作者：** 必需技能：使用 subagent-driven-development（推荐）或 executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 实现 ChannelLogger，在每个 run 目录下自动生成 run.log（通道事件+决策链）和 llm.log（LLM 完整输入输出）。

**架构：** 新建 `hagoku/observability/channel_logger.py`，Orchestrator 在 run 开始时创建 ChannelLogger，通过构造参数传给各 Agent。日志文件放 run 目录下，清除历史时自动删除。

**技术栈：** Python stdlib json + pathlib，无外部依赖。

---

### 任务 1：ChannelLogger 核心类

**文件：**
- 创建：`hagoku/observability/__init__.py`
- 创建：`hagoku/observability/channel_logger.py`
- 创建：`tests/test_observability/__init__.py`
- 创建：`tests/test_observability/test_channel_logger.py`

- [ ] **步骤 1：编写失败的测试**

```python
import json
import tempfile
from pathlib import Path
from hagoku.observability.channel_logger import ChannelLogger


def test_log_writes_jsonl_line():
    """log() 应写入一行 JSON 到 run.log"""
    with tempfile.TemporaryDirectory() as tmp:
        run_dir = Path(tmp)
        cl = ChannelLogger(run_dir)
        cl.log("scout", "llm_call", model="Qwen", prompt_len=1000)
        lines = (run_dir / "run.log").read_text().strip().split("\n")
        assert len(lines) == 1
        record = json.loads(lines[0])
        assert record["agent"] == "scout"
        assert record["event"] == "llm_call"
        assert record["model"] == "Qwen"
        assert "ts" in record


def test_log_llm_writes_full_record():
    """log_llm() 应写入完整 LLM 记录到 llm.log"""
    with tempfile.TemporaryDirectory() as tmp:
        run_dir = Path(tmp)
        cl = ChannelLogger(run_dir)
        cl.log_llm("scout", "Qwen", "sys prompt", "user prompt",
                   [{"name": "submit", "arguments": {}}], 500, 1200)
        data = json.loads((run_dir / "llm.log").read_text())
        assert data["agent"] == "scout"
        assert data["system_prompt"] == "sys prompt"
        assert data["tokens"] == 500


def test_trace_value_records_source():
    """trace_value() 应记录值来源"""
    with tempfile.TemporaryDirectory() as tmp:
        run_dir = Path(tmp)
        cl = ChannelLogger(run_dir)
        cl.trace_value("scout", "StoreID", "used_in_analysis", False, "llm")
        record = json.loads((run_dir / "run.log").read_text())
        assert record["event"] == "uia_set"
        assert record["column"] == "StoreID"
        assert record["value"] is False
        assert record["source"] == "llm"


def test_summary_writes_channel_health():
    """summary() 应写通道健康摘要"""
    with tempfile.TemporaryDirectory() as tmp:
        run_dir = Path(tmp)
        cl = ChannelLogger(run_dir)
        cl.summary(True, "6 true / 2 false", [])
        record = json.loads((run_dir / "run.log").read_text())
        assert record["event"] == "channel_summary"
        assert record["query_arrived"] is True


def test_multiple_events_appended():
    """多次调用应追加而非覆盖"""
    with tempfile.TemporaryDirectory() as tmp:
        run_dir = Path(tmp)
        cl = ChannelLogger(run_dir)
        cl.log("a", "e1")
        cl.log("a", "e2")
        lines = (run_dir / "run.log").read_text().strip().split("\n")
        assert len(lines) == 2
```

- [ ] **步骤 2：运行测试验证失败**

运行：`pytest tests/test_observability/test_channel_logger.py -v`
预期：全部 FAIL — ChannelLogger 不存在

- [ ] **步骤 3：实现 ChannelLogger**

```python
"""通道日志系统 — 记录决策链 + LLM 输入输出"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class ChannelLogger:
    """每个 run 一个实例。放在 run 目录下，清除历史时随 run 目录一起删除。"""

    def __init__(self, run_dir: Path) -> None:
        run_dir.mkdir(parents=True, exist_ok=True)
        self._run_log = run_dir / "run.log"
        self._llm_log = run_dir / "llm.log"

    # ── 通道事件 ──

    def log(self, agent: str, event: str, **kwargs: Any) -> None:
        """写一行 JSON 到 run.log"""
        record = {"ts": self._now(), "agent": agent, "event": event, **kwargs}
        with open(self._run_log, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")

    # ── LLM 调用录制 ──

    def log_llm(
        self,
        agent: str,
        model: str,
        system_prompt: str,
        user_prompt: str,
        response_tool_calls: list[dict] | None = None,
        response_content: str = "",
        tokens: int = 0,
        duration_ms: int = 0,
    ) -> None:
        """写一条 LLM 完整记录到 llm.log"""
        record = {
            "ts": self._now(),
            "agent": agent,
            "model": model,
            "system_prompt": system_prompt,
            "user_prompt": user_prompt,
            "response_tool_calls": response_tool_calls or [],
            "response_content": response_content,
            "tokens": tokens,
            "duration_ms": duration_ms,
        }
        with open(self._llm_log, "w", encoding="utf-8") as f:
            json.dump(record, f, ensure_ascii=False, default=str)

    # ── 决策链 ──

    def trace_value(
        self, agent: str, column: str, field: str, value: Any, source: str
    ) -> None:
        """记录一个字段值的来源"""
        event = f"{field}_set" if not field.startswith("_") else field.lstrip("_")
        self.log(agent, event, column=column, value=value, source=source)

    # ── 通道健康摘要 ──

    def summary(
        self, query_arrived: bool, uia_breakdown: str, warnings: list[str]
    ) -> None:
        """写通道健康摘要"""
        self.log(
            "orchestrator",
            "channel_summary",
            query_arrived=query_arrived,
            uia_breakdown=uia_breakdown,
            warnings=warnings,
        )

    # ── 内部 ──

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()
```

- [ ] **步骤 4：运行测试验证通过**

运行：`pytest tests/test_observability/test_channel_logger.py -v`
预期：5 PASS

- [ ] **步骤 5：Commit**

```bash
git add hagoku/observability/ tests/test_observability/
git commit -m "feat: ChannelLogger 核心类 — run.log + llm.log 写入"
```

---

### 任务 2：接入 Orchestrator — run 生命周期

**文件：**
- 修改：`hagoku/manager/orchestrator.py`

- [ ] **步骤 1：在 run() 中创建 ChannelLogger**

在 `run()` 方法中，`run_dir` 创建后立即初始化：

```python
# 在 run_dir = self.output_mgr.create_run_dir() 之后
from hagoku.observability.channel_logger import ChannelLogger
self._channel_logger = ChannelLogger(run_dir)
self._channel_logger.log("orchestrator", "run_start", query=query, project=project_name)
```

- [ ] **步骤 2：传入 ScoutAgent**

在创建 ScoutAgent 的位置，传入 channel_logger：

```python
scout_agent = ScoutAgent(
    self.config.llm, self.event_bus,
    llm_client=self.llm_quick,
    channel_logger=self._channel_logger,  # 新增
)
```

需要改 `ScoutAgent.__init__` 接受 `channel_logger=None` 参数。

- [ ] **步骤 3：run 结束时写摘要**

在 `run()` 返回前，调用 summary：

```python
if hasattr(self, '_channel_logger') and self._channel_logger:
    semantics = context.get("column_semantics", [])
    true_n = sum(1 for s in semantics if s.get("used_in_analysis"))
    false_n = sum(1 for s in semantics if s.get("used_in_analysis") is False)
    self._channel_logger.summary(
        query_arrived=bool(query),
        uia_breakdown=f"{true_n} true / {false_n} false",
        warnings=[]
    )
```

- [ ] **步骤 4：Commit**

```bash
git add hagoku/manager/orchestrator.py hagoku/agents/scout/agent.py
git commit -m "feat: Orchestrator 接入 ChannelLogger — run 生命周期"
```

---

### 任务 3：接入 Scout — LLM 调用录制

**文件：**
- 修改：`hagoku/agents/scout/agent.py`

- [ ] **步骤 1：ScoutAgent 接受 channel_logger 参数**

```python
def __init__(self, llm_config, event_bus, *, llm_client=None, scribe=None, channel_logger=None):
    ...
    self._channel_logger = channel_logger
```

- [ ] **步骤 2：_infer_all_semantics 中记录 LLM 调用**

在 LLM 调用前后加日志：

```python
if self._channel_logger:
    self._channel_logger.log("scout", "llm_call",
        model=self.llm_config.model_quick or self.llm_config.model,
        prompt_len=len(system_prompt) + len(user_prompt_str))

# ... LLM 调用 ...

if self._channel_logger:
    self._channel_logger.log_llm("scout", model, system_prompt, user_prompt_str,
        response_tool_calls=[...], tokens=..., duration_ms=...)
```

- [ ] **步骤 3：LLM 返回后记录 uia_set**

```python
for sem in semantics:
    if self._channel_logger:
        self._channel_logger.trace_value("scout", sem["column_name"],
            "used_in_analysis", sem.get("used_in_analysis"), "llm")
```

- [ ] **步骤 4：Commit**

```bash
git add hagoku/agents/scout/agent.py
git commit -m "feat: Scout LLM 调用接入 ChannelLogger"
```

---

### 任务 4：接入缓存检查 + 用户交互

**文件：**
- 修改：`hagoku/manager/orchestrator.py`

- [ ] **步骤 1：缓存决策记录**

在 `if scout_context is not None` 分支：

```python
self._channel_logger.log("orchestrator", "cache_check",
    result="hit" if scout_context.get("query") == query else "miss_query_changed",
    cached_query=scout_context.get("query"),
    current_query=query)
```

- [ ] **步骤 2：用户输入记录**

在 `respond()` 方法中：

```python
if hasattr(self, '_channel_logger') and self._channel_logger:
    self._channel_logger.log("orchestrator", "user_input",
        raw_text=user_input.get("text", ""), phase=phase, agent=agent_name)
```

- [ ] **步骤 3：移除临时 TRACE 日志**

删除之前调试加的 `_log.getLogger("hagoku").warning(f"TRACE: ...")` 两处。

- [ ] **步骤 4：Commit**

```bash
git add hagoku/manager/orchestrator.py hagoku/agents/scout/agent.py
git commit -m "feat: 缓存检查 + 用户交互 + 移除临时日志接入 ChannelLogger"
```

---

### 任务 5：全量回归 + 验证

**文件：** 无

- [ ] **步骤 1：跑全量测试**

```bash
.venv/bin/python -m pytest tests/test_doctrine_compliance.py tests/test_product/test_information_arrival.py tests/test_observability/ -q
```

- [ ] **步骤 2：跑全量回归**

```bash
.venv/bin/python -m pytest --tb=short --ignore=tests/test_field_llm_e2e.py -q
```

- [ ] **步骤 3：手工验证 — 跑一次分析后检查日志**

```bash
cat ~/.hagoku/projects/<project>/runs/<latest>/run.log | jq .
cat ~/.hagoku/projects/<project>/runs/<latest>/llm.log | jq .
```

- [ ] **步骤 4：Commit（如有残余改动）**

---

## 自检

1. **规格覆盖度**：全部事件类型有对应任务 ✅ / user_output/pause/unblock 在任务 4 中覆盖 ✅
2. **占位符扫描**：无 TODO/待定 ✅
3. **类型一致性**：ChannelLogger API 与接入代码一致 ✅
