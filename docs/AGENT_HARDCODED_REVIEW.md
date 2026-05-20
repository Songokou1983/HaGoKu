# Agent 硬编码审查报告

> 审查范围：Scout、Analyst、Reporter、Scribe 四个 Agent 及其依赖的工具模块、配置系统  
> 审查日期：2026-05-20  
> 审查视角：数值/阈值/行为硬编码 + 客户体验影响

---

## 目录

1. [总览与评级](#1-总览与评级)
2. [Scout Agent 硬编码清单](#2-scout-agent)
3. [Analyst Agent 硬编码清单](#3-analyst-agent)
4. [Reporter Agent 硬编码清单](#4-reporter-agent)
5. [Scribe Agent 硬编码清单](#5-scribe-agent)
6. [跨 Agent 共性问题](#6-跨-agent-共性问题)
7. [工具模块硬编码](#7-工具模块硬编码)
8. [配置系统现状与差距](#8-配置系统现状与差距)
9. [客户体验影响评估](#9-客户体验影响评估)
10. [修复优先级建议](#10-修复优先级建议)

---

## 1. 总览与评级

| Agent | 硬编码项数量 | 严重度 | 客户可感知风险 |
|-------|-------------|--------|---------------|
| Scout | 12 | **高** | 字段名截断、误解导致后续分析全部偏离 |
| Analyst | 10 | **高** | 显著性阈值/样本量阈值直接决定分析结论对错 |
| Reporter | 7 | **中** | 报告排版截断、部分发现被隐藏 |
| Scribe | 4 | **低** | 仅在日志/兜底场景，用户不可见 |
| **合计** | **33** | — | — |

**评级标准：**
- **严重**：硬编码值直接影响分析结论的正确性（如 p 值阈值、样本量门槛）
- **中等**：硬编码值影响用户体验但不影响正确性（如截断长度、显示格式）
- **轻微**：仅在调试/日志路径，用户不可见的硬编码

---

## 2. Scout Agent

**文件：** `hagoku/agents/scout/agent.py`

### 2.1 字段名/值显示截断（用户体验类）

| # | 位置 | 硬编码值 | 含义 | 影响 |
|---|------|---------|------|------|
| 1 | L46, L48 | `len(left.strip()) > 64` | 解析 LLM 输出的列名长度上限 | 超过 64 字符的列名被丢弃，导致该列完全不被理解 |
| 2 | L84 | `len(s) > 20` | 样本值显示截断 | 长值（如 URL、长文本）尾部分丢失 → 用户无法根据示例判断字段含义 |
| 3 | L83-84 | `s[:17] + "…"` | 截断后长度 17 字符 + "…" | 同上，且截断硬连字符 |
| 4 | L670 | `len(label) > 30` | top_values 的标签截断 | 高频值标签被截断 |
| 5 | L669 | `label[:27] + "…"` | 截断后长度 27 字符 | 同上 |

### 2.2 LLM 调用参数（行为类）

| # | 位置 | 硬编码值 | 含义 | 影响 |
|---|------|---------|------|------|
| 6 | L516 | `max_tokens=4096` | 字段推断 LLM 调用的 token 上限 | 列数过多时 LLM 输出被截断 → 部分列完全丢失 |
| 7 | L518 | `temperature=0.0` | 字段推断温度 | 虽然设 0.0 合理（确定性），但不可配置 |
| 8 | L801 | `temperature=0.5` | 确认消息生成温度 | 确认消息可能不稳定，导致每次显示不同 |
| 9 | L802 | `max_tokens=1200` | 确认消息生成 token 上限 | 多字段时确认消息被截断 |

### 2.3 数据分析判断（行为类）

| # | 位置 | 硬编码值 | 含义 | 影响 |
|---|------|---------|------|------|
| 10 | L649 | `maxv > q75v * 10` | "严重右偏" 判定因子 | 分布形状识别阈值不可调 |
| 11 | L651 | `maxv > q75v * 3` | "右偏" 判定因子 | 同上 |
| 12 | L653 | `pct < q25 * 0.3` | "左偏" 判定因子 | 同上 |
| 13 | L664 | `n_unique < 100` | 判定为"适合展示 top-values" 的唯一值数上限 | 唯一值 99 个展示 top-5，101 个完全不展示 → 断崖式体验 |
| 14 | L820 | `confidence < 0.85` | 学习阈值：只学习置信度 ≥0.85 的推断 | 0.84 置信度的有价值推断被丢弃 |
| 15 | L830 | `similarity > 0.9` | 去重阈值：已有条目相似度 > 0.9 则跳过 | 可能漏掉细微但重要的语义差异 |

---

## 3. Analyst Agent

**文件：** `hagoku/agents/analyst/agent.py`

### 3.1 统计显著性阈值（结论类 — 最严重）

| # | 位置 | 硬编码值 | 含义 | 影响 |
|---|------|---------|------|------|
| 1 | L394 | `p_values[f] < 0.05` | 回归显著预测变量筛选 | **分析结论直接依赖此值** |
| 2 | L476 | `p_val < 0.05` | 两样本假设检验显著性 | 同上 |
| 3 | L518 | `p_val < 0.05` | 多样本假设检验显著性 | 同上 |
| 4 | L580 | `p < 0.05` | 相关性显著性 | 同上 |
| 5 | L628 | `p_val < 0.05` | 趋势分析显著性 | 同上 |

**合计 5 处硬编码 `0.05`**，而 `config.py` 中 `AnalysisConfig.p_value_threshold = 0.05` 已经定义了该值，但这些地方没有引用它。

> ⚠️ **Config 已定义 `AnalysisConfig.p_value_threshold`，但 Agent 代码中硬编码了 5 处 `0.05`，形成「有配置但不使用」的假象。**

### 3.2 样本量/数据量阈值（行为类）

| # | 位置 | 硬编码值 | 含义 | 影响 |
|---|------|---------|------|------|
| 6 | L677 | `if n < 30` | 功效预检：数据量偏少门槛 | 29 条数据 → "功效不足"警告，31 条 → 无警告 |
| 7 | L686 | `if n_per_group < 15` | 每组样本偏少门槛 | 同上，断崖式 |
| 8 | L688 | `if n_per_group >= 30` | 每组样本充足门槛 | 同上 |
| 9 | L697 | `n < 10 * n_predictors` | 样本量-自变量比例门槛 | 1:10 规则硬编码，不同领域标准不同 |

### 3.3 知识库去重（行为类）

| # | 位置 | 硬编码值 | 含义 | 影响 |
|---|------|---------|------|------|
| 10 | L788 | `similarity > 0.85` | 分析经验去重阈值 | 和 Scout 的 0.9 不一致，暗示 Agent 间阈值规范不统一 |

---

## 4. Reporter Agent

**文件：** `hagoku/agents/reporter/agent.py`

### 4.1 显示截断（用户体验类）

| # | 位置 | 硬编码值 | 含义 | 影响 |
|---|------|---------|------|------|
| 1 | L326 | `len(headline) > 80` / `headline[:77] + "..."` | headline 截断 | 长结论被截断，关键信息丢失 |
| 2 | L377 | `len(headline) > 60` / `headline[:57] + "..."` | 关键发现 headline 截断 | 同上 |
| 3 | L434 | `len(headline) > 80` / `headline[:77] + "..."` | 结果章节 headline 截断 | 同上 |

### 4.2 硬编码映射表（行为类）

| # | 位置 | 硬编码值 | 含义 | 影响 |
|---|------|---------|------|------|
| 4 | L424-428 | `title_map` dict | 分析类型 → 章节标题映射 | 新增分析类型时此表需手动同步 |
| 5 | L414 | `p < 0.05` | 整体摘要中的显著性判断 | 与 Analyst 保持同步的需求，但又是硬编码 |

### 4.3 其他

| # | 位置 | 硬编码值 | 含义 | 影响 |
|---|------|---------|------|------|
| 6 | L580 | `abs(r) > 0.7` / `0.4` | 相关性强/中/弱判定 | 来自 Analyst 代码，但也是硬编码 |
| 7 | L311 | `existing[0]["similarity"] > 0.9` | 报告场景去重 | Scout 也是 0.9 |

---

## 5. Scribe Agent

**文件：** `hagoku/agents/_scribe/agent.py`

| # | 位置 | 硬编码值 | 含义 | 影响 |
|---|------|---------|------|------|
| 1 | L192 | `summary[:80]` | 工具结果日志截断 | 仅影响 process_log.md，用户不可见 |
| 2 | L182 | `thought[:100]` | thinking 日志截断 | 同上 |
| 3 | L457 | `max_tokens=max(256, len(missing) * 64)` | 兜底 LLM token 计算 | 64 token/列 的估算可能不准确 |
| 4 | L458 | `response_format={"type": "json_object"}` | JSON 模式调用 | 可接受，但 temperature=0.1(L456) 也硬编码 |

---

## 6. 跨 Agent 共性问题

### 6.1 显著性阈值 `0.05` 遍布各处

| 位置 | Agent | 使用方式 |
|------|-------|---------|
| `config.py:59` | Config | `AnalysisConfig.p_value_threshold = 0.05` ✅ 已定义 |
| `agent.py:394` | Analyst | `p_values[f] < 0.05` ❌ 硬编码 |
| `agent.py:476` | Analyst | `p_val < 0.05` ❌ 硬编码 |
| `agent.py:518` | Analyst | `p_val < 0.05` ❌ 硬编码 |
| `agent.py:580` | Analyst | `p < 0.05` ❌ 硬编码 |
| `agent.py:628` | Analyst | `p_val < 0.05` ❌ 硬编码 |
| `agent.py:414` | Reporter | `p < 0.05` ❌ 硬编码 |

**Config 已定义，但 Agent 代码从未引用 `self.llm_config` 以外的任何配置对象。**

### 6.2 代码重复：_load_memory / _save_memory

Scout、Analyst、Reporter 三个 Agent 中 `_load_memory()` 和 `_save_memory()` 的实现模式几乎一致（从 `memory.md` 读 YAML、写回），差异仅在正则 pattern 和 key 名称。这是技术债，但不是硬编码问题。

### 6.3 LLM 温度/Token 参数

所有 Agent 的 LLM 调用中 `temperature` 和 `max_tokens` 均为硬编码文字常量，未从 Config 读取。`LLMConfig` 虽有 `temperature` 和 `max_tokens` 字段，但实际上**没有任何 Agent 使用它们**。

### 6.4 相似度去重阈值不一致

| Agent | 阈值 | 用途 |
|-------|------|------|
| Scout | 0.9 | 字段推断知识库去重 |
| Analyst | 0.85 | 分析方法知识库去重 |

无文档解释为何不同。

---

## 7. 工具模块硬编码

### 7.1 `hagoku/tools/health.py`

| # | 位置 | 硬编码值 | 含义 |
|---|------|---------|------|
| 1 | L244 | `token_rate_tok_s < 5` | "Token 速率慢" 判定阈值（5 tok/s） |

### 7.2 `hagoku/tools/diagnostics.py`

| # | 位置 | 硬编码值 | 含义 |
|---|------|---------|------|
| 1 | L96-100 | `1.5 < dw < 2.5` | Durbin-Watson 自相关判定区间 |

### 7.3 `hagoku/tools/analysis.py`

| # | 位置 | 硬编码值 | 含义 |
|---|------|---------|------|
| 1 | L517 | `actual_k = min(k_folds, n // min_n)` | `min_n = len(features) + 3`（L505），交叉验证最小样本公式硬编码 |

---

## 8. 配置系统现状与差距

### 8.1 已有的可配置项（来自 `config.py`）

| Config 类 | 字段 | 默认值 | Agent 是否使用 |
|-----------|------|--------|---------------|
| `AnalysisConfig` | `p_value_threshold` | 0.05 | ❌ 未使用 |
| `AnalysisConfig` | `random_state` | 42 | ✅ 部分使用（analysis.py 引用 `_config`） |
| `AnalysisConfig` | `shapiro_sample_limit` | 5000 | ✅ 部分使用 |
| `AnalysisConfig` | `overfitting_gap_threshold` | 0.2 | ✅ 使用 |
| `CleaningConfig` | 全部 | 各项 | ✅ 使用（通过 `set_cleaning_config`） |
| `LLMConfig` | `temperature` | 0.6 | ❌ 未被 Agent 代码引用 |
| `LLMConfig` | `max_tokens` | 8192 | ❌ 未被 Agent 代码引用 |

### 8.2 应该可配置但硬编码的值

| 配置项 | 当前状态 | 建议增加到 |
|--------|---------|-----------|
| 显著性阈值 0.05 | 已有 `AnalysisConfig.p_value_threshold` 但 Agent 不使用 | 让 Agent 读取配置 |
| 样本量门槛 (30/15/10x) | 硬编码在 Analyst | `AnalysisConfig` |
| LLM temperature (各 Agent) | 硬编码在各自文件中 | 各 Agent 从 `LLMConfig.temperature` 读取 |
| LLM max_tokens (各 Agent) | 硬编码 | 各 Agent 从 `LLMConfig.max_tokens` 读取或按场景配置 |
| 分布形状阈值 (3x/10x/0.3) | 硬编码在 Scout | `AnalysisConfig` |
| 截断长度 (17/27/60/80) | 硬编码在各 Agent | `ManagerModeConfig` 或新 `DisplayConfig` |
| 去重相似度 (0.85/0.9) | 硬编码不一致 | 统一到一个配置值 |
| Token 速率阈值 (5 tok/s) | 硬编码在 health.py | 不适合配置（仅警告），但目前是魔法数字 |

---

## 9. 客户体验影响评估

### 9.1 高危：直接导致分析结论错误

| 场景 | 硬编码值 | 用户感知 | 后果 |
|------|---------|---------|------|
| 金融风控需要 p<0.01 的严格标准 | `p_value < 0.05` 硬编码在 6 处 | 报告显示"显著"但实际不满足业务标准 | **依报告做决策可能出错** |
| 小样本医学研究 (n=25) | `n < 30` 触发"功效不足"警告 | 用户被警告但无法调整（数据就这么大） | 信任危机：系统无法适应特殊场景 |
| 200 列宽表 | `max_tokens=4096` 截断 LLM 输出 | 后半部分列丢失，静默失败 | **用户不知道有些列没被分析** |

### 9.2 中危：用户体验断裂

| 场景 | 硬编码值 | 用户感知 | 后果 |
|------|---------|---------|------|
| 列名"customer_lifetime_value_forecast_2024_q4_adjusted" | 64 字符限制截断 | 该列完全不被理解，needs_user_input=True | 用户反复确认无意义的字段 |
| 样本值"https://api.example.com/v2/..." | 20 字符截断 | 显示 "https://api.examp…" 看不出是 URL | 用户无法根据截断后的值判断字段类型 |
| 99 个唯一值 vs 101 个唯一值 | `n_unique < 100` 阈值 | 前者显示 top-5 高频值，后者完全不显示 | 断崖式体验差异 |

### 9.3 低危：代码腐化风险

| 场景 | 问题 | 后果 |
|------|------|------|
| 新增分析类型（如 survival_analysis） | Reporter 的 `title_map` 硬编码表需手动同步 | 新增分析类型忘记同步 → 报告章节标题显示默认 |
| 多个 Agent 各自硬编码 `0.05` | 修改时需改 6 处 | 漏改一处 → 行为不一致 |

---

## 10. 修复优先级建议

### P0 — 必须修复（影响分析结论正确性）

1. **Analyst Agent：统一引用 `AnalysisConfig.p_value_threshold`**
   - 将 `analyst/agent.py` 中全部 5 处 `0.05` 替换为从配置读取
   - Reporter 中的 1 处也同步替换

2. **Scout Agent：`max_tokens=4096` 改为按列数动态计算**
   - 公式：`max(2048, min(8192, n_cols * 150))` — 每列约 150 token 开销
   - 或至少增大到 8192

3. **Scout Agent：L46/48 的 `64` 字符列名限制移除或放宽到 128+**
   - 列为名长不是问题，需要的是在 LLM prompt 中做截断而非直接丢弃

### P1 — 应该修复（影响用户体验一致性）

4. **样本值/标签截断：统一为可配置值**
   - 新增 `DisplayConfig.truncate_sample_value` (默认 40) 替代 20
   - 新增 `DisplayConfig.truncate_label` (默认 60) 替代 30

5. **统一去重相似度阈值：0.85 或 0.9 二选一**
   - 推荐 0.85（更保守，不丢新知识）

6. **LLM temperature/max_tokens：让 Agent 读取 `LLMConfig`**
   - 或为各 Agent 场景定义独立配置（如 `ScoutConfig.temperature`）

### P2 — 建议修复（技术债清理）

7. **分布形状阈值（3x/10x/0.3）：移到 `AnalysisConfig`**
8. **样本量/比例阈值（30/15/10x）：移到 `AnalysisConfig`**
9. **Reporter 的 `title_map`：改为从分析类型元数据注册表读取**
10. **提取 `_load_memory` / `_save_memory` 公共基类，减少重复代码**

---

## 附录：硬编码项完整索引

```
hagoku/agents/scout/agent.py:46     len(left.strip()) > 64         —— 列名长度截断
hagoku/agents/scout/agent.py:84     len(s) > 20                    —— 样本值截断
hagoku/agents/scout/agent.py:84     s[:17] + "…"                   —— 截断长度
hagoku/agents/scout/agent.py:516    max_tokens=4096                 —— LLM token
hagoku/agents/scout/agent.py:518    temperature=0.0                 —— LLM 温度
hagoku/agents/scout/agent.py:649    maxv > q75v * 10                —— 严重右偏阈值
hagoku/agents/scout/agent.py:651    maxv > q75v * 3                 —— 右偏阈值
hagoku/agents/scout/agent.py:653    min < q25 * 0.3                 —— 左偏阈值
hagoku/agents/scout/agent.py:664    n_unique < 100                  —— top-values 门槛
hagoku/agents/scout/agent.py:670    len(label) > 30                 —— 标签截断
hagoku/agents/scout/agent.py:801    temperature=0.5                 —— LLM 温度
hagoku/agents/scout/agent.py:802    max_tokens=1200                 —— LLM token
hagoku/agents/scout/agent.py:820    confidence < 0.85               —— 学习阈值
hagoku/agents/scout/agent.py:830    similarity > 0.9                —— 去重阈值
hagoku/agents/scout/agent.py:848    not isinstance(self.memory.get("fields"), dict) —— None 防御

hagoku/agents/analyst/agent.py:394  p_values[f] < 0.05             —— 显著性
hagoku/agents/analyst/agent.py:476  p_val < 0.05                   —— 显著性
hagoku/agents/analyst/agent.py:518  p_val < 0.05                   —— 显著性
hagoku/agents/analyst/agent.py:580  p < 0.05                       —— 显著性
hagoku/agents/analyst/agent.py:628  p_val < 0.05                   —— 显著性
hagoku/agents/analyst/agent.py:677  n < 30                         —— 样本量门槛
hagoku/agents/analyst/agent.py:686  n_per_group < 15               —— 每组件本门槛
hagoku/agents/analyst/agent.py:688  n_per_group >= 30              —— 每组件本充足门槛
hagoku/agents/analyst/agent.py:697  n < 10 * n_predictors          —— 比例门槛
hagoku/agents/analyst/agent.py:788  similarity > 0.85              —— 去重阈值

hagoku/agents/reporter/agent.py:326 len(headline) > 80             —— headline 截断
hagoku/agents/reporter/agent.py:377 len(headline) > 60             —— 关键发现截断
hagoku/agents/reporter/agent.py:414 p < 0.05                       —— 显著性
hagoku/agents/reporter/agent.py:424  title_map dict                —— 硬编码映射表
hagoku/agents/reporter/agent.py:434 len(headline) > 80             —— 结果标题截断
hagoku/agents/reporter/agent.py:492 not isinstance(self.memory.get("reports"), dict) —— None 防御

hagoku/agents/_scribe/agent.py:182  thought[:100]                  —— 日志截断
hagoku/agents/_scribe/agent.py:192  summary[:80]                   —— 日志截断
hagoku/agents/_scribe/agent.py:457  max_tokens=max(256, len(missing) * 64) —— LLM token

hagoku/tools/health.py:244          token_rate_tok_s < 5           —— 速率阈值
hagoku/tools/diagnostics.py:96      1.5 < dw < 2.5                 —— DW 区间
```

---

*本文档生成于 2026-05-20，供团队评审和修复跟踪使用。*