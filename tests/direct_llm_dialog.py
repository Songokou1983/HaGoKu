"""直接对话 LLM：用 Scout 完全相同的 prompt + 用户分析目标，看 used_in_analysis 输出"""
import json, urllib.request

LLM_URL = "http://localhost:8080/v1/chat/completions"
MODEL = "Huihui-Qwen3.6-35B-A3B-Claude-4.7-Opus-abliterated-ggml-model-Q5_K.gguf"

# 用户的实际分析目标
QUERY = "分析店铺的变动趋势"

# 模拟 8 列零售数据（与用户实际数据一致）
COLUMNS = [
    {"name": "BU", "dtype": "object", "n_unique": 3, "sample": ["事业部A", "事业部B", "事业部C"]},
    {"name": "Code", "dtype": "object", "n_unique": 50, "sample": ["SH001", "SH002", "BJ001"]},
    {"name": "Period", "dtype": "object", "n_unique": 24, "sample": ["2024-01", "2024-02", "2024-03"]},
    {"name": "Inc1", "dtype": "float64", "n_unique": 200, "sample": [1500.5, 2300.0, 1800.0]},
    {"name": "Inc2", "dtype": "float64", "n_unique": 200, "sample": [800.0, 1200.0, 950.0]},
    {"name": "Inc3", "dtype": "float64", "n_unique": 200, "sample": [300.0, 450.0, 380.0]},
    {"name": "StoreID", "dtype": "int64", "n_unique": 50, "sample": [1001, 1002, 1003]},
    {"name": "Bos1", "dtype": "float64", "n_unique": 150, "sample": [200.0, 350.0, 280.0]},
]

FIELDS_DESC = "\n".join(
    f"  {c['name']}: dtype={c['dtype']}, unique={c['n_unique']}, sample={c['sample'][:3]}"
    for c in COLUMNS
)

# ── 与 Scout 完全相同的 system prompt ──
SYSTEM_PROMPT = (
    "你是专业数据分析侦察员。基于每列的数据画像，推断每个字段的语义角色。\n"
    "你必须调用 submit_field_inference 工具来提交你的分析结果。\n"
    "同名 display_name 可以相同但不要编号——让后续流程处理重复。\n\n"
    f"【最高优先级 — 用户分析目标】\n"
    f"「{QUERY}」\n"
    f"你必须逐一检查每个字段是否能服务于上述分析目标。\n"
    f"将最相关的字段设为 target（目标变量），辅助字段设为 feature（特征变量），\n"
    f"无关字段设为 ignore 或 identifier。\n"
    f"不要仅根据数据类型（数值/文本/日期）推断角色——必须结合分析目标做语义判断。\n"
    f"\n"
    f"⚡ 关键：对于与本次分析目标「{QUERY}」无关的字段，\n"
    f"必须将 used_in_analysis 设为 false。\n"
    f"只有确实能服务于用户分析目标的字段才设为 true。\n"
    f"举例：用户问「各渠道收入对比」——渠道字段、收入字段 = true；\n"
    f"设备型号、注册日期等无关字段 = false。"
)

# ── Schema（当前生产版本，无 used_in_analysis 在 required 中）─
SCHEMA = {
    "type": "object", "properties": {
        "columns": {"type": "array", "items": {"type": "object", "properties": {
            "name": {"type": "string"},
            "inferred_type": {"type": "string", "enum": ["numeric","categorical","datetime","id","text","unknown"]},
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            "suggested_role": {"type": "string", "enum": ["target","feature","identifier","time_index","ignore","unknown"]},
            "display_name": {"type": "string", "description": "简短中文业务名称（≤6字）"},
            "description": {"type": "string", "description": "业务含义理解"},
            "needs_user_input": {"type": "boolean"},
            "used_in_analysis": {"type": "boolean", "description": "该字段是否参与本次分析。严格根据分析目标判断：能服务于用户问题的字段=true，无关字段=false。标识符、ID、与问题无关的文本列通常=false。"},
        }, "required": ["name","inferred_type","confidence","suggested_role","display_name","description","needs_user_input"]}},
    }, "required": ["columns"]
}

TOOL = {"type":"function","function":{"name":"submit_field_inference","description":"提交字段语义推断结果","parameters":SCHEMA}}

print("=" * 80)
print(f"  直接对话 LLM")
print(f"  分析目标: 「{QUERY}」")
print(f"  字段数: {len(COLUMNS)}")
print("=" * 80)

for run in range(3):
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"请分析以下数据集的字段语义：\n```json\n{json.dumps({'columns': COLUMNS}, ensure_ascii=False, default=str)}\n```"},
        ],
        "temperature": 0.0,
        "max_tokens": 2048,
        "tools": [TOOL],
        "tool_choice": "auto",
    }

    try:
        req = urllib.request.Request(LLM_URL, data=json.dumps(payload).encode(),
              headers={"Content-Type": "application/json"})
        r = json.loads(urllib.request.urlopen(req, timeout=180).read().decode())
        tc = r["choices"][0]["message"].get("tool_calls", [])
        if tc:
            args = json.loads(tc[0]["function"]["arguments"])
            cols = args.get("columns", [])
            print(f"\n┌─ Run {run+1} ─────────────────────────────────────────────┐")
            print(f"│ {'字段':<10} {'角色':<14} {'uia':<6} {'中文名':<12} │")
            print(f"│ {'-'*10} {'-'*14} {'-'*6} {'-'*12} │")
            for c in cols:
                n = c.get("name", "?")
                rl = c.get("suggested_role", "?")
                u = c.get("used_in_analysis")
                u_str = "true" if u is True else ("false" if u is False else "None")
                dn = c.get("display_name", "")[:10]
                flag = ""
                # 对「店铺变动趋势」，期望：
                #   Period → feature 或 time_index, uia=true（趋势需要时间）
                #   Inc1/Inc2/Inc3 → feature 或 target, uia=true（收入列）
                #   StoreID → identifier, uia=false
                #   Code → identifier, uia=false
                #   BU → ignore 或 feature（事业部可能相关）
                #   Bos1 → ignore（费用项与变动趋势无关）
                if n == "Period" and u is False: flag = " ⚠️ 趋势分析需要周期！"
                if n == "StoreID" and u is True: flag = " ⚠️ ID 不应参与"
                if n == "Code" and u is True and rl != "identifier": flag = " ⚠️ 编码不应参与"
                if n == "Bos1" and u is True: flag = " ⚠️ 费用与趋势无关？"
                print(f"│ {n:<10} {rl:<14} {u_str:<6} {dn:<12} │{flag}")
            print(f"└{'─'*50}┘")
        else:
            text = r["choices"][0]["message"].get("content", "")[:200]
            print(f"\n  Run {run+1}: 无 tool_calls, text={text}")
    except Exception as e:
        print(f"\n  Run {run+1}: ❌ {e}")

print("\n" + "=" * 80)
