# HaGoKu Studio 设计手册

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

> 契约全文：[AGENT_INTERACTION_CONTRACT.md](AGENT_INTERACTION_CONTRACT.md)（与 [PROJECT.md](../PROJECT.md)「人机互动」一致）。

### 交互场景测试（JSON 剧本驱动）

将"用户在分析页会看到什么"写成可执行、可回归的 JSON 剧本，避免只靠口头描述或临时抓包。

**剧本结构**（`tests/fixtures/interaction_scenarios/*.json`）：
```json
{
  "id": "scout_field_review",
  "name": "字段确认流程",
  "steps": [
    {
      "note": "用户看到字段表格后，回复字段含义修正",
      "ws": { "action": "respond", "message": "转化率 = 购买人数/总访问人数*100%" },
      "expected": { "status": "scout_done" }
    }
  ]
}
```

**核心组件**：

| 组件 | 文件 | 作用 |
|------|------|------|
| 剧本加载器 | `hagoku/devtools/interaction_scenarios.py` | 加载、校验 JSON 剧本（`id`/`steps` 结构验证） |
| 场景模拟器 | `scripts/simulate_interaction_scenario.py` | 按剧本步骤驱动 orchestrator，断言每步预期状态 |
| 产品契约测试 | `tests/test_product/test_interaction_scenarios.py` | 跑通所有场景的 pytest adapter |

**脚本用法**：
```bash
# 跑单个场景
.venv/bin/python scripts/simulate_interaction_scenario.py --scenario scout_field_review

# 列出所有可用场景
.venv/bin/python scripts/simulate_interaction_scenario.py --list
```

**剧本编写规则**：
- 每个 step 必须有 `note`（人类叙述，给作者看的）
- `ws` 可选字段：`action`（`respond`/`command`）、`message`（自然语言内容）
- `expected` 可选字段：`status`（预期的 orchestrator 返回状态）、`event`（预期的 WebSocket 事件类型）
- 校验失败时 `validation_errors` 列出人类可读错误

### UI 手动测试步骤
1. 浏览器打开前端界面（本地多为 Vite 终端打印的地址，常见形如 `http://localhost:5173`）
2. **项目** 页选择或创建项目，确认描述与数据文件
3. **分析** 页：选择项目与数据 → **开始分析**（必要时先输入/补充研究问题）
4. 观察 **流水线进度** 与 **对话区**：在暂停点应出现 Agent 引导语，用自然语言 **回复** 后继续
5. **报告** 页：切换项目，**按 run** 查看。**正常完成**：打开 HTML（默认双轨：要点速览 + 完整证据）。**强制级护栏未通过**：应看到说明（或链到 `GUARDRAILS_BLOCKED.md` 全文），**不**把「双轨 HTML 成功预览」当成该次的默认交付态。
6. **事件** 页（可选）：查看 WebSocket 事件流；若存在护栏拦截，`run_completed` 等在列表/标签上应与「成功完成」区分（含 `run_id` 以便对照报告与 API）。
7. **护栏拦截整条路径**（有可调触发数据时）：分析页终态、项目卡状态、`GET .../runs` 与 `.../detail` 的 `guardrails_blocked` 应与实际是否产出正式 HTML 一致。

### Playwright UI 自动化（受限）
```bash
.venv/bin/python -c "
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    browser = p.chromium.launch(headless=False, args=['--no-sandbox'])
    page = browser.new_page()
    page.goto('http://localhost:5173', timeout=60000)
    page.wait_for_load_state('domcontentloaded')
    page.get_by_text('分析', exact=True).first.click()
"
```

> **说明**：完整分析流可结合后端集成测试。旧版 Streamlit 限制见 [TROUBLESHOOTING.md §1](TROUBLESHOOTING.md#1-ui-自动化测试playwright)。

---

## 代码审查清单（每次提交前）

1. **通道完整性**：用户输入语义解析路径中是否出现中文硬匹配？
   ```bash
   # 审查命令：通道区域内禁止中文动词匹配
   grep -nE '(代表|表示|意为|是|当成|看作)' hagoku/agents/scout/agent.py
   grep -nE '(代表|表示|意为|是|当成|看作)' hagoku/manager/orchestrator.py
   ```
   若新增中文字符串匹配或 if-else 语义分支 → 拒绝合并，改为补通道。

2. `emit_event` 调用是否有遗漏的 3 参数形式？
   ```bash
   grep -n "emit_event(" hagoku/agents/*.py
   ```

3. `column_semantics` 是否正确传递？
   ```bash
   grep -n "column_semantics" hagoku/manager/orchestrator.py
   grep -n "column_semantics" hagoku/agents/scout/agent.py
   ```

4. SQLite 线程安全是否完整？
   - `memory_backends.py` 的 `save`/`delete` 用 `transaction()`
   - `database.py` 有 `check_same_thread=False` 和 `_lock`

5. pytest 是否通过？
   ```bash
   .venv/bin/python -m pytest tests/ -q
   ```

6. 若改动 `hagoku_web/src/utils/wsGuardrails.ts`：是否已同步 `tests/test_web/test_ws_guardrails_parity.py` 并通过？

7. orchestrator 3 个阶段是否都返回正确 status？
   - `scout_first` → `scout_done`
   - `cleaning_first` → `cleaner_strategy`
   - `analyst_first` → `analyst_preliminary`

8. 本地 `UI_CHANGELOG_backup_*` 快照是否误加入暂存区？

---

## 不要做的清单

- ❌ 不要修改 `~/.llama-proxy/` 下的任何文件
- ❌ 不要用 `pm2 restart` 或 `pm2 stop` 操作 llama-proxy
- ❌ 不要自己新建 llama.cpp 模型服务
- ❌ 不要改 `config.py` 里 `~/.hagoku/.env` 的加载逻辑
- ❌ 不要在 UI 代码里用 `time.sleep` 阻塞
- ❌ 不要在 UI 代码里用相对导入（用 `from hagoku.xxx`）
- ❌ 不要用已删除的 Streamlit 前提推断当前 React UI 的行为
- ❌ 不要在 commit message 里写 "various fixes" 或 "update"
- ❌ 不要硬编码字段语义兜底（所有语义决策交给 LLM，见 PROJECT.md「防退化机制」）

---

## 架构净化（P0，2026-05-20 已完成）

以下硬编码语义已被移除，相应环节改为 LLM 决策。新增代码**不得**恢复以下模式：

| 已移除的模式 | 原位置 | 犯规类型 |
|-------------|--------|---------|
| `if "分析" in text: intent="descriptive"` | `query_parser.py` | 关键词硬匹配 |
| `maxv > q75v * 10` / `* 3` / `pct < q25 * 0.3` | `scout/agent.py` | 数值阈值硬编码 |
| `DISTRIBUTION_CATEGORICAL_THRESHOLD` / `_LOW_CARDINALITY` 常量 | `agents/constants.py` | 已删除 |
| `re.match(r"^([^=]+)=(.+)$", line)` 字段描述解析 | `orchestrator.py` | 正则语义解析 |
| `s[:17] + "…"` / `_format_sample_preview()` | `scout/agent.py` | 硬编码格式化 |
| `match action_type: case "descriptive": goals.append(...)` | `orchestrator.py` | 枚举映射表 |
| `llm_lines = [f"正在{t}..."]` 阶段消息拼装 | `orchestrator.py` | 自然语言硬写 |

**约束**：
- 审查命令覆盖区已扩展：`orchestrator.py`、`scout/agent.py`、`query_parser.py`
- 发现同类模式 → 走 `docs/AGENT_HARDCODED_REVIEW.md` 流程录入，非紧急不在此次 P0 范围外自行删除

---

## 看板协作实现

### SQLite Schema

```sql
CREATE TABLE kanban_tasks (
    id              TEXT PRIMARY KEY,
    agent           TEXT NOT NULL,
    title           TEXT NOT NULL,
    description     TEXT,
    status          TEXT DEFAULT 'triage',
    priority        INTEGER DEFAULT 0,
    parent_id       TEXT,
    workspace_path  TEXT,
    created_at      TEXT,
    updated_at      TEXT,
    completed_at    TEXT,
    claim_lock      TEXT,
    claim_expires   INTEGER,
    FOREIGN KEY (parent_id) REFERENCES kanban_tasks(id)
);

CREATE TABLE task_events (
    id          TEXT PRIMARY KEY,
    task_id     TEXT NOT NULL,
    event_type  TEXT NOT NULL,
    actor       TEXT,
    body        TEXT,
    created_at  TEXT,
    FOREIGN KEY (task_id) REFERENCES kanban_tasks(id)
);

CREATE TABLE task_comments (
    id          TEXT PRIMARY KEY,
    task_id     TEXT NOT NULL,
    author      TEXT NOT NULL,
    body        TEXT,
    created_at  TEXT,
    FOREIGN KEY (task_id) REFERENCES kanban_tasks(id)
);
```

### 看板状态机

```
triage → todo → ready → running → blocked → ready → done
                                    ↓
                                 archived
```

### HaGoKu Studio 适配

| 看板状态 | HaGoKu Studio 含义 |
|----------|-------------|
| `triage` | 新建任务，Scout 待启动 |
| `todo` | Scout 正在理解字段 |
| `ready` | 等待用户确认（字段/策略/方向） |
| `running` | Agent 正在执行 |
| `blocked` | 等待用户输入 |
| `done` | 阶段完成，可交接下一 Agent |

### 关键机制

**父子任务依赖**：Scout 完成 → Cleaner 自动晋升 `ready`；`init_pipeline()` 建立 parent_id 关系。

**Claim 锁**：`ready → running` 原子操作，15 分钟过期，长任务需 heartbeat 续期。`claim_task()` 返回值必须检查。

**Orchestrator 钩子（2026-06-06 从 Scribe 内联而来）**：监听 EventBus → Agent STARTED 更新状态 → Agent COMPLETED 触发晋升 → USER_INPUT_REQUESTED 进入 blocked。

### 文件对应关系

| 功能 | 文件 |
|------|------|
| SQLite 操作 | `hagoku/storage/kanban.py` |
| **Orchestrator 内联 kanban** | `hagoku/manager/orchestrator.py`（_on_event / _init_pipeline_tasks / block_task / unblock_task） |
| kanban.db | 项目根目录 |
| ~~Scribe Agent~~ | ~~`hagoku/agents/_scribe/agent.py`~~ — **2026-06-06 删除** |
| ~~context.md~~ | **2026-06-06 删除**（handover 改直传） |
| ~~handover_notes.md~~ | **2026-06-06 删除** |
| ~~process_log.md~~ | **2026-06-06 删除** |

### 禁止事项

- ❌ kanban.db 不放在全局目录，必须在项目文件夹内
- ❌ 不做通用看板（不做多项目全局视图，不做用户管理）
- ❌ Orchestrator 不直接与用户对话，只在后台做 ctx 注入 + 看板管理
- ❌ 不要忽略 `claim_task()` 的返回值

---

## Agent 知识向量系统

### 技术栈

- **向量存储**：sqlite_vec（SQLite 扩展）+ OpenAI 兼容 embedding API
- **配置环境变量**：`HAGOKYU_EMBEDDING_BASE_URL` / `HAGOKYU_EMBEDDING_API_KEY` / `HAGOKYU_EMBEDDING_MODEL`
- **维度**：1536（text-embedding-3-small）

### 文件布局

```
hagoku/agents/<agent>/
  knowledge.yaml   ← 人可读知识条目
  knowledge.db     ← sqlite_vec 向量数据库
  knowledge.py     ← recall/learn 封装函数
```

### KnowledgeVectorStore API

```python
from hagoku.storage.knowledge_vector import KnowledgeVectorStore

store = KnowledgeVectorStore("path/to/knowledge.yaml", dimension=1536)

results = store.recall(query="渠道 ROI 分析", tags=["regression"], top_k=3)
# [{id, content, tags, metadata, similarity, use_count}, ...]

entry_id = store.add(content="场景：渠道分析；方法：回归", tags=["roi", "regression"],
    metadata={"method": "ols", "confidence": 0.8})
store.upsert(entry_id, content="...", tags=[...], metadata={...})
all_entries = store.list_all()
store.delete(entry_id)
```

### recall() 工作流程

1. `_sync_vectors()`：YAML 有条目但 DB 无向量时自动补全
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

## 错误处理与兜底原则

HaGoKu Studio 的字段理解完全依赖 LLM。任何「字段含义」相关产出 **不存在硬编码 if-else 兜底**。

### 三级防护

| 层级 | 触发条件 | 处理方式 | 负责模块 |
|------|---------|---------|---------|
| **1. 前置健康检查** | pipeline 启动前 | `check_llm_health()` 验证 LLM 可达；失败 → 返回错误，不进 pipeline | `hagoku/tools/health.py` |
| **2. Agent 异常上报** | Scout LLM 调用失败/返回空 | emit `AGENT_FAILED` → Orchestrator 看板 block + 前端展示错误 | `scout/agent.py` → `manager/orchestrator.py` |
| ~~**3. Scribe LLM 兜底恢复**~~ | ~~Scout 产出部分列描述缺失~~ | ~~Scribe 用 LLM 补全遗漏列；失败 → emit `AGENT_FAILED`~~ | ~~`_scribe/agent.py`~~ — **2026-06-06 Scribe 类删除，本层防护不再存在；Scout 走 `needs_user_input=True` 让用户填** |

### 健康检查流程

```
Orchestrator.run()
  ├─ check_llm_health(config)
  │   ├─ 1. HTTP GET /models (timeout=5s)
  │   ├─ 2. 模型名在列表中
  │   ├─ 3. Chat completion ("ping")
  │   └─ 4-5. Token速率/JSON mode (警告)
  ├─ PASS → 进入 pipeline
  └─ FAIL → emit HEALTH_CHECK, 前端红框, return
```

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