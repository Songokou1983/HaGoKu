---
title: 回归分析指南
category: statistics
tags: [回归, 线性回归, 逻辑回归, 系数, R方, 预测]
summary: 线性回归 vs 逻辑回归的选择，系数解读，模型评估指标
tools:
  - run_statistical_test
  - diagnose_regression
  - check_test_assumptions
  - assess_statistical_power
---

# 回归分析指南

## 线性回归 vs 逻辑回归

| | 线性回归 | 逻辑回归 |
|--|---------|---------|
| 因变量 | 连续（销售额、用户数） | 二分类（是否转化、是否流失） |
| 输出 | 具体数值 | 概率 [0, 1] |
| 系数解读 | 每增加1单位，Y增加β | 每增加1单位，Odds增加 e^β 倍 |

## 线性回归评估指标

- **R²（决定系数）**：模型解释的方差比例，0~1，越高越好
- **Adj R²**：考虑自变量数量的调整，更严格
- **残差标准误（ RSE）**：模型预测的平均误差

经验判断：
- R² > 0.7：模型解释力强
- 0.3 < R² < 0.7：中等
- R² < 0.3：弱，考虑增加变量或换模型

## 逻辑回归评估指标

- **AUC-ROC**：0.5（随机）~1（完美），>0.8 较好
- **Accuracy**：准确率，但要注意类别不平衡
- **Precision / Recall**：根据业务侧重选择

## 显著性判断

- **p < 0.05**：该变量对 Y 有显著影响
- 系数符号：正向（+）或负向（-），与业务直觉对照
- 95% 置信区间不包含 0 = 显著

## Python 示例

```python
import statsmodels.api as sm

# 线性回归（带截距）
X = sm.add_constant(df[features])
model = sm.OLS(df['target'], X).fit()
print(model.summary())

# 逻辑回归
X = sm.add_constant(df[features])
model = sm.Logit(df['target'], X).fit()
print(model.summary())
```
