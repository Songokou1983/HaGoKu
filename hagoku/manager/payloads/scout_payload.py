"""Scout 阶段暂停载荷 + 辅助函数。CH-5 从 orchestrator.py 拆分。"""
from __future__ import annotations

import re
from typing import Any

def _md_table_cell(s: str) -> str:
    """Markdown 表单元格：去换行、转义竖线。"""
    return (s or "").replace("|", "｜").replace("\n", " ").strip()

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
    """从 column_semantics（唯一权威）取列名列表。旧 column_descriptions 不再用于补充。"""
    out: list[str] = []
    seen: set[str] = set()
    for s in context.get("column_semantics") or []:
        n = str(s.get("column_name", "")).strip()
        if n and n not in seen:
            out.append(n)
            seen.add(n)
    return out


def derive_display_names(context: dict[str, Any]) -> dict[str, str]:
    """从 column_semantics 派生 display_name 字典（只读视图，不写回 context）。

    收口规则：display_name 的权威来源是 column_semantics[*].display_name。
    旧 column_display_names 字典仍可作为初始化兜底（历史兼容），但写入只走 column_semantics。
    """
    result: dict[str, str] = {}
    # 先从旧字典取（兼容历史项目记忆加载路径）
    for col, dn in (context.get("column_display_names") or {}).items():
        if dn and str(dn).strip():
            result[str(col)] = str(dn).strip()
    # 用 column_semantics 覆盖（权威）
    for s in context.get("column_semantics") or []:
        col = str(s.get("column_name", "")).strip()
        dn = str(s.get("display_name", "") or "").strip()
        if col and dn:
            result[col] = dn
    return result


def derive_descriptions(context: dict[str, Any]) -> dict[str, str]:
    """从 column_semantics 派生 description 字典（只读视图，不写回 context）。

    收口规则：description 的权威来源是 column_semantics[*].description。
    旧 column_descriptions 字典仍可作为初始化兜底（历史兼容），但写入只走 column_semantics。
    """
    result: dict[str, str] = {}
    # 先从旧字典取（兼容历史）
    for col, desc in (context.get("column_descriptions") or {}).items():
        if desc and str(desc).strip():
            result[str(col)] = str(desc).strip()
    # 用 column_semantics 覆盖（权威）
    for s in context.get("column_semantics") or []:
        col = str(s.get("column_name", "")).strip()
        desc = str(s.get("description", "") or "").strip()
        if col and desc:
            result[col] = desc
    return result


def sync_legacy_dicts(context: dict[str, Any]) -> None:
    """将 column_semantics 的最新状态同步回旧字典（保持向后兼容）。

    调用时机：任何对 column_semantics 做完写入后调用一次，确保旧路径不脏。
    这是收口双写状态的过渡桥梁——未来旧字典彻底退场后此函数可删除。
    """
    descs: dict[str, str] = {}
    dnames: dict[str, str] = {}
    for s in context.get("column_semantics") or []:
        col = str(s.get("column_name", "")).strip()
        if not col:
            continue
        desc = str(s.get("description", "") or "").strip()
        dn = str(s.get("display_name", "") or "").strip()
        if desc:
            descs[col] = desc
        if dn:
            dnames[col] = dn
    if descs:
        context["column_descriptions"] = descs
    if dnames:
        context["column_display_names"] = dnames

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

    # 注意：description 包含匹配（子串）已删除。
    # 原因：子串匹配在多个字段描述含相同词时会产生随机结果，且与工具文档
    # "必须传精确名"的要求矛盾。LLM 传不精确名时走 _last_understanding_failure。
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

def scout_user_input_received_state(
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
        "parse_hint": (
            str(uf.get("model_reply_text", "") or "").strip()
            if isinstance(uf, dict) and uf.get("model_reply_text")
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


# ── Scout 字段更新工具 schema（Phase D 后仅测试引用）────────────────────
# 原在 scout_reply.py（已删除），迁移至此供测试验证工具契约

_SCOUT_FIELD_UPDATE_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "update_field_understanding",
            "description": (
                "更新一个字段的中文名称（display_name）和/或业务含义理解（description）。"
                "当用户通过对话说明了某个字段的含义或中文名称时，主动调用此工具来更新字段表格。"
                "如果用户的说明一次覆盖多个字段，请多次调用此工具，每次更新一个字段。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "column_name": {
                        "type": "string",
                        "description": (
                            "要更新的字段。可以使用原始列名（如 Inc1）、业务名/中文名"
                            "（如「店铺收入」），或范围记号（如「Bos1-3」表示 Bos1,Bos2,Bos3）。"
                            "代码会自动映射到真实列名并展开范围。"
                        ),
                    },
                    "display_name": {
                        "type": "string",
                        "description": (
                            "字段的中文业务名称，简短（≤8字），面向业务同事。"
                            "例如：'店铺编号'、'销售额'、'周次'。"
                            "仅当用户在对话中明确提到了中文简称／名称时才填写此项。"
                            "如果用户只是解释了含义但未给中文名，则不填此字段。"
                        ),
                    },
                    "description": {
                        "type": "string",
                        "description": (
                            "字段的业务含义理解，自然语言一句话，必须基于 display_name 扩展。"
                            "例如 display_name='店铺编号' → description='唯一标识每个门店的数字编号'。"
                            "禁止直接把用户原话中的短标签（如'产品编码'）填入此字段——"
                            "短标签属于 display_name，description 必须是对短标签的业务展开说明。"
                            "如果用户只给了一个短标签（如只说'Code叫店铺编号'），"
                            "则 description 应为该标签的自然扩展（如'用于唯一标识每个店铺的数字编码'），"
                            "不要留空，也不要与 display_name 相同。"
                        ),
                    },
                    "suggested_role": {
                        "type": "string",
                        "enum": ["target", "feature", "identifier", "ignore"],
                        "description": (
                            "该字段在分析中的建议角色。请基于用户的分析目的和对话上下文主动推断。"
                            "target: 分析要预测/解释的目标变量（因变量）。"
                            "feature: 用于解释目标的特征变量（自变量）。"
                            "identifier: 非分析维度的标识列（如编码、ID、序号）。"
                            "ignore: 明确不参与分析的字段。"
                            "如果无法确定则不填此字段。"
                        ),
                    },
                    "used_in_analysis": {
                        "type": "boolean",
                        "description": (
                            "该字段是否参与本次分析。根据字段中文名和分析目标自行判断——"
                            "纠正中文名不代表该字段要参与。\n"
                            "例如分析「收入趋势」，字段中文名含「费用」→ 必须设为false，不管有没有间接关系。"
                        ),
                    },
                },
                "required": ["column_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_field_role",
            "description": (
                "当用户指定或修正了分析涉及的核心字段角色时，调用此工具来更新分析目标。"
                "例如用户说「目标变量应该是 B 而不是 A」← 更新 target 和 features。"
                "又或者用户说「这些字段才是核心分析字段：销售额、店龄、客流量」← 更新 features。"
                "角色包括：target（目标变量，唯一）、feature（特征变量，多个）、"
                "identifier（标识列）、ignore（分析不涉及）。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "target": {
                        "type": "string",
                        "description": "目标变量（因变量/Y 变量）的字段名，唯一。如果用户未提及则不设置。",
                    },
                    "features": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "特征变量（自变量/X 变量）的字段名列表。如果用户未提及则不设置。",
                    },
                    "ignored": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "用户明确说不参与分析的字段名列表。",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "restrict_analysis_to",
            "description": (
                "当用户用「只有 X、Y、Z 参与分析」「我只关心 A 和 B」等**包含集**语义"
                "限定参与分析的字段时调用此工具。"
                "代码会自动把未列出的字段 used_in_analysis 设为 false，无需你计算补集。"
                "字段标识**必须使用精确列名**（如 Code/Inc1）或**字段表第二列中的完整中文名**"
                "（如「店铺编号」「店铺收入」），代码会做精确映射。"
                "**不要传缩写或部分匹配词**（如用户说「店铺」但你看到的字段表第二列写的是「店铺编号」→ 传「店铺编号」）。"
                "调用此工具后，系统会自动触发重推断以同步角色分配。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "included_fields": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": (
                            "用户明确希望参与分析的字段，列名或业务名均可。"
                            "代码会自动将业务名映射到真实列名并对补集做排除。"
                        ),
                    },
                    "rationale": {
                        "type": "string",
                        "description": "你为何这样理解用户原话的简要说明（可选，便于审计）。",
                    },
                },
                "required": ["included_fields"],
            },
        },
    },
]
