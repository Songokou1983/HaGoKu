---
title: 生成分析报告
category: workflow
tags: [分析闭环, 报告, HTML]
summary: 将确认的分析发现生成 HTML 报告，支持多种模板
tools:
  - generate_report
  - create_plot
---

# 生成分析报告

## 作用

撰写报告阶段的核心工具。将 `submit_findings` 确认过的分析发现整理为正式 HTML 报告。

## 模板

| 模板 | 适用场景 |
|------|---------|
| default | 标准商业分析报告 |
| academic | 学术风格，含方法引用 |
| brief | 简短摘要，管理层汇报 |
| business_analysis | 详细商业分析 |

## 图表注入

`create_plot` 生成的图表会自动注入到报告中，无需在 `sections` 的 `charts` 字段手动传递。LLM 只需在统计分析阶段调用 `create_plot` 生成图表，报告生成时系统自动关联。

## 参数

| 参数 | 类型 | 说明 |
|------|------|------|
| sections | array | 报告章节，每项含 title/content/headline/findings/charts |
| template | string | 模板名（default/academic/brief/business_analysis） |

## 流程

1. 统计分析阶段调 `create_plot` 生成图表
2. 调 `submit_findings` 提交发现 → 调 `ask_user` 确认
3. 用户确认后调 `generate_report` 生成报告
4. 报告生成后调 `ask_user` 请用户确认
