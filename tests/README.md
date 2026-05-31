# HaGoKu 测试金字塔

> 本目录测试分层职责说明。新增测试前先读本文件——决定加到哪一层。
> 提交前必跑：`pytest tests/test_doctrine_compliance.py tests/test_product/test_information_arrival.py`

---

## 测试分层

```
                ┌────────────────────────────────┐
                │  L5: 真实 LLM 端到端           │  test_field_llm_e2e.py
                │  （依赖 localhost LLM 服务）   │  test_direct_llm_dialog*.py
                └────────────────────────────────┘
                ┌────────────────────────────────┐
                │  L4: 产品级正向契约            │  tests/test_product/
                │  （信息抵达、Agent 交互契约）  │
                └────────────────────────────────┘
                ┌────────────────────────────────┐
                │  L3: Pipeline / 失败路径       │  tests/test_pipeline/
                └────────────────────────────────┘
                ┌────────────────────────────────┐
                │  L2: 模块单元                  │  tests/test_agents/
                │  （Agent / Manager / Tool）    │  tests/test_manager/
                │                                │  tests/test_tools/
                │                                │  tests/test_storage/
                │                                │  tests/test_observability/
                │                                │  tests/test_guardrails/
                │                                │  tests/test_api/
                │                                │  tests/test_llm/
                └────────────────────────────────┘
                ┌────────────────────────────────┐
                │  L1: Doctrine 合规             │  test_doctrine_compliance.py
                │  （静态守门：禁止硬编码）      │
                └────────────────────────────────┘
```

---

## 各层职责与守则

### L1：Doctrine 合规（机器化哲学守门）

**文件**：`test_doctrine_compliance.py`

**职责**：把 PROJECT.md 的「零硬编码原则」变成机器可执行的断言。7 条守门：业务关键词列表 / 中文语义正则 / 中文 if-elif 链 / 伪 LLM 函数 / except 静默吞 + 2 条元测试。

**何时跑**：每次 PR 提交前必跑。**红 = 拒**。

**何时新增**：

- 发现新的硬编码伪装模式（在 4 类之外）
- 守门 5 历史债务清理后，从 `_KNOWN_LLM_EXCEPT_VIOLATIONS` 移除一行的同时

**禁止**：用 `xfail` 标记 doctrine 测试——历史债务必须显式入白名单（详见 [ADR-004](../docs/decisions/ADR-004-known-llm-except-violations-whitelist.md)）。

---

### L2：模块单元（Mock 一切外部依赖）

**目录**：`test_agents/` `test_manager/` `test_tools/` `test_storage/` `test_observability/` `test_guardrails/` `test_api/` `test_llm/`

**职责**：单一函数 / 单一类的契约测试。依赖 mock，不起服务、不发网络。

**何时跑**：开发循环中频繁跑（秒级反馈）。

**何时新增**：

- 新增公共函数 / 类
- 修复 bug 时配套写一条「复现 → 修复后转绿」的回归测试
- ProjectContext 类似的新模块上线时配套（如 `tests/test_context/`）

**禁止**：

- 在 L2 测试里写真实 LLM 调用（应进 L5）
- 在 L2 测试里跨 Agent 拼装（应进 L4）

---

### L3：Pipeline / 失败路径

**目录**：`tests/test_pipeline/`

**职责**：

- 端到端 pipeline 在不同 mock 场景下的行为（`test_pipeline.py`）
- 失败路径不降级、不兜底（`test_failure_path.py` 12 条）

**何时跑**：CI 全量跑；本地开发改动 Manager / orchestrator 时跑。

**何时新增**：

- 新增 pipeline 阶段（如插入新的 Agent）
- 新增「全局失败路径」（应触发 RUN_FAILED 不降级）

**禁止**：

- 在 L3 测试里加「降级合理性」断言——降级路径根本不应存在（铁律 2）

---

### L4：产品级正向契约（律 6 落地）

**目录**：`tests/test_product/`

**职责**：通道完备性十律的正向断言：

| 文件 | 守护 |
|------|------|
| `test_information_arrival.py` | 律 1（意图穿透）、律 2（原话抵达）、律 3（多轮历史）、律 4（工具表达通路）、律 7（未理解信号） |
| `test_agent_interaction_contract.py` | Agent 交互契约（用户原话送达 LLM 的 mock 录回） |
| `test_interaction_scenarios.py` | 多轮交互典型场景 |
| `test_scout_uia_prompt.py` | Scout used_in_analysis 决策路径 |

**何时跑**：每次 PR 提交前必跑（与 L1 一同）。

**何时新增**：

- 每发现一个真实失效案例（参见 `docs/cases/`）必须在此补一条守护测试
- 新增 LLM 工具时配套断言「LLM 听到 → 工具调到 → 状态写入」三段链路

**禁止**：

- 在 L4 测试里关心代码实现细节——只关心「信息是否抵达 LLM」「LLM 输出是否落地」

---

### L5：真实 LLM 端到端

**文件**：`test_field_llm_e2e.py`、`test_direct_llm_dialog*.py`、`test_trace_production_path.py`、`test_uia_experiment_round2.py`、`test_used_in_analysis_experiment.py`

**职责**：依赖真实 LLM 服务（`localhost:8080`），验证：

- mock 测试「**如果** LLM 这样调，代码处理对**」**
- L5 测试「**LLM 是否真的会这样调**」

**何时跑**：

- 重大 LLM prompt / 工具 schema 变更后
- 上线前
- 不进 CI（依赖外部服务）

**何时新增**：

- 引入新工具时配真实 LLM 验证（如 ADR-001 的 `restrict_analysis_to` 仍待真实 LLM 验证）
- 真实 LLM 抓到的失败必须复现为 L5 测试，再由 L4 mock 守护

---

## 测试新增决策树

```
新增测试需要写在哪一层？

是检查代码是否含硬编码模式吗？
    是 → L1 (test_doctrine_compliance.py)
    否 → 继续

是单一函数 / 类的契约吗？
    是 → L2 (对应 test_<module>/)
    否 → 继续

是 pipeline 跨 Agent / 失败路径吗？
    是 → L3 (test_pipeline/)
    否 → 继续

是「用户原话 / 意图 / 反馈是否抵达 LLM」吗？
    是 → L4 (test_product/test_information_arrival.py 或同目录)
    否 → 继续

是依赖真实 LLM 调用的吗？
    是 → L5 (test_field_llm_e2e.py 等)
    否 → 重新审视——要么不该写，要么是新维度需要新分层
```

---

## 提交前测试清单

```bash
# 强制（每次必跑）
.venv/bin/python -m pytest tests/test_doctrine_compliance.py -q                # L1
.venv/bin/python -m pytest tests/test_product/test_information_arrival.py -q   # L4 核心

# 推荐（改动 Agent / orchestrator 时）
.venv/bin/python -m pytest tests/test_product/ -q                              # L4 全量
.venv/bin/python -m pytest tests/test_pipeline/ -q                             # L3

# 全量
.venv/bin/python -m pytest --tb=short -q --ignore=tests/test_field_llm_e2e.py  # 跳过 L5 真实 LLM
```

---

## 反模式（不要做）

- ❌ 在 L1 测试里加业务逻辑断言
- ❌ 在 L4 测试里检查代码实现细节（应只检查信息抵达）
- ❌ 在任何 mock 测试中模拟 LLM 总是返回成功（必须包含失败路径 mock）
- ❌ 删除 / 弱化测试以让 PR 转绿（违反 testing discipline）
- ❌ 用 `pytest.skip` 跳过失败测试不留 issue（应在 plan 文件中记录修复路线）

---

## 相关文档

- [PROJECT.md §「通道完备性十律」](../PROJECT.md) — 测试守护的契约源头
- [PROJECT.md §「防退化机制」](../PROJECT.md) — 四重刹车（L1 是刹车 1，L4 是刹车 4）
- [docs/decisions/ADR-003](../docs/decisions/ADR-003-doctrine-compliance-test.md) — L1 设立决策
- [docs/decisions/ADR-004](../docs/decisions/ADR-004-known-llm-except-violations-whitelist.md) — L1 白名单管理
- [docs/cases/](../docs/cases/) — L4 测试的真实场景源头
