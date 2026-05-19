# 数据清洗代码审查：硬编码模块诊断 & 客户体验视角

> 审查范围：`hagoku/agents/cleaner/`、`hagoku/tools/cleaning.py`、`hagoku/manager/orchestrator.py`、`hagoku/config.py`
> 生成时间：2026-05-19

---

## 一、硬编码模块清单

### 1.1 `suggest_cleaning_strategy()` — 完全硬编码的规则引擎

**位置**：`hagoku/tools/cleaning.py:484-527`

```python
if null_rate > 0.5:
    return CleaningStrategy.DROP_COLUMN, f"缺失率 {null_rate:.1%} > 50%，建议删除列"
if null_rate < 0.02:
    return CleaningStrategy.DROP_ROWS, f"缺失率 {null_rate:.1%} < 2%，删除行影响极小"
if missing_mechanism == "mcar":
    if null_rate < 0.1:
        return CleaningStrategy.DROP_ROWS, f"MCAR 且缺失率 {null_rate:.1%} < 10%，删除行安全"
    return CleaningStrategy.FILL_MEDIAN, f"MCAR 但缺失率 {null_rate:.1%} 较高，中位数填充"
if missing_mechanism == "mar":
    return CleaningStrategy.MULTIPLE_IMPUTATION, "MAR 缺失，建议多重插补以减少偏差"
return CleaningStrategy.FLAG_AND_KEEP, "MNAR 缺失，建议标记缺失而非删除，避免引入偏差"
```

**问题**：这段代码是一个纯 if/elif 决策树，完全没有 LLM 参与。当 `auto_strategy=True`（默认值）时，`clean_data()` 会绕过 Cleaner Agent 的 LLM 规划，直接用这套硬编码规则。用户看到的是"系统自动决定"，但实际依据的是写死的 50%/2%/10% 三个阈值。

**客户体验影响**：
- 用户数据缺失 51% → 整列被删，用户不知道为什么是 50% 不是 40%
- 用户数据缺失 1.9% → 行被删，用户不知道这个阈值是否可以调整
- 阈值对任何业务场景一视同仁：金融风控数据和电商浏览数据的容忍度完全不同

---

### 1.2 `assess_bias_risk()` — 硬编码的风险分级阈值

**位置**：`hagoku/tools/cleaning.py:603-640`

```python
if impact_rate > 0.20:
    return "high", ...
if impact_rate > 0.10:
    return "medium", ...
if impact_rate > 0.05:  # 仅当有 MNAR 列时
    return "high", ...
if len(large_shift) >= 2:  # large_shift = s > 0.3
    return "medium", ...
return "low", "影响率低，缺失机制为 MCAR/MAR，偏差风险低"
```

**客户体验影响**：
- 影响率 9.9% → "低风险"，10.1% → "中风险"。用户看到的是一个魔术数字
- `distribution_shift > 0.3σ` 的阈值 0.3 是写死的，用户不知道 0.29 和 0.31 的区别
- "偏差风险低"的结论可能给用户虚假的安全感——实际上 MCAR/MAR 也可能引入偏差

---

### 1.3 `_assess_quality()` — 硬编码的数据质量分级

**位置**：`hagoku/agents/cleaner/agent.py:470-479`

```python
if outlier_count / max(n_rows, 1) > 0.1 or null_count / max(n_rows * len(df.columns), 1) > 0.2:
    return "poor"
elif outlier_count / max(n_rows, 1) > 0.05 or null_count / max(n_rows * len(df.columns), 1) > 0.1:
    return "medium"
return "good"
```

**客户体验影响**：
- "poor"/"medium"/"good" 三级标签仅基于统计量，不考虑业务场景
- 10% 异常值可能是正常业务波动（如促销期订单量），不应标为"poor"
- 用户看到"数据质量：poor"时可能恐慌，但实际数据完全可用

---

### 1.4 `PLAN_TEMPLATES` + `KEYWORD_MAP` — 硬编码的分析类型映射

**位置**：`hagoku/manager/orchestrator.py:30-59`

```python
KEYWORD_MAP: dict[str, str] = {
    r"趋势|变化|增长|下降|走势|上升|波动": "趋势分析",
    r"差异|对比|比较|不同|A/B|ab测试|是否不同": "差异比较",
    r"因果|影响|导致|因为|效果|是否有效": "因果推断",
    r"相关|关系|联系|关联|有关": "相关性分析",
    r"画像|概况|什么数据|什么样|描述|概览": "数据画像",
}
```

**客户体验影响**：
- 用户输入"这个活动对销量有什么影响"→匹配到"因果推断"，但用户可能只想看"差异比较"
- 正则匹配是贪婪的，可能存在歧义（"趋势"和"相关"同时出现在查询中）
- 用户无法自定义分析类型，系统替用户做了决策

---

### 1.5 `winsorize_column()` 默认截断比例

**位置**：`hagoku/tools/cleaning.py:458-462`

```python
def winsorize_column(series, lower=0.05, upper=0.05):
```

**问题**：固定 5% 双向截断。对于正态分布数据合理，但对严重右偏数据（如收入），下 5% 截断无意义。

---

### 1.6 `CleaningConfig` 默认参数

**位置**：`hagoku/config.py:64-69`

```python
class CleaningConfig(BaseModel):
    isolation_forest_n_estimators: int = 100
    iterative_imputer_max_iter: int = 10
    random_state: int = 42
```

**客户体验影响**：
- `random_state=42` 固定种子 → 每次运行结果相同，看似"稳定"但掩盖了模型不确定性
- 用户不知道这些参数的存在，也无法调整

---

### 1.7 `_cleaning_quality_display()` — 用户不可见的兜底文案引擎

**位置**：`hagoku/manager/orchestrator.py:649-672`

```python
def _cleaning_quality_display(report, *, impact_rate, t_orig, t_after, fallback_label):
    raw = (fallback_label or "").strip()
    if raw and raw.lower() != "unknown":
        return raw
    if t_after < t_orig:
        return "有删行"
    if impact_rate > 0.12:
        return "高影响（删行计）"
    if impact_rate > 0.04:
        return "中影响（删行计）"
    br = str(getattr(report, "bias_risk", "") or "").lower()
    if br in ("high", "medium"):
        return f"偏差风险 {br}"
    return "—"
```

**问题**：当 CleanerAgent 的 `data_quality` 为 `unknown` 时，编排层自行用一套硬编码规则生成中文标签。用户看到 "高影响（删行计）" 时，不知道这是 Cleaner 的结论还是 Orchestrator 的兜底。0.12 / 0.04 两个阈值与 Cleaner 内部阈值不一致——可能出现 Cleaner 说"中风险"但前端显示"高影响"的矛盾。

---

### 1.8 `clean_data()` 默认 `auto_strategy=True` — 自动模式下完全由代码输出结果

**位置**：`hagoku/tools/cleaning.py:646-832`

```python
def clean_data(df, operations=None, *, auto_strategy=True, ...):
```

当 `auto_strategy=True`（默认值），且未传入 `operations` 时：
1. 代码自动调用 `detect_missing_mechanism()` → 返回纯代码计算的机制标记
2. 代码自动调用 `suggest_cleaning_strategy()` → 返回纯代码决策的策略
3. 代码自动调用 `assess_bias_risk()` → 返回纯代码计算的风险等级
4. `impact_warning > impact_rate` 时自动追加代码生成的警告文案

**整个清洗决策链路无 LLM 参与，用户看到的结果 100% 由代码生成。**

---

### 1.9 Guardrails 规则 — 4 条硬编码的中文判断 + 文案

**位置**：`hagoku/guardrails/statistical.py:58-135`

| 规则 | 触发条件 | 对用户输出的硬编码中文 |
|------|---------|---------------------|
| `NoConclusionWithoutTest` | 有结论但无统计检验 | "下了结论但没有数据支撑，可能是分析类型选错了" |
| `MustReportEffectSize` | 有 p 值但无效应量 | "只说明了有没有差异，没说差异有多大，结论不够完整" |
| `MustReportCI` | 有点估计但无置信区间 | "只给了估计值，没说这个估计靠不靠谱" |
| `NoCausalClaimWithoutMethod` | 含因果词汇但无因果方法 | （继续阅读后续代码） |

**问题**：这些规则通过代码中的 if/else 判断结果是否完整，并用写死的中文文案输出给用户。LLM 无法参与裁决——即使 LLM 认为某个场景不需要置信区间，护栏依然会阻断。

---

### 1.10 `_cleaner_reply_accepts_proceed()` — 硬编码的确认词表

**位置**：`hagoku/manager/orchestrator.py:185-195`

```python
_STAGE_CLEANER_PROCEED_RE = re.compile(
    r"^(确认(?:继续|无误)?|好的|是|没问题|对的|正确|通过|ok|okay|yes)[\s!！。,\-\.]*$",
    re.I,
)
```

**问题**：用户回复是否表示"同意继续"由一个正则表达式决定。如果用户说 "看起来没问题，可以往下走了"，这个正则会判定为不同意，进入无限循环。

---

### 1.11 `_learn_from_results()` — 硬编码的风险分级阈值

**位置**：`hagoku/agents/cleaner/agent.py:703`

```python
risk = "low" if op.get("impact", 0) < 0.05 else "medium"
```

**问题**：学习记忆系统也用了写死的 5% 阈值，与前述其他阈值不一致（0.10/0.12/0.20），进一步加剧了阈值碎片化。

---

### 1.12 `_plan_via_llm()` 的 system_prompt — 硬编码的指令文本

**位置**：`hagoku/agents/cleaner/agent.py:501-606`

整个 system_prompt 在 Python 代码中通过字符串拼接构建，包含：
- 硬编码的策略枚举："winsorize / drop_rows / fill_median / fill_mean / fill_mode / fill_mcar / skip"
- 硬编码的输出格式要求："`operations` 数组"
- 硬编码的语气指令："统计依据（面向用户，用通俗语言，IQR 法改为分位数范围法）"

虽然这是 prompt 而非结果输出，但这些指令决定了 LLM 的行为模式，且完全写死在代码中，无法通过配置调整。

---

## 二、客户体验综合诊断

### 2.1 透明度问题

| 维度 | 现状 | 用户体验问题 |
|------|------|-------------|
| 清洗策略选择 | LLM 规划 + 硬编码规则引擎双路径 | 用户不知道当前走的是哪条路径 |
| 阈值来源 | 代码中写死的数字（至少 8 个不同阈值） | 用户看到"缺失率 > 50% 删列"但不知道为什么是 50% |
| 风险评级 | 硬编码 if/elif 决策树 × 3 处 | 同一份数据可能在不同层级被评出不同风险 |
| 分析类型 | 正则关键词匹配 | 用户可能被匹配到错误的模板 |
| 数据质量标签 | 三层兜底：Cleaner → Orchestrator → 硬编码 fallback | 用户看到"高影响（删行计）"不知是谁的判断 |
| Guardrails 阻断 | 硬编码 if/else + 固定中文文案 | 用户被阻止时看到的是代码死文案，非 LLM 解释 |

### 2.2 可控性问题

| 维度 | 现状 | 用户体验问题 |
|------|------|-------------|
| 阈值可调性 | 仅 `impact_warning` 可通过 API 传入，10+ 其他阈值均不可调 | 用户无法根据业务场景调整敏感度 |
| 策略否决 | 支持用户确认/修正 | 较好，但确认前的策略生成过程不可见 |
| 回滚能力 | 无 | 用户执行清洗后无法撤销 |
| 确认机制 | 正则匹配固定词表 | 用户说"可以往下走了"不被识别为确认 |

### 2.3 信任问题

- **魔术数字泛滥**：50%、20%、12%、10%、5%、4%、2%、0.3σ —— 至少 8 个不同阈值分布在 5 个文件中
- **阈值不一致**：`assess_bias_risk` 用 10%/20%，`_cleaning_quality_display` 用 4%/12%，`_learn_from_results` 用 5%，`_assess_quality` 用 5%/10%
- **三层兜底链路**：Cleaner Agent → Orchestrator `_cleaning_quality_display` → 最终回退 "—"，用户不知道自己在哪一层
- **Guardrails 绕过 LLM**：规则引擎直接判定 + 输出固定文案，LLM 的解释能力完全未利用

---

## 三、完整硬编码清单（汇总）

| # | 模块 | 文件:行号 | 类型 | 硬编码内容 |
|---|------|-----------|------|-----------|
| 1 | `suggest_cleaning_strategy()` | `cleaning.py:484` | **代码输出结果** | 6 个 if/elif + 阈值 50%/2%/10%，返回策略+原因文案 |
| 2 | `assess_bias_risk()` | `cleaning.py:603` | **代码输出结果** | 5 个 if/elif + 阈值 20%/10%/5%/0.3σ，返回中文风险等级+原因 |
| 3 | `_assess_quality()` | `cleaner/agent.py:745` | **代码输出结果** | poor/medium/good 三级判定，阈值 5%/10%（异常值）, 10%/20%（缺失） |
| 4 | `_cleaning_quality_display()` | `orchestrator.py:649` | **代码兜底** | data_quality 未知时，用 4%/12% 阈值生成"高影响""中影响"等标签 |
| 5 | `PLAN_TEMPLATES` + `KEYWORD_MAP` | `orchestrator.py:30` | **代码决策** | 5 组正则关键词→分析类型硬映射 |
| 6 | `winsorize_column()` | `cleaning.py:458` | **代码默认值** | `lower=0.05, upper=0.05` 固定截断比例 |
| 7 | `CleaningConfig` | `config.py:64` | **代码默认值** | `random_state=42`, `n_estimators=100`, `max_iter=10` |
| 8 | `clean_data()` auto_strategy 模式 | `cleaning.py:646` | **代码输出结果** | 串联 #1+#2 全自动生成清洗报告，无 LLM 参与 |
| 9 | Guardrails 4 条强制规则 | `guardrails/statistical.py:58` | **代码输出结果** | 硬编码 if/else + 中文阻断文案 |
| 10 | `_cleaner_reply_accepts_proceed()` | `orchestrator.py:185` | **代码决策** | 正则匹配固定确认词表 |
| 11 | `_learn_from_results()` | `cleaner/agent.py:703` | **代码决策** | 硬编码 5% 阈值判定风险等级 |
| 12 | `_plan_via_llm()` system_prompt | `cleaner/agent.py:501` | **代码控制** | 硬编码指令文本决定 LLM 行为边界 |

### 类型分布

| 类型 | 数量 | 说明 |
|------|------|------|
| **代码输出结果**（替换 LLM） | 5 处 | #1, #2, #3, #8, #9 |
| **代码兜底**（LLM 失败时补位） | 1 处 | #4 |
| **代码决策**（绕过 LLM） | 3 处 | #5, #10, #11 |
| **代码默认值**（不可配置） | 2 处 | #6, #7 |
| **代码控制**（限制 LLM） | 1 处 | #12 |


