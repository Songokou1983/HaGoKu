# ADR-002：律 7 引入 `_last_understanding_failure` 信号

- **日期**：2026-05-26
- **状态**：✅ 已落地
- **相关律 / 铁律**：律 2（原话不可销毁律）、律 7（语义不确定可见化律）、铁律 2（LLM 失败的唯一合法路径）

## 背景

test0526 现行犯（详见 ADR-001）的**第二症状**：当 LLM 收到用户原话但**未产生任何工具调用**时（包含集语义无落地通路），代码静默推进，用户感觉「我说了好几遍系统都没反应」。

律 7「语义不确定可见化律」要求：LLM 对用户输入未产生任何工具调用、或产出参数为空时，**必须**在 UI 层显式告知用户"系统未理解你的输入，请换一种说法"，不得静默继续。

但代码层缺一个**承载信号的容器**——LLM 失败时实现者要么 `logging.warning(...)` 静默推进（违反律 7），要么写规则兜底（违反铁律 1 / 铁律 2）。没有第三条路。

## 决策

引入 `context["_last_understanding_failure"]` 作为**结构化失败容器**：

```python
{
    "raw_text": str,            # 律 2：用户原话保留
    "model_reply_text": str,    # 模型实际回复内容（即使没调工具）
    "had_tool_calls": bool,     # 模型是否调了工具（参数空 / 参数无关）
    "stage": "scout_field_review",
}
```

写入时机（三处）：

1. **主路径**：LLM 调用成功但 `applied=[]` → 写信号 + `return []`
2. **异常路径**：LLM 调用抛异常但有 raw 用户原话 → 写信号 + `return []`（同时 raise 给上游处理）
3. **失败路径**：解析失败但保留 raw → 写信号

清除时机（三处）：

1. 成功落地任一 tool_call → `context.pop("_last_understanding_failure", None)`
2. 同时 `utterances[-1]["consumed"] = True`
3. 用户后续重发并被理解 → 同上

UI 层：`AnalyzePanel.tsx:510-515` 读取此字段，向用户显示「系统未理解你的输入「{snippet}」，请尝试换一种说法」。

## 替代方案

| 方案 | 否决理由 |
|------|---------|
| `logging.warning(...)` 后静默继续 | 违反律 7；开发者可见 ≠ 用户可见 |
| `raise ValueError("LLM 未理解")` | LLM 未理解不是异常，是常态；raise 会终止 pipeline |
| 直接清空 `column_semantics` 让用户重做 | 暴力；违反律 2 历史不可销毁；用户已说的话也丢失 |
| 加规则识别用户意图后兜底 | 违反铁律 1 + 铁律 2 |

## 后果

**正面**：

- 律 7 用户感知通路打通：LLM 真不懂时用户看得到
- 铁律 2「LLM 失败的唯一合法路径」第三种合法动作落地（B：写未理解信号 + return []）
- 实现者面对「LLM 没调工具」有明确的合法出路，不再被迫偷偷加兜底
- `consumed` 标记给 utterances 提供「是否被理解」的审计

**负面 / 待办**：

- 当前信号是**单值字段**（最多保留最近一次）；多次未理解会被覆盖。如需累积可改为 list，但目前未发现需求
- UI 仅在 Scout 字段评审阶段读取该信号，其他阶段（Cleaner / Analyst 反馈）暂未接入

**影响范围**：

- `hagoku/manager/orchestrator.py:1119-1126, 1138-1144`（写入位）
- `hagoku/manager/orchestrator.py:1079, 1129`（清除位）
- `hagoku/manager/orchestrator.py:1184-1188`（payload 透传）
- `hagoku_web/src/panels/AnalyzePanel.tsx:510-515`（UI 渲染）
- `PROJECT.md §「失败处理」§「代码层合法动作清单」`（铁律 2 写入约定）

## 引用

- 相关测试：
  - `tests/test_product/test_information_arrival.py::test_真实场景_律7_未理解信号_写入_context`
  - `tests/test_product/test_information_arrival.py::test_真实场景_律2_用户原话保存到context`
- 相关 ADR：[ADR-001](ADR-001-restrict-analysis-to-tool.md)（同期落地）
- 相关 plan：`docs/plans/fix-律4-律7-test0526.md`
