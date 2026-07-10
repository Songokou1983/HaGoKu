---
title: 趋势分解
summary: 将时间序列拆解为趋势、季节性和残差三个分量，识别长期走向和周期性规律
category: trading
tags: [trend, seasonal, time-series, decomposition]
tools: [run_statistical_test]
---

## 概述

趋势分解（Time Series Decomposition）将一条时间序列 $Y_t$ 拆解为：

$$Y_t = T_t + S_t + R_t$$

- $T_t$：趋势分量（长期走向）
- $S_t$：季节分量（固定周期的重复模式）
- $R_t$：残差（随机波动）

## 适用场景

- 股票价格的长期趋势 + 季节性模式识别
- 销售额的季节性分析
- 周期性行业的基本面判断

## 使用方式

在 HaGoKu 分析中，告诉 LLM「对收入做趋势分解」或在统计分析阶段要求使用趋势分解。LLM 会调用 `run_statistical_test(test_type="trend_decomposition")`。

## 解读要点

- 趋势分量占比越高，说明长期方向明确
- 季节分量显著 → 存在周期性规律，可用于择时
- 残差波动大 → 随机因素主导，预测难度高
- 结合单位根检验判断趋势是确定性还是随机游走
