---
title: 缺失数据处理指南
category: cleaning
tags: [缺失值, MCAR, MAR, MNAR, 插补, 清洗]
summary: 三种缺失机制（MCAR/MAR/MNAR）的识别与对应清洗策略
tools:
  - detect_missing_pattern
  - suggest_cleaning
---

# 缺失数据处理指南

## 三种缺失机制

| 机制 | 含义 | 检验 |
|------|------|------|
| MCAR | 完全随机缺失，缺失与任何变量无关 | Little's MCAR 检验 |
| MAR | 随机缺失，缺失与观测变量相关 | 分组 t 检验 |
| MNAR | 非随机缺失，缺失与缺失值本身相关 | 最危险，需业务知识 |

## 处理策略

| 机制 | 缺失率低 (<5%) | 缺失率中 (5-20%) | 缺失率高 (>20%) |
|------|---------------|-----------------|----------------|
| MCAR | 删除行 | 中位数/均值填充 | 中位数填充 |
| MAR | 删除行 | 多重插补 (MICE) | 多重插补 |
| MNAR | 标记保留 | 标记保留 + 敏感性分析 | 删除列或标记 |

## 核心原则

1. **先检测机制再选策略**：调 `detect_missing_pattern` 判断 MCAR/MAR/MNAR
2. **自动化策略**：调 `suggest_cleaning` 自动推荐
3. **MNAR 极度保守**：不删除、不随意填充，必须标记
4. **比较清洗前后**：调 `compare_before_after` 看清洗对分布的影响

## 使用方式

```
detect_missing_pattern(column='收入')  → 返回 mcar/mar/mnar
suggest_cleaning(column='收入')        → 返回推荐策略 + 理由
```
