---
title: 多重比较校正
category: statistics
tags: [多重比较, Bonferroni, FDR, 假阳性, 校正]
summary: 多次检验为什么要校正，Bonferroni / FDR 适用场景
tools:
  - correct_multiple_comparisons
---

# 多重比较校正

## 为什么要校正

做 20 次独立检验，每次 α=0.05，即使所有原假设都为真：
- 预期假阳性数 = 20 × 0.05 = **1 次**
- 至少出现一次假阳性的概率 = 1 - (1-0.05)^20 ≈ **64%**

做的检验越多，假阳性累积越多，必须校正。

## 校正方法

### 1. Bonferroni（最保守）

将显著性阈值除以检验次数：

```
校正后 α = 原始 α / m
例：20 次检验 → 0.05/20 = 0.0025
```

**适用**：检验次数少，要求严格控制假阳性

### 2. FDR（Benjamini-Hochberg）

控制**虚假发现率**（预期假阳性占显著结果的比例），比 Bonferroni 松：

```
对 p 值升序排列，找到最大的 k 使得 p(k) ≤ k/m × q
拒绝前 k 个原假设
```

**适用**：探索性分析，检验次数多，不要求零假阳性

| 方法 | 控制 | 适用 |
|------|------|------|
| Bonferroni | FWER（族误差率） | 确认真知，少次数 |
| Benjamini-Hochberg | FDR（虚假发现率） | 探索性研究，多次检验 |

## 业务场景选择

- **少次数精确验证**（3-5 个假设）：Bonferroni
- **多维度探索**（20+ 指标同时看）：BH-FDR
- **A/B 测试多指标同时监控**：用 Alpha-Spending（O'Brien-Fleming）

## Python 示例

```python
from statsmodels.stats.multitest import multipletests

p_values = [0.001, 0.01, 0.03, 0.08, 0.20]

# Bonferroni
reject, pvals_corrected, alphacSidak, alphBonf = multipletests(
    p_values, alpha=0.05, method='bonferroni'
)

# BH-FDR
reject, pvals_corrected, _, _ = multipletests(
    p_values, alpha=0.05, method='fdr_bh'
)
```
