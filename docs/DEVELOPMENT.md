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

### 分析流程与人机互动（与 Web UI 对齐）

- **不是聊天机器人**：用户不是在空框里随便问；主路径是 **Orchestrator 锁定的流水线**（Scout → Cleaner → Analyst → Reporter）。
- **规定暂停点**：在关键阶段结束后编排会 **暂停**，经 WebSocket 下发 **`USER_INPUT_REQUESTED`**（或等价事件）；前端优先渲染 **结构化工作流卡片**（`field_review` / `cleaning_review` / `analyst_review`），**不**用固定长模板冒充对话；若事件仍带短 `message`，可为 LLM 依当次结果生成（非必填）。
- **用户回复**：用户在分析页用 **自然语言** 回复；前端发送 **`respond`**，后端 **`unblock`** 继续执行。不要用「固定表单卡片」理解当前 Web 产品（CLI 分阶段测试仍可独立存在）。
- **体验原则**：Agent **主动引导**；进度展示应对应真实阶段（流水线状态 + 日志/事件），而非装饰性假状态。
- **目标态（多轮对齐）**：阶段内以「对齐」为结束条件，**不**预设用户只能回复固定次数；**Scout 字段表**已在编排层实现多轮 `user_input_requested` + `interaction_revision`（见 `hagoku/manager/orchestrator.py`）。**跨阶段闸门、Cleaner/Analyst 同构**仍见 [INTERACTION_MULTITURN_PLAN.md](INTERACTION_MULTITURN_PLAN.md) §2.2 / §4-B/C。实施计划与路线图勾选见 [DEVELOPMENT_PROMPT.md](../DEVELOPMENT_PROMPT.md) **阶段 2.8**；可执行契约见 [AGENT_INTERACTION_CONTRACT.md](AGENT_INTERACTION_CONTRACT.md) **C4**。

### 用户体验原则
- 进度条是真实的，不是 4 个格子轮流高亮的 checklist
- Agent 主动引导用户，不是等用户输入
- 4 个 Agent 要让用户感知到在做什么
- 不要让用户用专业方式理解和回答

---

## 测试方法

### Python 后端测试（主要依赖这个）
```bash
# 在仓库根目录（含 pyproject.toml）执行，已激活 .venv
cd /path/to/<repo-root>

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

# 护栏 / API / WebSocket（改 orchestrator、ws_handler、server 或 wsGuardrails 时建议跑）
.venv/bin/python -m pytest tests/test_api/ -q
.venv/bin/python -m pytest tests/test_web/test_ws_guardrails_parity.py -q

# Agent 互动与暂停路径（产品契约；改 orchestrator / AnalyzePanel 暂停与用户输入时必跑）
.venv/bin/python -m pytest tests/test_product/test_agent_interaction_contract.py -q
```

> 契约全文：[AGENT_INTERACTION_CONTRACT.md](AGENT_INTERACTION_CONTRACT.md)（与 [PROJECT.md](../PROJECT.md)「互动与成长：原则优先级与验收」一致）。

### UI 手动测试步骤
1. 浏览器打开 http://localhost:5173
2. **项目** 页选择或创建项目，确认描述与数据文件
3. **分析** 页：选择项目与数据 → **开始分析**（必要时先输入/补充研究问题）
4. 观察 **流水线进度** 与 **对话区**：在暂停点应出现 Agent 引导语，用自然语言 **回复** 后继续
5. **报告** 页：切换项目，**按 run** 查看。**正常完成**：打开 HTML（默认双轨：要点速览 + 完整证据）。**强制级护栏未通过**：应看到说明（或链到 `GUARDRAILS_BLOCKED.md` 全文），**不**把「双轨 HTML 成功预览」当成该次的默认交付态。
6. **事件** 页（可选）：查看 WebSocket 事件流；若存在护栏拦截，`run_completed` 等在列表/标签上应与「成功完成」区分（含 `run_id` 以便对照报告与 API）。
7. **护栏拦截整条路径**（有可调触发数据时）：分析页终态、项目卡状态、`GET .../runs` 与 `.../detail` 的 `guardrails_blocked` 应与实际是否产出正式 HTML 一致。契约与清单见 [DEVELOPMENT_PROMPT.md](../DEVELOPMENT_PROMPT.md)「护栏 × 沟通」。

> 下列「Scout 字段确认卡片」等描述适用于 **早期 PROTOTYPE / CLI 分阶段**，**当前 Web 主线以对话式暂停为准**。详见 [PROJECT.md](../PROJECT.md)「人机互动理念」。

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
    page.get_by_text("分析", exact=True).first.click()
"
```

> **说明**：旧版 Streamlit 的 Playwright 限制见 [TROUBLESHOOTING.md §1](TROUBLESHOOTING.md#1-ui-自动化测试playwright)；当前 React 侧栏通常为可点击，完整分析流可结合后端集成测试。

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
   grep -n "column_semantics" hagoku/agents/scout/agent.py
   ```

3. SQLite 线程安全是否完整？
   - `memory_backends.py` 的 `save`/`delete` 用 `transaction()`
   - `database.py` 有 `check_same_thread=False` 和 `_lock`

4. pytest 是否通过？
   ```bash
   .venv/bin/python -m pytest tests/ -q
   ```

5. 若改动 `hagoku_web/src/utils/wsGuardrails.ts`：是否已同步 `tests/test_web/test_ws_guardrails_parity.py` 并通过？
   ```bash
   .venv/bin/python -m pytest tests/test_web/test_ws_guardrails_parity.py -q
   ```

6. orchestrator 3 个阶段是否都返回正确 status？
   - `scout_first` → `scout_done`
   - `cleaning_first` → `cleaner_strategy`
   - `analyst_first` → `analyst_preliminary`

7. 本地 `UI_CHANGELOG_backup_*` 快照是否误加入暂存区？（应被 `.gitignore`；清理命令见 [DEV.md](../DEV.md)「本地 UI 快照」。）

---

## 不要做的清单

- ❌ 不要修改 `~/.llama-proxy/` 下的任何文件
- ❌ 不要用 `pm2 restart` 或 `pm2 stop` 操作 llama-proxy
- ❌ 不要自己新建 llama.cpp 模型服务
- ❌ 不要改 `config.py` 里 **`~/.hagoku/.env`** 的加载逻辑（本地密钥只放该文件；勿指望仓库根目录 `.env`）
- ❌ 不要在 UI 代码里用 `time.sleep` 阻塞
- ❌ 不要在 UI 代码里用相对导入（用 `from hagoku.xxx`）
- ❌ 不要用已删除的 Streamlit 前提推断当前 React UI 的行为（排错以 React 为准）
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