# 模型可移植性分析：used_in_analysis 在不同模型下的行为

> 基于 Qwen 对照实验的结论，推演换模型后的风险矩阵

---

## 1. 当前状态

经过本轮修复，`used_in_analysis` 的判断链路：

```
Scout LLM → suggested_role (target/feature/identifier/ignore/time_index)
          → used_in_analysis (LLM 也可直接输出，优先于机械推导)

代码层   → 机械映射: {identifier, ignore, time_index, unknown} → false
                      {target, feature} → true
                      (LLM 输出优先，仅当 LLM 未设置时生效)
```

## 2. 模型行为推演矩阵

基于已知的模型行为特征（公开 benchmarks + 社区经验）：

| 模型 | 角色识别 | 多字段独立判断 | feature→ignore 区分 | 风险 |
|------|---------|--------------|-------------------|------|
| **Qwen3.6-35B**（当前） | ⭐⭐⭐⭐⭐ | ⭐⭐ | 需 prompt 引导 | ✅ 已修复 |
| **GPT-4o / Claude 4** | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | 自然区分 | 🟢 低 |
| **DeepSeek-V3** | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | 自然区分 | 🟢 低 |
| **Llama 3.1-70B** | ⭐⭐⭐⭐ | ⭐⭐ | 需 prompt 引导 | 🟡 中 |
| **Llama 3.1-8B** | ⭐⭐⭐ | ⭐ | 困难 | 🔴 高 |
| **Qwen2.5-7B** | ⭐⭐⭐ | ⭐ | 困难 | 🔴 高 |
| **Mistral/Mixtral** | ⭐⭐⭐⭐ | ⭐⭐ | 需 prompt 引导 | 🟡 中 |

### 风险分级

**🟢 低风险（GPT-4o, Claude, DeepSeek-V3）**：
这些模型能独立处理 role + uia 两个判断点。即使不做机械推导，也能正确输出 `used_in_analysis=false` 给无关字段。当前架构对它们完全没问题。

**🟡 中风险（Llama-70B, Mixtral）**：
与 Qwen 类似——role 识别好，但多字段独立判断弱。如果 prompt 不显式引导它们用 `ignore`，会掉进 `feature→true` 陷阱。当前架构（机械推导 + prompt 引导）应该能覆盖，但需验证。

**🔴 高风险（7B-8B 小模型）**：
这些小模型连角色识别本身就不稳定。`suggested_role` 可能混入错误值，`used_in_analysis` 更不可靠。当前架构只能部分保护——如果 LLM 把无关字段错判为 `feature`，机械推导会将其标记为 `true`（参与）。

---

## 3. 换模型会出错的场景

### 场景 1：小模型角色识别错误

```
LLM 输出:  Quantity → suggested_role=feature  (错，应该=ignore)
代码推导:  feature → used_in_analysis=true     (连锁错)
结果:      无关字段参与分析
```

**根因**：机械推导是"信任 LLM 的角色判断"的。如果角色错了，一切皆错。

### 场景 2：模型不输出某些字段

```
LLM 输出:  Quantity → suggested_role=feature
           (没输出 used_in_analysis)
代码推导:  feature → true
结果:      看似正确，但如果模型也不输出 suggested_role...
           → 代码的 fallback 是 "unknown" → used_in_analysis=false
           → 字段被排除（保守策略，安全）
```

当前代码对这种情况有保护——`unknown` 角色映射到 `false`（保守）。

### 场景 3：不同模型对"ignore"的理解不同

```
GPT-4o:    ignore = 完全不参与，不展示给用户
Qwen:      ignore = 不参与分析
Llama-8B:  ignore = 不识别（可能当成 "i don't know"）
```

如果模型把"ignore"理解为"不知道"而非"排除"，它会避免使用这个角色，导致本应排除的字段变为 `feature`。

---

## 4. 模型无关的安全网设计

要让项目在换模型时不出错，需要**多层防护**，每一层都模型无关：

### 第 0 层：架构决策（已完成）

```
✅ 一个概念一个字段：suggested_role 是唯一的语义出口
✅ 代码只做枚举映射，不做语义推理
✅ 保守默认：unknown → false（而非 true）
```

### 第 1 层：异常检测（建议新增）

在 Scout 产出后、展示给用户前，做纯计数检查：

```python
def _validate_field_participation(column_semantics: list[dict]) -> list[str]:
    """纯计数检查，不涉及语义判断。"""
    warnings = []
    total = len(column_semantics)
    participating = sum(1 for s in column_semantics if s.get("used_in_analysis"))
    
    # 全选警告：>80% 字段参与 + 字段数 > 5 → 可能有问题
    if participating / max(total, 1) > 0.8 and total > 5:
        warnings.append(
            f"⚠️ {participating}/{total} 字段标记为参与分析，比例偏高。"
            f"如果分析目标明确，建议检查是否有无关字段被误标。"
        )
    
    # 全不选警告：无字段参与 → 肯定有问题
    if participating == 0:
        warnings.append("❌ 无字段参与分析，请检查分析目标是否正确。")
    
    return warnings
```

这是纯数学运算，铁律 1 合规。换任何模型都适用。

### 第 2 层：用户可纠正（已有）

`restrict_analysis_to` 工具 + 用户自然语言纠正通道——即使 Scout 判错了，用户可以一句话修正。这是最终安全网，模型无关。

### 第 3 层：回归测试（建议新增）

将对照实验固化为 CI 测试：

```python
# 每个模型接入时跑一次
def test_model_can_assign_ignore_to_irrelevant_fields():
    """模型无关的准入测试：给定明确的分析目标，
    模型必须将无关字段判为 ignore（而非 feature）。"""
    ...
```

新模型接入 → 跑这个测试 → 通过才允许上线。

---

## 5. 结论

| 问题 | 答案 |
|------|------|
| 换 GPT-4/Claude 会出错吗？ | **大概率不会**。它们能独立处理多字段判断。 |
| 换 Llama-70B 会出错吗？ | **可能不会**。当前架构的机械推导 + prompt 引导应该覆盖。但建议验证。 |
| 换 7B 小模型会出错吗？ | **很可能会**。角色识别本身就不稳定，机械推导会放大错误。 |
| 最安全的做法？ | **让 `used_in_analysis` 完全机械化** —— 删除 LLM 直接输出路径，只从 `suggested_role` 推导。然后所有精力放在让 role 准确上（一个判断点比两个容易）。 |

### 建议的终极方案

```
Scout LLM  → 只输出 suggested_role (target/feature/identifier/ignore/time_index)
代码层     → 纯机械映射:
              target, feature → used_in_analysis = true
              其他            → used_in_analysis = false
用户纠正   → restrict_analysis_to 工具覆盖（已有）

优势: 模型只需要做好一件事（角色判断），代码做确定性映射。
      换任何模型，只要它能区分 target/feature/identifier/ignore → 就不会出错。
```

当前代码已经接近这个方案——LLM 的 `used_in_analysis` 输出被保留但优先级低于机械推导。如果要彻底模型无关，可以考虑完全移除 LLM 的 `used_in_analysis` 输出路径，改为纯机械推导。
