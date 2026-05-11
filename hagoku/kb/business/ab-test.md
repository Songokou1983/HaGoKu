---
title: A/B 测试分析
category: business
tags: [AB测试, 实验设计, 随机分组, 显著性, 置信区间]
summary: A/B 测试完整流程：分组设计、样本量估算、结果解读
---

# A/B 测试分析

## 标准流程

```
1. 假设设定
2. 样本量计算（功效分析）
3. 随机分组
4. 流量分配
5. 执行测试
6. 收集数据
7. 统计检验
8. 结论输出
```

## 假设设定

- **原假设（H0）**：A 和 B 没有差异
- **备择假设（H1）**：A 和 B 有差异（或 B 优于 A）

## 随机分组检验

确保两组基线特征分布一致：

```python
from scipy import stats

# 检验两组年龄分布是否一致
chi2, p = stats.chisquare(
    observed=[group_a['age'].value_counts()],
    expected=[group_b['age'].value_counts()]
)
```

## 统计检验

| 指标类型 | 检验方法 |
|---------|---------|
| 转化率（二分类） | 卡方检验 或 z 检验 |
| 连续值（客单价、时长） | t 检验 或 Mann-Whitney U |
| 多指标同时监控 | FDR 校正 |

## 结果解读 Checklist

- [ ] p < 0.05？
- [ ] 效应量是否实际有意义？（不只是统计显著）
- [ ] 置信区间是否包含 0 / 1？
- [ ] 样本量是否达到功效分析要求？
- [ ] 测试时长是否覆盖完整用户周期（避免周一到周五偏差）？

## 常见陷阱

1. **新奇效应**：新版本初期效果好是因为用户好奇，非真实效应
2. **样本量不足**：没做功效分析，检测不到真实效应（Type II Error）
3. **多指标检验**：同时看 10 个指标，至少一个显著是大概率事件
4. **季节性**：节假日/大促期间数据不代表平常

## Python 示例

```python
from scipy import stats
import numpy as np

# 两组转化率比较（z 检验）
n1, n2 = 5000, 5000
conv1, conv2 = 250, 320

p1 = conv1 / n1
p2 = conv2 / n2
pooled_p = (conv1 + conv2) / (n1 + n2)
se = np.sqrt(pooled_p * (1-pooled_p) * (1/n1 + 1/n2))
z = (p2 - p1) / se
p_value = stats.norm.sf(abs(z)) * 2  # 双尾

print(f"z={z:.2f}, p={p_value:.4f}")
```
