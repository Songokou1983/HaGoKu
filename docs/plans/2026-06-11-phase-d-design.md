# Phase D 详细设计稿 — 4 agent 合 1（2026-06-11）

> **文档定位**：架构审核方出具的 Phase D 落地设计，交付实施 AI 执行。
>
> **上游 brief**：[`2026-06-11-collapse-to-single-agent-brief.md`](2026-06-11-collapse-to-single-agent-brief.md) §3 Phase D + [`2026-06-11-memory-three-layer-brief.md`](2026-06-11-memory-three-layer-brief.md)
>
> **前置条件**：Phase A/B/C 已完成（截至 commit `e4ce809`），570 tests 绿。
>
> **⚠️ 这是整个收缩改造的最大不可逆点。** brief §5 标为「高风险」。一旦 4 agent 物理合并，回退成本极高。

---

## ⚠️ §-1 启动前的前置风险（审核方必须先讲清）

### 风险 A：B/C 的真 LLM 验证仍挂账

| 挂账项 | 状态 |
|---|---|
| Phase B：analyst / reporter 真 LLM 全流程 | **从未跑过** |
| Phase C：V3/V4/V5（ask_user 暂停 / 回复继续 / 跳阶段）| 代码就绪，**未端到端验证** |
| reporter 阶段真 LLM route_to 收尾 | **从未验证** |

**问题**：Phase D 要把这 4 个**从未在真 LLM 下端到端验证过**的 agent 合并成 1 个。如果它们当前就有隐藏行为问题，合并后会**混在一起，无法定位是合并引入的还是原本就有的**。

### 审核方建议（但你已决定 go_d_full，我尊重）

理想顺序是：**先在宿主机跑一次 A/B/C 完整 pipeline 真 LLM 冒烟**（scout→cleaner→analyst→reporter 全程），确认 4 agent 当前行为正常，再动 Phase D。

**如果坚持直接开 D**：那么 Phase D 的 §9 真 LLM 冒烟就**同时承担**「验证合并」+「补验 B/C 挂账」两个职责——冒烟剧本必须覆盖 ask_user 暂停、跳阶段、reporter 收尾这些 B/C 没验过的点。**冒烟不过 = D 不结案**，这是唯一的安全网。

### 风险 B：不可逆性

Phase D 删除 `scout/` `cleaner/` `analyst/` `reporter/` 4 个目录。铁律 -1 禁止 `git revert`。**删之前必须确认合并版本真 LLM 冒烟全过**——删目录是 CO-D7（最后一步），前面所有步骤验证通过才能删。

---

## 目录

- §0 调研事实 + brief 校正
- §1 工作量
- §2 合并策略（核心：4 agent.py → 1 DataAnalystAgent）
- §3 统一 prompt 设计（铁律 10 红线）
- §4 工具可见性改造
- §5 orchestrator + reply_handlers 退化
- §6 memory 三层重组
- §7 UI 影响
- §8 测试改造
- §9 真 LLM 冒烟（5 步剧本 + B/C 补验）
- §10 律的减法
- §11 风险点
- §12 CO-D 任务执行顺序
- §13 终审清单
- §14 不做什么
- §15 硬规则
- §16 完成标准

---

## §0 调研事实 + brief 校正

### 0.1 当前 4 agent 真实结构（[Phase D 调研](937931f2-9789-419d-a048-ba00bfdf7278)）

| Agent | agent.py 行数 | 核心入口 | 老接口残留 |
|---|---|---|---|
| Scout | 1094 | `run()` + `_infer_all_semantics()` | `begin()` / `respond()` / `confirm_field()` |
| Cleaner | 1173 | `run_step()` + `assess()` + `run()` | `begin()` / `respond()` / `get_strategy_summary()` |
| Analyst | **265** | `run_step()` 仅此 | **无**（已收缩干净）|
| Reporter | 706 | `run_step()` + `run()` | `begin()` / `respond()` |

**关键洞察**：
1. **Analyst 是合并模板**——只剩 `run_step(context, df, user_input)`，265 行。Phase D 让其余 3 个向它看齐。
2. **4 agent 都继承 `BaseAgent → InteractionMixin`**（`base.py:22` / `_interactive.py:14`）。合并后只需 1 个类。
3. **knowledge.py 大多是死 import**——scout/analyst import 了但不调用；reporter 根本不 import；**只有 cleaner 真用**（recall/learn 4 处）。
4. **生产路径已经事件驱动**：`scout.run()` 在 orchestrator（L361），其余 3 个全走 `reply_handlers` 的 `run_step`/`assess`。

### 0.2 brief 校正

| brief 假设 | 实际 | 影响 |
|---|---|---|
| 「4 agent.py 合并，-3000 行」 | 合计 3238 行（1094+1173+265+706）| 估算量级对 |
| 「orchestrator 709 → ~200 行」 | 当前 703 行 | 目标合理 |
| 「删 4 份 knowledge.py」 | 只有 cleaner 真用，其余是死 import | 删除更干净 |
| 「工具 agents=[...] 改 phase_tag」 | 19 个工具，已按 agents 过滤 | 见 §4 |
| 「memory 三层重组」 | storage/memory.py 741 行 + knowledge_vector 396 + kb/ + 4 knowledge.py | 见 §6（引用 memory brief）|
| scout 有大量字段推断逻辑 | `_infer_all_semantics` + 字段表构建 ~600 行 | **合并最难的部分**，见 §2.4 |

---

## §1 工作量

| 文件 | 改动 | 类别 |
|---|---|---|
| `hagoku/agents/agent.py`（新建）| +400 行 | 统一 DataAnalystAgent |
| `hagoku/agents/prompt.md`（新建）| +250 行 | 统一 prompt（铁律 10）|
| `hagoku/agents/{scout,cleaner,analyst,reporter}/` | **-3238 行**（删 4 目录）| CO-D7 |
| `hagoku/manager/orchestrator.py` | -400 行 | 退化为客户端管理 + dispatch |
| `hagoku/manager/llm_dispatch/reply_handlers.py` | -250 行 | 4 handler → 1 |
| `hagoku/tools/agent_tool_defs.py` | ±50 行 | agents 字段 → phase_tag |
| `hagoku/memory/`（新建）| +300 行 | 三层重组（memory brief）|
| `hagoku/kb/` + `storage/memory.py` + `storage/knowledge_vector.py` | 迁移/删 | memory brief |
| `hagoku_web/src/` | ±100 行 | 进度条按 phase tag |
| `tests/` | 大改 | §8 |
| **合计净** | **约 -2500 行** | **工期 5-7 天** |

---

## §2 合并策略（核心）

### 2.1 目标形态

```
hagoku/agents/
├── agent.py          ← 新建：DataAnalystAgent（唯一 agent）
├── prompt.md         ← 新建：统一 prompt（4 关注点）
├── base.py           ← 保留（BaseAgent）
├── _interactive.py   ← 评估是否还需要（见 2.5）
├── types.py          ← 保留
└── __init__.py       ← 改：只导出 DataAnalystAgent
```

4 个子目录（scout/cleaner/analyst/reporter）**全删**（CO-D7）。

### 2.2 DataAnalystAgent 骨架

以 analyst（265 行模板）为基础，扩展为统一 agent：

```python
class DataAnalystAgent(BaseAgent):
    """数据分析师 — 唯一 agent。

    一套 chat、一套 prompt、全部工具可见。
    LLM 自己按 4 个关注点（理解字段/评估清洗/跑统计/写报告）切换焦点，
    通过 route_to 声明 phase tag（仅作 UI 进度 + LLM 自参考，不做工具过滤）。
    """

    ROLE = "analyst"  # prompt.md 目录名；保留单一 prompt

    def run_step(self, context: dict, df: pd.DataFrame | None = None, user_input: str = "") -> dict:
        """单步执行：跑 1 轮 LLM，处理 tool_calls。

        与 Phase C 的 analyst.run_step 同构——但工具集是全集，
        prompt 是统一 prompt，phase 来自 context['_current_phase']。
        """
        # 1. messages = project_ctx.to_messages_for_llm(...)
        # 2. tools = 全部工具（不再按 agent 过滤）
        # 3. LLM 调用 → tool dispatch（含 route_to / ask_user / submit_* / run_statistical_test...）
        # 4. add_tool_exchange 写回（方案 B）
        ...

    def infer_field_semantics(self, df, query, memory_project=None) -> list[dict]:
        """字段语义推断 — 从 scout._infer_all_semantics 迁入（见 2.4）。

        这是『理解字段』关注点的特化入口（首轮自动跑）。
        """
        ...
```

### 2.3 4 个 run_step 如何合并

cleaner/analyst/reporter 的 `run_step` 已经同构（`context, df, user_input` → LLM → tool dispatch → `add_tool_exchange`）。合并步骤：

1. 取 analyst.run_step 为基底（最干净）
2. 把 cleaner.run_step 的 `submit_assessment` 处理、reporter.run_step 的 `submit_report` 处理**合进同一个 tool dispatch 循环**
3. tool dispatch 不再按 agent 分支——所有 tool 的 handler 统一注册，LLM 调哪个执行哪个
4. phase 特化逻辑（如 cleaner 的 assess 首轮、analyst 的 first_pass）→ 由 prompt 引导，**不在 code 里分支**

### 2.4 Scout 字段推断的迁移（**最难**）

scout 的 `_infer_all_semantics`（L447，~150 行）是真正的 LLM 调用——推断字段语义。它**不是**简单的 run_step，有特殊的：
- 字段表构建
- memory_project 注入（已确认字段沿用）
- 结构化输出（submit_field_inference tool）

**迁移方案**：

```python
# DataAnalystAgent 内保留为特化方法
def infer_field_semantics(self, df, query, memory_project=None) -> list[dict]:
    # 从 scout._infer_all_semantics 整体迁入
    # 走 to_messages_for_llm + build_messages（Phase B 通道）
    # 仍用 submit_field_inference 结构化 tool
    ...
```

**调用时机**：orchestrator.run() 首轮调 `agent.infer_field_semantics()`（替代当前 `scout.run()`），之后全走 `agent.run_step()`。

> ⚠️ scout 的 `run()` 还有大量字段表构建 / kanban / memory 注入逻辑（L161-251）。这部分**纯通道代码**（构建 prompt 输入、序列化输出）保留，只是搬到统一 agent。**不删任何字段推断能力**。

### 2.5 InteractionMixin 是否保留

调研：`begin()` / `respond()` / `_pause()` / `_done()` 在 Phase C 后，生产路径已经走 `reply_handlers` + `run_step`，**老的 begin/respond 交互链可能已死**。

**CO-D2 时先 grep 确认**：

```bash
rg -n "\.begin\(|\.respond\(" hagoku/ --type py | rg -v "test|reply_handlers|orchestrator"
```

- 若生产代码已不调 agent.begin/respond → InteractionMixin 可删（律的减法）
- 若仍有调用 → 保留，Phase D 不强删

---

## §3 统一 prompt 设计（铁律 10 红线）

### 3.1 这是 Phase D 最危险的部分

4 套 prompt（scout 193 / cleaner 38 / analyst 183 / reporter 293 = 707 行）合并为 1 套。**铁律 10 + 刹车 B 全程适用**：

- ❌ 不许"觉得啰嗦"就精简
- ❌ 不许全文重写
- ✅ 合并 = **保留 4 套的关注点内容，按"关注点"重组**，配 dump 对比

### 3.2 统一 prompt 结构（CO-D1 起草）

```markdown
# 数据分析师

你是一个本地优先的严肃数据分析师。你的工作分 4 个关注点，你自己判断当前在哪个关注点，
用 route_to 声明你转移焦点。

## 关注点 1：理解字段
（从 scout/prompt.md 迁入：字段语义推断、记忆沿用、四大武器）

## 关注点 2：评估清洗
（从 cleaner/prompt.md 迁入：CLEANING_PLAN_RULES、清洗策略、判断原则）

## 关注点 3：跑统计
（从 analyst/prompt.md 迁入：两阶段、方法选择、五大武器）

## 关注点 4：写报告
（从 reporter/prompt.md 迁入：证据溯源、可视化、模板）

## 通用：你如何在关注点之间移动
（route_to 使用——已在 Phase C analyst/cleaner prompt 验证过的教学）
```

### 3.3 起草流程（严格按铁律 10）

1. **保留原文**：4 套 prompt 内容**逐段搬入**对应关注点，不删句子
2. **去重**：4 套都有的「管道体系」「输出规范」「看板交互规范」→ 合并为 1 份通用节（这是去重，不是精简）
3. **dump 对比**：起草后用 `HAGOKU_DUMP_LLM=1` 跑历史 dump 场景，对比合并前后 LLM 行为
4. **commit 引用 dump**（刹车 B）
5. 原 4 套 prompt.md 随 CO-D7 删除前，**git 历史保留**（可追溯）

### 3.4 风险缓解

统一 prompt 比 4 套短的部分（去重的通用节）**必须在 commit message 列出删了哪些重复段**，证明是去重不是精简。任何关注点的**实质指令一句不能少**。

---

## §4 工具可见性改造

### 4.1 当前：按 agents=[...] 过滤

19 个工具，`registry.to_openai(agent)` 按 `agent in t.agents` 过滤。合并后只有 1 个 agent，过滤失去意义。

### 4.2 改造：phase_tag（仅 LLM 参考，不过滤）

brief §3 CO-D3：`agents=[...]` 改为 `phase_tag=[...]`，**全工具对 LLM 可见**，phase_tag 仅作 LLM 自参考。

```python
# 改前
Tool(name="submit_assessment", agents=["cleaner"], ...)

# 改后
Tool(name="submit_assessment", phase_tag=["评估清洗"], ...)
# registry.to_openai() 返回全部工具，phase_tag 写入 description 供 LLM 参考
```

### 4.3 registry 改造

```python
@classmethod
def to_openai(cls, agent: str = None) -> list[dict]:
    """Phase D：返回全部工具（不再过滤）。
    phase_tag 作为 description 的一部分，让 LLM 知道工具的典型使用场景。
    """
    return [_to_openai_with_phase_hint(t) for t in cls._tools.values()]
```

### 4.4 风险

**全工具可见后，LLM 可能在"理解字段"阶段误调"submit_report"**。缓解：
- phase_tag 写进 description（"通常在【写报告】关注点使用"）
- 不做 code 强制过滤（铁律 1：不替 LLM 判断）
- 冒烟观察误调率

---

## §5 orchestrator + reply_handlers 退化

### 5.1 orchestrator（703 → ~250 行）

**删除**：
- 4 agent 实例化（L323-330）→ 1 个 `DataAnalystAgent`
- `_STAGE_HANDLERS` 4 项 → 单一 dispatch
- scout 特化的 run() 调用 → `agent.infer_field_semantics()` + `agent.run_step()`

**保留**：
- LLM 客户端管理
- ProjectContext 持有
- EventBus 桥
- kanban 事件同步（Phase C 已降级）
- WebSocket 接口

### 5.2 reply_handlers（4 handler → 1）

Phase C 后 4 个 handler 已经同构（检查 `_pending_ask_user` / `_*_route_to`）。合并为：

```python
def _handle_reply(self, user_input: str, context: dict) -> tuple:
    """统一回复处理 — 不分 agent。"""
    self._agent.run_step(context, self._df, user_input)

    ask = context.pop("_pending_ask_user", None)
    if ask:
        self._emit(EventType.USER_INPUT_REQUESTED, context["_current_phase"], ask)
        return ("stay", None)

    route = context.pop("_route_to", None)
    if route and route.get("stage"):
        return ("switch", route["stage"], {"reason": route.get("reason", "")})

    return ("stay", None)
```

> `_current_phase` 取代 `_stage`——语义从"哪个 agent"变成"哪个关注点"。

---

## §6 memory 三层重组

完整设计见 [`2026-06-11-memory-three-layer-brief.md`](2026-06-11-memory-three-layer-brief.md)。Phase D 内执行该 brief 的 §3 Phase D 部分（CO-D6.1~D6.6）：

| 子任务 | 操作 |
|---|---|
| CO-D6.1 | 创建 `hagoku/memory/` 骨架 |
| CO-D6.2 | `hagoku/kb/stats/` → `memory/methods/statistics/`；删 business/financial |
| CO-D6.3 | `storage/knowledge_vector.py` → `memory/_vector.py`（改 import）|
| CO-D6.4 | `storage/memory.py` → `memory/projects/_manager.py`（改 import + 迁移脚本）|
| CO-D6.5 | 删 4 份 `agents/*/knowledge.py` |
| CO-D6.6 | 创建 `memory/lessons.jsonl` 骨架 + Lesson schema |

> ⚠️ CO-D6.4 必须含**数据迁移脚本**——用户已有 `~/.hagoku/projects/*/memory.db` 不能丢（memory brief R1）。

> ⚠️ cleaner 是唯一真用 knowledge.py 的——删 `cleaner/knowledge.py` 时，它的 `recall`/`learn` 调用（agent.py L289/447/959/1102）要迁移到新 memory 工具或暂时保留。CO-D6.5 执行时单独处理。

---

## §7 UI 影响

### 7.1 进度条（PipelineBar）

当前按 `agent_started`/`agent_completed` 事件渲染 4 格。Phase D 后只有 1 个 agent——进度按 **phase tag**（route_to 的 stage）渲染。

```typescript
// 改：进度来自 STAGE_TRANSITION 事件的 phase tag
case "stage_transition":
  setCurrentPhase(event.data.stage);  // 理解字段/评估清洗/跑统计/写报告
```

UI 视觉**保持 4 段**（用户视角不变，brief FAQ Q3），底层是 1 个 LLM 切焦点。

### 7.2 kanban / chat / ToolExchangeTurn

- KanbanPanel：不变（Phase C 已降级为显示）
- ToolExchangeTurn（Phase B）：不变
- chat：现在是物理一条（Phase B 已做）

---

## §8 测试改造

### 8.1 受影响测试（调研点 8）

大量测试依赖「4 独立 agent」结构：

| 测试 | 改法 |
|---|---|
| `test_event_driven_channel.py`（断言 `_STAGE_HANDLERS` 4 项）| 改为单 handler 或 phase 列表 |
| `test_stage_handoff.py`（parametrize 3 agent）| 改为单 agent 多 phase |
| `test_cleaner_*` / `test_analyst_*`（实例化具体 agent）| 改为 `DataAnalystAgent` |
| `test_agents.py`（ScoutAgent._infer_all_semantics）| 改为 `DataAnalystAgent.infer_field_semantics` |
| `conftest.py`（mock 3 agent _save_memory）| 改为 1 agent |
| `test_information_arrival.py` | 改 agent 引用 |

### 8.2 测试基线

当前 570。Phase D 删大量 agent-specific 测试 + 加统一 agent 测试。**预期净减**，但**信息到达测试**（`test_information_arrival.py`）和 **doctrine 测试**必须保持绿——它们是架构守门。

---

## §9 真 LLM 冒烟（5 步剧本 + B/C 补验）

### 9.1 剧本（brief §3 CO-D «5 步剧本»）

宿主机跑完整 pipeline，用 `tests/fixtures/smoke_demo.csv`：

| 步 | 场景 | 验证 |
|---|---|---|
| S1 | 首波收敛 | agent 自动推断字段语义，输出字段表 |
| S2 | 工具调用 | LLM 调 get_column_stats / run_statistical_test 等 |
| S3 | 阶段切换 | LLM route_to 在 4 关注点间移动 |
| S4 | 用户挑战 | 用户质疑 → LLM 重新评估（不固执）|
| S5 | 留下/跳转 | 用户说"够了"→ LLM route_to(报告) |

### 9.2 同时补验 B/C 挂账（§-1 风险 A）

| 补验点 | 来源 |
|---|---|
| ask_user 暂停 + 回复继续 | Phase C V3/V4 |
| 跳阶段（理解字段 → 直接报告）| Phase C V5 |
| reporter 关注点 route_to 收尾 | Phase B/C 残留 |
| analyst 多轮 tool（方案 B 协议）| Phase B 残留 |

### 9.3 dump 对比

- 改前基线：`~/.hagoku/llm_dumps.before_phase_d`
- 关键验证：**合并后 chat 是物理一条**（不再是 4 条拼起来）——这是 Phase D 的核心成果
- LLM 看到的信息 ≥ 合并前

---

## §10 律的减法（Phase D 完成后）

| 律 | 状态 |
|---|---|
| 律 3（同阶段多轮记忆）| 自动满足——只有一条 chat |
| 律 9（重推断触发）| 作废——没有"重推断"概念，只有 LLM 继续 |
| 律 8（控制通道律）| 完全作废——1 agent 无跨 agent 控制 |
| InteractionMixin（若死）| 删除 |
| 4 份 knowledge.py | 删除 |
| `_STAGE_HANDLERS` | 删除（单 dispatch）|

这是 Phase F 律的减法的最大一笔。

---

## §11 风险点

| # | 风险 | 概率 | 影响 | 应对 |
|---|---|---|---|---|
| R1 | 统一 prompt 合并导致某关注点行为退化 | **高** | **高** | §3 严格 dump 对比；任何关注点指令不删 |
| R2 | 全工具可见 → LLM 误调跨关注点工具 | 中 | 中 | phase_tag 写 description；冒烟观察 |
| R3 | scout 字段推断迁移丢逻辑 | 中 | 高 | §2.4 整体迁入，不重写 |
| R4 | memory 迁移丢用户数据 | 中 | **高** | CO-D6.4 迁移脚本 + 备份 |
| R5 | 删 4 目录后有残留 import | 中 | 中 | CO-D7 前全仓 grep |
| R6 | 合并后无法定位是 D 引入还是 B/C 残留 | **高** | 高 | §9.2 冒烟同时覆盖 B/C |
| R7 | cleaner knowledge.py 删除断 recall/learn | 中 | 中 | CO-D6.5 单独迁移 cleaner 调用 |
| R8 | 测试大改引入回归 | 中 | 中 | doctrine + information_arrival 必须绿 |
| R9 | 不可逆——删目录后发现问题 | 低 | **极高** | CO-D7 最后做；前面全绿才删 |

---

## §12 CO-D 任务执行顺序

⚠️ **每步动手前报告审核方**（铁律 -2）。Phase D 风险最高，**每个 CO-D 都是审批门**，不是只有一个。

### CO-D0：预备
- 备份 `~/.hagoku/llm_dumps` → `before_phase_d`
- 备份 `~/.hagoku/projects/` → `before_phase_d`（用户数据！）
- 确认 570 tests 绿

### CO-D1：统一 prompt 起草（铁律 10）
- 新建 `hagoku/agents/prompt.md`，4 关注点合并
- dump 对比改前/改后
- **审批门**：审核方检视 prompt 合并是否丢指令

### CO-D2：DataAnalystAgent 骨架
- 新建 `hagoku/agents/agent.py`
- 以 analyst.run_step 为基底，合并 cleaner/reporter tool dispatch
- grep 确认 InteractionMixin 是否可删
- **审批门**

### CO-D3：scout 字段推断迁移
- `infer_field_semantics` 迁入
- orchestrator.run 首轮改调统一 agent
- **审批门** + 真 LLM 验字段推断不退化

### CO-D4：工具可见性改造
- agents=[] → phase_tag
- registry.to_openai 返回全集

### CO-D5：orchestrator + reply_handlers 退化
- 4 handler → 1
- orchestrator 删 4 agent 实例化
- **审批门**

### CO-D6：memory 三层重组（memory brief）
- 含迁移脚本 + 数据备份验证
- **审批门**（用户数据风险）

### CO-D7：删 4 目录 + 测试改造（**最不可逆**）
- 全仓 grep 确认无残留 import
- 删 scout/cleaner/analyst/reporter 4 目录
- 测试全改
- **审批门** + 全套真 LLM 冒烟 §9 全过才能删

### CO-D8：真 LLM 冒烟 §9（5 步 + B/C 补验）
- 宿主机完整 pipeline
- dump 对比：chat 物理一条

---

## §13 终审清单

```markdown
# Phase D 完成汇报

## 改动统计
- 净代码减少：__ 行（预期 ~2500）
- 删目录：scout/cleaner/analyst/reporter（4）
- 新建：agent.py + prompt.md + memory/

## grep 验证（应全 0）
- from hagoku.agents.scout|cleaner|analyst|reporter: __
- from hagoku.kb: __
- _STAGE_HANDLERS: __
- 4 份 knowledge.py: __

## 测试
pytest tests/ → __ passed
- doctrine 测试：绿
- information_arrival 测试：绿

## 真 LLM 冒烟（§9）
- S1-S5 五步：__
- B/C 补验（ask_user/跳阶段/reporter收尾/方案B协议）：__
- chat 物理一条：__
- dump 对比 LLM 信息不减：__

## memory 迁移
- 用户 projects 数据完整：__
- 迁移脚本 + 备份：__

## 律的减法
- 律 3/8/9 作废：✓
- InteractionMixin/_STAGE_HANDLERS/4 knowledge.py 删除：✓

## commit 哈希（CO-D1~D8）
...

## 风险残留
...
```

---

## §14 不做什么

- ❌ 不动统计护栏 / 工具实现（brief 红线 L7）
- ❌ 不动 ProjectContext 核心结构（Phase B 已升级）
- ❌ 不动 Meta 层基建（brief 红线 L4；Phase D 完成后才启动 v2）
- ❌ 不精简 prompt 实质指令（铁律 10）
- ❌ 不删用户数据（CO-D6 必须迁移 + 备份）
- ❌ 不在冒烟全过前删 4 目录（CO-D7 最后做）

---

## §15 硬规则

1. **每个 CO-D（D1~D7）动手前都要报告审核方**——Phase D 风险最高，全程审批门
2. 任何回滚不许 `git revert`（铁律 -1）——尤其 CO-D7 删目录前必须确认全绿
3. prompt 合并必须配 dump 对比（铁律 10 + 刹车 B）
4. 用户数据迁移必须备份 + 验证（CO-D6）
5. 删 4 目录（CO-D7）前必须真 LLM 冒烟 §9 全过
6. 任何"我觉得"判断不算数——dump/grep/测试做证据
7. 全套测试 FAIL → 停下贴 stderr

---

## §16 完成标准

Phase D **完成** ≡ 同时满足：

- [ ] CO-D1~D8 全部 commit
- [ ] 4 子目录删干净，grep 无残留 import
- [ ] 1 个 DataAnalystAgent + 1 套 prompt
- [ ] memory 三层重组完成，用户数据完整
- [ ] §9 真 LLM 冒烟 5 步 + B/C 补验全过
- [ ] chat dump 物理一条（核心成果验证）
- [ ] doctrine + information_arrival 测试绿
- [ ] 律的减法清单（律 3/8/9 作废）
- [ ] 风险残留经审核方接受

Phase D 完成后 → Phase E（工具箱 + memory 工具化 + Meta v2）+ Phase F（律的减法清账）。
