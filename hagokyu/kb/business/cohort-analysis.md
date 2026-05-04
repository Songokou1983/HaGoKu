---
title: 用户群组分析（Cohort）
category: business
tags: [cohort, 群组, 留存, 同期群, 生命周期]
summary: Cohort 分析的定义，如何按时间窗口分组，留存曲线如何解读
---

# 用户群组分析（Cohort Analysis）

## 什么是 Cohort

Cohort = 一组在**相同时间段**内共同经历某个事件的用户。

Cohort 分析追踪这群用户在不同时间点的行为变化，核心是**留存曲线**。

## 常见 Cohort 类型

| 类型 | 分组依据 | 用途 |
|------|---------|------|
| 注册 Cohort | 首次注册月份 | 长期留存率追踪 |
| 首次购买 Cohort | 首次购买月份 | 复购行为分析 |
| 激活 Cohort | 首次使用产品月份 | 激活质量对比 |

## 留存率计算

```
第 N 天留存率 = 第 N 天还活跃的用户数 / Cohort 总用户数 × 100%
```

Cohort Table 示例（行 = 注册月份，列 = 注册后第几个月）：

| 注册月份 | Month 0 | Month 1 | Month 2 | Month 3 |
|---------|---------|---------|--------|---------|
| 1月 | 100% | 45% | 30% | 22% |
| 2月 | 100% | 42% | 28% | - |
| 3月 | 100% | 48% | - | - |

## 留存曲线解读

- **初期流失快**（Month 0 → Month 1）：说明激活体验差
- **长期平稳**：真实用户沉淀，下滑缓慢
- **Cohort 对比**：新注册 Cohort 的 Month 1 留存是否比老 Cohort 高 → 判断产品改进效果

## 常见误区

1. **用自然月而非用户生命周期**：不同月注册用户量不同，直接比不公平
2. **忽略重新激活**：只算"首次活跃"，用户重新回来不算留存
3. **观测期不足**：留存曲线需要 3-6 个月才能看到真实平稳值

## Python 示例

```python
import pandas as pd

# 注册Cohort留存表
df['register_month'] = df['first_login'].dt.to_period('M')
df['cohort_month'] = df['login_date'].dt.to_period('M')
df['period_number'] = (df['cohort_month'].astype(int) -
                        df['register_month'].astype(int))

cohort_table = (df.groupby(['register_month', 'period_number'])['user_id']
                .nunique()
                .unstack(fill_value=0))

# 留存率
cohort_size = cohort_table.iloc[:, 0]
retention_table = cohort_table.divide(cohort_size, axis=0) * 100
print(retention_table.round(1))
```
