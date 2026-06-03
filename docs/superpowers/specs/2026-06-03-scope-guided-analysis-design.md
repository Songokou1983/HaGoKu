# Scope 引导式分析 — 字段理解的正向加强设计 (R2)

> 日期: 2026-06-03 | 修订: R2（回应审查意见） | 状态: 设计阶段

## 核心理念

**Scope 是引导性的，不是限制性的。** 全表始终对 LLM 可见（读），scope 告诉 LLM "优先关注这些列"。
Cleaner 是唯一例外——清洗是写操作，只洗 scope 内列，scope 外列原样保留以备解锁。
用户随时可以说"那个也看看"——解锁而非重新配置。

## 与现有机制的整合（B1）

`ProjectContext.build_prompt` 已产出 `system_prefix`，含字段状态表、target、features。
**本 spec 不新增并行通道，不替换 system_prefix，不新增第三段。**

Scope 信息通过 `system_prefix` 已有的字段状态表表达——其中每行的 `参与/不参与` 列和角色列已经传达了 scope。
唯一新增的是：当用户解锁/锁定字段时，**更新 `column_semantics` → `_derive_snapshot` 自动反映到 system_prefix**。
下游 Agent 的 prompt 里自然看到最新的 scope，无需额外 scope_block 文本。

## 与 Analyst 对话式分析 spec 的关系（B4）

本 spec 是 [Analyst 对话式分析 spec](2026-06-02-analyst-dialogue-design.md) 的**追加扩展**，不替换不并行。
在 Analyst 现有 4 工具基础上新增 `update_analysis_scope` 工具（见 §3）。

## 下游行为（B2 已解决）

| Agent | 操作类型 | Scope 行为 | 理由 |
|-------|---------|-----------|------|
| **Cleaner** | 写（清洗） | **硬过滤**：只洗 scope 内列 | 清洗是破坏性操作，不应修改用户未要求清洗的列；scope 外列在 df 中保留，解锁后可用 |
| **Analyst** | 读（分析） | **引导**：system_prefix 标注 scope，LLM 自己决定聚焦范围；全表可读 | 分析是探索性操作——LLM 看到全表才能发现意外关联 |
| **Reporter** | 读（渲染） | 不需要 scope | findings 已自带 `evidence_columns`，Reporter 只管渲染 Analyst 结论 |

## 两层解锁（B3 实施细节）

在 Analyst 工具集新增 `update_analysis_scope`：

```
Tool: update_analysis_scope
description: 调整分析范围——纳入或排除字段。调此工具后系统自动更新分析上下文。
parameters:
  add_columns: string[]    # 纳入分析的列名
  remove_columns: string[] # 移出分析的列名
  reason: string           # 调整原因
```

### 小解锁（数据干净，直接加）

```
用户: "把 Inc2 也看看"
  → LLM 调 get_column_stats("Inc2") 检查数据
  → 数据干净
  → LLM 调 update_analysis_scope(add_columns=["Inc2"], reason="用户要求纳入分析")
  → 代码: column_semantics["Inc2"]["used_in_analysis"] = True
  → 代码: 重新 _derive_roles()，更新 target/features
  → 代码: emit AGENT_THINKING "分析范围已更新：新增 Inc2"
  → Analyst 继续分析（无需重跑，数据已在 df 中）
```

### 大解锁（需要清洗，建议重跑）

```
用户: "把 Inc2 也看看"
  → LLM 调 get_column_stats("Inc2") 发现大量空值/异常
  → LLM 不调 update_analysis_scope
  → LLM 文本告知用户: "Inc2 数据质量问题较多（空值率 40%），建议从字段理解阶段重新开始以便清洗"
```

### 实施细节（B3 完整）

| 步骤 | 代码动作 | 文件 |
|------|---------|------|
| LLM 调 `update_analysis_scope` | `agent_tool_defs.py` 注册工具 + handler | `hagoku/tools/agent_tool_defs.py` |
| 更新 `used_in_analysis` | handler 遍历 `add_columns`/`remove_columns`，设 `column_semantics[i].used_in_analysis` | 同上 |
| 重新派生 target/features | 调 `_derive_roles(context)` | `hagoku/agents/scout/agent.py` |
| 写入 ProjectContext | `add_agent_response(stage="analyst", snapshot=_derive_snapshot(context), content="解锁 Inc2")` | `hagoku/context/project_context.py` |
| 通知前端 | `emit(AGENT_THINKING, "分析范围已更新")` | orchestrator |

### 大解锁 UX（W5）

LLM 文本告知用户建议重跑。前端不需要弹窗或自动跳转——**对话自然呈现**。
用户可选择：
- 接受建议 → 点「重置分析」重新开始
- 忽略建议 → 继续当前分析（Inc2 不参与）
- 强行纳入 → 用户说"不管，直接加" → LLM 调 `update_analysis_scope`（小解锁路径）

### 约束式 prompt 边界标注（W2）

`update_analysis_scope` 工具的 description 包含解锁判断指引：

> 调用前先检查字段数据质量（调 get_column_stats）。若空值率 < 20% 且无类型异常，可直接纳入。
> 此指引是约束式 prompt——LLM 根据数据自主判断，代码不设硬阈值。

## 数据流

```
Scout → context.column_semantics (used_in_analysis 已设)
  → Cleaner: 评估时只看 used_in_analysis=True 的列；清洗时只洗这些列
  → Analyst: system_prefix 含字段状态表；LLM 自由探索，全表可读
    → 用户解锁 → update_analysis_scope → 更新 scope → 继续分析
    → 用户要求大解锁 → LLM 文本建议重跑
  → Reporter: 收 findings 渲染，不管 scope
```

## 守门测试（W1）

| 编号 | 测试 | 验证方式 |
|------|------|---------|
| G1 | Analyst prompt 含字段状态表（参与/不参与/待定） | spy llm_client，断言 system_prefix 含 `参与  role=` |
| G2 | `update_analysis_scope` 小解锁后 column_semantics 更新 | 调 handler → 断言 `sem["used_in_analysis"]` 变为 True |
| G3 | 解锁后 `_derive_roles` 重新派生 target/features | 小解锁后断言 context["features"] 包含新列 |
| G4 | 解锁后 ProjectContext 写入 snapshot | 小解锁后断言 `add_agent_response` 被调用，snapshot.fields 含新列 |
| G5 | Cleaner assess prompt 不含 scope 外列 | spy LLM messages，断言 col_names 不含 `used_in_analysis=False` 的列 |
| G6 | 大解锁路径不调 `update_analysis_scope` | mock LLM 返回"建议重跑"文本 → 断言 handler 未被调 |

## 任务拆分（W1）

| Tier | 任务 | 范围 |
|------|------|------|
| T1 | 注册 `update_analysis_scope` 工具 + handler | `agent_tool_defs.py` |
| T2 | Analyst system prompt 追加 scope 解锁指引 | `analyst/agent.py` |
| T3 | 解锁后重新派生 target/features | `scout/agent.py:_derive_roles` （已存在，确认被调用） |
| T4 | 守门测试 G1–G6 | `tests/test_product/` |
| T5 | 小解锁后 emit 事件通知前端 | orchestrator 或 analyst respond 路径 |
| T6 | （可选）Cleaner run() 也过滤 scope 外列 | `cleaner/agent.py:run()` |
| T7 | （可选）大解锁建议文案优化 | prompt 调整 |

T1–T3 为最小可行，T4–T5 为质量保障，T6–T7 为后续优化。

## snapshot schema 建议（S1）

当前 `_derive_snapshot` 产出的 `fields` 已含 `{name, display, role, participating}`。解锁后 `participating` 字段自然更新。
不需新增 schema——现有 snapshot 已覆盖 scope 信息。

## 律 3 集成（S2）

| 事件 | ProjectContext 写入 |
|------|---------------------|
| LLM 调 `update_analysis_scope` 解锁 | `add_agent_response(stage="analyst", content="解锁 Inc2", snapshot=_derive_snapshot(context))` |
| LLM 建议大解锁（文本，未调工具） | `add_agent_response(stage="analyst", content="建议回 Scout 重跑", snapshot=不变)` |

## 与阶段 3 任务 K 协调（S3）

任务 K（agent_response.content 记 LLM 实际输出 + tool_calls）完成后，解锁的 tool_call 自动落 entries。
本 spec 的 `update_analysis_scope` 调用会被 K 的基础设施捕获，无需本 spec 额外设计。
