---
title: 召回成长经验
category: workflow
tags: [经验, 记忆, 跨项目]
summary: 从跨项目经验库中召回相关的历史分析经验和教训
tools:
  - recall_lessons
  - save_lesson
---

# 召回成长经验

## 作用

HaGoKu 的记忆系统在每次分析结束后自动记录经验（`save_lesson`）。`recall_lessons` 在新分析开始时召回相关的历史经验，帮助 LLM 参考之前有效的方法，避免已知的陷阱。

## 何时使用

- 分析开始时，根据当前分析目标召回相关经验
- 遇到问题时，查询是否有类似场景的经验教训
- 经验仅供参考——不是结论，LLM 应自行判断是否适用

## 参数

| 参数 | 类型 | 说明 |
|------|------|------|
| context_query | string | 描述当前场景的关键词或短句 |
| top_k | integer | 返回最相关的 N 条经验，默认 5 |

## 配套工具

`save_lesson` 在分析结束后记录新经验。经验包含：
- `scenario`：场景描述
- `what_worked`：有效做法
- `what_failed`：失败教训
- `lesson`：提炼的经验
- `confidence`：可信度（high/medium/low）

## 示例

```json
{
  "context_query": "店铺收入趋势分析 春节效应",
  "top_k": 3
}
```
