# Scope 引导式分析 — 字段理解的正向加强设计

> 日期: 2026-06-03 | 状态: 设计阶段

## 核心理念

**Scope 是引导性的，不是限制性的。** 全表始终对 LLM 可见，scope 告诉 LLM "优先关注这些列"。
用户随时可以说"那个也看看"——解锁而非重新配置。

## 当前问题

| 问题 | 现状 |
|------|------|
| Scope 产出未显式传递 | Scout 设了 `used_in_analysis`，但下游 Agent 的 prompt 没有统一引用 |
| Cleaner 只评估 scope 内列 | `cleaner/agent.py:570` 过滤了——但 scope 外列完全不可见 |
| Analyst 看到全表 | `analyst/agent.py:237` 列出全部 `df.columns`，无用列可能串台 |
| 无解锁机制 | 过了 Scout 阶段，用户想加回一个字段需要重跑 |

## 设计方案

### 1. Scope 结构

Scout 完成后产出显式 scope 块，注入到下游所有 Agent 的 system prompt：

```
【分析范围 (scope)】
  目标变量: Inc1（店铺收入）
  特征变量: Code（店铺编码）、Period（周期）
  排除字段: BU、Inc2、Bos1、Bos2、Bos3（与收入变动趋势无直接关系）
  全表列: BU, Code, Period, Inc1, Inc2, Bos1, Bos2, Bos3
```

### 2. 下游行为

| Agent | 收到 | 行为 |
|-------|------|------|
| **Cleaner** | scope + 全量 df | 只清洗 scope 内列；scope 外列原样保留，不洗 |
| **Analyst** | scope + 全量 df | prompt 注入 scope，LLM 优先分析 scope 内列；全表可读 |
| **Reporter** | scope + 结果 | 报告聚焦 scope 内结论 |

### 3. 两层解锁

| | 小解锁 | 大解锁 |
|------|------|------|
| 触发 | 分析阶段用户说"把 Inc2 也看看" | 用户要加的字段从未清洗 |
| 判断 | **LLM 自行判断**——检查字段类型、数据质量 | 同上 |
| 动作 | 更新 scope，Analyst 重跑（数据已在 df 中） | 建议回到 Scout 重跑（需要清洗） |
| 代价 | 零 | 需要重新清洗 |

LLM 判断逻辑（注入 prompt）：
> 如果用户要解锁的字段数据质量良好（无非空值异常、类型匹配、值域合理），
> 直接纳入 scope 继续分析。如果数据需要清洗，告知用户建议从字段理解阶段重新开始。

### 4. 数据流

```
Scout 产出 scope
  → Cleaner: 洗 scope 内列，scope 外列原样保留
  → Analyst: system prompt 注入 scope，LLM 主攻 scope
  → 用户: "加 Inc2"
    → LLM 检查 Inc2 数据 → 干净: 更新 scope + Analyst 重跑
                        → 需洗: 建议重回 Scout
```

### 5. 与现状的区别

| 维度 | 现状 | 改后 |
|------|------|------|
| Scope 传递 | 隐式（`used_in_analysis` 存在 context 中） | 显式 scope 块注入 prompt |
| Cleaner 范围 | scope 内列 | scope 内列（不变） |
| Analyst 可见列 | 全部 `df.columns` | 全部（不变），但 prompt 标注 scope |
| 解锁 | 无 | 两层：LLM 自判断 |

## 实现要点

1. Scout 完成后构建 scope 文本块，写入 context
2. Cleaner/Analyst/Reporter 的 system prompt 统一引用 `{scope_block}`
3. Analyst 对话中注入解锁判断指令
4. 解锁时更新 `context["column_semantics"]` 对应列的 `used_in_analysis`，重新触发 `_derive_roles`
