"""run_backtest 工具 — 按 strategy_spec 模拟交易，输出纯机械量。"""
from __future__ import annotations

import numpy as np
import pandas as pd


def run_backtest(
    strategy_spec: dict,
    _df: pd.DataFrame,
    ctx: dict | None = None,
) -> dict:
    """模拟策略交易，输出机械统计。

    Args:
        strategy_spec: {"name", "entry", "exit", "stop_loss?", "take_profit?"}
        _df: 当前项目 DataFrame（必须有 date/open/high/low/close/volume 列）

    Returns:
        纯机械量 dict（无 Sharpe/MaxDD/WinRate 等金融指标名）。
        LLM 用数学 + get_column_stats 推导金融指标。
    """
    required = ["name", "entry", "exit"]
    for k in required:
        if k not in strategy_spec:
            raise ValueError(f"strategy_spec 缺少字段: {k}（需要 {required}）")

    df = _df.copy()

    # Step 2: 求值表达式
    try:
        df["entry_signal"] = df.eval(strategy_spec["entry"]).astype(bool)
        df["exit_signal"] = df.eval(strategy_spec["exit"]).astype(bool)
    except Exception as e:
        raise RuntimeError(
            f"策略表达式求值失败。\n"
            f"entry: {strategy_spec['entry']}\n"
            f"exit: {strategy_spec['exit']}\n"
            f"原始错误: {type(e).__name__}: {e}\n"
            f"提示: 表达式必须是合法的 pandas 表达式，引用当前数据列名。"
        ) from e

    # Step 3: 推断 periods_per_year
    periods_per_year = _compute_periods_per_year(df)

    # Step 4: 事件驱动模拟（all_in + 可选止损止盈）
    stop_loss = strategy_spec.get("stop_loss")
    take_profit = strategy_spec.get("take_profit")
    in_position = False
    entry_price = None
    entry_time = None
    positions = []
    trades = []

    for _, row in df.iterrows():
        exit_now = False
        exit_reason = "signal"
        if in_position:
            current_pnl = (row["close"] - entry_price) / entry_price
            if stop_loss is not None and current_pnl <= -stop_loss:
                exit_now = True
                exit_reason = "stop_loss"
            elif take_profit is not None and current_pnl >= take_profit:
                exit_now = True
                exit_reason = "take_profit"

        if not in_position and row["entry_signal"]:
            in_position = True
            entry_price = row["close"]
            entry_time = row["date"]
            positions.append(1)
        elif in_position and (row["exit_signal"] or exit_now):
            exit_price = row["close"]
            pnl = (exit_price - entry_price) / entry_price
            trades.append({
                "entry_time": str(entry_time),
                "exit_time": str(row["date"]),
                "entry_price": float(entry_price),
                "exit_price": float(exit_price),
                "pnl": float(pnl),
                "exit_reason": exit_reason,
            })
            in_position = False
            entry_price = None
            positions.append(0)
        else:
            positions.append(1 if in_position else 0)

    positions_series = pd.Series(positions, index=df.index)

    # Step 5: 权益曲线（3.0 简化版：最终权益 = 10000 + 累计盈亏）
    final_pnl = sum(t["pnl"] for t in trades) if trades else 0.0
    equity = pd.Series(10000.0 + final_pnl, index=df.index)
    returns = equity.pct_change().fillna(0)

    summary = {
        "total_return": float((equity.iloc[-1] / equity.iloc[0]) - 1),
        "n_periods": int(len(df)),
        "n_trades": int(len(trades)),
        "n_positive_trades": int(sum(1 for t in trades if t["pnl"] > 0)),
        "n_negative_trades": int(sum(1 for t in trades if t["pnl"] <= 0)),
        "mean_trade_pnl": float(np.mean([t["pnl"] for t in trades])) if trades else 0.0,
    }

    return {
        "name": strategy_spec["name"],
        "equity_curve": equity,
        "trades": trades,
        "positions": positions_series,
        "returns": returns,
        "periods_per_year": periods_per_year,
        "summary": summary,
    }


def _compute_periods_per_year(df: pd.DataFrame) -> int:
    """从 df 时间间隔计算年化因子。"""
    if len(df) < 2:
        return 252
    delta = df["date"].iloc[1] - df["date"].iloc[0]
    seconds = delta.total_seconds()
    if seconds >= 86400 * 0.9:
        return 252          # 日线
    if seconds >= 3600 * 0.9:
        return 24 * 365    # 小时线
    return 252              # 其他兜底
