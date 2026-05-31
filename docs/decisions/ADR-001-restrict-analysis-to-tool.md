# ADR-001：律 4 引入 `restrict_analysis_to` 工具

- **日期**：2026-05-26
- **状态**：✅ 已落地
- **相关律 / 铁律**：律 4（工具 schema 覆盖完备律）、律 9（重推断触发律）、铁律 1（零硬编码）

## 背景

test0526 现行犯：用户对 Scout 字段评审说「**只有店铺编号、时间周期、店铺收入需要参与分析**」（典型「包含集」语义），结果系统未理解、字段全军覆没。

根因诊断（详见 `docs/cases/2026-05-26-restrict-analysis-to-failure.md`）：

1. Scout 阶段的字段更新工具 `update_field_understanding` / `update_field_role` 只支持「逐字段排除」（`ignored=true` 列表）
2. 用户表达「**只保留** X、Y、Z」是包含集语义，工具 schema 中**没有这个表达落点**
3. LLM 听懂了，但**无路可写** → 律 4「工具 schema 覆盖完备律」违反 → 用户原话即使到了 LLM 也产生不了任何工具调用 → 触发律 7 但用户还是感觉「我说了没反应」

## 决策

新增 `restrict_analysis_to(included_fields: list[str])` 工具，专门表达「只保留 X、Y、Z 参与分析」的包含集语义。

- LLM 传业务名（"店铺收入"）或列名（"Inc1"）均可，由 `_resolve_to_column_names` 做映射
- 代码做**机械补集运算**：`complement = columns - included_fields`，补集 `used_in_analysis=False`
- 触发 `_pending_reinference=True`（律 9：结构性变更后由 Manager 跑重推断）

## 替代方案

| 方案 | 否决理由 |
|------|---------|
| **扩展 `update_field_role` 加 `keep_only` 参数** | 语义模糊、与 `ignored` 同义共存，违反单一权威 |
| **代码识别「只」「只有」「仅」关键词后转换** | 违反铁律 1（中文语义正则 / 关键词列表硬编码） |
| **让用户被迫输入「除 X、Y、Z 外都不参与」逐字段排除** | 违反律 6（信息抵达正向断言）+ 用户体验灾难 |

## 后果

**正面**：

- 律 4 包含集表达通路打通；test0526 现行犯被 e2e 测试守护
- LLM 主导补集运算从此由代码执行（机械、可测试），LLM 不必算补集
- 律 9 重推断信号 `_pending_reinference` 同步落地，结构性变更后自动重跑

**负面 / 待办**：

- `_resolve_to_column_names` 当前仅支持精确匹配（列名 / display_name）；前缀 / description 子串匹配已删除（太宽，会把"店铺"命中所有含"店铺"描述的行）
- LLM 用 description 调工具时若未命中精确名 → `_resolve_to_column_names` 返回空 → 触发律 7 未理解信号（合规但用户感知是"系统没听懂"）
- 真实 LLM 端到端验证未做（mock 测试已守护，但 LLM 是否会主动调此工具未在真实环境验证）

**影响范围**：

- `hagoku/manager/orchestrator.py:568, 723-776`（工具定义 + handler）
- `hagoku/manager/orchestrator.py:943-947`（system prompt 教学段）
- `hagoku/manager/orchestrator.py:1017-1019`（dispatch 分支）
- `hagoku/manager/orchestrator.py:2135`（Manager 主循环响应 `_pending_reinference`）
- `tests/test_product/test_information_arrival.py`（多用例守护）

## 引用

- Commit hash：律 4-7 修复系列（2026-05-26 ~ 27）
- 相关测试：
  - `tests/test_product/test_information_arrival.py::test_真实场景_restrict_analysis_to_e2e`
  - `tests/test_product/test_information_arrival.py::test_真实场景_restrict_analysis_to_业务名解析`
- 相关 plan：
  - `docs/plans/fix-律4-律7-test0526.md`
  - `docs/plans/review-律4-律7-test0526-followups.md`
- 相关案例：
  - `docs/cases/2026-05-26-restrict-analysis-to-failure.md`
