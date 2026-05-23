# Cleaner Agent Memory

## 清洗偏好

> 记录每个项目中各列的清洗策略偏好

```yaml
cleaning_preferences: {}
```

### 规则

- 如果某列之前用 Winsorize 处理过异常值，下次优先用相同策略
- 如果某列之前用中位数填充缺失，下次优先用相同策略
- 保守原则：能保留数据就不删除

## 项目历史

| 项目ID | 清洗日期 | 影响率 | 偏差风险 |
|--------|----------|--------|----------|
| - | - | - | - |

## 用户约束

```yaml
user_constraints: []
```

## 架构变更记录

| 日期 | 变更 | 说明 |
|---|---|---|
| 2026-05-20 | P0 净化：`_plan_via_llm()` | 清洗策略选择从硬编码关键词映射表改为 LLM structured output；Cleaner 不再做策略分支判断 |
| 2026-05-20 | 看板列级审计能力 | Cleaner 通过 Scribe block/unblock 看板，等用户确认后再执行；`_write_cleaning_impact()` 支持看板可观测列更新 |