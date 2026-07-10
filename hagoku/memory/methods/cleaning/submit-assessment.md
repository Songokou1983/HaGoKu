---
title: 清洗评估提交
summary: 提交数据清洗评估结果——告知系统哪些列需要清洗、用什么策略、为什么
category: cleaning
tags: [cleaning, assessment, submit]
tools:
  - submit_assessment
  - detect_outliers
  - detect_missing_pattern
---

## 概述

`submit_assessment` 是评估清洗阶段的终点工具。LLM 在完成数据质量检查后，通过调用此工具提交清洗评估结果，系统据此进入统计分析阶段。

## 使用方式

在评估清洗阶段，LLM 先使用 `detect_outliers` 和 `detect_missing_pattern` 检查数据质量，然后调用 `submit_assessment` 提交评估结果。

参数结构：
```json
{
  "summary": "整体评估说明",
  "columns": [
    {
      "column": "列名",
      "display_name": "显示名",
      "action": "clean 或 skip",
      "reason": "处理原因",
      "operations": [{"strategy": "清洗策略"}]
    }
  ]
}
```

## 适用场景

- 数据质量检查完成后，提交清洗建议供用户确认
- 用户确认清洗方案后，LLM 调用此工具推进到统计分析阶段
- 如果用户对清洗方案有异议，LLM 更新评估后重新提交

## 解读要点

- `action: "clean"` 表示该列需要清洗处理
- `action: "skip"` 表示该列跳过清洗
- 此工具是评估清洗阶段的信号——调用后系统知道清洁阶段完成
