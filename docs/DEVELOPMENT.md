# HaGoKu 设计手册

> **快速上手** → [DEV.md](../DEV.md)
> **排错录** → [docs/TROUBLESHOOTING.md](TROUBLESHOOTING.md)
> **项目规范** → [PROJECT.md](../PROJECT.md)

---

## ⚠️ 最重要的经验教训

### 不要让我重复同一件事

用户最核心的抱怨是：同一个问题被重复提出，每次都要重新解释。

**规则：**
1. 用户说的问题 → 立即记录到文档 + 对应代码注释
2. 修完 bug → 写测试防止 regression
3. 每次对话开始 → 先读项目文档，不懂就问，不要猜
4. 不要 commit 后又忘记做了什么 → commit message 要写清楚

### 不要重新发明轮子

已有配置/服务 → 直接用，不要新建。

- **Hermes**：运行着本地 35B 模型，`~/.llama-proxy/` 配置（**不要动**）
- PM2 管理服务 → 不要 stop/restart 不认识的服务
- 如果需要调用已有 LLM → 找它的配置，不要自己新建

---

## 用户核心需求（必须时刻记住）

### 差异化定位
- **不是聊天工具**：不是把数据丢给 LLM 问答
- **不是 1 个 LLM**：4 个 Agent（Scout/Cleaner/Analyst/Reporter）+ Scribe 后台仲裁
- **限制互动内容**：禁止 Agent 聊无关问题

### 4-Agent 互动流程（Scribe 在后台自动协同）
1. Scout 跑 → 停下来 → 显示字段确认卡片
2. 用户确认 → Cleaner 跑 → 停下来 → 显示清洗策略卡片
3. 用户确认 → Analyst 跑 → 停下来 → 显示初步发现卡片
4. 用户确认 → 完整 pipeline → 出报告

**每个阶段都会停，不是点一下就跑到底。**

### 用户体验原则
- 进度条是真实的，不是 4 个格子轮流高亮的 checklist
- Agent 主动引导用户，不是等用户输入
- 4 个 Agent 要让用户感知到在做什么
- 不要让用户用专业方式理解和回答

---

## 测试方法

### Python 后端测试（主要依赖这个）
```bash
cd /home/son_goku/hagoku

# 3 阶段流程测试
.venv/bin/python -c "
import sys, time
sys.path.insert(0, '.')
from pathlib import Path
from hagoku.config import HaGoKuConfig
from hagoku.manager.orchestrator import Orchestrator
from hagoku.agents.scout import DataContext

config = HaGoKuConfig.load()
data_path = str(Path.home() / '.hagoku/projects/Playwright测试/input/ad_campaign_1.csv')

# Phase 1
orch1 = Orchestrator(config)
r1 = orch1.run(data_path, '', project_name='Playwright测试', phase='scout_first')
print(f'Phase1: {r1[\"status\"]}, cols={len(r1.get(\"column_semantics\",[]))}')
assert r1['status'] == 'scout_done'

# Phase 2
scout_ctx = DataContext.from_dict({
    'data_path': data_path,
    'n_rows': r1.get('n_rows', 0), 'n_cols': r1.get('n_cols', 0),
    'column_semantics': r1.get('column_semantics', []),
    'column_descriptions': r1.get('column_descriptions', {}),
})
time.sleep(1)
orch2 = Orchestrator(config)
r2 = orch2.run(data_path, '分析哪个渠道ROI最高',
    project_name='Playwright测试',
    phase='cleaning_first', scout_context=scout_ctx)
print(f'Phase2: {r2.get(\"status\")}')
assert r2.get('status') == 'cleaner_strategy'

# Phase 3
time.sleep(1)
orch3 = Orchestrator(config)
r3 = orch3.run(data_path, '分析哪个渠道ROI最高',
    project_name='Playwright测试',
    phase='analyst_first', scout_context=scout_ctx,
    cleaning_operations=r2.get('operations'))
print(f'Phase3: {r3.get(\"status\")}')
assert r3.get('status') == 'analyst_preliminary'

print('ALL 3 PHASES OK')
"

# pytest
.venv/bin/python -m pytest tests/ -q
```

### UI 手动测试步骤
1. 浏览器打开 http://localhost:5173
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
.venv/bin/python -c "
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    browser = p.chromium.launch(headless=False, args=['--no-sandbox'])
    page = browser.new_page()
    page.goto('http://localhost:5173', timeout=60000)
    page.wait_for_load_state('domcontentloaded')
    # 注意：按钮点击无法正确触发，只能测试导航和页面结构
    page.locator('text=互动分析').first.evaluate('(el) => el.click()')
"
```

> **已知限制**：Streamlit 按钮无法用 Playwright 触发，详见 [TROUBLESHOOTING.md §1](TROUBLESHOOTING.md#1-ui-按钮-playwright-无法触发)。

---

## 代码审查清单（每次提交前）

1. `emit_event` 调用是否有遗漏的 3 参数形式？
   ```bash
   grep -n "emit_event(" hagoku/agents/*.py
   # 确保都是 emit_event(EventType, {data})
   ```

2. `column_semantics` 是否正确传递？
   ```bash
   grep -n "column_semantics" hagoku/manager/orchestrator.py
   grep -n "scout_data.get" hagoku/agent/scout.py
   ```

3. SQLite 线程安全是否完整？
   - `memory_backends.py` 的 `save`/`delete` 用 `transaction()`
   - `database.py` 有 `check_same_thread=False` 和 `_lock`

4. pytest 是否通过？
   ```bash
   .venv/bin/python -m pytest tests/ -q
   ```

5. orchestrator 3 个阶段是否都返回正确 status？
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
- ❌ 不要在 UI 代码里用相对导入（用 `from hagoku.xxx`）
- ❌ 不要在 Playwright 里尝试完美模拟 Streamlit 按钮点击（不可能）
- ❌ 不要在 commit message 里写 "various fixes" 或 "update"

---

## 项目级看板（Kanban）

### 设计背景

参考 Hermes Agent Kanban 架构，为 HaGoKu 设计项目内部看板。

**核心目标**：可视化数据分析流程的每个阶段，外部与用户沟通，内部传递任务信息接力。

### 架构设计

**文件布局（每个项目独立）**：
```
~/.hagoku/projects/<project>/
  kanban.db        ← SQLite 看板数据库
  context.md       ← 接力棒（各 Agent 交接数据）
  progress.yaml    ← 项目记忆（字段决策、用户偏好、分析历史）
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
| SQLite 操作 | `hagoku/storage/kanban.py` |
| Scribe Agent | `hagoku/agents/_scribe/agent.py` |
| context.md | 项目根目录 |
| kanban.db | 项目根目录 |

### 禁止事项

- ❌ kanban.db 不放在全局目录，必须在项目文件夹内
- ❌ 不做通用看板（不做多项目全局视图，不做用户管理）
- ❌ Scribe 不直接与用户对话，只在后台记录
- ❌ 不要忽略 `claim_task()` 的返回值

---

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
hagoku/agents/<agent>/
  knowledge.yaml   ← 人可读知识条目（YAML）
  knowledge.db     ← sqlite_vec 向量数据库
  knowledge.py     ← recall/learn 封装函数
```

### KnowledgeVectorStore API

```python
from hagoku.storage.knowledge_vector import KnowledgeVectorStore

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

### 已知限制

- `use_count` 只保存在 YAML，不保存在 DB（YAML 是 truth source，DB 是向量索引）
- 如果 OpenAI API 不可用，`recall()` 返回空列表，系统降级运行（不影响核心分析功能）

---

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