# 数据清洗硬编码审查报告

> **审查日期**：2026-05-19  
> **审查范围**：`hagoku/tools/cleaning.py`、`hagoku/agents/cleaner/agent.py`、`hagoku/guardrails/`、`hagoku/agents/analyst/agent.py`、`hagoku/manager/refinement.py`  
> **审查维度**：① 硬编码模块/阈值确认 ② 客户体验影响

---

## 一、硬编码模块/阈值全景（✅ 已确认）

### 1.1 清洗层 — `hagoku/tools/cleaning.py`

| # | 位置 | 硬编码内容 | 值 | 影响 |
|---|------|-----------|-----|------|
| 1 | L30 | IQR 倍数 | `iqr_multiplier=1.5` | 所有异常值检测的灵敏度——固定 1.5 导致金融/医疗等异方差场景误判率偏高 |
| 2 | L34–35 | 小样本阈值 | `min_samples_for_zscore=30`, `min_samples_for_iforest=50` | n<30 自动跳过 z-score，但 n≈28-29 时客户会困惑为何 z-score 被跳过 |
| 3 | L40 | 离群比例上限 | `max_outlier_pct=0.20` | 若某列 21% 异常值，清洗策略从 winsorize 退化为"标记但不处理"；客户看到 21% 被标记却未修正 |
| 4 | L112–114 | 正态性阈值 | `alpha=0.05`（Shapiro-Wilk） | 当 n>5000 时 SW 测试过敏感，p<0.05 但实际分布近乎正态 |
| 5 | L214–270 | 缺失机制阈值 | MCAR 判定 p=0.05；缺失率分段 ≥0.15/% <0.05/介于之间 | 「15% 缺失率」一刀切决定`drop_column` / `impute` / `drop_rows`三种策略 |
| 6 | L273–327 | IQR 标签分类 | 仅分「normal / mild / extreme」3 档 | 高频交易场景需要 extra-extreme 档来区分噪声和信号 |
| 7 | L536 | 分布偏移阈值 | `sigma_diff=0.1` | 超过 0.1σ 即标记"分布变化"，但对偏态分布敏感 |
| 8 | L608 | 行删除影响率阈值 | `row_deletion_impact=0.05` | 删行>5% → 偏差风险升到 medium |

### 1.2 分析层 — `hagoku/agents/analyst/agent.py`

| # | 位置 | 硬编码内容 | 值 | 客户体验影响 |
|---|------|-----------|-----|------------|
| 9 | L394 | 显著性阈值 | `p < 0.05` | 用户无法调整 α（如 A/B 测试希望 0.01 的严格标准） |
| 10 | L395 | 显著截断 | `p_values[f] < 0.05` | 同上，单个预测变量判定 |
| 11 | L476 | 假设检验阈值 | `p_val < 0.05` | 结果"显著/不显著"二元化，丢失了边际显著（p≈0.05-0.07）的讨论可能 |
| 12 | L518 | Kruskal-Wallis | `p_val < 0.05` | 同上 |
| 13 | L580 | 相关性阈值 | `p < 0.05` | 同上 |
| 14 | L583 | 相关性强度分级 | `abs(r) > 0.7` → 强 / `> 0.4` → 中 / 否则弱 | 心理学标准（0.3/0.5）vs 经济学标准（0.1/0.3）vs 物理学（>0.9），一刀切误导结论 |
| 15 | L626 | 趋势方向判定 | `coeff > 0 → "上升"` / `p_val < 0.05` | 同上显著性，趋势分析被 0.05 硬绑 |
| 16 | L676 | 样本量警告 | `n < 30` | 与工具层 30 阈值重复，且 n<30 时直接 return 不检查功效 |
| 17 | L681–687 | 各组样本量功效 | `n_per_group < 15` 警告 / `n_per_group >= 30` 计算功效 | 对组间不平衡场景（如 12 vs 48）敏感度差 |
| 18 | L691 | 功效百分比 | `power_pct >= 80` → 足够 | 客户可能希望设置 90% 功效 |
| 19 | L696 | 样本量 vs 自变量比 | `n < 10 * n_predictors` | 经验法则 "10 events per variable"，未区分线性/逻辑回归 |
| 20 | L711 | 交叉验证折数 | `k_folds=5` | 始终 5 折 — 小样本时 5 折过少（不稳定），大样本时 5 折过多（算力浪费） |

### 1.3 护栏层 — 部分在 `guardrails/statistical.py`

| # | 位置 | 硬编码内容 | 值 |
|---|------|-----------|-----|
| 21 | guardrails L131 | 效应量 d 分级 | `0.2 = small / 0.5 = medium / 0.8 = large`（Cohen, 1988） |
| 22 | guardrails L147 | R² 报告质量 | `R² < 0.1` → warning |
| 23 | guardrails L162 | 显著性阈值 | `p < 0.05`（含 Bonferroni 校正） |
| 24 | guardrails L200 | 样本量门槛 | `n < 30` → 警告"小样本" |

### 1.4 意图解析层 — 均已暴露可配置接口 ✅

| 模块 | 硬编码内容 | 是否可外部化 |
|------|-----------|------------|
| `query_parser.py` | `INTENT_PATTERNS`、`TARGET_KEYWORDS`、`COLLOQUIAL_MAP`、维度关键词 | ✅ 支持外部 YAML + LLM 兜底 |
| `refinement.py` | `ALLOWED_PATTERNS`、`DIMENSION_KEYWORDS`、`TARGET_KEYWORDS`、`BLOCKED_PATTERNS` | ⚠️ **未**外部化，尚在 `refinement.py` 中硬编码 |

---

## 二、从客户体验角度分析

### 2.1 🟡 中等风险 — 清洗策略透明度不足

**场景**：客户上传销售数据集，某一列 22% 的值被标记为异常。系统选择 "标记但不 winsorize"，因为超过了 `max_outlier_pct=0.20`。客户只看到 "22% 异常值，已标记"，但不清楚为何没有修正。

**根因**：`max_outlier_pct=0.20` 硬编码 + 策略决策过程对用户不透明。

**缓解**：当前 Cleaner agent 的 `prompt.md` 已要求解释 "为何选择该策略"，但若 LLM 调用失败则回退到裸数值。建议在清洗摘要中增加 `policy_reason` 字段，直接展示决策逻辑（面向非技术用户）。

### 2.2 🟡 中等风险 — "显著" 的二元判定让结论过度简化

**场景**：分析师用户跑假设检验，p=0.051。系统输出 "差异不显著"。用户放弃进一步分析——但实际效应量 d=0.48（medium），可能只是样本量不足。

**根因**：`p < 0.05` 硬编码在多处（analyst L394, L476, L518, L580, L626）。Neyman-Pearson 框架的二元决策不适用于探索性分析。

**缓解**：当前 Analyst 已返回 `conclusion_plain` + `conclusion_statistical` 双结论。若 `p ∈ [0.03, 0.07]` 时可追加 "边际显著 — 建议追加样本" 的自然语言提示，避免用户误读。

### 2.3 🟢 低风险 — 意图识别已具备良好兜底

**场景**：用户说 "帮我看看供应链库存周转率"，`query_parser` 的硬编码列表未覆盖 "库存周转率"。

**行为**：`intent_type` fallback 为 `exploration(low)` → 触发 `_llm_fallback_intent()` 启发式 → "库存" 匹配到 `trend` → 置信度升为 `medium`。用户不会看到报错。

**评估**：✅ 客户体验友好。唯 `refinement.py` 的硬编码列表尚未类似对外部化接口。

### 2.4 🟡 低风险 — 效应量分级语义固定

**场景**：心理学研究者用 HaGoKu 分析实验数据，Cohen's d=0.45 被标记为 "中等效应"，但该研究领域通常认为 d=0.4 以下是"小效应"。

**根因**：`guardrails/statistical.py` L131 的 Cohen 分级（0.2/0.5/0.8）硬编码。

**缓解**：在报告阶段用 `conclusion_plain` 自然语言描述（"d=0.45，中等效应量"），客户可自行解读。面向学术场景的产品版本可让用户选择效应量标准（如 Funder & Ozer, 2019）。

---

## 三、整体评估

| 维度 | 评级 | 说明 |
|------|------|------|
| 硬编码程度 | ⚠️ 中等 | 清洗 + 分析层共 ~25 处硬编码阈值；意图解析层已具备外部化机制 |
| 客户可见性 | ✅ 较低 | 多数硬编码在后台运行，不影响结果展示（已有双结论缓冲） |
| 用户体验风险 | 🟡 了解即安全 | p<0.05 和 Cohen 分级是学科常识；真正风险在于 `max_outlier_pct` 等隐蔽参数 |
| 扩展性 | ⚠️ 需加强 | `refinement.py` 的硬编码列表是最后一块未外部化的缺口 |

---

## 四、建议行动（优先级排序）

1. **P1**：将清洗阈值（IQR 倍数、max_outlier_pct、sample_size_min）暴露至 `CleaningConfig`，可在 `hagoku/config.py` 或运行时覆盖
2. **P1**：在清洗摘要中增加 `policy_reason` 字段，向用户解释策略选择逻辑
3. **P2**：`refinement.py` 的 ALLOWED_PATTERNS / DIMENSION_KEYWORDS 外部化（参照 `query_parser.py` 已完成的模式）
4. **P2**：Analyst 对 p ∈ [0.03, 0.07] 追加 "边际显著" 提示
5. **P3**：添加 CI lint 规则（如 ruff 自定义插件检测裸的 `p < 0.05` 字面量）
6. **P3**：效应量分级支持配置化（学科特定标准）