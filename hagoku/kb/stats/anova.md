---
title: 方差分析（ANOVA）
category: stats
tags: [anova, 多组比较, F检验, 方差分析, post-hoc]
summary: 单因素/双因素 ANOVA 的选择条件，以及 post-hoc 检验的必要性
---

# 方差分析（ANOVA）

## 什么时候用 ANOVA 而非 t 检验

- **比较 3 组及以上**时用 ANOVA
- 同时比较两组时，ANOVA 与 t 检验等价，但 t 检验更常用
- ANOVA 的原假设：所有组均值相等

## 单因素 vs 双因素

| 类型 | 自变量数量 | 用途 |
|------|-----------|------|
| 单因素 ANOVA | 1 | 一个因素多水平（如渠道：A/B/C） |
| 双因素 ANOVA | 2 | 两个因素及其交互作用（如渠道 × 地区） |

## ANOVA 假设

1. **独立性**：各组观测独立
2. **正态性**：各组残差近似正态（样本量大时不严格）
3. **方差齐性**：各组方差相等（用 Levene 检验）

## Python 示例

```python
from scipy import stats

# 单因素 ANOVA
f, p = stats.f_oneway(group_a, group_b, group_c)

# 双因素 ANOVA（需要 pingouin 或 statsmodels）
# import pingouin as pg
# pg.anova(data=df, dv='value', between=['factor_a', 'factor_b'])
```

## 为什么 ANOVA 显著后还要做 Post-hoc

ANOVA 只告诉我们"至少有一组不同"，不说是哪一组。
Post-hoc 检验两两比较，常用方法：

| 方法 | 控制什么 | 适用场景 |
|------|---------|---------|
| Tukey HSD | 族误差率（FWER） | 组数不太多 |
| Bonferroni | 保守 | 组数多时功效下降 |
| Scheffé | 最保守 | 任意比较 |

```python
from scipy.stats import tukey_hsd

result = tukey_hsd(group_a, group_b, group_c)
print(result)
```
