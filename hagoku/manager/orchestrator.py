"""HaGoKu Manager — 编排器，规则+AI 双驱动"""

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
from ..llm.client import create_deep_client, create_quick_client, create_structured_llm_client
from ..observability.display import TerminalDisplay
from ..observability.event_bus import EventBus
from ..observability.events import EventType
from ..storage.database import HaGoKuDB
from ..storage.memory import MemoryManager
from ..storage.output import OutputManager
from ..storage.project_manager import ProjectManager
from ..tools.data_io import save_data

# ── 规则引擎 ──────────────────────────────────────────────────

PLAN_TEMPLATES: dict[str, dict[str, Any]] = {
    "趋势分析": {
        "agents": ["scout", "cleaner", "analyst", "reporter"],
        "analyst_focus": ["trend", "regression"],
    },
    "差异比较": {
        "agents": ["scout", "cleaner", "analyst", "reporter"],
        "analyst_focus": ["hypothesis_test", "effect_size"],
    },
    "因果推断": {
        "agents": ["scout", "cleaner", "analyst", "reporter"],
        "analyst_focus": ["regression", "causal"],
    },
    "相关性分析": {
        "agents": ["scout", "cleaner", "analyst", "reporter"],
        "analyst_focus": ["correlation"],
    },
    "数据画像": {
        "agents": ["scout", "reporter"],
        "analyst_focus": [],
    },
}

KEYWORD_MAP: dict[str, str] = {
    r"趋势|变化|增长|下降|走势|上升|波动": "趋势分析",
    r"差异|对比|比较|不同|A/B|ab测试|是否不同": "差异比较",
    r"因果|影响|导致|因为|效果|是否有效": "因果推断",
    r"相关|关系|联系|关联|有关": "相关性分析",
    r"画像|概况|什么数据|什么样|描述|概览": "数据画像",
}

# WebSocket「重置 / 取消」暂停时使用的哨兵（用户正常回复不会使用此串）
HAGOKU_CANCEL_PAUSE_TOKEN = "__HAGOKU_CANCEL__"

# Scout 兜底曾生成「列名（统计类型）」——对用户无信息增量，展示前过滤
_SCOUT_TYPE_ECHO_SUFFIXES: tuple[str, ...] = (
    "分类型",
    "数值型",
    "时间型",
    "文本型",
    "布尔型",
    "标识符",
    "未知类型",
)


def _scout_description_is_meaningful_for_user(col: str, desc: str) -> bool:
    """判断 column_descriptions 是否像业务含义；排除「BU（分类型）」式占位。"""
    d = (desc or "").strip()
    c = (col or "").strip()
    if not d or d == c:
        return False
    for suf in _SCOUT_TYPE_ECHO_SUFFIXES:
        for o, cl in (("（", "）"), ("(", ")")):
            if d == f"{c}{o}{suf}{cl}":
                return False
    return True


def _md_table_cell(s: str) -> str:
    """Markdown 表单元格：去换行、转义竖线。"""
    return (s or "").replace("|", "｜").replace("\n", " ").strip()


def _scout_display_name_cell(
    col: str,
    desc: str,
    display_names: dict[str, Any] | None,
) -> str:
    """表格第二列：理解名称（优先 Scout 解析的 column_display_names）。"""
    dmap = display_names if isinstance(display_names, dict) else {}
    v = dmap.get(col)
    if isinstance(v, str) and v.strip():
        return _md_table_cell(v.strip())
    if not desc:
        return "—"
    core = desc.split("（例：", 1)[0].strip()
    for p in ("多为", "常见于"):
        if core.startswith(p):
            core = core[len(p) :].strip()
    short = core.split("。", 1)[0].strip() if core else ""
    if not short:
        short = col
    if len(short) > 14:
        short = short[:12] + "…"
    return _md_table_cell(short)


def scout_field_review_pause_payload(context: dict[str, Any]) -> dict[str, Any]:
    """Scout 暂停：结构化字段表（供前端 HTML 渲染）；`message` 留空，不冒充 Agent 长文。"""
    cols = context.get("column_semantics") or []
    if not cols:
        return {"message": "共 0 列 — 无法生成字段表。", "field_review": None}
    descs = context.get("column_descriptions") or {}
    display_names = context.get("column_display_names") or {}
    n_rows = context.get("n_rows", "?")
    n_c = len(cols)
    noise_prefixes = ("初步推断：", "当前理解：", "系统暂理解为：")
    rows: list[dict[str, Any]] = []
    for s in cols:
        name = str(s.get("column_name", ""))
        d_raw = str(descs.get(name, "") or "").strip()
        d = d_raw if _scout_description_is_meaningful_for_user(name, d_raw) else ""
        for p in noise_prefixes:
            if d.startswith(p):
                d = d[len(p) :].strip()
        uncertain = bool(s.get("needs_user_input"))
        dname = _scout_display_name_cell(name, d, display_names)
        if len(d) > 400:
            d = d[:397] + "…"
        mean = d if d else "（待补充）"
        rows.append({
            "field_name": name,
            "understanding_name": dname,
            "meaning": mean,
            "needs_attention": uncertain,
        })
    return {
        "message": "",
        "field_review": {
            "n_rows": n_rows,
            "n_cols": n_c,
            "rows": rows,
        },
    }


# 用户仅表示「确认」、无字段纠错时，不写 column_descriptions、不污染 query 补充段
_SCOUT_PURE_CONFIRM_RE = re.compile(
    r"^(确认(?:无误|进清洗|继续)?|好的|是|没问题|对的|正确|已通过|pass|ok|okay|yes|y|thanks|thx)[\s!！。,\-\.]*$",
    re.I,
)


def _scout_reply_is_pure_confirm(user_reply: str) -> bool:
    t = (user_reply or "").strip()
    if not t:
        return False
    return bool(_SCOUT_PURE_CONFIRM_RE.match(t))


def _is_scout_aligned(context: dict[str, Any], user_reply: str) -> bool:
    """判断 Scout 字段理解是否已对齐：纯确认  OR  所有字段 needs_user_input=False。"""
    if _scout_reply_is_pure_confirm(user_reply):
        return True
    if not any(s.get("needs_user_input") for s in context.get("column_semantics", [])):
        return True
    return False


def gate_cleaning_pause_payload() -> dict[str, Any]:
    """跨阶段闸门：字段对齐后、进入清洗前，询问用户是否确认进入清洗阶段。"""
    return {
        "message": "",
        "gate": {
            "phase": "cleaning",
            "prompt": "字段理解已确认。是否进入数据清洗？",
        },
    }


# 闸门回复判定：显式纯确认 → 进下一阶段；空字串不视为确认；非确认 → 回 FieldReviewLoop
_GATE_SUPPLEMENT_RE = re.compile(
    r"补充|还有|改|不对|不对的|纠正|修正|更正|重新|再想想|再看看",
    re.I,
)


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


def _parse_scout_field_assignments(line: str) -> tuple[str | None, str | None]:
    """`Code=店铺`、`Code：店铺`、`Code: 店铺`（全角半角）。"""
    m = re.match(r"^\s*([^\s=:=：]+?)\s*[=＝:：]\s*(.+)\s*$", line)
    if not m:
        return None, None
    return m.group(1).strip(), m.group(2).strip()


def _parse_scout_means_clauses(text: str) -> list[tuple[str, str]]:
    """`code means store number`、一行内多个 `A means x, B means y`。"""
    out: list[tuple[str, str]] = []
    for m in re.finditer(r"(?i)\b([a-z0-9_]+)\s+means\s+([^,;，；\n]+)", text):
        col_t = m.group(1).strip()
        mean = m.group(2).strip().rstrip(".,;，；")
        if col_t and mean:
            out.append((col_t, mean))
    return out


def _parse_scout_column_prefixed_line(line: str, columns: list[str]) -> tuple[str | None, str | None]:
    """`Code是店铺编号`、`Code 表示 周`、`Code means x`（列名在句首，且列为真实列名）。"""
    s = line.strip()
    if not s:
        return None, None
    for col in sorted(set(columns), key=len, reverse=True):
        if len(s) < len(col) + 1:
            continue
        if s[: len(col)].lower() != col.lower():
            continue
        tail = s[len(col) :].strip()
        if not tail:
            return None, None
        m = re.match(
            r"(?is)^(means|is|are|[:=：]|是|就是|为|表示|指的是|意为)\s*(.+)$",
            tail,
        )
        if not m:
            continue
        mean = (m.group(2) or "").strip().rstrip(".,;，；")
        if mean:
            return col, mean
    return None, None


def apply_scout_user_field_reply_to_context(context: dict[str, Any], user_reply: str) -> list[str]:
    """
    将用户在 Scout 字段核对暂停点的说明写入 context（column_descriptions、needs_user_input）。

    不调 LLM：结构化行（Col=…）+ 常见英文 means / 句首列名 + 中文「是/表示」。
    返回简短人类可读记录（如 ``Code←店铺编号``），供事件或日志；无写入则返回 []。
    """
    raw = (user_reply or "").strip()
    if not raw or _scout_reply_is_pure_confirm(raw):
        return []

    columns = _known_scout_columns(context)
    if not columns:
        return []

    descs: dict[str, Any] = context.setdefault("column_descriptions", {})
    applied: list[str] = []
    seen_col: set[str] = set()

    def _apply_one(canonical: str, meaning: str) -> None:
        if not canonical or not meaning or canonical in seen_col:
            return
        seen_col.add(canonical)
        descs[canonical] = meaning
        for s in context.get("column_semantics") or []:
            if str(s.get("column_name", "")) == canonical:
                s["needs_user_input"] = False
        applied.append(f"{canonical}←{meaning}")

    lines = [ln.strip() for ln in raw.splitlines() if ln.strip()]
    if not lines:
        lines = [raw]

    for line in lines:
        handled = False
        lt, rt = _parse_scout_field_assignments(line)
        if lt and rt:
            c = _resolve_scout_column_token(lt, columns)
            if c:
                _apply_one(c, rt)
                handled = True
        if handled:
            continue
        pc, pm = _parse_scout_column_prefixed_line(line, columns)
        if pc and pm:
            _apply_one(pc, pm)
            continue
        for col_t, mean in _parse_scout_means_clauses(line):
            c = _resolve_scout_column_token(col_t, columns)
            if c:
                _apply_one(c, mean)

    return applied


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


class RuleEngine:
    """Manager 的规则引擎，覆盖 80% 常见决策"""

    def match_plan(self, query: str) -> dict[str, Any] | None:
        """关键词匹配计划模板"""
        for pattern, plan_name in KEYWORD_MAP.items():
            if re.search(pattern, query):
                return {**PLAN_TEMPLATES[plan_name], "plan_name": plan_name}
        return None


# ── 编排器 ────────────────────────────────────────────────────


class Orchestrator:
    """HaGoKu 编排器：规则+AI 双驱动，协调四个 Agent"""

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

        # 规则引擎
        self.rule_engine = RuleEngine()

        # 护栏
        self.guardrails = StatisticalGuardrails()

        # LLM 客户端（懒初始化，pure_rule 模式永远不会触发）
        self._llm_client: Any | None = None
        self._llm_deep: Any | None = None  # 深度推理客户端（懒初始化）
        self._llm_quick: Any | None = None  # 快速客户端（懒初始化）

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
        """快速客户端（懒初始化）"""
        if self._llm_quick is None:
            self._llm_quick = create_quick_client(self.config)
        return self._llm_quick

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

    def _generate_pause_message(self, agent: str, results: dict[str, Any]) -> str:
        """
        遗留路径：用 llm_quick 生成暂停说明；失败则规则回退。
        Scout / Cleaner / Analyst 主线暂停均使用结构化载荷（`scout_field_review_pause_payload`、
        `cleaning_review_pause_payload`、`analyst_review_pause_payload`），不在此生成面向用户的整段「台词」。
        """
        try:
            from openai import OpenAI
            client = OpenAI(
                base_url=self.config.llm.base_url,
                api_key=self.config.llm.api_key,
            )
            context_str = self._format_results_for_prompt(agent, results)
            system_content = (
                "你是 HaGoKu 数据分析助手中的一个 Agent。"
                "你的工作刚刚完成了一个阶段，现在需要向用户汇报发现，并询问是否继续。"
                "要求：语言简洁友好，不超过 5 句话，最后一句是一个具体的确认或引导性问题。"
                "不要使用 Markdown 标题，可以用短破折号列举要点。"
            )
            resp = client.chat.completions.create(
                model=self.config.llm.model_quick or self.config.llm.model,
                messages=[
                    {"role": "system", "content": system_content},
                    {"role": "user", "content": context_str},
                ],
                max_tokens=300,
                temperature=0.3,
            )
            body = resp.choices[0].message.content.strip()
        except Exception:
            body = self._fallback_pause_message(agent, results)
        return body

    def _format_results_for_prompt(self, agent: str, results: dict[str, Any]) -> str:
        """将 agent 结果格式化为 LLM prompt 的输入文本。"""
        if agent == "scout":
            cols = results.get("column_semantics", [])
            n_rows = results.get("n_rows", "?")
            n_cols = results.get("n_cols", len(cols))
            uncertain = [c["column_name"] for c in cols if c.get("needs_user_input")]
            per_col = []
            for c in cols:
                nm = c.get("column_name", "")
                role = c.get("suggested_role") or c.get("semantic_type") or "—"
                per_col.append(
                    f"  - {nm}: inferred_type={c.get('inferred_type')} role={role} "
                    f"needs_user_input={bool(c.get('needs_user_input'))} evidence={c.get('evidence', '')}"
                )
            col_block = "\n".join(per_col) if per_col else "（无列）"
            return (
                f"我是 Scout Agent，刚刚分析了数据集（{n_rows} 行 × {n_cols} 列）。\n"
                f"逐列推断如下：\n{col_block}\n"
                f"需要用户重点确认的列名：{uncertain if uncertain else '（无，均已高置信自动识别）'}\n"
                "请写**最多 2 句**日常中文开场：只表达「已读完、请看下方各列」即可。"
                "不要数据类型、统计角色、置信度、依据；不要复述清单也不要写「逐项核对下表」类话术（清单另附）。"
            )
        elif agent == "cleaner":
            ops = results.get("operations", [])
            norm_ops = [_normalize_cleaning_operation(op) for op in ops]
            quality = results.get("data_quality", "unknown")
            impact = results.get("impact_rate", 0)
            return (
                f"我是 Cleaner Agent，刚刚检测了数据质量。\n"
                f"数据质量评级：{quality}，清洗影响率：{impact:.1%}\n"
                f"计划执行的清洗操作（共 {len(norm_ops)} 个）：{[op.get('reason', '') for op in norm_ops[:5]]}\n"
                f"请向用户简要说明清洗计划，并询问是否可以继续执行。"
            )
        elif agent == "analyst":
            findings = results.get("findings", results.get("results", []))
            n = len(findings) if isinstance(findings, list) else 0
            sig = [f for f in (findings if isinstance(findings, list) else []) if f.get("significance") == "significant"]
            return (
                f"我是 Analyst Agent，刚刚完成了统计分析。\n"
                f"共找到 {n} 个分析结果，其中 {len(sig)} 个统计显著。\n"
                f"主要发现摘要：{[f.get('question', '') for f in sig[:3]]}\n"
                f"请向用户汇报核心发现，并询问他们想深入了解哪个方向，或者是否可以生成报告。"
            )
        return f"我是 {agent} Agent，刚刚完成了工作。请告诉用户进度并询问是否继续。"

    def _fallback_pause_message(self, agent: str, results: dict[str, Any]) -> str:
        """LLM 不可用时的规则拼接回退消息。"""
        if agent == "scout":
            cols = results.get("column_semantics", [])
            n_rows = results.get("n_rows", "?")
            return f"共 {n_rows} 行 × {len(cols)} 列 — 请确认字段业务含义；无误回「确认」。"
        elif agent == "cleaner":
            ops = results.get("operations", [])
            n = len([_normalize_cleaning_operation(o) for o in ops])
            return f"清洗阶段：共 {n} 条操作已记录，请查看结构化摘要并回复。"
        elif agent == "analyst":
            return "统计分析完成，已找到若干发现。可以生成完整报告了吗？"
        return f"{agent} 完成，是否继续？"

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
            "thought": f"🔍 理解你的问题：{self._describe_intent(parsed_intent)}",
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
            scout = ScoutAgent(self.config.llm, self.event_bus, llm_client=self.llm_quick, scribe=self.scribe)
            ir = scout.begin(data_path=data_path, query=query, project_id=project_name)
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
            quality_labels = {"good": "数据质量良好", "medium": "数据质量一般", "poor": "数据质量问题较多"}
            if operations:
                llm_message = f"数据质量：{quality_labels.get(quality, quality)}。我计划执行 {len(operations)} 个清洗操作："
                for op in operations[:6]:
                    col = op.get("column", "")
                    reason = op.get("reason", "")
                    llm_message += f"\n• **{col}**：{reason[:50]}{'...' if len(reason) > 50 else ''}"
                if len(operations) > 6:
                    llm_message += f"\n... 还有 {len(operations) - 6} 个操作"
                llm_message += "\n\n这个清洗方案可以吗？或者你想调整某个处理方式？"
            else:
                llm_message = f"数据质量：{quality_labels.get(quality, quality)}。未检测到需要清洗的问题，数据可以直接分析。这个清洗方案可以吗？或者你想做其他特殊处理？"
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
                df_clean, cleaning_report, _ = cleaner.run(
                    data_path, context,
                    user_operations=cleaning_operations,
                    impact_warning=self.config.manager.cleaning_impact_warning,
                    phase="full",
                )
            else:
                # 未确认 → 只返回策略供用户确认
                cleaner_result: tuple[Any, Any, Any] = cleaner.run(
                    data_path, context,
                    user_operations=cleaning_operations,
                    impact_warning=self.config.manager.cleaning_impact_warning,
                    phase="strategy_only",
                )
                if isinstance(cleaner_result, tuple) and len(cleaner_result) == 3:
                    _, _, strategy_dict = cleaner_result
                    if isinstance(strategy_dict, dict):
                        # 用户未确认操作，用自动规划的执行
                        auto_ops = strategy_dict.get("operations", [])
                        df_clean, cleaning_report, _ = cleaner.run(
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
                llm_lines = []
                if power_warnings:
                    llm_lines.append(f"⚡ {power_warnings[0]}")
                if findings:
                    llm_lines.append(f"初步找到了 {len(findings)} 个分析方向：")
                    for f in findings[:5]:
                        sig = "✅ 显著" if f.get("significance") == "significant" else "⚪ 不显著"
                        q = f.get("question", "")
                        p = f.get("p_value")
                        p_str = f"（p={p:.4f}）" if p is not None else ""
                        llm_lines.append(f"• {sig} {p_str}：{q}")
                else:
                    llm_lines.append("初步分析没有发现明显的统计规律。")
                if suggested:
                    llm_lines.append(f"💡 {suggested}")
                llm_lines.append("\n你想重点关注哪个方向？或者有其他想看的维度？")
                llm_message = "\n".join(llm_lines)
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
                context = scout.run(
                    data_path, query, project_id=project_name, emit_completed=False
                )
                if context.get("error"):
                    raise RuntimeError(str(context["error"]))

                if self._is_cancel_requested():
                    return self._finish_run_cancelled(run_id, project_name, run_start, run_dir)

                # ── 多轮对齐：Scout 字段理解子状态机 ───────────────────────────────
                # 结构：外层循环（Scout 循环 + gate）；内层 Scout 循环负责字段对齐
                # 对齐条件：用户纯确认  OR  所有字段 needs_user_input=False
                # 对齐后发 gate_to_cleaning 暂停；用户「还有补充」→ 回 Scout 循环；纯确认 → 进 Cleaner
                interaction_revision = 0
                while True:
                    # 内层：Scout 字段对齐循环
                    while True:
                        scout_msg = scout_field_review_pause_payload(context)
                        scout_msg["interaction_revision"] = interaction_revision
                        user_reply_scout = self._pause_and_wait("scout", scout_msg)
                        if user_reply_scout == HAGOKU_CANCEL_PAUSE_TOKEN:
                            return self._finish_run_cancelled(run_id, project_name, run_start, run_dir)
                        applied_scout = apply_scout_user_field_reply_to_context(context, user_reply_scout or "")
                        if user_reply_scout:
                            self.event_bus.emit(EventType.USER_INPUT_RECEIVED, "scout", {
                                "reply": user_reply_scout,
                                "applied_field_updates": applied_scout,
                                "interaction_revision": interaction_revision,
                            })
                            if not _scout_reply_is_pure_confirm(user_reply_scout):
                                query = f"{query}\n[用户补充] {user_reply_scout}".strip()
                        # 对齐判定：已对齐则出内层循环、进 gate；未对齐则继续内层（revision 递增）
                        if _is_scout_aligned(context, user_reply_scout):
                            break
                        interaction_revision += 1

                    # ── 跨阶段闸门：字段对齐后、进入清洗前 ────────────────────────
                    gate_msg = gate_cleaning_pause_payload()
                    gate_reply = self._pause_and_wait("scout", gate_msg)
                    if gate_reply == HAGOKU_CANCEL_PAUSE_TOKEN:
                        return self._finish_run_cancelled(run_id, project_name, run_start, run_dir)
                    if _is_gate_confirm(gate_reply):
                        # 确认进清洗 → 出外层循环，继续执行 Cleaner
                        break
                    # 「还有补充」→ 回 Scout 内层循环（context 已含上次纠错，revision 继续递增）

                n_sem = len(context.get("column_semantics", []))
                self.event_bus.emit(
                    EventType.AGENT_COMPLETED,
                    "scout",
                    {"result_summary": f"理解 {n_sem} 个字段（用户已确认）"},
                )

                # 4. Cleaner: 数据清洗
                df_clean, cleaning_report, _ = cleaner.run(
                    data_path, context,
                    impact_warning=self.config.manager.cleaning_impact_warning,
                    emit_completed=False,
                )

                if self._is_cancel_requested():
                    return self._finish_run_cancelled(run_id, project_name, run_start, run_dir)

                # ── 暂停：清洗结果待用户确认后再记 Cleaner 完成 ──
                cleaner_results = {
                    "operations": cleaning_report.operations if cleaning_report else [],
                    "data_quality": getattr(cleaning_report, "data_quality", "unknown"),
                    "impact_rate": cleaning_report.impact_rate if cleaning_report else 0,
                }
                cleaner_msg = cleaning_review_pause_payload(
                    cleaning_report,
                    data_quality=str(cleaner_results["data_quality"]),
                    impact_rate=float(cleaner_results["impact_rate"] or 0.0),
                )
                user_reply_cleaner = self._pause_and_wait("cleaner", cleaner_msg)
                if user_reply_cleaner == HAGOKU_CANCEL_PAUSE_TOKEN:
                    return self._finish_run_cancelled(run_id, project_name, run_start, run_dir)
                if user_reply_cleaner:
                    self.event_bus.emit(EventType.USER_INPUT_RECEIVED, "cleaner", {
                        "reply": user_reply_cleaner,
                    })
                    query = f"{query}\n[用户补充] {user_reply_cleaner}".strip()
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
                else:
                    cleaned_path_str = ""
                    self.event_bus.emit(EventType.QUALITY_CHECK, "manager", {
                        "verdict": "warning",
                        "detail": "数据清洗未成功，尝试使用原始数据",
                    })

                # 保存 resume 状态
                self.memory.save_resume_state(
                    project_name, "cleaned",
                    cleaned_path=cleaned_path_str,
                    context=context, run_id=run_id,
                )

                # 5. 质量检查
                if cleaning_report:
                    self.event_bus.emit(EventType.QUALITY_CHECK, "manager", {
                        "verdict": "pass" if cleaning_report.impact_rate < self.config.manager.cleaning_impact_warning else "warning",
                        "detail": f"清洗影响率 {cleaning_report.impact_rate:.1%}",
                    })

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

            # ── 暂停：分析结果待用户确认后再记 Analyst 完成 ──
            analyst_pause = analyst_review_pause_payload(
                results if isinstance(results, list) else [],
            )
            user_reply_analyst = self._pause_and_wait("analyst", analyst_pause)
            if user_reply_analyst == HAGOKU_CANCEL_PAUSE_TOKEN:
                return self._finish_run_cancelled(run_id, project_name, run_start, run_dir)
            if user_reply_analyst:
                self.event_bus.emit(EventType.USER_INPUT_RECEIVED, "analyst", {
                    "reply": user_reply_analyst,
                })
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
        """
        创建分析计划：规则优先匹配，AI 辅助微调
        """
        rule_plan = self.rule_engine.match_plan(query)

        if rule_plan:
            # 规则匹配成功，AI 做微调
            llm_plan = self._create_plan_hybrid(query, rule_plan, parsed_intent=parsed_intent)
            if llm_plan is not None:
                llm_plan["rule_match"] = True
                return llm_plan
            rule_plan["rule_match"] = True
            if parsed_intent and parsed_intent.target:
                rule_plan["target"] = parsed_intent.target
            return rule_plan

        # 无匹配规则，AI 生成
        new_plan: dict[str, Any] | None = self._create_plan_llm(query, rule_plan, parsed_intent=parsed_intent)
        if new_plan is not None:
            return new_plan
        plan = self._generic_plan(query)
        if parsed_intent and parsed_intent.target:
            plan["target"] = parsed_intent.target
        return plan

    def _generic_plan(self, query: str) -> dict[str, Any]:
        """返回通用分析计划（探索性分析）"""
        return {
            "plan_name": "通用分析",
            "agents": ["scout", "cleaner", "analyst", "reporter"],
            "analyst_focus": ["regression", "hypothesis_test", "correlation"],
            "query": query,
            "rule_match": False,
        }

    def _create_plan_hybrid(
        self,
        query: str,
        rule_plan: dict[str, Any],
        parsed_intent: Any | None = None,
    ) -> dict[str, Any]:
        """混合模式：规则计划为基础，LLM 调整优化"""
        llm_plan = self._call_llm_for_plan(
            query=query,
            rule_plan=rule_plan,
            mode="adjust",
            parsed_intent=parsed_intent,
        )
        if llm_plan is not None:
            llm_plan["rule_match"] = True
            llm_plan["llm_adjusted"] = True
            self.event_bus.emit(EventType.PLAN_ADJUSTED, "manager", {
                "original": rule_plan.get("plan_name"),
                "adjusted": llm_plan.get("plan_name"),
                "reasoning": llm_plan.get("reasoning", ""),
            })
            return llm_plan
        # LLM 失败，返回规则计划不变
        rule_plan["rule_match"] = True
        return rule_plan

    def _create_plan_llm(
        self,
        query: str,
        rule_plan: dict[str, Any] | None = None,
        parsed_intent: Any | None = None,
    ) -> dict[str, Any] | None:
        """LLM 从零生成分析计划（rule_plan 可作为参考 hint）"""
        llm_plan = self._call_llm_for_plan(
            query=query,
            rule_plan=rule_plan,
            mode="generate",
            parsed_intent=parsed_intent,
        )
        if llm_plan is not None:
            llm_plan["rule_match"] = rule_plan is not None
            llm_plan["llm_generated"] = True
            self.event_bus.emit(EventType.PLAN_CREATED, "manager", {
                "source": "llm",
                "plan_name": llm_plan.get("plan_name"),
                "reasoning": llm_plan.get("reasoning", ""),
            })
            return llm_plan
        return None

    def _call_llm_for_plan(
        self,
        query: str,
        rule_plan: dict[str, Any] | None = None,
        mode: str = "generate",
        parsed_intent: Any | None = None,
    ) -> dict[str, Any] | None:
        """
        调用 LLM 生成或调整分析计划

        Args:
            query: 用户分析问题
            rule_plan: 规则引擎输出（混合模式下作为上下文）
            mode: "generate"（从零生成）或 "adjust"（调整规则计划）

        Returns:
            计划 dict，LLM 失败时返回 None
        """
        from ..llm.plan_schema import (
            DEFAULT_EXPLORATORY_FOCUS,
            VALID_ANALYST_FOCUS,
            LLMPlanResponse,
        )
        from ..llm.prompts import PLAN_ADJUSTMENT_USER, PLAN_GENERATION_SYSTEM, PLAN_GENERATION_USER

        try:
            # 懒初始化 LLM 客户端
            if self._llm_client is None:
                self._llm_client = create_structured_llm_client(self.config.llm)

            # 构建消息
            messages = [{"role": "system", "content": PLAN_GENERATION_SYSTEM}]

            # 基于解析意图构建更丰富的用户查询上下文
            intent_context = self._build_intent_context(query, parsed_intent)

            if mode == "adjust" and rule_plan:
                user_content = PLAN_ADJUSTMENT_USER.format(
                    query=intent_context,
                    plan_name=rule_plan.get("plan_name", ""),
                    agents=", ".join(rule_plan.get("agents", [])),
                    analyst_focus=", ".join(rule_plan.get("analyst_focus", [])),
                    target=rule_plan.get("target") or "null",
                )
            else:
                user_content = PLAN_GENERATION_USER.format(query=intent_context)

            messages.append({"role": "user", "content": user_content})

            # 通过 instructor 获取结构化输出
            response: LLMPlanResponse = self._llm_client.chat.completions.create(
                model=self.config.llm.model,
                messages=messages,
                response_model=LLMPlanResponse,
                temperature=self.config.llm.temperature,
                max_tokens=self.config.llm.max_tokens,
                timeout=30,
            )

            # 服务端二次校验 analyst_focus
            validated_focus = [f for f in response.analyst_focus if f in VALID_ANALYST_FOCUS]
            if not validated_focus:
                validated_focus = DEFAULT_EXPLORATORY_FOCUS.copy()

            # 确保 agents 包含 scout 和 reporter
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
            }
            return plan

        except Exception as e:
            self.event_bus.emit(EventType.AGENT_THINKING, "manager", {
                "thought": f"LLM 计划生成失败: {e}",
            })
            return None

    def _parse_user_query(self, query: str) -> Any:
        """解析用户查询为结构化意图"""
        try:
            from .query_parser import parse_query
            return parse_query(query)
        except Exception:
            return None

    def _describe_intent(self, parsed_intent: Any) -> str:
        """将解析后的意图翻译成用户能理解的话"""
        if parsed_intent is None:
            return "探索这份数据有什么规律"

        intent_names = {
            "comparison": "对比不同组之间的差异",
            "causation": "找某个结果的原因",
            "correlation": "找变量之间的关系",
            "trend": "看某个指标随时间的变化趋势",
            "diagnostic": "诊断数据中的问题",
            "exploration": "探索数据有什么规律",
        }

        parts = []
        intent_name = intent_names.get(parsed_intent.intent_type, "探索数据")
        parts.append(intent_name)

        if parsed_intent.target:
            parts.append(f"，关注「{parsed_intent.target}」")

        if parsed_intent.time_range:
            parts.append(f"，时间范围「{parsed_intent.time_range}」")

        if parsed_intent.group_by:
            parts.append(f"，按「{'/'.join(parsed_intent.group_by)}」分组")

        return "".join(parts)

    def _build_intent_context(self, query: str, parsed_intent: Any) -> str:
        """将解析后的意图构建成 LLM 可用的上下文"""
        if parsed_intent is None:
            return query

        parts = [query]

        if parsed_intent.intent_type != "exploration":
            intent_labels = {
                "comparison": "用户想对比不同组的差异",
                "causation": "用户想找原因",
                "correlation": "用户想知道变量之间的关系",
                "trend": "用户想看变化趋势",
                "diagnostic": "用户想诊断问题",
            }
            if parsed_intent.intent_type in intent_labels:
                parts.append(f"\n【意图】：{intent_labels[parsed_intent.intent_type]}")

        if parsed_intent.target:
            parts.append(f"\n【目标变量】：{parsed_intent.target}")

        if parsed_intent.time_range:
            parts.append(f"\n【时间范围】：{parsed_intent.time_range}")

        if parsed_intent.group_by:
            parts.append(f"\n【分组维度】：{'、'.join(parsed_intent.group_by)}")

        if parsed_intent.filters:
            parts.append(f"\n【筛选条件】：{parsed_intent.filters}")

        return "".join(parts)

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
