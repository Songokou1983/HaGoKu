# HaGoKu Studio 排错录

记录每个经典 bug 的根因、修复方法和验证手段，防止 regression。

---

## 1. UI 自动化测试（Playwright）

### 当前 Web（React + Vite，`hagoku_web/`）

**侧栏导航**文案为「分析」「项目」等。可用例如：

```python
page.get_by_text("分析", exact=True).first.click()
# 或 page.locator("text=分析").first.click()
```

标准 `page.click()` 对多数 React 控件可用；若元素不可点，先 `wait_for_load_state`、检查是否被遮挡。**暂停与回复**依赖 WebSocket 与后端状态，完整流程建议辅以直接调用 `Orchestrator` 的集成测试：

```bash
cd /path/to/<repo-root>
.venv/bin/python -c "
from hagoku.manager.orchestrator import Orchestrator
from hagoku.config import HaGoKuConfig
config = HaGoKuConfig.load()
orch = Orchestrator(config)
result = orch.run('data.csv', '分析问题', project_name='test', phase='scout_first')
print(result['status'])
"
```

### 历史：旧版 Streamlit（`hagoku-ui`，已移除）

**根因**：Streamlit 1.57+ 使用 React 合成事件系统，Playwright 的 DOM click 无法触发部分 Streamlit widget。

**现象**：按钮 DOM 显示被点击，但 `session_state` 不变化，页面不更新。

**结论**：该限制仅针对已删除的 Streamlit 界面；当前仓库主线不再使用 Streamlit。

---

## 2. MiniMax 云端认证失败 / LLM 环境变量不生效

**根因**：密钥或 `base_url` 只写在**仓库根目录**的 `.env`，而 `config.py` **只加载** `~/.hagoku/.env`，因此 `load_dotenv` 从未读到你的配置。

**修复**：

```bash
mkdir -p ~/.hagoku
cp /path/to/hagoku/repo/.env.example ~/.hagoku/.env   # 或把原内容迁过去
# 编辑 ~/.hagoku/.env
```

`hagoku/config.py` 约定（勿随意改路径）：

```python
_load_env_path = Path.home() / ".hagoku" / ".env"
if _load_env_path.exists():
    load_dotenv(_load_env_path)
```

**注意**：不要改上述加载路径、不要删这段逻辑；仓库根目录 `.env` 已被 `.gitignore` 忽略且**不会**被加载。

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

---

## 8. 护栏拦截后 Web 仍像「成功完成」或报告页误判

**根因（历史）**：`RUN_COMPLETED` 未带 `run_id` 等字段、或 REST `runs`/`detail` 在仅有 `GUARDRAILS_BLOCKED.md` 时仍按「已完成 HTML」推断，会导致 CTA、报告预览或项目卡误导。

**修复方向（已合入主线，若复现请对照）**：
- 编排：`RUN_COMPLETED` 的 `data` 含 `guardrails_blocked`、`run_id`、`project`（见 `hagoku/manager/orchestrator.py`）。
- API：`GET .../runs` 与 `.../detail` 优先护栏元数据再判 HTML（见 `hagoku/api/server.py`）。
- 前端：分析/报告/事件/项目态与 `hagoku_web/src/utils/wsGuardrails.ts` 一致。

**验证（不依赖手动点完整 UI）**：
```bash
.venv/bin/python -m pytest tests/test_api/test_server.py tests/test_api/test_ws_handler.py -q
.venv/bin/python -m pytest tests/test_web/test_ws_guardrails_parity.py -q
```

**手动步骤**：见 [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md)「UI 手动测试步骤」第 5–7 步。

---

## 9. 知识库详情 `Internal Server Error`（`/api/kb/content`）

**常见根因**：运行 `hagoku-api` 的 Python 环境**未安装**依赖包 `markdown`（`pyproject.toml` 已声明 `markdown>=3.5`），首次点「查看正文」时 `import markdown` 失败。

**修复**：在**同一解释器**下执行 `pip install "markdown>=3.5"` 或从仓库根 `pip install -e .`，然后**重启** `hagoku-api`。确认使用虚拟环境：`.venv/bin/hagoku-api` 或先 `source .venv/bin/activate`。

**代码行为（主线）**：若仍缺包，接口会**降级**为转义后的纯文本 `<pre>`，不再返回 500；若仍见 500，请对照终端堆栈（其它异常如文件权限、注册表损坏等）。

---

## 10. `hagoku-api` 监听 8000 但整站「卡死」：HTTP / WebSocket 都不回

**高概率根因（已加固）**：`hagoku-api` 用**单进程 asyncio 事件循环**处理 HTTP 与 WebSocket。旧实现里 `WSBridge.broadcast` 对每个客户端**顺序** `await send_json(...)`；若某一连接发送缓冲区满、对端不读或链路僵死，`send` 会长时间阻塞，**整条事件循环被占住**，表现为**所有** `GET /`、`/api/*` 一起超时（不仅是 WS）。

**修复（主线）**：`broadcast` 改为 `asyncio.gather` + 每连接 `asyncio.wait_for(..., timeout=...)`（默认 5s，可用环境变量 `HAGOKU_WS_SEND_TIMEOUT` 覆盖）；超时的客户端会从桥接表移除。

**次要因素**：

- **`uvicorn --reload`**：`python -m hagoku.api.server` 曾默认开启 reload；文件监视 + 子进程在部分环境下会放大不稳定。现改为仅当 `HAGOKU_API_RELOAD` 为 `1`/`true`/`yes` 时启用；日常/生产建议**不**开 reload。
- **系统 HTTP 代理**：若 `http_proxy` 把 `localhost` 指到本地代理而代理未正确处理，浏览器或 `curl` 也会像「8000 死了」；可对 `127.0.0.1,localhost` 设 **NO_PROXY** 或代理直连规则。

**验证**：`python -m pytest tests/test_api/test_ws_handler.py -q`。

---

## 11. Web 工作台整页空白 / 黑屏（`hagoku_web`）

**常见现象**：侧栏不出现；整页白或整页深色无内容。

**常见根因**：

1. **主 JS 或 CSS 未加载成功**（404、反向代理未转发 `/assets/*`、子路径部署未配 `base`、强缓存了旧 `index.html` 却指向已删的 chunk 名）。
2. **未捕获的运行时错误**：打开开发者工具 **Console** 看红色栈；若 `index.css` 未加载，仅靠 Tailwind 的错误页可能看不清。
3. **连接状态误显示为「连接中」**：主线用 **`idle`** 表示「尚未发起 WS」，避免误铺「正在连接」全屏遮罩。

**已做工程缓解（主线）**：`index.html` 内联与主题一致的 **`#121826` 底 + 字色**；`initWebSocket` 在 `createRoot` 前 **`try/catch`**；`ErrorBoundary` 错误页保留**内联样式**（CSS chunk 丢失时仍可见）；`connectionStatus` 初始为 **`idle`**。

**自助排查**：硬刷新（Ctrl+Shift+R）、无痕窗口、看 **Network** 里 `index-*.js` / `index-*.css` 是否 200；生产环境若页面不在域名根路径，需在 Vite 配置 **`base`** 并在网关做对应路由。**勿**用 `file://` 直接打开 `dist/index.html`（模块脚本会被浏览器拦截）。

**`vite preview`（本地验收构建产物时）**：历史上若不配置 **`preview.proxy`**，`/api/*` 会打到预览服务器本身，易导致项目列表 **`fetch` 挂起**、界面一直「加载中…」。主线已在 `vite.config.ts` 为 **`preview`** 配置与开发环境一致的 **`/api`、`/ws`** 转发到 `localhost:8000`；与 **`npm run dev`** 一样，仍需要本机有可用的 **`hagoku-api`**（或等价后端）在 8000 提供接口。
