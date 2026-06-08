# HaGoKu Studio 代码结构重构审查报告

> **报告日期**: 2026-06-08  
> **审查范围**: `hagoku/`（后端 Python）+ `hagoku_web/`（前端 React/TypeScript）  
> **原则**: 只诊断，不修改。所有结论基于代码实况。

---

## 一、总体评估

| 维度 | 评级 | 说明 |
|------|------|------|
| 设计哲学 | ★★★★★ | 通道完备性十律、LLM/代码边界划分——业界少见的高水准思考 |
| 测试覆盖（后端） | ★★★★☆ | ~50 个测试文件，含独创的 Doctrine AST 守门测试 |
| 测试覆盖（前端） | ☆☆☆☆☆ | **零测试**，1647 行的核心面板无任何自动化覆盖 |
| 代码结构（后端） | ★★★☆☆ | 核心逻辑清晰，但有 monkey-patch 和重复代码问题 |
| 代码结构（前端） | ★★☆☆☆ | 上帝组件 + 零拆分，是当前最大的结构风险 |
| 可维护性 | ★★★☆☆ | 新人理解成本高，IDE 支持因 monkey-patch 打折 |

---

## 二、发现清单（按严重程度排序）

### 🔴 P0-1：AnalyzePanel.tsx — 上帝组件（严重）

**文件**: `hagoku_web/src/panels/AnalyzePanel.tsx`  
**行数**: 1647 行（全项目最大单文件，超过其他任何 .py 或 .tsx 文件）

#### 2.1 当前内容统计

| 内容类别 | 数量 | 说明 |
|----------|------|------|
| interface / type 定义 | 22 个 | 类型与组件混在同一文件 |
| function 定义 | 19 个 | 含 6 个 parser、4 个 table 组件、1 个对话 feed、1 个流水线 bar、3 个工具函数 |
| useState 调用 | ~30 处 | 涵盖了 session、对话、文件、暂停点、闸门 5 类完全不相关的状态 |
| React hooks (useEffect/useCallback/useRef/useLayoutEffect) | ~49 处 | 状态管理逻辑散落在各处 |
| 子组件（内联定义） | 6 个 | FieldReviewTable、CleaningReviewTable、AnalystReviewTable、PipelineBar、ConvoFeed、ClearHistoryButton |
| WebSocket 事件处理 | ~300 行 | 一个巨大的 useEffect 内用 `if (d.event_type === ...)` 分发 7+ 种事件 |
| 文件上传逻辑 | ~40 行 | handleUpload 内联在主组件中 |
| JSX 渲染 | ~380 行 | 包含 setup 面板、运行面板、项目/文件选择器、对话区、输入区 |

#### 2.2 具体拆分点

**(a) 类型定义应独立**

| 当前行号 | 类型 | 应迁至 |
|---------|------|--------|
| 22-23 | `AgentKey`, `AgentRunState` | `types.ts` |
| 41 | `SessionPhase` | `types.ts` |
| 44-63 | `FieldReviewPayload` | `types.ts` |
| 105-113 | `CleaningAssessment` | `types.ts` |
| 123-138 | `CleaningReviewPayload` | `types.ts` |
| 186-199 | `AnalystReviewPayload` | `types.ts` |
| 464-473 | `ConvoMessage` | `types.ts` |
| 475-480 | `ProjectFile` | `types.ts` |

**(b) 纯函数解析器应独立**

| 当前行号 | 函数 | 应迁至 |
|---------|------|--------|
| 26-33 | `resolveAgentKey()` | `parsers.ts` |
| 35-38 | `parsePauseInteractionRevision()` | `parsers.ts` |
| 65-102 | `parseFieldReview()` | `parsers.ts` |
| 115-120 | `parseCleaningAssessment()` | `parsers.ts` |
| 140-184 | `parseCleaningReview()` | `parsers.ts` |
| 201-238 | `parseAnalystReview()` + `significanceShort()` | `parsers.ts` |

**(c) 工具函数应独立**

| 当前行号 | 函数 | 应迁至 |
|---------|------|--------|
| 482-487 | `fmtSize()` | `utils.ts` |
| 489-490 | `uid()` | `utils.ts` |
| 492-495 | `formatScoutUserInputFactLine()` | `utils.ts` |
| 497-503 | `formatStageProceedFactLine()` | `utils.ts` |

**(d) 子组件应独立**

| 当前行号 | 组件 | 行数 | 应迁至 |
|---------|------|------|--------|
| 422-462 | `FieldReviewTable` | ~40 | `FieldReviewTable.tsx` |
| 241-332 | `AnalystReviewTable` | ~90 | `AnalystReviewTable.tsx` |
| 334-420 | `CleaningReviewTable` | ~85 | `CleaningReviewTable.tsx` |
| 506-553 | `PipelineBar` | ~45 | `PipelineBar.tsx` |
| 555-632 | `ConvoFeed` | ~75 | `ConvoFeed.tsx` |
| 633-681 | `ClearHistoryButton` | ~45 | `ClearHistoryButton.tsx` |

**(e) 状态逻辑应提取为 hooks**

| 当前代码区块 | 涉及 state | 应提取为 |
|-------------|-----------|----------|
| ~15 个 useState + handleStartSession + handleReset | phase, agentStates, agentElapsed, waitingAgent, guardrailsBlocked, blockedRunId, resultReportUrl | `useAnalyzeSession.ts` |
| messages state + 所有 setMessages 调用 | messages 数组 + addSystemMsg / addUserMsg / addAgentMsg / addWorkflowCard / updateWorkflowCard | `useConversation.ts` |
| uploading, uploadError, handleUpload, loadFiles, dataPath, fileExists | 文件上传相关所有状态 | `useFileUpload.ts` |
| 265 行的 useEffect 内事件分发 | batch.forEach 内的 7 种 event_type 处理 | `useWsEventHandler.ts`（纯 reducer 函数） |

#### 2.3 目标结构

```
panels/AnalyzePanel/
├── index.tsx              # ~200 行：调用 hooks + 组合子组件
├── types.ts               # 所有 interface/type
├── parsers.ts             # parse* + resolveAgentKey + significanceShort
├── utils.ts               # fmtSize, uid, format* 工具函数
├── PipelineBar.tsx        # 流水线进度条
├── FieldReviewTable.tsx   # Scout 字段核对表
├── CleaningReviewTable.tsx# Cleaner 清洗核对表
├── AnalystReviewTable.tsx # Analyst 结果核对表
├── ConvoFeed.tsx          # 对话 feed
└── ClearHistoryButton.tsx # 清除历史按钮
```

#### 2.4 风险控制

- **P0-1（类型/解析器提取）**: 零风险，纯搬迁，tsc 编译通过即验证
- **P0-2（子组件独立）**: 低风险，不改逻辑只改 import
- **P0-3（hooks 提取）**: 中风险，需保持依赖数组完全不变，不做任何"顺便优化"

---

### 🔴 P0-2：Orchestrator monkey-patch（严重）

**文件**: `hagoku/manager/orchestrator.py`（712 行）  
**问题**: 类定义完成后，用 20 行 monkey-patch 从外部子模块挂方法

#### 3.1 当前 monkey-patch 清单

```python
# orchestrator.py 末尾
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

**方法定义所在子模块**:

| 子模块 | 方法数 |
|--------|--------|
| `llm_dispatch/plan_generation.py` | 4 |
| `llm_dispatch/scout_reply.py` | 2 |
| `llm_dispatch/confirmation.py` | 4 |
| `llm_dispatch/reply_handlers.py` | 4 |
| `payloads/scout_payload.py` | 1（间接） |
| `payloads/pipeline_helpers.py` | 5 |

#### 3.2 后果

| 后果 | 严重程度 |
|------|----------|
| **IDE 跳转失效**: F12 跳到 `Orchestrator.xxx = yyy` 而非实际实现 | 高 |
| **mypy 类型检查失效**: 类定义里没有这些方法，类型检查器看不到 | 高 |
| **新人误导**: 看到 105 行的类定义以为很小，实际有 20 个外部注入方法 | 中 |
| **CH-5 拆分半途而废**: 方法拆到了子模块，但没有归位为类的正式成员 | 中 |

#### 3.3 修复方案：Composition + `__getattr__` 委托

```python
class Orchestrator:
    _METHOD_MAP: dict[str, str] = {
        "_parse_user_query": "_plan",
        "_describe_intent": "_plan",
        # ... 20 个映射
    }
    
    def __init__(self, ...):
        from .llm_dispatch.plan_generation import PlanGenerator
        from .llm_dispatch.scout_reply import ScoutReplyHandler
        # ...
        self._plan = PlanGenerator(self)
        self._scout = ScoutReplyHandler(self)
        # ...
    
    def __getattr__(self, name):
        """委托未定义属性到对应 handler"""
        handler_attr = self._METHOD_MAP.get(name)
        if handler_attr:
            handler = object.__getattribute__(self, handler_attr)
            return getattr(handler, name)
        raise AttributeError(name)
```

**风险**: 中低。`__getattr__` 只在常规属性查找失败时才触发，不影响已在 `__init__` 中定义的属性。需要确认每个 handler 类方法内部对 `self._orch`（原通过闭包访问的变量）的引用正确。

---

### 🟡 P1-1：Agent 层缺少 BaseAgent 基类（中等）

**相关文件**: `agents/scout/agent.py` (1063行), `agents/cleaner/agent.py` (1036行), `agents/analyst/agent.py` (279行), `agents/reporter/agent.py` (641行)  
**现有基类**: `InteractionMixin`（仅 60 行，提供 `_pause()`/`_done()` 两个方法）

#### 4.1 重复代码证据

**(a) `_load_prompt()` — 4 个 Agent 实现完全一致**

```python
# Scout、Cleaner、Analyst、Reporter 中字逐字相同：
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

**(d) `__init__` — 参数高度重复**

| Agent | 签名 |
|-------|------|
| Scout | `(self, llm_config, event_bus, orchestrator=None, llm_client=None, *, channel_logger=None)` |
| Cleaner | `(self, llm_config, event_bus, orchestrator=None, llm_client=None)` |
| Analyst | `(self, llm_config, event_bus, orchestrator=None, llm_client=None)` |
| Reporter | `(self, *args, event_bus=None, llm_client=None, orchestrator=None, **kwargs)` — **完全不同的签名** |

注意 Reporter 使用了 `*args/**kwargs` 兼容旧签名，与其他 3 个 Agent 不一致。

#### 4.2 建议的 BaseAgent

```python
# agents/base.py
class BaseAgent(InteractionMixin):
    role: str = ""
    
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
    
    def _load_prompt(self) -> str:
        """通用实现，按 self.role 定位 prompt.md"""
        path = Path(__file__).parent.parent / self.role / "prompt.md"
        if path.exists():
            return path.read_text(encoding="utf-8")
        return ""
    
    def _emit(self, event_type, data=None):
        """通用实现（含 None 检查，兼容所有 Agent）"""
        if self.event_bus:
            self.event_bus.emit(event_type=event_type, agent=self.role, data=data or {})
    
    def _load_memory(self) -> dict:
        """子类可覆盖 memory_key 控制读取的 YAML 区块"""
        key = getattr(self, "_memory_yaml_key", "fields")
        # ... 通用实现
    
    def _save_memory(self) -> None:
        """子类可覆盖"""
        pass
```

#### 4.3 影响范围

- 4 个 Agent 的 `__init__` 将简化为 `super().__init__(...)` + 自身特有初始化
- Reporter 的 `*args/**kwargs` 兼容可用 `**kwargs` 在 BaseAgent 中统一处理
- 后续新增 Agent 只需要 `class NewAgent(BaseAgent)`，自动获得 prompt 加载、事件发射、记忆管理

**风险**: 中。Reporter 的特殊签名需要仔细处理。建议在 P0-4（Orchestrator 重构）之后再做，因为 Agent 创建方式在 Orchestrator 中。

---

### 🟡 P1-2：tools/analysis.py 过大（中等）

**文件**: `hagoku/tools/analysis.py`（1194 行，41467 字节）  
**文件**: `hagoku/tools/analysis_registry.py`（562 行）  
**依赖方**: 仅 `agents/analyst/agent.py` 和 `manager/orchestrator.py`（只 import `set_analysis_config`）

#### 5.1 当前函数分布

| 函数类别 | 行号 | 函数 |
|----------|------|------|
| 配置 | 19 | `set_analysis_config()` |
| 组间比较 | 30-474 | `ttest()`, `anova()`, `chi_square()`, `correlation()`, `regression()`, `mann_whitney_u()`, `kruskal_wallis()` |
| 增强功能 | 478-1066 | `cross_validate()`, `multiple_comparison_correction()`, `check_test_assumptions()`, `interaction_analysis()` |
| 辅助函数 | 1071-1194 | `_cohens_d()`, `_mean_diff_ci()`, `_check_ttest_assumptions()`, `_regression_diagnostics()` |

#### 5.2 建议拆分

```
tools/analysis/              # 新建目录
├── __init__.py              # 重导出：保持 from hagoku.tools.analysis import ttest 兼容
├── comparison.py            # ttest, anova, mann_whitney_u, kruskal_wallis, chi_square
├── correlation.py           # correlation
├── regression.py            # regression, _regression_diagnostics
├── diagnostics.py           # check_test_assumptions, _check_ttest_assumptions, _cohens_d, _mean_diff_ci
├── advanced.py              # cross_validate, multiple_comparison_correction, interaction_analysis
├── config.py                # set_analysis_config, _insufficient_data
└── registry.py              # 从 analysis_registry.py 移入
```

#### 5.3 API 兼容

`__init__.py` 做重导出：

```python
from .comparison import ttest, anova, mann_whitney_u, kruskal_wallis, chi_square
from .correlation import correlation
from .regression import regression
from .diagnostics import check_test_assumptions
from .advanced import cross_validate, multiple_comparison_correction, interaction_analysis
from .config import set_analysis_config

__all__ = ["ttest", "anova", ...]
```

外部 import 路径 `from hagoku.tools.analysis import ttest` 完全不变。

**风险**: 低。纯文件拆分 + `__init__.py` 重导出。

---

### 🔵 P2-1：前端零测试覆盖（需关注）

**现状**: `tests/test_web/` 目录下仅 1 个文件，测的是 WebSocket guardrails parity，不涉及任何 UI 组件。

| 前端文件 | 行数 | 测试覆盖 |
|----------|------|----------|
| AnalyzePanel.tsx | 1647 | 无 |
| ProjectPanel.tsx | 489 | 无 |
| CommandsPanel.tsx | 456 | 无 |
| SettingsPanel.tsx | 416 | 无 |
| KanbanPanel.tsx | 282 | 无 |
| ReportPanel.tsx | 276 | 无 |
| 所有 hooks | ~266 | 无 |

**建议**: 在 P0-1~P0-3 完成后（类型和组件独立），为关键路径加测试。至少覆盖：
- `parsers.ts` 的 6 个 parse 函数（纯函数，最易测试）
- `useConversation` hook 的消息操作
- `PipelineBar` 组件的状态渲染

---

### 🔵 P2-2：UI_CHANGELOG_backup 文件未清理

**数量**: 18 个备份文件，共计 ~200KB

| 位置 | 文件数 |
|------|--------|
| `hagoku_web/src/panels/` | 4 |
| `hagoku_web/` | 2 |
| `hagoku/agents/scout/` | 3 |
| `hagoku/` 根目录 | 9 |

建议移入 `.archive/` 或添加 `.gitignore`。

---

## 三、执行计划

### 3.1 顺序与依赖关系

```
P0-1 (类型/解析器提取)          ← 第一步，零依赖，零风险
    │
    ▼
P0-2 (子组件独立)               ← 依赖 P0-1 的 types.ts
    │
    ▼
P0-3 (hooks 提取)               ← 依赖 P0-1 + P0-2
    │
    ├──────────────────────────┐
    ▼                          ▼
P0-4 (Orchestrator 重构)    P1-1 (BaseAgent)    P1-2 (tools 拆分)
    │                          │                  │
    └──────────────────────────┴──────────────────┘
                               │
                               ▼
                          最终验证
```

P0-4 / P1-1 / P1-2 互不依赖，可在 P0-3 完成后并行推进。

### 3.2 每步验证标准

| 步骤 | 验证命令 | 通过标准 |
|------|----------|----------|
| P0-1 | `npx tsc -b --noEmit` | 零 TS 错误 |
| P0-2 | `npx tsc -b --noEmit` | 零 TS 错误 |
| P0-3 | `npx tsc -b --noEmit && npm run build` | tsc 零错误 + vite build 成功 |
| P0-4 | `pytest tests/test_manager/ tests/test_product/ -q` | 全绿 |
| P1-1 | `pytest tests/test_agents/ tests/test_product/ -q` | 全绿 |
| P1-2 | `pytest tests/test_tools/ -q` | 全绿 |
| 最终 | `pytest tests/ -q` | 全绿 |

### 3.3 不可违反的铁律

1. **不改行为**：每一步只搬迁代码，不修改逻辑、不优化、不重构
2. **保持外部 API**：`Orchestrator`、`ScoutAgent` 等对外 import 路径不变
3. **一步一提交**：每步完成后可独立 review，方便回滚
4. **最后跑全量测试**：全部步骤完成后 `pytest tests/ -q` 必须全绿

---

## 四、影响汇总

| 问题 | 优先级 | 风险 | 收益 |
|------|--------|------|------|
| AnalyzePanel 上帝组件 | **P0** | 每次改前端要在 1647 行中翻找 | 拆成 10 个 <200 行的文件，职责清晰 |
| Orchestrator monkey-patch | **P0** | IDE 跳转/mypy 失效 | 标准 Python 类，工具链全支持 |
| Agent 无 BaseAgent | **P1** | 4 个 Agent 各写各的 `_load_prompt/_emit` | 新增 Agent 成本从复制 100 行降为 10 行 |
| tools/analysis.py 过大 | **P1** | 1194 行单一文件难导航 | 按统计领域拆为 6 个模块 |
| 前端零测试 | **P2** | 重构时没有安全网 | 至少 pure function 有覆盖 |
| UI_CHANGELOG_backup 残留 | **P2** | 混淆主代码 | 仓库整洁 |

---

> **核心建议**: 先做 P0-1。它完全零风险（只搬迁类型和纯函数），能立刻验证整条"拆分→tsc 通过"链路是否可行。做完 P0-1 后，后续步骤的模式就确立了。
