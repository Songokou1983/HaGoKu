---
title: 漏斗分析
category: business
tags: [漏斗, funnel, 转化率, 流失, 步骤]
summary: 漏斗分析步骤，每步转化率计算，如何找到最大流失节点
---

# 漏斗分析

## 基本流程

```
步骤1 → 步骤2 → 步骤3 → ... → 转化
  ↓       ↓       ↓            ↓
 进入   中间   中间         成交
```

## 漏斗指标

| 指标 | 计算方式 |
|------|---------|
| 每步转化率 | 步骤N+1 人数 / 步骤N 人数 |
| 总转化率 | 最终成交 / 总进入 |
| 流失率 | 1 - 转化率 |
| 流失集中度 | 各步流失占总流失的比例 |

## 如何找到最大流失节点

1. **计算每步绝对流失量**：进入数 - 下一进入数
2. **计算相对流失率**：流失数 / 上一步进入数
3. **流失集中度**：某步流失 / 总流失量 → 找到占比最高的步骤

**最大流失节点 = 相对流失率最高的步骤 ≠ 绝对流失量最大的步骤**

## 漏斗分析常见问题

1. **步骤定义不统一**：不同系统对"进入"的定义不同
2. **时间窗口错位**：步骤间隔太长，用户中途流失被漏计
3. **路径分叉**：用户可能跳过中间步骤，导致漏斗不闭合

## 改进效果衡量

```
改进前转化率 → 改进后转化率 → 提升幅度
   2.1%    →    3.5%    → +66.7%
```

## Python 示例

```python
import pandas as pd

funnel_data = {
    'step': ['浏览商品', '加入购物车', '提交订单', '支付成功'],
    'users': [10000, 3500, 1200, 840],
}

df = pd.DataFrame(funnel_data)

# 每步转化率
df['conversion_rate'] = df['users'] / df['users'].shift(1).fillna(df['users'])
df['drop_rate'] = 1 - df['conversion_rate']

# 每步绝对流失
df['drop'] = df['users'].shift(-1).fillna(0).astype(int) - df['users']
df['drop'] = df['drop'].abs()

# 总流失中各步占比
total_drop = df['drop'].sum()
df['drop_pct'] = df['drop'] / total_drop * 100

print(df)
# 找到最大流失节点
max_drop_step = df.loc[df['drop_pct'].idxmax(), 'step']
print(f"\n最大流失节点: {max_drop_step} ({df['drop_pct'].max():.1f}% of total drop)")
```
