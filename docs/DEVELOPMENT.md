# HaGoKu 开发指南

## ⚠️ 最重要的经验教训

### 不要让我重复同一件事

用户最核心的抱怨是：同一个问题被重复提出，每次都要重新解释。

**规则：**
1. 用户说的问题 → 立即记录到本文件 + 对应代码注释
2. 修完 bug → 写测试防止 regression
3. 每次对话开始 → 先读本文件，不懂就问，不要猜
4. 不要在 commit 后又忘记做了什么 → commit message 要写清楚

### 不要重新发明轮子

用户已经配好了本地 35B 模型给 Hermes 使用。不要去新建或修改：
- `~/.llama-proxy/` 下的任何配置
- PM2 llama-proxy 服务
- 任何 llama.cpp 模型配置

如果需要调用本地 LLM → 找 Hermes 的配置路径，不要自己新建。

---

## 用户核心需求（必须时刻记住）

### 差异化定位
- **不是聊天工具**：不是把数据丢给 LLM 问答
- **不是 1 个 LLM**：4 个 agent 各司其职
- **限制互动内容**：禁止 Agent 聊无关问题

### 4-Agent 互动流程（用户明确要求）
1. Scout 跑 → 停下来 → 显示字段确认卡片
2. 用户确认 → Cleaner 跑 → 停下来 → 显示清洗策略卡片
3. 用户确认 → Analyst 跑 → 停下来 → 显示初步发现卡片
4. 用户确认 → 完整 pipeline → 出报告

**每个阶段都会停，不是点一下就跑到底。**

### 用户体验原则
- 进度条是真实的，不是4个格子轮流高亮的 checklist
- Agent 主动引导用户，不是等用户输入
- 4个 Agent 要让用户感知到在做什么
- 不要让用户用专业方式理解和回答

---

## 已知问题及解决方案（不要重蹈覆辙）

### UI 按钮 Playwright 无法触发
**问题**：`page.click('text=启动分析')` 无法触发 Streamlit 按钮点击。Streamlit 1.57+ 用 React 合成事件系统，Playwright 的 DOM click 事件无法触发 Streamlit 内部的 widget 处理。

**现象**：按钮 DOM 显示被点击，但 Streamlit session_state 不变化，页面不更新。

**解决方案**：
1. 手动测试（浏览器打开 http://localhost:8501）
2. 如果需要自动化测试 → 用 JS 注入 `el.evaluate('(el) => el.click()')` 点击侧边栏导航可以工作，但按钮不行
3. 后端逻辑测试用 Python 直接调 orchestrator：
```bash
cd /home/son_goku/hagokyu
/home/son_goku/hagokyu/.venv/bin/python -c "
from hagokyu.manager.orchestrator import Orchestrator
from hagokyu.config import HaGoKuConfig
config = HaGoKuConfig.load()
orch = Orchestrator(config)
result = orch.run(data_path, query, project_name, phase='scout_first')
print(result['status'])
"
```

### Streamlit 按钮正确触发方式（经验）
- `locator('text=互动分析').first.evaluate('(el) => el.click()')` 可以工作（侧边栏导航）
- 普通 `page.click()` 对 Streamlit 按钮无效
- `page.mouse.click(x, y)` 也不能正确触发 Streamlit 的 WebSocket widget 消息

### MiniMax 云端认证失败
**问题**：API 认证失败 `login fail`。

**原因**：`.env` 文件没有在 config.py 加载时正确读取。

**修复**（config.py）：
```python
from dotenv import load_dotenv
_load_env_path = Path.home() / ".hagokyu" / ".env"
if _load_env_path.exists():
    load_dotenv(_load_env_path)
```

**注意**：不要修改 `.env` 路径，也不要把这个逻辑删掉。

### SQLite 线程安全问题
**问题**：worker 线程访问 SQLite 时报错 `SQLite objects created in a thread can only be used in that same thread`。

**修复**（database.py）：
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

memory_backends.py 的 save/delete 用 `with self._db.transaction()` 保护。

### emit_event 签名错误
**问题**：`emit_event(EventType, "AgentName", {...})` 3个参数报错。

**原因**：`emit_event` 定义是 `emit_event(event_type, data)`，2个参数。

**修复**：所有调用改为 `emit_event(EventType, {...})`，`self.role` 自动作为 agent。

**检查**：`grep "emit_event(" hagokyu/agents/*.py` 确保没有遗漏。

### column_semantics 在 scout_done 中丢失
**问题**：Scout 完成但 UI 显示 0 个字段。

**原因**：
1. orchestrator scout_done 返回缺 `column_semantics` 字段
2. UI 的 `DataContext.from_dict()` 用硬编码的空列表

**修复**：
1. orchestrator 返回：`"column_semantics": [s.to_dict() for s in context.column_semantics]`
2. UI 4处全部：`scout_data.get("column_semantics", [])`

### 进度条显示全部完成
**问题**：Scout 完成后，4个阶段全部显示 ✓。

**原因**：`_render_agent_pipeline` 只检查 `"complete" in etype`，不区分是哪个 agent。

**修复**：按 `agent` 名字判断阶段：
```python
if agent_name == "Reporter": current_stage = 3; pct = 100
elif agent_name == "Analyst": current_stage = 2; pct = 75
elif agent_name == "Cleaner": current_stage = 1; pct = 50
elif agent_name == "Scout": current_stage = 0; pct = 25
```

### DataContext.from_dict 缺少 data_path
**问题**：`DataContext.from_dict({...})` 报错 `missing 1 required positional argument: 'data_path'`。

**原因**：`from_dict` 传给 `cls(...)` 时没有包含 `data_path`。

**修复**：调用方必须包含 `"data_path": data_path`：
```python
scout_ctx = DataContext.from_dict({
    "data_path": data_path,  # 必须有
    "n_rows": result1.get("n_rows", 0),
    "column_semantics": result1.get("column_semantics", []),
    ...
})
```

---

## 测试方法

### Python 后端测试（主要依赖这个）
```bash
cd /home/son_goku/hagokyu

# 3阶段流程测试
/home/son_goku/hagokyu/.venv/bin/python -c "
import sys, time
sys.path.insert(0, '.')
from pathlib import Path
from hagokyu.config import HaGoKuConfig
from hagokyu.manager.orchestrator import Orchestrator
from hagokyu.agents.scout import DataContext

config = HaGoKuConfig.load()
data_path = str(Path.home() / '.hagokyu/projects/Playwright测试/input/ad_campaign_1.csv')

# Phase 1
orch1 = Orchestrator(config)
r1 = orch1.run(data_path, '', project_name='Playwright测试', user_mode='standard', phase='scout_first')
print(f'Phase1: {r1[\"status\"]}, cols={len(r1.get(\"column_semantics\",[]))}')
assert r1['status'] == 'scout_done'

# Phase 2
scout_ctx = DataContext.from_dict({
    'data_path': data_path,
    'n_rows': r1.get('n_rows', 0),
    'n_cols': r1.get('n_cols', 0),
    'column_semantics': r1.get('column_semantics', []),
    'column_descriptions': r1.get('column_descriptions', {}),
})
time.sleep(1)
orch2 = Orchestrator(config)
r2 = orch2.run(data_path, '分析哪个渠道ROI最高',
    project_name='Playwright测试', user_mode='standard',
    phase='cleaning_first', scout_context=scout_ctx)
print(f'Phase2: {r2.get(\"status\")}')
assert r2.get('status') == 'cleaner_strategy'

# Phase 3
time.sleep(1)
orch3 = Orchestrator(config)
r3 = orch3.run(data_path, '分析哪个渠道ROI最高',
    project_name='Playwright测试', user_mode='standard',
    phase='analyst_first', scout_context=scout_ctx,
    cleaning_operations=r2.get('operations'))
print(f'Phase3: {r3.get(\"status\")}')
assert r3.get('status') == 'analyst_preliminary'

print('ALL 3 PHASES OK')
"

# pytest
/home/son_goku/hagokyu/.venv/bin/python -m pytest tests/ -q
```

### UI 手动测试步骤
1. 浏览器打开 http://localhost:8501
2. 侧边栏 → 互动分析
3. 项目选 "Playwright测试"，数据选 "ad_campaign_1.csv"
4. 点击 🚀 启动分析
5. 观察 Scout 字段确认卡片是否出现
6. 确认后输入 "分析哪个渠道ROI最高"
7. 观察 Cleaner 策略卡片
8. 确认后观察 Analyst 初步发现
9. 确认后观察完整 pipeline 运行

### Playwright UI 自动化（受限）
```bash
/home/son_goku/camoufox_env/bin/python3 -c "
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    browser = p.chromium.launch(headless=False, args=['--no-sandbox'])
    page = browser.new_page()
    page.goto('http://localhost:8501', timeout=60000)
    page.wait_for_load_state('domcontentloaded')
    # 注意：按钮点击无法正确触发，只能测试导航和页面结构
    page.locator('text=互动分析').first.evaluate('(el) => el.click()')
    # ...
"
```

---

## 代码审查清单（每次提交前）

1. `emit_event` 调用是否有遗漏的3参数形式？
   ```bash
   grep -n "emit_event(" hagokyu/agents/*.py
   # 确保都是 emit_event(EventType, {data})
   ```

2. `column_semantics` 是否正确传递？
   ```bash
   grep -n "column_semantics" hagokyu/manager/orchestrator.py
   grep -n "scout_data.get" hagokyu/ui/_pages/app_analyze.py
   ```

3. SQLite 线程安全是否完整？
   - `memory_backends.py` 的 `save/delete` 用 `transaction()`
   - `database.py` 有 `check_same_thread=False` 和 `_lock`

4. pytest 是否通过？
   ```bash
   /home/son_goku/hagokyu/.venv/bin/python -m pytest tests/ -q
   ```

5. orchestrator 3个阶段是否都返回正确 status？
   - `scout_first` → `scout_done`
   - `cleaning_first` → `cleaner_strategy`
   - `analyst_first` → `analyst_preliminary`

---

## 不要做的清单

- ❌ 不要修改 `~/.llama-proxy/` 下的任何文件
- ❌ 不要用 `pm2 restart` 或 `pm2 stop` 操作 llama-proxy
- ❌ 不要自己新建 llama.cpp 模型服务
- ❌ 不要把 `.env` 路径改成其他位置
- ❌ 不要在 UI 代码里用 `time.sleep` 阻塞
- ❌ 不要在 UI 代码里用相对导入（用 `from hagokyu.xxx`）
- ❌ 不要在 Playwright 里尝试完美模拟 Streamlit 按钮点击（不可能）
- ❌ 不要在 commit message 里写"various fixes"或"update"

---

## 项目级看板（Kanban）

### 设计背景

参考 Hermes Agent Kanban 架构（kingkillery/pk-kanban + Shin-R2un/hermes-kanban-mcp），为 HaGoKu 设计项目内部看板。

**核心目标**：可视化数据分析流程的每个阶段，外部与用户沟通，内部传递任务信息接力。

### 架构设计

**文件布局（每个项目独立）**：
```
~/.hagokyu/projects/<project>/
  kanban.db        ← SQLite 看板数据库
  context.md       ← 接力棒（各 Agent 交接数据）
  schema.yaml      ← 字段定义记忆
  memory/          ← 各 Agent 私有记忆
```

**看板状态机**：
```
triage → todo → ready → running → blocked → ready → done
                                    ↓
                                 archived
```

**HaGoKu 适配**：
| 看板状态 | HaGoKu 含义 |
|----------|-------------|
| `triage` | 新建任务，Scout 待启动 |
| `todo` | Scout 正在理解字段 |
| `ready` | Scout 等待用户确认字段 / Cleaner 等待确认清洗策略 / Analyst 等待确认分析方向 |
| `running` | Agent 正在执行 |
| `blocked` | 等待用户输入（字段/策略/方向） |
| `done` | 阶段完成，可交接下一 Agent |

### SQLite Schema

```sql
CREATE TABLE kanban_tasks (
    id              TEXT PRIMARY KEY,
    agent           TEXT NOT NULL,           -- scout/cleaner/analyst/reporter
    title           TEXT NOT NULL,
    description     TEXT,
    status          TEXT DEFAULT 'triage',  -- triage/todo/ready/running/blocked/done/archived
    priority        INTEGER DEFAULT 0,
    parent_id       TEXT,                  -- 父任务（Scout 任务 → Cleaner 任务）
    workspace_path  TEXT,
    created_at      TEXT,
    updated_at      TEXT,
    completed_at    TEXT,
    claim_lock      TEXT,                 -- 防止重复执行的锁
    claim_expires   INTEGER,
    FOREIGN KEY (parent_id) REFERENCES kanban_tasks(id)
);

CREATE TABLE task_events (
    id          TEXT PRIMARY KEY,
    task_id     TEXT NOT NULL,
    event_type  TEXT NOT NULL,   -- created/claimed/completed/blocked/unblocked/comment
    actor       TEXT,            -- system/user/agent_name
    body        TEXT,
    created_at  TEXT,
    FOREIGN KEY (task_id) REFERENCES kanban_tasks(id)
);

CREATE TABLE task_comments (
    id          TEXT PRIMARY KEY,
    task_id     TEXT NOT NULL,
    author      TEXT NOT NULL,   -- user/agent_name
    body        TEXT,
    created_at  TEXT,
    FOREIGN KEY (task_id) REFERENCES kanban_tasks(id)
);
```

### 关键机制

**1. 父子任务依赖（Scout → Cleaner → Analyst → Reporter）**
- Scout 任务完成后，其子任务 Cleaner 任务自动晋升 `ready`
- `recompute_ready()`：当父任务达到 `done` 状态，子任务从 triage/todo 直接晋升到 ready
- **重要**：`init_pipeline()` 必须被调用来建立 parent_id 关系

**2. Claim 锁机制**
- `ready → running` 是原子操作，防止多 Agent 抢同一任务
- 锁 15 分钟过期，长任务需定期 heartbeat 续期
- **注意**：`claim_task()` 返回值必须检查，失败时不要继续处理

**3. Scribe Agent 钩子**
- 监听 EventBus 所有事件
- Agent STARTED → 更新任务状态
- Agent COMPLETED → 触发子任务晋升 + 通知下一 Agent
- USER_INPUT_REQUESTED → 任务进入 `blocked`

**4. 交接记录（context.md）**
- 每个 Agent 完成后，将产出写入 `context.md`
- `context.md` 是接力棒，不是状态机

### Scribe Agent 看板操作接口

```python
class ScribeAgent:
    def init_pipeline() -> str: ...  # 创建任务链，返回 scout_id，必须调用！
    def claim_task(agent) -> str | None: ...  # 返回 task_id 或 None
    def complete_task(agent, result) -> bool: ...
    def block_task(agent, reason) -> bool: ...
    def unblock_task(agent) -> bool: ...
    def heartbeat(agent) -> bool: ...
    def add_comment(agent, author, body) -> str | None: ...
    def get_task_status(agent) -> dict | None: ...
    def get_pipeline_status() -> dict[str, str]: ...
```

### init_pipeline() 使用方法

```python
# 在 Orchestrator 或 Manager 启动 pipeline 时调用
scribe = ScribeAgent(llm_config, event_bus, project_path)
scout_id = scribe.init_pipeline()  # 创建 Scout→Cleaner→Analyst→Reporter 任务链
# scout_id 可用于后续状态查询
```

### 文件对应关系

| 功能 | 文件 |
|------|------|
| SQLite 操作 | `hagokyu/storage/kanban.py` |
| Scribe Agent | `hagokyu/agents/_scribe/agent.py` |
| context.md | 项目根目录 |
| kanban.db | 项目根目录 |

### 禁止事项

- ❌ kanban.db 不放在全局目录，必须在项目文件夹内
- ❌ 不做通用看板（不做多项目全局视图，不做用户管理）
- ❌ Scribe 不直接与用户对话，只在后台记录
- ❌ 不要忽略 `claim_task()` 的返回值

## Agent 知识向量系统

### 技术栈

- **向量存储**：sqlite_vec（SQLite 扩展）+ OpenAI 兼容 embedding API
- **配置环境变量**：
  - `HAGOKYU_EMBEDDING_BASE_URL`：embedding API 地址（默认 `https://api.openai-proxy.org/v1`）
  - `HAGOKYU_EMBEDDING_API_KEY`：API 密钥
  - `HAGOKYU_EMBEDDING_MODEL`：模型名（默认 `text-embedding-3-small`）
- **维度**：1536（text-embedding-3-small）

### 文件布局

```
hagokyu/agents/<agent>/
  knowledge.yaml   ← 人可读知识条目（YAML）
  knowledge.db     ← sqlite_vec 向量数据库
  knowledge.py    ← recall/learn 封装函数
```

### KnowledgeVectorStore API

```python
from hagokyu.storage.knowledge_vector import KnowledgeVectorStore

store = KnowledgeVectorStore("path/to/knowledge.yaml", dimension=1536)

# 检索
results = store.recall(query="渠道 ROI 分析", tags=["regression"], top_k=3)
# [{id, content, tags, metadata, similarity, use_count}, ...]

# 添加
entry_id = store.add(
    content="场景：渠道分析；方法：回归",
    tags=["roi", "regression"],
    metadata={"method": "ols", "confidence": 0.8}
)

# 更新或插入
store.upsert(entry_id, content="...", tags=[...], metadata={...})

# 列出所有
all_entries = store.list_all()

# 删除
store.delete(entry_id)
```

### recall() 工作流程

1. `_sync_vectors()`：YAML 有条目但 DB 无向量时，自动补全
2. 对 query 做 embedding（调用 OpenAI API）
3. 从 DB 读取所有已有向量，计算余弦相似度
4. 按相似度排序，返回 top_k
5. `use_count++` 并写回 YAML

### learn() 时机

| Agent | 何时 learn | 何时 recall |
|-------|-----------|-------------|
| Scout | 高置信度(≥0.85)字段推断完成 | 生成字段描述时（top_k=3） |
| Analyst | 分析完成且结果显著 | 选择分析方法时（top_k=2） |
| Cleaner | 无知识集成 | 无 |

### 已知问题

- `use_count` 只保存在 YAML，不保存在 DB（YAML 是 truth source，DB 是向量索引）
- 如果 OpenAI API 不可用，`recall()` 返回空列表，系统降级运行（不影响核心分析功能）

## 提交规范

```bash
git add <files>
git commit -m "$(cat <<'EOF'
fix: <具体描述>

<改动1>
<改动2>

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

每次提交只做一件事，不要把不相关的改动混在一起。
