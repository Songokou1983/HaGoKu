---
title: t 检验选择指南
category: statistics
tags: [t检验, 独立样本, 配对样本, 单样本, 假设检验]
summary: 独立样本 t 检验 vs 配对样本 t 检验 vs 单样本 t 检验的选择逻辑
tools:
  - check_test_assumptions
  - run_statistical_test
  - assess_statistical_power
  - required_sample_size
---

# t 检验选择指南

## 三种 t 检验对比

| 类型 | 适用场景 | 示例 |
|------|---------|------|
| 独立样本 t 检验 | 两组独立个体，无关联 | A组用户 vs B组用户 |
| 配对样本 t 检验 | 同一组个体前后测量，或配对 | 服药前 vs 服药后 |
| 单样本 t 检验 | 一组数据与已知均值比较 | 数据均值是否等于 100 |

## 选择决策树

1. **有几组？**
   - 1 组 → 单样本 t 检验
   - 2 组 → 是否有配对关系？
     - 同一批人两次测量 / 配对对象 → 配对样本 t 检验
     - 两批独立个体 → 独立样本 t 检验
   - 3 组及以上 → 考虑 ANOVA（不是 t 检验）

2. **是否满足假设？**
   - 正态性：样本量 ≥ 30 时近似正态（中心极限定理）
   - 方差齐性：独立样本需检验方差是否相等，不等用 Welch 修正
   - 配对无要求正态

## 效应量（Cohen's d）

| d 值 | 含义 |
|------|------|
| 0.2 | 小效应 |
| 0.5 | 中效应 |
| 0.8 | 大效应 |

报告格式：「两组差异显著（t(58)=2.31, p=.025, d=0.61）」

## Python 示例

```python
from scipy import stats

# 独立样本
t, p = stats.ttest_ind(group_a, group_b)

# 配对样本
t, p = stats.ttest_rel(before, after)

# Welch 修正（方差不齐）
t, p = stats.ttest_ind(group_a, group_b, equal_var=False)
```
