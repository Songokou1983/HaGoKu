"""LessonAuditor 测试 — 启发式 + API mock"""
import json
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from hagoku.agents.lesson_auditor.agent import LessonAuditor, LessonAuditReport
from hagoku.api.server import app

client = TestClient(app)


def _make_lessons(tmp_path: Path, entries: list[dict]) -> Path:
    path = tmp_path / "lessons.jsonl"
    with open(path, "w") as f:
        f.write('{"_schema": "LessonEntry", "version": 1}\n')
        for e in entries:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")
    return path


def test_detect_duplicates(tmp_path):
    """同 scenario+lesson 应检出为重复。"""
    lessons = [
        {"id": "1", "scenario": "小样本ROI", "lesson": "用非参", "what_worked": "MW", "what_failed": "none", "confidence": "high"},
        {"id": "2", "scenario": "小样本ROI", "lesson": "用非参", "what_worked": "MW", "what_failed": "none", "confidence": "high"},
        {"id": "3", "scenario": "大样本ROI", "lesson": "用t检验", "what_worked": "t_test", "what_failed": "none", "confidence": "high"},
    ]
    path = _make_lessons(tmp_path, lessons)
    auditor = LessonAuditor()
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr("hagoku.agents.lesson_auditor.agent._LESSONS_PATH", path)
    report = auditor.review_batch()
    assert len(report.duplicates) == 1
    assert report.duplicates[0]["count"] == 2


def test_detect_contradictions(tmp_path):
    """同 scenario 不同 what_worked → 矛盾。"""
    lessons = [
        {"id": "1", "scenario": "缺失值处理", "lesson": "填中位数", "what_worked": "fill_median", "what_failed": "none", "confidence": "high"},
        {"id": "2", "scenario": "缺失值处理", "lesson": "删行", "what_worked": "drop_rows", "what_failed": "none", "confidence": "high"},
    ]
    path = _make_lessons(tmp_path, lessons)
    auditor = LessonAuditor()
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr("hagoku.agents.lesson_auditor.agent._LESSONS_PATH", path)
    report = auditor.review_batch()
    assert len(report.contradictions) == 1


def test_low_confidence_flag(tmp_path):
    """high + what_failed=none → 低质量标记。"""
    lessons = [
        {"id": "1", "scenario": "X", "lesson": "Y", "what_worked": "Z", "what_failed": "none", "confidence": "high"},
        {"id": "2", "scenario": "X", "lesson": "Y", "what_worked": "Z", "what_failed": "something wrong", "confidence": "high"},
    ]
    path = _make_lessons(tmp_path, lessons)
    auditor = LessonAuditor()
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr("hagoku.agents.lesson_auditor.agent._LESSONS_PATH", path)
    report = auditor.review_batch()
    assert len(report.low_confidence) == 1


def test_audit_api_endpoint():
    resp = client.post("/api/prompt-lab/audit-lessons")
    assert resp.status_code == 200
    assert "report_path" in resp.json()
