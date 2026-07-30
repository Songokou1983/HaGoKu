# 通道违规审计 — 处置方案

> 原则：代码只做机械执行。所有判断交 LLM。不碰 prompt——提供工具而非指令。

## 可直接删除（死代码/死数据）

| # | 位置 | 为什么可删 | 风险 |
|---|------|-----------|------|
| 1 | `profiling.py:156-157` `likely_id` | 全仓库零消费者 | 无 |
| 2 | `profiling.py:243` 相关性阈值 0.7 | `high_correlations` 无人读取 | 无 |
| 3 | `agent.py:30-40` `_description_is_user_facing_meaningful` | 调用函数已删除 | 无 |
| 4 | `agent.py:205-208` 质量警告阈值 | `context["warnings"]` 无人读取 | 无 |
| 5 | `agent.py:371-384` `_derive_roles` | `context["target"]`/`features` 无人读取 | 无 |
| 6 | `agent.py:216-218` FileNotFoundError 短路 | 异常仍被外层捕获 | 无 |

## 需改造（保留工具、删判断）

| # | 位置 | 问题 | 改造 |
|---|------|------|------|
| 7 | `profiling.py:175-209` `_infer_type` | 硬编码类型推断。CLI 读它做图标展示 | 删判断分支。CLI 改显示原始 dtype/n_unique |
| 8 | `profiling.py:256-275` 质量评分 | agent.py emit 读 `quality_score`，删了崩 | 保留基础计算，`quality_score` 作为数据传给 LLM，不做"优/劣"判断 |
| 9 | `cleaning.py:243-299` `detect_missing_mechanism` | LLM 工具依赖，但返回结论标签而非原始数据 | 返回值从 "mcar"/"mar"/"mnar" 改为原始检验数据（显著列、p 值分布） |
| 10 | `cleaning.py:170-174` 小样本默认 MCAR | `littles_mcar_test` 假设 MCAR | `is_mcar` 返回 None，`conclusion` 改为"无法判断" |
| 11 | `ws_handler.py:114-130` 分析异常 | 真实错误被替换为通用"刷新重试" | 保留广播机制，`message` 改传 `str(e)` |
| 12 | `agent_tool_defs.py:416-431` 图表自动分配 | 代码替 LLM 决定图表放哪 | 删自动分配逻辑。LLM 用 `generate_report` 的 `charts` 参数显式绑定 |
| 13 | `guardrails/statistical.py` | 硬编码阈值判断（VIF>10、样本<30 等） | 保留计算函数作工具，删 `MANDATORY_BLOCK` 等判断分支 |

## 保留（工具或基础设施）

| # | 位置 | 保留原因 |
|---|------|---------|
| 14 | `agent_tool_defs.py:388-394` markdown→HTML | 纯机械转换，工具能力，不做判断 |
| 15 | `reply_handlers.py:97-101` 死循环检测 | 工程防护，不涉及语义 |
| 16 | `data_io.py:55-63` 扩展名猜测 | 基础设施容错，不改 |

## 不动 prompt

零 prompt 改动。所有改造通过删代码判断分支、保留工具计算完成。
