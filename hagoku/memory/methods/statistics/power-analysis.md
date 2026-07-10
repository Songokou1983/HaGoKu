---
title: 统计功效与样本量（Power Analysis）
category: statistics
tags: [power, 功效, 样本量, 效应量, 检验力]
summary: 为什么分析前要做功效分析，如何计算所需样本量
tools:
  - assess_statistical_power
  - required_sample_size
---

# 统计功效与样本量（Power Analysis）

## 什么是统计功效（Power）

功效 = 当效应真实存在时，正确拒绝原假设的概率。

| 功效 | 含义 |
|------|------|
| 80% | 标准阈值，黄金标准 |
| 90% | 更严格，少漏检 |

## 功效分析的四个变量

**功效分析告诉你：给定任意三个变量，计算第四个。**

1. **样本量（n）**：数据点数量
2. **效应量（d / f）**：实际效应的大小
3. **显著性水平（α）**：通常 0.05
4. **功效（1-β）**：目标 80%

## 什么时候必须做功效分析

- **A/B 测试前**：避免样本量不足导致无法检测真实效应
- **实验设计阶段**：确定需要多少数据
- **事后分析**：解释"为什么没显著"——是真的没效应，还是样本不够

## 常见效应量参考

| 效应类型 | 小 | 中 | 大 |
|---------|-----|-----|-----|
| Cohen's d（t 检验）| 0.2 | 0.5 | 0.8 |
| Cohen's f（ANOVA）| 0.10 | 0.25 | 0.40 |
| r（相关）| 0.1 | 0.3 | 0.5 |

## Python 示例

```python
from statsmodels.stats.power import TTestIndPower, TTestPower

# 计算所需样本量（两组独立样本）
power_analysis = TTestIndPower()
n = power_analysis.solve_power(
    effect_size=0.5,   # 中效应
    alpha=0.05,
    power=0.8,
    alternative='two-sided'
)
print(f"每组需要 {n:.0f} 个样本")

# 分析已收集数据的功效
from statsmodels.stats.power import ttest_power
power = ttest_power(0.5, nobs=50, alpha=0.05, alternative='two-sided')
```
