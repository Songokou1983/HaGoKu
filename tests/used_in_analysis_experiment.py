#!/usr/bin/env python3
"""对照实验：测试 Qwen 模型是否能在不同 prompt/schema 下正确输出 used_in_analysis

实验设计：
  同一数据集（8 列零售数据）+ 同一分析目标（「各渠道收入对比」）
  3 种变体，各跑 3 次（共 9 次 LLM 调用）

变体 A: 当前生产 prompt + schema（used_in_analysis 在 required 中）
变体 B: 增强 prompt（已落地）+ schema（used_in_analysis 不在 required 中）
变体 C: 极简 prompt（只给角色描述，无 used_in_analysis 指令）

判断标准：
  - 渠道字段（Channel）、收入字段（Revenue）→ 期望 true
  - ID 字段（StoreID, ProductID）→ 期望 false
  - 日期字段（Date）→ 期望 false 或 true（看是否用于趋势）
  - 无关字段（Region, Discount, Quantity）→ 期望 false
"""

import json
import urllib.request
import sys
from pathlib import Path

LLM_URL = "http://localhost:8080/v1/chat/completions"
MODEL = "qwen"

# ── 测试数据：8 列零售数据 ──
SAMPLE_COLUMNS = [
    {"name": "StoreID", "dtype": "int64", "n_unique": 50, "sample": [1001, 1002, 1003, 1001, 1002]},
    {"name": "Date", "dtype": "datetime64", "n_unique": 365, "sample": ["2024-01-01", "2024-01-02", "2024-01-03"]},
    {"name": "Channel", "dtype": "object", "n_unique": 3, "sample": ["线上", "线下", "线上", "线下", "线下"]},
    {"name": "ProductID", "dtype": "int64", "n_unique": 200, "sample": [5001, 5002, 5003, 5001, 5002]},
    {"name": "Revenue", "dtype": "float64", "n_unique": 300, "sample": [1500.5, 2300.0, 1800.0, 1200.0, 2100.0]},
    {"name": "Quantity", "dtype": "int64", "n_unique": 10, "sample": [3, 5, 2, 4, 6]},
    {"name": "Discount", "dtype": "float64", "n_unique": 8, "sample": [0.1, 0.0, 0.15, 0.0, 0.05]},
    {"name": "Region", "dtype": "object", "n_unique": 5, "sample": ["华东", "华北", "华南", "华东", "西南"]},
]

ANALYSIS_GOAL = "分析各渠道的收入对比情况"

# ── 共享的字段表格描述 ──
FIELDS_DESC = "\n".join(
    f"  {c['name']}: dtype={c['dtype']}, unique={c['n_unique']}, sample={c['sample'][:3]}"
    for c in SAMPLE_COLUMNS
)

# ── Schema 变体 ──

def make_schema_variant_a():
    """变体 A: 当前生产 schema — used_in_analysis 在 required 中"""
    return {
        "type": "object",
        "properties": {
            "columns": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "inferred_type": {"type": "string", "enum": ["numeric", "categorical", "datetime", "id", "text", "unknown"]},
                        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                        "suggested_role": {"type": "string", "enum": ["target", "feature", "identifier", "time_index", "ignore", "unknown"]},
                        "display_name": {"type": "string", "description": "简短中文业务名称（≤6字）"},
                        "description": {"type": "string", "description": "业务含义理解"},
                        "needs_user_input": {"type": "boolean"},
                        "used_in_analysis": {"type": "boolean", "description": "是否参与本次分析"},
                    },
                    "required": ["name", "inferred_type", "confidence", "suggested_role", "display_name", "description", "needs_user_input", "used_in_analysis"],
                },
            },
        },
        "required": ["columns"],
    }


def make_schema_variant_b():
    """变体 B: 修复后 schema — used_in_analysis 不在 required 中"""
    return {
        "type": "object",
        "properties": {
            "columns": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "inferred_type": {"type": "string", "enum": ["numeric", "categorical", "datetime", "id", "text", "unknown"]},
                        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                        "suggested_role": {"type": "string", "enum": ["target", "feature", "identifier", "time_index", "ignore", "unknown"]},
                        "display_name": {"type": "string", "description": "简短中文业务名称（≤6字）"},
                        "description": {"type": "string", "description": "业务含义理解"},
                        "needs_user_input": {"type": "boolean"},
                        "used_in_analysis": {"type": "boolean", "description": "该字段是否参与本次分析。严格根据分析目标判断：能服务于用户问题的字段=true，无关字段=false。标识符、ID、与问题无关的文本列通常=false。"},
                    },
                    "required": ["name", "inferred_type", "confidence", "suggested_role", "display_name", "description", "needs_user_input"],
                },
            },
        },
        "required": ["columns"],
    }


def make_schema_variant_c():
    """变体 C: 极简 schema — 无 used_in_analysis 字段"""
    return {
        "type": "object",
        "properties": {
            "columns": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "inferred_type": {"type": "string", "enum": ["numeric", "categorical", "datetime", "id", "text", "unknown"]},
                        "confidence": {"type": "number"},
                        "suggested_role": {"type": "string", "enum": ["target", "feature", "identifier", "time_index", "ignore", "unknown"]},
                        "display_name": {"type": "string"},
                        "description": {"type": "string"},
                        "needs_user_input": {"type": "boolean"},
                    },
                    "required": ["name", "inferred_type", "suggested_role"],
                },
            },
        },
        "required": ["columns"],
    }


# ── Prompt 变体 ──

def make_sys_prompt_a():
    """变体 A: 当前生产 prompt"""
    return (
        "你是专业数据分析侦察员。基于每列的数据画像，推断每个字段的语义角色。\n"
        "你必须调用 submit_field_inference 工具来提交你的分析结果。\n\n"
        f"【最高优先级 — 用户分析目标】\n"
        f"「{ANALYSIS_GOAL}」\n"
        f"你必须逐一检查每个字段是否能服务于上述分析目标。\n"
        f"将最相关的字段设为 target（目标变量），辅助字段设为 feature（特征变量），\n"
        f"无关字段设为 ignore 或 identifier。\n"
        f"不要仅根据数据类型（数值/文本/日期）推断角色——必须结合分析目标做语义判断。"
    )


def make_sys_prompt_b():
    """变体 B: 增强 prompt（已落地）+ used_in_analysis 明确指令"""
    return (
        "你是专业数据分析侦察员。基于每列的数据画像，推断每个字段的语义角色。\n"
        "你必须调用 submit_field_inference 工具来提交你的分析结果。\n\n"
        f"【最高优先级 — 用户分析目标】\n"
        f"「{ANALYSIS_GOAL}」\n"
        f"你必须逐一检查每个字段是否能服务于上述分析目标。\n"
        f"将最相关的字段设为 target（目标变量），辅助字段设为 feature（特征变量），\n"
        f"无关字段设为 ignore 或 identifier。\n"
        f"不要仅根据数据类型（数值/文本/日期）推断角色——必须结合分析目标做语义判断。\n"
        f"\n"
        f"⚡ 关键：对于与本次分析目标「{ANALYSIS_GOAL}」无关的字段，\n"
        f"必须将 used_in_analysis 设为 false。\n"
        f"只有确实能服务于用户分析目标的字段才设为 true。\n"
        f"举例：用户问「各渠道收入对比」——渠道字段、收入字段 = true；\n"
        f"设备型号、注册日期等无关字段 = false。"
    )


def make_sys_prompt_c():
    """变体 C: 极简 prompt — 只有角色描述"""
    return (
        "你是数据分析师。根据字段的数据画像，推断每个字段的语义角色。\n"
        "调用 submit_field_inference 工具提交结果。"
    )


# ── LLM 调用 ──

def call_llm(sys_msg, usr_msg, schema, variant_label, run_idx):
    """调用 LLM，返回 tool_calls 中的 columns 数组"""
    tool = {
        "type": "function",
        "function": {
            "name": "submit_field_inference",
            "description": "提交字段语义推断结果",
            "parameters": schema,
        },
    }
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": sys_msg},
            {"role": "user", "content": usr_msg},
        ],
        "temperature": 0.0,
        "max_tokens": 2048,
        "tools": [tool],
        "tool_choice": {"type": "function", "function": {"name": "submit_field_inference"}},
    }
    try:
        req = urllib.request.Request(
            LLM_URL,
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
        )
        resp = json.loads(urllib.request.urlopen(req, timeout=180).read().decode())
        msg = resp["choices"][0]["message"]
        tool_calls = msg.get("tool_calls", [])
        if tool_calls:
            args = json.loads(tool_calls[0]["function"]["arguments"])
            return args.get("columns", [])
        else:
            text = msg.get("content", "")[:200]
            print(f"  ⚠️  {variant_label} run#{run_idx}: 无 tool_calls, text={text}")
            return None
    except Exception as e:
        print(f"  ❌ {variant_label} run#{run_idx}: LLM error: {e}")
        return None


def analyze_results(variant_label, all_runs):
    """分析多次运行的 used_in_analysis 输出"""
    print(f"\n{'='*70}")
    print(f"  {variant_label}")
    print(f"{'='*70}")

    # 聚合每个字段在所有 run 中的 used_in_analysis 值
    field_results = {c["name"]: [] for c in SAMPLE_COLUMNS}

    for run_idx, columns in enumerate(all_runs):
        if columns is None:
            continue
        col_map = {c.get("name", ""): c for c in columns}
        for name in field_results:
            item = col_map.get(name, {})
            uia = item.get("used_in_analysis")
            field_results[name].append(uia)

    # 打印结果
    print(f"  {'Field':<12} {'Role':<12} {'UIA (期望)':<15} {'Run1':<8} {'Run2':<8} {'Run3':<8} {'结论'}")
    print(f"  {'-'*12} {'-'*12} {'-'*15} {'-'*8} {'-'*8} {'-'*8} {'-'*20}")

    expected = {
        "StoreID": (False, "ID 列"),
        "Date": (False, "与渠道收入无关"),
        "Channel": (True, "渠道 = 分析维度"),
        "ProductID": (False, "ID 列"),
        "Revenue": (True, "收入 = 目标变量"),
        "Quantity": (False, "销量非渠道收入"),
        "Discount": (False, "折扣非渠道收入"),
        "Region": (False, "地区非渠道维度"),
    }

    all_ok = True
    for name, vals in field_results.items():
        exp, reason = expected[name]
        role = ""
        if all_runs[0]:
            for c in all_runs[0]:
                if c.get("name") == name:
                    role = c.get("suggested_role", "?")
                    break

        run_strs = []
        for v in vals:
            if v is True:
                run_strs.append("true")
            elif v is False:
                run_strs.append("false")
            elif v is None:
                run_strs.append("None")
            else:
                run_strs.append(str(v)[:5])

        # 多数投票
        true_cnt = sum(1 for v in vals if v is True)
        false_cnt = sum(1 for v in vals if v is False)
        none_cnt = sum(1 for v in vals if v is None)

        if none_cnt >= 2:
            verdict = "⚠️ 未输出（LLM 不填）"
            all_ok = False
        elif exp and true_cnt >= 2:
            verdict = "✅ 正确"
        elif exp and true_cnt < 2:
            verdict = "❌ 应 true 但非 true"
            all_ok = False
        elif not exp and false_cnt >= 2:
            verdict = "✅ 正确"
        elif not exp and false_cnt < 2:
            verdict = f"❌ 应 false 但 {true_cnt}x true"
            all_ok = False
        else:
            verdict = "?"

        print(f"  {name:<12} {role:<12} {f'{exp} ({reason})':<15} {run_strs[0] if len(run_strs)>0 else 'N/A':<8} {run_strs[1] if len(run_strs)>1 else 'N/A':<8} {run_strs[2] if len(run_strs)>2 else 'N/A':<8} {verdict}")

    return all_ok


def main():
    usr_msg = f"请分析以下数据集的字段语义：\n字段列表：\n{FIELDS_DESC}"

    variants = [
        ("A: 生产 prompt + required", make_sys_prompt_a(), make_schema_variant_a()),
        ("B: 增强 prompt + 非 required", make_sys_prompt_b(), make_schema_variant_b()),
        ("C: 极简 prompt + 无 uia 字段", make_sys_prompt_c(), make_schema_variant_c()),
    ]

    all_passed = True
    for label, sys_prompt, schema in variants:
        print(f"\n🧪 测试变体: {label}")
        all_runs = []
        for run_idx in range(3):
            print(f"  run {run_idx+1}/3...", end=" ", flush=True)
            columns = call_llm(sys_prompt, usr_msg, schema, label, run_idx + 1)
            if columns:
                uia_vals = {c.get("name", "?"): c.get("used_in_analysis") for c in columns}
                true_cnt = sum(1 for v in uia_vals.values() if v is True)
                false_cnt = sum(1 for v in uia_vals.values() if v is False)
                none_cnt = sum(1 for v in uia_vals.values() if v is None)
                print(f"  true={true_cnt} false={false_cnt} none={none_cnt}")
            else:
                print("  (无输出)")
            all_runs.append(columns)

        ok = analyze_results(label, all_runs)
        if not ok:
            all_passed = False

    print(f"\n{'='*70}")
    if all_passed:
        print("  ✅ 全部通过")
    else:
        print("  ❌ 存在失败")
    print(f"{'='*70}")


if __name__ == "__main__":
    main()
