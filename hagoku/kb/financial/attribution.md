---
title: 归因模型
category: financial
tags: [归因, attribution, 首次触点, 末次触点, 线性归因, 数据驱动]
summary: 各归因模型的优缺点，什么时候用什么模型
---

# 归因模型

## 主流归因模型对比

| 模型 | 逻辑 | 优点 | 缺点 |
|------|------|------|------|
| 首次触点 | 100% 归因第一个渠道 | 简单，利于发现拉新渠道 | 忽略后续培育 |
| 末次触点 | 100% 归因最后一个渠道 | 容易追踪，对直接转化有效 | 忽略前期种草 |
| 线性归因 | 平均分配给所有触点 | 公平，考虑全流程 | 忽略触点重要性差异 |
| 时间衰减 | 越近转化贡献越大 | 考虑时序 | 远端触点贡献被低估 |
| 位置分配 | 首尾各 40%，中间平分 20% | 平衡首尾 | 固定比例不灵活 |
| 数据驱动 | 算法学习每个触点真实贡献 | 最精准 | 需要足够数据量 |

## 选择原则

1. **短决策周期**（B2C 电商）：末次触点或末次非直接点击
2. **长决策周期**（B2B、企业服务）：首次触点 + 线性组合
3. **内容驱动**（教育、内容平台）：时间衰减或数据驱动
4. **预算有限**（小公司）：末次触点，追踪简单

## 跨渠道 ROI 对比时的坑

- 不同归因模型下同一渠道的 ROI 可能差 2-3 倍
- **对比时必须用同一归因模型**
- 数据驱动归因需要足够转化数据（建议月转化 > 1000）

## 实现示例

```python
# 末次触点归因
df['channel_last'] = df.groupby('session_id')['channel'].transform('last')

# 首次触点归因
df['channel_first'] = df.groupby('session_id')['channel'].transform('first')

# 线性归因（需 session 路径数据）
channel_path = df.groupby('session_id')['channel'].apply(list)
df['n_touches'] = df['session_id'].map(channel_path.str.len())
df['weight'] = 1 / df['n_touches']
```
