"""Scout 阶段 LLM 回复处理（function calling 通道）。CH-5 从 orchestrator.py 拆分。"""
from __future__ import annotations

import json as _json
import logging
from typing import Any

from ..payloads.scout_payload import (
    _expand_column_range,
    _known_scout_columns,
    _resolve_scout_column_token,
    _resolve_scout_column_token_with_context,
    _try_parse_json,
)

# 律 3：多轮对话历史窗口
_CONV_HISTORY_INJECT_TURNS = 3

def apply_scout_user_field_reply_to_context(
    context: dict[str, Any],
    user_reply: str,
    *,
    llm_client: Any = None,
    llm_model: str = "",
    channel_logger: Any = None,
) -> list[str]:
    """
    将用户在 Scout 字段核对暂停点的说明写入 context（column_descriptions、needs_user_input）。

    **核心设计：LLM 作为字段理解的唯一引擎。** 用户的自然语言说明（如"Code 代表店铺编号"）
    原样转发给 LLM 理解语义，LLM 主动识别目标字段、区分含义与中文名称。
    代码只负责把 LLM 返回的 JSON 机械写入 context —— 不解析、不判断、不兜底。

    若 LLM 不可用或调用失败，raise RuntimeError（铁律 2 路径 A / 铁律 7），
    让用户看见错误而非看见错误的结果。

    返回简短人类可读记录（如 ``Code←店铺编号``），供事件或日志；无写入则返回 []。
    """
    raw = (user_reply or "").strip()
    if not raw:
        return []

    columns = _known_scout_columns(context)
    if not columns:
        return []

    # ── LLM 唯一引擎：将用户自然语言说明交给 LLM 理解 ──────────
    # 铁律 2（路径 A）+ 铁律 7：LLM client 不可用必须 raise，不准静默兜底
    if llm_client is None:
        raise RuntimeError(
            "Scout 字段理解失败：LLM client 未初始化。\n"
            "请检查 LLM 配置（base_url / api_key / model）是否正确。"
        )
    return _apply_scout_reply_with_llm(context, raw, columns, llm_client, llm_model, channel_logger)

def _get_scout_tools() -> list[dict[str, Any]]:
    """从全局工具注册表获取 Scout Agent 可用的工具。"""
    from ...tools.registry import agent_tools
    return agent_tools.to_openai("scout")

_SCOUT_FIELD_UPDATE_TOOLS = [  # 保持向后兼容，逐步迁移到 _get_scout_tools()
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
                # 同步 suggested_role + used_in_analysis
                for s in semantics:
                    cname = str(s.get("column_name", ""))
                    if cname == resolved_target:
                        s["suggested_role"] = "target"
                        s["used_in_analysis"] = True
                    elif cname == old_target and s.get("suggested_role") == "target":
                        s["suggested_role"] = "feature"
                        s["used_in_analysis"] = True

        if new_features:
            resolved_features: list[str] = []
            for ft in new_features:
                r = _resolve_scout_column_token(str(ft), columns)
                if r and r not in resolved_features:
                    resolved_features.append(r)
            if resolved_features:
                context["features"] = resolved_features
                applied.append(f"[role]features:{resolved_features}")
                # 同步 suggested_role + used_in_analysis
                for s in semantics:
                    cname = str(s.get("column_name", ""))
                    if cname in resolved_features:
                        s["suggested_role"] = "feature"
                        s["used_in_analysis"] = True

        if new_ignored:
            for ig in new_ignored:
                r = _resolve_scout_column_token(str(ig), columns)
                if r:
                    applied.append(f"[role]ignore:{r}")
                    for s in semantics:
                        if str(s.get("column_name", "")) == r:
                            s["suggested_role"] = "ignore"
                            s["used_in_analysis"] = False

        # 更新 variable_roles 映射
        roles: dict[str, str] = context.get("variable_roles", {}) or {}
        if new_target:
            roles["target"] = new_target
        context["variable_roles"] = roles

def _resolve_to_column_names(
    tokens: list[str],
    columns: list[str],
    display_names: dict[str, Any],
    descriptions: dict[str, Any],
) -> list[str]:
    """把用户给的业务名 / 列名混合 token 映射为真实列名。

    优先级：精确列名 > display_name 完全匹配 > 列名前缀。
    无映射的 token 静默丢弃（由律 7 在外层判定空集时报「未理解」）。

    纯机械运算，不涉及语义判断。**不做 description 子串匹配** — 那是 LLM 的职责。
    LLM 应在工具参数中传精确列名或 display_name，代码只做确定性查找。
    """
    col_set = set(columns)
    dn_to_col: dict[str, str] = {}
    for c in columns:
        dv = str(display_names.get(c, "") or "").strip()
        if dv:
            dn_to_col[dv] = c
    out: list[str] = []
    for t in tokens:
        t = (t or "").strip()
        if not t:
            continue
        if t in col_set:
            out.append(t)
            continue
        if t in dn_to_col:
            out.append(dn_to_col[t])
            continue
        # 列名前缀匹配（如「Inc」→ Inc1,Inc2,Inc3）
        rl = t.lower()
        matched = [c for c in columns if c.lower().startswith(rl)]
        out.extend(matched)
    return list(dict.fromkeys(out))  # 去重保序

def _apply_restrict_analysis_to(
    context: dict[str, Any],
    columns: list[str],
    applied: list[str],
    semantics: list[dict[str, Any]],
    func_args_str: str,
) -> None:
    """处理 LLM 的 restrict_analysis_to 工具调用：机械执行补集排除。

    律 4 落地：LLM 表达「只保留 X、Y、Z」的正向工具。
    LLM 传业务名或列名均可——_resolve_to_column_names 做映射。
    代码只做机械运算（映射 + 集合差 + 字段标记），不涉及任何语义判断。
    """
    import json as _json

    try:
        args = _json.loads(func_args_str) if isinstance(func_args_str, str) else func_args_str
    except (_json.JSONDecodeError, TypeError):
        return

    keep_raw = list(args.get("included_fields") or [])
    if not keep_raw:
        return

    descs: dict[str, Any] = context.get("column_descriptions", {}) or {}
    dnames: dict[str, Any] = context.get("column_display_names", {}) or {}
    resolved = _resolve_to_column_names(keep_raw, columns, dnames, descs)
    if not resolved:
        return

    keep_set: set[str] = set(resolved)

    # 单次遍历：按列名索引 semantics，对每列设置 used_in_analysis（O(N)）
    sem_by_name: dict[str, dict[str, Any]] = {
        str(s.get("column_name", "")): s for s in semantics
    }
    for col in columns:
        s = sem_by_name.get(col)
        if s is None:
            continue
        target = col in keep_set
        s["used_in_analysis"] = target
        s["needs_user_input"] = False
        applied.append(f"{col}:[used_in_analysis]←{'true' if target else 'false'}")

    # 触发重推断信号（律 9）
    context["_pending_reinference"] = True
    applied.append("[signal]_pending_reinference←true")

def _apply_scout_reply_with_llm(
    context: dict[str, Any],
    raw: str,
    columns: list[str],
    llm_client: Any,
    llm_model: str,
    channel_logger: Any = None,
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

    # ── 通道：直传上下文，不做筛选 ─────────────
    query_raw = context.get("query", "") or ""
    project_ctx = context.get("_project_context")

    if project_ctx:
        ctx_block = project_ctx.build_prompt("scout", context)
        messages = [
            {"role": "system", "content": ctx_block["system_prefix"]},
            *ctx_block["messages_history"],
            {"role": "user", "content": raw},
        ]
    else:
        messages = [
            {"role": "system", "content": f"分析目标: {query_raw}"},
            {"role": "user", "content": raw},
        ]

    _raw_text: str = ""
    tool_calls = None  # 初始化，避免异常路径 UnboundLocalError
    try:
        if channel_logger:
            channel_logger.log("scout", "llm_call", model=llm_model, prompt_len=len(system_msg), phase="field_reply")

        # ── LLM dump（诊断用，HAGOKU_DUMP_LLM=1 才生效）──
        from ...observability.llm_dump import dump_messages
        dump_messages(
            "scout_reply_review",
            messages,
            model=llm_model,
            extra={"query": context.get("query", ""), "tools": [t["function"]["name"] for t in _get_scout_tools()]},
        )

        resp = llm_client.chat.completions.create(
            model=llm_model,
            messages=messages,
            temperature=0.1,
            tools=_get_scout_tools(),
            tool_choice="auto",
            max_tokens=8192,
        )

        msg = resp.choices[0].message
        tool_calls = getattr(msg, "tool_calls", None)
        _raw_text = (msg.content or "").strip()

        # ── Response dump ──
        dump_messages(
            "scout_reply_review_response",
            messages + [{"role": "assistant", "content": _raw_text,
             "tool_calls": [{"function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                            for tc in (tool_calls or [])] if tool_calls else None}],
            model=llm_model,
        )

        if channel_logger and tool_calls:
            for tc in (tool_calls or []):
                fn = tc.function.name if hasattr(tc, "function") else str(tc)
                fa = tc.function.arguments if hasattr(tc, "function") else ""
                channel_logger.log("scout", "field_updated", tool=fn, args=fa)

        # ── 追加本轮响应到 session 上下文 ──
        import re as _re2
        _think_match = _re2.search(r"<think>(.*?)</think>", _raw_text or "", _re2.DOTALL)
        if _think_match and channel_logger:
            channel_logger.log("scout", "llm_reasoning", think=_think_match.group(1).strip())
        # 过滤 think 标签，防止泄露到前端
        _raw_text = _re2.sub(r"<think>.*?</think>", "", _raw_text or "", flags=_re2.DOTALL).strip()

        assistant_turn = _raw_text or ""
        if tool_calls and isinstance(tool_calls, list):
            tc_parts = []
            for tc in tool_calls:
                fn = tc.function.name if hasattr(tc, "function") else ""
                fa = tc.function.arguments if hasattr(tc, "function") else "{}"
                tc_parts.append(f"{fn}({fa})")
            assistant_turn = "[调用] " + "; ".join(tc_parts)
            if _raw_text:
                assistant_turn += " " + _raw_text
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

                if func_name == "update_field_table":
                    from ...tools.registry import agent_tools
                    try:
                        args = _json.loads(func_args_str) if isinstance(func_args_str, str) else func_args_str
                    except (_json.JSONDecodeError, TypeError):
                        continue
                    result = agent_tools.dispatch("update_field_table", args, context)
                    applied.extend(result.get("updated", []))
                    continue

                if func_name == "update_field_role":
                    _apply_role_update(context, tool_calls, columns, applied, semantics)
                    continue

                if func_name == "restrict_analysis_to":
                    _apply_restrict_analysis_to(context, columns, applied, semantics, func_args_str)
                    continue

                if func_name == "route_to":
                    try:
                        args = _json.loads(func_args_str) if isinstance(func_args_str, str) else func_args_str
                    except (_json.JSONDecodeError, TypeError):
                        continue
                    context["_scout_route_to"] = {
                        "stage": args.get("stage"),
                        "reason": args.get("reason", ""),
                    }
                    continue

                if func_name != "update_field_understanding":
                    continue

                try:
                    args = _json.loads(func_args_str) if isinstance(func_args_str, str) else func_args_str
                except (_json.JSONDecodeError, TypeError):
                    continue

                col_t = str(args.get("column_name", "")).strip()
                resolved = _resolve_scout_column_token_with_context(col_t, columns, display_names, descs)
                if not resolved:
                    continue

                d_raw = str(args.get("description", "") or "").strip()
                dn_raw = str(args.get("display_name", "") or "").strip()
                role_raw = str(args.get("suggested_role", "") or "").strip()
                uia = args.get("used_in_analysis")
                ev_raw = str(args.get("evidence", "") or "").strip()

                # 对每个解析到的列应用相同的更新（支持范围展开如 Bos1-3）
                for c in resolved:
                    if c in seen_col:
                        continue
                    seen_col.add(c)

                    updated = False
                    if d_raw:
                        descs[c] = d_raw
                        for s in semantics:
                            if str(s.get("column_name", "")) == c:
                                s["description"] = d_raw
                                break
                        applied.append(f"{c}←{d_raw}")
                        updated = True
                    if dn_raw:
                        display_names[c] = dn_raw
                        for s in semantics:
                            if str(s.get("column_name", "")) == c:
                                s["display_name"] = dn_raw
                                break
                        applied.append(f"{c}:[display]←{dn_raw}")
                        updated = True
                    if role_raw and role_raw in ("target", "feature", "identifier", "ignore"):
                        for s in semantics:
                            if str(s.get("column_name", "")) == c:
                                s["suggested_role"] = role_raw
                                s["role"] = role_raw  # 律 5：同步 role
                                applied.append(f"{c}:[role]←{role_raw}")
                                updated = True
                    if uia is not None:
                        for s in semantics:
                            if str(s.get("column_name", "")) == c:
                                s["used_in_analysis"] = bool(uia)
                                applied.append(f"{c}:[used_in_analysis]←{bool(uia)}")
                                updated = True
                    if ev_raw:
                        for s in semantics:
                            if str(s.get("column_name", "")) == c:
                                s["evidence"] = ev_raw
                                break
                    if updated:
                        for s in semantics:
                            if str(s.get("column_name", "")) == c:
                                s["needs_user_input"] = False
                                s["confirmed_by_user"] = True  # 用户自由文本纠正的字段标记为已确认

            # 成功时清除上次的未理解信号
            context.pop("_last_understanding_failure", None)
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

        # ── 律 7：LLM 未产生有效工具调用 → 写入未理解信号 ──
        if raw and not applied:
            context["_last_understanding_failure"] = {
                "raw_text": raw,
                "model_reply_text": _raw_text or "",
                "had_tool_calls": bool(tool_calls),
                "stage": "scout_field_review",
            }
        else:
            context.pop("_last_understanding_failure", None)
        # ── LLM 文本回复原样保留 ──
        if _raw_text and _raw_text.strip():
            context["_last_llm_reply"] = _raw_text.strip()
        return applied

    except Exception as e:
        # 铁律 2（路径 A）：LLM 不可达 / 通道异常 → raise RuntimeError，让用户看见
        # 铁律 7：失败必须对用户可见，不准静默兜底
        context["_last_understanding_failure"] = {
            "raw_text": raw,
            "model_reply_text": _raw_text or "",
            "had_tool_calls": bool(tool_calls) if tool_calls else False,
            "stage": "scout_field_review",
        }
        raise RuntimeError(
            f"Scout 字段理解 LLM 调用失败：{e}\n"
            f"用户输入: {raw[:200]}\n"
            f"请检查 LLM 配置（base_url / api_key / model）是否正确。"
        ) from e
