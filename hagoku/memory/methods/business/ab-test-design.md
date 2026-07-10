---
title: A/B测试设计与评估
summary: 科学对比两个方案的效果差异——实验设计、样本量估算、统计检验
category: business
tags: [ab-test, experiment, significance, sample-size]
tools: [check_test_assumptions, run_statistical_test, assess_statistical_power]
---

## 概述

A/B 测试是比较两个版本（对照组 vs 实验组）效果差异的标准方法。

关键步骤：
1. **确定指标**：转化率、客单价、留存率等
2. **估算样本量**：根据期望效应量和统计功效计算需要多少用户
3. **随机分流**：确保两组用户特征可比
4. **统计检验**：t 检验或卡方检验判断差异是否显著
5. **评估实际显著性**：统计显著 ≠ 商业显著

## 适用场景

- 首页改版效果评估
- 定价策略 A/B 对比
- 营销文案转化率测试
- 推荐算法效果对比

## 使用方式

告诉 LLM「对比 A/B 两组的转化率差异」。LLM 调用 `check_test_assumptions` 验证前提后跑 `run_statistical_test`。

## 解读要点

- p < 0.05：差异统计显著，但还要看效应量是否够大
- 样本量不足 → 即使有真实差异也检不出 → 先做功效分析
- 多重比较问题：同时测多个指标需要校正（Bonferroni）
