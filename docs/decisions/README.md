# 架构决策日志（ADR）

> **目的**：让每个关键设计决策的「背景 / 决策 / 后果」可追溯。
> **使用规则**：新设计前先在本目录扫一遍——避免推翻已经论证过的决策。

---

## 索引

| ID | 标题 | 日期 | 状态 |
|----|------|------|------|
| [ADR-001](ADR-001-restrict-analysis-to-tool.md) | 律 4 引入 `restrict_analysis_to` 工具 | 2026-05-26 | ✅ 已落地 |
| [ADR-002](ADR-002-last-understanding-failure-signal.md) | 律 7 引入 `_last_understanding_failure` 信号 | 2026-05-26 | ✅ 已落地 |
| [ADR-003](ADR-003-doctrine-compliance-test.md) | 机器化 doctrine 守门测试 | 2026-05-28 | ✅ 已落地 |
| [ADR-004](ADR-004-known-llm-except-violations-whitelist.md) | 历史债务白名单 `_KNOWN_LLM_EXCEPT_VIOLATIONS` | 2026-05-28 | ⏳ 5 处待清理 |
| [ADR-005](ADR-005-project-context-memory-system.md) | ProjectContext 统一上下文记忆系统 | 2026-05-30 | 🟡 设计中（待修订） |

---

## ADR 模板

新建 ADR 时复制下面骨架到 `ADR-NNN-<slug>.md`：

```markdown
# ADR-NNN：<标题>

- **日期**：YYYY-MM-DD
- **状态**：草案 / 已落地 / 已废弃
- **相关律 / 铁律**：律 X / 铁律 Y

## 背景

什么问题/痛点驱动了这次决策？引用真实用户反馈或 commit hash 增强可信度。

## 决策

我们决定做什么。一句话能说清最好。

## 替代方案

考虑过哪些方案？为什么没选？

## 后果

- 正面：...
- 负面 / 待办：...
- 影响范围：哪些文件 / 测试受影响

## 引用

- 相关 commit / PR
- 相关测试
- 相关 plan / spec 文档
```

---

## 何时写 ADR

- 引入新的架构组件（如 ProjectContext）
- 关键 schema / 工具签名变更（如 restrict_analysis_to）
- 哲学边界争议的最终裁定（如「业务名解析算硬编码吗」）
- 历史债务管理决策（如白名单豁免）
- 任何「下一个 AI 看到会想推翻」的设计

## 何时**不**写 ADR

- 单文件实现层的细节
- 临时调试代码
- prompt 措辞调整（属于 LLM 调优范畴）
