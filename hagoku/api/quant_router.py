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
