---
title: RFM用户分层
summary: 基于最近消费时间(R)、消费频率(F)、消费金额(M)三个维度对用户进行价值分层
category: business
tags: [rfm, segmentation, user-value, retention]
tools: [get_column_stats, create_plot]
---

## 概述

RFM 模型是用户价值分析的经典框架：

- **R（Recency）**：最近一次消费距今多少天——越近越好
- **F（Frequency）**：一段时间内的消费次数——越多越好
- **M（Monetary）**：一段时间内的消费总金额——越高越好

对每个维度打分（1-5 分），组合成 RFM 分层：

| 分层 | 特征 | 策略 |
|------|------|------|
| 重要价值 | R高F高M高 | 保持，VIP 服务 |
| 重要发展 | R高F低M高 | 提升频次 |
| 重要保持 | R低F高M高 | 召回激活 |
| 一般价值 | R高F高M低 | 提升客单价 |
| 流失风险 | R低F低 | 低成本触达或放弃 |

## 使用方式

告诉 LLM「对用户做 RFM 分层分析」。LLM 会用 `get_column_stats` 获取分布后划分层级。

## 解读要点

- 不要机械分 5 层——根据实际分布调整为 3-4 层更实用
- 重点关注「重要保持」层——曾经高价值但最近沉默的用户
- RFM 是静态快照，结合趋势看更有价值
