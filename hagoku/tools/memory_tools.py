"""Memory 三层工具 — 注册到 agent_tools（Phase E CO-E4 ✅）。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from hagoku.memory.lessons import LESSON_RECALL_WARNING, LessonStore
from hagoku.tools.registry import Tool, agent_tools

_METHODS_ROOT = Path(__file__).resolve().parent.parent / "memory" / "methods"


def _project_id(ctx: dict) -> str:
    return str(ctx.get("_project_name") or ctx.get("project_id") or "")


def _memory_manager(ctx: dict):
    mm = ctx.get("_memory_manager")
    if mm is not None:
        return mm
    raise RuntimeError("项目记忆工具需在分析 pipeline 内调用（_memory_manager 未设置）")


def _parse_fm(raw: str) -> dict:
    """解析 YAML frontmatter。支持单行 key: val 和 multi-line list。"""
    if not raw.startswith("---"):
        return {}
    parts = raw.split("---", 2)
    if len(parts) < 3:
        return {}
    result: dict = {}
    lines = parts[1].splitlines()
    current_key: str | None = None
    current_list: list = []
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        # 多行列表项: "  - value"
        if line.startswith("- ") and current_key:
            item = line[2:].strip().strip('"').strip("'")
            current_list.append(item)
            continue
        # 保存上一个 key 的列表
        if current_key and current_list:
            result[current_key] = current_list
            current_key = None
            current_list = []
        # key: value 行
        if ":" in line:
            key, _, val = line.partition(":")
            key = key.strip()
            val = val.strip().strip('"').strip("'")
            if val.startswith("[") and val.endswith("]"):
                # 内联列表: [a, b, c]
                val = [v.strip().strip('"').strip("'") for v in val[1:-1].split(",")]
                result[key] = val
            elif val:
                result[key] = val
            else:
                # 空值 → 可能是多行列表的开始
                current_key = key
                current_list = []
    # 保存最后的列表
    if current_key and current_list:
        result[current_key] = current_list
    return result


def _handle_query_method(args: dict, _ctx: dict, _df: pd.DataFrame | None) -> dict:
    question = str(args.get("question", "") or "").strip()
    scope = args.get("scope")
    if not question:
        return {"error": "question 不能为空"}
    tokens = [t.lower() for t in question.split() if len(t) > 1]
    matches: list[dict] = []
    for md in sorted(_METHODS_ROOT.rglob("*.md")):
        rel = str(md.relative_to(_METHODS_ROOT))
        if scope:
            if not any(str(s).lower() in rel.lower() for s in scope):
                continue
        text = md.read_text(encoding="utf-8")
        blob = text.lower()

        # 匹配全文 token
        if tokens and not any(t in blob for t in tokens):
            continue

        # 解析 frontmatter
        fm = _parse_fm(text)

        # 摘要：优先 frontmatter summary，其次正文首段
        summary = fm.get("summary", "")
        if not summary:
            for line in text.splitlines():
                line = line.strip()
                if line and not line.startswith("#") and not line.startswith("---"):
                    summary = line[:200]
                    break

        matches.append({
            "path": rel,
            "summary": summary or rel,
            "title": fm.get("title", ""),
            "category": fm.get("category", ""),
            "tags": fm.get("tags", []),
        })
    return {"matches": matches[:10], "count": len(matches)}


def _handle_read_method(args: dict, _ctx: dict, _df: pd.DataFrame | None) -> dict:
    path = str(args.get("path", "") or "").strip().lstrip("/")
    if not path:
        return {"error": "path 不能为空"}
    target = (_METHODS_ROOT / path).resolve()
    if not str(target).startswith(str(_METHODS_ROOT.resolve())):
        return {"error": "非法路径"}
    if not target.is_file():
        return {"error": f"方法文档不存在: {path}"}
    raw = target.read_text(encoding="utf-8")
    fm = _parse_fm(raw)
    return {
        "path": path,
        "content": raw,
        "title": fm.get("title", ""),
        "summary": fm.get("summary", ""),
        "category": fm.get("category", ""),
        "tags": fm.get("tags", []),
        "tools": fm.get("tools", []),
    }


def _handle_save_lesson(args: dict, ctx: dict, _df: pd.DataFrame | None) -> dict:
    store = LessonStore()
    try:
        lid = store.save(
            scenario=str(args.get("scenario", "")),
            what_worked=str(args.get("what_worked", "")),
            what_failed=str(args.get("what_failed", "")),
            lesson=str(args.get("lesson", "")),
            conditions_to_recheck=args.get("conditions_to_recheck") or [],
            confidence=str(args.get("confidence", "medium")),
            project_id=_project_id(ctx),
        )
    except ValueError as e:
        return {"error": str(e)}
    # M3补: 每 10 条自动触发 LessonAuditor（计数不含 schema 行）
    count = store.count_lessons()
    if count > 0 and count % 10 == 0:
        from hagoku.agents.lesson_auditor.agent import on_lesson_written
        on_lesson_written(count)
    return {"lesson_id": lid}


def _handle_recall_lessons(args: dict, _ctx: dict, _df: pd.DataFrame | None) -> dict:
    store = LessonStore()
    top_k = int(args.get("top_k", 3))
    lessons = store.recall(str(args.get("context_query", "") or ""), top_k=top_k)
    return {
        "warning": LESSON_RECALL_WARNING,
        "lessons": lessons,
    }


def _handle_correct_lesson(args: dict, _ctx: dict, _df: pd.DataFrame | None) -> dict:
    store = LessonStore()
    try:
        store.correct(
            str(args.get("lesson_id", "")),
            args.get("new_lesson"),
            str(args.get("reason", "")),
        )
    except ValueError as e:
        return {"error": str(e)}
    return {"ok": True}


def _handle_remember_field(args: dict, ctx: dict, _df: pd.DataFrame | None) -> dict:
    from hagoku.memory.projects._manager import ColumnSemanticDef

    mm = _memory_manager(ctx)
    pid = _project_id(ctx)
    if not pid:
        return {"error": "无 project_id"}
    col = str(args.get("column", ""))
    sem = str(args.get("semantics") or args.get("semantic") or "")
    mm.save_column_semantic(
        pid,
        col,
        ColumnSemanticDef(
            semantic=sem,
            display_name=args.get("display_name"),
            description=sem,
            role=args.get("role"),
            confirmed_by_user=bool(args.get("confirmed_by_user", False)),
            source="user" if args.get("confirmed_by_user") else "auto",
        ),
    )
    return {"ok": True, "column": col}


def _handle_query_project_memory(args: dict, ctx: dict, _df: pd.DataFrame | None) -> dict:
    mm = _memory_manager(ctx)
    pid = str(args.get("project_id") or _project_id(ctx))
    if not pid:
        return {"error": "无 project_id"}
    aspect = str(args.get("aspect", "fields"))
    if aspect == "fields":
        return mm.build_memory_project(pid)
    if aspect == "corrections":
        return {"notes": mm.get_user_notes(pid)}
    if aspect == "history":
        return {"patterns": [p.model_dump() for p in mm.get_analysis_patterns(pid)]}
    return {"error": f"未知 aspect: {aspect}"}


def _handle_forget_project(args: dict, ctx: dict, _df: pd.DataFrame | None) -> dict:
    mm = _memory_manager(ctx)
    pid = str(args.get("project_id") or _project_id(ctx))
    if not pid:
        return {"error": "无 project_id"}
    mm.clear_project_memory(pid)
    return {"ok": True, "project_id": pid}


def _register_memory_tools() -> None:
    _common_phase = ["理解字段", "评估清洗", "跑统计", "写报告"]
    specs: list[tuple[str, str, dict, Any, list[str]]] = [
        ("query_method", "查询学术方法知识库，返回相关方法摘要与路径", {
            "type": "object",
            "properties": {
                "question": {"type": "string"},
                "scope": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["question"],
        }, _handle_query_method, _common_phase),
        ("read_method", "读取方法库 markdown 全文，返回 frontmatter 中的 tools 列表方便 LLM 读完后直接调工具", {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        }, _handle_read_method, _common_phase),
        ("save_lesson", "追加一条跨项目成长经验（what_failed 不可为空，无则写 none）", {
            "type": "object",
            "properties": {
                "scenario": {"type": "string"},
                "what_worked": {"type": "string"},
                "what_failed": {"type": "string"},
                "lesson": {"type": "string"},
                "conditions_to_recheck": {"type": "array", "items": {"type": "string"}},
                "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
            },
            "required": ["scenario", "what_worked", "what_failed", "lesson"],
        }, _handle_save_lesson, _common_phase),
        ("recall_lessons", "召回历史成长经验（参考用，不是结论）", {
            "type": "object",
            "properties": {
                "context_query": {"type": "string"},
                "top_k": {"type": "integer"},
            },
            "required": ["context_query"],
        }, _handle_recall_lessons, _common_phase),
        ("correct_lesson", "纠正或废弃一条成长经验", {
            "type": "object",
            "properties": {
                "lesson_id": {"type": "string"},
                "new_lesson": {"type": "string"},
                "reason": {"type": "string"},
            },
            "required": ["lesson_id", "reason"],
        }, _handle_correct_lesson, _common_phase),
        ("remember_field", "写入本项目字段语义记忆", {
            "type": "object",
            "properties": {
                "column": {"type": "string"},
                "display_name": {"type": "string"},
                "semantics": {"type": "string"},
                "role": {"type": "string"},
                "confirmed_by_user": {"type": "boolean"},
            },
            "required": ["column"],
        }, _handle_remember_field, ["理解字段"]),
        ("query_project_memory", "查询本项目记忆（fields/history/corrections）", {
            "type": "object",
            "properties": {
                "project_id": {"type": "string"},
                "aspect": {"type": "string", "enum": ["fields", "history", "corrections"]},
            },
            "required": ["aspect"],
        }, _handle_query_project_memory, _common_phase),
        ("forget_project", "清空本项目记忆（等同 clear-history）", {
            "type": "object",
            "properties": {"project_id": {"type": "string"}},
        }, _handle_forget_project, _common_phase),
    ]
    for name, desc, params, handler, tags in specs:
        agent_tools.register(Tool(
            name=name, description=desc, parameters=params,
            handler=handler, phase_tag=tags,
        ))


_register_memory_tools()
