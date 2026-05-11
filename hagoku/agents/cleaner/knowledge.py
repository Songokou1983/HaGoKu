"""Cleaner 知识库管理 — 数据清洗策略经验"""

from __future__ import annotations

from pathlib import Path

from ...storage.knowledge_vector import KnowledgeVectorStore


def _knowledge_path() -> Path:
    return Path(__file__).parent / "knowledge.yaml"


def recall(query: str, top_k: int = 3) -> list[dict]:
    """检索最相关的清洗策略经验"""
    store = KnowledgeVectorStore(_knowledge_path())
    return store.recall(query, top_k=top_k)


def learn(
    condition: str,
    action: str,
    risk: str = "low",
    tags: list[str] | None = None,
    metadata: dict | None = None,
) -> str:
    """
    记录一条清洗策略经验。

    Returns:
        新条目 id
    """
    store = KnowledgeVectorStore(_knowledge_path())
    content = f"条件：{condition}；清洗动作：{action}；风险等级：{risk}"
    return store.add(
        content=content,
        tags=tags or ["清洗策略", risk, condition[:20]],
        metadata={
            **(metadata or {}),
            "condition": condition,
            "action": action,
            "risk": risk,
        },
    )


def list_all() -> list[dict]:
    """列出所有清洗策略经验"""
    return KnowledgeVectorStore(_knowledge_path()).list_all()
