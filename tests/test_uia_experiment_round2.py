#!/usr/bin/env python3
"""对照实验 Round 2: 验证「用 ignore 替代 feature→false」方案

在变体 A/B 基础上追加变体 D:
  - 明确指示：与目标无关的字段 → suggested_role=ignore（而非 feature）
  - 然后 used_in_analysis 可从 role 机械推导
"""
import json, urllib.request, sys

LLM_URL = "http://localhost:8080/v1/chat/completions"
MODEL = "qwen"

SAMPLE_COLUMNS = [
    {"name": "StoreID", "dtype": "int64", "n_unique": 50, "sample": [1001, 1002, 1003]},
    {"name": "Date", "dtype": "datetime64", "n_unique": 365, "sample": ["2024-01-01", "2024-01-02"]},
    {"name": "Channel", "dtype": "object", "n_unique": 3, "sample": ["线上", "线下", "线上"]},
    {"name": "ProductID", "dtype": "int64", "n_unique": 200, "sample": [5001, 5002, 5003]},
    {"name": "Revenue", "dtype": "float64", "n_unique": 300, "sample": [1500.5, 2300.0, 1800.0]},
    {"name": "Quantity", "dtype": "int64", "n_unique": 10, "sample": [3, 5, 2]},
    {"name": "Discount", "dtype": "float64", "n_unique": 8, "sample": [0.1, 0.0, 0.15]},
    {"name": "Region", "dtype": "object", "n_unique": 5, "sample": ["华东", "华北", "华南"]},
]
ANALYSIS_GOAL = "分析各渠道的收入对比情况"
FIELDS_DESC = "\n".join(f"  {c['name']}: dtype={c['dtype']}, unique={c['n_unique']}, sample={c['sample']}" for c in SAMPLE_COLUMNS)

# 变体 D schema: same as B but prompt emphasizes ignore
SCHEMA_D = {
    "type": "object", "properties": {
        "columns": {"type": "array", "items": {"type": "object", "properties": {
            "name": {"type": "string"},
            "inferred_type": {"type": "string", "enum": ["numeric","categorical","datetime","id","text","unknown"]},
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            "suggested_role": {"type": "string", "enum": ["target","feature","identifier","time_index","ignore","unknown"]},
            "display_name": {"type": "string"},
            "description": {"type": "string"},
            "needs_user_input": {"type": "boolean"},
            "used_in_analysis": {"type": "boolean", "description": "是否参与本次分析。能服务目标=true，无关=false"},
        }, "required": ["name","inferred_type","suggested_role","display_name","description","needs_user_input"]}},
    }, "required": ["columns"]
}

PROMPT_D = (
    "你是专业数据分析侦察员。基于每列的数据画像，推断每个字段的语义角色。\n"
    "你必须调用 submit_field_inference 工具来提交你的分析结果。\n\n"
    f"【最高优先级 — 用户分析目标】\n"
    f"「{ANALYSIS_GOAL}」\n\n"
    f"角色分配规则（严格按分析目标判断，不要仅根据数据类型猜测）：\n"
    f"  • target: 被分析的指标，即用户关心的核心度量（如「收入」）\n"
    f"  • feature: 用于分组/切分/解释目标变量的维度（如「渠道」）\n"
    f"  • identifier: 纯标识列（如 ID、编码、序号），不参与计算\n"
    f"  • time_index: 时间戳，仅在用于趋势分析时为 feature\n"
    f"  • ignore: 与本次分析目标「{ANALYSIS_GOAL}」**完全无关**的列\n"
    f"            ⚡ 关键判断：「这个列能帮用户回答他的问题吗？」\n"
    f"            不能 → 设为 ignore，不要设为 feature\n"
    f"            举例：用户问「渠道收入对比」，销量/折扣/地区 → ignore\n\n"
    f"used_in_analysis 规则：\n"
    f"  • target 和 feature → true\n"
    f"  • identifier、time_index、ignore → false\n"
)

def call_llm(sys_msg, usr_msg, schema, label, run_idx):
    tool = {"type":"function","function":{"name":"submit_field_inference","description":"提交字段推断","parameters":schema}}
    payload = {"model":MODEL,"messages":[{"role":"system","content":sys_msg},{"role":"user","content":usr_msg}],
               "temperature":0.0,"max_tokens":2048,"tools":[tool],
               "tool_choice":{"type":"function","function":{"name":"submit_field_inference"}}}
    try:
        req = urllib.request.Request(LLM_URL, data=json.dumps(payload).encode(),
              headers={"Content-Type":"application/json"})
        r = json.loads(urllib.request.urlopen(req, timeout=180).read().decode())
        tc = r["choices"][0]["message"].get("tool_calls",[])
        if tc: return json.loads(tc[0]["function"]["arguments"]).get("columns",[])
        print(f"  {label} run#{run_idx}: no tool_calls, text={r['choices'][0]['message'].get('content','')[:100]}")
        return None
    except Exception as e:
        print(f"  {label} run#{run_idx}: error={e}")
        return None

EXPECTED = {
    "StoreID": ("identifier", "false"),
    "Date": ("time_index或ignore", "false"),
    "Channel": ("feature", "true"),
    "ProductID": ("identifier", "false"),
    "Revenue": ("target", "true"),
    "Quantity": ("ignore", "false"),
    "Discount": ("ignore", "false"),
    "Region": ("ignore", "false"),
}

def run_variant(label, prompt, schema, n=3):
    usr = f"请分析以下数据集的字段语义：\n字段列表：\n{FIELDS_DESC}"
    all_runs = []
    for i in range(n):
        print(f"  {label} run {i+1}/{n}...", end=" ", flush=True)
        cols = call_llm(prompt, usr, schema, label, i+1)
        if cols:
            cm = {c.get("name","?"): c for c in cols}
            roles = {n: cm[n].get("suggested_role","?") for n in EXPECTED}
            uias = {n: cm[n].get("used_in_analysis") for n in EXPECTED}
            tc = sum(1 for v in uias.values() if v is True)
            fc = sum(1 for v in uias.values() if v is False)
            nc = sum(1 for v in uias.values() if v is None)
            print(f"true={tc} false={fc} none={nc}  roles={roles}")
        else:
            print("(no output)")
        all_runs.append(cols)

    print(f"\n  {'Field':<12} {'期望 role':<18} {'期望 uia':<8} {'Run1':<25} {'Run2':<25} {'Run3':<25}")
    print(f"  {'-'*12} {'-'*18} {'-'*8} {'-'*25} {'-'*25} {'-'*25}")
    ok = 0; fail = 0
    for name in EXPECTED:
        exp_role, exp_uia = EXPECTED[name]
        exp_uia_bool = exp_uia == "true"
        cells = []
        for cols in all_runs:
            if cols is None:
                cells.append("N/A")
                continue
            cm = {c.get("name","?"): c for c in cols}
            item = cm.get(name, {})
            r = item.get("suggested_role","?")
            u = item.get("used_in_analysis")
            u_str = "true" if u is True else ("false" if u is False else "None")
            cells.append(f"{r} / uia={u_str}")
        all_match = all(
            (cols and {c.get("name","?"):c for c in cols}.get(name,{}).get("used_in_analysis") is exp_uia_bool)
            for cols in all_runs if cols
        )
        if all_match: ok += 1
        else: fail += 1
        flag = "✅" if all_match else "❌"
        print(f"  {flag} {name:<10} {exp_role:<18} {exp_uia:<8} {cells[0] if len(cells)>0 else '':<25} {cells[1] if len(cells)>1 else '':<25} {cells[2] if len(cells)>2 else '':<25}")
    print(f"  {'─'*90}")
    print(f"  准确率: {ok}/{ok+fail} ({ok*100/(ok+fail):.0f}%)")
    return ok == (ok+fail)

print("═" * 90)
print("  对照实验 Round 2: 变体 D — 用 ignore 角色替代 feature→false")
print("═" * 90)
run_variant("D: ignore 强化 prompt", PROMPT_D, SCHEMA_D, n=3)
