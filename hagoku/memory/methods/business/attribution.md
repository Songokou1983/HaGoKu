---
title: 渠道归因分析指南
category: business
tags: [归因, 渠道, 转化, 营销, attribution]
summary: 不同归因模型（最后触达/首次触达/线性）的选择与解读
tools:
---

# 渠道归因分析指南

## 归因方法对比

| 方法 | 逻辑 | 适用 |
|------|------|------|
| 最后触达 (last_touch) | 转化归功于最后一次接触渠道 | 短决策周期、效果广告 |
| 首次触达 (first_touch) | 转化归功于第一次接触渠道 | 品牌认知、长决策周期 |
| 线性归因 (linear) | 平均分配给所有触达渠道 | 多渠道协同、均衡评估 |

## 选择建议

- **效果评估**：优先 last_touch，反映直接 ROI
- **品牌评估**：first_touch 看渠道拉新能力
- **综合评估**：linear 避免单一渠道过度归功

## 局限

- 归因模型是简化假设，真实用户旅程远更复杂
- 无法追踪离线触达（门店、电话）→ 偏袒可追踪渠道
- 建议结合 A/B 测试验证归因结论

## 使用方式

调用 `attribution_analysis(conversions_col='...', channel_col='...', method='last_touch')`。
可选 `revenue_col` 做收益归因、`customer_col` 做旅程级归因。
