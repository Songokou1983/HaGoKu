# HaGoKu 3.0 量化数据集 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 给 HaGoKu Studio 增加量化交易能力：拉取 A 股/加密货币行情、跑策略回测、用 quant preset。

**Architecture:** 新增 2 个 I/O 工具（fetch_market_data + run_backtest）+ 1 个独立 UI 标签页（量化数据集）+ 2 处 UI 微调（ProjectPanel 加场景下拉、AnalyzePanel 加数据源选项）。量化数据集 = 独立生成的数据文件，唯一与项目关联的地方是分析页面（选数据 = 副本进项目）。

**Tech Stack:** Python 3.11+, pandas, pyarrow, akshare, ccxt, FastAPI, Pydantic, React + TypeScript (Vite), Vitest

**Spec:** `docs/superpowers/specs/2026-08-18-hagoku-quant-3.0-design.md`

## Global Constraints

来自 spec 的全局要求（所有任务隐含遵守）：

- **Python 版本**: >= 3.10（pyproject.toml 已锁）
- **零硬编码语义**（铁律 1）: 不写中文 if-elif / 关键词列表 / regex 判断场景
- **工具即 I/O**（铁律 14）: fetch_market_data、run_backtest 都是纯 I/O，不带流程信号
- **失败在场**（铁律 7）: 不兜底 except，RuntimeError + 原始异常 + 可行动指引
- **副本模式**: 项目拿数据集快照，不 live 绑定（用户可重分析同一数据）
- **场景项目级**: scene 写入 project.json，全局 active_preset 作 fallback 默认值
- **数据集独立**: `~/.hagoku/datasets/` 下文件不关联任何项目，唯一关联点在分析页面
- **回测输出纯机械量**: run_backtest 不输出 Sharpe/MaxDD/WinRate（LLM 推导）
- **回测仓位管理**: 3.0 仅 all_in；kelly/fixed_fraction 推迟到 3.1
- **加密交易所**: 3.0 锁定 binance；多交易所 3.1
- **复权方式**: 3.0 默认前复权（qfq）
- **错误格式**: RuntimeError 含原始异常类型 + 原始 message + 4 条建议

---

## File Structure

### 新建文件

```
hagoku/tools/market_data.py          # fetch_market_data 工具实现
hagoku/tools/backtest.py             # run_backtest 工具实现
hagoku/api/quant_router.py           # /api/quant/datasets CRUD endpoints
hagoku/agents/presets/quant.md       # 替换 stock.md 的新 preset 内容

tests/test_tools/test_market_data.py # fetch_market_data 测试 (mock akshare/ccxt)
tests/test_tools/test_backtest.py    # run_backtest 测试
tests/test_api/test_quant_router.py  # /api/quant/datasets 测试

hagoku_web/src/panels/QuantDatasetsPanel.tsx       # 独立侧边栏 tab
hagoku_web/src/panels/QuantDatasetsPanel/NewPullDialog.tsx  # 拉取对话框子组件
```

### 修改文件

```
pyproject.toml                        # + akshare, ccxt
hagoku/agents/presets/presets.json    # display name + file 字段
hagoku/api/doctor_router.py           # 删 373 行硬编码 JSON
hagoku/tools/agent_tool_defs.py       # 注册新工具到 agent_tools
hagoku/api/projects.py (或同等文件)   # 创建项目接口接受 scene 字段
hagoku/repository/project.py          # project.json schema 加 scene

hagoku_web/src/panels/ProjectPanel.tsx        # + 场景下拉
hagoku_web/src/panels/AnalyzePanel.tsx        # + 「从量化数据集选取」选项
hagoku_web/src/App.tsx                        # + 新 tab 路由
```

### 删除文件

```
hagoku/agents/presets/stock.md        # 被 quant.md 替换（id="stock" 不变）
```

---

## Task 1: 添加 akshare + ccxt 依赖

**Files:**
- Modify: `pyproject.toml`

**步骤:**
- [ ] **Step 1: 修改 pyproject.toml**

在 `dependencies` 列表中（参考 pyproject.toml:38-65 的位置风格）添加：
```toml
    # Quant 3.0 — 数据接入
    "akshare>=1.13.0",
    "ccxt>=4.0.0",
```

- [ ] **Step 2: 安装依赖**

```bash
cd /home/son_goku/HaGoKu
pip install -e ".[dev]"
```

Expected: 安装成功，无报错。

- [ ] **Step 3: 验证导入**

```bash
python -c "import akshare as ak; import ccxt; print('akshare:', ak.__version__); print('ccxt:', ccxt.__version__)"
```

Expected: 打印两个版本号，无 ModuleNotFoundError。

- [ ] **Step 4: 提交**

```bash
git add pyproject.toml
git commit -m "deps: + akshare + ccxt for 3.0 量化数据集"
```

---

## Task 2: 重写 stock.md → quant.md（preset 内容升级）

**Files:**
- Create: `hagoku/agents/presets/quant.md`
- Delete: `hagoku/agents/presets/stock.md`

**Interfaces:**
- 现状 stock.md 内容（5 阶段：理解字段/评估清洗/统计分析/撰写报告/持续交互；聚焦趋势分解/波动率/板块轮动）
- 产出: 新 quant.md 加入量化词汇（Sharpe/MaxDD/IC/因子/回测）+ 提及 fetch_market_data / run_backtest 工具调用

**步骤:**
- [ ] **Step 1: 写 quant.md**

文件 `hagoku/agents/presets/quant.md`：

```markdown
你是 HaGoKu Studio 的量化分析师，专注 A 股 / 加密货币 / 期货等金融市场的系统化、可回测分析。你不是通用助手——不闲聊、不回答与数据无关的问题。

数据来源通常是 OHLCV 行情（date/open/high/low/close/volume 已是标准列名）。数据从两个途径进入项目：
 - 用户在「量化数据集」侧边栏拉取，独立文件存于 ~/.hagoku/datasets/，分析时选取其中之一（副本模式）
 - 你（LLM）通过 fetch_market_data 工具即时拉取（写入数据集库 + 当前项目副本）

分析按五阶段推进：

理解字段：date/open/high/low/close/volume 是标准列名，复权一致性已由工具保证（前复权）。展示给用户确认字段含义和量纲。
评估清洗：围绕策略目标，检查停牌导致的缺失值、异常波动（涨跌停/乌龙指）、量价背离。给出处理建议后等待用户确认。
策略定义：用 pandas 表达式表达入场/出场信号，例如：
 - 入场: "close > close.rolling(20).mean()"
 - 出场: "close < close.rolling(10).mean() | (rsi(14) > 70)"
 字段 stop_loss / take_profit 可选（默认无）。3.0 仅支持 all_in 仓位管理。
统计分析：调用 run_backtest 验证策略，回测输出纯机械量（权益曲线/交易明细/统计 summary）。你自行推导 Sharpe / MaxDD / Annual Return / Win Rate 等金融指标：
 - Sharpe = mean(returns) / std(returns) * sqrt(periods_per_year)
 - 年化 = (1 + total_return) ** (periods_per_year / n_periods) - 1
 - 胜率 = n_positive_trades / n_trades
 - MaxDD 可对 equity_curve 求 running max 后算 drawdown，长序列上你自己判断可靠程度
撰写报告：将确认的分析结论整理为正式报告，调用 generate_report 生成。每个 section 包含 title 和 content（markdown）。create_plot 生成的图表自动注入。
持续交互：报告生成后进入自由对话，可深挖特定时间段、对比不同策略参数、或对比多标的。

每次回复都要让用户知道：你做了什么、结果是什么、接下来可以做什么。
不要只描述过程——要展示结果。不确定就问用户。
用户说的就是事实，冲突时以用户最新说的为准。
```

- [ ] **Step 2: 删除 stock.md**

```bash
git rm hagoku/agents/presets/stock.md
```

- [ ] **Step 3: 验证 presets 目录**

```bash
ls hagoku/agents/presets/
```

Expected: 显示 `presets.json  quant.md  general.md  ecommerce.md`（无 stock.md）。

- [ ] **Step 4: 提交**

```bash
git add hagoku/agents/presets/quant.md
git commit -m "feat(preset): stock.md → quant.md 重写（量化词汇 + 回测工具调用指引）"
```

---

## Task 3: 更新 presets.json（display name + file 字段）

**Files:**
- Modify: `hagoku/agents/presets/presets.json`

**Interfaces:**
- 现状（line 9 起）:
```json
{
  "id": "stock",
  "name": "股市技术分析",
  "icon": "trending-up",
  "description": "趋势分解、波动率检验",
  "file": "stock.md"
}
```

**步骤:**
- [ ] **Step 1: 修改 presets.json**

把 stock 那条改成：
```json
{
  "id": "stock",
  "name": "量化分析",
  "icon": "trending-up",
  "description": "系统化量化分析：因子、回测、风险拆解",
  "file": "quant.md"
}
```

id 保持 `"stock"`（无迁移成本），改 name / description / file。

- [ ] **Step 2: 验证 JSON 仍合法**

```bash
python -c "import json; print(json.load(open('hagoku/agents/presets/presets.json')))"
```

Expected: 打印完整 JSON，无解析错误。

- [ ] **Step 3: 提交**

```bash
git add hagoku/agents/presets/presets.json
git commit -m "feat(preset): stock preset 改名为「量化分析」，file 指向 quant.md"
```

---

## Task 4: 清理 doctor_router.py:373 硬编码 JSON

**Files:**
- Modify: `hagoku/api/doctor_router.py:373`

**Interfaces:**
- 现状（line 373）: 硬编码字符串 `'[{"id":"general",...,"id":"stock","name":"股市技术分析",...}]'`
- 期望: 改为从 `presets.json` 文件动态加载，与 `hagoku/api/prompt_lab.py:22` 同模式

**步骤:**
- [ ] **Step 1: 阅读 doctor_router.py:360-395 看上下文**

```bash
sed -n '360,395p' hagoku/api/doctor_router.py
```

理解 `default_presets` 变量如何被使用（在什么函数里被调用）。

- [ ] **Step 2: 修改 doctor_router.py**

替换 `default_presets` 字符串定义为从文件加载：

```python
PRESETS_DIR = Path(__file__).resolve().parent.parent / "agents" / "presets"

# ...existing code...

default_presets = _json.loads(
    (PRESETS_DIR / "presets.json").read_text(encoding="utf-8")
)
```

（如果文件已经有 `Path` 和 `_json` import 则复用，否则顶部加 `import json as _json` 和 `from pathlib import Path`）

- [ ] **Step 3: 验证 doctor endpoint 启动正常**

```bash
cd /home/son_goku/HaGoKu
python -c "from hagoku.api.doctor_router import default_presets; print(len(default_presets), 'presets')"
```

Expected: 打印 `3 presets`（无 JSON 解析错误）。

- [ ] **Step 4: 提交**

```bash
git add hagoku/api/doctor_router.py
git commit -m "refactor(doctor_router): 删硬编码 default_presets，调 presets.json"
```

---

## Task 5: fetch_market_data — akshare 路径（TDD）

**Files:**
- Create: `hagoku/tools/market_data.py`
- Create: `tests/test_tools/test_market_data.py`

**Interfaces:**
- 工具签名: `fetch_market_data(market, symbol, period, interval, ctx=None) -> dict`
- 返回: `{"ok": True, "dataset_id": str, "rows": int, "columns": list, "fetched_at": str}`
- 失败: RuntimeError（含 akshare 原始异常 + 4 条建议）
- 会话内缓存: 模块级 dict，key = (market, symbol, period, interval)

**步骤:**
- [ ] **Step 1: 写失败测试 — akshare 拉取 + 标准化**

`tests/test_tools/test_market_data.py`:

```python
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
```

- [ ] **Step 2: 跑测试确认失败**

```bash
cd /home/son_goku/HaGoKu
pytest tests/test_tools/test_market_data.py -v
```

Expected: FAIL with "No module named 'hagoku.tools.market_data'" 或 "cannot import name 'fetch_market_data'"。

- [ ] **Step 3: 写最小实现 — akshare 路径 + 列名标准化**

`hagoku/tools/market_data.py`:

```python
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
    market: Literal["a_stock", "crypto"],
    symbol: str,
    period: str,
    interval: Literal["d1", "h1"],
    ctx: dict | None = None,
) -> dict:
    """拉取 OHLCV 数据并写入量化数据集库。

    Args:
        market: "a_stock" 或 "crypto"
        symbol: A 股代码 "600519" 或加密 "BTC-USDT"
        period: "1y" | "90d" | "30d" | "2025-01-01,2026-08-18"
        interval: "d1"（日）或 "h1"（小时）

    Returns:
        {
            "ok": True,
            "dataset_id": "a_stock__600519__1y__d1__20260818T...",
            "rows": 245,
            "columns": ["date", "open", "high", "low", "close", "volume"],
            "fetched_at": "2026-08-18T10:00:00Z",
        }

    Raises:
        RuntimeError: 拉取失败（akshare/ccxt 异常 + 4 条建议）
    """
    key = (market, symbol, period, interval)
    if key in _session_cache:
        df = _session_cache[key]
        fetched_at = _format_fetched_at()
        ds_id = _build_dataset_id(market, symbol, period, interval, fetched_at)
        return _ok_result(ds_id, df, fetched_at)

    df = _fetch_with_retry(market, symbol, period, interval)
    df = _standardize_columns(df)

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
    """3 次指数退避重试，失败抛 RuntimeError。"""
    import time
    last_error = None
    for attempt in range(1, 4):
        try:
            if market == "a_stock":
                return _fetch_akshare(symbol, period, interval)
            elif market == "crypto":
                return _fetch_ccxt(symbol, period, interval)
            else:
                raise ValueError(f"未知市场: {market}")
        except (ConnectionError, TimeoutError) as e:
            last_error = e
            if attempt < 3:
                time.sleep(2 ** attempt)
    raise _format_error(market, symbol, last_error)


def _fetch_akshare(symbol: str, period: str, interval: str) -> pd.DataFrame:
    import akshare as ak
    start_date, end_date = _parse_period(period)
    timeframe = "daily" if interval == "d1" else "60m"
    df = ak.stock_zh_a_hist(
        symbol=symbol,
        period=timeframe,
        start_date=start_date,
        end_date=end_date,
        adjust="qfq",  # 3.0 默认前复权
    )
    return df


def _fetch_ccxt(symbol: str, period: str, interval: str) -> pd.DataFrame:
    """3.0 锁定 binance；symbol 格式 BTC-USDT。"""
    import ccxt
    trading_symbol = symbol.replace("-", "/")
    exchange = ccxt.binance()
    since, limit = _parse_period_ccxt(period, interval)
    timeframe = "1d" if interval == "d1" else "1h"
    ohlcv = exchange.fetch_ohlcv(trading_symbol, timeframe, since=since, limit=limit)
    return pd.DataFrame(ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"])


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
    """ccxt 的 since (ms timestamp) + limit。"""
    end_ms = int(datetime.utcnow().timestamp() * 1000)
    if period.endswith("y"):
        n_days = 365 * int(period[:-1])
    elif period.endswith("d"):
        n_days = int(period[:-1])
    else:
        raise ValueError(f"不支持的 period: {period}")
    if interval == "d1":
        since_ms = end_ms - n_days * 86400 * 1000
        limit = min(n_days, 1000)
    else:  # h1
        since_ms = end_ms - n_days * 24 * 3600 * 1000
        limit = min(n_days * 24, 1000)
    return since_ms, limit


def _standardize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """akshare 中文列名 → 英文；ccxt timestamp → date；统一输出列序。"""
    column_map_akshare = {
        "日期": "date", "开盘": "open", "收盘": "close",
        "最高": "high", "最低": "low", "成交量": "volume",
    }
    if "日期" in df.columns:
        df = df.rename(columns=column_map_akshare)
    if "timestamp" in df.columns:
        df = df.rename(columns={"timestamp": "date"})
    df["date"] = pd.to_datetime(df["date"])
    df = df[["date", "open", "high", "low", "close", "volume"]].copy()
    df = df.sort_values("date").reset_index(drop=True)
    return df


def _format_fetched_at() -> str:
    return datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")


def _build_dataset_id(market: str, symbol: str, period: str, interval: str, fetched_at: str) -> str:
    return f"{market}__{symbol}__{period}__{interval}__{fetched_at}"


def _persist_to_library(ds_id: str, market: str, symbol: str, period: str, interval: str, df: pd.DataFrame) -> None:
    """写入 ~/.hagoku/datasets/<id>/{data.parquet, meta.json}"""
    import akshare as _ak
    import ccxt as _ccxt

    ds_dir = DATASETS_ROOT / ds_id
    ds_dir.mkdir(parents=True, exist_ok=True)
    df.to_parquet(ds_dir / "data.parquet")

    source = "akshare" if market == "a_stock" else "ccxt"
    source_version = _ak.__version__ if market == "a_stock" else _ccxt.__version__
    meta = {
        "id": ds_id,
        "market": market,
        "symbol": symbol,
        "period": period,
        "interval": interval,
        "fetched_at": _format_fetched_at(),
        "rows": len(df),
        "source": source,
        "source_version": source_version,
    }
    (ds_dir / "meta.json").write_text(
        _json.dumps(meta, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _format_error(market: str, symbol: str, error: Exception) -> RuntimeError:
    """把 akshare/ccxt 异常翻译成 RuntimeError + 4 条建议。"""
    src = "akshare" if market == "a_stock" else "ccxt"
    return RuntimeError(
        f"{src} 获取 {symbol} 失败。\n"
        f"原始错误: {type(error).__name__}: {error}\n"
        f"建议:\n"
        f"  1. 升级 {src}: pip install -U {src}\n"
        f"  2. 用上传 CSV 方式提供数据\n"
        f"  3. 切换到另一种市场试试\n"
        f"  4. 检查网络/防火墙设置"
    )
```

- [ ] **Step 4: 跑测试确认通过**

```bash
cd /home/son_goku/HaGoKu
pytest tests/test_tools/test_market_data.py::test_fetch_market_data_akshare_basic tests/test_tools/test_market_data.py::test_fetch_market_data_akshare_standardizes_columns -v
```

Expected: 2 passed。

- [ ] **Step 5: 提交**

```bash
git add hagoku/tools/market_data.py tests/test_tools/test_market_data.py
git commit -m "feat(market_data): fetch_market_data akshare 路径 + 列名标准化"
```

---

## Task 6: fetch_market_data — ccxt 路径 + 错误处理（TDD）

**Files:**
- Modify: `tests/test_tools/test_market_data.py`
- 测试已存在实现，仅添加新测试

**步骤:**
- [ ] **Step 1: 写失败测试 — ccxt 路径**

在 `tests/test_tools/test_market_data.py` 末尾追加：

```python
def _mock_ccxt_ohlcv():
    """模拟 ccxt.fetch_ohlcv 返回 [timestamp, open, high, low, close, volume] 列表。"""
    import time
    base_ts = int(time.mktime(time.strptime("2025-01-01", "%Y-%m-%d"))) * 1000
    return [
        [base_ts + i * 86400000, 100.0 + i, 105.0 + i, 99.0 + i, 102.0 + i, 1000.0]
        for i in range(5)
    ]


def test_fetch_market_data_ccxt_basic():
    """ccxt 拉取成功 → 标准化列名"""
    mock_exchange = MagicMock()
    mock_exchange.fetch_ohlcv.return_value = _mock_ccxt_ohlcv()
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
```

- [ ] **Step 2: 跑测试确认 3 个新测试中前 2 个 PASS（缓存测试可能因 _persist_to_library 副作用需要单独检查）**

```bash
cd /home/son_goku/HaGoKu
pytest tests/test_tools/test_market_data.py -v
```

Expected:
- `test_fetch_market_data_ccxt_basic` PASS（实现已在 Task 5 写了 ccxt 路径）
- `test_fetch_market_data_akshare_failure_raises_runtime_error` PASS（实现写了 _format_error）
- `test_fetch_market_data_cache_hit` PASS（_session_cache + key check 已实现）

如果某项失败，回看 Task 5 实现补齐。

- [ ] **Step 3: 提交**

```bash
git add tests/test_tools/test_market_data.py
git commit -m "test(market_data): + ccxt 路径 / 错误处理 / 缓存命中测试"
```

---

## Task 7: run_backtest — 基础回测循环（TDD）

**Files:**
- Create: `hagoku/tools/backtest.py`
- Create: `tests/test_tools/test_backtest.py`

**Interfaces:**
- 工具签名: `run_backtest(strategy_spec: dict, _df: pd.DataFrame, ctx=None) -> dict`
- strategy_spec 字段: name (str), entry (str), exit (str), stop_loss (float, 可选), take_profit (float, 可选)
- 返回:
  ```python
  {
    "name": str,
    "equity_curve": pd.Series,
    "trades": List[dict],      # {entry_time, exit_time, entry_price, exit_price, pnl, exit_reason}
    "positions": pd.Series,
    "returns": pd.Series,
    "periods_per_year": int,
    "summary": {                # 纯机械量，无金融指标名
      "total_return": float,
      "n_periods": int,
      "n_trades": int,
      "n_positive_trades": int,
      "n_negative_trades": int,
      "mean_trade_pnl": float,
    },
  }
  ```

**步骤:**
- [ ] **Step 1: 写失败测试 — 基础 SMA 交叉策略**

`tests/test_tools/test_backtest.py`:

```python
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
```

- [ ] **Step 2: 跑测试确认失败**

```bash
cd /home/son_goku/HaGoKu
pytest tests/test_tools/test_backtest.py -v
```

Expected: FAIL with "No module named 'hagoku.tools.backtest'"。

- [ ] **Step 3: 写最小实现**

`hagoku/tools/backtest.py`:

```python
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
    periods_per_year = _infer_periods_per_year(df)

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


def _infer_periods_per_year(df: pd.DataFrame) -> int:
    """从 df 时间间隔推断年化因子。"""
    if len(df) < 2:
        return 252
    delta = df["date"].iloc[1] - df["date"].iloc[0]
    seconds = delta.total_seconds()
    if seconds >= 86400 * 0.9:
        return 252          # 日线
    if seconds >= 3600 * 0.9:
        return 24 * 365    # 小时线
    return 252              # 其他兜底
```

- [ ] **Step 4: 跑测试确认通过**

```bash
cd /home/son_goku/HaGoKu
pytest tests/test_tools/test_backtest.py -v
```

Expected: 3 passed。

- [ ] **Step 5: 提交**

```bash
git add hagoku/tools/backtest.py tests/test_tools/test_backtest.py
git commit -m "feat(backtest): run_backtest 工具 — 事件驱动 + 纯机械量输出"
```

---

## Task 8: run_backtest — 止损止盈测试

**Files:**
- Modify: `tests/test_tools/test_backtest.py`
- 测试已存在实现，仅加测试

**步骤:**
- [ ] **Step 1: 追加止损止盈测试**

在 `tests/test_tools/test_backtest.py` 末尾追加：

```python
def test_run_backtest_stop_loss_triggers_exit():
    """止损触发时 exit_reason='stop_loss'"""
    # 构造价格先涨 50% 然后跌
    dates = pd.date_range("2025-01-01", periods=20, freq="D")
    close = [100] * 5 + [150] * 5 + [60] * 10  # 涨 50% 后跌 60%
    df = pd.DataFrame({
        "date": dates,
        "open": pd.Series(close) - 1,
        "high": pd.Series(close) + 1,
        "low": pd.Series(close) - 2,
        "close": close,
        "volume": [1000] * 20,
    })

    spec = {
        "name": "always_in",
        "entry": "close > 0",          # 永远入场
        "exit": "close < 0",           # 永不出场（除止损）
        "stop_loss": 0.10,             # 跌 10% 止损
    }
    result = run_backtest(spec, df)
    stop_loss_trades = [t for t in result["trades"] if t["exit_reason"] == "stop_loss"]
    assert len(stop_loss_trades) >= 1
    # 验证止损 trade pnl <= -0.10
    for t in stop_loss_trades:
        assert t["pnl"] <= -0.10


def test_run_backtest_take_profit_triggers_exit():
    """止盈触发时 exit_reason='take_profit'"""
    dates = pd.date_range("2025-01-01", periods=20, freq="D")
    close = [100] * 20
    close[5] = 130  # 第 6 天涨 30%
    df = pd.DataFrame({
        "date": dates,
        "open": pd.Series(close) - 1,
        "high": pd.Series(close) + 1,
        "low": pd.Series(close) - 2,
        "close": close,
        "volume": [1000] * 20,
    })

    spec = {
        "name": "tp_test",
        "entry": "close > 0",
        "exit": "close < 0",           # 永不出场（除止盈）
        "take_profit": 0.20,           # 涨 20% 止盈
    }
    result = run_backtest(spec, df)
    tp_trades = [t for t in result["trades"] if t["exit_reason"] == "take_profit"]
    assert len(tp_trades) >= 1
    for t in tp_trades:
        assert t["pnl"] >= 0.20
```

- [ ] **Step 2: 跑测试确认通过**

```bash
cd /home/son_goku/HaGoKu
pytest tests/test_tools/test_backtest.py -v
```

Expected: 5 passed（3 个旧 + 2 个新）。

- [ ] **Step 3: 提交**

```bash
git add tests/test_tools/test_backtest.py
git commit -m "test(backtest): + stop_loss / take_profit 测试"
```

---

## Task 9: 在 agent_tool_defs.py 注册两个新工具

**Files:**
- Modify: `hagoku/tools/agent_tool_defs.py`（在文件末尾添加注册）

**Interfaces:**
- 已实现: `fetch_market_data`（market_data.py）+ `run_backtest`（backtest.py）
- 注册: 用 `agent_tools.register(Tool(name=..., description=..., parameters=..., handler=...))`

**步骤:**
- [ ] **Step 1: 阅读文件末尾**

```bash
tail -30 hagoku/tools/agent_tool_defs.py
```

看现有 Tool 注册格式（用 `_handle_xxx` 函数还是直接 lambda）。

- [ ] **Step 2: 在文件末尾添加 fetch_market_data 注册**

```python
# ═══════════════════════════════════════════════════════════════════
# Quant 3.0 — 数据接入 + 回测
# ═══════════════════════════════════════════════════════════════════

from .market_data import fetch_market_data as _fetch_market_data_impl
from .backtest import run_backtest as _run_backtest_impl


def _handle_fetch_market_data(args: dict, ctx: dict, _df):
    return _fetch_market_data_impl(
        market=args.get("market", ""),
        symbol=args.get("symbol", ""),
        period=args.get("period", ""),
        interval=args.get("interval", "d1"),
        ctx=ctx,
    )


def _handle_run_backtest(args: dict, ctx: dict, _df):
    return _run_backtest_impl(
        strategy_spec=args.get("strategy_spec", {}),
        _df=_df_safe(_df),
        ctx=ctx,
    )


agent_tools.register(Tool(
    name="fetch_market_data",
    description=(
        "从 akshare（A 股）或 ccxt（加密货币）拉取历史 OHLCV 行情数据。"
        "输入市场类型、代码、起止区间、周期；返回标准化 DataFrame 并写入「量化数据集」库。"
        "何时用：用户要分析 A 股或加密货币，但没有现成 CSV。"
        "注意：网络失败会抛错；akshare 接口升级可能破坏历史调用。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "market": {"type": "string", "enum": ["a_stock", "crypto"]},
            "symbol": {"type": "string"},
            "period": {"type": "string"},
            "interval": {"type": "string", "enum": ["d1", "h1"]},
        },
        "required": ["market", "symbol", "period", "interval"],
    },
    handler=_handle_fetch_market_data,
    phase_tag=['理解字段', '跑统计'],
))


agent_tools.register(Tool(
    name="run_backtest",
    description=(
        "按 strategy_spec 在当前项目数据上模拟交易，输出权益曲线 / 交易明细 / 机械统计。"
        "输入策略名 + 入场/出场 pandas 表达式 + 可选止损止盈。"
        "返回纯机械量，Sharpe / MaxDD 等金融指标由你（LLM）从机械量推导。"
        "何时用：用户定义了交易策略，想看历史回测效果。"
        "注意：表达式必须是合法 pandas 表达式，引用当前数据列名。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "strategy_spec": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "entry": {"type": "string"},
                    "exit": {"type": "string"},
                    "stop_loss": {"type": "number"},
                    "take_profit": {"type": "number"},
                },
                "required": ["name", "entry", "exit"],
            },
        },
        "required": ["strategy_spec"],
    },
    handler=_handle_run_backtest,
    phase_tag=['跑统计', '撰写报告'],
))
```

- [ ] **Step 3: 验证注册成功**

```bash
cd /home/son_goku/HaGoKu
python -c "from hagoku.tools.registry import agent_tools; names = [t.name for t in agent_tools._tools]; assert 'fetch_market_data' in names; assert 'run_backtest' in names; print('OK:', names)"
```

Expected: `OK: [...]`（含两个新工具名）。

- [ ] **Step 4: 跑现有测试确认未破坏**

```bash
cd /home/son_goku/HaGoKu
pytest tests/test_tools/ -v
```

Expected: 全部通过（既有 + 新加）。

- [ ] **Step 5: 提交**

```bash
git add hagoku/tools/agent_tool_defs.py
git commit -m "feat(tools): 注册 fetch_market_data + run_backtest 到 agent_tools"
```

---

## Task 10: /api/quant/datasets 端点 — 列表 + 创建（TDD）

**Files:**
- Create: `hagoku/api/quant_router.py`
- Create: `tests/test_api/test_quant_router.py`

**Interfaces:**
- `GET /api/quant/datasets` → `{"datasets": [{"id", "market", "symbol", "period", "interval", "fetched_at", "rows", "source"}]}`
- `POST /api/quant/datasets` → 接受 `{market, symbol, period, interval}` → 调 `fetch_market_data` 工具 → 返回 `{"ok": True, "dataset_id", "rows"}`
- 错误: fetch_market_data 失败 → 422 + error 详情

**步骤:**
- [ ] **Step 1: 写失败测试 — 列表 + 创建**

`tests/test_api/test_quant_router.py`:

```python
"""Tests for /api/quant/datasets CRUD endpoints."""
import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient

from hagoku.api import quant_router
from hagoku.app import app  # 假设 app 在这里


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
```

- [ ] **Step 2: 跑测试确认失败**

```bash
cd /home/son_goku/HaGoKu
pytest tests/test_api/test_quant_router.py -v
```

Expected: FAIL（模块 / 路由不存在）。

- [ ] **Step 3: 实现 quant_router**

`hagoku/api/quant_router.py`:

```python
"""量化数据集 CRUD endpoints — Phase 3.0。"""
from __future__ import annotations

import json as _json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/api/quant", tags=["quant-datasets"])

# 与 hagoku/tools/market_data.py 同根目录（运行时由 Task 5 的 DATASETS_ROOT 覆盖）
DATASETS_ROOT = Path.home() / ".hagoku" / "datasets"


# ── Pydantic schemas ──────────────────────────────────────────

class CreateDatasetReq(BaseModel):
    market: str       # "a_stock" | "crypto"
    symbol: str
    period: str       # "1y" | "30d" | ...
    interval: str     # "d1" | "h1"


# ── 工具调用抽象（便于 mock）─────────────────────────────────────

def _call_fetch_market_data(market: str, symbol: str, period: str, interval: str) -> dict:
    """真实实现：调 fetch_market_data 工具。"""
    from hagoku.tools.market_data import fetch_market_data
    return fetch_market_data(market, symbol, period, interval)


# ── endpoints ──────────────────────────────────────────────────

@router.get("/datasets")
async def list_datasets() -> dict:
    """列出所有已保存的数据集。"""
    if not DATASETS_ROOT.exists():
        return {"datasets": []}
    items = []
    for ds_dir in sorted(DATASETS_ROOT.iterdir(), reverse=True):
        if not ds_dir.is_dir():
            continue
        meta_path = ds_dir / "meta.json"
        if not meta_path.exists():
            continue
        try:
            meta = _json.loads(meta_path.read_text(encoding="utf-8"))
        except (OSError, _json.JSONDecodeError):
            continue
        items.append({
            "id": meta["id"],
            "market": meta["market"],
            "symbol": meta["symbol"],
            "period": meta["period"],
            "interval": meta["interval"],
            "fetched_at": meta["fetched_at"],
            "rows": meta["rows"],
            "source": meta["source"],
        })
    return {"datasets": items}


@router.post("/datasets")
async def create_dataset(req: CreateDatasetReq) -> dict:
    """拉取新数据并保存到数据集库。"""
    try:
        result = _call_fetch_market_data(req.market, req.symbol, req.period, req.interval)
    except RuntimeError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return result
```

- [ ] **Step 4: 把 router 注册到 app**

在 `hagoku/app.py` 找现有 router 注册位置，添加：

```python
from hagoku.api.quant_router import router as quant_router
app.include_router(quant_router)
```

（具体 import / include 位置参考现有 router 注册模式）

- [ ] **Step 5: 跑测试确认通过**

```bash
cd /home/son_goku/HaGoKu
pytest tests/test_api/test_quant_router.py -v
```

Expected: 3 passed。

- [ ] **Step 6: 提交**

```bash
git add hagoku/api/quant_router.py tests/test_api/test_quant_router.py hagoku/app.py
git commit -m "feat(api): /api/quant/datasets GET/POST endpoints"
```

---

## Task 11: /api/quant/datasets — 删除 + 刷新 + 单数据集读取

**Files:**
- Modify: `hagoku/api/quant_router.py`
- Modify: `tests/test_api/test_quant_router.py`

**步骤:**
- [ ] **Step 1: 追加测试 — 删除**

在 `tests/test_api/test_quant_router.py` 末尾追加：

```python
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
```

- [ ] **Step 2: 跑测试确认 404 PASS / 200 FAIL（路由不存在）**

```bash
cd /home/son_goku/HaGoKu
pytest tests/test_api/test_quant_router.py::test_delete_dataset_removes_directory -v
```

Expected: FAIL。

- [ ] **Step 3: 实现 DELETE 端点**

在 `hagoku/api/quant_router.py` 末尾添加：

```python
@router.delete("/datasets/{dataset_id}")
async def delete_dataset(dataset_id: str) -> dict:
    """删除一个数据集目录。"""
    ds_dir = DATASETS_ROOT / dataset_id
    if not ds_dir.exists():
        raise HTTPException(status_code=404, detail=f"数据集 {dataset_id} 不存在")
    import shutil
    shutil.rmtree(ds_dir)
    return {"ok": True, "deleted": dataset_id}
```

- [ ] **Step 4: 跑测试确认通过**

```bash
cd /home/son_goku/HaGoKu
pytest tests/test_api/test_quant_router.py -v
```

Expected: 5 passed。

- [ ] **Step 5: 追加测试 — 读单个数据集（项目引用时用）**

```python
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
```

测试 import `_json` 需要在文件顶部加：`import json as _json`

- [ ] **Step 6: 实现 GET 单个 parquet 端点**

```python
from fastapi.responses import Response

@router.get("/datasets/{dataset_id}/parquet")
async def get_dataset_parquet(dataset_id: str) -> Response:
    """返回 data.parquet 二进制（项目创建时复制用）。"""
    ds_dir = DATASETS_ROOT / dataset_id
    if not ds_dir.exists():
        raise HTTPException(status_code=404, detail=f"数据集 {dataset_id} 不存在")
    parquet_path = ds_dir / "data.parquet"
    if not parquet_path.exists():
        raise HTTPException(status_code=500, detail="数据集 parquet 缺失")
    return Response(
        content=parquet_path.read_bytes(),
        media_type="application/octet-stream",
    )
```

- [ ] **Step 7: 跑测试确认全部通过**

```bash
cd /home/son_goku/HaGoKu
pytest tests/test_api/test_quant_router.py -v
```

Expected: 6 passed。

- [ ] **Step 8: 提交**

```bash
git add hagoku/api/quant_router.py tests/test_api/test_quant_router.py
git commit -m "feat(api): /api/quant/datasets DELETE + GET parquet endpoints"
```

---

## Task 12: 项目创建 API 接受 scene 字段

**Files:**
- Modify: `hagoku/api/projects.py`（或同等文件 — 找现有 POST /api/projects handler）
- Modify: `hagoku/repository/project.py`（project.json schema 加 scene）

**Interfaces:**
- 现状 POST /api/projects 接受 `{name, description}`
- 期望: 增加可选 `{scene: "stock"}`，写入 project.json 的 `scene` 字段
- 默认 scene: `"general"`

**步骤:**
- [ ] **Step 1: 找现有 POST /api/projects handler**

```bash
grep -n "POST\|name.*description\|create.*project" hagoku/api/projects.py 2>/dev/null | head -20
```

确认 handler 位置。

- [ ] **Step 2: 修改 handler 接受 scene**

如果 handler 用 Pydantic BaseModel：
```python
class CreateProjectReq(BaseModel):
    name: str
    description: str = ""
    scene: str = "general"  # 新增，默认 general
```

修改 `_create_project` 函数（找现有 project.json 写入逻辑）：
```python
project_meta = {
    "name": req.name,
    "description": req.description,
    "scene": req.scene,  # 新增
    "created_at": datetime.utcnow().isoformat(),
}
```

（具体实现参考现有 schema，保持风格一致）

- [ ] **Step 3: 验证 scene 持久化**

写一个临时测试脚本：
```bash
cd /home/son_goku/HaGoKu
python -c "
from fastapi.testclient import TestClient
from hagoku.app import app
client = TestClient(app)
resp = client.post('/api/projects', json={'name': 'test_scene', 'description': '', 'scene': 'stock'})
print(resp.status_code, resp.json())
import json
proj = json.load(open('/tmp/test_scene/project.json'))
print('scene in meta:', proj.get('scene'))
"
```

Expected: scene 字段写入 project.json。

- [ ] **Step 4: 跑现有项目测试**

```bash
cd /home/son_goku/HaGoKu
pytest tests/test_api/ -v -k "project"
```

Expected: 既有测试全过（scene 默认 "general"，不影响）。

- [ ] **Step 5: 提交**

```bash
git add hagoku/api/projects.py hagoku/repository/project.py
git commit -m "feat(project): 创建项目接受 scene 字段（项目级 quant preset 选择）"
```

---

## Task 13: ProjectPanel 加场景下拉

**Files:**
- Modify: `hagoku_web/src/panels/ProjectPanel.tsx`

**Interfaces:**
- 现状：name + description + 创建按钮
- 期望：加 `场景` 下拉（源 = `/api/prompt-lab/presets`）
- 默认选项：当前 active_preset（从 `/api/prompt-lab/presets` 拿 `active` 字段）

**步骤:**
- [ ] **Step 1: 读 ProjectPanel.tsx 的 handleCreate 函数**

```bash
sed -n '333,355p' hagoku_web/src/panels/ProjectPanel.tsx
```

确认 fetch body 和 state 结构。

- [ ] **Step 2: 加 presets state 和 fetch effect**

在组件顶部加 state 和 effect：
```typescript
interface Preset {
  id: string;
  name: string;
  active?: boolean;
}

const [presets, set presets] = useState<Preset[]>([]);
const [selectedScene, setSelectedScene] = useState<string>("general");

useEffect(() => {
  fetch("/api/prompt-lab/presets")
    .then((r) => r.json())
    .then((data) => {
      const list = data.presets ?? [];
      set presets(list);
      const active = list.find((p: Preset) => p.active);
      if (active) setSelectedScene(active.id);
    });
}, []);
```

- [ ] **Step 3: 在 description input 下面加 scene select**

```tsx
{/* Scene field */}
<div>
  <label className="block text-ui-xs text-app-text-muted mb-1">场景</label>
  <select
    aria-label="分析场景"
    value={selectedScene}
    onChange={(e) => setSelectedScene(e.target.value)}
    className="w-full px-2.5 py-1.5 text-ui-sm bg-app-bg border border-app-border
               rounded font-mono text-app-text focus:outline-none focus:border-app-accent
               focus-visible:ring-1 focus-visible:ring-app-accent"
  >
    {presets.map((p) => (
      <option key={p.id} value={p.id}>{p.name}</option>
    ))}
  </select>
</div>
```

- [ ] **Step 4: 修改 handleCreate 把 scene 传到后端**

```typescript
await fetch("/api/projects", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({
    name: newName.trim(),
    description: newDesc.trim(),
    scene: selectedScene,   // 新增
  }),
});
```

- [ ] **Step 5: 验证 TypeScript 编译**

```bash
cd /home/son_goku/HaGoKu/hagoku_web
npx tsc --noEmit
```

Expected: 无错误。

- [ ] **Step 6: 提交**

```bash
git add hagoku_web/src/panels/ProjectPanel.tsx
git commit -m "feat(web): ProjectPanel 新建项目对话框加场景下拉"
```

---

## Task 14: AnalyzePanel 加「从量化数据集选取」选项

**Files:**
- Modify: `hagoku_web/src/panels/AnalyzePanel.tsx`

**Interfaces:**
- 现状：useFileUpload hook 处理 CSV 上传
- 期望：在现有上传 UI 旁加一个「从量化数据集选取」选项 → 弹下拉 → 调 `/api/quant/datasets/{id}/parquet` → 把数据复制进项目（写到当前项目 data path）

**步骤:**
- [ ] **Step 1: 找 AnalyzePanel 上传 UI 的位置**

```bash
grep -n "Upload\|上传\|handleUpload" hagoku_web/src/panels/AnalyzePanel.tsx | head -20
```

定位上传 UI 组件。

- [ ] **Step 2: 加 datasets state 和 fetch effect**

```typescript
interface DatasetMeta {
  id: string;
  market: string;
  symbol: string;
  period: string;
  interval: string;
  fetched_at: string;
  rows: number;
  source: string;
}

const [datasets, set datasets] = useState<DatasetMeta[]>([]);
const [showDatasetPicker, set showDatasetPicker] = useState(false);

useEffect(() => {
  fetch("/api/quant/datasets")
    .then((r) => r.json())
    .then((data) => set datasets(data.datasets ?? []));
}, []);
```

- [ ] **Step 3: 在上传 UI 旁加按钮**

```tsx
<div className="flex gap-2">
  {/* 现有上传按钮 */}
  <button onClick={/* 现有上传逻辑 */}>上传 CSV</button>

  {/* 新增：从量化数据集选取 */}
  <button
    onClick={() => set showDatasetPicker(true)}
    disabled={datasets.length === 0}
    className="..."
  >
    从量化数据集选取
  </button>
</div>
```

- [ ] **Step 4: 加下拉选择对话框（用现有 Modal/Portal 模式）**

```tsx
{showDatasetPicker && (
  <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
    <div className="bg-app-bg border border-app-border rounded-lg p-4 max-w-2xl w-full">
      <h3 className="text-ui-md mb-3">选择数据集</h3>
      <div className="max-h-96 overflow-y-auto space-y-1">
        {datasets.map((ds) => (
          <button
            key={ds.id}
            onClick={async () => {
              // 1. 拉 parquet
              const resp = await fetch(`/api/quant/datasets/${ds.id}/parquet`);
              const blob = await resp.blob();
              // 2. 上传到当前项目（用现有 upload 逻辑）
              const file = new File([blob], `${ds.symbol}.parquet`, { type: "application/octet-stream" });
              await handleUpload(file);
              set showDatasetPicker(false);
            }}
            className="w-full text-left p-2 hover:bg-app-bg-secondary rounded"
          >
            <div className="font-mono text-ui-sm">
              {ds.market} · {ds.symbol} · {ds.period} · {ds.interval}
            </div>
            <div className="text-ui-xs text-app-text-muted">
              {ds.fetched_at} · {ds.rows} 行 · {ds.source}
            </div>
          </button>
        ))}
      </div>
      <button onClick={() => set showDatasetPicker(false)} className="mt-3 ...">
        取消
      </button>
    </div>
  </div>
)}
```

- [ ] **Step 5: 验证 TypeScript 编译**

```bash
cd /home/son_goku/HaGoKu/hagoku_web
npx tsc --noEmit
```

Expected: 无错误。

- [ ] **Step 6: 提交**

```bash
git add hagoku_web/src/panels/AnalyzePanel.tsx
git commit -m "feat(web): AnalyzePanel 加「从量化数据集选取」选项"
```

---

## Task 15: QuantDatasetsPanel 组件（列表 + 新建 + 刷新 + 删除）

**Files:**
- Create: `hagoku_web/src/panels/QuantDatasetsPanel.tsx`
- Create: `hagoku_web/src/panels/QuantDatasetsPanel/NewPullDialog.tsx`

**Interfaces:**
- Props: 无（顶级 panel）
- State: `datasets: DatasetMeta[]`, `showNewDialog: boolean`, `loading: boolean`
- 调用: GET / POST / DELETE /api/quant/datasets

**步骤:**
- [ ] **Step 1: 写 NewPullDialog 子组件**

`hagoku_web/src/panels/QuantDatasetsPanel/NewPullDialog.tsx`:

```tsx
import { useState } from "react";

interface Props {
  onClose: () => void;
  onSuccess: (dsid: string) => void;
}

export function NewPullDialog({ onClose, onSuccess }: Props) {
  const [market, set market] = useState<"a_stock" | "crypto">("a_stock");
  const [symbol, set symbol] = useState("");
  const [period, set period] = useState("1y");
  const [interval, set interval] = useState<"d1" | "h1">("d1");
  const [loading, set loading] = useState(false);
  const [error, set error] = useState<string | null>(null);

  const handleSubmit = async () => {
    if (!symbol.trim()) return;
    set loading(true);
    set error(null);
    try {
      const resp = await fetch("/api/quant/datasets", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ market, symbol: symbol.trim(), period, interval }),
      });
      if (!resp.ok) {
        const body = await resp.json();
        throw new Error(body.detail ?? "拉取失败");
      }
      const data = await resp.json();
      onSuccess(data.dataset_id);
      onClose();
    } catch (e) {
      set error(e instanceof Error ? e.message : String(e));
    } finally {
      set loading(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-app-bg border border-app-border rounded-lg p-4 max-w-md w-full">
        <h3 className="text-ui-md mb-3">新建量化数据集</h3>
        <div className="space-y-3">
          <div>
            <label className="text-ui-xs text-app-text-muted">市场</label>
            <div className="flex gap-2 mt-1">
              <button onClick={() => set market("a_stock")} className={market === "a_stock" ? "btn-primary" : "btn-secondary"}>A 股</button>
              <button onClick={() => set market("crypto")} className={market === "crypto" ? "btn-primary" : "btn-secondary"}>加密货币</button>
            </div>
          </div>
          <div>
            <label className="text-ui-xs text-app-text-muted">代码</label>
            <input
              type="text"
              value={symbol}
              onChange={(e) => set symbol(e.target.value)}
              placeholder={market === "a_stock" ? "600519" : "BTC-USDT"}
              className="w-full px-2 py-1 border border-app-border rounded font-mono"
              autoFocus
            />
          </div>
          <div>
            <label className="text-ui-xs text-app-text-muted">区间</label>
            <select value={period} onChange={(e) => set period(e.target.value)} className="w-full px-2 py-1 border border-app-border rounded">
              <option value="30d">最近 30 天</option>
              <option value="90d">最近 90 天</option>
              <option value="1y">最近 1 年</option>
            </select>
          </div>
          <div>
            <label className="text-ui-xs text-app-text-muted">周期</label>
            <select value={interval} onChange={(e) => set interval(e.target.value as "d1" | "h1")} className="w-full px-2 py-1 border border-app-border rounded">
              <option value="d1">日线</option>
              <option value="h1">小时线</option>
            </select>
          </div>
          {error && (
            <pre className="text-ui-xs text-app-error whitespace-pre-wrap bg-app-bg-secondary p-2 rounded">
              {error}
            </pre>
          )}
        </div>
        <div className="flex gap-2 mt-4 justify-end">
          <button onClick={onClose} disabled={loading} className="btn-secondary">取消</button>
          <button onClick={handleSubmit} disabled={loading || !symbol.trim()} className="btn-primary">
            {loading ? "拉取中..." : "拉取"}
          </button>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: 写主面板组件**

`hagoku_web/src/panels/QuantDatasetsPanel.tsx`:

```tsx
import { useEffect, useState } from "react";
import { Plus, RefreshCw, Trash2 } from "lucide-react";
import { NewPullDialog } from "./QuantDatasetsPanel/NewPullDialog";
import { PanelHeader } from "../components/PanelHeader";

interface DatasetMeta {
  id: string;
  market: string;
  symbol: string;
  period: string;
  interval: string;
  fetched_at: string;
  rows: number;
  source: string;
}

export default function QuantDatasetsPanel() {
  const [datasets, set datasets] = useState<DatasetMeta[]>([]);
  const [showNewDialog, set showNewDialog] = useState(false);
  const [loading, set loading] = useState(false);

  const loadDatasets = async () => {
    set loading(true);
    try {
      const resp = await fetch("/api/quant/datasets");
      const data = await resp.json();
      set datasets(data.datasets ?? []);
    } finally {
      set loading(false);
    }
  };

  useEffect(() => {
    loadDatasets();
  }, []);

  const handleDelete = async (dsId: string) => {
    if (!confirm(`确认删除数据集 ${dsId}？`)) return;
    await fetch(`/api/quant/datasets/${dsId}`, { method: "DELETE" });
    await loadDatasets();
  };

  const handleRefresh = async (dsId: string) => {
    // 刷新 = 拉新数据生成新数据集（保留历史）
    const ds = datasets.find((d) => d.id === dsId);
    if (!ds) return;
    await fetch("/api/quant/datasets", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        market: ds.market, symbol: ds.symbol, period: ds.period, interval: ds.interval,
      }),
    });
    await loadDatasets();
  };

  return (
    <div className="h-full flex flex-col bg-app-bg text-app-text">
      <PanelHeader title="量化数据集">
        <button
          onClick={() => set showNewDialog(true)}
          className="flex items-center gap-1 px-2 py-0.5 text-ui-xs bg-app-accent
                     hover:bg-app-accent-hover text-white rounded cursor-pointer"
        >
          <Plus size={12} />
          新建拉取
        </button>
      </PanelHeader>

      <div className="flex-1 overflow-y-auto p-4 space-y-2">
        {loading && datasets.length === 0 && (
          <div className="text-ui-xs text-app-text-muted">加载中...</div>
        )}
        {!loading && datasets.length === 0 && (
          <div className="text-ui-xs text-app-text-muted">
            还没有数据集。点右上「+ 新建拉取」开始。
          </div>
        )}
        {datasets.map((ds) => (
          <div key={ds.id} className="bg-app-bg-secondary border border-app-border rounded p-3">
            <div className="font-mono text-ui-sm">
              {ds.market} · {ds.symbol} · {ds.period} · {ds.interval}
            </div>
            <div className="text-ui-xs text-app-text-muted mt-1">
              {ds.fetched_at} · {ds.rows} 行 · {ds.source}
            </div>
            <div className="flex gap-2 mt-2">
              <button onClick={() => handleRefresh(ds.id)} className="btn-secondary text-ui-xs">
                <RefreshCw size={11} /> 刷新
              </button>
              <button onClick={() => handleDelete(ds.id)} className="btn-danger text-ui-xs">
                <Trash2 size={11} /> 删除
              </button>
            </div>
          </div>
        ))}
      </div>

      {showNewDialog && (
        <NewPullDialog
          onClose={() => set showNewDialog(false)}
          onSuccess={() => loadDatasets()}
        />
      )}
    </div>
  );
}
```

- [ ] **Step 3: 验证 TypeScript 编译**

```bash
cd /home/son_goku/HaGoKu/hagoku_web
npx tsc --noEmit
```

Expected: 无错误。

- [ ] **Step 4: 提交**

```bash
git add hagoku_web/src/panels/QuantDatasetsPanel.tsx hagoku_web/src/panels/QuantDatasetsPanel/
git commit -m "feat(web): QuantDatasetsPanel + NewPullDialog 组件"
```

---

## Task 16: App.tsx 注册新 tab 路由

**Files:**
- Modify: `hagoku_web/src/App.tsx`

**Interfaces:**
- 现状：tabs 包括 "项目"、"分析"、"Prompt Lab" 等
- 期望：加 "量化数据集" tab → 渲染 `<QuantDatasetsPanel />`

**步骤:**
- [ ] **Step 1: 读 App.tsx 的 tabs 配置**

```bash
grep -n "tab\|panel\|<.*Panel" hagoku_web/src/App.tsx | head -30
```

定位 tab 切换逻辑。

- [ ] **Step 2: 导入 QuantDatasetsPanel**

```typescript
import QuantDatasetsPanel from "./panels/QuantDatasetsPanel";
```

- [ ] **Step 3: 加 tab 条目和路由分支**

在 tabs 数组加：
```typescript
{ id: "quant-datasets", label: "量化数据集" }
```

在 panel 渲染分支加：
```tsx
{activeTab === "quant-datasets" && <QuantDatasetsPanel />}
```

（具体模式参考现有 tab 切换代码）

- [ ] **Step 4: 验证 TypeScript 编译**

```bash
cd /home/son_goku/HaGoKu/hagoku_web
npx tsc --noEmit
```

Expected: 无错误。

- [ ] **Step 5: 提交**

```bash
git add hagoku_web/src/App.tsx
git commit -m "feat(web): App.tsx 注册「量化数据集」tab 路由"
```

---

## Task 17: 端到端手工测试 + self_check

**Files:** 无（纯验证）

**步骤:**
- [ ] **Step 1: 启动 backend**

```bash
cd /home/son_goku/HaGoKu
python -m hagoku  # 或对应启动命令
```

Expected: backend 在 :8000 启动。

- [ ] **Step 2: 启动 frontend**

```bash
cd /home/son_goku/HaGoKu/hagoku_web
npm run dev
```

Expected: frontend 在 :5173 启动。

- [ ] **Step 3: 浏览器跑完整工作流**

1. 打开 http://localhost:5173
2. 切到「量化数据集」tab → 点「+ 新建拉取」 → 选 A 股 / 600519 / 1y / 日线 → 拉取
3. 验证：列表多一行卡片，显示 245 行左右
4. 切到「项目」tab → 新建项目 → 项目名 + 场景选「量化分析」→ 创建
5. 进分析页面 → 点「从量化数据集选取」→ 选刚才的数据集 → 数据进项目
6. 输入框问：「做个动量策略回测，20 日均线上买下卖」
7. 验证：LLM 调 run_backtest → 出回测报告
8. 切回「量化数据集」tab → 刷新 / 删除刚才的数据集 → 验证操作
9. 验证：分析项目里的数据**不变**（副本模式生效）

- [ ] **Step 4: 跑 self_check.sh**

```bash
cd /home/son_goku/HaGoKu
bash scripts/ci/self_check.sh
```

Expected: 全绿。

- [ ] **Step 5: 跑全量 pytest**

```bash
cd /home/son_goku/HaGoKu
pytest tests/ -q
```

Expected: 全绿（既有 223 + 新增 ~12）。

- [ ] **Step 6: 提交任何遗漏的修复**

```bash
git add -A
git commit -m "chore: 3.0 端到端验证通过 — 任何遗留修复" --allow-empty
```

---

## 验收清单

3.0 完成 = 满足以下全部：

- [ ] `pyproject.toml` 含 akshare + ccxt
- [ ] `hagoku/agents/presets/quant.md` 存在，`stock.md` 已删
- [ ] `presets.json` 中 stock 的 display name 为「量化分析」
- [ ] `doctor_router.py:373` 硬编码 JSON 已删除，调 presets.json
- [ ] `fetch_market_data` 工具实现 + 测试通过（akshare + ccxt + 缓存 + 重试 + 错误格式）
- [ ] `run_backtest` 工具实现 + 测试通过（基础回测 + 止损止盈 + 表达式错误）
- [ ] 两个工具注册到 `agent_tools`
- [ ] `/api/quant/datasets` GET/POST/DELETE/parquet endpoints 全实现
- [ ] POST /api/projects 接受 `scene` 字段
- [ ] ProjectPanel 加场景下拉
- [ ] AnalyzePanel 加「从量化数据集选取」
- [ ] QuantDatasetsPanel + NewPullDialog 实现
- [ ] App.tsx 注册新 tab
- [ ] pytest 全绿（既有 + 新增）
- [ ] self_check.sh 全绿
- [ ] 浏览器手工跑通完整 quant 工作流