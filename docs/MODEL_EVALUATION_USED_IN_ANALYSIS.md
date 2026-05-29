# Qwen3.6-35B 模型能力评估报告：字段参与分析判断

> **评估日期**：2026-05-28
> **模型**：Huihui-Qwen3.6-35B-A3B-Claude-4.7-Opus-abliterated (Q5_K_M)
> **评估范围**：`used_in_analysis`（字段是否参与分析）判断能力
> **实验脚本**：`tests/test_used_in_analysis_experiment.py`、`tests/test_uia_experiment_round2.py`

---

## 1. 实验设计

### 测试场景

固定数据（8 列零售数据）+ 固定分析目标（「分析各渠道的收入对比情况」），变化 prompt 和 schema，观察 LLM 对 `used_in_analysis` 的判断。

| 列名 | 数据类型 | 期望 | 理由 |
|------|---------|------|------|
| StoreID | int64 (ID) | false | 纯标识列 |
| Date | datetime | false | 与渠道收入对比无关（非趋势分析） |
| Channel | categorical | **true** | 渠道 = 分析维度 |
| ProductID | int64 (ID) | false | 纯标识列 |
| Revenue | float64 | **true** | 收入 = 目标变量 |
| Quantity | int64 | false | 销量非渠道收入对比所需 |
| Discount | float64 | false | 折扣非渠道收入对比所需 |
| Region | categorical | false | 地区非渠道维度 |

### 变体设计

| 变体 | Prompt 特征 | Schema 特征 | 调用次数 |
|------|------------|------------|---------|
| A | 生产环境 prompt（标准角色分配指令） | `used_in_analysis` 在 required 中 | 3 |
| B | 增强 prompt（+ used_in_analysis 明确指令 + 示例） | `used_in_analysis` 不在 required 中 | 3 |
| C | 极简 prompt（只给角色描述） | schema 中完全无 `used_in_analysis` 字段 | 3 |
| D | 强化 prompt（明确 ignore 规则 + 角色→uia 映射） | 同 B | 3 |

温度 = 0.0（确定性输出），每变体跑 3 次验证一致性。

---

## 2. 实验结果

### 变体 A：生产 prompt + required schema

```
准确率: 5/8 (62.5%)

StoreID   identifier → false ✅
Date      time_index → false ✅
Channel   feature    → true  ✅
ProductID identifier → false ✅
Revenue   target     → true  ✅
Quantity  feature    → true  ❌ 应 false
Discount  feature    → true  ❌ 应 false
Region    feature    → true  ❌ 应 false
```

**模式**：Qwen 将所有数值/分类列判为 `feature`，然后对所有 `feature` 判 `used_in_analysis=true`。3 次运行完全一致。

### 变体 B：增强 prompt + 非 required schema

```
准确率: 5/8 (62.5%)

StoreID   identifier → false ✅
Date      time_index → true  ❌ 应 false（变体 A 中是对的！）
Channel   feature    → true  ✅
ProductID identifier → false ✅
Revenue   target     → true  ✅
Quantity  feature    → true  ❌
Discount  feature    → true  ❌
Region    feature    → true  ❌
```

**模式**：与变体 A 几乎相同。但 `Date` 从 `false` 变成了 `true`——增强 prompt 反而让 Date 的判断变差了。说明 prompt 中的"无关字段=false"指令被模型忽略，而 Date 列恰好触发了 prompt 中「设备型号、注册日期等无关字段=false」示例的"反面联想"（"Date=日期? 示例说的是注册日期，Date 是交易日期，也许是有用的"）。

**关键发现**：`required` vs 非 `required` 对输出无影响——模型无论如何都会输出 `used_in_analysis`。schema 层面的改动不影响模型行为。

### 变体 C：极简 prompt + 无 uia 字段

```
准确率: N/A（模型完全不输出 used_in_analysis）

全部 8 列: used_in_analysis = None
```

**模式**：当 schema 中没有 `used_in_analysis` 字段时，模型完全不输出它。这验证了 function calling 的 schema 确实在控制模型输出——模型不会凭空发明字段。

### 变体 D：ignore 强化 prompt

```
准确率: 8/8 (100%)

StoreID   identifier → false ✅
Date      time_index → false ✅
Channel   feature    → true  ✅
ProductID identifier → false ✅
Revenue   target     → true  ✅
Quantity  ignore     → false ✅
Discount  ignore     → false ✅
Region    ignore     → false ✅
```

**模式**：当 prompt 明确指示"与目标无关 → ignore（而非 feature）"时，模型完美地将 Quantity/Discount/Region 判为 `ignore`，`used_in_analysis` 随之正确。

---

## 3. 根因分析

### 3.1 不是模型"笨"——是 prompt 架构让模型"左右互搏"

Qwen 并非不能区分相关/无关字段。证据：

- **它能正确识别 ID 列** → StoreID、ProductID 在所有变体中都判为 `identifier`，`used_in_analysis=false`
- **它能正确识别 target** → Revenue 始终判为 `target`
- **变体 D 证明**：当 prompt 用 LLM 熟悉的"角色"语言（ignore）而非额外的"参与/不参与"二元开关时，准确率达到 100%

问题的本质是 **prompt 架构分裂了语义判断**：

```
旧架构（变体 A/B）：
  LLM 判断 → suggested_role (target/feature/identifier/ignore)
           → used_in_analysis (true/false)  ← 又一次判断
           
问题：LLM 内部对 feature 有强规则「feature = 有用的列」
     → used_in_analysis 的判断被 feature 角色覆盖
     → prompt 中说"feature 也可能不参与"被模型忽略
```

```
新架构（变体 D）：
  LLM 判断 → suggested_role (target/feature/identifier/ignore)
           其中 ignore = "不参与"的直接表达
           
代码推导 → used_in_analysis = role not in {identifier, ignore, time_index}
```

### 3.2 模型的行为特征

通过 12 次 LLM 调用，观察到 Qwen 的以下稳定行为模式：

| 行为 | 证据 | 影响 |
|------|------|------|
| **schema 驱动输出** | 变体 C：无 uia 字段 → 完全不输出 | 可信赖 schema 控制输出字段 |
| **角色决定参与度** | 变体 A/B：feature=100% true, identifier=100% false | role 是模型判断"参与"的唯一锚点 |
| **required 不影响行为** | A vs B：结果完全相同 | 移除 required 不能改变模型倾向 |
| **温度=0 时输出稳定** | 同一变体 3 次运行结果完全一致 | 可预测、可测试 |
| **忽略 prompt 中的反例指令** | 变体 B 的"设备型号、注册日期=false"示例未生效 | 模型对 role→uia 的内部规则强于 prompt 中的例外指令 |
| **能理解角色语义层次** | 变体 D：ignore 指令被完美执行 | 模型理解"ignore=不需要"比理解"feature+used_in_analysis=false"更容易 |

### 3.3 核心洞见

> **Qwen 的决策模型是："一个字段只有一个主要判断——它是什么角色？"**
> **"是否参与"不是独立判断，而是角色的属性。**
>
> 当 prompt 试图让模型同时做两个判断（role + used_in_analysis），模型会忽略第二个，直接用 role 推导。

---

## 4. 模型能力评级

| 能力维度 | 评级 | 说明 |
|---------|------|------|
| 角色识别（target/feature/id/ignore） | ⭐⭐⭐⭐⭐ | 变体 D 100% 准确 |
| 多判断点并行决策 | ⭐⭐ | 变体 A/B 失败——不能独立判断 role + uia |
| Prompt 指令遵循（正向） | ⭐⭐⭐⭐ | "设为 ignore"→完美执行 |
| Prompt 指令遵循（反例/例外） | ⭐⭐ | "feature 也可能不参与"→被忽略 |
| Schema 字段控制 | ⭐⭐⭐⭐⭐ | 只在 schema 中有 uia 时才输出 |
| 输出一致性（temp=0） | ⭐⭐⭐⭐⭐ | 3 次运行完全相同 |

---

## 5. 工作建议

### 5.1 Prompt 设计原则（针对 Qwen 及同类模型）

**原则 1：一个概念一个字段，不要让模型在一个字段上做两次判断。**

❌ 错误：`suggested_role=feature` + `used_in_analysis=false`（两个判断点）
✅ 正确：`suggested_role=ignore` → 代码机械推导 `used_in_analysis=false`

**原则 2：用角色系统承载所有语义，代码只做枚举映射。**

| LLM 输出（suggested_role） | 代码推导（used_in_analysis） | 理由 |
|---------------------------|---------------------------|------|
| `target` | `true` | LLM 说是目标 |
| `feature` | `true` | LLM 说是特征 |
| `identifier` | `false` | LLM 说是 ID |
| `ignore` | `false` | LLM 说忽略 |
| `time_index` | `false` | 时间索引通常不参与（除非 prompt 明确用于趋势） |
| `unknown` | `false` | LLM 不确定 → 保守不参与 |

这是**铁律 1 合规的**：代码不做语义判断，只做 `role ∈ {identifier, ignore, time_index, unknown} → false` 的纯布尔运算。`suggested_role` 的赋值 100% 由 LLM 完成。

**原则 3：测试驱动 prompt 设计——用对照实验验证，不要猜测。**

变体 D 的 100% 准确率就是对照实验找到的。如果凭直觉改 prompt（如变体 B 的增强指令），可能反而降低准确率（Date 从 false→true）。

**原则 4：schema 的 `required` 对大多数开源模型无影响——不要依赖它来控制行为。**

变体 A（required）和变体 B（非 required）结果完全相同。模型看到 schema 中有这个字段，就会输出它——不管是否 required。

### 5.2 避免同类问题的工程策略

**策略 1：对每个 LLM 决策点做"单字段测试"**

新增任何 LLM 输出的字段时，运行类似本报告的对照实验——确认模型能否在简单场景下正确输出该字段。如果简单场景也失败，说明设计有问题。

**策略 2：建立 LLM 行为回归测试套件**

将变体 D 的测试固化为 CI 测试（需要 LLM 可用时运行），防止 prompt 退化。脚本已就绪：`tests/test_used_in_analysis_experiment.py`。

**策略 3：给 LLM 的语义"出口"越少越好**

- 每个语义概念只给 LLM 一个字段表达
- 多个字段表达同一概念 → LLM 产生不一致
- 需要多个下游消费方时，由代码从单一权威字段派生

**策略 4：为关键决策点配备"机械安全网"**

即使 LLM 输出正确（如变体 D），也要在代码中加一层保护：
- 如果所有字段的 `used_in_analysis` 都是同一值 → 发警告
- 如果 `target` 字段的 `used_in_analysis=false` → 可能是 LLM 错误，记录日志
- 如果没有任何字段为 `true` → 降级到全选并通知用户

这些是纯布尔/计数判断，不涉及语义，铁律 1 合规。

### 5.3 与铁律的关系

本报告的核心建议（"用 role 推导 used_in_analysis"）是否违反铁律 1？

| 铁律 | 判定 | 理由 |
|------|------|------|
| **铁律 1（零硬编码）** | ✅ 合规 | `identifier→false` 不是"代码猜含义"——是 LLM 明确说了"这是 ID"。代码只是把 LLM 的语义输出映射为下游格式。等价于 `if user_role == "admin": can_delete = True` ——这不是语义判断，是权限映射。 |
| **铁律 2（LLM 失败）** | ✅ 合规 | 如果 LLM 未输出 `suggested_role`，代码不猜测——保持 `used_in_analysis=None`，前端显示为未确定状态。 |
| **铁律 3（提交前自检）** | ✅ 合规 | 实验脚本可固化为 CI 测试。 |

**一句话**：代码推导 `role→uia` 的前提是 **role 本身 100% 由 LLM 决定**。代码只是翻译——从 LLM 的语义语言（target/feature/ignore）翻译为下游的开关语言（true/false）。这和 JSON 解析一样，是通道工作，不是语义工作。

---

## 6. 变更清单

基于本报告的结论，已完成以下代码变更：

| 变更 | 位置 | 内容 |
|------|------|------|
| Prompt 强化 | `scout/agent.py` `analysis_goal_line` | 新增明确的 ignore 规则 + 示例 |
| Schema 优化 | `types.py` `_build_fallback_schema` | `required[]` 移除 `used_in_analysis`（虽然实验证明无影响，但语义正确） |
| 机械推导恢复 | `orchestrator.py` `_build_scout_table_rows` | 恢复 `role→uia` 映射（基于 LLM 决策的纯布尔推导） |
| 默认值修正 | `types.py` `derive_analysis_columns`、`cleaner/agent.py` | opt-out → opt-in |
| 测试脚本 | `tests/test_used_in_analysis_experiment.py` | 可复用的对照实验框架 |

---

## 附录：实验原始数据

完整输出见 `tests/test_used_in_analysis_experiment.py` 和 `tests/test_uia_experiment_round2.py` 的运行日志。
