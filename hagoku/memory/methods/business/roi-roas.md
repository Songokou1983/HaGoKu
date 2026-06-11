---
title: ROI 与 ROAS 计算指南
category: business
tags: [ROI, ROAS, 投资回报, 广告回报, 财务]
summary: 投资回报率 (ROI) 和广告支出回报率 (ROAS) 的计算公式与业务解读
tools:
  - calc_roi
  - calc_roas
---

# ROI 与 ROAS 计算指南

## ROI（投资回报率）

```
ROI = (收益 - 成本) / 成本 × 100%
```

- ROI > 0：盈利
- ROI = 0：持平
- ROI < 0：亏损

示例：投入 100 万，收益 150 万 → ROI = 50%

## ROAS（广告支出回报率）

```
ROAS = 广告带来的收益 / 广告支出
```

- ROAS > 1：广告盈利
- ROAS = 1：持平
- ROAS < 1：广告亏损

示例：广告花费 10 万，带来 40 万收益 → ROAS = 4x

## ROI 与 ROAS 的关系

| 指标 | 公式 | 关注点 |
|------|------|--------|
| ROI | (收益-成本)/成本 | 整体投资效率 |
| ROAS | 广告收益/广告支出 | 广告渠道效率 |

ROI 包含全部成本（含广告），ROAS 只看广告支出。两者结合才能全面评估营销效果。

## 何时使用

- 有收益和成本列的数据 → 使用 `calc_roi`
- 有广告收益和广告支出 → 使用 `calc_roas`
- 配合 `calc_ltv` + `calc_cac` 做完整商业评估
