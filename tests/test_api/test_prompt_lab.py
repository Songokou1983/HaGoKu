"""Prompt Lab API 测试 — mock LLM，不写真实 prompt.md"""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock

from hagoku.api.server import app

client = TestClient(app)


def test_run_returns_mock_result():
    with patch("hagoku.api.prompt_lab._call_llm") as mock_llm:
        mock_llm.return_value = {"content": "mock", "tool_calls": [], "tokens": 10, "model": "mock"}
        resp = client.post("/api/prompt-lab/run", json={
            "prompt_md": "test prompt", "messages": [],
        })
    assert resp.status_code == 200
    assert resp.json()["content"] == "mock"


def test_compare_returns_diff():
    with patch("hagoku.api.prompt_lab._call_llm") as mock_llm:
        mock_llm.return_value = {"content": "mock", "tool_calls": [], "tokens": 5, "model": "mock"}
        resp = client.post("/api/prompt-lab/compare", json={
            "baseline_prompt": "v1", "current_prompt": "v2", "messages": [],
        })
    assert resp.status_code == 200
    assert "diff" in resp.json()
