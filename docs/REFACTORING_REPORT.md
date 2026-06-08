# HaGoKu Studio 代码结构重构审查报告

> **报告日期**：2026-06-08（架构审核方核验修正版）
> **审查范围**：`hagoku/`（后端 Python）+ `hagoku_web/`（前端 React/TypeScript）
> **报告性质**：既是诊断也是可执行交付件——下半段（§三~§九）等同于 brief，直接交付实施 AI 执行
> **执行模式**：**单 commit 审核**（每步独立 commit + 立即审）

---

## 一、总体评估

| 维度 | 评级 | 说明 |
|------|------|------|
| 设计哲学 | ★★★★★ | 通道完备性十律、LLM/代码边界划分——业界少见的高水准思考 |
| 测试覆盖（后端） | ★★★★☆ | 50+ 测试文件，含独创的 Doctrine AST 守门测试 |
| 测试覆盖（前端） | ☆☆☆☆☆ | **零 React 组件测试**（test_web/ 仅 1 个测 WebSocket guardrails 的 .py） |
| 代码结构（后端） | ★★★☆☆ | 核心逻辑清晰，但 Orchestrator monkey-patch + Agent 重复代码 |
| 代码结构（前端） | ★★☆☆☆ | 上帝组件 + 零拆分，当前最大的结构风险 |
| 可维护性 | ★★★☆☆ | 新人理解成本高，IDE 支持因 monkey-patch 打折 |

---

## 二、现状盘点（基于代码审计，当次实测）

### 2.1 量化现状

| 文件 | 行数 | 主要问题 |
|------|------|---------|
| `hagoku_web/src/panels/AnalyzePanel.tsx` | 1647 | 上帝组件（详 §2.2） |
| `hagoku/agents/scout/agent.py` | 1063 | Agent 间重复代码（详 §2.4） |
| `hagoku/agents/cleaner/agent.py` | 1036 | 同上 |
| `hagoku/agents/reporter/agent.py` | 641 | 同上 + `__init__` 签名与其他 3 个不一致 |
| `hagoku/agents/analyst/agent.py` | 279 | 同上 |
| `hagoku/manager/orchestrator.py` | 712 | 末尾 20 行 monkey-patch（详 §2.3） |
| `hagoku/tools/analysis.py` | 1194 | 单文件混杂 7+ 统计类别 |
| `hagoku/tools/analysis_registry.py` | 562 | 与 analysis.py 强耦合 |

所有数字实施方必须**当次重新跑 `wc -l` 复核**（详 §三契约 2）。

### 2.2 AnalyzePanel 1647 行内容统计

| 内容类别 | 数量 | 备注 |
|----------|------|------|
| interface / type 定义 | 22 个 | 类型与组件混在同一文件 |
| function 定义 | 19 个 | 含 6 个 parser、4 个内联表格、1 个对话 feed、1 个流水线 bar、3 个工具函数 |
| useState 调用 | ~30 处 | 涵盖 session / 对话 / 文件 / 暂停点 / 闸门 5 类完全不相关的状态 |
| useEffect/useCallback/useRef/useLayoutEffect | ~49 处 | 状态管理逻辑散落在各处 |
| 内联子组件 | 6 个 | FieldReviewTable / CleaningReviewTable / AnalystReviewTable / PipelineBar / ConvoFeed / ClearHistoryButton |
| WebSocket 事件处理 useEffect | ~300 行 | 一个巨大 useEffect 内用 `if (d.event_type === ...)` 分发 7+ 种事件 |
| 文件上传逻辑 | ~40 行 | handleUpload 内联在主组件中 |
| JSX 渲染 | ~380 行 | 含 setup 面板、运行面板、项目/文件选择器、对话区、输入区 |

### 2.3 Orchestrator monkey-patch 实况

#### 2.3.1 末尾 20 行（已实测）

```python
# orchestrator.py 末尾
# ── CH-5 方法委托：将提取的实例方法挂回 Orchestrator ─────────
Orchestrator._parse_user_query = _parse_user_query
Orchestrator._describe_intent = _describe_intent
Orchestrator._build_analysis_purpose = _build_analysis_purpose
Orchestrator._get_upstream_summary = _get_upstream_summary
Orchestrator._llm_classify_confirmation = _llm_classify_confirmation
Orchestrator._build_intent_context = _build_intent_context
Orchestrator._request_field_confirmation = _request_field_confirmation
Orchestrator._apply_field_corrections = _apply_field_corrections
Orchestrator._handle_scout_reply = _handle_scout_reply
Orchestrator._handle_cleaner_reply = _handle_cleaner_reply
Orchestrator._handle_analyst_reply = _handle_analyst_reply
Orchestrator._handle_reporter_reply = _handle_reporter_reply
Orchestrator.respond = respond
Orchestrator._ensure_memory_for_respond = _ensure_memory_for_respond
Orchestrator._check_mandatory_guardrails = _check_mandatory_guardrails
Orchestrator._handle_mandatory_violations = _handle_mandatory_violations
Orchestrator._finish_run_cancelled = _finish_run_cancelled
Orchestrator._handle_command_if_present = _handle_command_if_present
Orchestrator._init_pipeline_tasks = _init_pipeline_tasks
Orchestrator._attach_pause_dialogue_message = _attach_pause_dialogue_message
```

20 个方法分布在 6 个子模块：`llm_dispatch/plan_generation.py` / `scout_reply.py` / `confirmation.py` / `reply_handlers.py`、`payloads/scout_payload.py` / `pipeline_helpers.py`。

#### 2.3.2 后果

| 后果 | 严重程度 |
|------|---------|
| IDE F12 跳转跳到 `Orchestrator.xxx = yyy` 而非实际实现 | 高 |
| mypy 类型检查失效：类定义里没有这些方法 | 高 |
| 新人误导：看到 105 行的类定义以为很小，实际有 20 个外部注入方法 | 中 |
| CH-5 拆分半途而废：方法拆到了子模块，但没有归位为类的正式成员 | 中 |

#### 2.3.3 为何 `__getattr__` 委托是伪修复

`__getattr__` 方案下：
- IDE F12 仍然跳到 `__getattr__` 实现而非真方法定义
- mypy 仍报 `Orchestrator has no attribute "_handle_scout_reply"`（除非用 `cast` / `# type: ignore`）
- 静态分析工具看不到方法签名（参数 / 返回类型）

**唯一干净的修复**是把方法定义合入类的 MRO——用 **Mixin 多继承**。Mixin 类的方法对 IDE / mypy 透明，零运行时开销。

### 2.4 Agent 重复代码

`hagoku/agents/base.py` **不存在**（实测 `ls` 返回"没有那个文件或目录"）。`InteractionMixin` 在 `hagoku/agents/_interactive.py`（71 行）提供 `_pause()` / `_done()` / `begin()` / `respond()` 基础，但**未覆盖** prompt/memory/事件发射这些 Agent 共享逻辑。

**(a) `_load_prompt()` — 4 个 Agent 实现逐字相同**

```python
def _load_prompt(self) -> str:
    path = Path(__file__).parent / "prompt.md"
    if path.exists():
        return path.read_text(encoding="utf-8")
    return ""
```

**(b) `_emit()` — 3 个 Agent 完全一致，Cleaner 多一个 if 守卫**

```python
# Scout、Analyst、Reporter（一致）:
def _emit(self, event_type, data=None):
    self.event_bus.emit(event_type=event_type, agent=self.role, data=data or {})

# Cleaner（多一个 None 检查）:
def _emit(self, event_type, data=None):
    if self.event_bus:
        self.event_bus.emit(event_type=event_type, agent=self.role, data=data or {})
```

**(c) `_load_memory()` — 结构相同，YAML key 不同**

```python
# Scout: re.search(r"```yaml\n(.*?)\n```", ...)
# Cleaner: re.search(r"```yaml\n(cleaning_preferences:.*?)```", ...)
# Analyst: re.search(r"```yaml\n(analysis_patterns:.*?)```", ...)
# Reporter: re.search(r"```yaml\n(reports:.*?)```", ...)
```

**(d) `__init__` 签名**

| Agent | 签名 |
|-------|------|
| Scout | `(self, llm_config, event_bus, orchestrator=None, llm_client=None, *, channel_logger=None)` |
| Cleaner | `(self, llm_config, event_bus, orchestrator=None, llm_client=None)` |
| Analyst | `(self, llm_config, event_bus, orchestrator=None, llm_client=None)` |
| Reporter | `(self, *args, event_bus=None, llm_client=None, orchestrator=None, **kwargs)` ← **不一致** |

### 2.5 UI_CHANGELOG_backup 残留

实测 **25 个**备份文件（不是早期版本说的 18 个）：

```bash
find . -name "UI_CHANGELOG_backup*" -not -path "./.git/*" -not -path "*/node_modules/*" | wc -l
# 输出：25
```

分布：仓库根目录 / `hagoku_web/` / `hagoku_web/src/panels/` / `hagoku/agents/scout/`。

### 2.6 前端测试覆盖

- `tests/test_web/test_ws_guardrails_parity.py` 1 个文件，测 WebSocket guardrails 等价性
- 所有 `.tsx` / `.ts` 文件**零自动化测试**
- 精确表述：**零 React 组件测试**，非"零前端测试"

---

# 第二部分：可执行交付件（brief 形态）

> 以下章节等同于 brief，交付实施 AI 直接执行。
> 文档前部分（一、二）是诊断依据；以下是修改契约。

---

## 三、角色与边界（实施方必读）

继承 `docs/plans/2026-06-07-channel-hardening-brief.md` §0 全部规则 + `docs/plans/2026-06-07-analyst-routing-execution-protocol.md` 的 9 步执行循环和 3 条诚信契约。

### 3.1 commit prefix

| 任务 | prefix |
|------|--------|
| R-1 ~ R-7 | `[R-N]` |

### 3.2 继承的 3 条诚信契约（CH-7-fixup 立 / 必须遵守）

1. body 中文件名 / grep / ls / wc 类断言必须有 shell 实测证据
2. 数字（test count / 行数 / 文件数）必须当次实测，禁止抄写本报告中的数字
3. 否定断言（不存在 / 空 / 无）须两种工具交叉验证

### 3.3 本报告特定红线

| # | 红线 | 理由 |
|---|------|------|
| L1 | **不改任何行为**——每个 R-N 都是纯搬迁/拆分，禁止顺手优化逻辑 | 单职责，便于回滚 |
| L2 | **保持外部 import 路径不变** | `from hagoku.tools.analysis import ttest` 等仍工作 |
| L3 | **一步一 commit，禁止合并** | 单 commit 审核模式要求 |
| L4 | **每个 commit 后跑全量 `pytest -q --tb=no`** | 任一红 = 改坏了，回滚不进下一步 |
| L5 | **Orchestrator monkey-patch 修复必须用 Mixin 多继承，禁止 `__getattr__` 委托** | `__getattr__` 不解决 IDE/mypy 痛点（详见 §2.3.3） |
| L6 | **不许新建 LLM 调用 / 不许改 prompt** | 本报告是代码组织重构，不是行为修改 |
| L7 | **UI_CHANGELOG_backup 清理只许 `git mv` 到 `.archive/` 或加 .gitignore，禁止 `rm`** | 保留历史 |

---

## 四、任务清单（7 个 commit，按依赖排序）

### R-1 AnalyzePanel — 类型 / parsers / utils 提取

**改动范围**：
- 新建 `hagoku_web/src/panels/AnalyzePanel/types.ts`
- 新建 `hagoku_web/src/panels/AnalyzePanel/parsers.ts`
- 新建 `hagoku_web/src/panels/AnalyzePanel/utils.ts`
- 修改 `hagoku_web/src/panels/AnalyzePanel.tsx`：移除已迁移代码 + 加 import

**迁移清单**（实施方按当次行号复核）：

| 内容类型 | 数量 | 目标文件 |
|---------|------|---------|
| 22 个 interface/type | 全部 | `types.ts` |
| `resolveAgentKey` / `parsePauseInteractionRevision` / `parseFieldReview` / `parseCleaningAssessment` / `parseCleaningReview` / `parseAnalystReview` / `significanceShort` | 7 个纯函数 | `parsers.ts` |
| `fmtSize` / `uid` / `formatScoutUserInputFactLine` / `formatStageProceedFactLine` | 4 个 | `utils.ts` |

**验收**：
1. `cd hagoku_web && npx tsc -b --noEmit` 零错误
2. `cd hagoku_web && npm run build` 成功
3. `pytest -q --tb=no | tail -3` 全绿（兜底）
4. `wc -l hagoku_web/src/panels/AnalyzePanel.tsx` 应明显减少
5. **反向断言**：`grep -n "^interface\|^type " hagoku_web/src/panels/AnalyzePanel.tsx` 零命中（双工具：grep + `npx tsc --listFiles | head`）

**红线**：L1（不改逻辑）；不许重命名导出符号

---

### R-2 AnalyzePanel — 子组件独立

**前置依赖**：R-1（types.ts 已就位）

**改动范围**：
- 新建 6 个文件在 `hagoku_web/src/panels/AnalyzePanel/`：
  - `PipelineBar.tsx`
  - `FieldReviewTable.tsx`
  - `CleaningReviewTable.tsx`
  - `AnalystReviewTable.tsx`
  - `ConvoFeed.tsx`
  - `ClearHistoryButton.tsx`
- 修改 `AnalyzePanel.tsx`：移除内联组件 + 加 import

**验收**：
1. `tsc -b --noEmit` 零错误
2. `npm run build` 成功
3. `wc -l hagoku_web/src/panels/AnalyzePanel.tsx` 应进一步减少
4. **反向断言**：`grep -n "^function \(FieldReviewTable\|CleaningReviewTable\|AnalystReviewTable\|PipelineBar\|ConvoFeed\|ClearHistoryButton\)" hagoku_web/src/panels/AnalyzePanel.tsx` 零命中
5. **手工冒烟**：实施方需在 commit body 声明已本地 `npm run dev` 跑过一次，UI 渲染无 regression

**红线**：L1（不改 JSX 结构、不改 props）

---

### R-3 AnalyzePanel — Hooks 提取

**前置依赖**：R-1 + R-2

**改动范围**：
- 新建 4 个 hook 文件在 `hagoku_web/src/panels/AnalyzePanel/hooks/`：
  - `useAnalyzeSession.ts`（phase / agentStates / agentElapsed / waitingAgent / guardrailsBlocked / blockedRunId / resultReportUrl）
  - `useConversation.ts`（messages + addSystemMsg / addUserMsg / addAgentMsg / addWorkflowCard / updateWorkflowCard）
  - `useFileUpload.ts`（uploading / uploadError / handleUpload / loadFiles / dataPath / fileExists）
  - `useWsEventHandler.ts`（300 行的 useEffect 内 batch.forEach 分发逻辑——**纯 reducer 函数**，禁止改控制流）

**验收**：
1. `tsc -b --noEmit` 零错误
2. `npm run build` 成功
3. `wc -l hagoku_web/src/panels/AnalyzePanel.tsx` 应 **≤ 400 行**（目标）
4. **手工冒烟**：本地完整跑一次 Scout → Cleaner → Analyst → Reporter，确认 WebSocket 事件流无 regression
5. **反向断言**：`grep -c "useState\|useEffect\|useCallback\|useRef\|useLayoutEffect" hagoku_web/src/panels/AnalyzePanel.tsx` 应 ≤ 8

**红线**：
- L1（依赖数组完全不变，不优化）
- 禁止在 hooks 间提前抽公共代码（提取公共是后续工作）

---

### R-4 Orchestrator monkey-patch 修复（Mixin 多继承）

**前置依赖**：无（独立任务，可与前端任务并行调度）

**改动范围**：
- 修改 6 个子模块，把模块级函数包装成 Mixin 类：
  - `hagoku/manager/llm_dispatch/plan_generation.py` → `PlanGenerationMixin`
  - `hagoku/manager/llm_dispatch/scout_reply.py` → `ScoutReplyMixin`
  - `hagoku/manager/llm_dispatch/confirmation.py` → `ConfirmationMixin`
  - `hagoku/manager/llm_dispatch/reply_handlers.py` → `ReplyHandlersMixin`
  - `hagoku/manager/payloads/pipeline_helpers.py` → `PipelineHelpersMixin`
  - `hagoku/manager/payloads/scout_payload.py` → `ScoutPayloadMixin`（若有方法挂回）
- 修改 `hagoku/manager/orchestrator.py`：
  - 顶部 `from .llm_dispatch.xxx import XxxMixin`
  - `class Orchestrator(PlanGenerationMixin, ScoutReplyMixin, ConfirmationMixin, ReplyHandlersMixin, PipelineHelpersMixin):`
  - **删除末尾 20 行 monkey-patch**

**实现要点**：
- Mixin 类内的方法签名保持 `def _handle_xxx(self, ...)` 完全不变
- 原模块级函数若被其他地方调用（如测试 import），保留模块级别名 `_handle_scout_reply = ScoutReplyMixin._handle_scout_reply`（兼容旧 import 路径）
- 调研先行：实施方先 grep 验证当前模块级函数有哪些外部调用方
  ```bash
  grep -rn "from hagoku.manager.llm_dispatch.scout_reply import" hagoku/ tests/ --include="*.py"
  grep -rn "from hagoku.manager.llm_dispatch.reply_handlers import" hagoku/ tests/ --include="*.py"
  # 等等 6 个模块
  ```

**验收**：
1. `pytest tests/test_manager/ tests/test_product/ -q --tb=no | tail -3` 全绿
2. `pytest -q --tb=no | tail -3` 全绿
3. **反向断言**：`grep -c "Orchestrator\._.*= _" hagoku/manager/orchestrator.py` 零命中（双工具：grep + `python -c "from hagoku.manager.orchestrator import Orchestrator; print([m for m in dir(Orchestrator) if not m.startswith('__')])"` 输出方法列表）
4. **IDE 验证**（commit body 声明）：`Orchestrator()._handle_scout_reply` 在 IDE 中 F12 能跳到 `ScoutReplyMixin._handle_scout_reply` 定义

**红线**：
- L5（禁止用 `__getattr__` 委托）
- L1（不改任何方法实现）
- Mixin 类的命名必须以 `Mixin` 结尾

**§六触发条件**：若调研发现某模块级函数被测试 / CLI 直接 import 调用（不经过 Orchestrator 实例），停下回报。决策是保留模块级别名兼容、还是修改 caller。

---

### R-5 BaseAgent 抽取

**前置依赖**：R-4（Orchestrator 已稳定）

**改动范围**：
- 新建 `hagoku/agents/base.py`：

```python
class BaseAgent(InteractionMixin):
    role: str = ""
    _memory_yaml_key: str = "fields"  # 子类覆盖

    def __init__(self, llm_config=None, event_bus=None,
                 orchestrator=None, llm_client=None, **kwargs):
        self.llm_config = llm_config
        self.event_bus = event_bus
        self.orchestrator = orchestrator
        self._llm_client = llm_client
        self._channel_logger = kwargs.get("channel_logger")
        self.prompt = self._load_prompt()
        self.memory = self._load_memory()
        self._phase = "begin"

    def _load_prompt(self) -> str: ...  # 通用实现
    def _emit(self, event_type, data=None): ...  # 含 if event_bus 守卫
    def _load_memory(self) -> dict: ...  # 按 self._memory_yaml_key 读取
    def _save_memory(self) -> None: ...  # 通用实现
```

- 修改 4 个 Agent：`class XxxAgent(BaseAgent)` 替换 `class XxxAgent(InteractionMixin)`
- 删除 4 个 Agent 中重复的 `_load_prompt` / `_emit` / `_load_memory` / `__init__` 中可被 `super().__init__()` 取代的部分
- **特殊处理 Reporter**：当前 `__init__` 用 `*args/**kwargs` 兼容旧签名——R-5 进一步统一为 `super().__init__(...)` + 自身特有字段

**调研先行**：

```bash
grep -n "def __init__\|def _load_prompt\|def _emit\|def _load_memory\|def _save_memory" hagoku/agents/*/agent.py
```

**验收**：
1. `pytest tests/test_agents/ tests/test_product/ -q --tb=no | tail -3` 全绿
2. `pytest -q --tb=no | tail -3` 全绿
3. **反向断言**：4 个 `agent.py` 中 `_load_prompt` 实现数应 ≤ 0（全部上移）
   ```bash
   grep -c "def _load_prompt" hagoku/agents/*/agent.py | grep -v ":0$"
   # 期望：无输出
   ```
4. Agent 行数应有显著减少（4 个文件合计至少减少 100 行）

**红线**：
- L1（不改 Agent 行为）
- Reporter 的特殊签名兼容必须在 BaseAgent 中处理，禁止重新引入 `*args/**kwargs` 兼容
- BaseAgent 不许添加新逻辑——仅是 4 个 Agent 现有共同代码的物理位置上移

**§六触发条件**：
- 若调研发现 4 个 Agent 的 `_load_prompt` 实际不完全一致（含路径定制 / 编码差异），停下回报
- 若 Reporter 的 `*args` 承担了不可移除的兼容路径，停下回报

---

### R-6 `tools/analysis.py` 拆分

**前置依赖**：无（独立任务）

**改动范围**：
- 新建目录 `hagoku/tools/analysis/`
- 拆分文件：

```
hagoku/tools/analysis/
├── __init__.py     # 重导出
├── comparison.py   # ttest, anova, mann_whitney_u, kruskal_wallis, chi_square
├── correlation.py  # correlation
├── regression.py   # regression, _regression_diagnostics
├── diagnostics.py  # check_test_assumptions, _check_ttest_assumptions, _cohens_d, _mean_diff_ci
├── advanced.py     # cross_validate, multiple_comparison_correction, interaction_analysis
└── config.py       # set_analysis_config, _insufficient_data
```

- **删除原 `hagoku/tools/analysis.py` 单文件**（被新目录的 `__init__.py` 取代）
- `analysis_registry.py` 暂不动

**`__init__.py` 重导出**（保持外部 import 路径不变 — L2）：

```python
from .comparison import ttest, anova, mann_whitney_u, kruskal_wallis, chi_square
from .correlation import correlation
from .regression import regression
from .diagnostics import check_test_assumptions
from .advanced import cross_validate, multiple_comparison_correction, interaction_analysis
from .config import set_analysis_config

__all__ = [
    "ttest", "anova", "mann_whitney_u", "kruskal_wallis", "chi_square",
    "correlation", "regression", "check_test_assumptions",
    "cross_validate", "multiple_comparison_correction", "interaction_analysis",
    "set_analysis_config",
]
```

**验收**：
1. `pytest tests/test_tools/ -q --tb=no | tail -3` 全绿
2. `pytest -q --tb=no | tail -3` 全绿
3. **导入路径不变性验证**：
   ```bash
   .venv/bin/python -c "from hagoku.tools.analysis import ttest, regression, correlation, set_analysis_config; print('OK')"
   ```
4. **反向断言**：`ls hagoku/tools/analysis.py 2>&1` 应返回"没有那个文件或目录"（双工具：`ls` + `find hagoku/tools -name "analysis.py" -maxdepth 1`）

**红线**：L1（不改函数实现）；L2（外部 import 路径不变）

---

### R-7 杂项清理（UI_CHANGELOG_backup + 前端 parsers 单测样板）

**前置依赖**：R-1（前端 parsers.ts 已独立）

**改动范围**：

#### 7.1 UI_CHANGELOG_backup 归档
- 实测当前数量：`find . -name "UI_CHANGELOG_backup*" -not -path "./.git/*" -not -path "*/node_modules/*" | wc -l`
- 全部 `git mv` 到 `.archive/ui_changelog_backups/`（保留路径结构）
- 更新 `.gitignore` 加 `.archive/` 规则
- 验证 `DEV.md` 中"UI 快照"段落仍引用正确路径

#### 7.2 前端 parsers 单测样板
- 新建 `hagoku_web/src/panels/AnalyzePanel/__tests__/parsers.test.ts`
- 安装 vitest（若 `package.json` 中无）：`cd hagoku_web && npm install -D vitest`
- 给 6 个 parse 函数中**至少 2 个**写单测（目的是建立"前端可测试"模式，不要求全覆盖）

**验收**：
1. `find . -name "UI_CHANGELOG_backup*" -not -path "./.git/*" -not -path "*/node_modules/*" -not -path "./.archive/*"` 零命中
2. `cd hagoku_web && npx vitest run` 通过
3. `pytest -q --tb=no | tail -3` 全绿

**红线**：
- L7（禁止 `rm`，必须 `git mv`）
- 单测样板写最简单的 2 个，禁止过度工程化

---

## 五、验收清单（每 R-N commit）

```
[ ] commit message 以 [R-N] 开头
[ ] body 中所有数字 / 文件名 / grep 结果有 shell 实测证据
[ ] 数字（test count / 行数 / 文件数）当次实测，未抄写本报告数字
[ ] 否定断言双工具交叉验证
[ ] diff 范围与本报告 "改动范围" 一致（无越界）
[ ] L1-L7 逐条检查无违反
[ ] 任务"验收"逐条满足
[ ] 自检三组 pytest 输出已附（pytest tests/test_doctrine_compliance.py + tests/test_product/test_information_arrival.py + 全量）
[ ] grep 反向断言输出已附
[ ] 前端任务额外含 tsc + build 输出
```

任一未通过 → 退回返工。

---

## 六、何时回到架构审核方

继承 channel-hardening-brief §7 5 种 + analyst-routing-execution-protocol §B 9 种。

本报告新增 4 种触发：

13. **R-4 调研发现某模块级函数被外部直接 import 调用**（如测试不经 Orchestrator 实例）→ 决策是保留兼容别名还是修改 caller，**实施方不得自行裁定**
14. **R-5 调研发现 4 个 Agent 的 `_load_prompt` 实际不完全一致**（含路径定制 / 编码处理差异）→ 停下回报
15. **R-5 Reporter 的 `*args/**kwargs` 兼容承担了不可移除的兼容路径**（如外部脚本调用旧签名）→ 停下回报
16. **任一任务 commit 后全量 `pytest -q` 红** → 立刻 `git reset --soft HEAD~1` 收回，回报根因；禁止继续下一任务"边修边推"

---

## 七、提交格式约定

```
[R-N] <一句话描述>

【自检】判断：本任务是否仅搬迁/拆分代码，不改任何行为？
答案：是 / 否 → 若否必须停下来回报（违反 L1）

【数字对账 — 当次实测】
- pytest --tb=no -q | tail -3 → <粘贴当次输出>
- wc -l <相关文件> → <粘贴当次输出>
- 关键 grep / find / ls 输出 → <粘贴当次输出>

根因：本报告 R-N — <引用哪一条>
改动：<文件 + 行号范围>
验收：
- pytest tests/test_doctrine_compliance.py -q → <结果>
- pytest tests/test_product/test_information_arrival.py -q → <结果>
- pytest -q → <结果>
- <任务特定验证>
- <前端任务额外：tsc + build 输出>

未越界声明：本 commit 未改动报告列出范围之外的文件。
```

---

## 八、任务依赖与建议顺序

```
R-1 (AnalyzePanel 类型/parsers/utils 提取)
    │
    ├──→ R-2 (AnalyzePanel 子组件独立)
    │       │
    │       └──→ R-3 (AnalyzePanel hooks 提取)
    │               │
    │               └──→ R-7 (UI_CHANGELOG 清理 + parsers 单测)
    │
    └──→ R-4 (Orchestrator monkey-patch 修复)
            │
            └──→ R-5 (BaseAgent 抽取)

R-6 (tools/analysis 拆分)        ← 独立任务，任意时机
```

**建议节奏**：
- Day 1：R-1 + R-2（前端结构）
- Day 2：R-3（前端 hooks）+ R-6（tools/analysis 拆分，独立可并行）
- Day 3：R-4（Orchestrator Mixin）
- Day 4：R-5（BaseAgent）+ R-7（杂项）

总计 7 commit，约 4 天。

---

## 九、与前序工作的关系

```
2026-06-07-channel-hardening-brief.md          ← 通道架构与行为收口（CH-1 ~ CH-7）✅
       │
       ├──→ 2026-06-07-analyst-and-routing-brief.md  ← Analyst 二段化 + 控制通道（A/B/C-N）✅
       │
       └──→ docs/REFACTORING_REPORT.md       ← 本报告：代码结构重构（R-1 ~ R-7）
                                                【与产品功能正交：仅改组织不改行为】

      2026-06-08-smoke-and-cleaner-dialog-brief.md  ← 产品演进（SK-N / CL-N）【独立路线】
```

**本报告与 smoke-and-cleaner brief 关系**：两条路线**正交**。R-N 改组织不改行为，SK-N/CL-N 改行为不动组织。建议先做 R-1~R-3（前端结构），再做 SK-1~SK-2（冒烟），并行推进 R-4~R-7（后端结构）与 CL-N（Cleaner 对话化）。

---

**报告出具时间**：2026-06-08
**架构审核方**：Cascade
**前置依赖**：所有前序 brief 已闭环 ✅
**预计完成**：2026-06-12
**执行模式**：单 commit 审核
