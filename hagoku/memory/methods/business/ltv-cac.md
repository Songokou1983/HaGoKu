---
title: LTV 与 CAC 计算指南
category: business
tags: [LTV, CAC, 用户价值, 获客成本, 商业]
summary: 用户生命周期价值 (LTV) 和客户获取成本 (CAC) 的计算与健康度判断
tools:
  - get_column_stats
  - run_statistical_test
---

# LTV 与 CAC 计算指南

## LTV（用户生命周期价值）

```
LTV = Σ(每期收益 × 留存概率)
```

简化为：用户在生命周期内贡献的总收益。

- avg_ltv：平均每用户价值
- median_ltv：中位数（偏态分布时更可靠）
- discounted_ltv：折现后的当前价值

## CAC（客户获取成本）

```
CAC = 总获取成本 / 新客户数
```

- 包含所有营销和销售费用
- 可选择按获取日期分月计算，观察 CAC 趋势

## LTV/CAC 比率

```
LTV/CAC = 用户生命周期价值 / 客户获取成本
```

| 比值 | 含义 |
|------|------|
| > 3x | 健康，商业模式可持续 |
| 1x ~ 3x | 边际，需优化 |
| < 1x | 不可持续，每获取一个用户亏钱 |

## 何时使用

- LTV 和 CAC 需串联使用：先调 `calc_ltv`、再调 `calc_cac`、最后 `calc_ltv_cac_ratio`
- 配合 ROI/ROAS 做完整商业分析
