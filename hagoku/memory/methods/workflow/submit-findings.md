---
title: 提交分析发现
category: workflow
tags: [分析闭环, 提交, 发现]
summary: 将统计分析阶段的发现提交给系统，支持首波探索性发现或最终结论
tools:
  - submit_findings
---

# 提交分析发现

## 作用

统计分析阶段结束后，将发现提交给系统。`submit_findings` 替代了旧的 `submit_first_pass`（首波提交）和 `submit_analysis`（最终提交）——现在统一为一个工具，由代码判断是首波还是后续。

## 何时使用

- 完成一轮统计分析后，将发现提交给用户
- 提交后通常调用 `ask_user` 请用户确认
- 用户确认后进入撰写报告阶段

## 参数

| 参数 | 类型 | 说明 |
|------|------|------|
| findings | array | 发现列表，每项含 title/detail/evidence_columns/confidence |
| method_used | array | 使用的统计方法名 |
| summary | string | 整体摘要 |

## 示例

```json
{
  "findings": [
    {
      "title": "店铺间收入差异显著",
      "detail": "单因素方差分析显示不同店铺收入存在显著差异（F=12.3, p<.001, η²=0.93）",
      "evidence_columns": ["Inc1", "StoreID"],
      "confidence": "high"
    }
  ],
  "method_used": ["anova"],
  "summary": "主要收入差异由店铺因素解释（η²=93.1%）"
}
```
