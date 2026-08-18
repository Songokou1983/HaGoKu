"""Tests for run_backtest tool."""
import numpy as np
import pandas as pd
import pytest
from hagoku.tools.backtest import run_backtest


def _sample_ohlcv(n=100):
    """生成简单上涨行情用于回测测试。"""
    np.random.seed(42)
    dates = pd.date_range("2025-01-01", periods=n, freq="D")
    close = 100 + np.cumsum(np.random.randn(n) * 0.5)
    return pd.DataFrame({
        "date": dates,
        "open": close - 0.5,
        "high": close + 1.0,
        "low": close - 1.0,
        "close": close,
        "volume": np.random.randint(1000, 10000, n),
    })


def test_run_backtest_basic_sma_cross():
    """简单 SMA 交叉：close > sma(10) 入场，close < sma(10) 出场"""
    df = _sample_ohlcv()
    spec = {
        "name": "sma_cross",
        "entry": "close > close.rolling(10).mean()",
        "exit": "close < close.rolling(10).mean()",
    }
    result = run_backtest(spec, df)

    assert result["name"] == "sma_cross"
    assert "equity_curve" in result
    assert "trades" in result
    assert "summary" in result

    summary = result["summary"]
    assert "total_return" in summary
    assert "n_periods" in summary
    assert "n_trades" in summary
    assert "n_positive_trades" in summary
    assert "n_negative_trades" in summary
    assert "mean_trade_pnl" in summary
    # 关键：summary 没有 "sharpe" / "max_dd" / "win_rate" 等金融指标名
    assert "sharpe" not in summary
    assert "max_dd" not in summary
    assert "win_rate" not in summary


def test_run_backtest_required_fields_missing():
    """spec 缺 name/entry/exit → ValueError"""
    df = _sample_ohlcv()
    with pytest.raises(ValueError, match="缺少字段"):
        run_backtest({"entry": "x", "exit": "y"}, df)
    with pytest.raises(ValueError, match="缺少字段"):
        run_backtest({"name": "x", "exit": "y"}, df)


def test_run_backtest_expression_eval_error():
    """非法 pandas 表达式 → RuntimeError 含表达式内容"""
    df = _sample_ohlcv()
    spec = {
        "name": "bad",
        "entry": "nonexistent_col > 0",  # 不存在的列
        "exit": "close > 100",
    }
    with pytest.raises(RuntimeError, match="策略表达式求值失败"):
        run_backtest(spec, df)
