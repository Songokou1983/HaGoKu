# Analyst Agent Memory

## 分析模式库

> 记录每个项目已完成的分析类型、有效方法和结论。
> Analyst 启动时自动读取此文件，同类数据直接复用经验。

```yaml
analysis_patterns: {}
```

### 分析模式格式（自动生成）

```yaml
analysis_patterns:
  ad_campaign_2026:
    data_signature: "12 列, 1 标识列, 1 数值目标变量(Conversion), 3 数值特征, 5000 行, 缺失率 2%"
    effective_methods:
      - type: "spearman_correlation"
        question: "Inc1 与 Inc2 的关联？"
        significance: "significant"
        effect_size: "medium (ρ=0.42)"
        date: "2026-05-20"
      - type: "regression"
        question: "Conversion 的预测因素是什么？"
        significance: "significant"
        effect_size: "large (R²=0.72)"
        date: "2026-05-20"
      - type: "ttest"
        question: "channel A 和 B 的 Conversion 有差异吗？"
        significance: "significant"
        effect_size: "small (d=0.18)"
        date: "2026-05-20"
    ineffective_methods:
      - type: "pearson_correlation"
        reason: "Inc2 为有序评分(1-5), Pearson 不适合, Spearman 才有效"
        date: "2026-05-20"
```

### 跨项目经验复用

当 Analyst 遇到新项目时：
1. 自动提取数据签名：列数、变量类型、样本量、缺失率
2. 在 analysis_patterns 中搜索最相似的数据签名
3. 复用有效方法列表（如"同类数据先用 Spearman 而非 Pearson"）
4. 跳过低效方法（如"评分列别用 Pearson"）

## 用户研究问题

```yaml
user_queries: {}
```

## 分析偏好

```yaml
preferences: {}
```

---

> **LLM 主导原则**：记忆是 LLM 的参考，不是硬约束。每次分析时 LLM 自主决定是否复用、如何复用。