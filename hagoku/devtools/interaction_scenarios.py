"""互动场景夹具：加载 / 校验面向 WebSocket 前端的事件序列。

用于把「用户在分析页会看到什么」写成可执行、可回归的剧本，
避免只靠口头描述或临时抓包。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def default_fixtures_dir() -> Path:
    return Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "interaction_scenarios"


def load_scenario(path: Path) -> dict[str, Any]:
    with open(path, encoding="utf-8") as f:
        doc = json.load(f)
    if not isinstance(doc, dict):
        raise ValueError(f"{path}: root must be an object")
    return doc


def iter_scenario_files(directory: Path | None = None) -> list[Path]:
    root = directory or default_fixtures_dir()
    if not root.is_dir():
        return []
    return sorted(root.glob("*.json"))


def validate_scenario_document(doc: dict[str, Any], *, source: str = "") -> list[str]:
    """返回人类可读错误列表；空列表表示通过。"""
    errs: list[str] = []
    prefix = f"{source}: " if source else ""

    sid = doc.get("id")
    if not isinstance(sid, str) or not sid.strip():
        errs.append(f"{prefix}missing non-empty string field 'id'")

    steps = doc.get("steps")
    if not isinstance(steps, list) or len(steps) == 0:
        errs.append(f"{prefix}field 'steps' must be a non-empty array")
        return errs

    for i, step in enumerate(steps):
        sp = f"{prefix}steps[{i}]"
        if not isinstance(step, dict):
            errs.append(f"{sp} must be an object")
            continue
        note = step.get("note")
        if not isinstance(note, str) or not note.strip():
            errs.append(f"{sp}.note must be a non-empty string (human narration for authors)")
        ws = step.get("ws")
        if ws is None:
            continue
        if not isinstance(ws, dict):
            errs.append(f"{sp}.ws must be an object or null")
            continue
        if ws.get("type") != "event":
            errs.append(f"{sp}.ws.type must be 'event'")
            continue
        outer = ws.get("data")
        if not isinstance(outer, dict):
            errs.append(f"{sp}.ws.data must be an object (Event.to_dict envelope)")
            continue
        for k in ("event_id", "event_type", "timestamp", "agent", "data"):
            if k not in outer:
                errs.append(f"{sp}.ws.data missing key '{k}'")
        inner = outer.get("data")
        if not isinstance(inner, dict):
            errs.append(f"{sp}.ws.data.data must be an object")
            continue

        et = outer.get("event_type")
        ag = outer.get("agent")
        if et == "user_input_requested":
            if not isinstance(ag, str) or not ag:
                errs.append(f"{sp}: user_input_requested needs string agent")
                continue
            fr = inner.get("field_review")
            cr = inner.get("cleaning_review")
            ar = inner.get("analyst_review")
            n_struct = sum(1 for x in (fr, cr, ar) if x is not None)
            if n_struct != 1:
                errs.append(
                    f"{sp}: user_input_requested must have exactly one of "
                    f"field_review / cleaning_review / analyst_review (got {n_struct})",
                )
                continue
            if fr is not None:
                if ag != "scout":
                    errs.append(f"{sp}: field_review pause expects agent 'scout', got {ag!r}")
                if not isinstance(fr, dict) or not isinstance(fr.get("rows"), list):
                    errs.append(f"{sp}: field_review must be object with 'rows' array")
            if cr is not None:
                if ag != "cleaner":
                    errs.append(f"{sp}: cleaning_review pause expects agent 'cleaner', got {ag!r}")
                if not isinstance(cr, dict) or not isinstance(cr.get("rows"), list):
                    errs.append(f"{sp}: cleaning_review must be object with 'rows' array")
            if ar is not None:
                if ag != "analyst":
                    errs.append(f"{sp}: analyst_review pause expects agent 'analyst', got {ag!r}")
                if not isinstance(ar, dict) or not isinstance(ar.get("rows"), list):
                    errs.append(f"{sp}: analyst_review must be object with 'rows' array")

    return errs


def format_scenario_script(doc: dict[str, Any]) -> str:
    """把剧本打印成可拿去评审 / 对需求的一页纸。"""
    lines: list[str] = []
    title = doc.get("title")
    sid = doc.get("id", "?")
    lines.append(f"# 互动场景：{title or sid}")
    lines.append("")
    steps = doc.get("steps", [])
    if not isinstance(steps, list):
        return "\n".join(lines)
    for i, step in enumerate(steps):
        if not isinstance(step, dict):
            continue
        note = step.get("note", "").strip()
        gap = step.get("gap")
        ws = step.get("ws")
        et = None
        if isinstance(ws, dict) and isinstance(ws.get("data"), dict):
            et = ws["data"].get("event_type")
        head = f"{i + 1}. " + (f"[{et}] " if et else "")
        lines.append(head + note)
        if isinstance(gap, str) and gap.strip():
            lines.append(f"   **缺口 / 目标态**: {gap.strip()}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"
