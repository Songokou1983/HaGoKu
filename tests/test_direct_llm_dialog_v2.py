"""直接对话 LLM v2：使用 OpenAI 客户端 + 完整 Scout schema"""
import json, os
from openai import OpenAI

# 清理代理
for k in ['ALL_PROXY','HTTP_PROXY','HTTPS_PROXY','all_proxy','http_proxy','https_proxy']:
    os.environ.pop(k, None)

client = OpenAI(base_url="http://localhost:8080/v1", api_key="none", timeout=180)

QUERY = "分析店铺的变动趋势"
MODEL = "Qwen3.6-35B-A3B"

COLUMNS = [
    {"name": "BU", "dtype": "object", "n_unique": 3, "sample": ["事业部A", "事业部B"]},
    {"name": "Code", "dtype": "object", "n_unique": 50, "sample": ["SH001", "SH002"]},
    {"name": "Period", "dtype": "object", "n_unique": 24, "sample": ["2024-01", "2024-02"]},
    {"name": "Inc1", "dtype": "float64", "n_unique": 200, "sample": [1500.5, 2300.0]},
    {"name": "Inc2", "dtype": "float64", "n_unique": 200, "sample": [800.0, 1200.0]},
    {"name": "Inc3", "dtype": "float64", "n_unique": 200, "sample": [300.0, 450.0]},
    {"name": "StoreID", "dtype": "int64", "n_unique": 50, "sample": [1001, 1002]},
    {"name": "Bos1", "dtype": "float64", "n_unique": 150, "sample": [200.0, 350.0]},
]

# 与 Scout 完全相同的 prompt
SYSTEM = (
    "你是专业数据分析侦察员。基于每列的数据画像，推断每个字段的语义角色。\n"
    "你必须调用 submit_field_inference 工具来提交你的分析结果。\n\n"
    f"【最高优先级 — 用户分析目标】\n"
    f"「{QUERY}」\n\n"
    f"字段角色含义：\n"
    f"  target — 核心度量指标\n"
    f"  feature — 分组维度或辅助度量\n"
    f"  identifier — 仅用于唯一标识行，无分析意义\n"
    f"  time_index — 时间戳\n"
    f"  ignore — 与本次分析无关\n"
    f"现在请调用 submit_field_inference 提交你的分析。"
)

# 完整 Scout schema
SCHEMA = {
    "type": "object", "properties": {
        "columns": {"type": "array", "items": {"type": "object", "properties": {
            "name": {"type": "string"},
            "inferred_type": {"type": "string", "enum": ["numeric","categorical","datetime","id","text","unknown"]},
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            "suggested_role": {"type": "string", "enum": ["target","feature","identifier","time_index","ignore","unknown"]},
            "display_name": {"type": "string"},
            "description": {"type": "string"},
            "needs_user_input": {"type": "boolean"},
            "used_in_analysis": {"type": "boolean"},
        }, "required": ["name","inferred_type","confidence","suggested_role","display_name","description","needs_user_input"]}},
    }
}

TOOL = {"type":"function","function":{"name":"submit_field_inference","parameters":SCHEMA}}

USER_MSG = f"请分析以下数据集的字段语义：\n```json\n{json.dumps({'columns': COLUMNS}, ensure_ascii=False, default=str)}\n```"

print("=" * 80)
print(f"  直接对话 LLM（OpenAI 客户端 + 完整 Scout schema）")
print(f"  分析目标: 「{QUERY}」")
print("=" * 80)

for run in range(3):
    resp = client.chat.completions.create(
        model=MODEL,
        messages=[{"role":"system","content":SYSTEM},{"role":"user","content":USER_MSG}],
        tools=[TOOL],
        tool_choice="auto",
        max_tokens=2048,
        temperature=0,
    )
    m = resp.choices[0].message
    if m.tool_calls:
        args = json.loads(m.tool_calls[0].function.arguments)
        cols = args.get("columns", [])
        print(f"\n┌─ Run {run+1} ───────────────────────────────────────┐")
        print(f"│ {'字段':<10} {'角色':<14} {'uia':<6} {'中文名':<10} │")
        print(f"│ {'-'*10} {'-'*14} {'-'*6} {'-'*10} │")
        for c in cols:
            n = c.get("name","?")
            rl = c.get("suggested_role","?")
            u = c.get("used_in_analysis")
            u_str = "true" if u is True else ("false" if u is False else "None")
            dn = str(c.get("display_name",""))[:8]
            flag = ""
            if n == "Period" and u is False: flag = " ⚠️ 趋势需要周期！"
            if n == "StoreID" and u is True: flag = " ⚠️ ID 不应参与"
            if n == "Code" and u is True and rl != "identifier": flag = " ⚠️ 编码不应参与"
            print(f"│ {n:<10} {rl:<14} {u_str:<6} {dn:<10} │{flag}")
        print(f"└{'─'*48}┘")
    else:
        print(f"\n  Run {run+1}: 无 tool_calls, text={m.content[:100] if m.content else '(空)'}")

print("\n" + "=" * 80)
