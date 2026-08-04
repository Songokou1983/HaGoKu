"""Memory 三层工具 — 注册到 agent_tools（Phase E CO-E4 ✅）。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

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


def _handle_save_lesson(args: dict, ctx: dict, _df: pd.DataFrame | None) -> dict:
    store = LessonStore()
    wf = str(args.get("what_failed", "") or "").strip()
    try:
        lid = store.save(
            scenario=str(args.get("scenario", "")),
            what_worked=str(args.get("what_worked", "")),
            what_failed=wf,
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


def _register_memory_tools() -> None:
    _common_phase = ["理解字段", "评估清洗", "跑统计", "写报告"]
    specs: list[tuple[str, str, dict, Any, list[str]]] = [
        ("save_lesson", "追加一条跨项目成长经验。what_failed 可选，填 none 表示无失败经验", {
            "type": "object",
            "properties": {
                "scenario": {"type": "string"},
                "what_worked": {"type": "string"},
                "what_failed": {"type": "string", "description": "失败经验，无则填 none"},
                "lesson": {"type": "string"},
                "conditions_to_recheck": {"type": "array", "items": {"type": "string"}},
                "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
            },
            "required": ["scenario", "what_worked", "lesson"],
        }, _handle_save_lesson, _common_phase),
        ("recall_lessons", "召回历史成长经验（参考用，不是结论）", {
            "type": "object",
            "properties": {
                "context_query": {"type": "string"},
                "top_k": {"type": "integer"},
            },
            "required": ["context_query"],
        }, _handle_recall_lessons, _common_phase),
        ("query_project_memory", "查询本项目记忆（fields/history/corrections）", {
            "type": "object",
            "properties": {
                "project_id": {"type": "string"},
                "aspect": {"type": "string", "enum": ["fields", "history", "corrections"]},
            },
            "required": ["aspect"],
        }, _handle_query_project_memory, _common_phase),
    ]
    for name, desc, params, handler, tags in specs:
        agent_tools.register(Tool(
            name=name, description=desc, parameters=params,
            handler=handler, phase_tag=tags,
        ))


_register_memory_tools()
