"""Phase E: 成长记忆 lessons.jsonl 契约测试."""

import json
import tempfile
from pathlib import Path

import pytest

from hagoku.memory.lessons import LESSON_RECALL_WARNING, LessonStore
from hagoku.tools.memory_tools import _handle_recall_lessons, _handle_save_lesson


def test_save_lesson_rejects_empty_what_failed():
    store = LessonStore(path=Path(tempfile.mktemp()))
    with pytest.raises(ValueError, match="what_failed"):
        store.save(
            scenario="s", what_worked="w", what_failed="  ",
            lesson="l",
        )


def test_save_lesson_tool_rejects_empty_what_failed():
    out = _handle_save_lesson(
        {"scenario": "s", "what_worked": "w", "what_failed": "", "lesson": "l"},
        {}, None,
    )
    assert "error" in out


def test_recall_lessons_store_finds_match():
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "lessons.jsonl"
        store = LessonStore(path=path)
        store.save(
            scenario="小样本 ROI",
            what_worked="Mann-Whitney",
            what_failed="t 检验方差不稳",
            lesson="n<10 用非参",
            conditions_to_recheck=["n<10"],
        )
        hits = store.recall("小样本 ROI")
    assert len(hits) >= 1


def test_recall_lessons_tool_includes_warning():
    out = _handle_recall_lessons({"context_query": "任意"}, {}, None)
    assert out["warning"] == LESSON_RECALL_WARNING
    assert "参考用不是结论" in out["warning"]


def test_lessons_jsonl_append_only():
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "lessons.jsonl"
        store = LessonStore(path=path)
        id1 = store.save(scenario="a", what_worked="b", what_failed="none", lesson="c")
        id2 = store.save(scenario="d", what_worked="e", what_failed="none", lesson="f")
        lines = [json.loads(l) for l in path.read_text().splitlines() if l.strip()]
    assert len(lines) == 2
    assert {lines[0]["id"], lines[1]["id"]} == {id1, id2}


def test_count_lessons_excludes_schema_line():
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "lessons.jsonl"
        path.write_text('{"_schema": "LessonEntry", "version": 1}\n', encoding="utf-8")
        store = LessonStore(path=path)
        assert store.count_lessons() == 0
        store.save(scenario="a", what_worked="b", what_failed="none", lesson="c")
        assert store.count_lessons() == 1
