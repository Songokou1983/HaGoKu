"""HaGoKu Studio Manager — 编排器：LLM 决策驱动，代码构建通道"""

from __future__ import annotations

import re
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

from ..agents._scribe.agent import ScribeAgent
from ..agents.analyst import AnalystAgent
from ..agents.cleaner import CleanerAgent
from ..agents.reporter import ReporterAgent
from ..agents.scout import ScoutAgent
from ..config import HaGoKuConfig
from ..guardrails.statistical import StatisticalGuardrails
from ..llm.client import create_deep_client, create_quick_client, create_raw_client, create_structured_llm_client
from ..observability.display import TerminalDisplay
from ..observability.event_bus import EventBus
from ..observability.events import EventType
from ..storage.database import HaGoKuDB
from ..storage.memory import MemoryManager
from ..storage.output import OutputManager
from ..storage.project_manager import ProjectManager
from ..tools.data_io import save_data

# ── 规则引擎 ──────────────────────────────────────────────────


# WebSocket「重置 / 取消」暂停时使用的哨兵（用户正常回复不会使用此串）
HAGOKU_CANCEL_PAUSE_TOKEN = "__HAGOKU_CANCEL__"

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


def _scout_description_is_meaningful_for_user(col: str, desc: str) -> bool:
    """判断字段描述是否对用户有业务含义（非「列名（统计类型）」占位符）。

    委托给 Scout agent 的同名逻辑，保持语义一致性。
    """
    from ..agents.scout.agent import _description_is_user_facing_meaningful
    return _description_is_user_facing_meaningful(col, desc)


def _scout_ai_meaning_cell(column_name: str, meaning_text: str, sem: dict[str, Any]) -> str:
    """字段核对表第三列：AI 对字段的含义理解；无描述时保留原文（不再硬编码 type/role 兜底文案）。"""
    d = (meaning_text or "").strip()
    if d:
        return d
    return ""


def scout_field_review_pause_payload(context: dict[str, Any]) -> dict[str, Any]:
    """Scout 暂停：结构化字段表（供前端 HTML 渲染）；`message` 留空，不冒充 Agent 长文。"""
    cols = context.get("column_semantics") or []
    if not cols:
        return {"message": "共 0 列 — 无法生成字段表。", "field_review": None}
    descs = context.get("column_descriptions") or {}
    display_names = context.get("column_display_names") or {}
    profiles = context.get("_column_profiles") or {}
    n_rows = context.get("n_rows", "?")
    n_c = len(cols)
    noise_prefixes = ("初步推断：", "当前理解：", "系统暂理解为：")
    rows: list[dict[str, Any]] = []
    for s in cols:
        name = str(s.get("column_name", ""))
        d = str(descs.get(name, "") or "").strip()
        for p in noise_prefixes:
            if d.startswith(p):
                d = d[len(p) :].strip()
        uncertain = bool(s.get("needs_user_input"))
        dname = _scout_second_column_cell(name, d if d else "", display_names, sem=s)
        if len(d) > 400:
            d = d[:397] + "…"
        mean = _scout_ai_meaning_cell(name, d if d else "", s)
        role = str(s.get("suggested_role", "")).strip() or "feature"

        rows.append({
            "field_name": name,
            "chinese_name": dname,
            "meaning": mean,
            "needs_attention": uncertain,
            "suggested_role": role,
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

# 用户仅表示「确认」、无字段纠错时，不写 column_descriptions、不污染 query 补充段
_SCOUT_PURE_CONFIRM_RE = re.compile(
    r"^(确认(?:无误|进清洗|继续)?|可以了|对齐了|就这样|没问题了|好的|是|没问题|对的|正确|已通过|妥当|行|"
    r"pass|ok|okay|yes|y|thanks|thx)[\s!！。,\-\.]*$",
    re.I,
)


# ==== CHANNEL ZONE: 禁止正则/if-else 语义分支 ====
def _scout_reply_is_pure_confirm(user_reply: str) -> bool:
    t = (user_reply or "").strip()
    if not t:
        return False
    return bool(_SCOUT_PURE_CONFIRM_RE.match(t))


# Cleaner / Analyst 多轮暂停：仅当用户显式「放行」才结束子循环（与 Web「确认继续」按钮一致）
_STAGE_CLEANER_PROCEED_RE = re.compile(
    r"^(确认(?:继续|无误)?|好的|是|没问题|对的|正确|通过|ok|okay|yes)[\s!！。,\-\.]*$",
    re.I,
)


def _cleaner_reply_accepts_proceed(user_reply: str) -> bool:
    t = (user_reply or "").strip()
    if not t:
        return False
    return bool(_STAGE_CLEANER_PROCEED_RE.match(t))


_ANALYST_EXACT_PROCEED_PHRASES = frozenset({
    "已核对上表中的 p 值、效应量与置信区间，同意进入报告阶段",
})

_STAGE_ANALYST_PROCEED_RE = re.compile(
    r"^(确认(?:继续|无误)?|生成报告|可以生成|同意进入报告|好的|是|没问题|对的|正确|通过|ok|okay|yes)[\s!！。,\-\.]*$",
    re.I,
)


def _analyst_reply_accepts_proceed(user_reply: str) -> bool:
    t = (user_reply or "").strip()
    if not t:
        return False
    if t in _ANALYST_EXACT_PROCEED_PHRASES:
        return True
    return bool(_STAGE_ANALYST_PROCEED_RE.match(t))


# ==== CHANNEL ZONE: 禁止正则/if-else 语义分支 ====
def _is_scout_aligned(context: dict[str, Any], user_reply: str) -> bool:
    """判断 Scout 字段理解是否已对齐：纯确认  OR  所有字段 needs_user_input=False。"""
    if _scout_reply_is_pure_confirm(user_reply):
        return True
    if not any(s.get("needs_user_input") for s in context.get("column_semantics", [])):
        return True
    return False


def analysis_purpose_pause_payload(context: dict[str, Any]) -> dict[str, Any]:
    """分析目的确认暂停：展示 LLM 推断的 target/features/roles，供用户确认或修正。"""
    ap = context.get("analysis_purpose") or _build_analysis_purpose_static(context)
    target = ap.get("target")
    features = ap.get("features") or []
    roles = ap.get("variable_roles") or {}
    cols = context.get("column_semantics") or []

    # 构建分析字段表格行
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    # 先 target
    if target:
        seen.add(target)
        rows.append({"column_name": target, "role": "target", "role_label": "目标变量（因变量）"})
    # 再 features
    for f in features:
        if f not in seen:
            seen.add(f)
            rows.append({"column_name": f, "role": "feature", "role_label": "特征变量（自变量）"})
    # 其余列
    for s in cols:
        name = str(s.get("column_name", ""))
        if name and name not in seen:
            seen.add(name)
            role = str(s.get("suggested_role", "")).strip()
            if role in ("ignore", "identifier"):
                rows.append({"column_name": name, "role": role, "role_label": "不参与分析"})
            else:
                rows.append({"column_name": name, "role": "other", "role_label": "其他"})

    prompt_lines = [
        "以上是 LLM 推断的本次分析涉及的核心字段。",
        "请核对目标变量和特征变量是否正确；",
        "如有调整请直接说明（例如「目标变量应该是 B，特征变量去掉 C」）。",
        "确认无误后点击「确认继续」进入数据清洗。",
    ]

    return {
        "message": "",
        "analysis_purpose_review": {
            "rows": rows,
            "prompt": "\n".join(prompt_lines),
        },
    }


def _build_analysis_purpose_static(context: dict[str, Any]) -> dict[str, Any]:
    """模块级静态版本的 _build_analysis_purpose（供模块级函数调用）。"""
    target = context.get("target")
    features = context.get("features") or []
    variable_roles = context.get("variable_roles") or {}
    summary_parts: list[str] = []
    if target:
        summary_parts.append(f"目标变量（因变量）：{target}")
    if features:
        summary_parts.append(f"特征变量（自变量）：{', '.join(str(f) for f in features)}")
    if variable_roles:
        role_lines = [f"  {k}: {v}" for k, v in sorted(variable_roles.items())]
        summary_parts.append(f"变量角色：\n{chr(10).join(role_lines)}")
    return {
        "target": target,
        "features": features,
        "variable_roles": variable_roles,
        "summary": "\n".join(summary_parts) or "（未指定分析字段角色）",
    }


def gate_cleaning_pause_payload(context: dict[str, Any] | None = None) -> dict[str, Any]:
    """跨阶段闸门：字段对齐后、进入清洗前（附带最终 field_review 供前端展示）。"""
    payload: dict[str, Any] = {
        "message": "",
        "gate": {
            "phase": "cleaning",
            "prompt": "",
        },
    }
    if context:
        fr = scout_field_review_pause_payload(context)
        payload["field_review"] = fr.get("field_review")
        payload["analysis_fields_summary"] = fr.get("analysis_fields_summary")
    return payload


# 闸门回复判定：显式纯确认 → 进下一阶段；空字串不视为确认；非确认 → 回 FieldReviewLoop
_GATE_SUPPLEMENT_RE = re.compile(
    r"补充|还有|改|不对|不对的|纠正|修正|更正|重新|再想想|再看看",
    re.I,
)


# ==== CHANNEL ZONE: 禁止正则/if-else 语义分支 ====
def _is_gate_confirm(user_reply: str) -> bool:
    """闸门回复是否为「确认进入下一阶段」而非「还有补充」。"""
    t = (user_reply or "").strip()
    if not t:
        return False
    if _scout_reply_is_pure_confirm(t):
        return True
    # 含「补充 / 还有 / 改」等词 → 拒绝闸门，回 FieldReviewLoop
    if _GATE_SUPPLEMENT_RE.search(t):
        return False
    return True


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
    raw = (token or "").strip().strip("`\"'“”‘’")
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




# ==== CHANNEL ZONE: 禁止正则/if-else 语义分支 ====
def apply_scout_user_field_reply_to_context(
    context: dict[str, Any],
    user_reply: str,
    *,
    llm_client: Any = None,
    llm_model: str = "",
) -> list[str]:
    """
    将用户在 Scout 字段核对暂停点的说明写入 context（column_descriptions、needs_user_input）。

    **核心设计：LLM 作为字段理解的唯一引擎。** 用户的自然语言说明（如"Code 代表店铺编号"）
    原样转发给 LLM 理解语义，LLM 主动识别目标字段、区分含义与中文名称。
    代码只负责把 LLM 返回的 JSON 机械写入 context —— 不解析、不判断、不兜底。

    若 LLM 不可用或解析失败，保留原 context 不变，返回 []，不启用代码硬解析。

    返回简短人类可读记录（如 ``Code←店铺编号``），供事件或日志；无写入则返回 []。
    """
    raw = (user_reply or "").strip()
    if not raw or _scout_reply_is_pure_confirm(raw):
        return []

    columns = _known_scout_columns(context)
    if not columns:
        return []

    # ── LLM 唯一引擎：将用户自然语言说明交给 LLM 理解 ──────────
    if llm_client is not None and llm_model:
        return _apply_scout_reply_with_llm(context, raw, columns, llm_client, llm_model)

    # ── LLM 不可用（client/model 为空）：保留原 context，无写入 ──
    import logging
    _log = logging.getLogger("hagoku.orchestrator")
    _log.warning("字段理解跳过：LLM client/model 不可用，保留原字段信息不变")

    return []


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
                        "description": "要更新的字段名，必须是当前字段表格中存在的字段。",
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
                            "字段的业务含义理解，自然语言一句话。"
                            "例如：'代表每个门店的唯一数字编号'、'该周期的总收入金额（万元）'。"
                            "如果用户给出的说明更适合放在 display_name（简短中文名），"
                            "则可将此字段设为相同或留空。"
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
]


# ==== CHANNEL ZONE: 禁止正则/if-else 语义分支 ====
def _apply_role_update(
    context: dict[str, Any],
    tool_calls: list[Any],
    columns: list[str],
    applied: list[str],
    semantics: list[dict[str, Any]],
) -> None:
    """处理 LLM 的 update_field_role 工具调用，更新 context 中的 target / features / variable_roles。

    将角色变更同步回 column_semantics 的 suggested_role 字段，
    并在 applied 列表中记录以便日志和持久化。
    """
    import json as _json

    for tc in tool_calls:
        if hasattr(tc, "function"):
            func_name = tc.function.name
            func_args_str = tc.function.arguments
        elif isinstance(tc, dict):
            f = tc.get("function", {})
            func_name = f.get("name", "")
            func_args_str = f.get("arguments", "{}")
        else:
            continue

        if func_name != "update_field_role":
            continue

        try:
            args = _json.loads(func_args_str) if isinstance(func_args_str, str) else func_args_str
        except (_json.JSONDecodeError, TypeError):
            continue

        new_target = str(args.get("target", "") or "").strip()
        new_features = list(args.get("features") or [])
        new_ignored = list(args.get("ignored") or [])

        # 解析字段名并更新
        if new_target:
            resolved_target = _resolve_scout_column_token(new_target, columns)
            if resolved_target:
                old_target = context.get("target")
                context["target"] = resolved_target
                applied.append(f"[role]target:{old_target}→{resolved_target}")
                # 同步 suggested_role
                for s in semantics:
                    cname = str(s.get("column_name", ""))
                    if cname == resolved_target:
                        s["suggested_role"] = "target"
                    elif cname == old_target and s.get("suggested_role") == "target":
                        s["suggested_role"] = "feature"

        if new_features:
            resolved_features: list[str] = []
            for ft in new_features:
                r = _resolve_scout_column_token(str(ft), columns)
                if r and r not in resolved_features:
                    resolved_features.append(r)
            if resolved_features:
                context["features"] = resolved_features
                applied.append(f"[role]features:{resolved_features}")
                # 同步 suggested_role
                for s in semantics:
                    cname = str(s.get("column_name", ""))
                    if cname in resolved_features:
                        s["suggested_role"] = "feature"

        if new_ignored:
            for ig in new_ignored:
                r = _resolve_scout_column_token(str(ig), columns)
                if r:
                    applied.append(f"[role]ignore:{r}")
                    for s in semantics:
                        if str(s.get("column_name", "")) == r:
                            s["suggested_role"] = "ignore"

        # 更新 variable_roles 映射
        roles: dict[str, str] = context.get("variable_roles", {}) or {}
        if new_target:
            roles["target"] = new_target
        context["variable_roles"] = roles


def _apply_scout_reply_with_llm(
    context: dict[str, Any],
    raw: str,
    columns: list[str],
    llm_client: Any,
    llm_model: str,
) -> list[str]:
    """
    LLM 作为字段理解的唯一引擎，通过 function calling 主动更新字段信息。

    **核心设计**：
    - 代码将当前「字段表格」完整状态传给 LLM
    - LLM 通过调用 `update_field_understanding` 工具来主动更新字段
    - 代码只负责机械执行 LLM 的工具调用结果——不解析、不判断、不兜底
    - 若模型不支持 tool calling（返回空 tool_calls），降级为 JSON 解析模式

    示例：
      用户："Code 代表店铺编号"
        → LLM 调用 update_field_understanding(column_name="Code", display_name="店铺编号", description="代表店铺编号")
      用户："Period的中文名是周次"
        → LLM 调用 update_field_understanding(column_name="Period", display_name="周次")
    """
    if not columns or not raw:
        return []

    descs: dict[str, Any] = context.setdefault("column_descriptions", {})
    display_names: dict[str, Any] = context.setdefault("column_display_names", {})
    semantics = context.get("column_semantics") or []
    applied: list[str] = []
    seen_col: set[str] = set()

    # ── 构建当前字段表格状态，供 LLM 理解已有信息 ─────────────
    field_state_lines: list[str] = []
    for sem in semantics:
        col = str(sem.get("column_name", ""))
        if not col:
            continue
        current_desc = str(descs.get(col, "") or "").strip()
        current_dn = str(display_names.get(col, "") or "").strip()
        parts = [f"  - {col}"]
        if current_dn:
            parts.append(f"中文名: {current_dn}")
        if current_desc:
            parts.append(f"含义: {current_desc}")
        if not current_dn and not current_desc:
            parts.append("(尚未理解)")
        field_state_lines.append(" | ".join(parts))

    field_state = "\n".join(field_state_lines) if field_state_lines else "（尚无任何字段）"

    system_msg = (
        "你是一个数据分析助手，正在帮用户理解一个数据表格的字段含义。\n"
        "用户会通过对话向你说明某些字段的含义，你需要主动识别、理解并更新字段表格。\n\n"
        "当前字段表格状态：\n"
        f"{field_state}\n\n"
        "规则：\n"
        "- 当用户说明了某个字段的含义时，调用 `update_field_understanding` 工具来更新该字段。\n"
        "- 如果用户说了中文名称（如'Code 叫店铺编号'），请同时更新 display_name 和 description。\n"
        "- 如果用户只解释了含义（如'Code 代表店铺的唯一编号'），只更新 description。\n"
        "- 如果用户的说明同时覆盖多个字段，请多次调用工具，每次更新一个字段。\n"
        "- 不要调用工具更新未被用户提及的字段。\n"
        "- 如果用户的输入不涉及字段含义（如纯确认'好的/确认'、闲聊），不要调用任何工具。"
    )

    user_msg = f"用户说：{raw}"

    messages: list[dict[str, str]] = [
        {"role": "system", "content": system_msg},
        {"role": "user", "content": user_msg},
    ]

    _raw_text: str = ""
    try:
        resp = llm_client.chat.completions.create(
            model=llm_model,
            messages=messages,
            temperature=0.0,
            max_tokens=512,
            tools=_SCOUT_FIELD_UPDATE_TOOLS,
            tool_choice="auto",
        )

        msg = resp.choices[0].message
        tool_calls = getattr(msg, "tool_calls", None)
        _raw_text = (msg.content or "").strip()

        # ── 处理 LLM 的工具调用（主路径）──────────────────────
        if tool_calls and isinstance(tool_calls, list) and len(tool_calls) > 0:
            import json as _json

            for tc in tool_calls:
                # 兼容 OpenAI SDK 的 ToolCall 对象和 dict
                if hasattr(tc, "function"):
                    func_name = tc.function.name
                    func_args_str = tc.function.arguments
                elif isinstance(tc, dict):
                    f = tc.get("function", {})
                    func_name = f.get("name", "")
                    func_args_str = f.get("arguments", "{}")
                else:
                    continue

                if func_name == "update_field_role":
                    _apply_role_update(context, tool_calls, columns, applied, semantics)
                    continue

                if func_name != "update_field_understanding":
                    continue

                try:
                    args = _json.loads(func_args_str) if isinstance(func_args_str, str) else func_args_str
                except (_json.JSONDecodeError, TypeError):
                    continue

                col_t = str(args.get("column_name", "")).strip()
                c = _resolve_scout_column_token(col_t, columns)
                if not c or c in seen_col:
                    continue
                seen_col.add(c)

                d_raw = str(args.get("description", "") or "").strip()
                dn_raw = str(args.get("display_name", "") or "").strip()

                updated_something = False
                if d_raw:
                    descs[c] = d_raw
                    applied.append(f"{c}←{d_raw}")
                    updated_something = True
                if dn_raw:
                    display_names[c] = dn_raw
                    applied.append(f"{c}:[display]←{dn_raw}")
                    updated_something = True
                if updated_something:
                    for s in semantics:
                        if str(s.get("column_name", "")) == c:
                            s["needs_user_input"] = False

            return applied

        # ── 无 tool_calls：尝试 JSON fallback（兼容旧模型）─────
        if _raw_text:
            parsed = _try_parse_json(_raw_text)
            if isinstance(parsed, dict):
                import json as _json

                for col_t, val in parsed.items():
                    c = _resolve_scout_column_token(col_t, columns)
                    if not c or c in seen_col:
                        continue
                    seen_col.add(c)

                    if isinstance(val, str):
                        if val.strip():
                            descs[c] = val.strip()
                            applied.append(f"{c}←{val.strip()}")
                            for s in semantics:
                                if str(s.get("column_name", "")) == c:
                                    s["needs_user_input"] = False
                    elif isinstance(val, dict):
                        d = str(val.get("description", "") or "").strip()
                        dn = str(val.get("display_name", "") or "").strip()
                        if d:
                            descs[c] = d
                            applied.append(f"{c}←{d}")
                        if dn:
                            display_names[c] = dn
                            applied.append(f"{c}:[display]←{dn}")
                        if d or dn:
                            for s in semantics:
                                if str(s.get("column_name", "")) == c:
                                    s["needs_user_input"] = False
                return applied

        return []

    except Exception as e:
        # LLM 失败 → 记录日志，返回 []，不阻断流程
        import traceback
        import logging

        _log = logging.getLogger("hagoku.orchestrator")
        _log.warning(
            "LLM 字段理解失败（保留原字段信息不变）：%s | 原始响应: %s",
            e,
            repr(_raw_text[:200] if _raw_text else "(无响应)"),
        )
        _log.debug(traceback.format_exc())
        return []


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
        and not _scout_reply_is_pure_confirm(raw)
        and len(applied_scout) == 0
    )
    return {
        "reply": user_reply,
        "applied_field_updates": list(applied_scout),
        "interaction_revision": interaction_revision,
        "pure_confirm": _scout_reply_is_pure_confirm(user_reply),
        "parse_applied_count": len(applied_scout),
        "parse_failed": parse_failed,
        "columns_still_needing_input": pending,
    }


def _normalize_cleaning_operation(op: Any) -> dict[str, Any]:
    """CleaningOp / dict 统一为 dict，供 prompt 与 cleaning_review 载荷使用。"""
    if op is None:
        return {}
    if isinstance(op, dict):
        return op
    if hasattr(op, "to_dict") and callable(getattr(op, "to_dict")):
        try:
            return dict(op.to_dict())  # type: ignore[arg-type]
        except Exception:
            pass
    col = getattr(op, "column", "") or ""
    strat = getattr(op, "strategy", "")
    if hasattr(strat, "value"):
        strat = strat.value
    reason = getattr(op, "reason", "") or ""
    ra = int(getattr(op, "rows_affected", 0) or 0)
    return {"column": str(col), "strategy": str(strat), "reason": str(reason), "rows_affected": ra}


def _cleaning_quality_display(
    report: Any,
    *,
    impact_rate: float,
    t_orig: int,
    t_after: int,
    fallback_label: str,
) -> str:
    """CleaningReport 无标准 data_quality 字段；避免把用户晾在 unknown 上。"""
    raw = (fallback_label or "").strip()
    if raw and raw.lower() != "unknown":
        return raw
    if t_orig <= 0:
        return "—"
    if t_after < t_orig:
        return "有删行"
    if impact_rate > 0.12:
        return "高影响（删行计）"
    if impact_rate > 0.04:
        return "中影响（删行计）"
    br = str(getattr(report, "bias_risk", "") or "").lower()
    if br in ("high", "medium"):
        return f"偏差风险 {br}"
    return "—"


def cleaning_review_pause_payload(
    cleaning_report: Any,
    *,
    data_quality: str,
    impact_rate: float,  # 与编排层传入一致；当前以报告内 impact_rate 为准
) -> dict[str, Any]:
    """Cleaner 暂停：结构化清洗结果表；`message` 留空，避免编排层写死「Agent 台词」。"""
    if cleaning_report is None:
        return {
            "message": "",
            "cleaning_review": {
                "data_quality": "—",
                "impact_rate": float(impact_rate or 0.0),
                "total_rows_original": 0,
                "total_rows_after": 0,
                "rows_removed": 0,
                "bias_risk": "unknown",
                "n_ops": 0,
                "warnings": [],
                "rows": [],
            },
        }
    ops_raw: list[Any] = list(getattr(cleaning_report, "operations", None) or [])
    rows: list[dict[str, Any]] = []
    for op in ops_raw[:120]:
        d = _normalize_cleaning_operation(op)
        col = str(d.get("column", "") or "")
        strat = str(d.get("strategy", "") or "")
        reason = str(d.get("reason", "") or "")
        if len(reason) > 400:
            reason = reason[:397] + "…"
        rows.append({
            "column": col,
            "strategy": strat,
            "reason": reason,
            "rows_affected": int(d.get("rows_affected", 0) or 0),
        })
    t_orig = int(getattr(cleaning_report, "total_rows_original", 0) or 0)
    t_after = int(getattr(cleaning_report, "total_rows_after", 0) or 0)
    bias = str(getattr(cleaning_report, "bias_risk", "unknown") or "unknown")
    warnings = getattr(cleaning_report, "warnings", None) or []
    if not isinstance(warnings, list):
        warnings = []
    warn_strs = [str(w) for w in warnings[:8] if str(w).strip()]
    rep_impact = float(getattr(cleaning_report, "impact_rate", 0) or float(impact_rate or 0.0))
    rows_removed = max(0, t_orig - t_after)
    dq = _cleaning_quality_display(
        cleaning_report,
        impact_rate=rep_impact,
        t_orig=t_orig,
        t_after=t_after,
        fallback_label=str(data_quality or ""),
    )
    return {
        "message": "",
        "cleaning_review": {
            "data_quality": dq,
            "impact_rate": rep_impact,
            "total_rows_original": t_orig,
            "total_rows_after": t_after,
            "rows_removed": rows_removed,
            "bias_risk": bias,
            "n_ops": len(ops_raw),
            "warnings": warn_strs,
            "rows": rows,
        },
    }


def _fmt_pause_p_value(v: Any) -> str:
    if v is None:
        return "—"
    try:
        fv = float(v)
    except (TypeError, ValueError):
        s = str(v).strip()
        return s[:20] + ("…" if len(s) > 20 else "") if s else "—"
    if fv < 0.0001:
        return "<0.0001"
    if fv < 0.001:
        return "<0.001"
    return f"{fv:.4g}"


def _fmt_pause_effect_summary(effect_type: str, effect_size: Any) -> str:
    et = (effect_type or "").strip()
    if effect_size is None:
        return et if et else "—"
    try:
        ev = float(effect_size)
    except (TypeError, ValueError):
        return f"{et} {effect_size}".strip() if et else str(effect_size)[:32]
    frag = f"{ev:.4g}"
    if et:
        return f"{et}={frag}"
    return frag


def _fmt_pause_ci(ci: Any, max_len: int = 56) -> str:
    if ci is None:
        return "—"
    s = str(ci).strip()
    if not s:
        return "—"
    if len(s) > max_len:
        return s[: max_len - 1] + "…"
    return s


def analyst_review_pause_payload(findings: list[Any]) -> dict[str, Any]:
    """Analyst 暂停：结构化统计结果摘要表；`message` 留空，避免用 LLM 冒充「Agent 对话」。"""
    rows_out: list[dict[str, Any]] = []
    sig_n = 0
    seq = findings if isinstance(findings, list) else []
    for item in seq[:80]:
        d: dict[str, Any]
        if isinstance(item, dict):
            d = item
        elif hasattr(item, "to_dict") and callable(getattr(item, "to_dict")):
            try:
                raw = item.to_dict()  # type: ignore[union-attr]
                d = dict(raw) if isinstance(raw, dict) else {}
            except Exception:
                d = {}
        else:
            d = {}
        sig = str(d.get("significance") or "")
        if sig == "significant":
            sig_n += 1
        rid = str(d.get("result_id") or "")
        q = str(d.get("question") or "")
        if len(q) > 320:
            q = q[:317] + "…"
        at = str(d.get("analysis_type") or "")
        plain = str(d.get("conclusion_plain") or "")
        if len(plain) > 240:
            plain = plain[:237] + "…"
        rows_out.append({
            "result_id": rid,
            "analysis_type": at,
            "question": q,
            "significance": sig,
            "conclusion_plain": plain,
            "p_value": _fmt_pause_p_value(d.get("p_value")),
            "effect_summary": _fmt_pause_effect_summary(str(d.get("effect_type") or ""), d.get("effect_size")),
            "confidence_interval": _fmt_pause_ci(d.get("confidence_interval")),
        })
    n_tot = len(seq)
    return {
        "message": "",
        "analyst_review": {
            "n_findings": n_tot,
            "n_significant": sig_n,
            "rows": rows_out,
        },
    }


# ── 编排器 ────────────────────────────────────────────────────


class Orchestrator:
    """HaGoKu Studio 编排器：规则+AI 双驱动，协调四个 Agent"""

    def __init__(self, config: HaGoKuConfig | None = None) -> None:
        self.config = config or HaGoKuConfig.load()
        self.config.ensure_work_dir()

        # 核心组件
        self.event_bus = EventBus()
        self.db = HaGoKuDB.get_instance(self.config.work_dir / "hagoku.db")
        self.display = TerminalDisplay(verbosity="normal")
        self.output_mgr: OutputManager | None = None  # 按项目初始化
        self.memory: MemoryManager | None = None  # 按项目初始化
        self.project_mgr = ProjectManager(self.config.output.project_dir)  # 全局项目管理器

        # 订阅显示
        self.event_bus.subscribe(self.display)

        # 护栏
        self.guardrails = StatisticalGuardrails()

        # LLM 客户端（懒初始化，pure_rule 模式永远不会触发）
        self._llm_client: Any | None = None
        self._llm_deep: Any | None = None  # 深度推理客户端（懒初始化）
        self._llm_quick: Any | None = None  # 快速客户端（懒初始化，instructor 包装）
        self._llm_quick_raw: Any | None = None  # 快速原始客户端（非 instructor 包装）

        # 设置模块级配置
        from ..tools.analysis import set_analysis_config
        from ..tools.cleaning import set_cleaning_config
        set_analysis_config(self.config.analysis)
        set_cleaning_config(self.config.cleaning)

        # 交互式暂停机制（分析线程用 Event 等待用户回复）
        self._pause_event: threading.Event = threading.Event()
        self._user_response: str | None = None
        self._is_paused: bool = False
        # 用户请求中止本轮分析（WebSocket cancel_analysis）
        self._cancel_lock = threading.Lock()
        self._cancel_requested_flag = False

    @property
    def llm_deep(self) -> Any:
        """深度推理客户端（懒初始化）"""
        if self._llm_deep is None:
            self._llm_deep = create_deep_client(self.config)
        return self._llm_deep

    @property
    def llm_quick(self) -> Any:
        """快速客户端（懒初始化，instructor 包装，用于结构化输出）"""
        if self._llm_quick is None:
            self._llm_quick = create_quick_client(self.config)
        return self._llm_quick

    @property
    def llm_quick_raw(self) -> Any:
        """快速原始客户端（懒初始化，非 instructor 包装，用于 _apply_scout_reply_with_llm 等 JSON-only 调用）"""
        if self._llm_quick_raw is None:
            self._llm_quick_raw = create_raw_client(self.config)
        return self._llm_quick_raw

    # ── 交互式暂停 / 恢复 ─────────────────────────────────────

    def unblock(self, user_response: str) -> None:
        """前端用户发送回复后，ws_handler 调用此方法解除线程阻塞。"""
        self._user_response = user_response
        self._is_paused = False
        self._pause_event.set()

    def _pause_and_wait(self, agent: str, payload: str | dict[str, Any], timeout: float = 300.0) -> str:
        """
        发射 user_input_requested 事件，然后阻塞当前线程直到用户回复。
        payload 可为 str（仅 message）或 dict（可含 message、field_review 等，由前端渲染）。
        timeout: 秒，超时后自动用空字符串恢复（防止永久阻塞）。
        """
        self._pause_event.clear()
        self._user_response = None
        self._is_paused = True
        if isinstance(payload, str):
            data: dict[str, Any] = {"message": payload, "agent": agent}
        else:
            data = dict(payload)
            data["agent"] = agent
            if "message" not in data:
                data["message"] = ""
        self.event_bus.emit(EventType.USER_INPUT_REQUESTED, agent, data)
        self._pause_event.wait(timeout=timeout)
        self._is_paused = False
        return self._user_response or ""

    def request_cancel(self) -> None:
        """前端「重置分析」：在暂停点打断；非暂停时长任务结束后在检查点退出。"""
        with self._cancel_lock:
            self._cancel_requested_flag = True
        if self._is_paused:
            self.unblock(HAGOKU_CANCEL_PAUSE_TOKEN)

    def _is_cancel_requested(self) -> bool:
        with self._cancel_lock:
            return self._cancel_requested_flag

    def _finish_run_cancelled(
        self,
        run_id: str,
        project_name: str,
        run_start: datetime,
        run_dir: Path,
    ) -> dict[str, Any]:
        duration_ms = int((datetime.now() - run_start).total_seconds() * 1000)
        now = datetime.now().isoformat()
        self.db.update_run(
            run_id,
            status="cancelled",
            completed_at=now,
            duration_ms=duration_ms,
        )
        self.event_bus.emit(EventType.AGENT_THINKING, "manager", {
            "thought": "分析已由用户中止。",
        })
        self.event_bus.emit(EventType.RUN_COMPLETED, "manager", {
            "duration": f"{duration_ms / 1000:.1f}s",
            "cancelled": True,
            "run_id": run_id,
            "project": project_name,
        })
        try:
            events_path = run_dir / "events.jsonl"
            self.event_bus.save_to_file(events_path)
        except Exception:
            pass
        return {
            "status": "cancelled",
            "message": "分析已中止",
            "run_id": run_id,
            "project": project_name,
            "duration_ms": duration_ms,
        }

    def _attach_pause_dialogue_message(
        self,
        agent: str,
        payload: dict[str, Any],
        **kwargs: Any,
    ) -> dict[str, Any]:
        """不在暂停点注入任何固定/模型生成台词；仅保证 `message` 键存在（与结构化卡片分工）。"""
        del agent, kwargs  # API 兼容旧调用点，不再使用
        out = dict(payload)
        if "message" not in out or out.get("message") is None:
            out["message"] = ""
        return out

    def _mandatory_guardrails_block_report(self, results: list[dict[str, Any]]) -> tuple[bool, str]:
        """逐条检查 Analyst 结果：任一强制级护栏未通过则不应调用 Reporter。

        Returns:
            (True, markdown_body) 若应阻止正式报告；否则 (False, "").
        """
        if not results:
            return False, ""
        sections: list[str] = []
        for i, result in enumerate(results):
            grs = self.guardrails.check(result)
            if self.guardrails.can_output(grs):
                continue
            label = str(result.get("question") or result.get("result_id") or f"结果 {i + 1}")
            sections.append(f"## {label}\n\n{self.guardrails.format_report(grs)}")
        if not sections:
            return False, ""
        header = (
            "# 统计护栏：强制级未通过\n\n"
            "按产品约定，**未生成正式 HTML 报告**（Reporter 已跳过）。\n\n"
            "---\n\n"
        )
        return True, header + "\n\n---\n\n".join(sections)

    def run(
        self,
        data_path: str,
        query: str = "",
        *,
        project_name: str | None = None,
        output_dir: str | None = None,
        formats: list[str] | None = None,
        template: str | None = None,
        resume: bool = False,
        progress_path: str | None = None,
        phase: str = "full",
        scout_context: dict | None = None,
        cleaning_operations: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """
        主入口：执行完整分析流程

        Args:
            data_path: 数据文件路径
            query: 用户的分析问题
            project_name: 项目名（默认从文件名推断）
            output_dir: 自定义输出目录
            formats: 报告输出格式
            template: 报告模板 (default/academic/brief/business_analysis/ab_test/executive_brief/data_audit)
            resume: 是否从上次断点继续
            progress_path: 外部 progress.yaml 路径
            phase: 运行阶段
                - "scout_first": 只跑 Scout，返回字段信息
                - "cleaning_first": Scout（缓存）+ Cleaner（strategy_only），返回清洗策略
                - "analyst_first": Scout（缓存）+ Cleaner（strategy_only，已确认）+ Analyst（preliminary）
                - "full": 完整 pipeline
            scout_context: Scout 的缓存上下文（用于避免重复跑 Scout）
            cleaning_operations: 用户确认的清洗操作（Cleaner 直接执行，不重新规划）

        Returns:
            运行结果摘要。`status` 可能为 `completed` / `guardrails_blocked`（强制级护栏未通过，已跳过 Reporter）/
            `scout_confirm` / `cleaner_strategy` / `analyst_preliminary` 等阶段返回值。
        """
        run_start = datetime.now()

        # 1. 创建项目
        if project_name is None:
            project_name = Path(data_path).stem.replace(" ", "_")

        self.event_bus.emit(EventType.RUN_STARTED, "manager", {
            "query": query,
            "project": project_name,
        })

        self.output_mgr = OutputManager(self.config.output, project_name)
        schema_file = self.output_mgr.project_dir / "progress.yaml"
        self.memory = MemoryManager(self.db, progress_path=schema_file)

        # 初始化 Scribe Agent（看板驱动）
        self.scribe = ScribeAgent(self.config.llm, self.event_bus, self.output_mgr.project_dir)
        self.scribe.init_pipeline()

        # 处理 --progress 参数
        if progress_path:
            n = self.memory.import_progress_yaml(project_name, Path(progress_path))
            if n > 0:
                self.event_bus.emit(EventType.AGENT_THINKING, "manager", {
                    "thought": f"📄 导入了 {n} 条进度定义",
                })

        run_dir = self.output_mgr.create_run_dir()
        run_id = run_dir.name

        with self._cancel_lock:
            self._cancel_requested_flag = False

        # 创建数据库记录
        self.db.create_project(project_name, data_path=data_path)

        # 1.5 解析用户查询 — 理解用户真正想问什么
        parsed_intent = self._parse_user_query(query)
        self.event_bus.emit(EventType.AGENT_THINKING, "manager", {
            "thought": f"🔍 收到，启动分析，让我来{self._describe_intent(parsed_intent)}",
        })

        # 2. 创建分析计划
        plan = self._create_plan(query, parsed_intent=parsed_intent)
        # 与 HaGoKuDB.create_run 默认一致；仅为 runs 表元数据，非面向用户的模式档位
        self.db.create_run(run_id, project_name, query=query, plan=plan, manager_mode="balanced")

        # 初始化 Agent（传入 scribe 用于看板 block/unblock）
        # 双层 LLM 策略：Scout/Cleaner/Reporter 用 quick，Analyst 用 deep
        scout = ScoutAgent(self.config.llm, self.event_bus, llm_client=self.llm_quick, scribe=self.scribe)
        cleaner = CleanerAgent(self.config.llm, self.event_bus, llm_client=self.llm_quick, scribe=self.scribe)
        analyst = AnalystAgent(self.config.llm, self.event_bus, llm_client=self.llm_deep, scribe=self.scribe)
        reporter = ReporterAgent(self.config.llm, self.event_bus, llm_client=self.llm_quick, scribe=self.scribe)

        # Resume 支持
        context: dict | None = None
        df_clean = None
        cleaning_report = None
        cleaned_path_str = ""

        if resume:
            state = self.memory.get_resume_state(project_name)
            if state and state["stage"] in ("cleaned", "analyzed", "reported"):
                self.event_bus.emit(EventType.AGENT_THINKING, "manager", {
                    "thought": f"⏩ 从 {state['stage']} 阶段恢复，跳过 Scout 和 Cleaner",
                })
                # 恢复上下文
                if state.get("context") and isinstance(state["context"], dict):
                    context = state["context"]
                # 加载清洗后数据
                if state.get("cleaned_path"):
                    import pandas as pd
                    cleaned_path_str = state["cleaned_path"]
                    if Path(cleaned_path_str).exists():
                        df_clean = pd.read_parquet(cleaned_path_str)

        # ── Scout 交互确认阶段 ──────────────────────────────────
        # phase="scout_first" 时只跑 Scout，返回 pending_items 供用户确认
        if phase == "scout_first":
            self.event_bus.emit(EventType.AGENT_THINKING, "manager", {
                "thought": "🔍 正在识别数据字段，请稍候...",
            })
            # 加载项目历史记忆，避免用户重复回答字段含义
            memory_project = self.memory.build_memory_project(project_name) if self.memory else None
            scout = ScoutAgent(self.config.llm, self.event_bus, llm_client=self.llm_quick, scribe=self.scribe,
                               memory_project=memory_project)
            ir = scout.begin(data_path=data_path, query=query, project_id=project_name,
                             memory_project=memory_project)
            # begin() 已触发 AGENT_STARTED（由 Scribe claim 任务），并在需要确认时 block 了看板
            # 返回 InteractionResult 给 UI 显示确认项
            return {
                "status": "scout_confirm",
                "phase": ir.phase,
                "message": ir.message,
                "needs_confirmation": ir.needs_confirmation,
                "pending_items": ir.pending_items,
                "data": ir.data,
                "final": ir.final,
                "memory_loaded": bool(memory_project and memory_project.get("fields")),
            }

        # ── Cleaner 策略阶段 ────────────────────────────────────
        # phase="cleaning_first"：跑 Scout（缓存）+ Cleaner（strategy_only），返回清洗策略供用户确认
        if phase == "cleaning_first":
            # Scout（使用缓存上下文或重新跑）
            if scout_context is not None:
                context = scout_context
                self.event_bus.emit(EventType.AGENT_THINKING, "manager", {
                    "thought": f"🔍 使用缓存的字段信息（{context['n_cols']} 个字段）",
                })
            else:
                self.event_bus.emit(EventType.AGENT_THINKING, "manager", {
                    "thought": "🔍 Scout 缓存未命中，重新识别字段...",
                })
                scout_agent = ScoutAgent(self.config.llm, self.event_bus, llm_client=self.llm_quick)
                context = scout_agent.run(data_path, query="", project_id=project_name)

            # Cleaner：只检测+计划，不执行清洗
            self.event_bus.emit(EventType.AGENT_THINKING, "manager", {
                "thought": "🧹 检测数据质量，生成清洗策略...",
            })
            cleaner = CleanerAgent(self.config.llm, self.event_bus, llm_client=self.llm_quick)
            strategy_result = cleaner.get_strategy_summary(data_path, context)
            operations = strategy_result.get("operations", [])
            quality = strategy_result.get("data_quality", "unknown")
            llm_message = self._generate_phase_message(
                "cleaning_strategy",
                operations=operations,
                data_quality=quality,
            )
            if isinstance(strategy_result, dict):
                self.event_bus.emit(EventType.AGENT_COMPLETED, "cleaner", {
                    "result_summary": f"检测完成：{len(operations)} 个计划操作",
                })
                return {
                    "status": "cleaner_strategy",
                    "message": llm_message,
                    "scout_data": {
                        "n_cols": context["n_cols"],
                        "n_rows": context["n_rows"],
                        "columns": [s["column_name"] for s in context["column_semantics"]],
                        "uncertain_columns": [s["column_name"] for s in context["column_semantics"] if s.get("needs_user_input")],
                        "column_descriptions": context["column_descriptions"],
                    },
                    "outliers": strategy_result.get("outliers", {}),
                    "missing_mechanisms": strategy_result.get("missing_mechanisms", {}),
                    "operations": operations,
                    "data_quality": quality,
                    "duration_ms": int((datetime.now() - run_start).total_seconds() * 1000),
                }
            # 正常执行（用户已确认操作，直接清洗）
            df_clean, cleaning_report = strategy_result

        # ── Analyst 初步发现阶段 ─────────────────────────────────
        # phase="analyst_first"：Scout（缓存）+ Cleaner（strategy_only，已确认）+ Analyst（preliminary）
        if phase == "analyst_first":
            # Scout
            if scout_context is not None:
                context = scout_context
                self.event_bus.emit(EventType.AGENT_THINKING, "manager", {
                    "thought": f"🔍 使用缓存的字段信息（{context['n_cols']} 个字段）",
                })
            else:
                scout_agent = ScoutAgent(self.config.llm, self.event_bus, llm_client=self.llm_quick)
                context = scout_agent.run(data_path, query="", project_id=project_name)

            # Cleaner
            self.event_bus.emit(EventType.AGENT_THINKING, "manager", {
                "thought": "🧹 数据清洗（已确认策略）...",
            })
            cleaner = CleanerAgent(self.config.llm, self.event_bus, llm_client=self.llm_quick)
            if cleaning_operations is not None:
                # 用户已确认策略 → 执行清洗
                df_raw, df_clean, cleaning_report, _ = cleaner.run(
                    data_path, context,
                    user_operations=cleaning_operations,
                    impact_warning=self.config.manager.cleaning_impact_warning,
                    phase="full",
                )
            else:
                # 未确认 → 只返回策略供用户确认
                cleaner_result = cleaner.run(
                    data_path, context,
                    user_operations=cleaning_operations,
                    impact_warning=self.config.manager.cleaning_impact_warning,
                    phase="strategy_only",
                )
                if isinstance(cleaner_result, tuple) and len(cleaner_result) >= 4:
                    _, _, _, strategy_dict = cleaner_result
                    if isinstance(strategy_dict, dict):
                        # 用户未确认操作，用自动规划的执行
                        auto_ops = strategy_dict.get("operations", [])
                        df_raw, df_clean, cleaning_report, _ = cleaner.run(
                            data_path, context,
                            user_operations=auto_ops,
                            impact_warning=self.config.manager.cleaning_impact_warning,
                            phase="full",
                        )
                    else:
                        df_clean, cleaning_report, _ = cleaner_result
                else:
                    df_clean, cleaning_report, _ = cleaner_result  # type: ignore[assignment]

            # Analyst：初步发现或完整分析（取决于phase）
            analyst_phase = "full" if phase == "full" else "preliminary"
            self.event_bus.emit(EventType.AGENT_THINKING, "manager", {
                "thought": "📊 初步分析，发现数据中的规律..." if analyst_phase == "preliminary" else "📊 完整分析中...",
            })
            analyst = AnalystAgent(self.config.llm, self.event_bus, llm_client=self.llm_deep)
            analyst_result = analyst.run(df_clean, context, plan, phase=analyst_phase)
            if isinstance(analyst_result, dict):
                self.event_bus.emit(EventType.AGENT_COMPLETED, "analyst", {
                    "result_summary": f"初步发现 {len(analyst_result.get('preliminary_findings', []))} 个，待确认",
                })
                findings = analyst_result.get("preliminary_findings", [])
                suggested = analyst_result.get("suggested_focus", "")
                power_warnings = analyst_result.get("power_warnings", [])[:2]
                llm_message = self._generate_phase_message(
                    "analyst_preliminary",
                    findings=findings,
                    power_warnings=power_warnings,
                    suggested_focus=suggested,
                )
                return {
                    "status": "analyst_preliminary",
                    "message": llm_message,
                    "power_warnings": power_warnings,
                    "business_metrics": analyst_result.get("business_metrics", []),
                    "preliminary_findings": findings,
                    "suggested_focus": suggested,
                    "cleaning_impact": cleaning_report.impact_rate if cleaning_report else 0,
                    "duration_ms": int((datetime.now() - run_start).total_seconds() * 1000),
                }
            results, business_metrics = analyst_result

        try:
            # Scout + Cleaner（如果不是 resume）
            if context is None:
                # 3. Scout: 数据侦察
                # 加载项目历史记忆，避免用户重复回答字段含义
                memory_project = self.memory.build_memory_project(project_name) if self.memory else None
                scout.memory_project = memory_project
                context = scout.run(
                    data_path, query, project_id=project_name, emit_completed=False,
                    memory_project=memory_project,
                )
                if context.get("error"):
                    raise RuntimeError(str(context["error"]))

                if self._is_cancel_requested():
                    return self._finish_run_cancelled(run_id, project_name, run_start, run_dir)

                # ── 多轮对齐：Scout 字段理解子状态机 ───────────────────────────────
                # 结构：外层循环（Scout 循环 + gate）；内层 Scout 循环负责字段对齐
                # 对齐条件：用户纯确认  OR  所有字段 needs_user_input=False
                # 对齐后发 gate_to_cleaning 暂停；用户「还有补充」→ 回 Scout 内层循环；纯确认 → 进 Cleaner
                interaction_revision = 0
                while True:
                    # 内层：Scout 字段对齐循环
                    while True:
                        scout_msg = scout_field_review_pause_payload(context)
                        scout_msg["interaction_revision"] = interaction_revision
                        scout_msg = self._attach_pause_dialogue_message("scout", scout_msg)
                        user_reply_scout = self._pause_and_wait("scout", scout_msg)
                        if user_reply_scout == HAGOKU_CANCEL_PAUSE_TOKEN:
                            return self._finish_run_cancelled(run_id, project_name, run_start, run_dir)
                        applied_scout = apply_scout_user_field_reply_to_context(
                            context,
                            user_reply_scout or "",
                            llm_client=self.llm_quick_raw,
                            llm_model=self.config.llm.model_quick or self.config.llm.model,
                        )
                        # 用户字段回复：持久化到项目记忆，避免下次重复询问
                        if applied_scout and self.memory:
                            self._persist_scout_field_updates(project_name, applied_scout, context)
                        if user_reply_scout:
                            self.event_bus.emit(
                                EventType.USER_INPUT_RECEIVED,
                                "scout",
                                scout_user_input_received_payload(
                                    context,
                                    user_reply_scout,
                                    applied_scout,
                                    interaction_revision,
                                ),
                            )
                            if not _scout_reply_is_pure_confirm(user_reply_scout):
                                query = f"{query}\n[用户补充] {user_reply_scout}".strip()
                        # 对齐判定：已对齐则出内层循环、进 gate；未对齐则继续内层（revision 递增）
                        if _is_scout_aligned(context, user_reply_scout):
                            break
                        interaction_revision += 1

                    # ── 跨阶段闸门：字段对齐后、进入清洗前 ────────────────────────
                    gate_msg = gate_cleaning_pause_payload(context)
                    gate_msg["interaction_revision"] = interaction_revision
                    gate_msg = self._attach_pause_dialogue_message("scout", gate_msg)
                    gate_reply = self._pause_and_wait("scout", gate_msg)
                    if gate_reply == HAGOKU_CANCEL_PAUSE_TOKEN:
                        return self._finish_run_cancelled(run_id, project_name, run_start, run_dir)
                    if _is_gate_confirm(gate_reply):
                        # 确认进清洗 → 出外层循环，继续执行 Cleaner
                        break
                    # 「还有补充 / 纠错」→ 先解析并应用到 context，再回 Scout 内层循环
                    if gate_reply and not _scout_reply_is_pure_confirm(gate_reply):
                        gate_applied = apply_scout_user_field_reply_to_context(
                            context,
                            gate_reply,
                            llm_client=self.llm_quick_raw,
                            llm_model=self.config.llm.model_quick or self.config.llm.model,
                        )
                        # 闸门处的字段补充也持久化到项目记忆
                        if gate_applied and self.memory:
                            self._persist_scout_field_updates(project_name, gate_applied, context)
                        if gate_reply:
                            self.event_bus.emit(
                                EventType.USER_INPUT_RECEIVED,
                                "scout",
                                scout_user_input_received_payload(
                                    context,
                                    gate_reply,
                                    gate_applied,
                                    interaction_revision,
                                ),
                            )
                        query = f"{query}\n[用户补充] {gate_reply}".strip()
                    # 必须递增 revision，否则下一轮 field_review 与上一轮同号，前端会再插一张表。
                    interaction_revision += 1

                # ── 分析目的确认暂停点（仅当存在 target/features 时）──
                # 闸门确认字段对齐后、进入 Cleaner 前，让用户确认分析目的（目标变量、特征变量）
                analysis_purpose = self._build_analysis_purpose(context)
                context["analysis_purpose"] = analysis_purpose

                if analysis_purpose.get("target") or analysis_purpose.get("features"):
                    ap_payload = analysis_purpose_pause_payload(context)
                    ap_payload["interaction_revision"] = interaction_revision
                    ap_payload = self._attach_pause_dialogue_message("scout", ap_payload)
                    ap_reply = self._pause_and_wait("scout", ap_payload)
                    if ap_reply == HAGOKU_CANCEL_PAUSE_TOKEN:
                        return self._finish_run_cancelled(run_id, project_name, run_start, run_dir)

                    # 用户可能在此修正 target/features：用 LLM tool calling 解析
                    if ap_reply and not _scout_reply_is_pure_confirm(ap_reply):
                        ap_applied = apply_scout_user_field_reply_to_context(
                            context,
                            ap_reply,
                            llm_client=self.llm_quick_raw,
                            llm_model=self.config.llm.model_quick or self.config.llm.model,
                        )
                        if ap_reply:
                            self.event_bus.emit(
                                EventType.USER_INPUT_RECEIVED,
                                "scout",
                                scout_user_input_received_payload(
                                    context,
                                    ap_reply,
                                    ap_applied,
                                    interaction_revision,
                                ),
                            )
                        # 重新构建 analysis_purpose（可能因用户修正而改变）
                        context["analysis_purpose"] = self._build_analysis_purpose(context)
                    interaction_revision += 1

                n_sem = len(context.get("column_semantics", []))
                self.event_bus.emit(
                    EventType.AGENT_COMPLETED,
                    "scout",
                    {"result_summary": f"理解 {n_sem} 个字段（用户已确认）"},
                )

                # 注入上游摘要（Scout → Cleaner）
                upstream_note = self._get_upstream_summary("cleaner")
                if upstream_note:
                    context["upstream_summary"] = upstream_note
                    self.event_bus.emit(EventType.AGENT_THINKING, "manager", {
                        "thought": f"📋 已注入 Scout 上游摘要给 Cleaner",
                    })

                # 4. Cleaner: 数据清洗
                df_raw, df_clean, cleaning_report, _ = cleaner.run(
                    data_path, context,
                    impact_warning=self.config.manager.cleaning_impact_warning,
                    emit_completed=False,
                )

                if self._is_cancel_requested():
                    return self._finish_run_cancelled(run_id, project_name, run_start, run_dir)

                # ── 暂停：清洗结果待用户确认后再记 Cleaner 完成（多轮：仅显式放行才出子循环）──
                cleaner_results = {
                    "operations": [op.to_dict() if hasattr(op, 'to_dict') else op for op in (cleaning_report.operations if cleaning_report else [])],
                    "data_quality": getattr(cleaning_report, "data_quality", "unknown"),
                    "impact_rate": cleaning_report.impact_rate if cleaning_report else 0,
                }
                cleaning_revision = 0
                while True:
                    cleaner_msg = cleaning_review_pause_payload(
                        cleaning_report,
                        data_quality=str(cleaner_results["data_quality"]),
                        impact_rate=float(cleaner_results["impact_rate"] or 0.0),
                    )
                    cleaner_msg["interaction_revision"] = cleaning_revision
                    cleaner_msg = self._attach_pause_dialogue_message("cleaner", cleaner_msg)
                    user_reply_cleaner = self._pause_and_wait("cleaner", cleaner_msg)
                    if user_reply_cleaner == HAGOKU_CANCEL_PAUSE_TOKEN:
                        return self._finish_run_cancelled(run_id, project_name, run_start, run_dir)
                    if user_reply_cleaner:
                        self.event_bus.emit(EventType.USER_INPUT_RECEIVED, "cleaner", {
                            "reply": user_reply_cleaner,
                            "interaction_revision": cleaning_revision,
                            "proceed_accepted": _cleaner_reply_accepts_proceed(user_reply_cleaner),
                        })
                        if not _cleaner_reply_accepts_proceed(user_reply_cleaner):
                            query = f"{query}\n[用户补充] {user_reply_cleaner}".strip()
                    if _cleaner_reply_accepts_proceed(user_reply_cleaner or ""):
                        break
                    cleaning_revision += 1
                ir = cleaning_report.impact_rate if cleaning_report else 0.0
                self.event_bus.emit(
                    EventType.AGENT_COMPLETED,
                    "cleaner",
                    {"result_summary": f"影响率 {ir:.1%}（用户已确认）"},
                )
                if df_clean is not None:
                    cleaned_path = self.output_mgr.data_dir / f"cleaned_{run_id}.parquet"
                    save_data(df_clean, cleaned_path)
                    cleaned_path_str = str(cleaned_path)

                    # 同时保存原始数据副本，供 Analyst 按分析类型选用（P1-3）
                    if df_raw is not None:
                        raw_path = self.output_mgr.data_dir / f"raw_{run_id}.parquet"
                        save_data(df_raw, raw_path)
                        raw_path_str = str(raw_path)
                    else:
                        raw_path_str = cleaned_path_str
                else:
                    cleaned_path_str = ""
                    raw_path_str = ""
                    self.event_bus.emit(EventType.QUALITY_CHECK, "manager", {
                        "verdict": "warning",
                        "detail": "数据清洗未成功，尝试使用原始数据",
                    })

                # 保存 resume 状态（包含 raw 路径）
                self.memory.save_resume_state(
                    project_name, "cleaned",
                    cleaned_path=cleaned_path_str,
                    raw_path=raw_path_str if df_clean is not None else "",
                    context=context, run_id=run_id,
                )

                # 5. 质量检查
                if cleaning_report:
                    self.event_bus.emit(EventType.QUALITY_CHECK, "manager", {
                        "verdict": "pass" if cleaning_report.impact_rate < self.config.manager.cleaning_impact_warning else "warning",
                        "detail": f"清洗影响率 {cleaning_report.impact_rate:.1%}",
                    })

            # 注入上游摘要（Cleaner → Analyst）
            upstream_note_analyst = self._get_upstream_summary("analyst")
            if upstream_note_analyst:
                context["upstream_summary"] = upstream_note_analyst
                self.event_bus.emit(EventType.AGENT_THINKING, "manager", {
                    "thought": "📋 已注入 Cleaner 上游摘要给 Analyst",
                })

            # 确保 analysis_purpose 仍然在 context 中
            if "analysis_purpose" not in context:
                context["analysis_purpose"] = self._build_analysis_purpose(context)

            # 6. Analyst: 统计分析
            if df_clean is None or context is None:
                # 尝试加载原始数据继续
                if context is not None and context.get("data_path"):
                    try:
                        from ..tools.data_io import load_data
                        df_clean = load_data(context["data_path"])
                        self.event_bus.emit(EventType.QUALITY_CHECK, "manager", {
                            "verdict": "warning",
                            "detail": "使用原始数据继续分析",
                        })
                    except Exception:
                        raise RuntimeError(
                            f"无法获取有效数据（context.data_path={context['data_path']}），分析无法继续"
                        )
                else:
                    raise RuntimeError(
                        "Pipeline error: 缺少有效数据和上下文，无法继续分析。"
                    )
            results, business_metrics = analyst.run(
                df_clean, context, plan, emit_completed=False
            )

            if self._is_cancel_requested():
                return self._finish_run_cancelled(run_id, project_name, run_start, run_dir)

            # ── 暂停：分析结果待用户确认后再记 Analyst 完成（多轮：仅显式放行才出子循环）──
            analyst_revision = 0
            while True:
                analyst_pause = analyst_review_pause_payload(
                    results if isinstance(results, list) else [],
                )
                analyst_pause["interaction_revision"] = analyst_revision
                analyst_pause = self._attach_pause_dialogue_message("analyst", analyst_pause)
                user_reply_analyst = self._pause_and_wait("analyst", analyst_pause)
                if user_reply_analyst == HAGOKU_CANCEL_PAUSE_TOKEN:
                    return self._finish_run_cancelled(run_id, project_name, run_start, run_dir)
                if user_reply_analyst:
                    self.event_bus.emit(EventType.USER_INPUT_RECEIVED, "analyst", {
                        "reply": user_reply_analyst,
                        "interaction_revision": analyst_revision,
                        "proceed_accepted": _analyst_reply_accepts_proceed(user_reply_analyst),
                    })
                    if not _analyst_reply_accepts_proceed(user_reply_analyst):
                        query = f"{query}\n[用户补充] {user_reply_analyst}".strip()
                if _analyst_reply_accepts_proceed(user_reply_analyst or ""):
                    break
                analyst_revision += 1
            n_res = len(results) if isinstance(results, list) else 0
            self.event_bus.emit(
                EventType.AGENT_COMPLETED,
                "analyst",
                {"result_summary": f"完成 {n_res} 项分析（用户已确认）"},
            )

            # 7. 统计护栏（编排层）：强制级未通过则跳过 Reporter
            blocked, blocked_md = self._mandatory_guardrails_block_report(
                results if isinstance(results, list) else [],
            )
            if blocked:
                notice_path = run_dir / "output" / "GUARDRAILS_BLOCKED.md"
                notice_path.parent.mkdir(parents=True, exist_ok=True)
                notice_path.write_text(blocked_md, encoding="utf-8")
                output_path = str(notice_path)
                self.event_bus.emit(EventType.QUALITY_CHECK, "manager", {
                    "verdict": "fail",
                    "detail": "强制级统计护栏未通过，已跳过 Reporter（未生成正式 HTML 报告）",
                })
                self.event_bus.emit(EventType.AGENT_COMPLETED, "reporter", {
                    "result_summary": "已跳过：强制级护栏未通过",
                    "skipped": True,
                })
                # 保存 findings（便于审计）
                for result in results:
                    self.db.save_finding({
                        "id": result["result_id"],
                        "run_id": run_id,
                        "analysis_type": result["analysis_type"],
                        "question": result["question"],
                        "conclusion_plain": result.get("conclusion_plain", ""),
                        "conclusion_statistical": result.get("conclusion_statistical", ""),
                        "p_value": result.get("p_value"),
                        "effect_size": result.get("effect_size"),
                        "effect_type": result.get("effect_type", ""),
                        "confidence_interval": result.get("confidence_interval"),
                        "significance": result.get("significance", ""),
                    })
                run_meta = {
                    "run_id": run_id,
                    "project": project_name,
                    "query": query,
                    "plan": plan,
                    "n_results": len(results),
                    "cleaning_impact": cleaning_report.impact_rate if cleaning_report else 0,
                    "output_path": output_path,
                    "guardrails_blocked": True,
                }
                self.output_mgr.save_run_meta(run_dir, run_meta)
                duration_ms = int((datetime.now() - run_start).total_seconds() * 1000)
                self.db.complete_run(run_id, duration_ms=duration_ms, output_path=output_path)
                learned = self.memory.learn_from_run(project_name, context, results, cleaning_report)
                if learned > 0:
                    self.event_bus.emit(EventType.AGENT_THINKING, "manager", {
                        "thought": f"🧠 学习了 {learned} 条记忆，下次分析将自动应用",
                    })
                self.memory.save_resume_state(
                    project_name, "analyzed",
                    cleaned_path=cleaned_path_str,
                    context=context, run_id=run_id,
                )
                self.output_mgr.create_latest_symlink(run_dir)
                if self.project_mgr.exists(project_name):
                    self.project_mgr.record_run(project_name)
                events_path = run_dir / "events.jsonl"
                self.event_bus.save_to_file(events_path)
                self.event_bus.emit(EventType.RUN_COMPLETED, "manager", {
                    "duration": f"{duration_ms / 1000:.1f}s",
                    "token_count": sum(
                        e.data.get("token_count", 0)
                        for e in self.event_bus.events
                        if e.event_type == EventType.TOOL_RESULT and "token_count" in e.data
                    ),
                    "output_path": output_path,
                    "guardrails_blocked": True,
                    "run_id": run_id,
                    "project": project_name,
                })
                return {
                    "status": "guardrails_blocked",
                    "message": "统计护栏强制级未通过，已跳过 Reporter。说明见 GUARDRAILS_BLOCKED.md",
                    "run_id": run_id,
                    "project": project_name,
                    "output_path": output_path,
                    "n_results": len(results),
                    "duration_ms": duration_ms,
                }

            # 注入上游摘要（Analyst → Reporter）
            upstream_note_reporter = self._get_upstream_summary("reporter")
            if upstream_note_reporter:
                context["upstream_summary"] = upstream_note_reporter
                self.event_bus.emit(EventType.AGENT_THINKING, "manager", {
                    "thought": "📋 已注入 Analyst 上游摘要给 Reporter",
                })

            # 确保 analysis_purpose 仍然在 context 中
            if "analysis_purpose" not in context:
                context["analysis_purpose"] = self._build_analysis_purpose(context)

            # 7b. Reporter: 生成报告
            output_path = str(run_dir / "output" / "report.html")
            reporter.run(
                results=results,
                context=context,
                cleaning_summary=cleaning_report.to_dict() if cleaning_report else {},
                project_name=project_name,
                query=query,
                output_path=output_path,
                formats=formats or self.config.output.formats,
                template=template,
                df=df_clean,
                business_metrics=business_metrics,
            )

            # 8. 保存运行元数据
            run_meta = {
                "run_id": run_id,
                "project": project_name,
                "query": query,
                "plan": plan,
                "n_results": len(results),
                "cleaning_impact": cleaning_report.impact_rate if cleaning_report else 0,
                "output_path": output_path,
            }
            self.output_mgr.save_run_meta(run_dir, run_meta)

            # 9. 更新数据库
            duration_ms = int((datetime.now() - run_start).total_seconds() * 1000)
            self.db.complete_run(run_id, duration_ms=duration_ms, output_path=output_path)

            # 保存 findings
            for result in results:
                self.db.save_finding({
                    "id": result["result_id"],
                    "run_id": run_id,
                    "analysis_type": result["analysis_type"],
                    "question": result["question"],
                    "conclusion_plain": result.get("conclusion_plain", ""),
                    "conclusion_statistical": result.get("conclusion_statistical", ""),
                    "p_value": result.get("p_value"),
                    "effect_size": result.get("effect_size"),
                    "effect_type": result.get("effect_type"),
                    "confidence_interval": result.get("confidence_interval"),
                    "significance": result.get("significance"),
                })

            # 10. 学习 + 导出 progress.yaml
            learned = self.memory.learn_from_run(project_name, context, results, cleaning_report)
            if learned > 0:
                self.event_bus.emit(EventType.AGENT_THINKING, "manager", {
                    "thought": f"🧠 学习了 {learned} 条记忆，下次分析将自动应用",
                })

            # 保存 resume 状态
            self.memory.save_resume_state(
                project_name, "reported",
                cleaned_path=cleaned_path_str,
                context=context, run_id=run_id,
            )

            # 11. 创建 latest 链接
            self.output_mgr.create_latest_symlink(run_dir)

            # 11.5 记录到项目管理器（更新运行计数等）
            if self.project_mgr.exists(project_name):
                self.project_mgr.record_run(project_name)

            # 12. 事件日志
            events_path = run_dir / "events.jsonl"
            self.event_bus.save_to_file(events_path)

            # 13. 发射完成事件
            self.event_bus.emit(EventType.RUN_COMPLETED, "manager", {
                "duration": f"{duration_ms / 1000:.1f}s",
                "token_count": sum(
                    e.data.get("token_count", 0)
                    for e in self.event_bus.events
                    if e.event_type == EventType.TOOL_RESULT and "token_count" in e.data
                ),
                "output_path": output_path,
                "run_id": run_id,
                "project": project_name,
            })

            return {
                "status": "completed",
                "message": f"✅ 分析完成！共生成 {len(results)} 项发现，报告已保存。",
                "run_id": run_id,
                "project": project_name,
                "output_path": output_path,
                "n_results": len(results),
                "duration_ms": duration_ms,
            }

        except Exception as e:
            duration_ms = int((datetime.now() - run_start).total_seconds() * 1000)
            self.db.fail_run(run_id, duration_ms=duration_ms)
            self.event_bus.emit(EventType.RUN_FAILED, "manager", {"error": str(e)})
            raise

    def _create_plan(
        self,
        query: str,
        parsed_intent: Any | None = None,
    ) -> dict[str, Any]:
        """创建分析计划：LLM 唯一决策引擎，零硬编码规则。"""
        plan = self._call_llm_for_plan(query, parsed_intent=parsed_intent)
        if plan is not None:
            return plan
        # LLM 不可达时的最小兜底
        return {
            "plan_name": "通用分析",
            "agents": ["scout", "cleaner", "analyst", "reporter"],
            "analyst_focus": ["regression", "hypothesis_test", "correlation"],
            "query": query,
            "llm_generated": False,
        }

    def _call_llm_for_plan(
        self,
        query: str,
        parsed_intent: Any | None = None,
    ) -> dict[str, Any] | None:
        """LLM 驱动的分析计划生成（唯一路径）。

        Returns:
            计划 dict，LLM 失败时返回 None。
        """
        from ..llm.plan_schema import (
            DEFAULT_EXPLORATORY_FOCUS,
            VALID_ANALYST_FOCUS,
            LLMPlanResponse,
        )
        from ..llm.prompts import PLAN_GENERATION_SYSTEM, PLAN_GENERATION_USER

        try:
            if self._llm_client is None:
                self._llm_client = create_structured_llm_client(self.config.llm)

            intent_context = self._build_intent_context(query, parsed_intent)
            messages = [
                {"role": "system", "content": PLAN_GENERATION_SYSTEM},
                {"role": "user", "content": PLAN_GENERATION_USER.format(query=intent_context)},
            ]

            response: LLMPlanResponse = self._llm_client.chat.completions.create(
                model=self.config.llm.model,
                messages=messages,
                response_model=LLMPlanResponse,
                temperature=self.config.llm.temperature,
                max_tokens=self.config.llm.max_tokens,
                timeout=30,
            )

            validated_focus = [f for f in response.analyst_focus if f in VALID_ANALYST_FOCUS]
            if not validated_focus:
                validated_focus = DEFAULT_EXPLORATORY_FOCUS.copy()

            agents = list(response.agents)
            if "scout" not in agents:
                agents.insert(0, "scout")
            if "reporter" not in agents:
                agents.append("reporter")

            plan = {
                "plan_name": response.plan_name,
                "agents": agents,
                "analyst_focus": validated_focus,
                "target": response.target,
                "query": response.query,
                "reasoning": response.reasoning,
                "llm_generated": True,
            }
            self.event_bus.emit(EventType.PLAN_CREATED, "manager", {
                "source": "llm",
                "plan_name": plan["plan_name"],
                "reasoning": plan.get("reasoning", ""),
            })
            return plan

        except Exception as e:
            self.event_bus.emit(EventType.AGENT_THINKING, "manager", {
                "thought": f"LLM 计划生成失败: {e}",
            })
            return None

    def _persist_scout_field_updates(
        self,
        project_name: str,
        applied_scout: list[str],
        context: dict[str, Any],
    ) -> None:
        """
        将用户在 Scout 字段核对中的字段理解回复持久化到项目记忆。

        从 `applied_scout`（如 "Code←店铺编号"）中提取字段名与含义，
        通过 MemoryManager.persist_field_descriptions() 写入 SQLite + YAML。
        下次同一项目分析时，这些字段理解会被重新加载，避免重复询问。
        """
        if not self.memory or not applied_scout or not context:
            return

        descs: dict[str, Any] = context.get("column_descriptions", {}) or {}
        display_names: dict[str, Any] = context.get("column_display_names", {}) or {}
        new_descs: dict[str, str] = {}
        new_dnames: dict[str, str] = {}

        for a in applied_scout:
            if not a or "←" not in a:
                continue
            # 格式: "col←desc" 或 "col:[display]←中文名"
            col_part, _, val = a.partition("←")
            col = col_part.strip()
            val = val.strip()
            if not col or not val:
                continue

            if col.endswith(":[display]"):
                col = col.replace(":[display]", "").strip()
                new_dnames[col] = val
            else:
                new_descs[col] = val

        # 补充 context 中已有的 column_descriptions（不上覆盖的应用字段）
        full_descs: dict[str, str] = {}
        for col, d in descs.items():
            if isinstance(d, str) and d.strip():
                full_descs[str(col)] = str(d).strip()
        full_descs.update(new_descs)

        if full_descs:
            self.memory.persist_field_descriptions(
                project_name, full_descs, column_display_names=new_dnames,
            )

    def _parse_user_query(self, query: str) -> Any:
        """解析用户查询为结构化意图"""
        try:
            from .query_parser import parse_query
            return parse_query(query)
        except Exception:
            return None

    def _generate_phase_message(
        self,
        phase: str,
        *,
        operations: list[dict[str, Any]] | None = None,
        data_quality: str = "",
        findings: list[dict[str, Any]] | None = None,
        power_warnings: list[str] | None = None,
        suggested_focus: str = "",
    ) -> str:
        """LLM 生成阶段用户消息（零硬编码文案）。LLM 不可达时返回最小兜底。"""
        from openai import OpenAI

        if phase == "cleaning_strategy":
            n_ops = len(operations) if operations else 0
            if n_ops == 0:
                return f"数据质量：{data_quality}。未检测到需要清洗的问题，数据可以直接分析。"

            ops_desc_lines: list[str] = []
            for op in (operations or [])[:6]:
                col = op.get("column", "")
                reason = op.get("reason", "")
                ops_desc_lines.append(f"  {col}: {reason[:80]}")
            ops_desc = "\n".join(ops_desc_lines) if ops_desc_lines else "（无详情）"

        elif phase == "analyst_preliminary":
            n_findings = len(findings) if findings else 0
            pw = power_warnings[0] if power_warnings else ""
            finding_lines: list[str] = []
            for f in (findings or [])[:5]:
                sig = "显著" if f.get("significance") == "significant" else "不显著"
                q = f.get("question", "")
                p = f.get("p_value")
                p_str = f"（p={p:.4f}）" if p is not None else ""
                finding_lines.append(f"  [{sig}] {p_str}：{q}")
            findings_desc = "\n".join(finding_lines) if finding_lines else "（无显著发现）"
            sf = suggested_focus or "无"
        else:
            return ""

        try:
            client = OpenAI(
                api_key=self.config.llm.api_key,
                base_url=self.config.llm.base_url,
            )
            system_prompt = (
                "你是数据分析助手 HaGoKu Studio。请用自然、亲切的中文为用户生成一段对话消息。"
                "不要使用模板化的句式，用你自己的语言风格来表达。"
                "保持简洁（3-5句话），像一个同事在群里说话的语气。"
            )

            if phase == "cleaning_strategy":
                user_prompt = (
                    f"你刚完成数据清洗策略检测。数据质量：{data_quality}。"
                    f"计划执行 {n_ops} 个清洗操作：\n{ops_desc}\n"
                    "请生成一条消息告知用户，并询问是否可以按此方案清洗（或者想调整）。"
                )
            elif phase == "analyst_preliminary":
                pw_line = f"\n注意：{pw}" if pw else ""
                user_prompt = (
                    f"你刚完成初步数据分析。共 {n_findings} 个发现：\n{findings_desc}{pw_line}\n"
                    f"建议关注方向：{sf}\n"
                    "请生成一条消息告知用户，并询问用户想关注哪个方向。"
                )
            else:
                return ""

            response = client.chat.completions.create(
                model=self.config.llm.model_quick or self.config.llm.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.7,
                max_tokens=300,
            )
            msg = response.choices[0].message.content or ""
            return msg.strip()

        except Exception:
            # LLM 不可达时返回兜底
            if phase == "cleaning_strategy":
                n_ops = len(operations) if operations else 0
                quality_labels = {"good": "数据质量良好", "medium": "数据质量一般", "poor": "数据质量问题较多"}
                q = quality_labels.get(data_quality, data_quality)
                if n_ops == 0:
                    return f"{q}，未检测到需要清洗的问题，可以直接分析。"
                return f"{q}，计划执行 {n_ops} 个清洗操作。这个方案可以吗？"
            elif phase == "analyst_preliminary":
                n_findings = len(findings) if findings else 0
                if n_findings == 0:
                    return "初步分析没有发现明显的统计规律。你想从哪个维度再看一下？"
                return f"初步发现 {n_findings} 个分析方向。你想重点关注哪个？"
            return ""

    def _describe_intent(self, parsed_intent: Any) -> str:
        """将解析后的意图译成接在「让我来」后的自然短句（LLM thinking 驱动，零硬编码映射）。"""
        if parsed_intent is None:
            return "探索一下这份数据有什么规律"

        # 优先使用 LLM 在意图解析时给出的 thinking
        thinking = getattr(parsed_intent, "thinking", "") or ""
        if thinking.strip():
            return thinking.strip()

        # LLM 未提供 thinking 时的最小兜底
        parts: list[str] = []
        if getattr(parsed_intent, "target", None):
            parts.append(f"关注「{parsed_intent.target}」")
        if getattr(parsed_intent, "time_range", None):
            parts.append(f"时间范围「{parsed_intent.time_range}」")
        if getattr(parsed_intent, "group_by", None):
            parts.append(f"按「{'/'.join(parsed_intent.group_by)}」分组")

        base = getattr(parsed_intent, "intent_type", "exploration") or "exploration"
        kind = {"comparison": "对比差异", "causation": "找原因", "correlation": "看关系",
                "trend": "看趋势", "diagnostic": "诊断问题"}.get(base, "探索规律")
        return f"{kind}，{'，'.join(parts)}" if parts else f"{kind}"

    def _build_analysis_purpose(self, context: dict[str, Any]) -> dict[str, Any]:
        """从 context 提取本次分析涉及的核心字段信息，供下游 Agent 聚焦。

        包含 target（目标变量）、features（特征变量）、roles（变量角色映射），
        以及一份人类可读的总结字符串。
        """
        target = context.get("target")
        features = context.get("features") or []
        variable_roles = context.get("variable_roles") or {}

        summary_parts: list[str] = []
        if target:
            summary_parts.append(f"目标变量（因变量）：{target}")
        if features:
            summary_parts.append(f"特征变量（自变量）：{', '.join(str(f) for f in features)}")
        if variable_roles:
            role_lines = [f"  {k}: {v}" for k, v in sorted(variable_roles.items())]
            summary_parts.append(f"变量角色：\n{chr(10).join(role_lines)}")

        return {
            "target": target,
            "features": features,
            "variable_roles": variable_roles,
            "summary": "\n".join(summary_parts) or "（未指定分析字段角色）",
        }

    def _get_upstream_summary(self, agent_name: str) -> str | None:
        """获取指定 Agent 的上游交接笔记，供注入到下游 Agent 的上下文中。

        在启动 Cleaner/Analyst/Reporter 前调用，拉取上游 Agent 的完整产出摘要和交接建议，
        让 Agent 在启动时就能看到全貌，实现全过程理解。
        """
        if self.scribe is None:
            return None
        return self.scribe.get_upstream_summary(agent_name)

    def _build_intent_context(self, query: str, parsed_intent: Any) -> str:
        """将解析后的意图构建成 LLM 可用的上下文（无硬编码标签）。"""
        if parsed_intent is None:
            return query

        parts = [query]
        attrs = [
            ("intent_type", "意图"),
            ("target", "目标变量"),
            ("time_range", "时间范围"),
            ("group_by", "分组维度"),
            ("filters", "筛选条件"),
        ]
        for attr, label in attrs:
            v = getattr(parsed_intent, attr, None)
            if v:
                if isinstance(v, list):
                    v = "、".join(str(x) for x in v)
                parts.append(f"\n【{label}】：{v}")

        thinking = getattr(parsed_intent, "thinking", "") or ""
        if thinking.strip():
            parts.append(f"\n【LLM 理解】：{thinking.strip()}")

        return "".join(parts)

    # ==== CLI 降级模式：允许简化确认匹配 ====
    # 此方法仅用于 CLI 交互模式（非 Web UI 主路径）。
    # 在终端环境中，function calling 的多轮确认流程过于繁琐，
    # 故使用硬编码关键词匹配作为降级方案。Web UI 中走正常的 function calling 通道。
    def _request_field_confirmation(
        self,
        context: dict,
        project_name: str,
    ) -> dict | None:
        """
        Scout 识别完字段后，和用户对话确认字段含义。
        Scout 展示理解，用户纠正，直到用户确认。
        必须用户明确说"好"才能继续。
        """
        print("\n" + "=" * 60)
        print("📋 字段理解")
        print("=" * 60)

        # 展示 Scout 识别出的所有字段
        print("\n我看到了这些字段：")
        for sem in context["column_semantics"]:
            col = sem["column_name"]
            desc = context["column_descriptions"].get(col, sem["inferred_type"])
            print(f"  {col} → {desc}")

        print("\n有不对的，纠正我。直接说就行")
        print("  比如：Inc1 是销售额，不是收入")
        print()

        corrections: dict[str, dict[str, str]] = {}

        while True:
            user_input = input("➜ ").strip()

            if user_input.lower() in ("cancel", "q", "取消"):
                print("\n❌ 已取消")
                return None

            if not user_input:
                continue

            # 用户说"好"或"继续"或"是"表示确认
            if user_input.lower() in ("好", "是", "ok", "继续", "next", "y", "yes"):
                # Scout 展示最终理解，建议进入数据清洗
                print("\n📋 最终字段理解：")
                for sem in context["column_semantics"]:
                    col = sem["column_name"]
                    desc = context["column_descriptions"].get(col, sem["inferred_type"])
                    print(f"  {col} = {desc}")
                print("\n我准备进入数据清洗阶段，可以吗？")
                confirm = input("➜ (回车确认，或继续纠正) ").strip()
                if confirm.lower() in ("好", "是", "ok", "y", "yes", ""):
                    break
                elif confirm:
                    user_input = confirm
                else:
                    continue

            # 让 LLM 理解用户说的话，更新 context
            understood = self._llm_understand_field_update(context, user_input)
            if understood:
                corrections.update(understood)

        if corrections:
            print(f"\n📝 保存 {len(corrections)} 个字段...")
            for col, info in corrections.items():
                context["column_descriptions"][col] = f"{info['chinese_name']}（{info['business_meaning']}）"
                for s in context["column_semantics"]:
                    if s["column_name"] == col:
                        s["evidence"] = info['business_meaning']
                        break
            self._save_field_descriptions(project_name, corrections)

        print("\n✅ 进入数据清洗...")
        return context

    def _llm_understand_field_update(
        self,
        context: dict,
        user_input: str,
    ) -> dict[str, dict[str, str]] | None:
        """让 LLM 理解用户说的字段更新，返回更新的字段字典"""
        try:
            from openai import OpenAI

            columns = [s["column_name"] for s in context["column_semantics"]]

            client = OpenAI(
                api_key=self.config.llm.api_key,
                base_url=self.config.llm.base_url,
            )

            response = client.chat.completions.create(
                model=self.config.llm.model,
                messages=[
                    {"role": "system", "content": "你是数据分析师。用户告诉你字段的含义。请理解用户说的话，提取出字段名、中文名、业务含义。\n输出格式（JSON，只输出JSON）：\n{\"字段名\": {\"chinese_name\": \"中文名\", \"business_meaning\": \"业务含义\"}}"},
                    {"role": "user", "content": f"字段列表：{', '.join(columns)}\n用户说：{user_input}"}
                ],
                temperature=0.1,
                max_tokens=200,
            )
            import json
            result_text = response.choices[0].message.content.strip()
            if result_text.startswith("```"):
                result_text = result_text.split("```")[1]
                if result_text.startswith("json"):
                    result_text = result_text[4:]
            result = json.loads(result_text.strip())

            valid_updates = {}
            for col, info in result.items():
                if col in columns:
                    valid_updates[col] = info
                    print(f"   ✅ {col} = {info['chinese_name']}（{info['business_meaning']}）")

            return valid_updates if valid_updates else None

        except Exception as e:
            print(f"   ⚠️ 没理解：{e}")
            return None

    def respond(
        self,
        user_input: dict,
        project_name: str | None = None,
    ) -> dict[str, Any]:
        """
        处理 Agent 暂停后的用户响应，继续工作流。

        user_input 格式:
          {
            "agent": "scout",           # 当前等待的 agent
            "phase": "confirm_fields",   # 当前阶段
            "confirmed": {...},          # Scout.respond() 格式
            "action": "进入清洗",        # 用户选择的操作（next_step 阶段）
          }

        Returns:
            与 run() 返回格式相同的 dict
        """
        agent_name = user_input.get("agent", "")
        phase = user_input.get("phase", "")

        # 重新初始化 scribe（因为 respond() 是新调用，scribe 需要恢复状态）
        if self.output_mgr is None:
            self.output_mgr = OutputManager(self.config.output, project_name or "default")
        self.scribe = ScribeAgent(self.config.llm, self.event_bus, self.output_mgr.project_dir)

        if agent_name == "scout" and phase == "confirm_fields":
            # 恢复 Scout 状态
            scout = ScoutAgent(self.config.llm, self.event_bus, llm_client=self.llm_quick, scribe=self.scribe)
            # 从 user_input 恢复 Scout 内部状态
            scout._phase = "confirm_fields"
            scout._data_path = user_input.get("data_path", "")
            scout._query = user_input.get("query", "")
            scout._context = user_input.get("context")

            ir = scout.respond(user_input, project_id=project_name)

            # 持久化用户在 confirm_fields 阶段的字段理解回复
            if project_name:
                applied_updates = ir.data.get("applied_field_updates", [])
                if applied_updates:
                    self._ensure_memory_for_respond(project_name)
                    if self.memory:
                        self._persist_scout_field_updates(project_name, applied_updates, scout._context or {})

            if ir.final:
                # Scout 完成了，返回后续指令
                return {
                    "status": "scout_done",
                    "message": ir.message,
                    "phase": ir.phase,
                    "data": ir.data,
                    "final": True,
                }

            # Scout 再次暂停（next_step），返回给 UI
            return {
                "status": "scout_next_step",
                "phase": ir.phase,
                "message": ir.message,
                "actions": ir.actions,
                "pending_items": ir.pending_items,
                "data": ir.data,
                "final": ir.final,
            }

        elif agent_name == "scout" and phase == "next_step":
            action = user_input.get("action", "")
            if action in ("进入清洗", "继续"):
                # 进入清洗阶段
                return {
                    "status": "ready_for_cleaning",
                    "phase": "cleaning_first",
                    "message": "好的，进入清洗阶段",
                    "data": user_input.get("data", {}),
                }
            elif action in ("重新理解字段", "重新开始"):
                # 重新跑 Scout
                return {
                    "status": "restart_scout",
                    "phase": "scout_first",
                    "message": "好的，重新开始字段理解",
                }
            elif action in ("结束分析", "结束"):
                return {
                    "status": "done",
                    "message": "分析结束",
                }
            return {
                "status": "done",
                "message": "未知的操作",
            }

        # 未知 agent/phase
        return {
            "status": "error",
            "message": f"未知阶段: {agent_name}/{phase}",
        }

    def _ensure_memory_for_respond(self, project_name: str) -> None:
        """确保 self.memory 已初始化（供 WebSocket respond() 路径使用）。"""
        if self.memory is not None:
            return
        if self.output_mgr is None:
            self.output_mgr = OutputManager(self.config.output, project_name)
        schema_file = self.output_mgr.project_dir / "progress.yaml"
        self.memory = MemoryManager(self.db, progress_path=schema_file)

    def _save_field_descriptions(
        self,
        project_name: str,
        corrections: dict[str, dict[str, str]],
    ) -> None:
        """保存用户确认的字段描述到 memory/progress.yaml"""
        if not corrections:
            return

        if self.output_mgr is None:
            self.output_mgr = OutputManager(self.config.output, project_name)

        try:
            # 构建 schema 更新
            schema_file = self.output_mgr.project_dir / "progress.yaml"
            import yaml

            # 读取现有 schema
            schema_data: dict[str, Any] = {}
            if schema_file.exists():
                with open(schema_file, "r", encoding="utf-8") as f:
                    schema_data = yaml.safe_load(f) or {}

            if "columns" not in schema_data:
                schema_data["columns"] = {}

            # 更新 columns
            for col, info in corrections.items():
                if col not in schema_data["columns"]:
                    schema_data["columns"][col] = {}
                schema_data["columns"][col]["description"] = f"{info['chinese_name']}（{info['business_meaning']}）"

            # 写回 progress.yaml
            schema_file.parent.mkdir(parents=True, exist_ok=True)
            with open(schema_file, "w", encoding="utf-8") as f:
                yaml.dump(schema_data, f, allow_unicode=True, default_flow_style=False)

        except Exception as e:
            # 保存失败不影响主流程，只打印警告
            print(f"   ⚠️ 保存字段描述失败: {e}")
