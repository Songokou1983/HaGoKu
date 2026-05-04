---
title: LTV 与 CAC
category: financial
tags: [LTV, CAC, 用户生命周期价值, 获客成本, 比率]
summary: LTV 计算方法（历史法/预测法），LTV/CAC 比率的健康阈值
---

# LTV 与 CAC

## 基本概念

- **CAC（Customer Acquisition Cost）**：获取一个新客户的平均成本

```
CAC = 总获客成本 / 新客户数
```

- **LTV（Life Time Value）**：一个用户在整个生命周期内贡献的总价值

```
LTV = 用户平均生命周期 × 单个用户平均收入
```

## LTV 计算方法

### 方法一：历史法（适合成熟业务）

```
LTV = 平均订单价值 × 平均订单频次 × 平均生命周期（月）× 毛利率
```

### 方法二：Cohort 推算法（更精准）

按月份 Cohort 计算累计 ARPU（Average Revenue Per User），
追踪每个 Cohort 的衰减曲线直到稳定。

```python
# 简化版 Cohort LTV 计算
cohort = df.groupby(['cohort_month', 'month']).agg({'revenue': 'sum', 'users': 'nunique'})
cohort['arpu'] = cohort['revenue'] / cohort['users']

# 累计 ARPU 即为 LTV 近似
cohort_ltv = cohort.groupby('cohort_month')['arpu'].cumsum()
```

## LTV/CAC 比率的健康阈值

| 比率 | 健康状态 |
|------|---------|
| LTV/CAC < 1 | 亏损，获客不划算 |
| 1 ~ 3 | 可持续，盈利但增长慢 |
| 3 ~ 5 | 最佳，有钱投入扩张 |
| > 5 | 增长慢，市场份额在流失 |

> 经验值：LTV/CAC > 3 是健康线，最好能到 5 以上

## 应用场景

- **预算分配**：哪个渠道 CAC 低且 LTV 高 → 增加投入
- **用户分层**：LTV 高的用户重点维护，不值得为低 LTV 用户大幅加码
- **增长决策**：CAC 回收周期（Month to CAC payback）< 12 个月较健康
