"""HaGoKu 记忆系统 — 存储后端

策略模式：MemoryBackend(ABC) → SqliteMemoryBackend / YamlMemoryBackend
- SQLite: 程序化查询，所有类别
- YAML: 人可读、git 友好，column_semantic / target_variable 为主
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from .database import HaGoKuDB


class MemoryBackend(ABC):
    """记忆存储后端抽象基类"""

    @abstractmethod
    def save(
        self,
        project_id: str | None,
        category: str,
        key: str,
        value: str,
        source: str = "auto",
        confidence: float = 1.0,
    ) -> None:
        """Upsert 一条记忆"""

    @abstractmethod
    def load(
        self,
        project_id: str | None,
        category: str | None = None,
    ) -> list[dict[str, Any]]:
        """加载记忆条目，可选按类别过滤"""

    @abstractmethod
    def delete(self, project_id: str | None, category: str, key: str) -> bool:
        """删除一条记忆，返回是否找到并删除"""

    def load_column_semantics(self, project_id: str) -> dict[str, dict[str, Any]]:
        """加载所有 column_semantic 记忆为结构化 dict"""
        entries = self.load(project_id, category="column_semantic")
        result: dict[str, dict[str, Any]] = {}
        for e in entries:
            val = e.get("value", "")
            if isinstance(val, str):
                try:
                    val = json.loads(val)
                except (json.JSONDecodeError, TypeError):
                    val = {}
            result[e["key"]] = val
        return result

    def save_column_semantic(
        self,
        project_id: str,
        column: str,
        sem_dict: dict[str, Any],
        source: str = "auto",
        confidence: float = 1.0,
    ) -> None:
        """保存列语义定义"""
        self.save(
            project_id, "column_semantic", column,
            json.dumps(sem_dict, ensure_ascii=False),
            source=source, confidence=confidence,
        )


# ── SQLite 后端 ──────────────────────────────────────────────


class SqliteMemoryBackend(MemoryBackend):
    """SQLite 存储后端，直接操作 memory 表"""

    def __init__(self, db: HaGoKuDB) -> None:
        self._db = db  # 保留 HaGoKuDB 实例以使用线程锁
        self._conn = db.conn
        self._index_ensured = False

    def save(
        self,
        project_id: str | None,
        category: str,
        key: str,
        value: str,
        source: str = "auto",
        confidence: float = 1.0,
    ) -> None:
        now = datetime.now().isoformat()
        mem_id = f"{project_id or '_global'}:{category}:{key}"
        # 通过 transaction() 使用线程锁（包含索引创建 + 数据写入）
        with self._db.transaction():
            # 确保 idx_memory_uniq 索引存在（旧 DB 可能没有），只检查一次
            if not self._index_ensured:
                self._conn.execute(
                    "CREATE UNIQUE INDEX IF NOT EXISTS idx_memory_uniq ON memory(project_id, category, key)"
                )
                self._index_ensured = True
            self._conn.execute(
                "INSERT OR REPLACE INTO memory (id, project_id, category, key, value, source, confidence, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (mem_id, project_id, category, key, value, source, confidence, now, now),
            )

    def load(
        self,
        project_id: str | None,
        category: str | None = None,
    ) -> list[dict[str, Any]]:
        # SQLite 中 NULL = ? 不匹配 NULL，需要 IS NULL
        if project_id is None:
            if category is not None:
                rows = self._conn.execute(
                    "SELECT * FROM memory WHERE project_id IS NULL AND category = ? ORDER BY updated_at DESC",
                    (category,),
                ).fetchall()
            else:
                rows = self._conn.execute(
                    "SELECT * FROM memory WHERE project_id IS NULL ORDER BY updated_at DESC",
                ).fetchall()
        else:
            if category is not None:
                rows = self._conn.execute(
                    "SELECT * FROM memory WHERE project_id = ? AND category = ? ORDER BY updated_at DESC",
                    (project_id, category),
                ).fetchall()
            else:
                rows = self._conn.execute(
                    "SELECT * FROM memory WHERE project_id = ? ORDER BY updated_at DESC",
                    (project_id,),
                ).fetchall()

        result = []
        for r in rows:
            d = dict(r)
            # 解析 JSON value
            if d.get("value") and isinstance(d["value"], str):
                try:
                    d["value"] = json.loads(d["value"])
                except (json.JSONDecodeError, TypeError):
                    pass
            result.append(d)
        return result

    def delete(self, project_id: str | None, category: str, key: str) -> bool:
        with self._db.transaction():
            if project_id is None:
                cursor = self._conn.execute(
                    "DELETE FROM memory WHERE project_id IS NULL AND category = ? AND key = ?",
                    (category, key),
                )
            else:
                cursor = self._conn.execute(
                    "DELETE FROM memory WHERE project_id = ? AND category = ? AND key = ?",
                    (project_id, category, key),
                )
        return cursor.rowcount > 0

    def get_latest_mtime(self, project_id: str | None) -> str | None:
        """获取最新记忆的更新时间（用于 YAML 同步判断）"""
        row = self._conn.execute(
            "SELECT MAX(updated_at) FROM memory WHERE project_id = ?",
            (project_id,),
        ).fetchone()
        return row[0] if row and row[0] else None


# ── YAML 后端 ────────────────────────────────────────────────


class YamlMemoryBackend(MemoryBackend):
    """YAML 存储后端，读写 progress.yaml

    progress.yaml 结构：
        columns:
          col_name: {semantic: "xxx", role: "xxx", ...}
        target: col_name
        confounders: [...]
        time_column: col_name
        group_columns: [...]
        user_constraints: [...]
        _memory:            # 非核心记忆
          cleaning_pref: {...}
          analysis_pattern: {...}
          user_note: {...}
    """

    def __init__(self, progress_path: Path) -> None:
        self._path = progress_path

    def _read(self) -> dict[str, Any]:
        if not self._path.exists():
            return {}
        with open(self._path, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}

    def _write(self, data: dict[str, Any]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._path, "w", encoding="utf-8") as f:
            yaml.dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

    def save(
        self,
        project_id: str | None,
        category: str,
        key: str,
        value: str,
        source: str = "auto",
        confidence: float = 1.0,
    ) -> None:
        data = self._read()

        # 解析 value
        try:
            val = json.loads(value) if isinstance(value, str) else value
        except (json.JSONDecodeError, TypeError):
            val = value

        if category == "column_semantic":
            if "columns" not in data:
                data["columns"] = {}
            data["columns"][key] = val if isinstance(val, dict) else {"semantic": val}

        elif category == "target_variable":
            if isinstance(val, dict):
                data["target"] = val.get("column", key)
            else:
                data["target"] = key

        elif category == "column_semantic_confounders":
            # confounders 列表
            if isinstance(val, list):
                data["confounders"] = val

        elif category == "column_semantic_time_column":
            data["time_column"] = val if isinstance(val, str) else key

        elif category == "column_semantic_group_columns":
            if isinstance(val, list):
                data["group_columns"] = val

        else:
            # 其他类别 → _memory 段
            if "_memory" not in data:
                data["_memory"] = {}
            if category not in data["_memory"]:
                data["_memory"][category] = {}
            data["_memory"][category][key] = val

        self._write(data)

    def load(
        self,
        project_id: str | None,
        category: str | None = None,
    ) -> list[dict[str, Any]]:
        data = self._read()
        result: list[dict[str, Any]] = []

        if category == "column_semantic" or category is None:
            columns = data.get("columns", {})
            for col_name, col_def in columns.items():
                result.append({
                    "project_id": project_id,
                    "category": "column_semantic",
                    "key": col_name,
                    "value": col_def if isinstance(col_def, dict) else {"semantic": col_def},
                    "source": "user",
                    "confidence": 1.0,
                })

        if category == "target_variable" or category is None:
            target = data.get("target")
            if target:
                result.append({
                    "project_id": project_id,
                    "category": "target_variable",
                    "key": target,
                    "value": {"column": target, "role": "target"},
                    "source": "user",
                    "confidence": 1.0,
                })

        if category == "column_semantic_confounders" or category is None:
            confounders = data.get("confounders", [])
            if confounders:
                result.append({
                    "project_id": project_id,
                    "category": "column_semantic_confounders",
                    "key": "_confounders",
                    "value": confounders,
                    "source": "user",
                    "confidence": 1.0,
                })

        if category == "column_semantic_time_column" or category is None:
            tc = data.get("time_column")
            if tc:
                result.append({
                    "project_id": project_id,
                    "category": "column_semantic_time_column",
                    "key": tc,
                    "value": tc,
                    "source": "user",
                    "confidence": 1.0,
                })

        if category == "column_semantic_group_columns" or category is None:
            gc = data.get("group_columns", [])
            if gc:
                result.append({
                    "project_id": project_id,
                    "category": "column_semantic_group_columns",
                    "key": "_group_columns",
                    "value": gc,
                    "source": "user",
                    "confidence": 1.0,
                })

        # 从 _memory 段加载其他类别
        mem_section = data.get("_memory", {})
        for cat_name, entries in mem_section.items():
            if category is not None and cat_name != category:
                continue
            if not isinstance(entries, dict):
                continue
            for k, v in entries.items():
                result.append({
                    "project_id": project_id,
                    "category": cat_name,
                    "key": k,
                    "value": v,
                    "source": "auto",
                    "confidence": 0.8,
                })

        # 加载 user_constraints
        uc = data.get("user_constraints", [])
        if uc and (category is None or category == "user_note"):
            for i, note in enumerate(uc):
                result.append({
                    "project_id": project_id,
                    "category": "user_note",
                    "key": f"constraint_{i}",
                    "value": note,
                    "source": "user",
                    "confidence": 1.0,
                })

        return result

    def delete(self, project_id: str | None, category: str, key: str) -> bool:
        data = self._read()
        changed = False

        if category == "column_semantic":
            if "columns" in data and key in data["columns"]:
                del data["columns"][key]
                changed = True

        elif category == "target_variable":
            if data.get("target") == key:
                del data["target"]
                changed = True

        else:
            mem = data.get("_memory", {}).get(category, {})
            if key in mem:
                del mem[key]
                if not mem:
                    del data["_memory"][category]
                if not data.get("_memory"):
                    data.pop("_memory", None)
                changed = True

        if changed:
            self._write(data)
        return changed

    def load_column_semantics(self, project_id: str) -> dict[str, dict[str, Any]]:
        """重写：直接从 YAML columns 段读取"""
        data = self._read()
        columns = data.get("columns", {})
        result: dict[str, dict[str, Any]] = {}
        for col_name, col_def in columns.items():
            if isinstance(col_def, dict):
                result[col_name] = col_def
            elif isinstance(col_def, str):
                result[col_name] = {"semantic": col_def}
        return result

    @property
    def path(self) -> Path:
        return self._path

    def exists(self) -> bool:
        return self._path.exists()

    def mtime(self) -> float | None:
        """返回文件修改时间，不存在返回 None"""
        if self._path.exists():
            return self._path.stat().st_mtime
        return None
