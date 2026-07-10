---
title: 购物篮分析
summary: 发现商品之间的购买关联关系——「买了A的人通常也买了B」
category: business
tags: [basket, association, cross-sell, market-basket]
tools: [run_statistical_test, create_plot]
---

## 概述

购物篮分析（Market Basket Analysis）通过分析订单中商品共现关系，挖掘交叉销售机会。

核心指标：
- **支持度（Support）**：A和B同时出现的概率
- **置信度（Confidence）**：买了A的人中也买了B的比例
- **提升度（Lift）**：买A对买B概率的提升倍数

$$ Lift(A \rightarrow B) = \frac{P(B|A)}{P(B)} $$

Lift > 1 表示正关联，< 1 表示负关联，= 1 表示独立。

## 适用场景

- 商品推荐：「看了A的人也看了B」
- 促销组合设计：高关联商品打包
- 货架布局优化

## 使用方式

告诉 LLM「做购物篮关联分析」。LLM 调用 `run_statistical_test` 计算商品对的相关性或共现频率。

## 解读要点

- 关注高提升度搭配——这些是真正的交叉销售机会
- 高支持度但低提升度——只是热门商品，不是真关联
- 周期性关联：某些搭配只在特定时段出现（如节日礼盒）
