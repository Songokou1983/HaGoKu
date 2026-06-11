"""Prompt Lab API 测试 — mock LLM，不写真实 prompt.md"""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock

from hagoku.api.server import app

client = TestClient(app)


def test_current_prompt_returns_content():
    resp = client.get("/api/prompt-lab/current-prompt")
    assert resp.status_code == 200
    data = resp.json()
    assert "content" in data
    assert len(data["content"]) > 200  # 256 行 prompt


def test_run_returns_mock_result():
    with patch("hagoku.api.prompt_lab._call_llm") as mock_llm:
        mock_llm.return_value = {"content": "mock", "tool_calls": [], "tokens": 10, "model": "mock"}
        resp = client.post("/api/prompt-lab/run", json={
            "prompt_md": "test prompt", "messages": [],
        })
    assert resp.status_code == 200
    assert resp.json()["content"] == "mock"


def test_apply_with_mock_gate(tmp_path, monkeypatch):
    """用临时文件替代真实 prompt.md，避免写坏。"""
    test_prompt = tmp_path / "prompt.md"
    test_prompt.write_text("# test prompt content", encoding="utf-8")
    monkeypatch.setattr("hagoku.api.prompt_lab.PROMPT_PATH", test_prompt)

    resp = client.post("/api/prompt-lab/apply", json={"prompt_md": "# new content"})
    assert resp.status_code == 200
    assert "gate_output" in resp.json() or "ok" in resp.json()


def test_compare_returns_diff():
    with patch("hagoku.api.prompt_lab._call_llm") as mock_llm:
        mock_llm.return_value = {"content": "mock", "tool_calls": [], "tokens": 5, "model": "mock"}
        resp = client.post("/api/prompt-lab/compare", json={
            "baseline_prompt": "v1", "current_prompt": "v2", "messages": [],
        })
    assert resp.status_code == 200
    assert "diff" in resp.json()


def test_dumps_list_returns_array():
    resp = client.get("/api/prompt-lab/dumps?limit=5")
    assert resp.status_code == 200
    assert "dumps" in resp.json()
