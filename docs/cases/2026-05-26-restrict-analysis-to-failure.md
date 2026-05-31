# 案例：包含集语义无落地通路 → 用户原话送达 LLM 但无法表达

- **日期**：2026-05-26
- **状态**：✅ 已根治
- **报告人**：项目所有者真实使用反馈
- **相关律**：律 4（工具 schema 覆盖完备律）、律 7（语义不确定可见化律）、律 9（重推断触发律）

## 用户原话

> "字段理解，在分析目标时已录入分析每个店铺的收入增长趋势，结果字段理解出来的结果，参与分析的字段都是错的。而且错的离谱，我告诉他应该是哪个也毫无反应。我可以猜出 LLM 根本没有收到有效信息"

后续在 Scout 字段评审阶段用户回复：

> "只有店铺编号、时间周期、店铺收入需要参与分析"

## 现象

- 用户在 Scout 字段评审阶段说「只有店铺编号、时间周期、店铺收入需要参与分析」（典型「包含集」语义）
- 系统 UI 上没有任何明显反馈——既没有「未理解」提示，也没有字段更新
- 用户感受：「我说了好几遍系统都没反应」

## 复现步骤

数据集：含 `Code / Period / Inc1 / Inc2 / Inc3 / BU / StoreID / Bos1` 等列。

1. 用户提交 query：「分析每个店铺的收入增长趋势」
2. Scout 推断字段角色（错位）
3. 用户回复：「只有店铺编号、时间周期、店铺收入需要参与分析」
4. **预期**：Inc1（店铺收入）保留参与分析，其它（Inc2/Inc3/BU/StoreID/Bos1）`used_in_analysis=False`
5. **实际**：所有字段保持原状，UI 无反馈

## 根因诊断

通过补正向断言测试（`tests/test_product/test_information_arrival.py`）逐律核查，发现两条通道残缺：

### 残缺 1（律 4）：工具 schema 缺包含集表达通路

Scout 阶段的字段更新工具 `update_field_understanding` / `update_field_role` 只支持「**逐字段排除**」（`ignored=true` 列表）。用户表达「**只保留** X、Y、Z」是包含集语义，工具 schema 中**没有这个表达落点**。

**结果**：LLM 听懂了，但无路可写工具调用。

### 残缺 2（律 7）：LLM 未理解信号不送达 UI

`_apply_scout_reply_with_llm` 在 LLM 没产生工具调用时，仅 `logging.warning(...)` 然后默默推进。`logging.warning` 只对开发者可见，用户感知不到——违反律 7。

**结果**：用户感觉「系统没反应」。

### 残缺 3（律 2）：用户原话只在局部变量

`raw` 字符串作为函数参数传入，函数返回后即丢失，没有结构化保留——违反律 2。

## 修复

通过 `docs/plans/fix-律4-律7-test0526.md` 8 步落地：

| 修复 | 位置 |
|------|------|
| 引入 `restrict_analysis_to(included_fields)` 工具 | `hagoku/manager/orchestrator.py:568` |
| 引入 `_resolve_to_column_names` 业务名 → 列名映射 | `hagoku/manager/orchestrator.py:~690-720` |
| 引入 `_last_understanding_failure` 信号 + UI 渲染 | `orchestrator.py:1119-1126` + `AnalyzePanel.tsx:510-515` |
| 引入 `utterances` 结构化原话保留 | `orchestrator.py:805-810` |
| 引入 `_pending_reinference` 信号触发律 9 重推断 | `orchestrator.py:775, 2135` |
| 引入 `_conversation_history` 多轮对话累积（律 3 落地） | `orchestrator.py:958-995` |

详见：

- ADR-001（restrict_analysis_to 工具）
- ADR-002（_last_understanding_failure 信号）

## 守护测试

`tests/test_product/test_information_arrival.py` 中 12 条用例守护此案例不再发生：

- `test_律1_意图穿透_query抵达LLM`
- `test_律2_scout字段纠错_用户原话抵达LLM`
- `test_律3_scout多轮纠错_前一轮LLM输出抵达本轮`
- `test_律4_包含集表达通路_restrict_analysis_to工具存在`
- `test_律7_LLM未产生工具调用_写入未理解信号`
- `test_真实场景_律2_用户原话保存到context`
- `test_真实场景_律7_未理解信号_写入_context`
- `test_真实场景_restrict_analysis_to_e2e`
- `test_真实场景_restrict_analysis_to_业务名解析`

新增的回归契约 mock LLM 抛出与 test0526 同构的工具调用，断言：

1. `column_semantics` 中 keep set `used_in_analysis=True`
2. 补集 `used_in_analysis=False`
3. `_pending_reinference=True`
4. 无 `_last_understanding_failure`
5. `utterances[-1].consumed=True`

## 影响范围

- 已修：Scout 字段评审阶段（包含集语义已通）
- 仍可能漏水：Cleaner / Analyst 反馈阶段同类问题（其它 Agent 的工具 schema 也未必覆盖完备——参考 ADR-005 ProjectContext 推进时一并审视）

## 教训

设计 LLM 工具时**必须列出该阶段用户可能说的 10 种纠正措辞**，每一种都能在工具参数中找到落点。否则工具 schema 残缺，LLM 听懂了也无路可写。

具体方法（来自 PROJECT.md §「律 4」）：

> 列出该阶段用户可能说的 10 种纠正措辞，每一种都能在工具参数中找到落点。否则工具 schema 残缺，LLM 听懂了也无路可写。

例如 Scout 字段评审阶段，用户的纠正措辞包括：

| 措辞 | 工具 |
|------|------|
| 「Inc1 是收入」 | `update_field_understanding` |
| 「Inc1 应该是 target」 | `update_field_role` |
| 「Inc1 不参与分析」 | `update_field_role(ignored=true)` |
| **「只有 X、Y、Z 参与分析」** | **`restrict_analysis_to(included_fields=[...])`** ← 之前缺 |
| 「目标变量改为 Y」 | `update_field_role` |

新增 LLM 工具前，至少做这种 10 种措辞 → 工具落点对照表。覆盖不全则不上线。

## 待真实 LLM 验证

mock 测试只验证「**如果** LLM 调用了 `restrict_analysis_to`，代码正确处理」。
真实 LLM 验证要回答「**LLM 是否真的会调用** `restrict_analysis_to`」。

详见 `docs/plans/review-律4-律7-test0526-followups.md` §「真实 LLM 验证」。
