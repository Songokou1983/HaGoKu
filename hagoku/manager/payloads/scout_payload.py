"""Scout 阶段暂停载荷 + 辅助函数。CH-5 从 orchestrator.py 拆分。"""
from __future__ import annotations

import re
from typing import Any

def _md_table_cell(s: str) -> str:
    """Markdown 表单元格：去换行、转义竖线。"""
    return (s or "").replace("|", "｜").replace("\n", " ").strip()

def _scout_display_name_cell(
    col: str,
    desc: str,
    display_names: dict[str, Any] | None,
) -> str:
    """从含义里抽短标签（测试/遗留）；字段核对表第二列优先用 `_scout_second_column_cell`。"""
    dmap = display_names if isinstance(display_names, dict) else {}
    v = dmap.get(col)
    if isinstance(v, str) and v.strip():
        return _md_table_cell(v.strip())
    if not desc:
        return "—"
    core = desc.split("（例：", 1)[0].strip()
    short = core.split("。", 1)[0].strip() if core else ""
    if not short:
        short = col
    if len(short) > 14:
        short = short[:12] + "…"
    return _md_table_cell(short)

def _scout_chinese_display_cell(col: str, display_names: dict[str, Any] | None) -> str:
    """仅当存在 `column_display_names` 时的显式中文名；无则返回占位符「—」（供第二列组合逻辑使用）。"""
    dmap = display_names if isinstance(display_names, dict) else {}
    v = dmap.get(col)
    if isinstance(v, str) and v.strip():
        return _md_table_cell(v.strip())
    return "—"

def _scout_second_column_cell(
    col: str,
    meaning_for_short: str,
    display_names: dict[str, Any] | None,
    sem: dict[str, Any] | None = None,
) -> str:
    """字段核对表第二列：优先独立中文名；否则从含义里抽沟通简称（避免全表「—」）。"""
    explicit = _scout_chinese_display_cell(col, display_names)
    if explicit != "—":
        return explicit
    label = _scout_display_name_cell(col, meaning_for_short, display_names)
    if label != "—":
        return label
    # 兜底：含义也空则用字段语义类型作为简称
    return _scout_semantic_fallback_label(col, sem)

def _scout_semantic_fallback_label(col: str, sem: dict[str, Any] | None) -> str:
    """无 display_names 且含义为空时，回退为列名。不再硬编码类型→中文映射。"""
    return _md_table_cell(col)

def _scout_ai_meaning_cell(column_name: str, meaning_text: str, sem: dict[str, Any]) -> str:
    """字段核对表第三列：AI 对字段的含义理解；无描述时保留原文（不再硬编码 type/role 兜底文案）。"""
    d = (meaning_text or "").strip()
    if d:
        return d
    return ""

# `suggested_role` 枚举 → 前端展示中文名（全数据集通用，不针对特定字段硬编码）
_ROLE_DISPLAY_MAP: dict[str, str] = {
    "target": "目标变量",
    "feature": "特征",
    "numeric_feature": "特征",
    "categorical_feature": "特征",
    "binary_feature": "特征",
    "identifier": "标识列",
    "time_index": "时间索引",
    "ignore": "不参与",
    "text_feature": "文本特征",
    "unknown": "—",
}

def scout_field_review_pause_payload(context: dict[str, Any]) -> dict[str, Any]:
    """Scout 暂停：结构化字段表（供前端 HTML 渲染）；`message` 留空，不冒充 Agent 长文。

    律 5：display_name / description 首选 column_semantics，兜底 column_descriptions/column_display_names。
    """
    cols = context.get("column_semantics") or []
    if not cols:
        return {"message": "共 0 列 — 无法生成字段表。", "field_review": None}
    # 律 5：优先从 column_semantics 取，兜底旧 dict
    descs = context.get("column_descriptions") or {}
    display_names = context.get("column_display_names") or {}
    profiles = context.get("_column_profiles") or {}
    n_rows = context.get("n_rows", "?")
    n_c = len(cols)
    noise_prefixes = ("初步推断：", "当前理解：", "系统暂理解为：")
    rows: list[dict[str, Any]] = []
    for s in cols:
        name = str(s.get("column_name", ""))
        # 律 5：description 首选 column_semantics，兜底旧 dict
        d = str(s.get("description", "") or descs.get(name, "") or "").strip()
        for p in noise_prefixes:
            if d.startswith(p):
                d = d[len(p) :].strip()
        uncertain = bool(s.get("needs_user_input"))
        dname = _scout_second_column_cell(name, d if d else "", display_names, sem=s)
        if len(d) > 400:
            d = d[:397] + "…"
        mean = _scout_ai_meaning_cell(name, d if d else "", s)
        role = str(s.get("suggested_role", "")).strip()
        role_display = _ROLE_DISPLAY_MAP.get(role, role)

        # used_in_analysis: LLM 直接决策，代码不做角色推导
        used_in_analysis = bool(s.get("used_in_analysis")) if s.get("used_in_analysis") is not None else None
        rows.append({
            "field_name": name,
            "chinese_name": dname,
            "meaning": mean,
            "evidence": str(s.get("evidence", "") or "").strip()[:200],
            "needs_attention": uncertain,
            "suggested_role": role_display,
            "used_in_analysis": used_in_analysis,
        })

    # 分析涉及字段摘要
    target = context.get("target")
    features = context.get("features") or []
    variable_roles = context.get("variable_roles") or {}
    ignored_cols = [
        s.get("column_name") for s in cols
        if str(s.get("suggested_role", "")).strip() in ("ignore", "identifier")
    ]

    return {
        "message": "",
        "field_review": {
            "n_rows": n_rows,
            "n_cols": n_c,
            "rows": rows,
        },
        "analysis_fields_summary": {
            "target": target,
            "features": features,
            "ignored": ignored_cols,
            "roles": variable_roles,
            "prompt": "LLM 推断以上字段是本次分析的核心字段（target=目标变量，features=特征变量）。请确认是否正确；如有误请直接说明。",
        },
    }

# ── 状态机管理判断（非语义决策）────────────────────────────
# 以下正则为管道状态机转换判断：仅判断用户是「确认放行」还是「有补充内容」，
# 不做字段语义理解。若判断为「有补充」，仍走 LLM function calling 通道处理语义。
# 符合 PROJECT.md「看板状态机（确定性状态转换）」定义。
# ⚠️ 禁止在此区域添加语义判断逻辑（如根据关键词推断字段含义）。

# ==== CHANNEL ZONE: 禁止正则/if-else 语义分支 ====
# 用户意图判断统一入口：LLM 是唯一语义判断引擎。
# 代码不做任何语义判断——不匹配正则、不检测关键词、不分类意图。
# 代码只做通道：组装上下文 → 调 LLM → 解析结构化输出 → 返回结果。
# LLM 不可用或出错时必须 raise RuntimeError（铁律 2 路径 A / 铁律 7），
# 不得回退到"安全默认值"——用户必须看见 AI 没答。




def _known_scout_columns(context: dict[str, Any]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for s in context.get("column_semantics") or []:
        n = str(s.get("column_name", "")).strip()
        if n and n not in seen:
            out.append(n)
            seen.add(n)
    for k in (context.get("column_descriptions") or {}).keys():
        kn = str(k).strip()
        if kn and kn not in seen:
            out.append(kn)
            seen.add(kn)
    return out

def _resolve_scout_column_token(token: str, columns: list[str]) -> str | None:
    """将用户或 LLM 给出的字段标识解析为真实列名。

    匹配优先级：精确列名 > 忽略下划线匹配 > display_name 匹配 > description 包含。
    纯机械结构查找，不涉及语义判断。
    """
    raw = (token or "").strip().strip("`\"'“”‘’")
    if not raw:
        return None
    # 1. 精确列名（大小写不敏感）
    rl = raw.lower()
    for c in columns:
        if c.lower() == rl:
            return c
    # 2. 忽略下划线匹配
    rl2 = rl.replace("_", "")
    for c in columns:
        if c.lower().replace("_", "") == rl2:
            return c
    return None

def _resolve_scout_column_token_with_context(
    token: str,
    columns: list[str],
    display_names: dict[str, Any] | None = None,
    descriptions: dict[str, Any] | None = None,
) -> list[str]:
    """将用户或 LLM 给出的字段标识解析为真实列名列表（支持范围记号展开）。

    用于 _apply_scout_reply_with_llm 中 update_field_understanding 的 column_name
    解析 —— LLM 可能传业务名（如「店铺收入」）或范围记号（如「Bos1-3」）。

    匹配优先级：精确列名 > 范围展开 > 忽略下划线 > display_name > description。
    纯机械结构查找，不涉及语义判断。
    """
    raw = (token or "").strip().strip("`\"'“”‘’")
    if not raw:
        return []

    # 1. 精确列名（大小写不敏感）
    rl = raw.lower()
    for c in columns:
        if c.lower() == rl:
            return [c]

    # 2. 范围记号展开：「Bos1-3」→ 匹配 Bos1, Bos2, Bos3
    expanded = _expand_column_range(raw, columns)
    if expanded:
        return expanded

    # 3. 忽略下划线匹配
    rl2 = rl.replace("_", "")
    for c in columns:
        if c.lower().replace("_", "") == rl2:
            return [c]

    # 4. display_name 完全匹配
    dnames = display_names or {}
    dn_to_col = {str(v).strip(): k for k, v in dnames.items() if v}
    if token in dn_to_col:
        return [dn_to_col[token]]

    # 5. description 包含匹配
    descs = descriptions or {}
    for c in columns:
        desc = str(descs.get(c, "") or "")
        if desc and token in desc:
            return [c]

    return []

def _expand_column_range(token: str, columns: list[str]) -> list[str]:
    """展开范围记号「PrefixN-M」→ 匹配 columns 中所有 Prefix{num}（N ≤ num ≤ M）。

    纯机械字符串匹配，零语义判断。例如：
      「Bos1-3」 + columns=[Bos1,Bos2,Bos3,Bos4] → [Bos1, Bos2, Bos3]
      「Inc1-2」  + columns=[Inc1,Inc2,Inc3]      → [Inc1, Inc2]
    """
    import re
    m = re.match(r"^(.+?)(\d+)\s*[-–—]\s*(\d+)$", token)
    if not m:
        return []
    prefix = m.group(1)
    lo = int(m.group(2))
    hi = int(m.group(3))
    if lo > hi:
        lo, hi = hi, lo  # 容忍倒序如 "3-1"
    if hi - lo > 20:     # 安全上限
        return []
    result: list[str] = []
    for num in range(lo, hi + 1):
        candidate = f"{prefix}{num}"
        for c in columns:
            if c.lower() == candidate.lower():
                result.append(c)
                break
    return result

# ==== CHANNEL ZONE: 禁止正则/if-else 语义分支 ====

def _try_parse_json(text: str) -> Any:
    """尝试从文本中提取并解析 JSON 对象。先直接解析，失败后用正则提取第一个 {...}。"""
    import json
    import re

    if not text:
        return None

    # 1) 直接解析（去掉可能的 markdown 包裹）
    cleaned = text.strip()
    for prefix in ("```json", "```"):
        if cleaned.startswith(prefix):
            cleaned = cleaned[len(prefix):].strip()
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3].strip()

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    # 2) 正则提取第一个 JSON 对象
    m = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group())
        except json.JSONDecodeError:
            pass

    return None

# ── LLM 工具定义：字段理解（function calling）──────────────────
# LLM 通过调用这些工具来主动更新字段表格，而非被动输出 JSON。

def scout_user_input_received_payload(
    context: dict[str, Any],
    user_reply: str,
    applied_scout: list[str],
    interaction_revision: int,
) -> dict[str, Any]:
    """`user_input_received` 的可核验字段，供前端按事实渲染（非固定台词库）。"""
    # 提取已应用列名（格式为 "col←desc" 或纯 "col"）
    applied_cols = {
        a.split("←", 1)[0].strip()
        for a in (applied_scout or [])
        if a and a.strip()
    }
    pending = [
        str(s.get("column_name", "")).strip()
        for s in (context.get("column_semantics") or [])
        if s.get("needs_user_input")
        and str(s.get("column_name", "")).strip()
        and str(s.get("column_name", "")).strip() not in applied_cols
    ]
    raw = (user_reply or "").strip()
    parse_failed = (
        raw
        and len(applied_scout) == 0
    )
    uf = context.get("_last_understanding_failure")
    return {
        "reply": user_reply,
        "applied_field_updates": list(applied_scout),
        "llm_reply": context.get("_last_llm_reply", ""),
        "interaction_revision": interaction_revision,
        "parse_applied_count": len(applied_scout),
        "parse_failed": parse_failed,
        "columns_still_needing_input": pending,
        "understanding_failure": (
            {"raw_text": uf.get("raw_text", ""), "stage": uf.get("stage", "")}
            if isinstance(uf, dict)
            else None
        ),
    }

def _scout_description_is_meaningful_for_user(col_name: str, desc: str) -> bool:
    """检查字段描述是否向用户展示了超出类型回显的信息（结构性检查）。

    委托给 scout/agent.py 的 _description_is_user_facing_meaningful。
    纯字符串形状匹配，不涉及语义判断。
    """
    from hagoku.agents.agent import _description_is_user_facing_meaningful

    return _description_is_user_facing_meaningful(col_name, desc)
