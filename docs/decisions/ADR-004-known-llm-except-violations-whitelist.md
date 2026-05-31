# ADR-004：历史债务白名单 `_KNOWN_LLM_EXCEPT_VIOLATIONS`

- **日期**：2026-05-28
- **状态**：⏳ 5 处待清理（白名单生效中）
- **相关律 / 铁律**：铁律 2（LLM 失败的唯一合法路径）、ADR-003 的配套机制

## 背景

[ADR-003](ADR-003-doctrine-compliance-test.md) 上线 doctrine 守门测试时，守门 5（LLM 调用 except 块不得静默吞）扫出了 **5 处真实违规**：

```
agents/analyst/agent.py::_plan_analysis_via_llm:886    # LLM 失败回退机械序列
agents/analyst/agent.py::_plan_analysis_via_llm:911    # JSON 解析失败回退
manager/orchestrator.py::_call_llm_for_plan:2889       # LLM 失败 return None
manager/orchestrator.py::_try_generate_phase_llm:3074  # 同上
manager/orchestrator.py::_llm_understand_field_update:3382  # 同上
```

**这 5 处就是项目所有者报告的「死循环」的实证**——AI 实现者在 LLM 失败时偷偷加的兜底。

如果 CI 直接红，会阻塞所有 PR，反而逼得新 AI 实现者去「让它绿」（最快路径仍然是规则）；如果默认豁免，下个 AI 看到守门 5 没事就开始模仿。

需要一个折中：**让违规可见、不阻塞，但永远不忘记需要清理**。

## 决策

在 `tests/test_doctrine_compliance.py` 中维护一个**显式的历史债务白名单**：

```python
_KNOWN_LLM_EXCEPT_VIOLATIONS: set[str] = {
    "agents/analyst/agent.py::_plan_analysis_via_llm:886",
    "agents/analyst/agent.py::_plan_analysis_via_llm:911",
    "manager/orchestrator.py::_call_llm_for_plan:2889",
    "manager/orchestrator.py::_try_generate_phase_llm:3074",
    "manager/orchestrator.py::_llm_understand_field_update:3382",
}
```

守门 5 的逻辑：

1. 扫所有 LLM 调用 except 块
2. 若 except 块直接 return 空值 → 视为违规
3. 若违规 key (`{file}::{func}:{line}`) 在白名单中 → 跳过（豁免）
4. 否则报错

**清理路线**：[`docs/plans/doctrine-violations-cleanup.md`](../plans/doctrine-violations-cleanup.md) 详述每处的修复指引。每修一处从白名单移除一行，最终清空。

## 替代方案

| 方案 | 否决理由 |
|------|---------|
| 上线即强制全绿（不要白名单） | 阻塞所有 PR；逼 AI 走旁门左道 |
| 用 `@pytest.xfail` 标记守门 5 | 函数级 xfail，新增违规也会被吃掉，遮蔽未来违规 |
| 把 5 处违规直接修复后才上线守门 | 修复涉及 Manager / Analyst 的失败路径重设计，是独立大工程；不该阻塞守门上线 |
| 把违规写在 git commit message 而非测试代码 | 不可执行，会被遗忘；不在 PR 视野内 |

## 后果

**正面**：

- 历史违规集中可见，永远在测试报告里晒着
- 新增违规立即被拦截（不在白名单 → 红）
- 修复路线明确，每处都有 ADR 级的归档
- 设立了「历史债务可豁免但必须显式」的工程模式，未来其他守门可复用

**负面 / 待办**：

- 5 处违规未修，即代码仍存在「LLM 失败 → 静默兜底」的真实路径
- 用户看不到这些 LLM 失败（因为静默走了机械序列），潜在 UX 漏水
- 白名单文件名 / 行号若文件被重排会失效，需要修测试中的 key（建议偶尔跑 `pytest tests/test_doctrine_compliance.py` 验证白名单仍准）

**影响范围**：

- `tests/test_doctrine_compliance.py:310-316`（白名单定义）
- `tests/test_doctrine_compliance.py:370-374`（豁免逻辑）
- `docs/plans/doctrine-violations-cleanup.md`（清理路线）

## 引用

- 上游 ADR：[ADR-003](ADR-003-doctrine-compliance-test.md)
- 清理 plan：`docs/plans/doctrine-violations-cleanup.md`
- 修复后的检查清单（每修一处必做）：
  1. 改 `except` 为 `raise RuntimeError(...)` 或写 `_last_understanding_failure`
  2. 调用方相应处理
  3. 跑 `pytest tests/` 无回归
  4. 从白名单移除该条
  5. 跑 `pytest tests/test_doctrine_compliance.py` 仍绿
