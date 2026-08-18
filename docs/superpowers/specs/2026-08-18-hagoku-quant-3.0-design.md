# HaGoKu 3.0 — 量化数据集（Quant Datasets）

> **版本**：3.0（设计文档）
> **日期**：2026-08-18
> **状态**：草案，待 review

---

## 1. 背景与目标

### 1.1 现状

HaGoKu Studio 当前是「通用商业分析 + 电商运营 + 股市技术分析」三 preset 的数据分析平台。quant（系统化、可回测、因子驱动）能力缺失——既有「股市技术」preset 偏描述性叙事分析，无回测、无数据接入。

用户的实际 quant 工作流：

1. 拉取标的行情数据（akshare / ccxt）
2. 清洗 + 字段理解
3. 写策略（因子 / 信号 / 规则）
4. 跑回测看收益曲线 + 风险指标
5. 解读结果，调整策略

当前 HaGoKu 只能支持步骤 2（清洗）和 5（解读）。1/3/4 全缺。

### 1.2 目标

3.0 = **量化数据集**（侧边栏）+ **数据接入工具** + **回测工具** + **quant preset**。

不破坏现有架构：
- 单 DataAnalystAgent 不变
- 12 个现有工具不动
- 分析窗口不动
- Session 持久化机制复用
- preset 哲学贯彻（一个 lens 一件事）

### 1.3 核心信条（贯穿设计）

| 信条 | 含义 | 反映到设计 |
|---|---|---|
| 通道 × 提示词 = 多维度分析 | 同一引擎不同 preset = 不同领域 | 新 quant preset 是「quant lens」 |
| 工具即 I/O | 工具只做机械执行，不带流程信号 | fetch_market_data、run_backtest 都是纯 I/O |
| 减法是唯一方向 | 不加不必要的依赖 / 模块 / 工具 | 回测用现有 pandas/numpy，不加新库 |
| 0 硬编码 | 不预设语义，让 LLM 决定 | run_backtest 只输出机械量，LLM 推导金融指标 |
| 数据可靠性 = 第一位 | 没有数据，再好的分析也无用 | 清晰错误 + 网络重试 + 数据集库独立持久化 |
| 用户能力局限 | 用户看不懂 akshare 内部错误 | 工具翻译为可行动指引 |

---

## 2. 范围

### 2.1 3.0 做

- ✅ **量化数据集侧边栏**（新 UI 标签页）
  - 列表展示所有已保存数据集
  - 「新建拉取」/「刷新」/「删除」操作
- ✅ **fetch_market_data 工具**（LLM 可调用）
  - A 股（akshare）+ 加密货币（ccxt）
  - 会话内缓存 + 网络重试 + 清晰错误
  - 写入「量化数据集」库
- ✅ **run_backtest 工具**（LLM 可调用）
  - 结构化策略 spec（pandas 表达式）
  - 纯机械量输出，无金融指标命名
  - LLM 推导 Sharpe / MaxDD / 年化等
- ✅ **新增项目对话框** UI 改造
  - 数据源三选一：CSV / 选取数据集 / 拉取新数据
  - 场景下拉（源 = presets.json）
- ✅ **stock preset → quant preset 重写**
  - id 保持 `"stock"`（无迁移成本）
  - display name `股市技术分析` → `量化分析`
  - 内容：原 stock + 量化词汇 + 新工具调用指引
- ✅ **doctor_router.py:373 硬编码清理**（顺手）

### 2.2 3.0 不做

- ❌ 落盘缓存层（数据集库 = 持久化，足够）
- ❌ 数据集与项目 live 绑定（项目拿副本，保复现性）
- ❌ 自动定时刷新 / 后台拉取
- ❌ 多标批量拉取
- ❌ 数据集版本管理
- ❌ 场景自动检测（用户手动下拉选）
- ❌ 实时行情（只做历史 EOD）
- ❌ 基本面数据 / 财务数据（仅 OHLCV）
- ❌ 加新 agent / 新增除 fetch / backtest 外的工具

### 2.3 推迟到 3.1+

- 限流层（撞限流时再加）
- 备用数据源 fallback
- 多标批量拉取
- 数据集版本管理 + diff
- 实时行情接入
- 基本面 / 财务数据接入
- 因子库预定义（alpha101 之类）

---

## 3. 架构总览

```
┌─────────────────────────────────────────────────────────────────┐
│                    HaGoKu 3.0 架构                                │
└─────────────────────────────────────────────────────────────────┘

[前端 UI]
  │
  ├── ProjectPanel (项目列表 + 场景)        ← 现状
  ├── AnalyzePanel (分析窗口 + 报告)        ← 不动
  ├── QuantDatasetsPanel (量化数据集) ← 新增 tab
  │   ├── 列表: ~/.hagoku/datasets/* (parquet + meta.json)
  │   ├── 新建拉取 → 调用 /api/quant/fetch
  │   ├── 刷新     → 重新拉取覆盖
  │   └── 删除     → 删目录
  │
  └── NewProjectDialog (新增项目)            ← 改造
        ├── 数据源: CSV / 数据集 / 拉取新
        ├── 场景:  ▼ 通用 / 量化 / 电商 (源=presets.json)
        └── 创建 → 项目状态含数据副本

[后端 API]
  │
  ├── /api/quant/datasets         GET    列表
  ├── /api/quant/datasets         POST   新建（market, symbol, period, interval）
  ├── /api/quant/datasets/{id}    DELETE 删除
  ├── /api/quant/datasets/{id}/refresh POST  刷新
  ├── /api/projects                POST   创建（接受 dataset_id 引用）
  └── /api/prompt-lab/presets      GET    （现状不动，前端直接读）

[后端 工具层]
  │
  ├── fetch_market_data(market, symbol, period, interval) → ok dict
  │   ├── 会话内缓存 (in-memory dict, 进程生命周期)
  │   ├── 网络重试 (3 次指数退避, ConnectionError/Timeout)
  │   ├── 失败 → RuntimeError 带原始错误 + 操作建议
  │   └── 写入 ~/.hagoku/datasets/<id>/{data.parquet, meta.json}
  │
  └── run_backtest(strategy_spec, data) → {
        equity_curve: Series,
        trades: List[dict],
        positions: Series,
        returns: Series,
        periods_per_year: int,
        summary: { total_return, n_periods, n_trades,
                   n_positive_trades, n_negative_trades,
                   mean_trade_pnl }
      }

[预设层]
  └── presets.json: { general, stock→改名quant, ecommerce }
  └── presets/quant.md: 重写（量化词汇 + 新工具调用指引）
  └── active_preset: id="stock" 不变（用户文件无需迁移）

[数据层]
  └── ~/.hagoku/datasets/<id>/{data.parquet, meta.json}
  └── ~/.hagoku/projects/<id>/ (现有)
  └── ~/.hagoku/active_preset (现有)
```

---

## 4. 模块详细规格

### 4.1 量化数据集（Quant Datasets）侧边栏

#### 4.1.1 数据集标识

每个数据集一个独立目录，目录名由参数拼出：

```
~/.hagoku/datasets/{market}__{symbol}__{period}__{interval}__{fetched_at}/
├── data.parquet       # OHLCV DataFrame，列: date/open/high/low/close/volume
└── meta.json          # 元数据
```

**meta.json 格式**：

```json
{
  "id": "a_stock__600519__1y__d1__20260818",
  "market": "a_stock",
  "symbol": "600519",
  "period": "1y",
  "interval": "d1",
  "fetched_at": "2026-08-18T10:00:00Z",
  "rows": 245,
  "source": "akshare",
  "source_version": "1.13.0"
}
```

**注意**：`id` = `{market}__{symbol}__{period}__{interval}__{fetched_at}`，按此拼出目录名。这意味着：
- 同一 (market, symbol, period, interval) 多次拉取 = 多个目录（每次有独立的 fetched_at）
- 用户主动「刷新」可选择：新建目录（保留历史）或覆盖现有（最新覆盖）
- **3.0 决定**：刷新 = 创建新目录（不覆盖），删除由用户手动控制

#### 4.1.2 侧边栏 UI

位置：ProjectPanel 旁的标签页（不独立路由）

```
┌─────────────────────────────────────────────┐
│ [项目] [分析] [量化数据集]  ← 新标签        │
├─────────────────────────────────────────────┤
│ 量化数据集                       [新建拉取] │
├─────────────────────────────────────────────┤
│ ┌─────────────────────────────────────────┐ │
│ │ A 股 · 600519 · 1y · d1          [⋯]   │ │
│ │ 2026-08-18 10:00 · 245 行 · akshare    │ │
│ │                          [刷新] [删除]  │ │
│ └─────────────────────────────────────────┘ │
│ ┌─────────────────────────────────────────┐ │
│ │ 加密 · BTC-USDT · 90d · h1       [⋯]   │ │
│ │ 2026-08-15 14:30 · 2160 行 · ccxt      │ │
│ │                          [刷新] [删除]  │ │
│ └─────────────────────────────────────────┘ │
└─────────────────────────────────────────────┘
```

#### 4.1.3 「新建拉取」对话框

```
┌─────────────────────────────────┐
│ 新建量化数据集                [×] │
├─────────────────────────────────┤
│ 市场: ○ A 股   ○ 加密货币      │
│ 代码: [______________]         │
│ 区间: [▼最近 1y / 自定义]      │
│ 周期: [▼日线 d1 / 小时 h1]     │
│                                 │
│ 预览: akshare.stock_zh_a_hist  │
│       (600519, adjust=qfq)     │
│                                 │
│            [取消]  [拉取]      │
└─────────────────────────────────┘
```

参数映射：
- 市场：`a_stock` / `crypto`
- 代码：用户输入（如 `600519` 或 `BTC-USDT`）
- 区间：预设（`1y` / `90d` / `30d` / 自定义日期范围）
- 周期：`d1`（日）/ `h1`（小时）

---

### 4.2 fetch_market_data 工具

#### 4.2.1 接口

```python
def fetch_market_data(
    market: str,         # "a_stock" | "crypto"
    symbol: str,         # "600519" | "BTC-USDT"
    period: str,         # "1y" | "90d" | "30d" | "2025-01-01,2026-08-18"
    interval: str,       # "d1" | "h1"
    ctx: dict,           # 框架上下文（含 _project_name 等）
) -> dict:
    """
    返回:
    {
        "ok": True,
        "dataset_id": "a_stock__600519__1y__d1__20260818",
        "rows": 245,
        "columns": ["date","open","high","low","close","volume"],
        "saved_to": "~/.hagoku/datasets/a_stock__600519__1y__d1__20260818/",
        "fetched_at": "2026-08-18T10:00:00Z"
    }
    """
```

#### 4.2.2 内部流程

```
1. 查会话内缓存
   key = (market, symbol, period, interval)
   命中 → return cached df（库已有，不重复写）

2. 未命中 → 网络重试拉取
   for attempt in 1..3:
       try:
           if market == "a_stock":
               df = _fetch_akshare(symbol, period, interval)
           elif market == "crypto":
               df = _fetch_ccxt(symbol, period, interval)
           break
       except (ConnectionError, Timeout) as e:
           if attempt == 3: raise
           sleep(2 ** attempt)

3. 标准化列名 → date/open/high/low/close/volume
   (akshare 中文列名 → 英文映射；ccxt 数组 → DataFrame)

4. 写入数据集库
   dir = ~/.hagoku/datasets/<id>/
   df.to_parquet(dir/data.parquet)
   meta.json 写入元数据

5. 写入会话内缓存
   _session_cache[key] = df

6. return ok dict
```

#### 4.2.3 失败错误信息

```python
except Exception as e:
    raise RuntimeError(
        f"akshare 获取 {symbol} 失败。\n"
        f"原始错误: {type(e).__name__}: {e}\n"
        f"建议:\n"
        f"  1. 升级 akshare: pip install -U akshare\n"
        f"  2. 用上传 CSV 方式提供数据\n"
        f"  3. 切换到加密货币试试 (ccxt 接口更稳定)\n"
        f"  4. 检查网络/防火墙设置"
    )
```

**不兜底**（铁律 7）：失败抛 RuntimeError，原始异常 + 4 条建议。

#### 4.2.4 工具描述（给 LLM 看）

```
从 akshare（A 股）或 ccxt（加密货币）拉取历史 OHLCV 行情数据。
输入市场类型、代码、起止区间、周期；返回标准化 DataFrame（写入「量化数据集」库）。
何时用：用户要分析 A 股或加密货币，但没有现成 CSV。
注意：网络失败会抛错；akshare 接口升级可能破坏历史调用。
```

**不写「你必须先调这个」**（铁律 G 不写禁止 / 不写「应该」）。

---

### 4.3 run_backtest 工具

#### 4.3.1 接口

```python
def run_backtest(
    strategy_spec: dict,
    ctx: dict,
    _df: pd.DataFrame,    # 框架注入当前项目 DataFrame
) -> dict:
    """
    strategy_spec 格式：
    {
        "name": str,                      # 策略名（人类可读）
        "entry": str,                     # pandas 表达式: "close > close.rolling(20).mean()"
        "exit": str,                      # pandas 表达式: "close < close.rolling(10).mean()"
        "stop_loss": float                # 可选, 例如 0.05（默认无）
        "take_profit": float              # 可选, 例如 0.20（默认无）
    }

    3.0 简化为 all_in 仓位管理（信号触发即全仓进出）。
    kelly / fixed_fraction 等仓位管理在 3.1 引入。
    """

    返回:
    {
        "name": str,
        "equity_curve": Series,
        "trades": List[dict],
        "positions": Series,
        "returns": Series,
        "periods_per_year": int,          # 自动推断: d1→252, h1→24*365
        "summary": {
            "total_return": float,
            "n_periods": int,
            "n_trades": int,
            "n_positive_trades": int,
            "n_negative_trades": int,
            "mean_trade_pnl": float
        }
    }
    """
```

#### 4.3.2 内部实现

**step 1: 校验 spec**

```python
required = ["name", "entry", "exit"]
for k in required:
    if k not in strategy_spec:
        raise ValueError(f"strategy_spec 缺少字段: {k}")
```

**step 2: 求值表达式**

```python
df = _df.copy()
signals = df.copy()

try:
    signals["entry_signal"] = df.eval(strategy_spec["entry"])
    signals["exit_signal"] = df.eval(strategy_spec["exit"])
except Exception as e:
    raise RuntimeError(
        f"策略表达式求值失败。\n"
        f"entry: {strategy_spec['entry']}\n"
        f"exit: {strategy_spec['exit']}\n"
        f"原始错误: {e}\n"
        f"提示: 表达式必须是合法的 pandas 表达式，列名引用当前数据 DataFrame。"
    )
```

**step 3: 推断 periods_per_year**（从 df 自身的时间间隔推断，不依赖外部参数）

```python
if len(df) > 1:
    delta = df["date"].iloc[1] - df["date"].iloc[0]
    seconds = delta.total_seconds()
    if seconds >= 86400 * 0.9:        # ~ 日线
        periods_per_year = 252
    elif seconds >= 3600 * 0.9:       # ~ 小时线
        periods_per_year = 24 * 365
    else:                              # 分钟/秒级（3.0 不直接拉，但兜底）
        periods_per_year = 252
else:
    periods_per_year = 252  # 默认
```

**step 4: 模拟交易（事件驱动简化版）**

```python
positions = []  # Series of {0, 1}：0=空仓，1=持仓
trades = []
in_position = False
entry_price = None
entry_time = None
stop_loss = strategy_spec.get("stop_loss")       # 可选
take_profit = strategy_spec.get("take_profit")   # 可选

for i, row in df.iterrows():
    exit_now = False
    exit_reason = "signal"

    if in_position:
        # 检查止损止盈
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

# 权益曲线（3.0 简化版）：初始 10000，最终权益 = 10000 + 累计盈亏
# 3.0 不做精细bar-by-bar浮动盈亏计算（避免 LLM 误用权益曲线形状）
final_pnl = sum(t["pnl"] for t in trades) if trades else 0
equity = pd.Series(10000.0 + final_pnl, index=df.index)
returns = equity.pct_change().fillna(0)
```

**step 5: 算 summary（纯机械量）**

```python
summary = {
    "total_return": float((equity_curve.iloc[-1] / equity_curve.iloc[0]) - 1),
    "n_periods": int(len(df)),
    "n_trades": int(len(trades)),
    "n_positive_trades": int(sum(1 for t in trades if t["pnl"] > 0)),
    "n_negative_trades": int(sum(1 for t in trades if t["pnl"] <= 0)),
    "mean_trade_pnl": float(np.mean([t["pnl"] for t in trades])) if trades else 0.0,
}
```

#### 4.3.3 LLM 推导金融指标（不写在代码里）

LLM 拿到上面的输出后，自己用数学推理 + get_column_stats：

```python
# Sharpe
sharpe = summary["mean_return"] / summary["std_return"] * sqrt(periods_per_year)
# 其中 mean_return / std_return 通过 get_column_stats(returns) 获得

# MaxDD
# LLM 扫描 equity_curve 找峰谷；或对 equity_curve 求 running max 后算 drawdown

# Annual Return
annual_return = (1 + summary["total_return"]) ** (periods_per_year / summary["n_periods"]) - 1

# Win Rate
win_rate = summary["n_positive_trades"] / summary["n_trades"] if summary["n_trades"] > 0 else 0
```

**为什么 LLM 推导**：0 硬编码。无 "Sharpe" / "MaxDD" / "WinRate" 命名出现在代码里。

**LLM 数学风险**：
- 简单运算（Sharpe, Win Rate, Annual Return）：可靠
- 复杂运算（MaxDD on 长序列）：LLM 可声明"只能给出大致范围"，或多次调用 get_column_stats 拼凑
- **3.0 不做**：专门 `compute_drawdown(series)` 工具——保持工具集精简

#### 4.3.4 工具描述（给 LLM 看）

```
按 strategy_spec 在当前项目数据上模拟交易，输出权益曲线 / 交易明细 / 机械统计。
输入策略名 + 入场/出场 pandas 表达式 + 仓位管理 + 可选止损止盈。
返回纯机械量，Sharpe / MaxDD 等金融指标由你（LLM）从机械量推导。
何时用：用户定义了交易策略，想看历史回测效果。
注意：表达式必须是合法 pandas 表达式，引用当前数据列名。
```

---

### 4.4 新增项目对话框改造

#### 4.4.1 当前流程（保留）

```
项目名: [_____]
数据源: ○ 上传 CSV  ← 现状
        ○ 拉取行情   ← 现状
场景: ▼ 通用商业分析  ← 现状（来自 presets.json）
[创建]
```

#### 4.4.2 3.0 流程

```
项目名: [_____]
数据源: ○ 上传 CSV
        ○ 从量化数据集选取     ← 新
        ○ 拉取新数据           ← 重命名（原「拉取行情」）
场景: ▼ 通用商业分析 / 量化分析 / 电商运营分析
[创建]
```

**「从量化数据集选取」子流程**：
- 弹下拉，列出所有数据集
- 用户选一个
- 创建项目时**复制数据集内容**进项目状态（独立副本）

**「拉取新数据」子流程**：
- 等同 4.1.3「新建拉取」对话框
- 创建项目时**立即拉取**，写入数据集库 + 项目副本

#### 4.4.3 场景下拉

- 数据源：`presets.json` 全文（动态同步）
- 选中即写入 `~/.hagoku/active_preset`

**不做自动检测**（铁律 0 硬编码：不让代码判断场景）。

---

### 4.5 quant preset 重写

#### 4.5.1 文件变化

- 新增：`hagoku/agents/presets/quant.md`（重写内容）
- 删除：`hagoku/agents/presets/stock.md`
- 改：`hagoku/agents/presets/presets.json`
  - `id: "stock"` 不变
  - `name: "股市技术分析"` → `"量化分析"`
  - `description: "趋势分解、波动率检验"` → `"系统化量化分析：因子、回测、风险拆解"`
  - `file: "stock.md"` → `"quant.md"`
- 改：`hagoku/api/doctor_router.py:373`
  - 删硬编码 JSON 字符串
  - 改为 `json.loads((PRESETS_DIR / "presets.json").read_text())`

#### 4.5.2 迁移

- `~/.hagoku/active_preset` 写的是 id `"stock"`
- id 不变 → **无需迁移**
- 用户已有的「stock」选择自动变成「量化分析」

#### 4.5.3 quant.md 内容大纲

```
你是 HaGoKu Studio 的量化分析师...

数据来源：通常从「量化数据集」侧边栏拉取的 OHLCV 行情；
         也可能用户上传 CSV；也可能通过 fetch_market_data 即时拉取。

工作流程：
 1. 理解数据字段（date/open/high/low/close/volume 已是标准列名）
 2. 评估数据质量（缺失值、异常值、复权一致性）
 3. 定义策略（用 pandas 表达式）
 4. 调用 run_backtest 验证
 5. 解读结果（Sharpe / MaxDD / Annual Return / Win Rate 等由你推导）

常用工具：
 - fetch_market_data: 拉新行情（A 股用 akshare，加密货币用 ccxt）
 - run_backtest: 跑策略回测
 - get_column_stats / get_group_stats: 基础统计

分析目标：
 - 找到能解释收益的因子
 - 评估策略风险（最大回撤、波动率）
 - 给用户可执行的策略建议
```

---

## 5. 数据流

### 5.1 用户拉取数据 + 创建项目

```
用户                                  前端                      后端                     文件系统
 │                                  │                          │                          │
 │─ 切到「量化数据集」标签 ─────────→│                          │                          │
 │─ 点「新建拉取」 ─────────────────→│                          │                          │
 │─ 填表（市场/代码/区间/周期） ────→│                          │                          │
 │─ 点「拉取」 ─────────────────────→│ /api/quant/datasets POST│                          │
 │                                  │                          │─ 检查会话内缓存          │
 │                                  │                          │─ akshare.fetch(...)      │
 │                                  │                          │─ 标准化列名              │
 │                                  │                          │─ 写 parquet ─────────────→│ data.parquet
 │                                  │                          │─ 写 meta.json ──────────→│ meta.json
 │                                  │                          │─ 写会话内缓存            │
 │← 列表刷新 ──────────────────────│                          │                          │
 │                                  │                          │                          │
 │─ 切回「项目」标签，点「新建」 ───→│                          │                          │
 │─ 数据源选「从量化数据集选取」 ──→│                          │                          │
 │─ 弹下拉，选刚才的数据集 ────────→│                          │                          │
 │─ 场景选「量化分析」 ─────────────→│                          │                          │
 │─ 点「创建」 ─────────────────────→│ /api/projects POST       │                          │
 │                                  │                          │─ 读 parquet ────────────←│ data.parquet
 │                                  │                          │─ 复制进新项目状态         │
 │                                  │                          │─ 写项目文件 ─────────────→│ project.json + data
 │← 跳转到分析窗口 ────────────────│                          │                          │
```

### 5.2 LLM 调 fetch_market_data

```
LLM                            框架                    fetch_market_data                文件系统
 │                              │                          │                              │
 │─ tool_call fetch_market_data→│                          │                              │
 │  (a_stock, 600519, 1y, d1)   │                          │                              │
 │                              │─ 查会话内缓存            │                              │
 │                              │─ miss → 调 fetch ──────→│                              │
 │                              │                          │─ 网络重试 (3 次)            │
 │                              │                          │─ akshare.fetch              │
 │                              │                          │─ 标准化列名                  │
 │                              │                          │─ 写数据集库 ────────────────→│ parquet + meta
 │                              │                          │─ 写会话内缓存                │
 │                              │← ok dict ───────────────│                              │
 │← tool_result ───────────────│                          │                              │
 │   {ok, dataset_id, rows}     │                          │                              │
 │                              │                          │                              │
 │ (后续工具调用如 get_column_stats│                          │                              │
 │  在项目 DataFrame 上操作)    │                          │                              │
```

### 5.3 LLM 调 run_backtest

```
LLM                            框架                    run_backtest
 │                              │                          │
 │─ tool_call run_backtest ───→│                          │
 │  (strategy_spec)             │                          │
 │                              │─ 注入项目 DataFrame ───→│
 │                              │                          │─ 校验 spec
 │                              │                          │─ df.eval(entry/exit)
 │                              │                          │─ 模拟交易
 │                              │                          │─ 算 summary（机械量）
 │← tool_result ──────────────│← ok dict ───────────────│
 │   {equity_curve, trades,    │
 │    summary...}              │
 │                              │
 │─ 自己用 get_column_stats 推 Sharpe/MaxDD
 │─ 写进报告
```

---

## 6. 可靠性

### 6.1 错误处理（铁律 7：失败在场）

**不兜底**。失败抛 RuntimeError，原始异常 + 可行动指引。

错误分类：

| 错误类型 | 处理 |
|---|---|
| 网络 ConnectionError / Timeout | 重试 3 次指数退避 |
| akshare 接口不存在（升级后改名） | RuntimeError + 提示升级 akshare |
| akshare 返回空数据 | RuntimeError + 提示换区间或换标的 |
| ccxt 限流 | RuntimeError + 提示等会儿再试 |
| 表达式求值失败（run_backtest）| RuntimeError + 显示哪条表达式 + pandas 错误 |
| spec 缺字段 | ValueError + 列出缺哪些 |
| parquet 读写失败 | RuntimeError + 检查磁盘权限 |

### 6.2 持久化

| 层 | 路径 | 触发时机 |
|---|---|---|
| 会话内缓存 | 进程内存 dict | fetch_market_data 命中/写入 |
| 量化数据集库 | `~/.hagoku/datasets/<id>/` | fetch_market_data 写入 |
| 项目状态 | `~/.hagoku/projects/<id>/` | 创建项目时立即写，后续分析时自动落盘 |
| 活动 preset | `~/.hagoku/active_preset` | 用户切换 preset 时 |

**进程中断恢复**：
- 重启 backend → 量化数据集库持久 ✓ → 项目状态持久 ✓
- akshare 又挂了 → RuntimeError → 引导用户上传 CSV 兜底

### 6.3 限流

**3.0 不做**。如果实际撞限流，RuntimeError 抛清晰错误。3.1 再加缓存层。

---

## 7. 预设迁移

### 7.1 文件改动

| 文件 | 操作 |
|---|---|
| `hagoku/agents/presets/quant.md` | 新增（重写内容） |
| `hagoku/agents/presets/stock.md` | 删除 |
| `hagoku/agents/presets/presets.json` | 改 display name + file 字段 |
| `hagoku/api/doctor_router.py:373` | 删硬编码，调 presets.json |

### 7.2 用户数据

- `~/.hagoku/active_preset` 写的是 `"stock"` → **无需迁移**（id 不变）
- 用户下次启动 UI，看到「量化分析」显示，原「股市技术」自动变成 quant 能力

---

## 8. 测试策略

### 8.1 单元测试

- `test_market_data_akshare.py`：mock akshare 返回，验证列名标准化
- `test_market_data_ccxt.py`：mock ccxt 返回，验证列名标准化
- `test_market_data_cache.py`：同 key 二次调用命中缓存
- `test_market_data_retry.py`：模拟 ConnectionError，验证 3 次重试
- `test_market_data_error.py`：模拟 akshare 失败，验证 RuntimeError 内容含建议
- `test_backtest_basic.py`：固定输入，验证权益曲线 / trades / summary
- `test_backtest_expressions.py`：测试多种 pandas 表达式
- `test_backtest_errors.py`：spec 缺字段、表达式求值失败

### 8.2 集成测试

- `test_quant_dataset_lifecycle.py`：拉取 → 写入 → 列表 → 刷新 → 删除 → 项目引用
- `test_preset_migration.py`：stock.md 删除后，active_preset="stock" 仍能加载 quant.md

### 8.3 手工测试

- 跑一次完整工作流：拉 600519 → 创建项目 → run_backtest → 生成报告
- 模拟 akshare 失败：断网 → 看 RuntimeError 内容是否清晰
- 验证中断恢复：拉数据 → kill backend → 重启 → 数据还在

### 8.4 验证协议

- `bash scripts/ci/self_check.sh` 必须通过
- pytest 全绿
- 浏览器手动跑一次（per 项目 DEVELOPING 流程）

---

## 9. 风险与缓解

| 风险 | 缓解 |
|---|---|
| akshare 接口升级破坏 | 错误信息提示升级；用户可上传 CSV 兜底 |
| LLM 算 MaxDD 不可靠（长序列） | LLM 可声明"大致范围"；或多次 get_column_stats 拼凑 |
| ccxt 限流撞限 | RuntimeError 清晰提示；3.1 加缓存 |
| 回测表达式过于复杂（pandas 表达力有限）| 3.0 接受此限制；3.1 可加信号库预定义 |
| 数据集库膨胀（用户反复拉）| 3.0 不处理；3.1 加配额 / 清理工具 |

---

## 10. 不在 3.0（明确推迟）

3.0 不做的事（已在 §2.2 详列）：

- 数据集版本管理 / diff
- 自动定时刷新
- 多标批量拉取
- 实时行情
- 基本面 / 财务数据
- 因子库预定义（alpha101）
- 限流层 / 备用数据源
- 数据集与项目 live 绑定

每个推迟项都是 explicit choice，不是遗漏。

---

## 11. 验收标准

3.0 完成 = 满足以下全部：

- [ ] 量化数据集侧边栏可显示、新建、刷新、删除数据集
- [ ] fetch_market_data 工具可拉 A 股（akshare）和加密货币（ccxt）
- [ ] 失败抛 RuntimeError 含原始异常 + 建议
- [ ] 网络重试 3 次指数退避
- [ ] run_backtest 工具可跑策略，返回机械量
- [ ] LLM 可从机械量推导 Sharpe / MaxDD / Annual Return
- [ ] 新增项目对话框支持 CSV / 数据集 / 拉取三选一 + 场景下拉
- [ ] 场景下拉源 = presets.json 全文
- [ ] quant preset 重写完成，id="stock" 不变，doctor_router 硬编码清除
- [ ] pytest 全绿（新增 + 现有 223 个）
- [ ] self_check.sh 全绿
- [ ] 浏览器手动跑一次完整 quant 工作流

---

## 附录 A：fetch_market_data 完整签名（伪代码）

```python
class MarketDataFetcher:
    _session_cache: dict[tuple, pd.DataFrame] = {}

    def fetch(
        self,
        market: Literal["a_stock", "crypto"],
        symbol: str,
        period: str,
        interval: Literal["d1", "h1"],
    ) -> pd.DataFrame:
        key = (market, symbol, period, interval)
        if key in self._session_cache:
            return self._session_cache[key]

        df = self._fetch_with_retry(market, symbol, period, interval)
        df = self._standardize_columns(df)
        self._persist_to_library(market, symbol, period, interval, df)
        self._session_cache[key] = df
        return df

    def _fetch_with_retry(self, market, symbol, period, interval):
        last_error = None
        for attempt in range(1, 4):
            try:
                if market == "a_stock":
                    return self._fetch_akshare(symbol, period, interval)
                elif market == "crypto":
                    return self._fetch_ccxt(symbol, period, interval)
            except (ConnectionError, Timeout) as e:
                last_error = e
                if attempt < 3:
                    sleep(2 ** attempt)
        raise RuntimeError(self._format_error(market, symbol, last_error))

    def _fetch_akshare(self, symbol, period, interval):
        import akshare as ak
        # 区间映射: "1y" → start_date/end_date
        start_date, end_date = self._parse_period(period)
        adjust = "qfq"  # 前复权，3.0 写死
        df = ak.stock_zh_a_hist(
            symbol=symbol,
            period="daily" if interval == "d1" else "hourly",
            start_date=start_date,
            end_date=end_date,
            adjust=adjust,
        )
        return df

    def _fetch_ccxt(self, symbol, period, interval):
        import ccxt
        # 3.0 锁定 binance 交易所；多交易所支持推迟到 3.1
        # symbol 格式: "BTC-USDT" → ("BTC/USDT", "binance")
        trading_symbol = symbol.replace("-", "/")  # BTC-USDT → BTC/USDT
        exchange = ccxt.binance()
        since, limit = self._parse_period(period, interval)
        timeframe = "1d" if interval == "d1" else "1h"
        ohlcv = exchange.fetch_ohlcv(trading_symbol, timeframe, since=since, limit=limit)
        return pd.DataFrame(ohlcv, columns=["timestamp","open","high","low","close","volume"])

    def _standardize_columns(self, df):
        # akshare: 日期/股票代码/开盘/收盘/最高/最低/成交量/成交额/振幅/涨跌幅/涨跌额/换手率
        # ccxt: timestamp/open/high/low/close/volume
        column_map_akshare = {
            "日期": "date", "开盘": "open", "收盘": "close",
            "最高": "high", "最低": "low", "成交量": "volume",
        }
        if "日期" in df.columns:
            df = df.rename(columns=column_map_akshare)
        if "timestamp" in df.columns:
            df = df.rename(columns={"timestamp": "date"})
        df["date"] = pd.to_datetime(df["date"])
        df = df[["date","open","high","low","close","volume"]].copy()
        df = df.sort_values("date").reset_index(drop=True)
        return df

    def _persist_to_library(self, market, symbol, period, interval, df):
        fetched_at = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
        ds_id = f"{market}__{symbol}__{period}__{interval}__{fetched_at}"
        ds_dir = Path.home() / ".hagoku" / "datasets" / ds_id
        ds_dir.mkdir(parents=True, exist_ok=True)
        df.to_parquet(ds_dir / "data.parquet")
        meta = {
            "id": ds_id,
            "market": market,
            "symbol": symbol,
            "period": period,
            "interval": interval,
            "fetched_at": fetched_at,
            "rows": len(df),
            "source": "akshare" if market == "a_stock" else "ccxt",
            "source_version": akshare.__version__ if market == "a_stock" else ccxt.__version__,
        }
        (ds_dir / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2))
```

## 附录 B：run_backtest 完整签名（伪代码）

```python
def run_backtest(strategy_spec: dict, df: pd.DataFrame) -> dict:
    required = ["name", "entry", "exit"]
    for k in required:
        if k not in strategy_spec:
            raise ValueError(f"strategy_spec 缺少字段: {k}")

    df = df.copy()
    try:
        df["entry_signal"] = df.eval(strategy_spec["entry"]).astype(bool)
        df["exit_signal"] = df.eval(strategy_spec["exit"]).astype(bool)
    except Exception as e:
        raise RuntimeError(
            f"策略表达式求值失败。\n"
            f"entry: {strategy_spec['entry']}\n"
            f"exit: {strategy_spec['exit']}\n"
            f"原始错误: {e}\n"
            f"提示: 表达式必须是合法的 pandas 表达式。"
        )

    # 推断 periods_per_year
    if len(df) > 1:
        delta = df["date"].iloc[1] - df["date"].iloc[0]
        seconds = delta.total_seconds()
        if seconds >= 86400 * 0.9:
            periods_per_year = 252
        elif seconds >= 3600 * 0.9:
            periods_per_year = 24 * 365
        else:
            periods_per_year = 252
    else:
        periods_per_year = 252

    # 事件驱动模拟（all_in 仓位 + 可选止损止盈）
    stop_loss = strategy_spec.get("stop_loss")
    take_profit = strategy_spec.get("take_profit")
    in_position = False
    entry_price = None
    entry_time = None
    positions = []
    trades = []

    for i, row in df.iterrows():
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

    # 权益曲线（3.0 简化版）
    final_pnl = sum(t["pnl"] for t in trades) if trades else 0
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
```

---

**END OF SPEC**

下一步：spec self-review（占位 / 一致性 / 范围 / 歧义）→ 你 review → 批准后 invoke writing-plans 拆任务。