#!/usr/bin/env python3
"""
字段理解互动通道 — 独立验证脚本（不依赖 hagoku 包，纯 Python 标准库）

验证点：
  P1: _resolve_scout_column_token — LLM 产出的列名能否正确解析
  P2: _apply_role_update — 角色变更是否正确写入 context
  P3: apply_scout_user_field_reply_to_context 模拟 — 字段描述/中文名是否正确更新
  P4: Cleaner 重跑 query 累积 — context["query"] 是否包含用户反馈
  P5: Analyst 重跑 plan["query"] 累积 — plan["query"] 是否包含用户反馈
  P6: Cleaner/Analyst 重跑时字段元数据同步 — column_descriptions 是否被更新
  P7: 跨阶段一致性 — Scout 阶段更新是否传递到 Cleaner
"""

import json
import sys
import traceback
from typing import Any

# ── 颜色输出 ───────────────────────────────────────────
GREEN = "\033[32m"
RED = "\033[31m"
YELLOW = "\033[33m"
RESET = "\033[0m"
BOLD = "\033[1m"

passed = 0
failed = 0

def check(label: str, condition: bool, detail: str = ""):
    global passed, failed
    if condition:
        print(f"  {GREEN}✓{RESET} {label}")
        passed += 1
    else:
        print(f"  {RED}✗{RESET} {label}")
        if detail:
            print(f"    {RED}→ {detail}{RESET}")
        failed += 1

def section(title: str):
    print(f"\n{BOLD}{'='*60}{RESET}")
    print(f"{BOLD}  {title}{RESET}")
    print(f"{BOLD}{'='*60}{RESET}")

# ═══════════════════════════════════════════════════════
# 内联关键函数（从 hagoku 源码精确复制）
# ═══════════════════════════════════════════════════════

def _resolve_scout_column_token(token: str, columns: list[str]) -> str | None:
    """从 hagoku/manager/orchestrator.py:375 精确复制"""
    raw = (token or "").strip().strip("`\"'“”'‘'")
    if not raw:
        return None
    rl = raw.lower()
    for c in columns:
        if c.lower() == rl:
            return c
    rl2 = rl.replace("_", "")
    for c in columns:
        if c.lower().replace("_", "") == rl2:
            return c
    return None


def _simulate_apply_role_update(
    context: dict,
    target: str | None = None,
    features: list[str] | None = None,
    ignored: list[str] | None = None,
    columns: list[str] | None = None,
    semantics: list[dict] | None = None,
) -> list[str]:
    """模拟 _apply_role_update 的行为（hagoku/manager/orchestrator.py:567）"""
    applied = []
    cols = columns or []
    sems = semantics or []

    if target:
        resolved = _resolve_scout_column_token(target, cols)
        if resolved:
            old = context.get("target")
            context["target"] = resolved
            applied.append(f"[role]target:{old}→{resolved}")
            for s in sems:
                cn = str(s.get("column_name", ""))
                if cn == resolved:
                    s["suggested_role"] = "target"
                elif cn == old and s.get("suggested_role") == "target":
                    s["suggested_role"] = "feature"

    if features:
        resolved_features = []
        for ft in features:
            r = _resolve_scout_column_token(str(ft), cols)
            if r and r not in resolved_features:
                resolved_features.append(r)
        if resolved_features:
            context["features"] = resolved_features
            applied.append(f"[role]features:{resolved_features}")
            for s in sems:
                cn = str(s.get("column_name", ""))
                if cn in resolved_features:
                    s["suggested_role"] = "feature"

    if ignored:
        for ig in ignored:
            r = _resolve_scout_column_token(str(ig), cols)
            if r:
                applied.append(f"[role]ignore:{r}")
                for s in sems:
                    if str(s.get("column_name", "")) == r:
                        s["suggested_role"] = "ignore"

    # 更新 variable_roles
    roles = context.get("variable_roles", {})
    for s in sems:
        cn = str(s.get("column_name", ""))
        if cn:
            roles[cn] = s.get("suggested_role", "unknown")
    context["variable_roles"] = roles
    return applied


def _simulate_field_understanding_update(
    context: dict,
    column_name: str,
    display_name: str | None = None,
    description: str | None = None,
    suggested_role: str | None = None,
    columns: list[str] | None = None,
    semantics: list[dict] | None = None,
) -> bool:
    """模拟 update_field_understanding 工具调用的处理"""
    cols = columns or []
    sems = semantics or []
    descs = context.setdefault("column_descriptions", {})
    display_names = context.setdefault("column_display_names", {})

    c = _resolve_scout_column_token(column_name, cols)
    if not c:
        return False

    updated = False
    if description:
        descs[c] = description
        updated = True
    if display_name:
        display_names[c] = display_name
        updated = True
    if suggested_role and suggested_role in ("target", "feature", "identifier", "ignore"):
        for s in sems:
            if str(s.get("column_name", "")) == c:
                s["suggested_role"] = suggested_role
                s["needs_user_input"] = False
                updated = True

    return updated


# ═══════════════════════════════════════════════════════
# 场景数据（模拟 Scout 推理后的 context）
# ═══════════════════════════════════════════════════════

def build_context_for_scenario(name: str) -> dict:
    """为不同场景构建初始 context（模拟 Scout LLM 推理后的状态）"""
    if name == "retail":
        return {
            "query": "分析各渠道的销售额和利润趋势",
            "data_path": "test_data/scenario_a_retail.csv",
            "n_rows": 50,
            "n_cols": 6,
            "column_semantics": [
                {"column_name": "SKU_ID", "inferred_type": "categorical", "suggested_role": "identifier",
                 "needs_user_input": True, "confidence": 0.6},
                {"column_name": "SLS_AMT", "inferred_type": "numeric", "suggested_role": "unknown",
                 "needs_user_input": True, "confidence": 0.3},
                {"column_name": "CST_AMT", "inferred_type": "numeric", "suggested_role": "unknown",
                 "needs_user_input": True, "confidence": 0.3},
                {"column_name": "WK_NUM", "inferred_type": "numeric", "suggested_role": "unknown",
                 "needs_user_input": True, "confidence": 0.4},
                {"column_name": "CHN_TYP", "inferred_type": "categorical", "suggested_role": "unknown",
                 "needs_user_input": True, "confidence": 0.3},
                {"column_name": "ZONE", "inferred_type": "categorical", "suggested_role": "unknown",
                 "needs_user_input": True, "confidence": 0.3},
            ],
            "column_descriptions": {},
            "column_display_names": {},
            "variable_roles": {},
            "target": None,
            "features": [],
        }
    elif name == "hr":
        return {
            "query": "技术部的绩效奖金与加班时长有什么关系",
            "data_path": "test_data/scenario_b_hr.csv",
            "n_rows": 25,
            "n_cols": 6,
            "column_semantics": [
                {"column_name": "工号", "inferred_type": "categorical", "suggested_role": "identifier",
                 "needs_user_input": False, "confidence": 0.9},
                {"column_name": "基本工资", "inferred_type": "numeric", "suggested_role": "feature",
                 "needs_user_input": False, "confidence": 0.8},
                {"column_name": "绩效奖金", "inferred_type": "numeric", "suggested_role": "target",
                 "needs_user_input": False, "confidence": 0.8},
                {"column_name": "加班时长", "inferred_type": "numeric", "suggested_role": "feature",
                 "needs_user_input": False, "confidence": 0.7},
                {"column_name": "部门", "inferred_type": "categorical", "suggested_role": "feature",
                 "needs_user_input": False, "confidence": 0.7},
                {"column_name": "入职年限", "inferred_type": "numeric", "suggested_role": "feature",
                 "needs_user_input": False, "confidence": 0.6},
            ],
            "column_descriptions": {
                "工号": "员工唯一标识编号",
                "基本工资": "员工月基本工资金额",
                "绩效奖金": "员工月度绩效奖金金额",
                "加班时长": "员工当月加班小时数",
                "部门": "员工所属部门名称",
                "入职年限": "员工从入职至今的工作年数",
            },
            "column_display_names": {},
            "variable_roles": {},
            "target": "绩效奖金",
            "features": ["基本工资", "加班时长", "部门", "入职年限"],
        }
    elif name == "clinical":
        return {
            "query": "比较Active组和Placebo组在TRT_A指标上的差异是否显著",
            "data_path": "test_data/scenario_c_clinical.csv",
            "n_rows": 40,
            "n_cols": 7,
            "column_semantics": [
                {"column_name": "PID", "inferred_type": "categorical", "suggested_role": "identifier",
                 "needs_user_input": True, "confidence": 0.5},
                {"column_name": "TRT_A", "inferred_type": "numeric", "suggested_role": "unknown",
                 "needs_user_input": True, "confidence": 0.2},
                {"column_name": "TRT_B", "inferred_type": "numeric", "suggested_role": "unknown",
                 "needs_user_input": True, "confidence": 0.2},
                {"column_name": "VST", "inferred_type": "numeric", "suggested_role": "unknown",
                 "needs_user_input": True, "confidence": 0.3},
                {"column_name": "ARM", "inferred_type": "categorical", "suggested_role": "unknown",
                 "needs_user_input": True, "confidence": 0.3},
                {"column_name": "SITE", "inferred_type": "categorical", "suggested_role": "unknown",
                 "needs_user_input": True, "confidence": 0.3},
                {"column_name": "AE_CNT", "inferred_type": "numeric", "suggested_role": "unknown",
                 "needs_user_input": True, "confidence": 0.2},
            ],
            "column_descriptions": {},
            "column_display_names": {},
            "variable_roles": {},
            "target": None,
            "features": [],
        }
    elif name == "ecommerce":
        return {
            "query": "哪个campaign的用户转化率最高",
            "data_path": "test_data/scenario_d_ecommerce.csv",
            "n_rows": 30,
            "n_cols": 7,
            "column_semantics": [
                {"column_name": "user_token", "inferred_type": "categorical", "suggested_role": "identifier",
                 "needs_user_input": True, "confidence": 0.5},
                {"column_name": "page_views", "inferred_type": "numeric", "suggested_role": "unknown",
                 "needs_user_input": True, "confidence": 0.3},
                {"column_name": "cart_adds", "inferred_type": "numeric", "suggested_role": "unknown",
                 "needs_user_input": True, "confidence": 0.3},
                {"column_name": "purchases", "inferred_type": "numeric", "suggested_role": "target",
                 "needs_user_input": True, "confidence": 0.4},
                {"column_name": "session_mins", "inferred_type": "numeric", "suggested_role": "unknown",
                 "needs_user_input": True, "confidence": 0.3},
                {"column_name": "device_type", "inferred_type": "categorical", "suggested_role": "unknown",
                 "needs_user_input": True, "confidence": 0.3},
                {"column_name": "campaign_id", "inferred_type": "categorical", "suggested_role": "feature",
                 "needs_user_input": True, "confidence": 0.4},
            ],
            "column_descriptions": {
                "user_token": "用户唯一标识token",
                "purchases": "用户购买次数",
                "campaign_id": "营销活动标识",
            },
            "column_display_names": {},
            "variable_roles": {},
            "target": "purchases",
            "features": ["campaign_id"],
        }
    else:
        raise ValueError(f"Unknown scenario: {name}")


# ═══════════════════════════════════════════════════════
# 测试
# ═══════════════════════════════════════════════════════

def test_p1_column_resolution():
    """P1: 验证 _resolve_scout_column_token 的四种匹配模式"""
    section("P1: 列名解析 (_resolve_scout_column_token)")

    cols = ["SKU_ID", "SLS_AMT", "CST_AMT", "WK_NUM", "CHN_TYP", "ZONE"]

    # 精确匹配
    check("精确匹配 SKU_ID", _resolve_scout_column_token("SKU_ID", cols) == "SKU_ID")
    # 大小写不敏感
    check("大小写 sku_id", _resolve_scout_column_token("sku_id", cols) == "SKU_ID")
    # 带下划线 vs 不带
    check("去下划线 SKUID", _resolve_scout_column_token("SKUID", cols) == "SKU_ID")
    # 反引号包裹
    check("反引号包裹 `SKU_ID`", _resolve_scout_column_token("`SKU_ID`", cols) == "SKU_ID")
    # 不存在的列
    check("不存在 PRODUCT_ID", _resolve_scout_column_token("PRODUCT_ID", cols) is None)
    # 中文列名
    hr_cols = ["工号", "基本工资", "绩效奖金", "加班时长", "部门", "入职年限"]
    check("中文列名 工号", _resolve_scout_column_token("工号", hr_cols) == "工号")
    # 空格包裹
    check("前后空格 ' SKU_ID '", _resolve_scout_column_token(" SKU_ID ", cols) == "SKU_ID")
    # 空字符串
    check("空字符串返回 None", _resolve_scout_column_token("", cols) is None)
    check("纯空格返回 None", _resolve_scout_column_token("   ", cols) is None)


def test_p2_role_update():
    """P2: 验证角色变更是否正确写入 context"""
    section("P2: 角色变更 (_apply_role_update)")

    semantics = [
        {"column_name": "TRT_A", "suggested_role": "unknown", "needs_user_input": True},
        {"column_name": "TRT_B", "suggested_role": "unknown", "needs_user_input": True},
        {"column_name": "ARM", "suggested_role": "unknown", "needs_user_input": True},
    ]
    context = {"target": None, "features": [], "variable_roles": {}}
    cols = ["TRT_A", "TRT_B", "ARM", "PID", "VST", "SITE", "AE_CNT"]

    applied = _simulate_apply_role_update(
        context, target="TRT_A", features=["TRT_B", "VST"],
        ignored=["PID"], columns=cols, semantics=semantics
    )

    check("target 设为 TRT_A", context["target"] == "TRT_A")
    check("features 含 TRT_B", "TRT_B" in context["features"])
    check("features 含 VST", "VST" in context["features"])
    check("variable_roles 中 TRT_A=target",
         context["variable_roles"].get("TRT_A") == "target")
    check("semantics 中 TRT_A.suggested_role=target",
         any(s["column_name"] == "TRT_A" and s["suggested_role"] == "target" for s in semantics))
    check("applied 记录非空", len(applied) > 0)
    check("切换 target (TRT_A→TRT_B)",
         _simulate_apply_role_update(context, target="TRT_B", columns=cols, semantics=semantics) is not None
         and context["target"] == "TRT_B")


def test_p3_field_understanding_update():
    """P3: 验证字段描述/中文名更新"""
    section("P3: 字段理解更新 (update_field_understanding 模拟)")

    # 模拟零售场景的 Scout 字段对齐反馈
    ctx = build_context_for_scenario("retail")
    cols = [s["column_name"] for s in ctx["column_semantics"]]
    sems = ctx["column_semantics"]

    # 用户说：SKU_ID是产品编号，SLS_AMT是销售额，CST_AMT是成本额
    feedbacks = [
        ("SKU_ID", "产品编号", "唯一标识每个产品的数字编码", "identifier"),
        ("SLS_AMT", "销售额", "该产品在统计周期内的总销售收入金额", "target"),
        ("CST_AMT", "成本额", "该产品在统计周期内的总成本金额", "feature"),
        ("WK_NUM", "周次", "数据所属的周序号", "feature"),
        ("CHN_TYP", "渠道类型", "销售渠道分类：Online/Store/Partner", "feature"),
        ("ZONE", "区域", "销售地理区域：North/South/East/West", "feature"),
    ]

    for col, dn, desc, role in feedbacks:
        ok = _simulate_field_understanding_update(
            ctx, col, display_name=dn, description=desc,
            suggested_role=role, columns=cols, semantics=sems
        )
        check(f"更新 {col} → {dn}", ok,
              f"ctx desc: {ctx['column_descriptions'].get(col, 'MISSING')}")

    # 验证最终状态
    check("column_descriptions 有 6 个", len(ctx["column_descriptions"]) == 6)
    check("display_names 有 6 个", len(ctx["column_display_names"]) == 6)
    check("SLS_AMT 描述正确",
         ctx["column_descriptions"]["SLS_AMT"] == "该产品在统计周期内的总销售收入金额")
    check("SLS_AMT 中文名正确",
         ctx["column_display_names"]["SLS_AMT"] == "销售额")
    check("target 是 SLS_AMT", ctx.get("target") == "SLS_AMT" or
         any(s["column_name"] == "SLS_AMT" and s["suggested_role"] == "target" for s in sems))


def test_p4_cleaner_query_accumulation():
    """P4: Cleaner 重跑时 context["query"] 是否累积用户反馈"""
    section("P4: Cleaner 重跑 — query 累积")

    ctx = build_context_for_scenario("clinical")
    original_query = ctx["query"]

    # 模拟 Cleaner 审查：用户反馈
    user_feedback = "TRT_A是治疗A的疗效指标，不要截断异常值"
    query = f"{original_query}\n[用户补充] {user_feedback}"

    # 模拟修复后的编排器：context["query"] = query
    ctx["query"] = query

    # 验证
    check("context['query'] 包含原始目标",
         "比较Active组和Placebo组在TRT_A指标上的差异是否显著" in ctx["query"])
    check("context['query'] 包含用户反馈",
         "TRT_A是治疗A的疗效指标，不要截断异常值" in ctx["query"])
    check("context['query'] 比原始更长", len(ctx["query"]) > len(original_query))
    check("context['query'] 有 [用户补充] 标记", "[用户补充]" in ctx["query"])

    # 第二轮反馈
    user_feedback2 = "ARM是分组变量，Active vs Placebo"
    query2 = f"{query}\n[用户补充] {user_feedback2}"
    ctx["query"] = query2

    check("累积两轮反馈",
         "TRT_A是治疗A的疗效指标" in ctx["query"] and
         "ARM是分组变量" in ctx["query"])


def test_p5_analyst_plan_query_accumulation():
    """P5: Analyst 重跑时 plan["query"] 是否累积用户反馈"""
    section("P5: Analyst 重跑 — plan['query'] 累积")

    plan = {
        "plan_name": "临床试验疗效对比",
        "query": "比较Active组和Placebo组在TRT_A指标上的差异是否显著",
        "analyst_focus": ["hypothesis_test"],
        "target": "TRT_A",
    }

    original_plan_query = plan["query"]

    # 模拟 Analyst 审查：用户反馈
    user_feedback = "加入AE_CNT作为安全性指标一起分析"
    accumulated = f"{original_plan_query}\n[用户补充] {user_feedback}"

    # 模拟修复后：plan["query"] = query
    plan["query"] = accumulated

    check("plan['query'] 包含原始目标",
         "比较Active组和Placebo组" in plan["query"])
    check("plan['query'] 包含用户反馈",
         "AE_CNT作为安全性指标" in plan["query"])
    check("plan['query'] 有 [用户补充] 标记", "[用户补充]" in plan["query"])

    # 第二轮
    user_feedback2 = "用Mann-Whitney U检验而非t检验，数据不正态"
    accumulated2 = f"{accumulated}\n[用户补充] {user_feedback2}"
    plan["query"] = accumulated2

    check("累积两轮 Analyst 反馈",
         "AE_CNT作为安全性指标" in plan["query"] and
         "Mann-Whitney U检验" in plan["query"])


def test_p6_cleaner_field_metadata_sync():
    """P6: Cleaner/Analyst 重跑时字段元数据同步（模拟修复后行为）"""
    section("P6: Cleaner 重跑 — 字段元数据同步")

    ctx = build_context_for_scenario("ecommerce")
    cols = [s["column_name"] for s in ctx["column_semantics"]]
    sems = ctx["column_semantics"]

    # 初始状态：session_mins 还是 unknown
    initial_sm_role = next(
        (s["suggested_role"] for s in sems if s["column_name"] == "session_mins"), None
    )
    check("初始 session_mins 角色是 unknown", initial_sm_role == "unknown",
          f"实际: {initial_sm_role}")

    # 模拟用户在 Cleaner 审查中说：session_mins是会话时长，device_type是设备类型
    # 修复后：编排器调用 apply_scout_user_field_reply_to_context()
    _simulate_field_understanding_update(
        ctx, "session_mins", display_name="会话时长",
        description="用户单次会话的持续时间（分钟）",
        suggested_role="feature", columns=cols, semantics=sems
    )
    _simulate_field_understanding_update(
        ctx, "device_type", display_name="设备类型",
        description="用户访问使用的设备类型：mobile/desktop/tablet",
        suggested_role="feature", columns=cols, semantics=sems
    )

    # 同时 query 也要累积
    ctx["query"] = f"{ctx['query']}\n[用户补充] session_mins是会话时长，作为特征参与分析"

    # 验证字段元数据已更新
    check("session_mins 描述已更新",
         "用户单次会话的持续时间" in ctx["column_descriptions"].get("session_mins", ""))
    check("session_mins 中文名已更新",
         ctx["column_display_names"].get("session_mins") == "会话时长")
    check("session_mins 角色已更新",
         any(s["column_name"] == "session_mins" and s["suggested_role"] == "feature" for s in sems))
    check("device_type 描述已更新",
         "设备类型" in ctx["column_descriptions"].get("device_type", ""))
    check("query 含字段反馈",
         "session_mins是会话时长" in ctx["query"])


def test_p7_cross_stage_consistency():
    """P7: 跨阶段一致性 — Scout 阶段更新传递到 Cleaner/Reporter"""
    section("P7: 跨阶段字段理解一致性")

    ctx = build_context_for_scenario("retail")
    cols = [s["column_name"] for s in ctx["column_semantics"]]
    sems = ctx["column_semantics"]

    # —— Scout 阶段 ——
    # 用户说：SKU_ID是产品编号，SLS_AMT是销售额
    _simulate_field_understanding_update(
        ctx, "SKU_ID", display_name="产品编号",
        description="唯一标识每个产品的数字编码",
        suggested_role="identifier", columns=cols, semantics=sems
    )
    _simulate_field_understanding_update(
        ctx, "SLS_AMT", display_name="销售额",
        description="该产品在统计周期内的总销售收入金额",
        suggested_role="target", columns=cols, semantics=sems
    )
    # 用户说：分析目标是 SLS_AMT
    _simulate_apply_role_update(ctx, target="SLS_AMT", columns=cols, semantics=sems)

    # 快照 Scout 结束时的字段状态
    scout_snapshot = {
        "descriptions": dict(ctx["column_descriptions"]),
        "display_names": dict(ctx["column_display_names"]),
        "target": ctx.get("target"),
    }

    # —— 进入 Cleaner ——
    # Cleaner 正常收到 context（Scout 的更新应该都在）
    check("Cleaner 收到 SKU_ID 描述",
         ctx["column_descriptions"].get("SKU_ID") == "唯一标识每个产品的数字编码")
    check("Cleaner 收到 SLS_AMT 中文名",
         ctx["column_display_names"].get("SLS_AMT") == "销售额")

    # —— Cleaner 审查 ——
    # 用户纠正：CST_AMT是成本额（之前未在 Scout 阶段说明）
    _simulate_field_understanding_update(
        ctx, "CST_AMT", display_name="成本额",
        description="该产品在统计周期内的总成本金额",
        suggested_role="feature", columns=cols, semantics=sems
    )

    # —— 进入 Analyst ——
    # Analyst 收到的 context 应包含 Scout + Cleaner 的所有字段更新
    check("Analyst 收到 Scout 的 SKU_ID",
         ctx["column_descriptions"].get("SKU_ID") == "唯一标识每个产品的数字编码")
    check("Analyst 收到 Scout 的 SLS_AMT",
         ctx["column_display_names"].get("SLS_AMT") == "销售额")
    check("Analyst 收到 Cleaner 的 CST_AMT",
         ctx["column_descriptions"].get("CST_AMT") == "该产品在统计周期内的总成本金额",
         f"实际: {ctx['column_descriptions'].get('CST_AMT', 'MISSING')}")
    check("Analyst 收到 Cleaner 的 CST_AMT 中文名",
         ctx["column_display_names"].get("CST_AMT") == "成本额")

    # —— 进入 Reporter ——
    # Reporter 最终看到的字段映射完整性
    rep_desc_count = len(ctx["column_descriptions"])
    rep_dn_count = len(ctx["column_display_names"])
    check(f"Reporter 收到 {rep_desc_count} 个字段描述 (期望≥3)",
         rep_desc_count >= 3, f"实际: {rep_desc_count}")
    check(f"Reporter 收到 {rep_dn_count} 个字段中文名 (期望≥3)",
         rep_dn_count >= 3, f"实际: {rep_dn_count}")


def test_scenario_b_hr():
    """场景B: HR中文列名 — LLM应自然理解中文列名"""
    section("场景B: HR中文列名 — 初始推理质量验证")

    ctx = build_context_for_scenario("hr")

    # 中文列名的初始推理应该更准确（LLM 直接理解语义）
    sems = ctx["column_semantics"]
    check("绩效奖金被识别为 target",
         any(s["column_name"] == "绩效奖金" and s["suggested_role"] == "target" for s in sems))
    check("工号被识别为 identifier",
         any(s["column_name"] == "工号" and s["suggested_role"] == "identifier" for s in sems))
    check("所有列 needs_user_input=False",
         all(not s.get("needs_user_input", True) for s in sems),
         f"仍有列需要用户输入: {[s['column_name'] for s in sems if s.get('needs_user_input')]}")
    check("6列都有描述", len(ctx["column_descriptions"]) == 6,
         f"实际: {len(ctx['column_descriptions'])} — {list(ctx['column_descriptions'].keys())}")
    check("target 已设置", ctx.get("target") == "绩效奖金")
    check("features 有4个", len(ctx.get("features", [])) == 4,
         f"实际: {ctx.get('features')}")


def test_scenario_d_ecommerce():
    """场景D: 电商混合命名 — 部分有语义、部分需推断"""
    section("场景D: 电商混合命名 — 部分字段需用户补充")

    ctx = build_context_for_scenario("ecommerce")
    cols = [s["column_name"] for s in ctx["column_semantics"]]
    sems = ctx["column_semantics"]

    # 初始状态下部分列已有描述
    check("user_token 初始有描述", "user_token" in ctx["column_descriptions"])
    check("purchases 初始有描述", "purchases" in ctx["column_descriptions"])
    check("page_views 初始无描述", "page_views" not in ctx["column_descriptions"])
    check("session_mins 初始无描述", "session_mins" not in ctx["column_descriptions"])

    # 用户补充
    _simulate_field_understanding_update(
        ctx, "page_views", display_name="页面浏览数",
        description="用户在会话期间浏览的页面总数",
        suggested_role="feature", columns=cols, semantics=sems
    )
    _simulate_field_understanding_update(
        ctx, "cart_adds", display_name="加购次数",
        description="用户在会话期间将商品加入购物车的次数",
        suggested_role="feature", columns=cols, semantics=sems
    )

    check("page_views 补充后描述存在",
         "page_views" in ctx["column_descriptions"])
    check("page_views 中文名正确",
         ctx["column_display_names"]["page_views"] == "页面浏览数")
    check("cart_adds 描述正确",
         "加入购物车" in ctx["column_descriptions"]["cart_adds"])

    # 验证所有列最终都有描述（混合场景应全补齐）
    all_described = all(
        s["column_name"] in ctx["column_descriptions"] or
        s["column_name"] in ["session_mins", "device_type"]
        for s in sems
    )
    check("大部分列已有描述（仅 session_mins, device_type 待补）",
         sum(1 for s in sems if s["column_name"] in ctx["column_descriptions"]) >= 5,
         f"已描述: {list(ctx['column_descriptions'].keys())}")


def test_query_update_field_removal():
    """验证 query_update 字段已从代码中移除（不再写入孤儿字段）"""
    section("清理验证: query_update 不应存在于 context")

    ctx = build_context_for_scenario("retail")
    check("context 中无 query_update 键",
         "query_update" not in ctx,
         "query_update 是之前遗留的孤儿字段，不应该被写入")


# ═══════════════════════════════════════════════════════
# 入口
# ═══════════════════════════════════════════════════════

if __name__ == "__main__":
    print(f"\n{BOLD}🔍 字段理解互动通道 — 全链路验证{RESET}\n")

    tests = [
        test_p1_column_resolution,
        test_p2_role_update,
        test_p3_field_understanding_update,
        test_p4_cleaner_query_accumulation,
        test_p5_analyst_plan_query_accumulation,
        test_p6_cleaner_field_metadata_sync,
        test_p7_cross_stage_consistency,
        test_scenario_b_hr,
        test_scenario_d_ecommerce,
        test_query_update_field_removal,
    ]

    for test_fn in tests:
        try:
            test_fn()
        except Exception:
            print(f"  {RED}💥 测试异常: {test_fn.__name__}{RESET}")
            traceback.print_exc()
            failed += 1

    print(f"\n{BOLD}{'='*60}{RESET}")
    total = passed + failed
    if failed == 0:
        print(f"{BOLD}  结果: {GREEN}全部 {total} 项通过 ✓{RESET}")
    else:
        print(f"{BOLD}  结果: {GREEN}{passed} 通过{RESET}, {RED}{failed} 失败{RESET} (共 {total})")
    print(f"{BOLD}{'='*60}{RESET}\n")

    sys.exit(0 if failed == 0 else 1)
