"""Agent 知识库 — 向量检索 + YAML 持久化

每个 Agent 一个 knowledge.yaml（人可读）+ knowledge.db（向量检索）。
使用 text-embedding-3-small (OpenAI兼容) + sqlite_vec 实现语义检索。
"""

from __future__ import annotations

import sqlite3
import struct
import threading
import uuid
from pathlib import Path
from typing import Any

import requests
import yaml

try:
    import sqlite_vec
except ImportError:
    sqlite_vec = None

from hagoku.config import HaGoKuConfig

# 全局配置（从 .env 加载）
_ha_config: HaGoKuConfig | None = None


def _get_config() -> HaGoKuConfig:
    global _ha_config
    if _ha_config is None:
        _ha_config = HaGoKuConfig.load()
    return _ha_config


def _get_embedding(text: str) -> list[float] | None:
    """调用 embedding API，返回 embedding 向量"""
    cfg = _get_config()
    emb_cfg = cfg.embedding
    try:
        # 直接拼接 /embeddings，不剥离 /v1（部分 proxy 要求保留 v1 前缀）
        url = emb_cfg.base_url.rstrip("/") + "/embeddings"
        resp = requests.post(
            url,
            headers={
                "Authorization": f"Bearer {emb_cfg.api_key}",
                "Content-Type": "application/json",
            },
            json={"model": emb_cfg.model, "input": text[:8192]},
            timeout=60,
        )
        resp.raise_for_status()
        data = resp.json()
        embedding = data.get("data", [{}])[0].get("embedding")
        return embedding if isinstance(embedding, list) else None
    except Exception:
        return None


def _cosine_sim(a: list[float], b: list[float]) -> float:
    """计算两个向量的余弦相似度"""
    import math
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


class KnowledgeVectorStore:
    """
    Agent 知识向量存储。

    - YAML 文件（knowledge.yaml）：人可读、可 git 管理的知识条目
    - SQLite 向量库（knowledge.db）：机器向量检索

    检索时：
      1. 从 YAML 加载所有条目
      2. 对 query 做 embedding
      3. 计算余弦相似度，返回 top-k
    """

    def __init__(self, yaml_path: str | Path, dimension: int = 1536) -> None:
        self.yaml_path = Path(yaml_path)
        self.db_path = self.yaml_path.with_suffix(".db")
        self.dimension = dimension
        self._lock = threading.RLock()
        self._ensure_db()

    def _ensure_db(self) -> None:
        if sqlite_vec is None:
            return
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            conn = sqlite3.connect(str(self.db_path), timeout=30)
            conn.enable_load_extension(True)
            sqlite_vec.load(conn)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            # 向量表
            conn.execute("""
                CREATE TABLE IF NOT EXISTS knowledge_vec (
                    id TEXT PRIMARY KEY,
                    embedding BLOB,
                    updated_at TEXT
                )
            """)
            # 元数据表
            conn.execute("""
                CREATE TABLE IF NOT EXISTS knowledge_meta (
                    id TEXT PRIMARY KEY,
                    tags TEXT,
                    content TEXT,
                    metadata TEXT,
                    updated_at TEXT
                )
            """)
            conn.commit()
            conn.close()

    def _load_yaml(self) -> dict[str, Any]:
        """从 YAML 加载知识条目（不含 embedding）"""
        if not self.yaml_path.exists():
            return {"knowledge": []}
        try:
            with open(self.yaml_path, encoding="utf-8") as f:
                return yaml.safe_load(f) or {"knowledge": []}
        except yaml.YAMLError:
            return {"knowledge": []}

    def _save_yaml(self, data: dict[str, Any]) -> None:
        self.yaml_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.yaml_path, "w", encoding="utf-8") as f:
            yaml.dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

    # ── 核心接口 ────────────────────────────────────────────

    def add(
        self,
        content: str,
        tags: list[str],
        metadata: dict[str, Any] | None = None,
        embedding: list[float] | None = None,
    ) -> str:
        """
        添加一条知识条目。

        Returns:
            新条目的 id
        """
        entry_id = str(uuid.uuid4())[:8]
        if embedding is None:
            embedding = _get_embedding(content) or [0.0] * self.dimension
        data = self._load_yaml()
        entry = {
            "id": entry_id,
            "content": content,
            "tags": tags,
            "metadata": metadata or {},
            "created_at": self._now(),
            "use_count": 0,
        }
        data.setdefault("knowledge", []).append(entry)
        self._save_yaml(data)

        # 向量入库
        self._upsert_vector(entry_id, embedding, tags, content, metadata)
        return entry_id

    def upsert(
        self,
        entry_id: str,
        content: str,
        tags: list[str],
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """更新或插入一条知识条目（根据 id）"""
        embedding = _get_embedding(content) or [0.0] * self.dimension
        data = self._load_yaml()
        entries = data.get("knowledge", [])

        # 查找是否已存在
        found = False
        for e in entries:
            if e.get("id") == entry_id:
                e["content"] = content
                e["tags"] = tags
                e["metadata"] = {**(e.get("metadata", {})), **(metadata or {})}
                e["updated_at"] = self._now()
                found = True
                break

        if not found:
            entries.append({
                "id": entry_id,
                "content": content,
                "tags": tags,
                "metadata": metadata or {},
                "created_at": self._now(),
                "use_count": 0,
            })

        self._save_yaml(data)
        self._upsert_vector(entry_id, embedding, tags, content, metadata)

    def _sync_vectors(self) -> None:
        """
        同步 YAML 中的条目到向量 DB。
        YAML 中有但 DB 中没有的条目，自动生成向量并写入 DB。
        """
        if sqlite_vec is None:
            return
        data = self._load_yaml()
        if not data.get("knowledge"):
            return

        conn = sqlite3.connect(str(self.db_path), timeout=30)
        conn.enable_load_extension(True)
        sqlite_vec.load(conn)
        existing_ids = set(row[0] for row in conn.execute("SELECT id FROM knowledge_vec").fetchall())
        conn.close()

        for entry in data["knowledge"]:
            if entry.get("id") in existing_ids:
                continue
            # 优先用 content 字段，否则从元数据字段构造
            content = entry.get("content", "")
            if not content:
                # 从 metadata 或 entry 字段构造
                meta = entry.get("metadata", {})
                parts = []
                for key in ("scenario", "condition", "field", "meaning", "method", "action", "report_type"):
                    if key in meta:
                        parts.append(f"{key}={meta[key]}")
                if not parts:
                    for key in ("scenario", "condition", "field", "meaning", "method", "action", "report_type"):
                        if key in entry:
                            parts.append(f"{key}={entry[key]}")
                content = "; ".join(parts) if parts else ", ".join(entry.get("tags", []))
            if not content:
                continue
            embedding = _get_embedding(content)
            if embedding:
                self._upsert_vector(
                    entry["id"],
                    embedding,
                    entry.get("tags", []),
                    content,
                    entry.get("metadata"),
                )

    def recall(
        self,
        query: str,
        tags: list[str] | None = None,
        top_k: int = 3,
    ) -> list[dict[str, Any]]:
        """
        检索最相关的知识条目。

        1. 同步缺失的向量（YAML 有条目但 DB 无向量时补全）
        2. 对 query 做 embedding
        3. 从 DB 取出所有已有 embedding，算余弦相似度
        4. 按相似度排序返回 top_k
        """
        # 补全缺失向量
        self._sync_vectors()

        query_emb = _get_embedding(query)
        if query_emb is None:
            return []

        data = self._load_yaml()
        entries_by_id = {e["id"]: e for e in data.get("knowledge", [])}
        if not entries_by_id:
            return []

        # 从 DB 读取已有向量
        conn = sqlite3.connect(str(self.db_path), timeout=30)
        conn.enable_load_extension(True)
        sqlite_vec.load(conn)
        rows = conn.execute("SELECT id, embedding FROM knowledge_vec").fetchall()
        conn.close()

        if not rows:
            return []

        scored = []
        for row_id, emb_blob in rows:
            if row_id not in entries_by_id:
                continue
            emb = struct.unpack(f"{len(emb_blob)//4}f", emb_blob)
            sim = _cosine_sim(query_emb, list(emb))
            # 标签过滤
            if tags:
                entry_tags = entries_by_id[row_id].get("tags", [])
                if not any(t.lower() in [et.lower() for et in entry_tags] for t in tags):
                    continue
            scored.append((sim, row_id, entries_by_id[row_id]))

        scored.sort(key=lambda x: x[0], reverse=True)
        results = []
        for sim, entry_id, entry in scored[:top_k]:
            # 增加 use_count
            entry["use_count"] = entry.get("use_count", 0) + 1
            entry_copy = dict(entry)
            entry_copy["similarity"] = round(sim, 4)
            # metadata 为空时，从顶层字段补全（YAML 直接写条目时没有 metadata 包装）
            if not entry_copy.get("metadata"):
                entry_copy["metadata"] = {}
                for key in ("scenario", "condition", "field", "meaning", "method", "action", "report_type", "confidence", "risk"):
                    if key in entry_copy:
                        entry_copy["metadata"][key] = entry_copy[key]
            # 没有 content 字段时，从 metadata 或顶层字段构造
            if "content" not in entry_copy:
                meta = entry_copy.get("metadata", {})
                parts = []
                for key in ("scenario", "condition", "field", "meaning", "method", "action", "report_type"):
                    if key in meta:
                        parts.append(f"{key}={meta[key]}")
                entry_copy["content"] = "; ".join(parts) if parts else ", ".join(entry_copy.get("tags", []))
            results.append(entry_copy)

        # 保存 use_count 更新
        self._save_yaml(data)
        return results

    def increment_use(self, entry_id: str) -> None:
        """增加某条目的 use_count（每次被召回时调用）"""
        data = self._load_yaml()
        for e in data.get("knowledge", []):
            if e.get("id") == entry_id:
                e["use_count"] = e.get("use_count", 0) + 1
                break
        self._save_yaml(data)

    def list_all(self) -> list[dict[str, Any]]:
        """列出所有知识条目（不含 similarity）"""
        data = self._load_yaml()
        knowledge = data.get("knowledge", [])
        return knowledge if isinstance(knowledge, list) else []

    def delete(self, entry_id: str) -> bool:
        """删除一条知识条目"""
        data = self._load_yaml()
        entries = data.get("knowledge", [])
        before = len(entries)
        data["knowledge"] = [e for e in entries if e.get("id") != entry_id]
        if len(data["knowledge"]) == before:
            return False
        self._save_yaml(data)

        # 从 DB 删除
        with self._lock:
            conn = sqlite3.connect(str(self.db_path), timeout=30)
            conn.execute("DELETE FROM knowledge_vec WHERE id = ?", (entry_id,))
            conn.execute("DELETE FROM knowledge_meta WHERE id = ?", (entry_id,))
            conn.commit()
            conn.close()
        return True

    def _upsert_vector(
        self,
        entry_id: str,
        embedding: list[float],
        tags: list[str],
        content: str,
        metadata: dict[str, Any] | None,
    ) -> None:
        if sqlite_vec is None:
            return
        with self._lock:
            conn = sqlite3.connect(str(self.db_path), timeout=30)
            conn.enable_load_extension(True)
            sqlite_vec.load(conn)
            packed = sqlite_vec.serialize_float32(embedding)
            now = self._now()
            conn.execute("""
                INSERT INTO knowledge_vec(id, embedding, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET embedding=excluded.embedding, updated_at=excluded.updated_at
            """, (entry_id, packed, now))
            conn.execute("""
                INSERT INTO knowledge_meta(id, tags, content, metadata, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET tags=excluded.tags, content=excluded.content, metadata=excluded.metadata, updated_at=excluded.updated_at
            """, (entry_id, ",".join(tags), content, yaml.dump(metadata or {}), now))
            conn.commit()
            conn.close()

    @staticmethod
    def _now() -> str:
        from datetime import datetime
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
