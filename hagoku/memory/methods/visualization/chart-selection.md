---
title: 图表选择指南
category: visualization
tags: [图表, 可视化, plotly, scatter, bar]
summary: 根据数据类型和分析问题选择最合适的图表类型
tools:
  - create_plot
---

# 图表选择指南

## 按分析问题选图表

| 分析问题 | 推荐图表 | chart_type |
|---------|---------|------------|
| 两变量关系 | 散点图 | scatter |
| 时间趋势 | 折线图 | line |
| 分组对比 | 柱状图/箱线图 | bar / box |
| 分布形态 | 直方图 | histogram |
| 多组分布对比 | 小提琴图/箱线图 | violin / box |
| 变量相关性 | 热力图 | heatmap |

## 图表设计原则

1. **标题说结论**：不只是"销售额趋势图"，而是"Q3 销售额环比增长 23%"
2. **标注关键数据**：在显著变化点标注数值
3. **颜色区分组别**：传 `color` 参数按组着色
4. **大图不进 LLM context**：图表走 tool_exchange 展示，LLM 只收到路径和摘要

## 使用方式

```python
create_plot(chart_type='scatter', columns=['广告支出', '转化率'], title='广告支出与转化率正相关')
create_plot(chart_type='box', x='渠道', y='收益', color='渠道', title='各渠道收益分布')
create_plot(chart_type='heatmap', title='变量相关性热力图')
```

传 `output_path='/path/to/chart.html'` 可写出文件供报告引用。
