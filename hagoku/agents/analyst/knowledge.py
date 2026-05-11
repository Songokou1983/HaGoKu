"""Analyst 知识库管理 — 分析方法选择经验"""

from __future__ import annotations

from pathlib import Path

from ...storage.knowledge_vector import KnowledgeVectorStore


def _knowledge_path() -> Path:
    return Path(__file__).parent / "knowledge.yaml"


def recall(query: str, top_k: int = 3) -> list[dict]:
    """检索最相关的分析方法选择经验"""
    store = KnowledgeVectorStore(_knowledge_path())
    return store.recall(query, top_k=top_k)


def learn(
    scenario: str,
    method: str,
    method_code: str | None = None,
    confidence: float = 0.85,
    tags: list[str] | None = None,
    metadata: dict | None = None,
) -> str:
    """
    记录一条分析方法选择经验。

    Returns:
        新条目 id
    """
    store = KnowledgeVectorStore(_knowledge_path())
    content = f"场景：{scenario}；选用方法：{method}；代码：{method_code or 'N/A'}"
    meta = dict(metadata or {})
    meta.update({"scenario": scenario, "method": method, "method_code": method_code, "confidence": confidence})
    return store.add(content=content, tags=tags or [scenario[:20], method], metadata=meta)


def list_all() -> list[dict]:
    """列出所有分析方法经验"""
    return KnowledgeVectorStore(_knowledge_path()).list_all()
