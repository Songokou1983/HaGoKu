"""Tests for /api/quant/datasets CRUD endpoints."""
import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient

from hagoku.api import quant_router
from hagoku.api.server import app  # actual app location


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def mock_datasets_dir(tmp_path, monkeypatch):
    """把数据集库根目录重定向到 tmp_path。"""
    monkeypatch.setattr(quant_router, "DATASETS_ROOT", tmp_path)
    return tmp_path


def test_list_datasets_empty(client, mock_datasets_dir):
    """库为空 → 空列表"""
    resp = client.get("/api/quant/datasets")
    assert resp.status_code == 200
    assert resp.json() == {"datasets": []}


def test_create_dataset_calls_fetch_and_returns_ok(client, mock_datasets_dir):
    """POST 创建 → 调 fetch_market_data → 200 + dataset_id"""
    fake_result = {
        "ok": True,
        "dataset_id": "a_stock__600519__1y__d1__20260818T100000Z",
        "rows": 245,
        "columns": ["date","open","high","low","close","volume"],
        "fetched_at": "20260818T100000Z",
    }
    with patch.object(quant_router, "_call_fetch_market_data", return_value=fake_result):
        resp = client.post(
            "/api/quant/datasets",
            json={
                "market": "a_stock",
                "symbol": "600519",
                "period": "1y",
                "interval": "d1",
            },
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["dataset_id"] == fake_result["dataset_id"]
    assert body["rows"] == 245


def test_create_dataset_fetch_failure_returns_422(client, mock_datasets_dir):
    """fetch_market_data 抛 RuntimeError → 422 + 错误信息"""
    with patch.object(
        quant_router,
        "_call_fetch_market_data",
        side_effect=RuntimeError("akshare 获取 600519 失败\n建议：..."),
    ):
        resp = client.post(
            "/api/quant/datasets",
            json={"market": "a_stock", "symbol": "600519", "period": "1y", "interval": "d1"},
        )
    assert resp.status_code == 422
    body = resp.json()
    assert "akshare 获取 600519 失败" in str(body)
