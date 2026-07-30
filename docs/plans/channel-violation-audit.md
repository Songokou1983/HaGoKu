# 通道违规审计 — 处置方案

> 原则：代码只做机械执行。所有判断交 LLM。不碰 prompt——提供工具而非指令。
> 状态：9/16 已完成，1 撤回，6 延后（#7-9 需更深入改造）。

## 已完成

| # | 位置 | 改动 | commit |
|---|------|------|--------|
| 1 | `profiling.py` `likely_id` | 删 | ae4c16e |
| 2 | `profiling.py` 相关性阈值 | 删阈值，全量输出 | ae4c16e |
| 3 | `agent.py` 描述判断 | 删函数 | ae4c16e |
| 4 | `agent.py` 质量警告 | 删 5%/10% 阈值 | ae4c16e |
| 5 | `agent.py` `_derive_roles` | 删函数+调用 | ae4c16e |
| 12 | `agent_tool_defs.py` 图表分配 | 删轮询分配 | 4e3b6d2 |
| 13 | `guardrails/statistical.py` | MANDATORY→WARNING | 4e3b6d2 |
| 10 | `cleaning.py` 小样本默认 | `is_mcar`=None | 55e19cb |
| 11 | `ws_handler.py` 异常广播 | `str(e)` 替代固定文案 | 55e19cb |

## 撤回

| # | 位置 | 原因 |
|---|------|------|
| 6 | `agent.py` FileNotFoundError | try/except 嵌套过深，改动性价比低 |

## 延后（需更深入改造）

| # | 位置 | 原因 |
|---|------|------|
| 7 | `profiling.py` `_infer_type` | CLI 依赖，需单独改造 |
| 8 | `profiling.py` 质量评分 | 已保留计算，判断已删 |
| 9 | `cleaning.py` `detect_missing_mechanism` | 返回值改造需同步更新调用方 |
