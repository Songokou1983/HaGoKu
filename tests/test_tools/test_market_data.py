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


def _mock_ccxt_ohlcv(n=5):
    """模拟 ccxt.fetch_ohlcv 返回 [timestamp, open, high, low, close, volume] 列表。"""
    import time
    base_ts = int(time.mktime(time.strptime("2025-01-01", "%Y-%m-%d"))) * 1000
    return [
        [base_ts + i * 86400000, 100.0 + i, 105.0 + i, 99.0 + i, 102.0 + i, 1000.0]
        for i in range(n)
    ]


def test_fetch_market_data_ccxt_basic():
    """ccxt 拉取成功 → 标准化列名"""
    mock_exchange = MagicMock()
    mock_exchange.fetch_ohlcv.return_value = _mock_ccxt_ohlcv(5)
    with patch("ccxt.binance", return_value=mock_exchange), \
         patch("hagoku.tools.market_data._persist_to_library"):
        result = fetch_market_data(
            market="crypto",
            symbol="BTC-USDT",
            period="30d",
            interval="d1",
        )
    assert result["ok"] is True
    assert "BTC-USDT" in result["dataset_id"]
    assert result["rows"] == 5


def test_fetch_market_data_ccxt_long_period_loops():
    """90d h1 = 2160 根 > 1000 限制 → 多次循环拼接"""
    mock_exchange = MagicMock()

    # 模拟：第一次返回 1000 根，第二次返回 1000 根，第三次返回 160 根
    call_count = {"n": 0}
    def ohlvc_paged(symbol, timeframe, since=None, limit=None):
        call_count["n"] += 1
        if call_count["n"] == 1:
            return _mock_ccxt_ohlcv(1000)
        elif call_count["n"] == 2:
            # 时间戳接着上一批
            base_ts = int(time.mktime(time.strptime("2025-01-01", "%Y-%m-%d"))) * 1000
            return [
                [base_ts + i * 3600000, 100.0 + i, 105.0 + i, 99.0 + i, 102.0 + i, 1000.0]
                for i in range(1000, 2000)
            ]
        else:
            base_ts = int(time.mktime(time.strptime("2025-01-01", "%Y-%m-%d"))) * 1000
            return [
                [base_ts + i * 3600000, 100.0 + i, 105.0 + i, 99.0 + i, 102.0 + i, 1000.0]
                for i in range(2000, 2160)
            ]

    import time
    mock_exchange.fetch_ohlcv.side_effect = ohlvc_paged
    with patch("ccxt.binance", return_value=mock_exchange), \
         patch("hagoku.tools.market_data._persist_to_library"):
        result = fetch_market_data(
            market="crypto",
            symbol="BTC-USDT",
            period="90d",
            interval="h1",
        )
    assert result["rows"] == 2160
    assert mock_exchange.fetch_ohlcv.call_count == 3


def test_fetch_market_data_akshare_failure_raises_runtime_error():
    """akshare 抛 ConnectionError → RuntimeError 含 4 条建议"""
    with patch("akshare.stock_zh_a_hist", side_effect=ConnectionError("refused")):
        with pytest.raises(RuntimeError) as exc_info:
            fetch_market_data(
                market="a_stock",
                symbol="600519",
                period="1y",
                interval="d1",
            )
        err = str(exc_info.value)
        assert "akshare 获取 600519 失败" in err
        assert "ConnectionError" in err
        assert "refused" in err
        assert "升级 akshare" in err
        assert "上传 CSV" in err


def test_fetch_market_data_a_stock_h1_raises_interval_error():
    """A 股 interval='h1' → RuntimeError 含 'akshare 不支持小时级' 提示"""
    with pytest.raises(RuntimeError) as exc_info:
        fetch_market_data(market="a_stock", symbol="600519", period="30d", interval="h1")
    err = str(exc_info.value)
    assert "akshare 不支持小时级" in err
    assert "d1" in err
    assert "加密货币" in err


def test_fetch_market_data_invalid_market_raises_market_error():
    """market='stock' → RuntimeError 含 '未知市场' 提示"""
    with pytest.raises(RuntimeError) as exc_info:
        fetch_market_data(market="stock", symbol="600519", period="1y", interval="d1")
    err = str(exc_info.value)
    assert "未知市场" in err
    assert "a_stock" in err or "crypto" in err


def test_fetch_market_data_akshare_unexpected_columns_raises():
    """akshare 列名改了（缺 '日期' 等）→ RuntimeError 含 columns 提示"""
    bad_df = pd.DataFrame({"some_col": [1, 2, 3]})  # 没有 "日期"
    with patch("akshare.stock_zh_a_hist", return_value=bad_df):
        with pytest.raises(RuntimeError, match="列名"):
            fetch_market_data(market="a_stock", symbol="600519", period="1y", interval="d1")


def test_fetch_market_data_cache_hit():
    """同 key 二次调用 → 命中缓存，不再调 akshare"""
    call_count = {"n": 0}
    def counting_mock(*args, **kwargs):
        call_count["n"] += 1
        return _mock_akshare_df()

    with patch("akshare.stock_zh_a_hist", side_effect=counting_mock), \
         patch("hagoku.tools.market_data._persist_to_library"):
        fetch_market_data("a_stock", "600519", "1y", "d1")
        fetch_market_data("a_stock", "600519", "1y", "d1")
        fetch_market_data("a_stock", "600519", "1y", "d1")
    assert call_count["n"] == 1  # 只调一次