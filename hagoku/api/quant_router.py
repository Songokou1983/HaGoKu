"""量化数据集 CRUD endpoints — Phase 3.0。"""
from __future__ import annotations

import json as _json
import logging
import shutil
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

_log = logging.getLogger(__name__)
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


def _read_dataset_meta(ds_dir: Path) -> dict:
    """从挂载的 parquet 文件 metadata 读 meta（仅量化数据集路径 ~/.hagoku/datasets/<id>/data.parquet）。

    优先读 parquet schema metadata（bytes 解码）。
    找不到字段 → fallback 解析目录名 ({market}__{symbol}__{period}__{interval}__{fetched_at})。
    """
    import pyarrow.parquet as _pq
    parquet_path = ds_dir / "data.parquet"
    meta = {}
    if parquet_path.exists():
        try:
            schema_meta = _pq.read_metadata(parquet_path).metadata or {}
            decoded = {}
            for k, v in schema_meta.items():
                try:
                    decoded[k.decode() if isinstance(k, bytes) else k] = v.decode() if isinstance(v, bytes) else v
                except (UnicodeDecodeError, AttributeError):
                    continue
            meta.update(decoded)
        except Exception:
            pass

    if "id" not in meta:
        # 全新代码写入的 parquet 必有 meta；旧文件没有 → fallback 解析目录名
        # 目录格式: {market}__{symbol}__{period}__{interval}__{fetched_at}
        parts = ds_dir.name.split("__")
        if len(parts) >= 5:
            meta["id"] = ds_dir.name
            meta["market"] = parts[0]
            meta["symbol"] = parts[1]
            meta["period"] = parts[2]
            meta["interval"] = parts[3]
            meta["fetched_at"] = "__".join(parts[4:])
            meta["source"] = "akshare" if parts[0] == "a_stock" else "ccxt"
            meta["_timezone"] = "Asia/Shanghai" if parts[0] == "a_stock" else "UTC"

    if "rows" in meta:
        try:
            meta["rows"] = int(meta["rows"])
        except (TypeError, ValueError):
            pass
    return meta


# ── endpoints ──────────────────────────────────────────────────

@router.get("/datasets")
async def list_datasets() -> dict:
    """列出所有已保存的数据集。"""
    if not DATASETS_ROOT.exists():
        return {"datasets": []}
    import pyarrow.parquet as _pq
    items = []
    for ds_dir in sorted(DATASETS_ROOT.iterdir(), reverse=True):
        if not ds_dir.is_dir():
            continue
        parquet_path = ds_dir / "data.parquet"
        if not parquet_path.exists():
            continue
        try:
            schema_meta = _pq.read_metadata(parquet_path).metadata or {}
            # PyArrow schema_meta keys/values 是 bytes
            meta = {k.decode(): v.decode() for k, v in schema_meta.items()}
        except (OSError, _json.JSONDecodeError, KeyError, UnicodeDecodeError):
            continue
        if "id" not in meta:
            continue
        items.append({
            "id": meta["id"],
            "market": meta["market"],
            "symbol": meta["symbol"],
            "period": meta["period"],
            "interval": meta["interval"],
            "fetched_at": meta["fetched_at"],
            "rows": int(meta.get("rows", "0")),
            "source": meta["source"],
        })
    return {"datasets": items}


@router.post("/datasets")
async def create_dataset(req: CreateDatasetReq) -> dict:
    """拉取新数据并保存到数据集库。"""
    _log.info(f"POST /datasets received: market={req.market} symbol={req.symbol} period={req.period} interval={req.interval}")
    try:
        result = _call_fetch_market_data(req.market, req.symbol, req.period, req.interval)
    except RuntimeError as e:
        _log.warning(f"POST /datasets failed: {e}")
        raise HTTPException(status_code=422, detail=str(e))
    _log.info(f"POST /datasets ok: dataset_id={result.get('dataset_id')} rows={result.get('rows')}")
    return result


@router.delete("/datasets/{dataset_id}")
async def delete_dataset(dataset_id: str) -> dict:
    """删除一个数据集目录。"""
    ds_dir = DATASETS_ROOT / dataset_id
    if not ds_dir.exists():
        raise HTTPException(status_code=404, detail=f"数据集 {dataset_id} 不存在")
    shutil.rmtree(ds_dir)
    return {"ok": True, "deleted": dataset_id}


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
