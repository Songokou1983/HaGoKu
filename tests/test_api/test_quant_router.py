"""Tests for /api/quant/datasets CRUD endpoints."""
import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient
import json as _json

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


def test_delete_dataset_removes_directory(client, mock_datasets_dir):
    """DELETE → 删目录"""
    ds_id = "a_stock__600519__1y__d1__20260818T100000Z"
    ds_dir = mock_datasets_dir / ds_id
    ds_dir.mkdir()
    (ds_dir / "data.parquet").write_bytes(b"")
    (ds_dir / "meta.json").write_text('{"id": "' + ds_id + '"}')

    resp = client.delete(f"/api/quant/datasets/{ds_id}")
    assert resp.status_code == 200
    assert not ds_dir.exists()


def test_delete_nonexistent_dataset_404(client, mock_datasets_dir):
    resp = client.delete("/api/quant/datasets/nonexistent__id")
    assert resp.status_code == 404


def test_get_dataset_returns_parquet(client, mock_datasets_dir):
    """GET 单个 → 返回 parquet 二进制（项目创建时复制用）"""
    import pandas as pd
    from io import BytesIO
    df = pd.DataFrame({
        "date": pd.date_range("2025-01-01", periods=3),
        "open": [1.0, 2.0, 3.0],
        "high": [1.5, 2.5, 3.5],
        "low": [0.5, 1.5, 2.5],
        "close": [1.2, 2.2, 3.2],
        "volume": [100, 200, 300],
    })
    ds_id = "a_stock__600519__1y__d1__20260818T100000Z"
    ds_dir = mock_datasets_dir / ds_id
    ds_dir.mkdir()
    df.to_parquet(ds_dir / "data.parquet")
    (ds_dir / "meta.json").write_text(
        _json.dumps({"id": ds_id, "market": "a_stock", "symbol": "600519",
                     "period": "1y", "interval": "d1", "fetched_at": "20260818T100000Z",
                     "rows": 3, "source": "akshare"}, ensure_ascii=False)
    )

    resp = client.get(f"/api/quant/datasets/{ds_id}/parquet")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/octet-stream"
    df_loaded = pd.read_parquet(BytesIO(resp.content))
    assert len(df_loaded) == 3
    assert "date" in df_loaded.columns
