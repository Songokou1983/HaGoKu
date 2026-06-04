#!/usr/bin/env python3
"""字段理解+分析字段选择 端到端 LLM 测试 — 极致省 token"""
import csv, json, urllib.request, time, re
from pathlib import Path

LLM_URL = "http://localhost:8080/v1/chat/completions"
MODEL = "qwen"
G = "\033[32m"; R = "\033[31m"; B = "\033[1m"; X = "\033[0m"
ok = 0; ng = 0
def ck(label, cond, det=""):
    global ok, ng
    if cond: print(f"  {G}✓{X} {label}"); ok += 1
    else: print(f"  {R}✗{X} {label} {det}"); ng += 1

def llm(sys_msg, usr_msg, tools=None, max_tok=1024, temp=0.0):
    p = {"model": MODEL, "messages": [{"role": "system", "content": sys_msg},
         {"role": "user", "content": usr_msg}], "temperature": temp, "max_tokens": max_tok}
    if tools: p["tools"] = tools; p["tool_choice"] = "auto"
    req = urllib.request.Request(LLM_URL, data=json.dumps(p).encode(),
          headers={"Content-Type": "application/json"})
    r = json.loads(urllib.request.urlopen(req, timeout=120).read().decode())
    m = r["choices"][0]["message"]
    return m.get("tool_calls", []), m.get("content", "") or ""

# ── 工具定义 ──
SCOUT_TOOL = [{"type": "function", "function": {
    "name": "submit_field_inference",
    "description": "提交字段推断结果",
    "parameters": {"type": "object", "properties": {
        "columns": {"type": "array", "items": {"type": "object", "properties": {
            "name": {"type": "string"}, "inferred_type": {"type": "string",
                "enum": ["numeric", "categorical", "datetime", "id", "text", "unknown"]},
            "suggested_role": {"type": "string",
                "enum": ["target", "feature", "identifier", "time_index", "ignore", "unknown"]},
            "display_name": {"type": "string", "description": "≤8字中文名"},
            "description": {"type": "string", "description": "一句话业务含义"},
            "confidence": {"type": "number"}, "needs_user_input": {"type": "boolean"},
            "used_in_analysis": {"type": "boolean"}},
        "required": ["name", "inferred_type", "suggested_role"]}}
    }, "required": ["columns"]}
}}]

CORRECT_TOOL = [{"type": "function", "function": {
    "name": "update_field_understanding",
    "description": "更新字段中文名/含义/角色",
    "parameters": {"type": "object", "properties": {
        "column_name": {"type": "string"},
        "display_name": {"type": "string", "description": "≤8字中文名"},
        "description": {"type": "string", "description": "业务含义展开"},
        "suggested_role": {"type": "string", "enum": ["target", "feature", "identifier", "ignore"]}
    }, "required": ["column_name"]}
}}, {"type": "function", "function": {
    "name": "update_field_role",
    "description": "更新分析目标变量和特征变量",
    "parameters": {"type": "object", "properties": {
        "target": {"type": "string", "description": "目标变量列名"},
        "features": {"type": "array", "items": {"type": "string"}},
        "ignored": {"type": "array", "items": {"type": "string"}}
    }, "required": []}
}}]


def load_csv(path):
    with open(path) as f:
        rows = list(csv.DictReader(f))
    cols = list(rows[0].keys())
    profile = []
    for c in cols:
        vals = [r[c] for r in rows if r[c].strip()]
        n = len(rows); nu = len(set(vals)); nulls = n - len(vals)
        is_num = all(re.match(r'^-?[\d.]+$', v) for v in vals[:min(20, len(vals))])
        samples = list(dict.fromkeys(vals))[:3]
        p = {"name": c, "n_total": n, "n_null": nulls, "n_unique": nu, "samples": samples}
        if is_num:
            nv = sorted(float(v) for v in vals)
            p.update({"dtype": "numeric", "min": nv[0], "max": nv[-1],
                      "median": nv[len(nv)//2], "mean": round(sum(nv)/len(nv), 2)})
        else:
            p["dtype"] = "categorical"
        profile.append(p)
    return cols, profile, rows


# ══════════════════════════════════  TEST 1 ══════════════════════════════════
print(f"\n{B}TEST 1: 零售缩写列名 — 分析目标推断{X}")
cols, prof, _ = load_csv("test_data/scenario_a_retail.csv")

sys1 = f"""你是数据分析侦察员。根据列画像和分析目标，推断每个字段的角色。
必须调用 submit_field_inference 提交结果。"""

usr1 = f"""分析目标：比较各渠道的销售额和利润，找出ROI最高的渠道

列画像：
{json.dumps(prof, ensure_ascii=False)}"""

tc, txt = llm(sys1, usr1, SCOUT_TOOL, max_tok=2048)
print(f"  LLM: {len(tc)} tool_calls")

if tc:
    args = json.loads(tc[0]["function"]["arguments"])
    cols_out = args.get("columns", [])
    roles = {c["name"]: c.get("suggested_role","?") for c in cols_out}
    descs = {c["name"]: c.get("display_name","") for c in cols_out}
    print(f"  角色: {roles}")
    print(f"  中文名: {descs}")

    ck("SLS_AMT 是 target", roles.get("SLS_AMT") == "target", f"={roles.get('SLS_AMT')}")
    ck("CST_AMT 是 feature", roles.get("CST_AMT") == "feature", f"={roles.get('CST_AMT')}")
    ck("SKU_ID 是 identifier", roles.get("SKU_ID") == "identifier", f"={roles.get('SKU_ID')}")
    ck("CHN_TYP 参与分析(非ignore)", roles.get("CHN_TYP") not in ("ignore","unknown"),
       f"={roles.get('CHN_TYP')}")
    ck("ZONE 参与分析(非ignore)", roles.get("ZONE") not in ("ignore","unknown"),
       f"={roles.get('ZONE')}")
    ck("SLS_AMT 有中文名", bool(descs.get("SLS_AMT")), f"={descs.get('SLS_AMT')}")
else:
    ck("LLM 返回 tool_calls", False, f"文本: {txt[:150]}")


# ══════════════════════════════════  TEST 2 ══════════════════════════════════
print(f"\n{B}TEST 2: 临床试验极简列名 — 需要领域知识推断{X}")
cols, prof, _ = load_csv("test_data/scenario_c_clinical.csv")

sys2 = sys1
usr2 = f"""分析目标：比较Active组和Placebo组在治疗A疗效指标上的差异是否显著

列画像：
{json.dumps(prof, ensure_ascii=False)}"""

tc, txt = llm(sys2, usr2, SCOUT_TOOL, max_tok=2048)
print(f"  LLM: {len(tc)} tool_calls")

if tc:
    args = json.loads(tc[0]["function"]["arguments"])
    cols_out = args.get("columns", [])
    roles = {c["name"]: c.get("suggested_role","?") for c in cols_out}
    descs = {c["name"]: c.get("display_name","") for c in cols_out}
    used = {c["name"]: c.get("used_in_analysis") for c in cols_out}
    print(f"  角色: {roles}")
    print(f"  used_in_analysis: {used}")

    ck("TRT_A 参与分析", roles.get("TRT_A") in ("target","feature"),
       f"={roles.get('TRT_A')}")
    ck("ARM 参与分析(分组)", roles.get("ARM") in ("target","feature"),
       f"={roles.get('ARM')}")
    ck("PID 不参与分析", roles.get("PID") in ("identifier","ignore"),
       f"={roles.get('PID')}")
    ck("SITE 参与分析", roles.get("SITE") in ("target","feature"),
       f"={roles.get('SITE')}")
    ck("VST 参与分析(时间)", roles.get("VST") in ("feature","time_index"),
       f"={roles.get('VST')}")
    ck("AE_CNT 参与分析(安全性)", used.get("AE_CNT") != False,
       f"used_in_analysis={used.get('AE_CNT')}")
else:
    ck("LLM 返回 tool_calls", False, f"文本: {txt[:150]}")


# ══════════════════════════════════  TEST 3 ══════════════════════════════════
print(f"\n{B}TEST 3: 初始错误→用户纠正→重推断（模拟 Scout 反馈循环）{X}")
cols, prof, _ = load_csv("test_data/scenario_d_ecommerce.csv")

# 阶段1: 给一个不带分析目标的初始推理（模拟 LLM 不知道要分析什么）
sys3a = "你是数据分析侦察员。推断每个字段的类型和角色。必须调用 submit_field_inference。"
usr3a = f"数据列表：{', '.join(cols)}\n列画像：{json.dumps(prof, ensure_ascii=False)}"

tc1, _ = llm(sys3a, usr3a, SCOUT_TOOL, max_tok=2048)
if tc1:
    args1 = json.loads(tc1[0]["function"]["arguments"])
    roles1 = {c["name"]: c.get("suggested_role","?") for c in args1.get("columns", [])}
    print(f"  初始角色: {roles1}")
else:
    roles1 = {}
    print(f"  初始LLM无tool_calls，文本: {txt[:100]}")

# 阶段2: 用户反馈（纠正 + 分析目标）
print(f"\n  用户反馈: page_views→页面浏览量, purchases→购买次数(目标), user_token→用户标识, campaign_id→忽略")

sys3b = f"""用户正在纠正字段理解。请调用 update_field_understanding 和 update_field_role 更新。

当前字段状态：
{chr(10).join(f'  - {c}: 角色={roles1.get(c,"?")}' for c in cols)}

用户分析目标：找出驱动 purchases 的关键因素"""

tc2, _ = llm(sys3b, f"用户说：purchases是分析目标（用户购买次数）。page_views是页面浏览量。cart_adds是加购次数。session_mins是会话时长。user_token是用户唯一标识。campaign_id不参与分析。device_type是设备类型。",
             CORRECT_TOOL, max_tok=1024, temp=0.1)

ctx = {c: {"role": roles1.get(c,"?"), "dn": "", "desc": ""} for c in cols}
print(f"  LLM反馈: {len(tc2)} 个tool_call")
for t in tc2:
    a = json.loads(t["function"]["arguments"])
    fn = t["function"]["name"]
    cn = a.get("column_name", "")
    if fn == "update_field_understanding" and cn in ctx:
        if a.get("display_name"): ctx[cn]["dn"] = a["display_name"]
        if a.get("description"): ctx[cn]["desc"] = a["description"]
        if a.get("suggested_role"): ctx[cn]["role"] = a["suggested_role"]
        print(f"    {cn} → dn={a.get('display_name','')[:12]} role={a.get('suggested_role','')}")
    elif fn == "update_field_role":
        if a.get("target"): ctx[a["target"]]["role"] = "target"
        for f in a.get("features", []):
            if f in ctx: ctx[f]["role"] = "feature"
        for ig in a.get("ignored", []):
            if ig in ctx: ctx[ig]["role"] = "ignore"
        print(f"    ROLES: target={a.get('target')} features={a.get('features')} ignored={a.get('ignored')}")

ck("purchases→target", ctx["purchases"]["role"] == "target", f"={ctx['purchases']['role']}")
ck("page_views→feature", ctx["page_views"]["role"] == "feature", f"={ctx['page_views']['role']}")
ck("user_token→identifier", ctx["user_token"]["role"] in ("identifier","ignore"),
   f"={ctx['user_token']['role']}")
ck("campaign_id→ignore", ctx["campaign_id"]["role"] in ("identifier","ignore"),
   f"={ctx['campaign_id']['role']}")
ck("purchases 有中文名", bool(ctx["purchases"]["dn"]), f"={ctx['purchases']['dn']}")
ck("page_views 有中文名", bool(ctx["page_views"]["dn"]), f"={ctx['page_views']['dn']}")

# 阶段3: 用更新后的 context 重跑推理（模拟 Cleaner 重跑拿到正确字段）
print(f"\n  阶段3: 重跑推理（context已更新）")
usr3c = f"""分析目标：找出驱动 purchases 的关键因素

字段理解（用户已确认）：
{chr(10).join(f'  - {c}: {ctx[c]["dn"]}({ctx[c]["desc"][:30] if ctx[c]["desc"] else "?"}) 角色={ctx[c]["role"]}' for c in cols)}

列画像：
{json.dumps(prof, ensure_ascii=False)}"""

tc3, _ = llm(sys3a, usr3c, SCOUT_TOOL, max_tok=2048)
if tc3:
    args3 = json.loads(tc3[0]["function"]["arguments"])
    roles3 = {c["name"]: c.get("suggested_role","?") for c in args3.get("columns", [])}
    print(f"  重跑角色: {roles3}")
    ck("重跑后 purchases→target", roles3.get("purchases") == "target", f"={roles3.get('purchases')}")
    ck("重跑后 campaign_id 不干扰分析", roles3.get("campaign_id") != "target",
       f"={roles3.get('campaign_id')}")
else:
    ck("LLM 返回 tool_calls", False, f"文本: {txt[:150]}")


# ══════════════════════════════════  TEST 4 ══════════════════════════════════
print(f"\n{B}TEST 4: HR 中文列名 — 分析目标字段选择{X}")
cols, prof, _ = load_csv("test_data/scenario_b_hr.csv")

sys4 = sys1
usr4 = f"""分析目标：找出影响员工绩效奖金的关键因素，哪些部门的奖金差距最大

列画像：
{json.dumps(prof, ensure_ascii=False)}"""

tc, txt = llm(sys4, usr4, SCOUT_TOOL, max_tok=2048)
print(f"  LLM: {len(tc)} tool_calls")

if tc:
    args = json.loads(tc[0]["function"]["arguments"])
    cols_out = args.get("columns", [])
    roles = {c["name"]: c.get("suggested_role","?") for c in cols_out}
    used = {c["name"]: c.get("used_in_analysis") for c in cols_out}
    types = {c["name"]: c.get("inferred_type") for c in cols_out}
    print(f"  角色: {roles}")
    print(f"  used: {used}")

    ck("绩效奖金 是 target", roles.get("绩效奖金") == "target", f"={roles.get('绩效奖金')}")
    ck("基本工资 是 feature", roles.get("基本工资") == "feature", f"={roles.get('基本工资')}")
    ck("部门 是 feature(分组)", roles.get("部门") in ("feature","target"), f"={roles.get('部门')}")
    ck("加班时长 是 feature", roles.get("加班时长") == "feature", f"={roles.get('加班时长')}")
    ck("入职年限 是 feature", roles.get("入职年限") == "feature", f"={roles.get('入职年限')}")
    ck("工号 不是 target", roles.get("工号") != "target", f"={roles.get('工号')}")
else:
    ck("LLM 返回 tool_calls", False, f"文本: {txt[:150]}")


# ══════════════════════════════════  TEST 5 ══════════════════════════════════
print(f"\n{B}TEST 5: 分析目标不匹配 — 用户改了目标，LLM 能否重新选字段{X}")

sys5 = sys1
usr5 = f"""分析目标：分析员工加班时长与入职年限的关系，新员工和老员工加班差异大吗

列画像：
{json.dumps(prof, ensure_ascii=False)}"""

tc, txt = llm(sys5, usr5, SCOUT_TOOL, max_tok=2048)
print(f"  LLM: {len(tc)} tool_calls")

if tc:
    args = json.loads(tc[0]["function"]["arguments"])
    cols_out = args.get("columns", [])
    roles = {c["name"]: c.get("suggested_role","?") for c in cols_out}
    used = {c["name"]: c.get("used_in_analysis") for c in cols_out}
    print(f"  角色(目标=加班关系): {roles}")

    ck("加班时长 是 target(目标是加班)", roles.get("加班时长") == "target",
       f"={roles.get('加班时长')}")
    ck("入职年限 是 feature", roles.get("入职年限") == "feature",
       f"={roles.get('入职年限')}")
    ck("绩效奖金 不再是 target", roles.get("绩效奖金") != "target",
       f"={roles.get('绩效奖金')}")
    ck("部门 参与分析", roles.get("部门") in ("feature","target"),
       f"={roles.get('部门')}")
else:
    ck("LLM 返回 tool_calls", False, f"文本: {txt[:150]}")


# ══════════════════════════════════  结果 ══════════════════════════════════
print(f"\n{B}结果: {G}{ok} 通过{X}, {R}{ng} 失败{X} (共 {ok+ng}){X}")
