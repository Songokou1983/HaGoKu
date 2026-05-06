"""Scout 知识库管理 — 字段语义理解经验"""

from __future__ import annotations

from pathlib import Path

from ...storage.knowledge_vector import KnowledgeVectorStore


def _knowledge_path() -> Path:
    return Path(__file__).parent / "knowledge.yaml"


def recall(query: str, top_k: int = 3) -> list[dict]:
    """检索最相关的字段理解经验"""
    store = KnowledgeVectorStore(_knowledge_path())
    return store.recall(query, top_k=top_k)


def learn(
    field: str,
    meaning: str,
    data_pattern: str,
    inferred_role: str = "feature",
    confidence: float = 0.85,
    tags: list[str] | None = None,
    metadata: dict | None = None,
) -> str:
    """
    记录一条字段理解经验。

    Returns:
        新条目 id
    """
    store = KnowledgeVectorStore(_knowledge_path())
    content = f"字段名：{field}；含义：{meaning}；数据特征：{data_pattern}；推断角色：{inferred_role}"
    return store.add(
        content=content,
        tags=tags or [inferred_role, data_pattern[:20]],
        metadata={
            **(metadata or {}),
            "field": field,
            "meaning": meaning,
            "data_pattern": data_pattern,
            "inferred_role": inferred_role,
            "confidence": confidence,
        },
    )


def list_all() -> list[dict]:
    """列出所有字段理解经验"""
    return KnowledgeVectorStore(_knowledge_path()).list_all()
