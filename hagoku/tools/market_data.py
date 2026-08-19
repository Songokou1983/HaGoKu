"""fetch_market_data 工具 — 从 akshare（A 股）或 ccxt（加密货币）拉取历史 OHLCV。"""
from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import Literal
import json as _json

import pandas as pd


_session_cache: dict[tuple, pd.DataFrame] = {}

DATASETS_ROOT = Path.home() / ".hagoku" / "datasets"


def fetch_market_data(
    market: str,
    symbol: str,
    period: str,
    interval: str,
    ctx: dict | None = None,
) -> dict:
    """拉取 OHLCV 数据并写入量化数据集库。

    Raises:
        RuntimeError: 拉取失败（统一格式：market / interval / fetch / columns）
    """
    # 提前校验（不重试，直接 RuntimeError）
    if market not in ("a_stock", "crypto"):
        raise _format_error(market, symbol, ValueError(f"market must be 'a_stock' or 'crypto', got '{market}'"), "market")
    if market == "a_stock" and interval not in ("d1",):
        raise _format_error(market, symbol, ValueError(f"akshare 不支持 interval='{interval}'"), "interval")

    key = (market, symbol, period, interval)
    if key in _session_cache:
        df = _session_cache[key]
        fetched_at = _format_fetched_at()
        ds_id = _build_dataset_id(market, symbol, period, interval, fetched_at)
        return _ok_result(ds_id, df, fetched_at)

    # 缓存命中：磁盘已有同名 (market, symbol, period, interval) → 直接复用，不发网络请求
    cached_ds_id = _find_latest_cached_dataset(market, symbol, period, interval)
    if cached_ds_id:
        try:
            df = pd.read_parquet(DATASETS_ROOT / cached_ds_id / "data.parquet")
            _session_cache[key] = df
            fetched_at = _format_fetched_at()
            return _ok_result(cached_ds_id, df, fetched_at)
        except Exception:
            pass  # 缓存坏则 fallback 到网络

    df = _fetch_with_retry(market, symbol, period, interval)
    df = _standardize_columns(df, market)

    fetched_at = _format_fetched_at()
    ds_id = _build_dataset_id(market, symbol, period, interval, fetched_at)
    _persist_to_library(ds_id, market, symbol, period, interval, df)
    _session_cache[key] = df

    return _ok_result(ds_id, df, fetched_at)


def _ok_result(ds_id: str, df: pd.DataFrame, fetched_at: str) -> dict:
    return {
        "ok": True,
        "dataset_id": ds_id,
        "rows": len(df),
        "columns": list(df.columns),
        "fetched_at": fetched_at,
    }


def _fetch_with_retry(market, symbol, period, interval):
    """3 次指数退避重试；ValueError 不重试（参数错）。
    限流信号（429 / DDoSProtection / RequestTimeout）最多 3 次退避重试（10s → 30s → 90s）。"""
    import time
    last_error = None
    for attempt in range(1, 4):
        try:
            if market == "a_stock":
                return _fetch_akshare(symbol, period, interval)
            elif market == "crypto":
                return _fetch_ccxt(symbol, period, interval)
        except (ConnectionError, TimeoutError) as e:
            last_error = e
            if attempt < 3:
                time.sleep(2 ** attempt)
        except ImportError:  # ccxt 缺
            raise
        except Exception as e:
            # 限流类异常（DDoSProtection / RequestTimeout / 429）→ 退避后重试
            if _is_rate_limit_error(e):
                last_error = e
                if attempt < 3:
                    time.sleep(10 * (3 ** (attempt - 1)))  # 10s → 30s → 90s
                continue
            # 永久错误（无效 symbol 等）→ 不重试
            if _is_permanent_error(e):
                raise
            # 未知错误 → 不重试，抛
            raise
    raise _format_error(market, symbol, last_error, "rate_limit")


def _is_rate_limit_error(e: Exception) -> bool:
    """检测 ccxt 限流类异常（DDoSProtection / RequestTimeout / 429）。"""
    import ccxt
    name = type(e).__name__
    if name in ("DDoSProtection", "RequestTimeout", "ExchangeNotAvailable", "RateLimitExceeded"):
        return True
    msg = str(e).lower()
    if "too many requests" in msg or "rate limit" in msg or "ip banned" in msg:
        return True
    return False


def _is_permanent_error(e: Exception) -> bool:
    """检测 ccxt 永久错误（无效 symbol / 交易所不存在）→ 不重试。"""
    import ccxt
    name = type(e).__name__
    if name in ("BadSymbol", "InvalidSymbol", "SymbolNotFound", "ExchangeError"):
        return True
    msg = str(e).lower()
    if "invalid symbol" in msg or "symbol not found" in msg:
        return True
    return False


def _fetch_akshare(symbol: str, period: str, interval: str) -> pd.DataFrame:
    """3.0 锁定 daily（akshare 仅支持 daily/weekly/monthly）。adjust='qfq' 前复权。"""
    import akshare as ak
    start_date, end_date = _parse_period(period)
    df = ak.stock_zh_a_hist(
        symbol=symbol,
        period="daily",  # 3.0 锁定 daily
        start_date=start_date,
        end_date=end_date,
        adjust="qfq",
    )
    return df


def _fetch_ccxt(symbol: str, period: str, interval: str) -> pd.DataFrame:
    """3.0 锁定 binance。>1000 根 K 线自动循环拼接。"""
    import ccxt
    trading_symbol = symbol.replace("-", "/")
    exchange = ccxt.binance()
    timeframe = "1d" if interval == "d1" else "1h"

    since_ms, total_limit = _parse_period_ccxt(period, interval)
    all_ohlcv = []
    while len(all_ohlcv) < total_limit:
        batch_limit = min(1000, total_limit - len(all_ohlcv))
        batch = exchange.fetch_ohlcv(trading_symbol, timeframe, since=since_ms, limit=batch_limit)
        if not batch:
            break  # 交易所返回空，到顶了
        all_ohlcv.extend(batch)
        since_ms = batch[-1][0] + 1  # 下一页起点
        if len(batch) < batch_limit:
            break  # 没满 = 到底了
    return pd.DataFrame(all_ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"])


def _parse_period(period: str) -> tuple[str, str]:
    """'1y'/'90d'/'30d' → (start_date, end_date)；'2025-01-01,2026-08-18' 直接返回。"""
    if "," in period:
        return period.split(",")
    end = datetime.utcnow()
    if period.endswith("y"):
        start = end - timedelta(days=365 * int(period[:-1]))
    elif period.endswith("d"):
        start = end - timedelta(days=int(period[:-1]))
    else:
        raise ValueError(f"不支持的 period 格式: {period}")
    return start.strftime("%Y%m%d"), end.strftime("%Y%m%d")


def _parse_period_ccxt(period: str, interval: str):
    """ccxt 的 (since_ms, total_limit)。total_limit 是预期总根数（可能超过 1000）。"""
    end_ms = int(datetime.utcnow().timestamp() * 1000)
    if period.endswith("y"):
        n_days = 365 * int(period[:-1])
    elif period.endswith("d"):
        n_days = int(period[:-1])
    else:
        raise ValueError(f"不支持的 period: {period}")
    since_ms = end_ms - n_days * 86400 * 1000
    if interval == "d1":
        total_limit = n_days
    else:  # h1
        total_limit = n_days * 24
    return since_ms, total_limit


def _standardize_columns(df: pd.DataFrame, market: str = "") -> pd.DataFrame:
    """akshare 中文列名 → 英文；ccxt timestamp → date；统一输出列序。

    Raises:
        RuntimeError: 缺必要列（akshare 接口改了）→ 走 _format_error("columns")
    """
    column_map_akshare = {
        "日期": "date", "开盘": "open", "收盘": "close",
        "最高": "high", "最低": "low", "成交量": "volume",
    }
    try:
        if "日期" in df.columns:
            df = df.rename(columns=column_map_akshare)
        if "timestamp" in df.columns:
            df = df.rename(columns={"timestamp": "date"})
        df["date"] = pd.to_datetime(df["date"])
        df = df[["date", "open", "high", "low", "close", "volume"]].copy()
    except KeyError as e:
        raise _format_error(market, "", e, "columns")
    df = df.sort_values("date").reset_index(drop=True)
    return df


def _format_fetched_at() -> str:
    return datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")


def _build_dataset_id(market: str, symbol: str, period: str, interval: str, fetched_at: str) -> str:
    return f"{market}__{symbol}__{period}__{interval}__{fetched_at}"


def _find_latest_cached_dataset(market: str, symbol: str, period: str, interval: str) -> str | None:
    """找磁盘上同名 (market, symbol, period, interval) 的最新数据集。返回 ds_id 或 None。"""
    if not DATASETS_ROOT.exists():
        return None
    prefix = f"{market}__{symbol}__{period}__{interval}__"
    candidates = []
    for d in DATASETS_ROOT.iterdir():
        if not d.is_dir():
            continue
        name = d.name
        if not name.startswith(prefix):
            continue
        # 名字格式：market__symbol__period__interval__fetched_at
        # 排序按 fetched_at（最后一段）
        fetched_at = name[len(prefix):]
        candidates.append((fetched_at, name))
    if not candidates:
        return None
    # fetched_at 格式 YYYYMMDDTHHMMSSZ 字典序 = 时间序
    candidates.sort(reverse=True)
    return candidates[0][1]


def _persist_to_library(ds_id: str, market: str, symbol: str, period: str, interval: str, df: pd.DataFrame) -> None:
    """写入 ~/.hagoku/datasets/<id>/data.parquet（meta 嵌入 parquet metadata，不另写 meta.json）"""
    import akshare as _ak
    import ccxt as _ccxt
    import pyarrow as _pa
    import pyarrow.parquet as _pq

    ds_dir = DATASETS_ROOT / ds_id
    ds_dir.mkdir(parents=True, exist_ok=True)

    source = "akshare" if market == "a_stock" else "ccxt"
    source_version = _ak.__version__ if market == "a_stock" else "ccxt"
    # meta 嵌入 parquet 文件 metadata（PyArrow 原生支持），一个文件不分裂
    meta_dict = {
        "id": ds_id,
        "market": market,
        "symbol": symbol,
        "period": period,
        "interval": interval,
        "fetched_at": _format_fetched_at(),
        "rows": str(len(df)),
        "source": source,
        "source_version": source_version,
        "_timezone": "Asia/Shanghai" if market == "a_stock" else "UTC",
    }
    table = _pa.Table.from_pandas(df)
    table = table.replace_schema_metadata(meta_dict)
    _pq.write_table(table, ds_dir / "data.parquet")


def _format_error(market: str, symbol: str, error: Exception, error_kind: str = "fetch") -> RuntimeError:
    """统一错误格式：RuntimeError + 原始异常 + 4 条建议。

    error_kind: "fetch" | "columns" | "interval" | "market" | "rate_limit"
    """
    if error_kind == "interval" and market == "a_stock":
        return RuntimeError(
            f"akshare 不支持小时级 A 股数据。\n"
            f"原始错误: interval='h1' 不被 akshare.stock_zh_a_hist 接受（仅 daily/weekly/monthly）\n"
            f"建议:\n"
            f"  1. 把 interval 改为 'd1'（日线）\n"
            f"  2. 切换到加密货币（ccxt 支持 h1）\n"
            f"  3. 用上传 CSV 方式提供数据"
        )
    if error_kind == "market":
        return RuntimeError(
            f"未知市场类型: {market}。\n"
            f"原始错误: {type(error).__name__}: {error}\n"
            f"建议:\n"
            f"  1. market 只接受 'a_stock' 或 'crypto'\n"
            f"  2. 检查参数拼写"
        )
    if error_kind == "columns":
        src = "akshare" if market == "a_stock" else "ccxt"
        return RuntimeError(
            f"{src} 接口列名变了，缺少标准列（如 '日期'/'date'）。\n"
            f"原始错误: {type(error).__name__}: {error}\n"
            f"建议:\n"
            f"  1. 升级 {src}: pip install -U {src}\n"
            f"  2. 用上传 CSV 方式提供数据\n"
            f"  3. 切换到另一种市场试试\n"
            f"  4. 检查网络/防火墙设置"
        )
    src = "akshare" if market == "a_stock" else "ccxt"
    if error_kind == "rate_limit":
        return RuntimeError(
            f"{src} 限流（3 次重试后仍被拒绝）。\n"
            f"原始错误: {type(error).__name__}: {error}\n"
            f"建议:\n"
            f"  1. 等待几分钟后重试（限流窗口过去后）\n"
            f"  2. 同一 (symbol, period, interval) 的数据已自动缓存，重新拉取走磁盘（不消耗限流）\n"
            f"  3. 上传 CSV 方式提供数据绕过限流"
        )
    return RuntimeError(
        f"{src} 获取 {symbol} 失败。\n"
        f"原始错误: {type(error).__name__}: {error}\n"
        f"建议:\n"
        f"  1. 升级 {src}: pip install -U {src}\n"
        f"  2. 用上传 CSV 方式提供数据\n"
        f"  3. 切换到另一种市场试试\n"
        f" 4. 检查网络/防火墙设置"
    )