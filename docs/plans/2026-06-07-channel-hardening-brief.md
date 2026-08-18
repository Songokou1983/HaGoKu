# 通道收口修复 Brief（2026-06-07）

> **文档定位**：本文件由架构审核方（Cascade）出具，交付给实施 AI（Claude / Codex / 其它）执行代码修复。实施方按本 brief 顺序推进，每完成一项提交一次，由架构审核方逐项验收。
>
> **不是**：新功能规格、架构再造、推翻现有通道。
> **是**：在已成型的通道脊梁上做收口——堵铁律 7 复辟点、合并冗余观察通道、拆 2500 行编排器、补律 4/律 8 的契约盲区、清理环境腐烂。

---

## 0. 角色与边界（实施方必读）

| 角色 | 谁 | 权限 |
|------|---|------|
| **架构审核方** | Cascade（本文档作者） | 出 brief / 验收 / 拒绝 / 退回返工。不写代码。 |
| **实施方** | 接到此 brief 的 AI（或人类工程师） | 按顺序执行任务 1→N。**每个任务独立 commit**，跨任务不混改。 |
| **用户** | 项目所有者 | 最终批准。铁律 -2 适用：实施方在动 `edit_file` 前必须用户说"修/改/做"才能动。 |

### 不可越界事项

1. **不许做未列入本 brief 的"顺手优化"**（CLAUDE.md §Karpathy 编码原则 3）。看到旁边丑代码忍住。
2. **不许 `git revert` / `git reset`**（铁律 -1）。修复只能前向。
3. **不许把问题推给 LLM / 浏览器 / 网络**（铁律 -3）。先读 dump / 日志。
4. **不许在已知 dump 没读完前加新日志**（铁律 -4）。
5. **每个任务的 PR/commit 必须跑过自检三组**（铁律 3）：
   ```bash
   .venv/bin/python -m pytest tests/test_doctrine_compliance.py -q
   .venv/bin/python -m pytest tests/test_product/test_information_arrival.py -q
   .venv/bin/python -m pytest --tb=short -q
   ```
6. **每个任务的 commit message 必须以 `[CH-N]` 开头**（N = 任务编号），方便审核方按编号追溯。

---

## 1. 当前审计结论（背景）

通道脊梁已成型（详见 2026-06-07 全面评估对话）：

- 信息通道 `ProjectContext.build_prompt` + 控制通道 `agent_tools.dispatch(tool_calls)` 二分清晰
- 铁律 0/-1/-2/-3/-4 + 1-9 全部成文，并有 `test_doctrine_compliance.py` / `test_information_arrival.py` 守门
- 工具单一注册表（16 个工具，按 `agents=[...]` 路由）
- 配置中性律落地干净

**但通道收口未完成**——存在以下残留：

| 类别 | 数量 | 严重度 |
|------|------|--------|
| 铁律 7（失败在场）复辟点 | 3 处 | 🔴 高 |
| 平行观察通道（无单源） | 4 套 | 🟡 中 |
| 单文件复杂度爆表（>2000 行） | 1 处 | 🟡 中 |
| 律 4 / 律 8 契约盲区 | 2 项 | 🟡 中 |
| 环境腐烂（备份文件入仓 / 实验脚本误置 / 全局副作用） | 5 类 | 🟢 低但累积危险 |

本 brief 用 7 个有序任务收口这些残留。

---

## 2. 任务清单（按优先级 + 依赖顺序）

> 任务结构统一：**根因 → 改动范围 → 验收标准 → 红线**。
> 实施方读完每条的"红线"就知道哪些写法会被审核打回。

---

### CH-1 修复 `Analyst.run()` 的 `except → _done` 兜底（🔴 铁律 7）

**根因**
`@HaGoKu/hagoku/agents/analyst/agent.py:448-450` 的 `except Exception: return self._done(...)` 把通道层异常吞掉、向下游 Reporter 输出"已完成"假信号。违反铁律 7 路径 1（LLM 异常应 `raise RuntimeError`）。

**改动范围**
- 仅 `hagoku/agents/analyst/agent.py:406-450` `begin()` 方法。
- `except Exception as e:` 段改为 `raise RuntimeError(f"Analyst 通道失败：{e}") from e`。
- `self._emit(EventType.AGENT_FAILED, ...)` 在 raise 之前保留（用户可见性）。

**验收标准**
1. 跑 `pytest tests/test_doctrine_compliance.py -q` 全绿
2. 跑 `pytest tests/test_agents/ -q` 全绿
3. 手工 grep：`grep -n "except Exception" hagoku/agents/analyst/agent.py` 输出应仅有 `_json.JSONDecodeError` 这类**纯解析异常**，不再有捕获 LLM 调用异常并返回 done 的路径
4. 不允许新增任何 `_done("done", f"...失败...", ...)` 形式的"假装完成"

**红线**
- 不许"为了让测试绿"改测试断言。测试不绿 → 测试是对的，代码有问题。
- 不许把 raise 改成"先 emit AGENT_FAILED 再返回 None"——返回 None 同样是兜底。
- 此任务**不涉及** `run()` 与 `run_step()` 合并（那是 CH-3 的事）。Surgical changes。

---

### CH-2 删除/收紧 `DataAgentBase.call_llm` 的静默失败（🔴 铁律 7 + 死代码）

**根因**
`@HaGoKu/hagoku/agents/base.py:174-182` 的 `call_llm` 在 LLM 异常时 `return ""`。虽然当前 4 个 Agent 均未继承 `DataAgentBase`（实际为死代码），但它仍位于 `tests/test_doctrine_compliance.py` 的扫描路径上，是"潜伏复辟点"——新 Agent 一旦继承就立刻违规。

**改动范围**

二选一（实施方按调研结论选）：

**方案 A（推荐）**：彻底删除 `DataAgentBase`。
- 前置调研：`grep -rn "DataAgentBase\|from .base\|from ..base\|from ...base" hagoku/ tests/`
- 若无外部引用 → 整文件删除 `hagoku/agents/base.py`
- 同步清理 `hagoku/agents/__init__.py` 的相关导出

**方案 B**：保留但去毒。
- 删 `call_llm` 的 `try/except`，让异常自然抛出
- 删 `ask_llm` 的 `try/except TypeError` fallback（这条 fallback 隐藏了 instructor 客户端协议差异，是 future bug 温床）
- 在 `DataAgentBase` 顶部加 docstring：`"此基类禁止用于 LLM 通道调用，仅供事件/状态托管。LLM 调用请直接用 tools.registry + create_*_client。"`

**验收标准**
1. `grep -rn "except.*return.*\"\"" hagoku/agents/` 输出空
2. `pytest tests/ -q` 全绿
3. 提交时附 commit message 注明选择了 A 还是 B 以及理由

**红线**
- 不许保留"emit_thinking + return 默认值"任何变种
- 不许把 fallback 改成 `return None` 当借口

---

### CH-3 修复 `ProjectContext._on_event` 的静默降级（🔴 律 7 通道自身）

**根因**
`@HaGoKu/hagoku/context/project_context.py:256-260` 在 `_context_ref is None` 时 `logging.warning + ctx = {}` 继续。律 7 明确：「`logging.warning` 只对开发者可见，不算履行义务」。**信息通道的载体丢失**是通道断裂，不是降级。

**改动范围**
- `project_context.py:256-275`（含 `AGENT_COMPLETED` 和 `USER_INPUT_RECEIVED` 两个分支）
- `_context_ref is None` 时改为 `raise RuntimeError("ProjectContext._context_ref 未设置，信息通道断裂")`
- 上游 `orchestrator.py:1671` 已经在 subscribe 时传入 context_ref，正常路径不受影响

**验收标准**
1. 单元测试：构造一个未 set_context_ref 就发事件的场景，断言 raise
2. `pytest tests/test_context/ -q` 全绿
3. `pytest tests/test_observability/ -q` 全绿

**红线**
- 不许把 raise 包成 try/except 在 EventBus 那一层吞掉
- 注意 `EventBus.emit` 的 subscriber callback 异常处理（`@HaGoKu/hagoku/observability/event_bus.py:36-39`）——它 `logger.warning` 吞了。这次**不要顺手改 EventBus**（surgical），但要在 commit message 里 flag 这是后续 CH-X 候选

---

### CH-4 观察通道四合一：合并 `ChannelLogger` 进 `llm_dump`（🟡 单源）

**根因**
4 套并行观察通道（`EventBus.save_to_file` / `ProjectContext` JSONL / `ChannelLogger` / `llm_dump`）。其中 `ChannelLogger.log_llm` 和 `llm_dump.dump_messages` 职责重叠——都是 LLM 调用的录制。

**职责重排目标**

| 通道 | 唯一职责 |
|------|----------|
| `EventBus` | 事件流（AGENT_STARTED / TOOL_CALLED 等） |
| `ProjectContext` | 上下文重建（供 `build_prompt`） |
| `llm_dump` | **LLM 调用现场**（messages + tool_calls + response）唯一权威 |
| `ChannelLogger.log` / `trace_value` | 字段决策溯源（保留），但 `log_llm` 删除 |

**改动范围**
1. `hagoku/observability/channel_logger.py`：删除 `log_llm` 方法及其字段
2. `hagoku/observability/llm_dump.py`：
   - 把环境变量闸门 `HAGOKU_DUMP_LLM=1` 改为默认开启（每个 run 一份 dump 写到 `run_dir/llm_dumps/`，与 `events.jsonl` 同目录）
   - 保留环境变量但语义反转：`HAGOKU_DUMP_LLM=0` 才关闭
   - **rationale**：铁律 0「先查 dump」与默认不写 dump 是矛盾的，必须默认开
3. 全 repo 替换 `ChannelLogger.log_llm` 调用点为 `llm_dump.dump_messages`：
   ```bash
   grep -rn "log_llm(" hagoku/
   ```

**验收标准**
1. `grep -rn "log_llm" hagoku/` 输出空
2. 默认运行一次 pipeline，`run_dir/llm_dumps/` 下有文件
3. `pytest tests/test_observability/ -q` 全绿（必要时同步更新测试）

**红线**
- 不许把 `ChannelLogger` 整个删掉——`trace_value` 仍是字段决策溯源单源
- 不许动 `EventBus` 和 `ProjectContext`（这俩不在本任务范围）

---

### CH-5 拆分 `orchestrator.py`（🟡 复杂度）

**根因**
`@HaGoKu/hagoku/manager/orchestrator.py` 2507 行，承担 ≥6 项职责（pipeline / kanban / payload 渲染 / LLM 调度 / 命令路由 / guardrails）。

**改动范围**

新建子模块，**只搬代码不改逻辑**：

```
hagoku/manager/
├── orchestrator.py            # 仅保留 Orchestrator 类主壳 + pipeline 主循环
├── payloads/
│   ├── __init__.py
│   ├── scout_payload.py       # 搬 scout_field_review_pause_payload 及 _scout_* 辅助
│   └── cleaner_payload.py     # 同上
├── llm_dispatch/
│   ├── __init__.py
│   ├── plan_generation.py     # 搬 _call_llm_for_plan
│   ├── confirmation.py        # 搬 _llm_classify_confirmation
│   └── scout_reply.py         # 搬 _apply_scout_reply_with_llm 及配套
└── command_parser.py          # 已有
```

**目标**：拆完后 `orchestrator.py` ≤ 800 行。

**验收标准**
1. `wc -l hagoku/manager/orchestrator.py` ≤ 800
2. 所有测试不修改断言、不修改 mock 路径前提下保持绿（`pytest -q`）
3. 用 `git log --stat` 或 `git diff --stat HEAD~1` 证明**没有新增逻辑**——只是 move + import 调整

**红线**
- 不许"顺手改重命名变量"
- 不许借机修 bug——若搬代码时发现 bug，单独开 issue/任务，不在此 commit 解决
- import 调整必须保持公共 API 不变（外部测试不动）

---

### CH-6 补律 4 + 律 8 的契约（🟡 防退化）

**律 4（工具 schema 覆盖完备）契约**

新建 `tests/test_product/test_tool_schema_coverage.py`：

对每个阶段（scout/cleaner/analyst/reporter），列出 **N 条用户可能的纠正措辞**（每阶段 ≥ 8 条），断言每条措辞所对应的状态变更维度都能在 `agent_tools.to_openai(agent)` 中找到落点（落点 = 至少一个工具的 parameters 字段名匹配该维度）。

示例骨架：

```python
SCOUT_USER_INTENTS = [
    ("把 Code 改成中文名 '店铺编号'", {"tool": "update_field_understanding", "param": "display_name"}),
    ("Inc1 是目标变量", {"tool": "update_field_role", "param": "suggested_role"}),
    ("只用 Inc1 Inc2 Inc3 三列分析", {"tool": "restrict_analysis_to", "param": "columns"}),
    # ... ≥ 5 more
]

def test_scout_tool_schema_covers_user_intents():
    tools = {t["function"]["name"]: t for t in agent_tools.to_openai("scout")}
    for utterance, expected in SCOUT_USER_INTENTS:
        tool = tools.get(expected["tool"])
        assert tool, f"工具 {expected['tool']} 不存在，律 4 残缺: {utterance}"
        params = tool["function"]["parameters"]["properties"]
        assert expected["param"] in params, ...
```

**律 8（控制通道）契约**

新建 `tests/test_product/test_control_channel.py`：

断言每个 Agent 的工具集中至少有一个控制类工具（`done_with_*` / `request_*` / `route_*`），允许 LLM 主动表达"本阶段完成 / 请求更多输入 / 跳转"。

**如果当前没有任何控制工具**——这条契约会立刻红。**这就是律 8 的盲区暴露**。在此情形下：
- 测试保留为 `@pytest.mark.xfail(strict=True, reason="律 8 控制工具尚未实现")`
- commit message 说明：「契约就位 + 标记 xfail，待后续 CH-X 补控制工具」

**验收标准**
1. 两个新测试文件存在
2. `test_tool_schema_coverage.py` 全绿
3. `test_control_channel.py` 要么全绿、要么严格 xfail（不允许 skip）

**红线**
- 不许把契约写得很宽以让它通过（"任一工具存在" 不算覆盖）
- 不许为了让律 8 绿就硬塞一个空控制工具——补工具是另一个任务

---

### CH-7 环境清理（🟢 累积危险）

**改动范围**

| 子任务 | 操作 |
|--------|------|
| 7a | `git rm --cached UI_CHANGELOG_backup_*.tsx UI_CHANGELOG_backup_*.py hagoku/agents/scout/UI_CHANGELOG_backup_*.py`（已被 .gitignore 但已入仓的文件移出） |
| 7b | 删除 `hagoku/agents/reporter.py`（219 字节 stub），其引用合并到 `hagoku/agents/reporter/__init__.py` |
| 7c | 把 `tests/direct_llm_dialog*.py` / `tests/uia_experiment_round2.py` / `tests/used_in_analysis_experiment.py` 移到 `scripts/experiments/` |
| 7d | `hagoku/agents/scout/knowledge.yaml`（696KB）audit：跑 `python -c "import yaml; d=yaml.safe_load(open('hagoku/agents/scout/knowledge.yaml')); print(len(d), list(d.keys())[:5])"`，若发现字段名沉淀（PROJECT.md §字段理解归属禁止），提 issue 但**本任务不修复**——单独 brief 处理 |
| 7e | `hagoku/llm/client.py:24-35` `_clear_proxy_env`：改为 per-client httpx transport，不再永久污染进程级环境变量 |

**验收标准**
- 7a-7c：`git status` 干净，`pytest -q` 全绿
- 7d：commit 附 audit 输出（仅 print 结果，不改 yaml）
- 7e：`grep -n "os.environ.pop" hagoku/llm/client.py` 输出空；嵌入 IDE 场景手工冒烟测试一次

**红线**
- 7d 发现污染时**不在此任务里清理 yaml**——会变成隐性大改
- 7e 不许把代理设置写死或硬编码

---

## 3. 全局红线汇总（每个任务都适用）

| # | 红线 | 对应铁律 |
|---|------|---------|
| G1 | 不许 `git revert` / `git reset` | -1 |
| G2 | 动代码前必须用户说"修/改/做" | -2 |
| G3 | 不许把问题推给 LLM / 浏览器 / 网络 | -3 |
| G4 | 不许在 dump 没读完时加新日志 | -4 |
| G5 | 不许 `except: return ""/None/default` | 7 |
| G6 | 不许 `@lru_cache / @cache` 装饰 LLM 调用 | 6 |
| G7 | 不许写中文关键词列表 / `if intent == "..."` 链 | 1 |
| G8 | 不许在文档/输出/记忆里出现具体模型名 / URL | 9 |
| G9 | 不许"顺手优化"未列入本 brief 的代码 | Karpathy 3 |
| G10 | 每 commit 必须跑过自检三组 | 3 |

---

## 4. 审核方验收清单（架构审核方自用）

每收到一个任务的 commit，按下表打勾：

```
CH-N 验收
[ ] commit message 以 [CH-N] 开头
[ ] diff 范围与本 brief 列出的"改动范围"一致（无越界）
[ ] 自检三组测试输出已附在 PR 描述/commit body
[ ] 红线逐条检查无违反
[ ] 任务的"验收标准"逐条满足
[ ] grep 检查命令的输出已附（如适用）
```

**任一项未通过 → 退回返工，不接受"小问题下次改"。**

---

## 5. 提交格式约定

每个任务一个 commit（或一个 PR），message 模板：

```
[CH-N] <一句话描述>

根因：<引用本 brief 哪一条>
改动：<文件 + 行号范围>
验收：
- pytest tests/test_doctrine_compliance.py -q  → <结果>
- pytest tests/test_product/test_information_arrival.py -q  → <结果>
- pytest -q  → <结果>
- <任务特定的 grep / 行数验证>

未越界声明：本 commit 未改动 brief 列出范围之外的文件。
```

---

## 6. 任务依赖与建议顺序

```
CH-1 (Analyst.run 兜底)     ─┐
CH-2 (base.py 死代码)        │  独立，可并行
CH-3 (ProjectContext)       ─┘
                ↓
CH-4 (观察通道四合一)        ← 依赖 CH-3（避免互相打架）
                ↓
CH-5 (orchestrator 拆分)    ← 依赖 CH-4（dump 默认开后再拆才能验证日志不丢）
                ↓
CH-6 (律 4/8 契约)          ← 独立，但建议放在拆分后跑
                ↓
CH-7 (环境清理)              ← 最后做，避免和上面 diff 混淆
```

**建议节奏**：每天 1-2 个任务，全部 7 个任务 1 周内收口。

---

## 7. 何时回到架构审核方

实施方遇到下列情况**必须停下来询问**，不许自己拍板：

1. 发现本 brief 描述与代码现状不符（例如行号对不上）
2. 修复后某个测试无法绿（怀疑测试本身要改）
3. 发现额外的铁律 7 复辟点（不在本 brief 7 条范围内）
4. 用户要求"顺便也修一下 X"，但 X 不在本 brief 范围
5. 任务依赖关系实际上需要调整

询问通道：直接在对话里 @ 架构审核方，附上证据（dump 文件名 / 测试输出 / grep 结果）。**铁律 -3 适用：不准凭感觉归因。**

---

**Brief 出具时间**：2026-06-07
**Brief 出具方**：Cascade（架构审核方）
**预计完成**：2026-06-14
**下一次评估**：全部 7 任务收口后，重跑「通道完备性十律对照体检」，确认所有 ✅，再讨论下一阶段架构议题。
