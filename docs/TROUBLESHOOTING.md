# HaGoKu 排错录

记录每个经典 bug 的根因、修复方法和验证手段，防止 regression。

---

## 1. UI 按钮 Playwright 无法触发

**根因**：Streamlit 1.57+ 使用 React 合成事件系统，Playwright 的 DOM click 事件无法触发 Streamlit 内部的 widget 处理。

**现象**：按钮 DOM 显示被点击，但 `session_state` 不变化，页面不更新。

**修复**：UI 按钮测试必须手动在浏览器操作。自动化测试用 Python 直接调 orchestrator（见下方验证命令）。

**验证**：
```bash
cd /home/son_goku/hagoku
.venv/bin/python -c "
from hagoku.manager.orchestrator import Orchestrator
from hagoku.config import HaGoKuConfig
config = HaGoKuConfig.load()
orch = Orchestrator(config)
result = orch.run('data.csv', '分析问题', project_name='test', phase='scout_first')
print(result['status'])
"
```

**已确认**：
- `locator('text=互动分析').first.evaluate('(el) => el.click()')` → 侧边栏导航 **可以** 工作
- `page.click()` 和 `page.mouse.click()` → Streamlit 按钮 **不能** 工作

---

## 2. MiniMax 云端认证失败

**根因**：`.env` 文件没有被 `config.py` 正确加载。

**修复** (`hagoku/config.py`)：
```python
from dotenv import load_dotenv
_load_env_path = Path.home() / ".hagoku" / ".env"
if _load_env_path.exists():
    load_dotenv(_load_env_path)
```

**注意**：不要修改 `.env` 路径，不要删除这个逻辑。

**验证**：运行 `hagoku doctor` 检查 LLM 连接。

---

## 3. SQLite 线程安全问题

**根因**：worker 线程访问 SQLite 时报 `SQLite objects created in a thread can only be used in that same thread`。

**修复** (`hagoku/storage/database.py`)：
```python
self.conn = sqlite3.connect(str(db_path), timeout=30, check_same_thread=False)
self._lock = threading.RLock()

@contextmanager
def transaction(self):
    with self._lock:
        try:
            yield self.conn
            self.conn.commit()
        except Exception:
            self._conn.rollback()
            raise
```

`memory_backends.py` 的 `save`/`delete` 用 `with self._db.transaction()` 保护。

**验证**：`pytest tests/ -q` 应全部通过。

---

## 4. emit_event 签名错误

**根因**：多处调用 `emit_event(EventType, "AgentName", {...})` 传 3 个参数，但 `emit_event` 定义是 2 个参数 `(event_type, data)`，`self.role` 自动作为 agent。

**修复**：所有调用改为 `emit_event(EventType, {...})`。

**验证**：
```bash
grep -n "emit_event(" hagoku/agents/*.py
# 确保都是 emit_event(EventType, {data})，没有 3 参数形式
```

---

## 5. column_semantics 在 scout_done 中丢失

**根因**：
1. orchestrator 的 `scout_done` 返回缺失 `column_semantics` 字段
2. UI 的 `DataContext.from_dict()` 用硬编码的空列表

**修复**：
1. orchestrator 返回中加：`"column_semantics": [s.to_dict() for s in context.column_semantics]`
2. UI 所有位置改为：`scout_data.get("column_semantics", [])`

**验证**：
```bash
grep -n "column_semantics" hagoku/manager/orchestrator.py
grep -n "scout_data.get" hagoku/ui/_pages/app_analyze.py
```

---

## 6. 进度条显示全部完成（Scout 刚完就全 ✓）

**根因**：`_render_agent_pipeline` 只检查 `"complete" in etype`，不区分哪个 agent。

**修复**：按 `agent` 名字判断阶段：
```python
if agent_name == "Reporter":   current_stage = 3; pct = 100
elif agent_name == "Analyst":  current_stage = 2; pct = 75
elif agent_name == "Cleaner":  current_stage = 1; pct = 50
elif agent_name == "Scout":    current_stage = 0; pct = 25
```

**验证**：Web UI 手动测试流程，确认每个阶段完成后进度条只到对应位置。

---

## 7. DataContext.from_dict 缺少 data_path

**根因**：`from_dict` 传给 `cls(...)` 时没有包含 `data_path`。

**修复**：调用方必须包含 `"data_path": data_path`：
```python
scout_ctx = DataContext.from_dict({
    "data_path": data_path,  # 必须有
    "n_rows": result1.get("n_rows", 0),
    "column_semantics": result1.get("column_semantics", []),
})
```

**验证**：运行 3 阶段流程测试（见 [docs/DEVELOPMENT.md §测试方法](docs/DEVELOPMENT.md#测试方法)）。