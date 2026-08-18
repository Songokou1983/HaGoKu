"""Tests for fetch_market_data tool."""
import pytest
from unittest.mock import patch, MagicMock
import pandas as pd
from hagoku.tools.market_data import fetch_market_data, _session_cache


@pytest.fixture(autouse=True)
def _clear_cache():
    """每个测试前清空会话内缓存。"""
    _session_cache.clear()
    yield
    _session_cache.clear()


def _mock_akshare_df():
    """模拟 akshare 返回的中文列名 DataFrame。"""
    return pd.DataFrame({
        "日期": pd.date_range("2025-01-01", periods=5),
        "股票代码": ["600519"] * 5,
        "开盘": [100.0, 101.0, 102.0, 103.0, 104.0],
        "收盘": [101.0, 102.0, 103.0, 104.0, 105.0],
        "最高": [102.0, 103.0, 104.0, 105.0, 106.0],
        "最低": [99.0, 100.0, 101.0, 102.0, 103.0],
        "成交量": [1000, 1100, 1200, 1300, 1400],
        "成交额": [100000, 110000, 120000, 130000, 140000],
    })


def test_fetch_market_data_akshare_basic():
    """akshare 拉取成功 → 返回 ok dict + 标准化列名"""
    with patch("akshare.stock_zh_a_hist", return_value=_mock_akshare_df()), \
         patch("hagoku.tools.market_data._persist_to_library"):
        result = fetch_market_data(
            market="a_stock",
            symbol="600519",
            period="1y",
            interval="d1",
        )
    assert result["ok"] is True
    assert "dataset_id" in result
    assert result["dataset_id"].startswith("a_stock__600519__1y__d1__")
    assert result["rows"] == 5


def test_fetch_market_data_akshare_standardizes_columns():
    """akshare 中文列名 → 英文标准列名"""
    with patch("akshare.stock_zh_a_hist", return_value=_mock_akshare_df()), \
         patch("hagoku.tools.market_data._persist_to_library"):
        # 触发标准化（通过内部函数）
        from hagoku.tools.market_data import _standardize_columns
        df = _standardize_columns(_mock_akshare_df())
        assert list(df.columns) == ["date", "open", "high", "low", "close", "volume"]
        assert pd.api.types.is_datetime64_any_dtype(df["date"])