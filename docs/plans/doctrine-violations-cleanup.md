# Doctrine 违规清理 — 历史债务

**触发**：`tests/test_doctrine_compliance.py` 上线时扫出 5 处「LLM 调用 except 块静默吞失败」
**状态**：5 处违规已加入 `_KNOWN_LLM_EXCEPT_VIOLATIONS` 白名单豁免，CI 不阻塞。
**目标**：按本文件逐一修复，每修一处从白名单移除。修完后白名单为空集，整套 doctrine 测试无豁免。

---

## 为何这 5 处是违规

`PROJECT.md §「代码层合法动作清单」` 规定：LLM 调用失败时**唯一合法动作**是：

- A. `raise RuntimeError(...)`（路径 1）
- B. 写 `_last_understanding_failure` + `return []`（路径 3）

但这 5 处都是：

```python
except Exception as e:
    self._emit(THINKING, {"thought": f"LLM 失败：{e}"})  # 仅日志
    return []  # 或 return None
```

后果：用户看不到失败、Pipeline 默默走"机械序列"或跳过——这正是用户报告的
「我说了系统没反应」B 类语义漏水的同源症状。

---

## 5 处违规清单

### 违规 1：`hagoku/agents/analyst/agent.py:886`

**函数**：`_plan_analysis_via_llm`
**当前代码**：

```python
except Exception as e:
    self._emit(EventType.AGENT_THINKING, {"thought": f"LLM 分析规划失败，回退到机械序列：{e}"})
    return []
```

**问题**：LLM 不可达直接吞掉，回退到"机械序列"——典型隐性降级。

**修复**：

```python
except Exception as e:
    raise RuntimeError(
        f"Analyst LLM 分析规划失败：LLM 不可达，请检查 API 配置。原始错误: {e}"
    ) from e
```

调用方需配套处理 RuntimeError（若已有"机械序列"作为业务降级，需重新审视它的合法性——
机械序列若是真正"无 LLM 也能跑的纯统计 baseline"则属合法工具，但那应该由 Manager 显式选择，
不应作为 LLM 失败的兜底）。

### 违规 2：`hagoku/agents/analyst/agent.py:911`

**函数**：`_plan_analysis_via_llm`（同一函数的 JSON 解析失败分支）
**当前代码**：

```python
except Exception:
    self._emit(EventType.AGENT_THINKING, {"thought": "LLM 分析计划 JSON 解析失败，回退到机械序列"})
    return []
```

**问题**：同上，且更隐蔽——JSON 解析失败属"通道失败"，按 PROJECT.md §「路径 2 通道失败 = 项目失败」应当**项目失败必须修复通道**，绝不允许降级。

**修复**：

```python
except Exception as e:
    raise RuntimeError(
        f"Analyst LLM 输出解析失败：通道异常，必须修复后重跑。原始 raw 输出已记入日志。\n"
        f"raw_text={raw[:500]!r}\n原始错误: {e}"
    ) from e
```

### 违规 3：`hagoku/manager/orchestrator.py:2889`

**函数**：`_call_llm_for_plan`
**当前代码**：

```python
except Exception as e:
    self.event_bus.emit(EventType.AGENT_THINKING, "manager", {
        "thought": f"LLM 计划生成失败: {e}",
    })
    return None
```

**问题**：返回 None 让上游走"无 LLM 计划"路径。

**修复**：

```python
except Exception as e:
    raise RuntimeError(
        f"Manager LLM 计划生成失败：LLM 不可达，请检查配置。原始错误: {e}"
    ) from e
```

调用方应捕获 RuntimeError 并通过 EventBus 通知用户"LLM 配置问题，请修复后重试"，不再静默继续。

### 违规 4：`hagoku/manager/orchestrator.py:3074`

**函数**：`_try_generate_phase_llm`
**待办**：阅读上下文，按相同思路修复（路径 1 抛异常 / 路径 3 写未理解信号）。

### 违规 5：`hagoku/manager/orchestrator.py:3382`

**函数**：`_llm_understand_field_update`
**待办**：阅读上下文，按相同思路修复。
**注意**：此函数命名含 `_llm_understand_` 前缀但当前未通过守门 4 检测——意味着函数体内**确实**有 LLM 调用标记，是合规的。问题只在 except 处理。

---

## 推进顺序

按影响面排序（修一处验证一处）：

1. **违规 3**（`_call_llm_for_plan`）— Manager 层，影响最大
2. **违规 1 + 2**（`_plan_analysis_via_llm`）— Analyst 双分支一并修
3. **违规 4 + 5**（`orchestrator.py` 其余两处）— 同文件可一并修

每修一处的检查清单：

- [ ] 改 `except` 块为 `raise RuntimeError(...)` 或写 `_last_understanding_failure`
- [ ] 调用方相应处理（不再依赖 `None`/`[]` 返回）
- [ ] 跑 `pytest tests/` 确认无回归
- [ ] 从 `_KNOWN_LLM_EXCEPT_VIOLATIONS` 移除该条
- [ ] 跑 `pytest tests/test_doctrine_compliance.py` 确认守门 5 仍绿

---

## 修复时的注意事项

1. **"机械序列" / "默认计划" 是否合法**？
   它们若作为 LLM 失败的**兜底**，违规；若作为 LLM **主动选择的工具**（LLM 看完上下文后调用 `use_baseline_pipeline()` 工具），合规。
   修复时需把"机械序列"从代码兜底路径移到 LLM 工具菜单中。

2. **用户感知**：
   修完后，用户若遇到 LLM 配置问题，会看到明确的 RuntimeError 提示而非"系统看起来在跑实际没结果"。
   这是 PROJECT.md §「失败处理」§「设计原则」要求的——**"不做降级，只做三种响应"**。

3. **测试**：
   每处违规修复必须配一条单元测试 mock LLM 抛异常，断言：
   - 修复 1/3/4：`pytest.raises(RuntimeError)`
   - 修复 5（若属语义未理解）：`assert ctx["_last_understanding_failure"] is not None`

---

## 给实施者的一句话

> 这 5 处不是 bug——它们是 5 个 AI 实现者在你之前留下的"防御性兜底"。
> 你的职责是**把它们变成显式失败**，让用户看到，让代码不再装作能跑。
> 修完后，把白名单清空——这是项目「LLM 主导」哲学的真正落地。
