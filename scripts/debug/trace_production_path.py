"""追踪生产路径：用真实数据和 query 调用 Scout._infer_all_semantics

这是**调试取证探针**，不是 pytest 测试：
- 无断言、纯 print，输出供人工检查
- 直连真实 LLM（无 mock），需要 ~/.hagoku/.env 配置
- 用法：`python scripts/debug/trace_production_path.py`

适用场景：「LLM 拿到真实数据 + 真实 query 后，字段分类异常 / used_in_analysis 错位」
类问题的取证。改 QUERY 与 df 即可复用于其它案例。

历史背景：本脚本最初为追踪 test0526 现行犯（详见
docs/cases/2026-05-26-restrict-analysis-to-failure.md）而写。
"""
import json, os, sys
sys.path.insert(0, ".")
from unittest.mock import MagicMock
import pandas as pd
from hagoku.config import HaGoKuConfig
from hagoku.agents.scout.agent import ScoutAgent

# 清理代理
for k in ['ALL_PROXY','HTTP_PROXY','HTTPS_PROXY','all_proxy','http_proxy','https_proxy']:
    os.environ.pop(k, None)

cfg = HaGoKuConfig()
agent = ScoutAgent(cfg.llm, event_bus=MagicMock())

# 用户的实际分析目标
QUERY = "分析店铺的变动趋势"

# 模拟实际数据
df = pd.DataFrame({
    "BU": ["事业部A", "事业部B"],
    "Code": ["SH001", "SH002"],
    "Period": ["2024-01", "2024-02"],
    "Inc1": [1500.5, 2300.0],
    "Inc2": [800.0, 1200.0],
    "Inc3": [300.0, 450.0],
    "StoreID": [1001, 1002],
    "Bos1": [200.0, 350.0],
})

print(f"分析目标: 「{QUERY}」")
print(f"字段数: {len(df.columns)}")
print()

semantics = agent._infer_all_semantics(df, query=QUERY)

print(f"{'字段':<10} {'角色':<14} {'uia':<6} {'中文名':<10}")
print(f"{'-'*10} {'-'*14} {'-'*6} {'-'*10}")
for s in semantics:
    n = s["column_name"]
    r = s.get("suggested_role", "?")
    u = s.get("used_in_analysis")
    u_str = "true" if u is True else ("false" if u is False else "None")
    d = str(s.get("display_name", ""))[:10]
    print(f"{n:<10} {r:<14} {u_str:<6} {d:<10}")
