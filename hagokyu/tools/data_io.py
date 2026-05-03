"""HaGoKu 数据加载与保存"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import pandas as pd


# ── 支持的文件格式 ────────────────────────────────────────────

SUPPORTED_FORMATS = {
    ".csv": "csv",
    ".tsv": "csv",
    ".xlsx": "excel",
    ".xls": "excel",
    ".json": "json",
    ".jsonl": "json_lines",
    ".parquet": "parquet",
    ".pq": "parquet",
    ".feather": "feather",
    ".arrow": "feather",
}


def load_data(
    path: str | Path,
    *,
    encoding: str = "utf-8",
    sheet_name: int | str = 0,
    **kwargs: Any,
) -> pd.DataFrame:
    """
    统一数据加载入口，根据扩展名自动选择加载方式

    Args:
        path: 文件路径
        encoding: 文本编码（CSV/TSV）
        sheet_name: Excel sheet 名或索引
        **kwargs: 传递给底层 pandas 读取函数的额外参数

    Returns:
        加载的 DataFrame

    Raises:
        FileNotFoundError: 文件不存在
        ValueError: 不支持的文件格式
    """
    path = Path(path)
    ext = path.suffix.lower()
    fmt = SUPPORTED_FORMATS.get(ext)

    # 尝试常见扩展名（少假设多适配）
    if not path.exists() or fmt is None:
        suffixes = [".csv", ".parquet", ".xlsx", ".json", ".tsv"]
        for suf in suffixes:
            candidate = path.parent / (path.stem + suf)
            if candidate.exists():
                path = candidate
                ext = suf
                fmt = SUPPORTED_FORMATS.get(ext)
                break

    if not path.exists():
        raise FileNotFoundError(f"数据文件不存在（尝试过常见扩展名）: {path}")

    if fmt is None:
        raise ValueError(
            f"不支持的文件格式: {ext}，"
            f"支持: {', '.join(sorted(SUPPORTED_FORMATS.keys()))}"
        )

    if fmt == "csv":
        sep = "\t" if ext == ".tsv" else kwargs.pop("sep", ",")
        df = pd.read_csv(path, encoding=encoding, sep=sep, **kwargs)
    elif fmt == "excel":
        df = pd.read_excel(path, sheet_name=sheet_name, **kwargs)
    elif fmt == "json":
        df = pd.read_json(path, encoding=encoding, **kwargs)
    elif fmt == "json_lines":
        df = pd.read_json(path, lines=True, encoding=encoding, **kwargs)
    elif fmt == "parquet":
        df = pd.read_parquet(path, **kwargs)
    elif fmt == "feather":
        df = pd.read_feather(path, **kwargs)
    else:
        raise ValueError(f"加载器未实现: {fmt}")

    return df


def save_data(
    df: pd.DataFrame,
    path: str | Path,
    *,
    encoding: str = "utf-8",
    index: bool = False,
    **kwargs: Any,
) -> Path:
    """
    保存数据，根据扩展名自动选择格式

    Args:
        df: 要保存的 DataFrame
        path: 目标文件路径
        encoding: 文本编码
        index: 是否保存索引
        **kwargs: 传递给底层 pandas 写入函数的额外参数

    Returns:
        保存的文件路径
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    ext = path.suffix.lower()
    fmt = SUPPORTED_FORMATS.get(ext)
    if fmt is None:
        raise ValueError(f"不支持的保存格式: {ext}")

    if fmt == "csv":
        df.to_csv(path, encoding=encoding, index=index, **kwargs)
    elif fmt == "excel":
        df.to_excel(path, index=index, **kwargs)
    elif fmt == "json":
        df.to_json(path, orient="records", force_ascii=False, indent=2, **kwargs)
    elif fmt == "json_lines":
        df.to_json(path, orient="records", lines=True, force_ascii=False, **kwargs)
    elif fmt == "parquet":
        df.to_parquet(path, index=index, engine="pyarrow", **kwargs)
    elif fmt == "feather":
        df.to_feather(path, **kwargs)

    return path


def compute_data_hash(path: str | Path) -> str:
    """
    计算数据文件的 MD5 哈希，用于检测数据变更

    Args:
        path: 文件路径

    Returns:
        MD5 哈希值（十六进制）
    """
    path = Path(path)
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def get_data_info(df: pd.DataFrame, path: str | Path | None = None) -> dict[str, Any]:
    """
    获取数据基本信息

    Args:
        df: 数据
        path: 原始文件路径（可选，用于记录来源）

    Returns:
        数据信息字典
    """
    info: dict[str, Any] = {
        "n_rows": len(df),
        "n_columns": len(df.columns),
        "columns": list(df.columns),
        "dtypes": {col: str(dt) for col, dt in df.dtypes.items()},
        "memory_mb": round(df.memory_usage(deep=True).sum() / 1024 / 1024, 2),
        "null_count": int(df.isnull().sum().sum()),
        "null_columns": {
            col: int(cnt)
            for col, cnt in df.isnull().sum().items()
            if cnt > 0
        },
        "duplicate_rows": int(df.duplicated().sum()),
    }

    if path is not None:
        path = Path(path)
        info["source_path"] = str(path)
        info["source_suffix"] = path.suffix.lower()
        if path.exists():
            info["source_size_mb"] = round(path.stat().st_size / 1024 / 1024, 2)
            info["source_hash"] = compute_data_hash(path)

    return info


def load_sql(
    query: str,
    connection: str,
    *,
    engine: str = "sqlite",
    **kwargs: Any,
) -> pd.DataFrame:
    """
    从数据库加载数据

    Args:
        query: SQL 查询
        connection: 连接字符串或文件路径
        engine: 数据库引擎 (sqlite / postgres / mysql)
        **kwargs: 传递给 pd.read_sql 的额外参数

    Returns:
        查询结果 DataFrame
    """
    if engine == "sqlite":
        import sqlite3

        conn = sqlite3.connect(connection)
        try:
            df = pd.read_sql(query, conn, **kwargs)
        finally:
            conn.close()
    else:
        # 需要 sqlalchemy
        df = pd.read_sql(query, connection, **kwargs)

    return df
