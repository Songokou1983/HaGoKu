"""Reporter 知识库管理 — 报表呈现模板经验"""

from __future__ import annotations

from pathlib import Path

from ...storage.knowledge_vector import KnowledgeVectorStore


def _knowledge_path() -> Path:
    return Path(__file__).parent / "knowledge.yaml"


def recall(query: str, top_k: int = 3) -> list[dict]:
    """检索最相关的报表模板经验"""
    store = KnowledgeVectorStore(_knowledge_path())
    return store.recall(query, top_k=top_k)


def learn(
    report_type: str,
    structure: str,
    visualizations: list[str] | None = None,
    tags: list[str] | None = None,
    metadata: dict | None = None,
) -> str:
    """
    记录一条报表模板经验。

    Returns:
        新条目 id
    """
    store = KnowledgeVectorStore(_knowledge_path())
    content = f"报告类型：{report_type}；结构：{structure}；可视化：{', '.join(visualizations or [])}"
    return store.add(
        content=content,
        tags=tags or [report_type, "报表模板"],
        metadata={
            **(metadata or {}),
            "report_type": report_type,
            "structure": structure,
            "visualizations": visualizations or [],
        },
    )


def list_all() -> list[dict]:
    """列出所有报表模板经验"""
    return KnowledgeVectorStore(_knowledge_path()).list_all()
